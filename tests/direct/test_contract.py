"""Consensus and storage behaviour of ChronoSpan, exercised through the
genlayer-test direct-mode harness: mocked publisher downloads, an in-memory
VM, revert assertions and a validator round-trip.

These tests need ``pip install -r requirements-dev.txt``.  Everything that
does not need a VM lives in ``tests/test_*.py`` and runs under plain
``pytest``.
"""

import json
import re

PUBLISHERS = [
    "https://hpiers.obspm.fr/iers/bul/bulc/ntp/leap-seconds.list",
    "https://tf.nist.gov/leap-seconds.list",
]
SOURCE = "contracts/chrono_span.py"


def install(direct_vm, document, bodies=None):
    """Answer both publisher downloads with well-formed files."""
    direct_vm.clear_mocks()
    for index, url in enumerate(PUBLISHERS):
        direct_vm.mock_web(
            re.escape(url) + "$",
            {
                "method": "GET",
                "response": {
                    "status": 200,
                    "headers": {},
                    "body": document(index) if bodies is None else bodies[index],
                },
            },
        )


def test_import_stores_one_content_addressed_record(
    direct_vm, direct_deploy, document, schedule
):
    contract = direct_deploy(SOURCE)
    install(direct_vm, document)

    table_id = contract.import_schedule()

    assert re.fullmatch(r"[0-9a-f]{64}", table_id)
    record = contract.get_table(table_id)
    assert record["schema"] == "chronospan/v1"
    assert record["rows"] == schedule["rows"]
    assert record["expires_ntp"] == schedule["expires_ntp"]
    assert record["sources"] == schedule["sources"]

    # Re-importing identical evidence reuses the same immutable id.
    assert contract.import_schedule() == table_id
    assert contract.list_tables() == [table_id]

    meta = contract.table_meta(table_id)
    assert meta["table_id"] == table_id
    assert meta["transition_count"] == len(schedule["rows"])
    assert len(meta["sources"]) == 2

    coverage = contract.coverage(table_id)
    assert coverage["first_utc"] == "1972-01-01T00:00:00Z"
    assert coverage["last_utc_exclusive"] > coverage["first_utc"]


def test_measure_counts_two_seconds_across_the_2016_insertion(
    direct_vm, direct_deploy, document
):
    contract = direct_deploy(SOURCE)
    install(direct_vm, document)
    table_id = contract.import_schedule()

    result = contract.measure(
        table_id, "2016-12-31T23:59:59Z", "2017-01-01T00:00:00Z"
    )

    assert result["elapsed_seconds"] == 2
    assert result["start_atomic"] == 3692217635
    assert result["end_atomic"] == 3692217637
    assert result["offset_changes"] == [[3692217600, 37]]
    assert result["table_id"] == table_id


def test_advance_and_rewind_walk_through_the_inserted_label(
    direct_vm, direct_deploy, document
):
    contract = direct_deploy(SOURCE)
    install(direct_vm, document)
    table_id = contract.import_schedule()

    before = "2016-12-31T23:59:59Z"
    inserted = "2016-12-31T23:59:60Z"
    midnight = "2017-01-01T00:00:00Z"

    assert contract.advance(table_id, before, 1) == inserted
    assert contract.advance(table_id, inserted, 1) == midnight
    assert contract.rewind(table_id, midnight, 1) == inserted
    assert contract.rewind(table_id, midnight, 2) == before
    assert contract.shift(table_id, before, -1) == "2016-12-31T23:59:58Z"
    assert contract.shift(table_id, inserted, 0) == inserted


def test_next_transition_describes_the_upcoming_leap(
    direct_vm, direct_deploy, document
):
    contract = direct_deploy(SOURCE)
    install(direct_vm, document)
    table_id = contract.import_schedule()

    upcoming = contract.next_transition(table_id, "2016-06-01T00:00:00Z")
    assert upcoming["effective_utc"] == "2017-01-01T00:00:00Z"
    assert upcoming["inserted_utc"] == "2016-12-31T23:59:60Z"
    assert contract.next_transition(table_id, "2020-01-01T00:00:00Z") is None


def test_reversed_interval_reverts(
    direct_vm, direct_deploy, document, schedule
):
    contract = direct_deploy(SOURCE)
    install(direct_vm, document)
    table_id = contract.import_schedule()

    with direct_vm.expect_revert("end label precedes start label"):
        contract.measure(table_id, "2017-01-01T00:00:00Z", "2016-12-31T23:59:59Z")


def test_unknown_table_id_reverts(direct_vm, direct_deploy, document):
    contract = direct_deploy(SOURCE)
    install(direct_vm, document)
    contract.import_schedule()

    with direct_vm.expect_revert("unknown table id"):
        contract.get_table("0" * 64)
    with direct_vm.expect_revert("unknown table id"):
        contract.measure("not-a-digest", "2017-01-01T00:00:00Z", "2017-01-01T00:00:01Z")


def test_label_outside_coverage_reverts(direct_vm, direct_deploy, document):
    contract = direct_deploy(SOURCE)
    install(direct_vm, document)
    table_id = contract.import_schedule()

    with direct_vm.expect_revert("outside schedule coverage"):
        contract.measure(table_id, "1971-12-31T23:59:59Z", "1972-01-01T00:00:00Z")
    with direct_vm.expect_revert("does not exist"):
        contract.advance(table_id, "2016-12-30T23:59:60Z", 1)


def test_signed_duration_must_not_be_negative(direct_vm, direct_deploy, document):
    contract = direct_deploy(SOURCE)
    install(direct_vm, document)
    table_id = contract.import_schedule()

    with direct_vm.expect_revert("duration must not be negative"):
        contract.advance(table_id, "2017-01-01T00:00:00Z", -1)
    with direct_vm.expect_revert("duration must not be negative"):
        contract.rewind(table_id, "2017-01-01T00:00:00Z", -1)


def test_disagreeing_publishers_revert_the_import(
    direct_vm, direct_deploy, document, schedule
):
    contract = direct_deploy(SOURCE)
    install(direct_vm, document)
    table_id = contract.import_schedule()

    shortened = document(1, rows=schedule["rows"][:-1])
    install(direct_vm, document, bodies=[document(0), shortened])

    with direct_vm.expect_revert("publisher evidence unavailable or inconsistent"):
        contract.import_schedule()

    # A failed import never disturbs an already agreed record.
    assert contract.get_table(table_id)["rows"] == schedule["rows"]
    assert contract.list_tables() == [table_id]


def test_validator_accepts_matching_evidence_and_rejects_a_forged_record(
    direct_vm, direct_deploy, document, schedule
):
    contract = direct_deploy(SOURCE)
    install(direct_vm, document)
    table_id = contract.import_schedule()
    record = contract.get_table(table_id)

    assert direct_vm.run_validator()

    forged = dict(record)
    forged["expires_ntp"] = record["expires_ntp"] + 1
    leader_result = json.dumps(forged, sort_keys=True, separators=(",", ":"))

    assert not direct_vm.run_validator(leader_result=leader_result)
    assert contract.get_table(table_id)["expires_ntp"] == schedule["expires_ntp"]
