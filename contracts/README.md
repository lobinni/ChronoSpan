# contracts/ — the submission unit

Everything a GenLayer submission needs is in this folder. Nothing else in the
repository ships with it: no frontend, no build step, no Python dependencies
beyond the GenVM runtime.

| File | Contents |
| --- | --- |
| [`chrono_span.py`](chrono_span.py) | the `ChronoSpan` contract — 462 lines, one class, ten public methods |

```sh
genvm-lint check contracts/chrono_span.py    # static analysis
python -m pytest tests -q                    # 46 deterministic + 10 harness tests
gltest --network studionet deploy contracts/chrono_span.py
```

## Layout inside the file

| Lines | Section | Contents |
| --- | --- | --- |
| 1 | header | `Depends` pin for the GenVM runtime |
| 2–24 | docstring | what the contract does and how the file is organized |
| 39–77 | 00 constants | publisher endpoints, coordinate origin, bounds, compiled patterns, error catalogue |
| 80–196 | 00 helpers | canonical JSON, atomic conversions, digest, publisher parsing, agreement, normalization |
| 204–253 | 01 label codec | `encode_label`, `decode_label` — including `23:59:60Z` |
| 261–310 | 02 interval engine | `measure_span`, `shift_label`, `next_transition` |
| 318–323 | 03 consensus input | `read_table`, the only GenVM-specific helper |
| 331–462 | 04 public surface | `class ChronoSpan(gl.Contract)` |

Sections 00–03 are pure: `tests/conftest.py` executes them under plain CPython
with the GenVM import and the contract class stripped away, so the logic that
decides every answer is unit-testable without a VM.

## Public surface

`import_schedule` (write) plus `get_table`, `list_tables`, `table_meta`,
`coverage`, `measure`, `shift`, `advance`, `rewind`, `next_transition` (views).
Signatures, return shapes and the revert catalogue:
[`../docs/CONTRACT_API.md`](../docs/CONTRACT_API.md).

## Rules the file never breaks

1. No wall clock, no floats, no time zones — whole SI seconds only.
2. The single `gl.nondet.*` call sits inside `evaluate`, which is passed to
   `gl.vm.run_nondet_unsafe`; validators compare canonical JSON byte for byte.
3. Records are written once under their content digest and never mutated.
4. Every failure is one of the nine catalogued `chronospan:` messages.
