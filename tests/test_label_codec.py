"""UTC label codec: strict whole-second input, an explicit 23:59:60Z,
coverage bounds and the deleted second of a negative leap."""

from datetime import datetime, timedelta

import pytest


def rows_of(schedule):
    return schedule["rows"], schedule["expires_ntp"]


def test_encodes_and_decodes_the_2016_insertion(core, schedule):
    rows, expires = rows_of(schedule)
    labels = [
        "2016-12-31T23:59:59Z",
        "2016-12-31T23:59:60Z",
        "2017-01-01T00:00:00Z",
    ]
    atomic = [3692217635, 3692217636, 3692217637]

    assert [core["encode_label"](rows, expires, label) for label in labels] == atomic
    assert [core["decode_label"](rows, expires, stamp) for stamp in atomic] == labels


def test_round_trip_across_every_scheduled_transition(core, schedule):
    rows, expires = rows_of(schedule)
    for effective, after in rows[1:]:
        midnight = datetime(1900, 1, 1) + timedelta(seconds=effective)
        preceding = (midnight - timedelta(seconds=1)).isoformat()
        labels = [
            preceding + "Z",
            preceding[:-2] + "60Z",
            midnight.isoformat() + "Z",
        ]
        expected = [effective + after - 2, effective + after - 1, effective + after]

        assert [core["encode_label"](rows, expires, label) for label in labels] == expected
        assert [core["decode_label"](rows, expires, stamp) for stamp in expected] == labels


@pytest.mark.parametrize(
    "label, message",
    [
        ("2016-12-30T23:59:60Z", "does not exist"),
        ("2016-12-31T23:58:60Z", "does not exist"),
        ("2016-12-31T23:59:61Z", "whole-second"),
        ("2017-01-01T00:00:60Z", "does not exist"),
        ("2017-02-29T00:00:00Z", "not a real calendar instant"),
        ("2017-01-01T00:00:00+00:00", "whole-second"),
        ("2017-01-01 00:00:00Z", "whole-second"),
        ("", "whole-second"),
        ("1971-12-31T23:59:59Z", "outside schedule coverage"),
        ("1971-12-31T23:59:60Z", "outside schedule coverage"),
        ("2029-01-01T00:00:00Z", "outside schedule coverage"),
        ("9999-12-31T23:59:59Z", "outside schedule coverage"),
    ],
)
def test_rejects_labels_the_schedule_does_not_contain(core, schedule, label, message):
    rows, expires = rows_of(schedule)
    with pytest.raises(ValueError, match=message):
        core["encode_label"](rows, expires, label)


def test_coverage_bounds_are_inclusive_then_exclusive(core, schedule):
    rows, expires = rows_of(schedule)
    first = core["decode_label"](rows, expires, rows[0][0] + rows[0][1])
    last = core["decode_label"](rows, expires, expires + rows[-1][1] - 1)

    assert first == "1972-01-01T00:00:00Z"
    assert core["encode_label"](rows, expires, first) == rows[0][0] + rows[0][1]

    # One second past the exclusive bound must revert, not round.
    with pytest.raises(ValueError, match="outside schedule coverage"):
        core["decode_label"](rows, expires, expires + rows[-1][1])
    with pytest.raises(ValueError, match="outside schedule coverage"):
        core["encode_label"](rows, expires, "2029-01-01T00:00:00Z")

    # The last covered label still round-trips.
    assert core["encode_label"](rows, expires, last) == expires + rows[-1][1] - 1


def test_negative_leap_deletes_a_label(core):
    """A negative leap removes 23:59:59Z instead of inserting 23:59:60Z.
    The codec must refuse both rather than invent an instant."""
    moment = 2287785600  # 1972-07-01T00:00:00Z
    rows = [[2272060800, 10], [moment, 9]]
    expires = moment + 86400

    assert core["encode_label"](rows, expires, "1972-06-30T23:59:58Z") == moment + 8
    assert core["decode_label"](rows, expires, moment + 8) == "1972-06-30T23:59:58Z"
    assert core["decode_label"](rows, expires, moment + 9) == "1972-07-01T00:00:00Z"

    with pytest.raises(ValueError, match="does not exist"):
        core["encode_label"](rows, expires, "1972-06-30T23:59:59Z")
    with pytest.raises(ValueError, match="does not exist"):
        core["encode_label"](rows, expires, "1972-06-30T23:59:60Z")


def test_next_transition_reports_the_inserted_label(core, schedule):
    rows, expires = rows_of(schedule)

    forward = core["next_transition"](rows, expires, "2016-06-01T00:00:00Z")
    assert forward == {
        "effective_utc": "2017-01-01T00:00:00Z",
        "inserted_utc": "2016-12-31T23:59:60Z",
        "old_offset": 36,
        "new_offset": 37,
        "atomic": 3692217637,
    }

    # Strictly after: the transition itself is not reported again.
    assert core["next_transition"](rows, expires, "2017-01-01T00:00:00Z") is None
    assert core["next_transition"](rows, expires, "2020-01-01T00:00:00Z") is None

    first = core["next_transition"](rows, expires, "1972-01-01T00:00:00Z")
    assert first["effective_utc"] == "1972-07-01T00:00:00Z"
    assert first["inserted_utc"] == "1972-06-30T23:59:60Z"
    assert (first["old_offset"], first["new_offset"]) == (10, 11)


def test_next_transition_walks_every_scheduled_leap(core, schedule):
    """Chaining next_transition from 1972 must visit every row of the table
    once, in order, and then stop."""
    rows, expires = rows_of(schedule)
    seen = []
    after = "1972-01-01T00:00:00Z"

    while True:
        upcoming = core["next_transition"](rows, expires, after)
        if upcoming is None:
            break
        seen.append(upcoming["effective_utc"])
        after = upcoming["effective_utc"]
        assert len(seen) <= len(rows)

    assert len(seen) == len(rows) - 1
    assert seen[0] == "1972-07-01T00:00:00Z"
    assert seen[-1] == "2017-01-01T00:00:00Z"
    assert core["next_transition"](rows, expires, seen[-1]) is None


def test_shift_navigates_forward_and_backward_through_the_inserted_label(
    core, schedule
):
    rows, expires = rows_of(schedule)
    before = "2016-12-31T23:59:59Z"
    inserted = "2016-12-31T23:59:60Z"
    midnight = "2017-01-01T00:00:00Z"

    assert core["shift_label"](rows, expires, before, 1) == inserted
    assert core["shift_label"](rows, expires, before, 2) == midnight
    assert core["shift_label"](rows, expires, inserted, -1) == before
    assert core["shift_label"](rows, expires, midnight, -1) == inserted
    assert core["shift_label"](rows, expires, midnight, -2) == before
    assert core["shift_label"](rows, expires, before, 0) == before


def test_shift_past_the_end_of_coverage_reverts(core, schedule):
    rows, expires = rows_of(schedule)
    last = core["decode_label"](rows, expires, expires + rows[-1][1] - 1)

    with pytest.raises(ValueError, match="outside schedule coverage"):
        core["shift_label"](rows, expires, last, 1)
