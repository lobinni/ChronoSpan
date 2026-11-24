"""Interval engine: elapsed SI seconds, offset changes and signed shifts."""


def test_two_second_interval_across_the_2016_insertion(core, schedule):
    rows, expires = schedule["rows"], schedule["expires_ntp"]

    result = core["measure_span"](
        rows, expires, "2016-12-31T23:59:59Z", "2017-01-01T00:00:00Z"
    )

    assert result == {
        "start_atomic": 3692217635,
        "end_atomic": 3692217637,
        "elapsed_seconds": 2,
        "offset_changes": [[3692217600, 37]],
    }


def test_interval_through_the_inserted_second_is_one_second(core, schedule):
    rows, expires = schedule["rows"], schedule["expires_ntp"]

    result = core["measure_span"](
        rows, expires, "2016-12-31T23:59:59Z", "2016-12-31T23:59:60Z"
    )

    assert result["elapsed_seconds"] == 1
    assert result["offset_changes"] == []


def test_plain_interval_reports_no_offset_change(core, schedule):
    rows, expires = schedule["rows"], schedule["expires_ntp"]

    result = core["measure_span"](
        rows, expires, "2016-01-01T00:00:00Z", "2016-01-01T00:00:07Z"
    )

    assert result["elapsed_seconds"] == 7
    assert result["offset_changes"] == []


def test_zero_length_interval_is_zero_seconds(core, schedule):
    rows, expires = schedule["rows"], schedule["expires_ntp"]

    result = core["measure_span"](
        rows, expires, "2016-12-31T23:59:60Z", "2016-12-31T23:59:60Z"
    )

    assert result["elapsed_seconds"] == 0
    assert result["start_atomic"] == result["end_atomic"]


def test_reversed_interval_reverts(core, schedule):
    rows, expires = schedule["rows"], schedule["expires_ntp"]

    try:
        core["measure_span"](
            rows, expires, "2017-01-01T00:00:00Z", "2016-12-31T23:59:59Z"
        )
    except ValueError as error:
        assert "end label precedes start label" in str(error)
    else:
        raise AssertionError("reversed interval must revert")


def test_interval_cannot_start_before_coverage(core, schedule):
    rows, expires = schedule["rows"], schedule["expires_ntp"]

    try:
        core["measure_span"](
            rows, expires, "1971-01-01T00:00:00Z", "1972-01-01T00:00:00Z"
        )
    except ValueError as error:
        assert "outside schedule coverage" in str(error)
    else:
        raise AssertionError("out-of-coverage interval must revert")


def test_measure_across_the_whole_coverage_window(core, schedule):
    """First covered label to the last covered label: every transition in the
    table must be reported exactly once."""
    rows, expires = schedule["rows"], schedule["expires_ntp"]
    first = core["decode_label"](rows, expires, rows[0][0] + rows[0][1])
    last = core["decode_label"](rows, expires, expires + rows[-1][1] - 1)

    result = core["measure_span"](rows, expires, first, last)

    assert result["elapsed_seconds"] == (
        expires + rows[-1][1] - 1
    ) - (rows[0][0] + rows[0][1])
    assert len(result["offset_changes"]) == len(rows) - 1
    assert result["offset_changes"][-1] == [3692217600, 37]


def test_interval_spanning_a_whole_year_counts_every_inserted_second(
    core, schedule
):
    rows, expires = schedule["rows"], schedule["expires_ntp"]

    result = core["measure_span"](
        rows, expires, "2016-01-01T00:00:00Z", "2017-01-01T00:00:00Z"
    )

    # 2016 is a leap year: 366 civil days, one inserted SI second.
    assert result["elapsed_seconds"] == 366 * 86400 + 1
    assert result["offset_changes"] == [[3692217600, 37]]
