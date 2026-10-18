"""Offline LXMF peer for the lxmd propagation interop probe."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import LXMF
import RNS

mode, base, port, pn_hex = sys.argv[1], Path(sys.argv[2]), int(sys.argv[3]), sys.argv[4]
base.mkdir(parents=True, exist_ok=True)
cfg = base / "rns"
cfg.mkdir(exist_ok=True)
(cfg / "config").write_text(
    "[reticulum]\n  enable_transport = No\n  share_instance = No\n"
    "[logging]\n  loglevel = 4\n"
    "[interfaces]\n  [[Loop]]\n    type = TCPClientInterface\n"
    f"    enabled = yes\n    target_host = 127.0.0.1\n    target_port = {port}\n"
)
RNS.Reticulum(configdir=str(cfg))
identity_path = base / "identity"
if identity_path.exists():
    identity = RNS.Identity.from_file(str(identity_path))
else:
    identity = RNS.Identity()
    identity.to_file(str(identity_path))

storage = base / "lxmf"
storage.mkdir(exist_ok=True)
router = LXMF.LXMRouter(
    identity=identity, storagepath=str(storage), autopeer=False
)
dest = router.register_delivery_identity(identity, display_name="Offline Peer C")
address = dest.hash.hex()

if mode == "announce":
    router.announce(dest.hash)
    print(json.dumps({"event": "announced", "address": address}), flush=True)
    time.sleep(8)
    raise SystemExit(0)

received: list[dict] = []


def on_receive(lxm):
    data = {
        "event": "received",
        "content": lxm.content.decode("utf-8", "replace")
        if isinstance(lxm.content, bytes) else str(lxm.content),
        "source": lxm.source_hash.hex(),
        "signature_valid": bool(getattr(lxm, "signature_validated", False)),
    }
    received.append(data)
    print(json.dumps(data), flush=True)


router.register_delivery_callback(on_receive)
print(json.dumps({"event": "ready", "address": address}), flush=True)
router.set_outbound_propagation_node(bytes.fromhex(pn_hex))
router.request_messages_from_propagation_node(identity)
print(json.dumps({"event": "sync_requested", "pn": pn_hex}), flush=True)
deadline = time.time() + 120
while time.time() < deadline and not received:
    time.sleep(0.5)
print(json.dumps({"event": "done", "received": len(received)}), flush=True)
