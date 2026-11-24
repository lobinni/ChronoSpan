# Deployments

One JSON record per deployed instance. Nothing else in the repository
depends on this folder, and nothing in this folder is part of a contract
submission — a submission is `contracts/` alone.

## Records

| File | Network | Address |
| --- | --- | --- |
| [`chronospan.studionet.json`](chronospan.studionet.json) | Studionet | [`0x499D1d2b5ee169b89Fa20aB426B754E8579EE2dd`](https://explorer-studio.genlayer.com/address/0x499D1d2b5ee169b89Fa20aB426B754E8579EE2dd) |

## Record shape

| Field | Meaning |
| --- | --- |
| `address` | deployed contract address, checksummed as published by the explorer |
| `explorer` | canonical read-only link for that address |
| `network` | the GenLayer network the address lives on |
| `source` | path of the source file that was submitted |
| `source_sha256` | sha256 of that source at deploy time — compare with the explorer's source before trusting a call |
| `deployment_tx`, `deployer`, `recorded_on` | filled in from the deploy receipt; `null` until then |
| `expected_after_import` | what the instance must answer once `import_schedule()` has run |

## Keeping a record honest

```sh
sha256sum contracts/chrono_span.py        # must equal source_sha256
python -m pytest tests -q                 # must stay green
node samples/verify_deployment.mjs        # must exit 0
```

`verify_deployment.mjs` talks to the address in the record and asserts the
behaviour listed in `expected_after_import`, so a redeploy that silently
changes the contract fails the check instead of quietly disagreeing with the
documentation.

When you redeploy: copy this file, update `address`, `explorer`,
`source_sha256` and `deployment_tx`, move the old file to
`archive/`, and re-run the verification script against the new address.
