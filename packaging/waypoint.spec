# PyInstaller spec for a one-file Waypoint binary.
# Build with: make package   (frontend/dist must be built first)

import pathlib

ROOT = pathlib.Path(SPECPATH).parent  # repo root when invoked from repo root

block_cipher = None

# Every RNS interface module must be frozen in: Reticulum binds interface
# classes via `from RNS.Interfaces import *`, and star-import binding depends
# on what other modules have already loaded. The shim additionally
# force-imports them so ordering is guaranteed regardless.
RNS_IFACE_MODULES = [
    "RNS.Interfaces.Interface",
    "RNS.Interfaces.LocalInterface",
    "RNS.Interfaces.AutoInterface",
    "RNS.Interfaces.TCPInterface",
    "RNS.Interfaces.BackboneInterface",
    "RNS.Interfaces.UDPInterface",
    "RNS.Interfaces.I2PInterface",
    "RNS.Interfaces.RNodeInterface",
    "RNS.Interfaces.RNodeMultiInterface",
    "RNS.Interfaces.KISSInterface",
    "RNS.Interfaces.SerialInterface",
    "RNS.Interfaces.AX25KISSInterface",
    "RNS.Interfaces.PipeInterface",
    "RNS.Interfaces.WeaveInterface",
]

a = Analysis(
    [str(ROOT / "packaging" / "waypoint_main.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=[
        # embed the built web UI so the binary is fully self-contained
        (str(ROOT / "frontend" / "dist"), "frontend/dist"),
    ],
    hiddenimports=[
        *RNS_IFACE_MODULES,
        "RNS.vendor.configobj",
        "RNS.vendor.umsgpack",
        "aiohttp.web",
        "msgpack",
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=["pytest", "ruff"],
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="waypoint",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
)
