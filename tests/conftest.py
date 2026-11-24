"""Shared fixtures for the ChronoSpan test-suite.

The contract source is loaded with its GenVM import and its contract class
stripped away, so the deterministic core - publisher parsing, the label
codec and the interval engine - runs under plain CPython with no VM, no
network and no mocks.  Consensus and storage behaviour are covered
separately by ``tests/direct/``.
"""

import ast
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "contracts" / "chrono_span.py"
FIXTURES = ROOT / "tests" / "fixtures"


@pytest.fixture(scope="session")
def schedule() -> dict:
    """The normalized record the two publisher files are expected to agree
    on, together with the publisher metadata that accompanies it."""
    return json.loads((FIXTURES / "schedule.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def core() -> dict:
    """Module-level namespace of ``contracts/chrono_span.py`` minus the
    GenVM import and the ``ChronoSpan`` class."""
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


@pytest.fixture
def document(schedule):
    """Rebuild a publisher file from the fixture record, so a test can alter
    one field at a time and watch the parser reject it."""

    def build(source_index: int = 0, rows=None, expires=None) -> bytes:
        source = schedule["sources"][source_index]
        rows = schedule["rows"] if rows is None else rows
        expiry = source["expires_ntp"] if expires is None else expires
        pairs = [f"{stamp}  {offset}" for stamp, offset in rows]
        fields = [str(source["updated_ntp"]), str(expiry), *pairs]
        material = "".join("".join(fields).split())
        checksum = hashlib.sha1(material.encode("ascii")).hexdigest()
        if source_index == 0:
            # IERS prints the digest in five 8-character groups.
            checksum = " ".join(
                checksum[offset : offset + 8] for offset in range(0, 40, 8)
            )
        lines = [f"#$ {fields[0]}", f"#@ {fields[1]}", *pairs, f"#h {checksum}"]
        return ("\n".join(lines) + "\n").encode("utf-8")

    return build


@pytest.fixture
def fetcher(core, document):
    """Build a deterministic ``fetch`` replacement that records the urls it
    was asked for, exactly like the contract's consensus input."""

    def build(bodies=None, status: int = 200):
        calls: list = []

        def fetch(url: str):
            calls.append(url)
            index = core["PUBLISHERS"].index(url)
            body = document(index) if bodies is None else bodies[index]
            return SimpleNamespace(status=status, body=body)

        fetch.calls = calls
        return fetch

    return build
