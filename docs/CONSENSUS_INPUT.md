# Consensus input

The only non-deterministic part of ChronoSpan is the evidence used to build a
table. Everything after it is pure arithmetic.

## 1. What is downloaded

| Publisher | Endpoint |
| --- | --- |
| IERS Bulletin C (NTP list) | `https://hpiers.obspm.fr/iers/bul/bulc/ntp/leap-seconds.list` |
| NIST leap-second list | `https://tf.nist.gov/leap-seconds.list` |

Both files describe the same transitions in the same `leap-seconds.list`
format. They are fetched **independently** by the leader and by every
validator, and both files are fetched on every node - never one file from one
node and the other from a different node.

## 2. What is checked, in order

`parse_leap_list()` rejects the file unless every one of these holds:

1. the body is bytes and at most 16384 bytes;
2. it decodes as UTF-8;
3. exactly the three metadata fields `#$` (updated), `#@` (expires) and `#h`
   (checksum) are present, each exactly once;
4. at least one transition row exists and the first row is the baseline
   `[2272060800, 10]` (1972-01-01, TAI-UTC = 10 s);
5. both lifetime fields are plain positive integers, and
   `baseline <= updated < expires <= year-9999`, with the last transition
   strictly before the expiry;
6. transitions are strictly increasing, fall on midnight, differ from their
   predecessor by exactly ±1 second, and land on the first day of January,
   April, July or October;
7. the `#h` field is a 40-hex SHA-1, printed either as one group or as five
   8-character groups;
8. that SHA-1 equals
   `sha1(updated + expires + concat(effective, offset)...)` over the numeric
   content - the publisher's own integrity field, which detects a corrupted
   or truncated file.

Then `acquire()`:

9. requires **identical transition rows** from both publishers - a mismatch
   aborts the whole import even when each file is individually valid;
10. `normalize()` takes `min(expiry)` across publishers as the effective
    expiry, so coverage never outlives the more conservative claim.

Failure at any step raises; `import_schedule` converts it to
`chronospan: publisher evidence unavailable or inconsistent`, which reverts
the transaction. There is no partial import and no fallback source.

## 3. How agreement is reached

```python
def evaluate() -> str:
    try:
        return canonical(acquire(gl.nondet.web.get))
    except Exception:
        raise gl.vm.UserError(ERROR_EVIDENCE)

def validate(leader) -> bool:
    if not isinstance(leader, gl.vm.Return):
        return False
    try:
        return evaluate() == leader.calldata
    except Exception:
        return False

agreed = gl.vm.run_nondet_unsafe(evaluate, validate)
```

* `evaluate` runs on the leader and produces the canonical JSON string.
* `validate` runs on each validator: it re-downloads, re-parses and compares
  its own string to the leader's **byte for byte**, including both publishers'
  `updated_ntp`, `expires_ntp` and `file_sha1`.
* Any difference - a different row, a different expiry, a different checksum,
  an unreachable publisher - makes the validator return `False`, so the
  leader's result is not accepted.

Because the record contains the full publisher metadata, "the rows match but
the files came from somewhere else" is not an agreement.

## 4. Identity

```python
table_id = sha256(canonical_record)   # 64 hex characters
```

* The id is a content digest: same evidence, same id, on every import.
* Different evidence produces a different id and is stored alongside the
  first - tables are never overwritten.
* Callers pass the id to every read. Naming an unknown id reverts with
  `chronospan: unknown table id`, so a query can never silently fall back to
  "whatever the latest table happens to be".

## 5. What the contract trusts - and what it does not

ChronoSpan trusts the two publishers for *scheduling*: it will not invent or
shift a leap second on its own. The SHA-1 fields protect against corruption,
dual publication plus row agreement protect against a single compromised
mirror, and GenLayer consensus pins which exact files the network agreed on.

ChronoSpan does **not** trust the caller. Labels are validated against the
agreed table; out-of-coverage and impossible labels revert rather than being
clamped.

## 6. Coverage and time basis

* Unsmeared UTC, whole seconds only.
* Atomic coordinates count SI seconds from 1900-01-01T00:00:00 (the NTP
  epoch); UTC labels map to coordinates through the agreed TAI-UTC offsets.
* Supported label range: `1972-01-01T00:00:00Z` (inclusive) to the effective
  expiry (exclusive). `coverage()` reports both ends.
* An older table still answers historical queries inside its own coverage -
  the id, not the newest import, decides.
