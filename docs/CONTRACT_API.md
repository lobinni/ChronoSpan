# Contract API

Contract: `contracts/chrono_span.py`, class `ChronoSpan`.
All methods are read-only (`@gl.public.view`) except `import_schedule`.
Every argument and return value is a primitive the calldata encoder accepts:
`str`, `int`, `dict`/`list` returned as `typing.Any`.

## Methods

| Method | Kind | Signature | Returns |
| --- | --- | --- | --- |
| `import_schedule` | write | `() -> str` | content digest of the agreed table |
| `get_table` | view | `(table_id: str) -> dict` | full agreed record |
| `list_tables` | view | `() -> list` | agreed ids, insertion order |
| `table_meta` | view | `(table_id: str) -> dict` | digest, counts, publisher metadata |
| `coverage` | view | `(table_id: str) -> dict` | inclusive first / exclusive last label |
| `measure` | view | `(table_id, start_utc, end_utc) -> dict` | elapsed SI seconds + offset changes |
| `shift` | view | `(table_id, label, delta_seconds: int) -> str` | label after a signed move |
| `advance` | view | `(table_id, label, seconds: int) -> str` | label after a forward move |
| `rewind` | view | `(table_id, label, seconds: int) -> str` | label after a backward move |
| `next_transition` | view | `(table_id, after_utc: str) -> dict \| None` | next leap-second transition |

## Records

### Table record (`get_table`)

```json
{
  "schema": "chronospan/v1",
  "rows": [[2272060800, 10], [2287785600, 11], "..."],
  "expires_ntp": 4023129600,
  "sources": [
    {"url": "https://hpiers.obspm.fr/iers/bul/bulc/ntp/leap-seconds.list",
     "updated_ntp": 3992312697, "expires_ntp": 4023129600,
     "file_sha1": "a9bad14584c31c70758402aab37bfd545923836a"},
    {"url": "https://tf.nist.gov/leap-seconds.list",
     "updated_ntp": 3676924800, "expires_ntp": 4023129600,
     "file_sha1": "39096da8b66c33126ea48831363f817b36782978"}
  ]
}
```

`rows` are `[effective_ntp_seconds, tai_utc_offset]` pairs. The offset applies
from the effective second (inclusive) until the next row. `expires_ntp` is the
*earlier* of the two publishers' expiry fields.

### Measure result

```json
{
  "table_id": "9f2c…64 hex chars…",
  "start_utc": "2016-12-31T23:59:59Z",
  "end_utc": "2017-01-01T00:00:00Z",
  "start_atomic": 3692217635,
  "end_atomic": 3692217637,
  "elapsed_seconds": 2,
  "offset_changes": [[3692217600, 37]]
}
```

`offset_changes` lists every transition that becomes effective *after*
`start_atomic` and on or before `end_atomic`.

### Transition result (`next_transition`)

```json
{
  "effective_utc": "2017-01-01T00:00:00Z",
  "inserted_utc": "2016-12-31T23:59:60Z",
  "old_offset": 36,
  "new_offset": 37,
  "atomic": 3692217637
}
```

`inserted_utc` is `null` for a negative leap (the schedule deletes a label
instead of inserting one) and the whole result is `null` when no transition
follows the given label inside coverage.

## Labels

Accepted form only: `YYYY-MM-DDThh:mm:ssZ`, whole seconds, no fractional
part, no offset, no local time. The inserted second is written `23:59:60Z`
and is a normal value in both directions.

| Example | Meaning |
| --- | --- |
| `2016-12-31T23:59:59Z` | last ordinary second before the insertion |
| `2016-12-31T23:59:60Z` | the inserted SI second |
| `2017-01-01T00:00:00Z` | first second after it |

## Error catalogue

Every failure reverts with one of these messages.

| Message | Raised by | Cause |
| --- | --- | --- |
| `chronospan: unknown table id` | all table reads | malformed digest, or a table the network never agreed |
| `chronospan: publisher evidence unavailable or inconsistent` | `import_schedule` | a publisher unreachable, corrupt, or disagreeing with the other |
| `chronospan: expected a whole-second UTC label YYYY-MM-DDThh:mm:ssZ` | label input | malformed label, seconds above 60 |
| `chronospan: label is not a real calendar instant` | label input | impossible date such as `2017-02-29` |
| `chronospan: label outside schedule coverage` | label input | before 1972-01-01 or at/after the effective expiry |
| `chronospan: label does not exist in this schedule` | label input | false `23:59:60Z`, or a second deleted by a negative leap |
| `chronospan: end label precedes start label` | `measure` | reversed interval |
| `chronospan: duration must not be negative` | `advance`, `rewind` | signed value passed to a directional helper |
| `chronospan: target instant outside schedule coverage` | `shift` | the move lands outside the table |

## Examples

```python
table = contract.import_schedule()                 # -> "3f0a…c1" (sha256 hex)

contract.coverage(table)
# {"first_utc": "1972-01-01T00:00:00Z",
#  "last_utc_exclusive": "2027-…T00:00:00Z"}

contract.measure(table, "2016-12-31T23:59:59Z", "2017-01-01T00:00:00Z")
# {"elapsed_seconds": 2, "offset_changes": [[3692217600, 37]], …}

contract.advance(table, "2016-12-31T23:59:59Z", 1)   # "2016-12-31T23:59:60Z"
contract.rewind(table, "2017-01-01T00:00:00Z", 2)    # "2016-12-31T23:59:59Z"
contract.shift(table, "2016-12-31T23:59:60Z", -1)    # "2016-12-31T23:59:59Z"

contract.next_transition(table, "2016-06-01T00:00:00Z")
# {"effective_utc": "2017-01-01T00:00:00Z",
#  "inserted_utc": "2016-12-31T23:59:60Z", …}
```

## Versioning

The record carries `"schema": "chronospan/v1"`. A change to the record shape
bumps the schema and therefore changes every content digest; old tables remain
readable because callers hold the id, not the shape.

## Live instance

| | |
| --- | --- |
| Network | Studionet |
| Address | [`0x499D1d2b5ee169b89Fa20aB426B754E8579EE2dd`](https://explorer-studio.genlayer.com/address/0x499D1d2b5ee169b89Fa20aB426B754E8579EE2dd) |
| Source | `contracts/chrono_span.py` (`sha256 8a6412255eb6dd0c941af3187f1005f3b5c628cbc6aeb182f722acf2d07eac27`) |

Every method in this document is callable against that address. The read
methods return the shapes shown here; `import_schedule` is the only write.
Reproduce the table with:

```sh
node samples/query.mjs          # reads, prints each result
node samples/verify_deployment.mjs   # same reads, asserted, exit code
```

Deployment, source verification and the full check table:
[`docs/DEPLOYMENT.md`](DEPLOYMENT.md).
