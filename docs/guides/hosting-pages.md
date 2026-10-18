# Hosting and browsing pages on Reticulum

MeshDeck nodes can **host pages** (NomadNet-compatible) and **browse** pages
hosted by others. Pages are tiny, encrypted, work over any transport (radio,
LAN, serial, TCP) — no web server, no DNS, no IP addresses to share.

## Hosting your own pages

1. Open the **Pages** tab.
2. Create `index.mu` — every node needs a home page.
3. Write in **micron** markup:
   - `>Big title`, `>>Section`, `>>>Sub-section` headings
   - plain lines are paragraphs; `• ` bullets; `-` alone on a line is a divider
   - `` `*bold`* `` and `` `_underline`_ `` inline styles
   - code blocks fenced with lines containing only `` `= ``
   - links: `[label`/page/other.mu]` for other pages on your node
4. Pages are **live the moment you save** — no restarts.
5. Give your node a name and switch on **Announce my node** so others can
   find you by browsing. The announce is a plain broadcast like your chat
   address; pages are still served without it, but then only people who
   already know your node address can visit.

Your node address is the 32-character hash shown at the top of *My pages*.
Share it like a chat address.

> ⚠️ Executable pages (`.mu` files with the execute bit) are **not** run by
> MeshDeck — NomadNet executes them server-side; we deliberately keep pages
> static for safety.

## Browsing other nodes

Discovered nodes appear as chips in *Browse other nodes* after they announce.
Click one (or paste any node address) and **Open** to fetch their home page.

- `no route to that node yet` — the node may be offline or too new; a path
  request was sent automatically, try again in a minute.
- Everything you fetch comes over an encrypted, identity-verified link. The
  address you connect to is cryptographically tied to the operator's keys —
  there are no impostor nodes.

## Compatibility

MeshDeck implements the same node scheme as NomadNet (destination aspect
`nomadnetwork.node`, request paths `/page/...`), so your pages are also
browsable from NomadNet and any client speaking that protocol — and you can
browse theirs the same way.
