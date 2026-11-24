# Samples

Everything in `samples/` is runnable code a coder can copy. None of it is
part of the contract submission.

| Sample | Needs | What it shows |
| --- | --- | --- |
| `samples/local_demo.py` | plain Python 3 | the whole contract core: parse both publisher files, digest, measure across the 2016 insertion, walk forward and backward through `23:59:60Z`, show the reverts |
| `samples/build_publisher_files.py` | plain Python 3 | regenerate `publisher_files/` from `tests/fixtures/schedule.json` |
| `samples/publisher_files/` | none | byte-exact IERS and NIST files with valid checksums, plus a manifest |
| `samples/deploy_and_call.py` | `genlayer-py` | deploying `ChronoSpan` and calling `import_schedule`, `measure`, `advance`, `rewind` over RPC |
| `samples/query.mjs` | `genlayer-js` | read-only calls against a deployed address: `list_tables`, `coverage`, `measure`, `next_transition` |
| `samples/verify_deployment.mjs` | `genlayer-js` | 13 asserted checks against `0x499D1d2b5ee169b89Fa20aB426B754E8579EE2dd`, exits non-zero on the first failure |

Live instance: [`0x499D1d2b5ee169b89Fa20aB426B754E8579EE2dd`](https://explorer-studio.genlayer.com/address/0x499D1d2b5ee169b89Fa20aB426B754E8579EE2dd)
(Studionet) — both `.mjs` samples default to it.

Full instructions: [docs/SAMPLES.md](../docs/SAMPLES.md).
