# Deployment and live verification

> Commands run from the `intelligent/` folder. The `frontend/` workspace and
> the Vite shell at the repository root are unrelated to this process.

ChronoSpan is deployed on Studionet:

```
0x499D1d2b5ee169b89Fa20aB426B754E8579EE2dd
https://explorer-studio.genlayer.com/address/0x499D1d2b5ee169b89Fa20aB426B754E8579EE2dd
```

The machine-readable record lives in
[`deployments/chronospan.studionet.json`](../deployments/chronospan.studionet.json).

## 1. Deploy

```sh
genvm-lint check contracts/chrono_span.py     # static analysis
python -m pytest tests -q                     # 46 deterministic + 10 harness tests

# through GenLayer Studio (studio.genlayer.com): paste contracts/chrono_span.py
# or through the CLI, which deploys the file as-is:
gltest --network studionet deploy contracts/chrono_span.py
```

The constructor takes no arguments and the contract starts with empty
storage: there is nothing to configure, because a table only exists after
the network has agreed on publisher evidence.

## 2. Record it

Write the address, network, source path and `sha256sum contracts/chrono_span.py`
into `deployments/<contract>.<network>.json`. See
[`deployments/README.md`](../deployments/README.md) for the field meanings.

## 3. Verify the source before anything else

Open the explorer link and compare the published source with
`contracts/chrono_span.py`. The record pins the expectation:

```
source_sha256 = 8a6412255eb6dd0c941af3187f1005f3b5c628cbc6aeb182f722acf2d07eac27
```

If the hashes differ, the address is running different code and every
documented behaviour below is unverified for it.

## 4. First write: import the schedule

`import_schedule()` is the only write method. It takes no arguments and no
caller evidence — the leader and every validator download both publisher
lists, verify them and must return byte-identical canonical JSON.

```sh
node samples/query.mjs 0x499D1d2b5ee169b89Fa20aB426B754E8579EE2dd   # reads
# write, from a wallet or a funded account:
#   client.writeContract({ address, functionName: "import_schedule", args: [] })
```

Consensus writes on Studionet take roughly a minute while validators
re-download the evidence. The receipt returns the table id: 64 hex
characters, the sha256 of the agreed record.

## 5. Verify the live instance

```sh
npm install genlayer-js
node samples/verify_deployment.mjs                    # uses the record's address
node samples/verify_deployment.mjs 0xYourOtherAddress # or any other instance
```

The script exits non-zero on the first failure. It asserts:

| # | Check | Expected |
| --- | --- | --- |
| 1 | `list_tables()` | at least one agreed table, each a 64-hex digest |
| 2 | `table_meta(id)` | `transition_count` 28, two publisher sources, schema `chronospan/v1` |
| 3 | `coverage(id)` | first label `1972-01-01T00:00:00Z`, last exclusive label at or after it |
| 4 | `measure(id, 2016-12-31T23:59:59Z, 2017-01-01T00:00:00Z)` | `elapsed_seconds` **2**, `offset_changes` `[[3692217600, 37]]` |
| 5 | `advance(id, 23:59:59Z, 1)` | `2016-12-31T23:59:60Z` |
| 6 | `rewind(id, 2017-01-01T00:00:00Z, 2)` | `2016-12-31T23:59:59Z` |
| 7 | `next_transition(id, 2016-06-01T00:00:00Z)` | inserted label `2016-12-31T23:59:60Z` |
| 8 | `get_table("0" × 64)` | reverts with `unknown table id` |
| 9 | `measure(id, 1971-…, …)` | reverts with `outside schedule coverage` |
| 10 | `measure(id, end, start)` | reverts with `end label precedes start label` |

Checks 4–7 are the behaviour the contract exists for; checks 8–10 prove the
revert paths are live on chain and not only in the unit suite.

## 6. What is *not* verified by a read

`measure` and friends only prove arithmetic against the table the instance
already holds. Whether that table came from honest publisher evidence is
established at import time, by consensus — which is why the verification
script checks `sources` (two publishers, both URLs) as well as the rows.

Re-running `import_schedule()` on a fresh instance is the only way to see the
consensus path execute; on an existing instance it is idempotent and returns
the same id.
