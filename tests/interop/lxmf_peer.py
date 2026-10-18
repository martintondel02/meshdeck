"""Independent LXMF peer using only official rns/lxmf from /tmp/interop."""

from __future__ import annotations

import json
import sys
import tempfile
import time
from pathlib import Path

import LXMF
import RNS

port = int(sys.argv[1])
a_hex = sys.argv[2]
storage = Path(tempfile.mkdtemp(prefix="lxmf-peer-"))
cfg = Path(tempfile.mkdtemp(prefix="lxmf-rns-"))
(cfg / "config").write_text(
    "[reticulum]\n  enable_transport = No\n  share_instance = No\n"
    "[logging]\n  loglevel = 4\n"
    "[interfaces]\n  [[Loop]]\n    type = TCPClientInterface\n"
    f"    enabled = yes\n    target_host = 127.0.0.1\n    target_port = {port}\n"
)
RNS.Reticulum(configdir=str(cfg))
identity = RNS.Identity()
router = LXMF.LXMRouter(identity=identity, storagepath=str(storage), autopeer=True)
dest = router.register_delivery_identity(identity, display_name="Interop LXMF Peer")


def on_receive(lxm):
    try:
        print(json.dumps({
            "event": "received",
            "content": lxm.content.decode("utf-8", "replace")
            if isinstance(lxm.content, bytes) else str(lxm.content),
            "source": lxm.source_hash.hex(),
            "signature_valid": bool(getattr(lxm, "signature_validated", False)),
        }), flush=True)
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"event": "error", "error": str(exc)}), flush=True)


router.register_delivery_callback(on_receive)
router.announce(dest.hash)
print(json.dumps({"event": "ready", "address": dest.hash.hex()}), flush=True)

# Wait for MeshDeck's identity/path, then send one message to it.
a_dest_hash = bytes.fromhex(a_hex)
for _ in range(120):
    if RNS.Identity.recall(a_dest_hash) is not None:
        break
    RNS.Transport.request_path(a_dest_hash)
    time.sleep(0.5)
a_identity = RNS.Identity.recall(a_dest_hash)
if a_identity is None:
    print(json.dumps({"event": "error", "error": "meshdeck_identity_not_known"}), flush=True)
else:
    out_dest = RNS.Destination(
        a_identity, RNS.Destination.OUT, RNS.Destination.SINGLE, "lxmf", "delivery"
    )
    lxm = LXMF.LXMessage(
        out_dest, dest, "from lxmf to meshdeck", desired_method=LXMF.LXMessage.DIRECT
    )
    lxm.register_delivery_callback(
        lambda m: print(json.dumps({"event": "sent", "hash": m.hash.hex()}), flush=True)
    )
    lxm.register_failed_callback(
        lambda m: print(json.dumps({"event": "send_failed", "hash": m.hash.hex()}), flush=True)
    )
    lxm.pack()
    router.handle_outbound(lxm)
    print(json.dumps({"event": "sending", "hash": lxm.hash.hex()}), flush=True)

# Keep the router alive so inbound delivery callbacks can fire.
while True:
    time.sleep(1)
