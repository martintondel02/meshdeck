"""Opt-in interop tests: real NomadNet / lxmd / official-lxmf binaries.

They are skipped unless the environment points at an external toolchain:

    MESHDECK_INTEROP_PYTHON=/tmp/interop/bin/python
    MESHDECK_INTEROP_NOMADNET=/tmp/interop/bin/nomadnet
    MESHDECK_INTEROP_LXMD=/tmp/interop/bin/lxmd

CI stays green because nothing runs without those variables. Everything is
loopback TCP with temp dirs and OS-chosen ports.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

pytestmark = pytest.mark.interop


def _tool(env: str) -> Path | None:
    raw = os.environ.get(env)
    return Path(raw) if raw else None


@pytest.fixture
def interop() -> dict[str, Path]:
    py = _tool("MESHDECK_INTEROP_PYTHON")
    if py is None or not py.exists():
        pytest.skip("MESHDECK_INTEROP_PYTHON is not set to an existing interpreter")
    tools = {"python": py}
    for key, env in (
        ("nomadnet", "MESHDECK_INTEROP_NOMADNET"),
        ("lxmd", "MESHDECK_INTEROP_LXMD"),
    ):
        path = _tool(env)
        if path is not None and path.exists():
            tools[key] = path
    return tools
