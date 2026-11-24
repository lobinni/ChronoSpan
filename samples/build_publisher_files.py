#!/usr/bin/env python3
"""Rebuild the canned publisher files in samples/publisher_files/.

The files are byte-exact leap-seconds.list documents: IERS prints the
publisher SHA-1 in five 8-character groups, NIST prints it as one 40-hex
string. Both parse under the contract's own rules, which is what makes them
useful as offline mocks.

    python samples/build_publisher_files.py
"""

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "schedule.json"
OUTPUT = ROOT / "samples" / "publisher_files"
NAMES = ("iers_bulletin_c.list", "nist_leap_seconds.list")


def build(schedule: dict, index: int) -> bytes:
    source = schedule["sources"][index]
    pairs = [f"{stamp}  {offset}" for stamp, offset in schedule["rows"]]
    fields = [str(source["updated_ntp"]), str(source["expires_ntp"]), *pairs]
    material = "".join("".join(fields).split())
    checksum = hashlib.sha1(material.encode("ascii")).hexdigest()
    if index == 0:
        checksum = " ".join(
            checksum[offset : offset + 8] for offset in range(0, 40, 8)
        )
    lines = [f"#$ {fields[0]}", f"#@ {fields[1]}", *pairs, f"#h {checksum}"]
    return ("\n".join(lines) + "\n").encode("utf-8")


def main() -> int:
    schedule = json.loads(FIXTURE.read_text(encoding="utf-8"))
    OUTPUT.mkdir(parents=True, exist_ok=True)

    files = []
    for index, name in enumerate(NAMES):
        data = build(schedule, index)
        (OUTPUT / name).write_bytes(data)
        files.append(
            {
                "name": name,
                "bytes": len(data),
                "sha256": hashlib.sha256(data).hexdigest(),
            }
        )
        print(f"{name:<26} {len(data):>5} bytes  sha256 {files[-1]['sha256']}")

    manifest = {"schema": schedule["schema"], "files": files}
    (OUTPUT / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    print(f"manifest.json                 written to {OUTPUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
