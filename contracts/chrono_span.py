# { "Depends": "py-genlayer:test" }
"""ChronoSpan - leap-second aware UTC interval arithmetic for GenLayer.

ChronoSpan measures elapsed SI seconds between whole-second UTC labels and
shifts a label forward or backward by a signed count of SI seconds.  The
inserted label ``23:59:60Z`` is a first-class value: it is accepted on input
and produced on output whenever the agreed schedule says a positive leap
second was inserted.

The schedule itself is never supplied by a caller.  The leader and every
validator independently download the IERS and NIST leap-second lists, parse
every transition, verify each publisher checksum, require identical transition
rows and take the earlier of the two expiry fields.  The agreed record is
stored once, keyed by the SHA-256 digest of its canonical JSON form, and every
later call names the immutable table it wants.

Contract layout
---------------
00  constants and pure helpers (parsing, canonical form, digests)
01  label codec      encode_label / decode_label
02  interval engine  measure_span / shift_label / next_transition
03  consensus input  acquire / normalize / import_schedule
04  public surface   ChronoSpan
"""

from genlayer import DynArray, TreeMap, gl

import hashlib
import json
import re
import typing
from bisect import bisect_right
from datetime import datetime, timedelta

# ---------------------------------------------------------------------------
# 00 - constants
# ---------------------------------------------------------------------------

SCHEMA = "chronospan/v1"

# Publisher endpoints.  Both files carry the same transition rows; they are
# fetched independently so that a single compromised mirror cannot invent a
# leap second.
PUBLISHERS = (
    "https://hpiers.obspm.fr/iers/bul/bulc/ntp/leap-seconds.list",
    "https://tf.nist.gov/leap-seconds.list",
)

# Atomic coordinates count SI seconds from the conventional coordinate
# origin 1900-01-01T00:00:00 (the NTP epoch).  UTC labels are unrelated to
# that origin; they are converted through the schedule's TAI-UTC offsets.
COORDINATE_ORIGIN = datetime(1900, 1, 1)

BASE_ROW = [2272060800, 10]  # 1972-01-01, TAI-UTC = 10 s
DAY = 86400
MAX_ROWS = 128
MAX_BYTES = 16384
MAX_EXPIRY = (datetime(9999, 1, 1) - COORDINATE_ORIGIN).days * DAY

LABEL_RE = re.compile(
    r"([0-9]{4})-([0-9]{2})-([0-9]{2})T([0-9]{2}):([0-9]{2}):([0-9]{2})Z"
)
TABLE_ID_RE = re.compile(r"[0-9a-f]{64}")
ROW_RE = re.compile(r"([1-9][0-9]{0,11})[ \t]+([1-9][0-9]{0,2})")
LIFETIME_RE = re.compile(r"[1-9][0-9]{0,11}")
CHECKSUM_RE = re.compile(
    r"(?:[0-9a-f]{40}|[0-9a-f]{8}(?:[ \t]+[0-9a-f]{8}){4})"
)

ERROR_UNKNOWN_TABLE = "chronospan: unknown table id"
ERROR_EVIDENCE = "chronospan: publisher evidence unavailable or inconsistent"
ERROR_NO_COVERAGE = "chronospan: label outside schedule coverage"
ERROR_NO_LABEL = "chronospan: label does not exist in this schedule"
ERROR_BAD_LABEL = "chronospan: expected a whole-second UTC label YYYY-MM-DDThh:mm:ssZ"
ERROR_END_BEFORE_START = "chronospan: end label precedes start label"
ERROR_NEGATIVE_DELTA = "chronospan: duration must not be negative"
ERROR_OUT_OF_RANGE = "chronospan: target instant outside schedule coverage"


