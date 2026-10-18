# Interoperability with real NomadNet / LXMF / lxmd

Verified on 2026-10-19 against independent binaries in a throwaway venv
(`/tmp/interop`), with everything on loopback TCP interfaces and temp data
dirs. MeshDeck used the same working tree as the rest of this session.

## Exact versions

| Component | Version | How obtained |
|---|---|---|
| `nomadnet` | **1.4.4** | `pip install nomadnet` |
| `lxmf` (library + `lxmd` script) | **1.2.1** | dependency of NomadNet / explicit `pip install lxmf` |
| `rns` | **1.5.7** | dependency of LXMF |
| MeshDeck | **0.2.0** (Phase 7.1–7.6) | this repo |

`pip install nomadnet lxmd` **fails**: `lxmd` is not a PyPI distribution. The
`lxmd` executable ships with the `lxmf` package (`LXMF.Utilities.lxmd`), so
`pip install nomadnet lxmf` provides both. That is the command actually used.

Reproduce the toolchain:

```bash
python -m venv /tmp/interop
/tmp/interop/bin/pip install nomadnet lxmf
/tmp/interop/bin/pip list | grep -Ei 'nomadnet|lxmf|rns'
```

## Results

Everything below was run; no claim is based on reading upstream source alone.

### 1. NomadNet hosts a page → MeshDeck browses it — **verified**

Real `nomadnet -d` (node mode), `node_name = NomadNet Interop`, page in
`storage/pages/index.mu`, TCP server interface. MeshDeck B used a TCP client
interface and a temp data dir.

```
NODE: {'hash': '245d99c1...', 'name': 'Interop Node', ...}
BROWSE: 200
  {'node_hash': ..., 'path': '/page/index.mu',
   'content': '>Interop Node\n\nThis page is served by real NomadNet.\n',
   'bytes': 53, 'elapsed_ms': 52.1,
   'served_from_cache': False, 'stale': False}
PAGES INTEROP OK (NomadNet hosts -> MeshDeck browses)
```

MeshDeck used its production `/api/v1/browse` route and page client over a real
RNS link; the page bytes match exactly.

### 2. MeshDeck hosts a page → independent client fetches it — **verified (protocol-level)**

The client is a separate `/tmp/interop/bin/python` process importing **only
official RNS 1.5.7** (no MeshDeck code) and speaking the documented
NomadNet wire format: `RNS.Link` to a `nomadnetwork.node` destination, then
`link.request("/page/index.mu")`.

```
MESHDECK NODE: {'node_hash': 'cfc55962...', 'node_name': 'MeshDeck Interop'}
RAW CLIENT: {"has_path": true, "status": 2, "concluded": true,
             "response": ">MeshDeck Interop\n\nServed by MeshDeck and fetched by an independent RNS client.\n",
             "rns_version": "1.5.7"}
PAGES INTEROP OK (MeshDeck hosts -> independent RNS client)
```

**Independence note:** this is a protocol-level client, not an independent
GUI/TUI. NomadNet 1.4.4's browser lives inside its urwid TextUI
(`nomadnet/ui/textui/Browser.py`) and the `nomadnet -d` daemon does not expose
a non-interactive "fetch this page" CLI. Driving the TUI headlessly was not
attempted here; the raw client proves the wire contract but not a NomadNet UI
session.

### 3. LXMF direct exchange with official `lxmf` 1.2.1 — **verified, both directions**

A standalone peer in `/tmp/interop` (new RNS identity, `LXMRouter`, delivery
destination `Interop LXMF Peer`) connected over a loopback TCP pair.

- MeshDeck → peer: peer received `"from meshdeck to lxmf"`, source hash equal
  to MeshDeck's chat address, `signature_valid: true`.
- Peer → MeshDeck: MeshDeck's `/api/v1/messages` shows
  `"from lxmf to meshdeck"` with `peer_hash` equal to the peer's address.

```
PEER: {'event': 'received', 'content': 'from meshdeck to lxmf',
       'source': '42d48e8d...', 'signature_valid': True}
MESHDECK RECEIVED FROM PEER OK: from lxmf to meshdeck
LXMF INTEROP OK (both directions, official lxmf 1.2.1 peer)
```

### 4. Real `lxmd` propagation node — **verified store-and-forward**

`lxmd -p` (propagation node, 50 MB store, stamp cost 13, TCP server with
transport enabled). MeshDeck A was configured with `delivery_method =
propagated` and `propagation_node_hash` = lxmd's propagation address.

1. An offline peer C announced its delivery identity, then went away.
2. MeshDeck sent `"propagated through real lxmd"` to C; lxmd stored it.
3. C came back, set lxmd as its outbound propagation node and synced.

```
C SYNC: {"event": "received", "content": "propagated through real lxmd",
         "source": "961162ae...", "signature_valid": true}
LXMD PROPAGATION INTEROP OK
```

### 5. MeshDeck hosting a propagation node → independent sender + receiver — **verified**

MeshDeck A hosted (`host_propagation_node = true`, transport enabled). A
separate official-`lxmf` sender D submitted a propagated message to offline C
through A; C later synced from A.

```
SENDER: {"event": "delivered", "hash": "5f7669c8..."}
PN AFTER SEND: {'hosting': True, 'stored_messages': 1, 'store_bytes': 272,
                'messages_received': 1, 'messages_served': 0, ...}
C SYNC: {"event": "received",
         "content": "via MeshDeck PN from independent sender",
         "source": "ffe63ff3...", "signature_valid": true}
MESHDECK PN + INDEPENDENT SENDER/RECEIVER OK
```

This also exercises the Phase 7.5 dashboard counters on the real router.

## Opt-in tests

`tests/interop/test_interop.py` codifies the four scenarios above. They are
marked `interop` and skipped unless all required paths are supplied:

```bash
MESHDECK_INTEROP_PYTHON=/tmp/interop/bin/python \
MESHDECK_INTEROP_NOMADNET=/tmp/interop/bin/nomadnet \
MESHDECK_INTEROP_LXMD=/tmp/interop/bin/lxmd \
.venv/bin/python -m pytest tests/interop -m interop -q
```

They use loopback TCP, temp dirs, OS-chosen ports and process-group teardown;
nothing touches the host network or the real user data dir. Without the env
vars pytest deselects/skips them, so CI stays green.

## Not tested / not claimed

- **Sideband, Android, iOS, MeshChat/MeshChatX** — no binaries used.
- **NomadNet's TUI browser** — not driven headlessly; direction 2 is a raw RNS
  protocol client, not an independent UI.
- **lxmd autopeering** with MeshDeck hosting — the propagation tests used a
  single PN and explicit addresses, not automatic peer discovery.
- **Large interop transfers** (multi-MiB attachments/resources), propagation
  stamp costs above the minimum 13, retries under loss, and cross-platform
  (Windows/macOS) binaries.
- **NomadNet inline images / `/media`** — MeshDeck does not implement them.
