#!/usr/bin/env python3
"""PyInstaller entry shim: python -m meshdeck as an importable main().

Packaging shim note: RNS.Reticulum populates its module namespace with the
interface modules via `from RNS.Interfaces import *`. A star-import on a
package without `__all__` discovers submodules by enumerating the PACKAGE
DIRECTORY on disk — which does not exist inside the frozen binary. So the
binary boots to `NameError: BackboneInterface is not defined`.

The workaround below is pure namespace binding (no behaviour change): import
the interface modules — which PyInstaller froze into the archive via
hiddenimports — and bind them as attributes on the *real* RNS.Reticulum
module before anything constructs a Reticulum instance. Normal (non-frozen)
installs never run this file.

CAREFUL: `import RNS.Reticulum` returns the re-exported CLASS, not the
module, because RNS/__init__ does `from .Reticulum import Reticulum`. Use
importlib.import_module and patch THAT.
"""

from __future__ import annotations

import importlib
import sys

_IFACE_MODULES = [
    "Interface",
    "LocalInterface",
    "AutoInterface",
    "TCPInterface",
    "BackboneInterface",
    "UDPInterface",
    "I2PInterface",
    "RNodeInterface",
    "RNodeMultiInterface",
    "KISSInterface",
    "SerialInterface",
    "AX25KISSInterface",
    "PipeInterface",
    "WeaveInterface",
]


def _bind_rns_interfaces() -> None:
    modules = {}
    for name in _IFACE_MODULES:
        try:
            modules[name] = importlib.import_module(f"RNS.Interfaces.{name}")
        except ImportError:
            continue  # optional-hardware modules may be absent; fine
    rns_reticulum_module = importlib.import_module("RNS.Reticulum")
    for name, module in modules.items():
        setattr(rns_reticulum_module, name, module)


_bind_rns_interfaces()

from meshdeck.__main__ import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
