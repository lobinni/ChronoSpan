# Testing

> Every command below runs from the `intelligent/` folder — the submission
> root — unless stated otherwise.

Three tiers. The first runs anywhere, in milliseconds, with no network and no
VM. The second exercises consensus and storage inside the GenVM direct-mode
harness. The third re-reads the deployed instance and asserts the same
behaviour over RPC.

```sh
python -m pip install -r requirements-dev.txt   # tiers 1-2 + linter (Python >= 3.12)

python -m pytest tests/test_*.py -q             # tier 1: plain pytest is enough
python -m pytest tests -q                       # tiers 1-2
genvm-lint check contracts/chrono_span.py       # static analysis before deploy

npm install genlayer-js
node samples/verify_deployment.mjs              # tier 3: live instance
```

## Tier 1 - deterministic core (`tests/test_*.py`)

`tests/conftest.py` parses `contracts/chrono_span.py` with `ast`, removes the
`genlayer` import and the `ChronoSpan` class, and executes the remaining
module. Every function from section `00` to `03` therefore runs under plain
CPython against the *real* contract source - not a copy.

| File | Tests | Covers |
| --- | --- | --- |
| `test_schedule.py` | 18 | both publisher formats, checksum verification, corrupt/truncated/oversized/duplicated files, cross-publisher row disagreement, the earlier-expiry rule, unreachable publisher, canonical form, content digest, the golden fixture table id, canned sample files |
| `test_label_codec.py` | 20 | strict label grammar, the 2016 insertion in both directions, a round-trip over every scheduled transition, false leap labels, impossible dates, coverage bounds, negative-leap label deletion, `next_transition` (single and chained across the whole table), signed shifts |
| `test_intervals.py` | 8 | the two-second interval across the 2016 insertion, intervals through the inserted second, zero-length and reversed intervals, out-of-coverage starts, the full coverage window, a full leap year with its inserted second |

Fixtures:

* `core` - the executed contract namespace (session-scoped),
* `schedule` - `tests/fixtures/schedule.json`, the normalized record both
  publishers are expected to agree on,
* `document(index, rows=…, expires=…)` - rebuilds a publisher file from the
  fixture so a test can corrupt exactly one field,
* `fetcher(bodies=…, status=…)` - a recording `fetch` replacement.

### The test cases the brief asks for

| Requirement | Test |
| --- | --- |
| import of both publisher formats | `test_both_publishers_normalize_to_the_same_record` |
| two-second interval across the 2016 insertion | `test_two_second_interval_across_the_2016_insertion` |
| forward navigation through `23:59:60Z` | `test_shift_navigates_forward_and_backward_through_the_inserted_label` (`+1`, `+2`) |
| reverse navigation through `23:59:60Z` | the same test (`-1`, `-2`) |
| rejection of a false leap label | `test_rejects_labels_the_schedule_does_not_contain` (`2016-12-30T23:59:60Z`, `23:59:61Z`, `23:58:60Z`) |
| rejection of dates outside coverage | the same test (`1971-12-31…`, `2029-01-01…`, `9999-…`) |
| publisher checksum verified | `test_rejects_corrupt_or_incomplete_publisher_files` |
| transition rows must match | `test_disagreeing_transition_rows_are_rejected` |
| earlier expiry wins | `test_effective_expiry_is_the_earlier_publisher_expiry` |
| content-addressed table id | `test_content_digest_addresses_the_record_not_the_caller`, `test_fixture_record_has_a_stable_content_id` |
| negative leap deletes a label | `test_negative_leap_deletes_a_label` |
| the same over RPC | `samples/verify_deployment.mjs` checks 4-10 |

## Tier 2 - contract behaviour (`tests/direct/`)

Runs the contract in the GenVM harness with mocked downloads. The directory
skips itself when `genlayer-test` is not installed, so a bare
`pytest tests` never fails for lack of it.

