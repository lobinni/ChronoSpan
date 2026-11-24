"""Direct-mode tier: consensus and storage behaviour inside the GenVM
harness.  Install ``requirements-dev.txt`` first; without it this whole
directory is skipped and the deterministic suite still runs."""

import pytest

pytest.importorskip(
    "gltest", reason="genlayer-test is not installed (see requirements-dev.txt)"
)
