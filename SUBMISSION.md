**Contribution type** Builder → Intelligent Contracts

**Title** ChronoSpan — Leap-Second Interval Arithmetic

**Notes / Description**

ChronoSpan measures elapsed SI seconds between whole-second UTC labels and
advances or rewinds a timestamp by a signed duration. It represents the
inserted label `23:59:60Z` explicitly.

The leader and validators independently download the IERS and NIST leap-second
tables. They parse every transition, verify the publisher checksums, require
matching transition rows, and use the earlier expiry. Exact agreement on the
normalized table and both publishers' metadata is required. The contract
stores the agreed table by content digest. Callers select an immutable table
ID. Labels outside its coverage revert.

StudioNet verifies the import, a two-second interval across the 2016
insertion, forward and reverse navigation through `23:59:60Z`, and rejection
of a false leap label and dates outside coverage. The deterministic suite runs
46 tests without a VM; the direct-mode harness runs 10 more against mocked
publisher downloads.

**Evidence**

- Intelligent Contract: [`contracts/chrono_span.py`](contracts/chrono_span.py)
  (`sha256 8a6412255eb6dd0c941af3187f1005f3b5c628cbc6aeb182f722acf2d07eac27`)
- Deployed contract:
  [0x499D1d2b5ee169b89Fa20aB426B754E8579EE2dd](https://explorer-studio.genlayer.com/address/0x499D1d2b5ee169b89Fa20aB426B754E8579EE2dd)
- Deployment record:
  [`deployments/chronospan.studionet.json`](deployments/chronospan.studionet.json)
- Live verification: `node samples/verify_deployment.mjs`
- Tests: `python -m pytest tests -q`
- Documentation: [`docs/`](docs/) — architecture, API, consensus input,
  testing, samples, deployment and the line-by-line comparison with the
  reference contract

**Scope**

This repository is a pure Intelligent Contracts project. The submission is
this folder — `intelligent/` — whose contract is
[`contracts/chrono_span.py`](contracts/chrono_span.py). The UI workspace
([`../frontend/`](../frontend/README.md)) and the Vite build shell at the
repository root (`index.html`, `package.json`, `vite.config.ts`) are
excluded.
