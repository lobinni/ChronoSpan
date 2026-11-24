#!/usr/bin/env python3
"""Offline demo of the ChronoSpan contract core.

Runs the real contract source (minus the GenVM shell) with both publisher
files served from memory: parse, verify, agree, digest, measure, navigate
through 23:59:60Z, and show the reverts.

    python samples/local_demo.py
"""

import ast
import hashlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "contracts" / "chrono_span.py"
SCHEDULE = json.loads((ROOT / "tests" / "fixtures" / "schedule.json").read_text())


def load_core() -> dict:
    """Execute contracts/chrono_span.py without the GenVM import or the
    contract class - the same trick tests/conftest.py uses."""
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    tree.body = [
        node
        for node in tree.body
        if not isinstance(node, ast.ClassDef)
        and not (isinstance(node, ast.ImportFrom) and node.module == "genlayer")
    ]
    namespace: dict = {}
    exec(compile(tree, str(SOURCE), "exec"), namespace)
    return namespace


def build_document(core: dict, index: int) -> bytes:
    source = SCHEDULE["sources"][index]
    rows = SCHEDULE["rows"]
    pairs = [f"{stamp}  {offset}" for stamp, offset in rows]
    fields = [str(source["updated_ntp"]), str(source["expires_ntp"]), *pairs]
    material = "".join("".join(fields).split())
    checksum = hashlib.sha1(material.encode("ascii")).hexdigest()
    if index == 0:
        checksum = " ".join(
            checksum[offset : offset + 8] for offset in range(0, 40, 8)
        )
    lines = [f"#$ {fields[0]}", f"#@ {fields[1]}", *pairs, f"#h {checksum}"]
    return ("\n".join(lines) + "\n").encode("utf-8")


def show(title: str, payload) -> None:
    print(f"{title:<46} {payload}")


def main() -> int:
    core = load_core()
    documents = [build_document(core, 0), build_document(core, 1)]

    # 1. Evidence: both publishers, downloaded independently.
    calls = []

    def fetch(url: str):
        calls.append(url)
        index = core["PUBLISHERS"].index(url)
        return SimpleNamespace(status=200, body=documents[index])

    record = core["acquire"](fetch)
    table_id = core["content_digest"](core["canonical"](record))

    print("=" * 78)
    print("1. Publisher evidence")
    print("=" * 78)
    show("files fetched", len(calls))
    show("transition rows", len(record["rows"]))
    show("effective expiry (earlier)", record["expires_ntp"])
    show("table id (sha256)", table_id)
    show("schema", record["schema"])

    rows, expires = record["rows"], record["expires_ntp"]

    # 2. The 2016 insertion.
    print()
    print("=" * 78)
    print("2. Two SI seconds across 2016-12-31 23:59:60Z")
    print("=" * 78)
    result = core["measure_span"](
        rows, expires, "2016-12-31T23:59:59Z", "2017-01-01T00:00:00Z"
    )
    show("start_atomic", result["start_atomic"])
    show("end_atomic", result["end_atomic"])
    show("elapsed_seconds", result["elapsed_seconds"])
    show("offset_changes", result["offset_changes"])

    # 3. Navigation through the inserted label.
    print()
    print("=" * 78)
    print("3. Forward and reverse through the inserted second")
    print("=" * 78)
    before = "2016-12-31T23:59:59Z"
    inserted = "2016-12-31T23:59:60Z"
    midnight = "2017-01-01T00:00:00Z"
    for start, delta in ((before, 1), (inserted, 1), (midnight, -1), (midnight, -2)):
        show(f"{delta:+d}s  {start}", core["shift_label"](rows, expires, start, delta))

    # 4. Rejections.
    print()
    print("=" * 78)
    print("4. What reverts")
    print("=" * 78)
    rejections = [
        ("false leap label", lambda: core["encode_label"](rows, expires,
                                                           "2016-12-30T23:59:60Z")),
        ("date outside coverage", lambda: core["encode_label"](rows, expires,
                                                               "2029-01-01T00:00:00Z")),
        ("date before 1972", lambda: core["encode_label"](rows, expires,
                                                          "1971-12-31T23:59:59Z")),
        ("impossible calendar date", lambda: core["encode_label"](rows, expires,
                                                                  "2017-02-29T00:00:00Z")),
        ("reversed interval", lambda: core["measure_span"](
            rows, expires, midnight, before)),
        ("shift past coverage", lambda: core["shift_label"](
            rows, expires,
            core["decode_label"](rows, expires, expires + rows[-1][1] - 1), 1)),
    ]
    for name, action in rejections:
        try:
            action()
        except ValueError as error:
            show(name, f"revert: {error}")
        else:
            print(f"{name:<46} NOT REJECTED")
            return 1

    # 5. Next transition.
    print()
    print("=" * 78)
    print("5. Next transition after 2016-06-01T00:00:00Z")
    print("=" * 78)
    print(json.dumps(core["next_transition"](rows, expires, "2016-06-01T00:00:00Z"),
                     indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
