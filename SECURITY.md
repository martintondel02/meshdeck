# Security policy

MeshDeck is pre-release software. It handles private keys, messages and local
files, so security reports are welcome and taken seriously.

## Reporting a vulnerability

Please use GitHub's private vulnerability reporting for this repository:

**https://github.com/martintondel02/meshdeck/security/advisories/new**

That opens a private GitHub Security Advisory visible to the maintainers.
Please do **not** open a public issue, pull request or discussion for a
vulnerability before it has been fixed and disclosed.

A useful report includes:

- affected version or commit (the app prints `meshdeck <version>` for
  `--version`; the UI shows the version on the Settings screen),
- operating system and how MeshDeck was installed or run (source checkout,
  `make package` binary, etc.),
- a minimal reproduction, or a clear description of the attack path,
- impact: what an attacker gains (message disclosure, identity/key theft,
  local file read/write, API control, denial of service),
- relevant logs — with tokens, identity keys, private messages and peers'
  addresses removed.

There is no bug bounty and no guaranteed response time; this is a small
project. Reports are handled on a best-effort basis, and we will credit you in
the advisory unless you prefer otherwise. Please test only against your own
instance and your own nodes, not against other people's infrastructure.

## Supported versions

| Version | Supported |
|---|---|
| `0.1.1` (latest tagged release) | Yes |
| `main` (development) | Best effort |
| Any earlier commit or pre-release | No |

`v0.1.1` is the latest tagged release (v0.1.0 was the first). Fixes land on
`main` and are released in the next tag; there are no backport branches for
pre-1.0 releases.

## What MeshDeck does and does not protect

MeshDeck is an application on top of the official `rns` and `lxmf` libraries.
It does not implement cryptography or the Reticulum wire protocol itself. The
trust model is therefore mostly Reticulum's:

- **Identity and encryption.** Your identity is a Reticulum keypair stored in
  the data directory. Messages are encrypted and authenticated end-to-end by
  RNS/LXMF. There is no MeshDeck server and no account.
- **Peers are identified by destination hashes.** Display names are announced
  by peers and are neither unique nor verified. A peer can call itself
  whatever it likes; do not treat a name as an identity check.
- **Announces, pages and files are untrusted input.** MeshDeck validates page
  names and paths, caps page/file sizes and escapes page text before rendering
  it. It never executes `.mu` pages. A malicious node can still send you
  content designed to look like something else; treat browsed pages like email
  from a stranger.
- **Local API.** The daemon binds `127.0.0.1` by default. `/api/v1` and `/ws`
  require a bearer token that is generated on first run and stored with mode
  `0600`. The token grants full control of the node (send messages, change
  settings, restart, read history), so treat it like a password. The web UI
  itself is served without auth because it contains no data; all data access
  goes through the authenticated API.
- **No TLS.** There is no HTTPS listener. `--host` can bind the API to another
  interface, but that exposes the token-authenticated API over plain HTTP to
  your network. That mode is unsupported as a security boundary; keep the
  default loopback binding.
- **Data at rest is not encrypted by MeshDeck.** Messages, peers and settings
  live in SQLite; the identity key and token are files in the data directory.
  File permissions are the only protection. Use full-disk encryption and an
  OS account you trust.
- **No telemetry.** MeshDeck has no analytics, crash reporting, update checks
  or other phone-home behavior. It contacts only the Reticulum peers and
  interfaces you configure. Note that Reticulum itself is not an anonymity
  network: announces and traffic metadata may be observable to peers and
  interface operators.
- **Propagation nodes.** If you configure an LXMF propagation node, messages
  may be stored there for later delivery. The content is encrypted by LXMF, but
  the node operator can observe envelope metadata and availability patterns.

## Scope

In scope:

- authentication or authorization bypass in the local API, WebSocket or token
  handling,
- token or identity-key disclosure caused by MeshDeck (logs, error pages,
  URL handling, file permissions, temporary files),
- path traversal or arbitrary file read/write through pages, shared files,
  attachments or page names,
- XSS or HTML injection through the micron renderer or anything else fed to
  the web UI,
- crashes or resource exhaustion that a remote Reticulum peer or a malicious
  page/node can trigger,
- input-validation failures in generated Reticulum config or interface
  settings that could be used to execute code or kill the process,
- vulnerabilities in MeshDeck's own dependencies that are reachable through
  MeshDeck.

Out of scope (report upstream instead unless MeshDeck introduces the issue):

- the design of Reticulum or LXMF, including their cryptography and routing,
- vulnerabilities in `rns`, `lxmf`, NomadNet, MeshChatX or other clients,
- attacks that require root, physical access, or code already running as your
  user (such an attacker can read the token and identity anyway),
- denial of service from simply being offline or from a peer choosing not to
  respond,
- reports that only say a dependency version is outdated without a reachable
  attack path.

If you are unsure whether something is in scope, report it privately and we
will work it out together.
