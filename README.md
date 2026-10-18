# Waypoint

> An all-in-one Reticulum application — chat, file sharing, page hosting and network infrastructure, with a basic mode for everyone and an advanced mode for tinkerers.

**Status:** early development (Phase 1). Working title "Waypoint" — final name TBD.

Waypoint is a free and open-source application built on the
[Reticulum Network Stack](https://reticulum.network/). It aims to be the
friendly front door to Reticulum: one program where you can message people,
send files, publish pages, and run your own piece of network infrastructure —
without ever touching a config file, unless you *want* to.

It fills a similar space to [MeshChatX](https://github.com/Quad4-Software/MeshChatX)
(development ends January 2027), but is a fresh codebase with a different
design focus: two first-class UI modes and guides/tooltips built into every
screen. Waypoint is fully interoperable with MeshChatX and other LXMF-based
apps on the messaging layer.

## Design pillars

1. **Two modes, one app.**
   - **Basic mode** — sane defaults, zero jargon on screen, wizards and
     tooltips for everything. Connects locally via AutoInterface, with
     optional one-click public entrypoints. No config text visible anywhere.
   - **Advanced mode** — unlocks the interface editor, raw Reticulum config,
     transport-node / public-entrypoint hosting, path diagnostics, micron
     page editing, and network maps. Advanced mode *adds*; it never changes
     how basic features behave.
2. **Docs in the app, not next to it.** Every screen carries contextual help:
   tooltips ("What is an announce?"), guided first-run flows, and short
   guides shipped with the app and readable offline.
3. **Stand on the official stack.** We use the reference `rns` and `lxmf`
   Python packages as dependencies. We do not reimplement the protocol;
   we build the application on top of it — like NomadNet, Sideband and
   MeshChatX do.
4. **Own your infrastructure.** Hosting a page, a propagation node or a
   public entrypoint is a first-class, guided feature — not a hidden expert
   trick. Small personal nodes are what make Reticulum resilient.

## Architecture (overview)

```
Frontend (Vite + Svelte web UI, runs in any browser)
    └── WebSocket/REST ──► local Python daemon (127.0.0.1 only)
                               ├── Identity & contacts
                               ├── LXMF router (chat, store-and-forward)
                               ├── File transfer service
                               ├── Page/site hosting (micron nodes)
                               └── Interface & transport-node manager
                                        │
                                     RNS core
              (AutoInterface · TCP/Backbone · RNode/LoRa · I2P · …)
```

**The full build plan — architecture, API spec, storage schema, phases, and
testing strategy — is in [BUILD_PLAN.md](BUILD_PLAN.md).** It is the single
source of truth for development.

## Development quickstart

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .          # once pyproject.toml lands (Phase 1, step 1)
python -m waypoint
```

Current status and next steps: [BUILD_PLAN.md §12 and §15](BUILD_PLAN.md).

## License

Waypoint's own code is MIT — see [LICENSE](LICENSE). Reticulum and LXMF are
distributed under their own licenses (Copyright (c) Mark Qvist and others,
see the upstream projects); using them as libraries imposes no copyleft on
Waypoint, but redistribution of the stack itself must follow the
[Reticulum license](https://github.com/markqvist/Reticulum/blob/master/LICENSE).

## Acknowledgements

- [Mark Qvist](https://github.com/markqvist) — Reticulum, LXMF, NomadNet.
- [Liam Cottle](https://github.com/liamcottle) — original MeshChat.
- [Quad4 Software](https://github.com/Quad4-Software) — MeshChatX, which
  demonstrated what a modern Reticulum client can be, and whose source is a
  reference for protocol-integration patterns.
