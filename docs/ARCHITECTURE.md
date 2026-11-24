# Architecture

ChronoSpan is a single deployable GenVM source unit plus a test-suite that
runs the same source under plain CPython. This document explains the layers,
the data flow and the rules that keep the contract deterministic.

## 1. Why the contract is one file

GenVM deploys one Python source unit; that file *is* the artifact. Contract
code cannot lean on a package of imported modules the way an application
does, so ChronoSpan keeps `contracts/chrono_span.py` self-contained and
organizes it with numbered section banners instead of package boundaries:

| Section | Contents | Pure? |
| --- | --- | --- |
| `00` constants | publisher endpoints, coordinate origin, bounds, compiled patterns, error catalogue | yes |
| `00` helpers | `canonical`, `to_atomic`, `to_civil`, `content_digest`, `parse_leap_list`, `normalize`, `acquire` | yes |
| `01` label codec | `encode_label`, `decode_label` | yes |
| `02` interval engine | `measure_span`, `shift_label`, `next_transition` | yes |
| `03` consensus input | `read_table` (the only place that touches `gl.vm`) | no |
| `04` public surface | `ChronoSpan(gl.Contract)` | no |

Everything above section `03` is deterministic, side-effect free and unit
testable without a VM. `tests/conftest.py` proves the split: it parses the
contract with `ast`, drops the `genlayer` import and the contract class, and
executes the rest. 46 assertions run that way in milliseconds.

The only GenVM-specific surface is:

* storage declarations (`TreeMap`, `DynArray`),
* decorators (`@gl.public.write`, `@gl.public.view`),
* non-deterministic input (`gl.nondet.web.get`),
* consensus (`gl.vm.run_nondet_unsafe`),
* errors (`gl.vm.UserError`).

## 2. Data flow

```
                 import_schedule()  - permissionless, no caller evidence
                          |
        +-----------------+------------------+
        | leader                              | validator 1..n
        v                                     v
   gl.nondet.web.get(url)  <--- IERS list ---+--- NIST list
        |                                     |
        +--> parse_leap_list()  : size, metadata, baseline row,
        |                       transitions, quarter-day rule,
        |                       publisher SHA-1 checksum
        +--> acquire()          : identical rows across publishers
        +--> normalize()        : earlier of the two expiry fields
        v
   canonical(record)  -- byte-identical string required on every node
        |
   gl.vm.run_nondet_unsafe(evaluate, validate)
        |
   table_id = sha256(canonical record)
        |
   tables[table_id] = record     (written once, never mutated)
   order.append(table_id)        (insertion order, enumeration only)
        |
        +--> measure / shift / advance / rewind / next_transition
             every call names an explicit table_id
```

## 3. Storage

| Field | Type | Meaning |
| --- | --- | --- |
| `tables` | `TreeMap[str, str]` | `table_id` (64 hex chars) → canonical record JSON |
| `order` | `DynArray[str]` | agreed ids in the order the network agreed them |

Records are immutable: `import_schedule` writes a key only when it is absent,
so a repeated import of identical evidence is a no-op that still returns the
same id, and a repeated import of *different* evidence yields a different id
that coexists with the first. Nothing ever edits a stored record.

## 4. Determinism rules

1. **No wall clock.** Nothing calls `datetime.now()` or reads the system
   time. Every answer is a function of the labels supplied by the caller and
   the table the caller selected.
2. **No non-determinism outside consensus.** The only `gl.nondet.*` call sits
   inside `evaluate`, which is handed to `gl.vm.run_nondet_unsafe`. The
   validator re-runs it and must produce byte-identical JSON.
3. **Canonical JSON.** `canonical()` sorts keys and strips whitespace so the
   comparison is over bytes, not over dict ordering.
4. **Errors are typed.** The pure core raises `ValueError`; the public
   boundary converts to `gl.vm.UserError` with a stable, greppable message.
5. **Integer arithmetic only.** Atomic coordinates are whole SI seconds from
   1900-01-01T00:00:00. No floats, no rounding, no time zones.

## 5. Identity and coverage

* `table_id = sha256(canonical_record)` - the table is content-addressed.
* Coverage is `[rows[0][0], expires_ntp)` on the atomic axis; `coverage()`
  reports it as an inclusive first label and an exclusive last label.
* A label before the first covered second, at or after the exclusive end, or
  one the schedule does not contain (`23:59:60Z` on a non-leap night, a
  deleted second under a negative leap) reverts instead of rounding.

## 6. Separation from the frontend

This document describes `intelligent/` — the folder that is submitted. The
repository around it is split so that a submission never carries UI code:

```
intelligent/     the GenLayer Intelligent Contracts submission
  contracts/     the submission unit: Python Intelligent Contracts only
  deployments/   one JSON record per deployed instance (address, source hash)
  tests/         deterministic suite (no VM) + direct-mode suite (genlayer-test)
  docs/          architecture, API, consensus input, testing, deployment,
                 samples, comparison
  samples/       runnable scripts a coder can copy to exercise the contract
  SUBMISSION.md  the evidence list that ships with the contract
frontend/                          the documentation site - never submitted
index.html · package.json · vite.config.ts   the site's build shell - never submitted
```

Nothing outside `intelligent/contracts/` is required to run, deploy or submit
the contract. `deployments/` records where a copy of it lives, `tests/` proves
its behaviour, `docs/` and `samples/` explain and demonstrate it, and the
frontend is only an optional reader of the deployed address.

`frontend/` has its own toolchain, its own dependencies and its own build.
Deploying or submitting ChronoSpan means sending `contracts/` and nothing
else; see `frontend/README.md`.