def canonical(value: typing.Any) -> str:
    """Deterministic JSON: sorted keys, no whitespace.  Byte-identical on
    every node, which is what makes the consensus comparison meaningful."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def to_atomic(instant: datetime) -> int:
    delta = instant - COORDINATE_ORIGIN
    return delta.days * DAY + delta.seconds


def to_civil(atomic: int) -> datetime:
    return COORDINATE_ORIGIN + timedelta(seconds=atomic)


def content_digest(record: str) -> str:
    """Table identity: SHA-256 over the canonical record, hex encoded."""
    return hashlib.sha256(record.encode("utf-8")).hexdigest()


def parse_leap_list(body: bytes) -> typing.Tuple[list, dict]:
    """Parse one publisher's leap-second list into transition rows plus the
    publisher metadata that accompanies them.

    Every field is validated: file size, metadata completeness, the baseline
    row, monotone strictly-increasing transitions of exactly one second at a
    quarter-day boundary, a bounded lifetime and the publisher's own SHA-1
    over the numeric content.  Anything unexpected raises ``ValueError``.
    """
    if not isinstance(body, bytes) or not 0 < len(body) <= MAX_BYTES:
        raise ValueError("missing or oversized leap-second list")

    metadata: dict = {}
    rows: list = []
    for line in body.decode("utf-8").splitlines():
        line = line.strip(" \t")
        if not line:
            continue
        if line.startswith(("#$", "#@", "#h")):
            marker = line[:2]
            if marker in metadata:
                raise ValueError("duplicate leap-second metadata field")
            metadata[marker] = line[2:].strip(" \t")
        elif not line.startswith("#"):
            fields = ROW_RE.fullmatch(line.split("#", 1)[0].rstrip(" \t"))
            if not fields or len(rows) == MAX_ROWS:
                raise ValueError("malformed leap-second row")
            rows.append([int(fields[1]), int(fields[2])])

    if set(metadata) != {"#$", "#@", "#h"} or not rows or rows[0] != BASE_ROW:
        raise ValueError("incomplete leap-second list")
    for key in ("#$", "#@"):
        if not LIFETIME_RE.fullmatch(metadata[key]):
            raise ValueError("malformed leap-second lifetime")

    updated = int(metadata["#$"])
    expires = int(metadata["#@"])
    if not BASE_ROW[0] <= updated < expires <= MAX_EXPIRY or rows[-1][0] >= expires:
        raise ValueError("invalid leap-second lifetime")

    for (previous, previous_offset), (effective, offset) in zip(rows, rows[1:]):
        if (
            not previous < effective < expires
            or effective % DAY
            or abs(offset - previous_offset) != 1
        ):
            raise ValueError("invalid leap-second transition")
        moment = to_civil(effective)
        if moment.day != 1 or moment.month not in (1, 4, 7, 10):
            raise ValueError("leap second not scheduled at a quarter-day boundary")

    field = metadata["#h"].lower()
    if not CHECKSUM_RE.fullmatch(field):
        raise ValueError("malformed publisher checksum")
    checksum = "".join(field.split())
    material = str(updated) + str(expires) + "".join(
        f"{stamp}{offset}" for stamp, offset in rows
    )
    if hashlib.sha1(material.encode("ascii")).hexdigest() != checksum:
        raise ValueError("publisher checksum mismatch")

    return rows, {
        "updated_ntp": updated,
        "expires_ntp": expires,
        "file_sha1": checksum,
    }


def normalize(rows: list, sources: list) -> dict:
    """Build the agreed record.  The effective expiry is the earlier of the
    two publishers' expiry fields, so coverage never outlives the more
    conservative claim."""
    if not sources:
        raise ValueError("no publisher evidence")
    return {
        "schema": SCHEMA,
        "rows": rows,
        "expires_ntp": min(source["expires_ntp"] for source in sources),
        "sources": sources,
    }


def acquire(fetch: typing.Callable) -> dict:
    """Download every publisher list, verify it, and require the transition
    rows to be identical across publishers before normalizing."""
    rows = None
    sources = []
    for url in PUBLISHERS:
        response = fetch(url)
        if response.status != 200:
            raise ValueError("publisher unavailable")
        current, metadata = parse_leap_list(response.body)
        if rows is not None and current != rows:
            raise ValueError("publisher transition rows disagree")
        rows = current
        sources.append({"url": url, **metadata})
    return normalize(rows, sources)


# ---------------------------------------------------------------------------
# 01 - label codec
# ---------------------------------------------------------------------------


def encode_label(rows: list, expires: int, label: str) -> int:
    """UTC label -> atomic coordinate.

    ``23:59:60Z`` resolves to the inserted SI second when, and only when, the
    schedule inserts one at that instant.  A label the schedule does not
    contain (a false leap label, or a deleted second under a negative leap)
    raises instead of silently rounding.
    """
    parts = LABEL_RE.fullmatch(label)
    if not parts:
        raise ValueError(ERROR_BAD_LABEL)
    year, month, day, hour, minute, second = map(int, parts.groups())
    if second > 60:
        raise ValueError(ERROR_BAD_LABEL)
    try:
        mark = to_atomic(datetime(year, month, day, hour, minute, min(second, 59)))
    except ValueError:
        raise ValueError("chronospan: label is not a real calendar instant")

    if not rows[0][0] <= mark < expires:
        raise ValueError(ERROR_NO_COVERAGE)

    index = bisect_right(rows, mark, key=lambda row: row[0]) - 1
    offset = rows[index][1]
    change = 0
    if index + 1 < len(rows) and rows[index + 1][0] == mark + 1:
        change = rows[index + 1][1] - offset

    if second == 60:
        if change == 1:
            return mark + offset + 1
        raise ValueError(ERROR_NO_LABEL)
    if change == -1:
        raise ValueError(ERROR_NO_LABEL)
    return mark + offset


def decode_label(rows: list, expires: int, atomic: int) -> str:
    """Atomic coordinate -> UTC label, emitting ``23:59:60Z`` for the
    inserted second."""
    if not rows[0][0] + rows[0][1] <= atomic < expires + rows[-1][1]:
        raise ValueError(ERROR_OUT_OF_RANGE)

    index = bisect_right(rows, atomic, key=lambda row: row[0] + row[1]) - 1
    offset = rows[index][1]
    if index + 1 < len(rows):
        effective, future = rows[index + 1]
        if future == offset + 1 and atomic == effective + offset:
            return to_civil(effective - 1).isoformat()[:-2] + "60Z"
    return to_civil(atomic - offset).isoformat() + "Z"


# ---------------------------------------------------------------------------
# 02 - interval engine
# ---------------------------------------------------------------------------


def measure_span(rows: list, expires: int, start_utc: str, end_utc: str) -> dict:
    """Elapsed SI seconds between two labels, plus every offset change that
    becomes effective after the start and on or before the end."""
    start = encode_label(rows, expires, start_utc)
    end = encode_label(rows, expires, end_utc)
    if end < start:
        raise ValueError(ERROR_END_BEFORE_START)
    changes = [
        [stamp, offset]
        for stamp, offset in rows[1:]
        if start < stamp + offset <= end
    ]
    return {
        "start_atomic": start,
        "end_atomic": end,
        "elapsed_seconds": end - start,
        "offset_changes": changes,
    }


def shift_label(rows: list, expires: int, label: str, delta: int) -> str:
    """Advance (delta > 0) or rewind (delta < 0) a label by whole SI
    seconds.  The result is whatever label the schedule contains at that
    atomic coordinate - including 23:59:60Z."""
    start = encode_label(rows, expires, label)
    return decode_label(rows, expires, start + delta)


def next_transition(rows: list, expires: int, after_utc: str) -> typing.Any:
    """First schedule transition strictly after a label, or ``None`` when
    the schedule has no later transition inside its coverage."""
    mark = encode_label(rows, expires, after_utc)
    previous_offset = rows[0][1]
    for index in range(1, len(rows)):
        effective, offset = rows[index]
        atomic = effective + offset
        if atomic <= mark:
            previous_offset = offset
            continue
        inserted = None
        if offset > previous_offset:
            inserted = decode_label(rows, expires, atomic - 1)
        return {
            "effective_utc": decode_label(rows, expires, atomic),
            "inserted_utc": inserted,
            "old_offset": previous_offset,
            "new_offset": offset,
            "atomic": atomic,
        }
    return None


# ---------------------------------------------------------------------------
# 03 - consensus input
# ---------------------------------------------------------------------------


def read_table(stored: str, table_id: str) -> dict:
    """Decode a stored record, or revert when the caller names a table that
    was never agreed."""
    if not TABLE_ID_RE.fullmatch(table_id) or stored == "":
        raise gl.vm.UserError(ERROR_UNKNOWN_TABLE)
    return json.loads(stored)


# ---------------------------------------------------------------------------
# 04 - public surface
# ---------------------------------------------------------------------------


class ChronoSpan(gl.Contract):
    """Immutable, content-addressed leap-second schedules plus the interval
    arithmetic that runs on top of them."""

    # table id (sha256 hex) -> canonical record JSON
    tables: TreeMap[str, str]
    # insertion order of agreed table ids, for enumeration only
    order: DynArray[str]

    def __init__(self) -> None:
        pass

    # -- consensus -------------------------------------------------------

    @gl.public.write
    def import_schedule(self) -> str:
        """Permissionless.  Takes no caller evidence: the leader and every
        validator download both publisher lists, verify them independently
        and must return byte-identical canonical JSON.  The agreed record is
        stored under its content digest; importing the same evidence twice
        reuses the same id."""
        def evaluate() -> str:
            try:
                return canonical(acquire(gl.nondet.web.get))
            except Exception:
                raise gl.vm.UserError(ERROR_EVIDENCE)

        def validate(leader: typing.Any) -> bool:
            if not isinstance(leader, gl.vm.Return):
                return False
            try:
                return evaluate() == leader.calldata
            except Exception:
                return False

        agreed = gl.vm.run_nondet_unsafe(evaluate, validate)
        table_id = content_digest(agreed)
        if table_id not in self.tables:
            self.tables[table_id] = agreed
            self.order.append(table_id)
        return table_id

    # -- reads -----------------------------------------------------------

    @gl.public.view
    def get_table(self, table_id: str) -> typing.Any:
        """Full agreed record: transition rows, both publishers' metadata and
        the effective (earlier) expiry."""
        raw = self.tables[table_id] if table_id in self.tables else ""
        return read_table(raw, table_id)

    @gl.public.view
    def list_tables(self) -> typing.Any:
        """Every agreed table id, in the order the network agreed them."""
        return [str(self.order[index]) for index in range(len(self.order))]

    @gl.public.view
    def table_meta(self, table_id: str) -> typing.Any:
        """Digest, schema, row count, expiry and publisher metadata without
        shipping the whole row list."""
        record = self.get_table(table_id)
        return {
            "table_id": table_id,
            "schema": record["schema"],
            "transition_count": len(record["rows"]),
            "expires_ntp": record["expires_ntp"],
            "sources": record["sources"],
        }

    @gl.public.view
    def coverage(self, table_id: str) -> typing.Any:
        """Inclusive first and exclusive last label this table can answer."""
        record = self.get_table(table_id)
        rows, expires = record["rows"], record["expires_ntp"]
        return {
            "first_utc": decode_label(rows, expires, rows[0][0] + rows[0][1]),
            "last_utc_exclusive": decode_label(
                rows, expires, expires + rows[-1][1] - 1
            ),
        }

    @gl.public.view
    def measure(self, table_id: str, start_utc: str, end_utc: str) -> typing.Any:
        """Elapsed SI seconds between two labels inside one table's
        coverage."""
        record = self.get_table(table_id)
        try:
            result = measure_span(
                record["rows"], record["expires_ntp"], start_utc, end_utc
            )
        except ValueError as error:
            raise gl.vm.UserError(str(error))
        result["table_id"] = table_id
        result["start_utc"] = start_utc
        result["end_utc"] = end_utc
        return result

    @gl.public.view
    def shift(self, table_id: str, label: str, delta_seconds: int) -> str:
        """Move a label by a signed number of SI seconds."""
        record = self.get_table(table_id)
        try:
            return shift_label(
                record["rows"], record["expires_ntp"], label, delta_seconds
            )
        except ValueError as error:
            raise gl.vm.UserError(str(error))

    @gl.public.view
    def advance(self, table_id: str, label: str, seconds: int) -> str:
        """Move a label forward by ``seconds`` SI seconds."""
        if seconds < 0:
            raise gl.vm.UserError(ERROR_NEGATIVE_DELTA)
        return self.shift(table_id, label, seconds)

    @gl.public.view
    def rewind(self, table_id: str, label: str, seconds: int) -> str:
        """Move a label backward by ``seconds`` SI seconds."""
        if seconds < 0:
            raise gl.vm.UserError(ERROR_NEGATIVE_DELTA)
        return self.shift(table_id, label, -seconds)

    @gl.public.view
    def next_transition(self, table_id: str, after_utc: str) -> typing.Any:
        """Describe the next leap-second transition after a label."""
        record = self.get_table(table_id)
        try:
            return next_transition(
                record["rows"], record["expires_ntp"], after_utc
            )
        except ValueError as error:
            raise gl.vm.UserError(str(error))
