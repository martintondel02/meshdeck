# Sending files & managing contacts

> This content also ships inside the app under **Guides** — no internet needed.

## Sending a file

1. Open a chat with the recipient.
2. Press the 📎 paperclip and pick a file (current limit: ~1.5 MB per message).
3. Optionally type a caption — it travels with the file.
4. The bubble shows a 📎 chip with the filename and size, plus the usual
   delivery ticks (… → ✓ → ✓✓ when the peer's node confirms).

Files ride **inside the LXMF message**, so they're end-to-end encrypted and
signed exactly like chat text. MeshDeck stores received files under
`<data-dir>/files/<peer-hash>/<message-hash>/` and serves them to the UI via
`/api/v1/attachments/…` (token-protected).

### Notes

- Peer runs MeshChat/Sideband? They typically accept up to 1 MB inbound;
  oversize files simply fail with a "failed" tick instead of hanging.
- The filename is sanitized before saving (directory components are dropped;
  odd characters are replaced) — path traversal is not possible.
- File integrity: every attachment carries a SHA-256 in its metadata; the
  integration test transfers a random 1 MiB file and asserts hash equality.

## Contacts

- **Discover automatically**: peers appear when they announce (they'll show a
  green dot if seen in the last 10 minutes).
- **Add by address**: press ＋ in the Peers panel and paste their 32-character
  hash. MeshDeck asks the network for a path to them immediately — no need to
  wait for an announce.
- **Rename**: ⋯ → Rename… gives a peer a local nickname.
- **Block**: ⋯ → Block hides their messages; the peer disappears from the list.