| Test | Covers |
| --- | --- |
| `test_import_stores_one_content_addressed_record` | digest-shaped id, full record read-back, idempotent re-import, `list_tables`, `table_meta`, `coverage` |
| `test_measure_counts_two_seconds_across_the_2016_insertion` | elapsed 2 s, both atomic endpoints, the `[[3692217600, 37]]` change |
| `test_advance_and_rewind_walk_through_the_inserted_label` | `23:59:59Z → 23:59:60Z → 00:00:00Z` and the reverse, plus `shift` |
| `test_next_transition_describes_the_upcoming_leap` | transition payload, `None` past the last transition |
| `test_reversed_interval_reverts` | `end label precedes start label` |
| `test_unknown_table_id_reverts` | malformed and unknown digests |
| `test_label_outside_coverage_reverts` | pre-1972 dates and a false leap label |
| `test_signed_duration_must_not_be_negative` | `advance`/`rewind` reject negative input |
| `test_disagreeing_publishers_revert_the_import` | revert on row disagreement, existing table untouched |
| `test_validator_accepts_matching_evidence_and_rejects_a_forged_record` | `run_validator()` accepts identical evidence and rejects a leader record whose expiry was altered |

Mock shape used for the publisher downloads:

```python
direct_vm.mock_web(re.escape(url) + "$", {
    "method": "GET",
    "response": {"status": 200, "headers": {}, "body": document(index)},
})
```

## Tier 3 - live deployment (`samples/verify_deployment.mjs`)

Read-only, no wallet, no gas. Address comes from
`deployments/chronospan.studionet.json` unless you pass one:

```sh
node samples/verify_deployment.mjs
node samples/verify_deployment.mjs 0x499D1d2b5ee169b89Fa20aB426B754E8579EE2dd
```

Thirteen checks, exit code 0 only when all pass:

1. `list_tables()` returns at least one id, all 64-hex;
2. `table_meta` reports schema `chronospan/v1`, 28 transitions and both
   publisher hosts;
3. `coverage()` starts at `1972-01-01T00:00:00Z` and ends after it;
4. `measure(2016-12-31T23:59:59Z, 2017-01-01T00:00:00Z)` = **2** seconds;
5. the same call reports `[[3692217600, 37]]` and echoes the table id;
6. `advance(+1)` reaches `2016-12-31T23:59:60Z`;
7. `rewind(-2)` returns to `2016-12-31T23:59:59Z`;
8. `next_transition` reports the inserted label and `2017-01-01T00:00:00Z`;
9. an unknown table id reverts;
10. a label before coverage reverts;
11. a false leap label reverts;
12. a reversed interval reverts;
13. every table id read back is the id that was requested.

What tier 3 does *not* prove: that the stored table came from honest
publisher evidence. That is decided once, at import time, by consensus - see
`docs/CONSENSUS_INPUT.md`.

## Lint

```sh
genvm-lint check contracts/chrono_span.py
```

The linter checks storage types, decorators, return annotations, forbidden
imports and that non-deterministic calls are only reachable from a consensus
block. `gl.nondet.web.get` appears once, as an argument handed to
`evaluate`, which is passed to `gl.vm.run_nondet_unsafe` - if your linter
build reports `E010` for it, that is the known false positive for indirect
nondet references; the call is inside the consensus block by construction.

## Adding a test

1. Pure behaviour (parsing, labels, arithmetic) -> a new function in an
   existing `tests/test_*.py`, using `core` and `schedule`. No imports from
   `genlayer` are allowed in those files.
2. Behaviour that needs storage, reverts or consensus -> `tests/direct/`,
   deploying with `direct_deploy("contracts/chrono_span.py")`.
3. Behaviour that must hold on chain -> extend
   `samples/verify_deployment.mjs` with one more `check(...)` and add a row
   to the table above.
4. Keep every assertion about a *stable* message from the error catalogue in
   `docs/CONTRACT_API.md`; those strings are part of the API.
5. Re-run all three tiers before committing, and keep the counts in
   `README.md`, `docs/ARCHITECTURE.md` and the site in sync with
   `python -m pytest tests --collect-only -q`.
