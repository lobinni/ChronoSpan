# ChronoSpan

**This folder is the GenLayer submission.** Everything needed to lint, test,
deploy and verify the Intelligent Contract is here; nothing from
[`../frontend/`](../frontend/README.md) ships with it.

> Every command in this document runs from `intelligent/`.

Leap-second aware UTC interval arithmetic as a GenLayer Intelligent Contract.

ChronoSpan measures elapsed SI seconds between whole-second UTC labels and
moves a label forward or backward by a signed duration. The inserted label
`23:59:60Z` is a first-class value: accepted on input, produced on output,
round-tripped in both directions. The interval from `23:59:59Z` on
31 December 2016 to `00:00:00Z` on 1 January 2017 is **two** SI seconds, and
the contract says so, together with the offset change that caused it.

The leader and every validator independently download the IERS and NIST
leap-second lists, parse every transition, verify each publisher's checksum,
require the transition rows to match and take the earlier expiry. Exact
agreement on the canonical record - including both publishers' metadata - is
required before anything is stored. The agreed table is kept under the
SHA-256 of its canonical JSON; callers select that immutable table id, and
labels outside its coverage revert.

## Deployed instance

| | |
| --- | --- |
| Network | Studionet |
| Address | [`0x499D1d2b5ee169b89Fa20aB426B754E8579EE2dd`](https://explorer-studio.genlayer.com/address/0x499D1d2b5ee169b89Fa20aB426B754E8579EE2dd) |
| Source | `contracts/chrono_span.py` — `sha256 8a6412255eb6dd0c941af3187f1005f3b5c628cbc6aeb182f722acf2d07eac27` |
| Record | [`deployments/chronospan.studionet.json`](deployments/chronospan.studionet.json) |
| Verify | `node samples/verify_deployment.mjs` |
| Docs | [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md) |

## Layout

```
contracts/chrono_span.py     the submission unit - one GenVM source file
contracts/README.md          section map of that file
deployments/                 one JSON record per deployed instance
tests/conftest.py            executes the contract core without a VM
tests/test_*.py              46 deterministic tests (plain pytest)
tests/direct/                10 consensus/storage tests (genlayer-test)
docs/                        architecture, API, consensus, testing, deployment,
                             samples, and the line-by-line comparison with the
                             reference contract
samples/                     offline demo, publisher files, deploy script,
                             genlayer-js reader, live verifier
SUBMISSION.md                the text submitted with the contract
requirements-dev.txt         genlayer-test, genvm-linter, pytest
pyproject.toml  gltest.config.yaml
```

Out of scope, at the repository root: `frontend/` (the documentation site)
and `index.html` / `package.json` / `vite.config.ts` (its build shell).
See [`../frontend/README.md`](../frontend/README.md).

## Quick start

```sh
python -m pip install -r requirements-dev.txt

python -m pytest tests/test_*.py -q     # deterministic core, no VM needed
python -m pytest tests -q               # adds the direct-mode suite
genvm-lint check contracts/chrono_span.py

python samples/local_demo.py            # whole flow, offline, printable

node samples/verify_deployment.mjs      # live checks against the deployed address
```

## Contract surface

| Method | Kind | Purpose |
| --- | --- | --- |
| `import_schedule()` | write | download, verify and agree both publisher lists; returns the content digest |
| `get_table(table_id)` | view | full agreed record |
| `list_tables()` | view | agreed ids in insertion order |
| `table_meta(table_id)` | view | digest, row count, expiry, publisher metadata |
| `coverage(table_id)` | view | inclusive first / exclusive last label |
| `measure(table_id, start, end)` | view | elapsed SI seconds + offset changes |
| `shift(table_id, label, delta)` | view | signed move |
| `advance(table_id, label, seconds)` | view | forward move |
| `rewind(table_id, label, seconds)` | view | backward move |
| `next_transition(table_id, after)` | view | next leap-second transition |

Signatures, return shapes and the full revert catalogue:
[`docs/CONTRACT_API.md`](docs/CONTRACT_API.md).

## Determinism

* No wall clock, no floats, no time zones - integer SI seconds from
  1900-01-01T00:00:00, converted through the agreed TAI-UTC offsets.
* The only non-deterministic call is `gl.nondet.web.get`, reached through
  `gl.vm.run_nondet_unsafe`, whose validator re-runs the whole pipeline and
  compares canonical JSON byte for byte.
* Storage is two fields: `tables: TreeMap[str, str]` (id → record) and
  `order: DynArray[str]` (insertion order). Records are written once and
  never mutated.

## Tests

| Tier | Count | Needs | Command |
| --- | --- | --- | --- |
| Deterministic core | 46 | plain pytest | `python -m pytest tests/test_*.py -q` |
| Consensus + storage | 10 | genlayer-test | `python -m pytest tests -q` |
| Live deployment | 13 | genlayer-js | `node samples/verify_deployment.mjs` |

Covered explicitly: import and content addressing, a two-second interval
across the 2016 insertion, forward and reverse navigation through
`23:59:60Z`, rejection of a false leap label, rejection of dates outside
coverage, publisher checksum failures, cross-publisher disagreement, the
earlier-expiry rule, a forged leader record refused by the validator, and the
same behaviours re-read from the deployed instance. Test guide:
[`docs/TESTING.md`](docs/TESTING.md).

## Documentation

| File | Contents |
| --- | --- |
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | layers, data flow, storage, determinism rules |
| [`docs/CONTRACT_API.md`](docs/CONTRACT_API.md) | methods, records, labels, error catalogue |
| [`docs/CONSENSUS_INPUT.md`](docs/CONSENSUS_INPUT.md) | publisher checks, agreement, identity, coverage |
| [`docs/TESTING.md`](docs/TESTING.md) | all three test tiers, fixtures, lint, how to add a test |
| [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md) | deploy, record, source check, live verification |
| [`docs/SAMPLES.md`](docs/SAMPLES.md) | how to run every sample |
| [`docs/SAMPLE_COMPARISON.md`](docs/SAMPLE_COMPARISON.md) | line-by-line comparison with the reference contract |
| [`SUBMISSION.md`](SUBMISSION.md) | the submission text and evidence list |

## Sources

* [IERS Bulletin C — leap-seconds.list](https://hpiers.obspm.fr/iers/bul/bulc/ntp/leap-seconds.list)
* [NIST — leap seconds](https://www.nist.gov/pml/time-and-frequency-division/time-realization-leap-seconds)

ChronoSpan trusts the publishers for scheduling, dual publication plus
consensus for provenance, and the caller for nothing: labels are validated
against the selected table, and everything else reverts.
