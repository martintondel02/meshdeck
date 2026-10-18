"""Independent LXMF sender (official lxmf) submitting a propagated message."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import LXMF
import RNS

base, port, pn_hex, recipient_hex, content = (
    Path(sys.argv[1]), int(sys.argv[2]), sys.argv[3], sys.argv[4], sys.argv[5]
)
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
router = LXMF.LXMRouter(identity=identity, storagepath=str(storage), autopeer=False)
own = router.register_delivery_identity(identity, display_name="Interop Sender D")
router.announce(own.hash)
print(json.dumps({"event": "ready", "sender": own.hash.hex()}), flush=True)

pn = bytes.fromhex(pn_hex)
router.set_outbound_propagation_node(pn)
recipient = bytes.fromhex(recipient_hex)
for _ in range(120):
    if RNS.Identity.recall(recipient) is not None:
        break
    RNS.Transport.request_path(recipient)
    time.sleep(0.5)
rec_identity = RNS.Identity.recall(recipient)
if rec_identity is None:
    print(json.dumps({"event": "error", "error": "recipient_identity_not_known"}), flush=True)
    raise SystemExit(1)
rec_dest = RNS.Destination(
    rec_identity, RNS.Destination.OUT, RNS.Destination.SINGLE, "lxmf", "delivery"
)
lxm = LXMF.LXMessage(
    rec_dest, own, content, desired_method=LXMF.LXMessage.PROPAGATED
)
result: list[str] = []
lxm.register_delivery_callback(
    lambda m: (result.append("delivered"), print(json.dumps({"event": "delivered", "hash": m.hash.hex()}), flush=True))
)
lxm.register_failed_callback(
    lambda m: (result.append("failed"), print(json.dumps({"event": "failed", "hash": m.hash.hex()}), flush=True))
)
lxm.pack()
router.handle_outbound(lxm)
print(json.dumps({"event": "sending", "hash": lxm.hash.hex()}), flush=True)
deadline = time.time() + 60
while time.time() < deadline and not result:
    time.sleep(0.5)
print(json.dumps({"event": "done", "result": result}), flush=True)
