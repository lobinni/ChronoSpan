# Line-by-line comparison of the contract

Reference: `contracts/AtomicIntervalMeter.py` in
[`ehsandto/atomic-interval-meter`](https://github.com/ehsandto/atomic-interval-meter)
- 189 lines, one file, one contract class, four public methods.
Subject: `contracts/chrono_span.py` - 462 lines (the extra lines are section
banners, docstrings and the error catalogue), one file, one contract class,
ten public methods.

Both projects implement the same contract: leap-second aware interval
arithmetic over publisher-verified IERS/NIST tables, content-addressed and
settled by GenLayer consensus. This file records where every part of the
reference landed in the new code, and what was added, moved or renamed.

## 1. Module-level code

| Reference lines | Reference symbol | ChronoSpan lines | ChronoSpan symbol | Change |
| --- | --- | --- | --- | --- |
| 1 | `Depends` header | 1 | `Depends` header | same mechanism; SDK pin set to `py-genlayer:test` |
| - | - | 2-24 | module docstring | new: layout, evidence rules and what a caller may rely on, at the top of the file |
| 2-8 | imports | 26-33 | imports | `typing` added for annotations |
| 10-13 | `SOURCES` | 41-47 | `PUBLISHERS` | renamed; documented as two independent fetches |
| 14 | `EPOCH` | 52 | `COORDINATE_ORIGIN` | renamed to state what the origin is |
| 15-17 | `BASE_ROW`, `DAY`, `MAX_NTP` | 54-58 | `BASE_ROW`, `DAY`, `MAX_ROWS`, `MAX_BYTES`, `MAX_EXPIRY` | size and row-count bounds promoted to named constants |
| - | - | 60-67 | compiled `LABEL_RE`, `TABLE_ID_RE`, `ROW_RE`, `LIFETIME_RE`, `CHECKSUM_RE` | regexes compiled once and reused by tests and contract |
| - | - | 70-77 | `ERROR_*` catalogue | every revert message named once, documented in `docs/CONTRACT_API.md` |
| 20-21 | `canonical` | 80-84 | `canonical` | unchanged semantics, typed |
| 24-26 | `ntp` | 86-89 | `to_atomic` | renamed; identical arithmetic |
| 29-30 | `civil` | 91-93 | `to_civil` | renamed; identical arithmetic |
| - | - | 95-97 | `content_digest` | digest formula extracted so tests and contract share one definition |
| 33-76 | `parse_table` | 100-165 | `parse_leap_list` | same eight validation stages, split into single-purpose messages; regexes hoisted; quarter-day rule extracted to its own branch |
| 79-96 | `acquire` (record built inline) | 168-196 | `normalize` + `acquire` | earlier-expiry rule isolated in `normalize`, which now also rejects an empty source list |
| 99-117 | `encode_utc` | 204-238 | `encode_label` | adds a real-calendar-instant check (`2017-02-29T00:00:00Z` now reverts with its own message instead of a bare Python error) and a distinct message for a label outside coverage |
| 120-129 | `decode_utc` | 241-253 | `decode_label` | unchanged algorithm, named errors |
| - | - | 261-278 | `measure_span` | interval logic lifted out of the contract class so it is unit-testable |
| - | - | 281-286 | `shift_label` | signed move lifted out of the contract class |
| - | - | 289-310 | `next_transition` | **new**: next transition after a label, with the inserted label of a positive leap and `null` for a negative one |
| - | - | 318-323 | `read_table` | **new**: one place that validates a table id and reverts with a stable message |

## 2. Contract class

| Reference lines | Reference symbol | ChronoSpan lines | ChronoSpan symbol | Change |
| --- | --- | --- | --- | --- |
| 132-133 | `class AtomicIntervalMeter`, `tables: TreeMap[str, str]` | 331-338 | `class ChronoSpan`, `tables`, `order: DynArray[str]` | second storage field records insertion order |
| 135-136 | `__init__` | 340-342 | `__init__` | unchanged (VM zero-initialises storage) |
| 138-158 | `import_table` | 345-373 | `import_schedule` | same consensus primitive (`gl.vm.run_nondet_unsafe` with a byte-comparison validator); digest via `content_digest`; agreed id appended to `order` |
| 160-164 | `get_table` | 376-380 | `get_table` | id check and revert moved to `read_table` |
| - | - | 383-385 | `list_tables` | **new**: enumerate agreed ids |
| - | - | 388-398 | `table_meta` | **new**: digest, row count, expiry and publisher metadata without the row list |
| - | - | 401-410 | `coverage` | **new**: inclusive first / exclusive last label |
| 166-179 | `measure` | 413-426 | `measure` | delegates to `measure_span`; result now echoes `start_utc` and `end_utc` alongside the atomic coordinates |
| 181-189 | `advance` (signed seconds) | 429-437, 440-444, 447-451 | `shift`, `advance`, `rewind` | the single signed method became `shift`, with directional wrappers that reject a negative magnitude (`chronospan: duration must not be negative`) so a caller cannot rewind by +5 by mistake |
| - | - | 454-461 | `next_transition` view | **new**: the engine function exposed to callers |

## 3. Feature matrix

| Capability | Reference | ChronoSpan |
| --- | --- | --- |
| Two publishers downloaded independently by leader and validators | yes | yes |
| Publisher SHA-1 checksum verified per file | yes | yes |
| Cross-publisher transition rows must match | yes | yes |
| Effective expiry = earlier of the two | yes | yes |
| Full publisher metadata part of the agreed record | yes | yes |
| Table stored by content digest, immutable | yes | yes |
| Caller selects the table id, unknown id reverts | yes | yes |
| Labels outside coverage revert | yes | yes |
| Explicit `23:59:60Z` in both directions | yes | yes |
| Negative leap deletes `23:59:59Z` instead of inventing a second | yes | yes |
| Elapsed SI seconds between two labels | yes | yes |
| Offset changes inside the interval | yes | yes |
| Signed advance/rewind | one `advance(seconds)` | `shift(delta)` + `advance` + `rewind` |
| Enumerate agreed tables | no | `list_tables()` |
| Table metadata without the rows | no | `table_meta()` |
| Coverage endpoints as labels | no | `coverage()` |
| Next scheduled transition | no | `next_transition()` |
| Result echoes the caller's labels | no | `start_utc`, `end_utc` |
| Deterministic core unit-tested without a VM | yes (8 test functions, one file) | yes (46 tests, three files) |
| Consensus/storage tested in the VM harness | yes (1 combined test) | yes (10 tests) |
| Corrupt, truncated, oversized, duplicated-field files rejected | yes | yes (+8 parametrized cases) |
| Error messages | 11 ad-hoc strings | 9 catalogued, prefixed `chronospan:` |
| Frontend | none (Node proof scripts sit at the repository root) | separate `frontend/` workspace, excluded from submission |
| Documentation | `README.md` | `README.md` + 6 documents under `docs/` |

## 4. Contract content

| Field | Reference record | ChronoSpan record |
| --- | --- | --- |
| `schema` | `atomic-interval/v1` | `chronospan/v1` |
| `rows` | `[[ntp, offset], …]` | `[[ntp, offset], …]` (identical format) |
| `expires_ntp` | earlier publisher expiry | earlier publisher expiry |
| `sources` | `url`, `updated_ntp`, `expires_ntp`, `file_sha1` | identical keys |
| Digest | `sha256(canonical JSON)` | `sha256(canonical JSON)` (identical formula) |
| Key ordering | `json.dumps(sort_keys=True, separators=(",", ":"))` | identical |

The record format is deliberately unchanged: it is the format the publishers'
own data normalizes into, and keeping it means the two projects' fixtures are
interchangeable.

## 5. Verdict

Everything the reference contract does, ChronoSpan does with the same rules
and the same evidence standard. What changed is the shape of the code (pure
core separated from the GenVM shell so it can be tested without a VM), the
public surface (four methods -> ten, all of them documented), the error
contract (catalogued, prefixed, asserted in tests) and the repository layout
(contracts-only submission, frontend and samples kept outside it).
