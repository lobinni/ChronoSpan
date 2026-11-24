# Samples

> Run every command below from the `intelligent/` folder. Paths inside the
> samples are module-relative, so they work from anywhere once you are there.

Six entry points, from "runs right now" to "asserts the deployed instance".

| # | Sample | Needs | What it shows |
| --- | --- | --- | --- |
| 1 | `samples/local_demo.py` | plain Python 3 | the whole contract core, offline |
| 2 | `samples/publisher_files/` | none | canned publisher evidence with valid checksums |
| 3 | `samples/build_publisher_files.py` | plain Python 3 | regenerate those files from the fixture |
| 4 | `samples/deploy_and_call.py` | `genlayer-py` | deploy, `import_schedule`, `measure`, `advance`, `rewind` |
| 5 | `samples/query.mjs` | `genlayer-js` | read-only client against a deployed address |
| 6 | `samples/verify_deployment.mjs` | `genlayer-js` | 13 asserted checks, exit code 0/1 |

## 1. `samples/local_demo.py` - no dependencies

Runs the contract's deterministic core under plain Python: builds both
publisher files offline, parses and verifies them, computes the content
digest, measures across the 2016 insertion, walks forward and backward
through `23:59:60Z`, then prints the reverts.

```sh
python samples/local_demo.py
```

Expected tail:

```
measure  2016-12-31T23:59:59Z -> 2017-01-01T00:00:00Z = 2 SI seconds
         offset change at 3692217600 -> TAI-UTC 37
+1s      2016-12-31T23:59:59Z -> 2016-12-31T23:59:60Z
+1s      2016-12-31T23:59:60Z -> 2017-01-01T00:00:00Z
-1s      2017-01-01T00:00:00Z -> 2016-12-31T23:59:60Z
-2s      2017-01-01T00:00:00Z -> 2016-12-31T23:59:59Z
```

## 2. `samples/publisher_files/` - canned evidence

Two byte-exact publisher files (IERS formatting with grouped checksum,
NIST formatting with a plain checksum) plus their SHA-256 manifest. Use them
to mock `gl.nondet.web.get` in direct-mode tests or to replay `acquire()`
offline:

```python
direct_vm.mock_web(r"leap-seconds\.list$", {
    "method": "GET",
    "response": {"status": 200, "headers": {}, "body": body},
})
```

`tests/test_schedule.py::test_canned_publisher_files_parse_and_agree` keeps
them honest: if the contract's parser ever changes, that test fails.

## 3. `samples/build_publisher_files.py`

```sh
python samples/build_publisher_files.py
```

Rebuilds section 2 from `tests/fixtures/schedule.json` and rewrites
`manifest.json`.

## 4. `samples/deploy_and_call.py` - deploy and write

Deploys `ChronoSpan`, imports the schedule (the consensus call), then calls
`measure`, `advance` and `rewind`. Requires a funded account and
`genlayer-py`.

```sh
python -m pip install genlayer-py
python samples/deploy_and_call.py
```

Record the resulting address in `deployments/<contract>.<network>.json`.

## 5. `samples/query.mjs` - read-only

`genlayer-js` reads against a deployed address: list tables, read coverage,
measure an interval, ask for the next transition. Defaults to the address in
`deployments/chronospan.studionet.json`.

```sh
npm install genlayer-js
node samples/query.mjs                                    # 0x499D…E2dd
node samples/query.mjs 0xYourContractAddress              # any instance
```

## 6. `samples/verify_deployment.mjs` - asserted live checks

Thirteen checks over the same reads, ending in an exit code so it can gate a
release. Full expected table: [`TESTING.md`](TESTING.md#tier-3---live-deployment-samplesverify_deploymentmjs).

```sh
node samples/verify_deployment.mjs
echo $?     # 0 = every check passed
```

## Deploying

```sh
genvm-lint check contracts/chrono_span.py
python -m pytest tests -q
gltest --network studionet deploy contracts/chrono_span.py
sha256sum contracts/chrono_span.py     # record it next to the address
```

Steps and the verification checklist:
[`DEPLOYMENT.md`](DEPLOYMENT.md).

Only this folder is submitted - see
[`../../frontend/README.md`](../../frontend/README.md) for why the UI
workspace and the build shell stay out of the submission.
