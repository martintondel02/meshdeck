# Screenshots

The README shows four screenshots, captured from the running app. They are
captures of real daemons with throwaway data — nothing is mocked up or drawn in
an editor. Captured 2026-10-18 at 1440×900 with Playwright/Chromium against two
local nodes (Ada and Grace, throwaway identities).

## Wanted

| File | Screen | What it should show |
|---|---|---|
| `01-chats.png` | Chats | Two peers in the sidebar, an open conversation with a few short messages, delivery ticks (✓/✓✓), and one file attachment chip. This is the README hero shot. |
| `02-pages-editor.png` | Pages & Node | The page editor with a small `index.mu` in the textarea, or the edit/preview toggle showing a rendered page. The "My pages" list should have at least `index.mu`. |
| `03-browse-node.png` | Pages & Node → reader | A page fetched from the other local node: node name, a heading/bullets/link rendered by the micron reader, and the ← back control visible. |
| `04-settings-advanced.png` | Settings (advanced) | Advanced mode on, the transport-node toggle, the Message delivery section, and the propagation-host node toggle with its address. |

Optional, only if they add something the four above do not:

| File | Screen | What it should show |
|---|---|---|
| `05-onboarding.png` | First run | The "Welcome to MeshDeck" card with the display-name field, before the main UI. |
| `06-guides.png` | Guides | The Guides tab with two or three guide sections and the glossary visible. |
| `07-transfer.png` | Pages & Node | The transfer progress bar mid-download of a large node file. Hard to time; skip it rather than fake it. |

## Capture recipe

Two instances on one machine are enough. Use a throwaway data directory so no
real identity, address or message ends up in a PNG:

```bash
rm -rf /tmp/meshdeck-shots
.venv/bin/python -m meshdeck --data-dir /tmp/meshdeck-shots/a --port 8570 --open-browser
.venv/bin/python -m meshdeck --data-dir /tmp/meshdeck-shots/b --port 8571 --open-browser
```

1. Give the instances neutral display names (for example "Ada" and "Grace").
2. Copy the address from each instance's Settings screen and add it as a peer in
   the other (`＋` in the Peers panel). Exchange a few messages and attach a
   small file. Wait for the delivery ticks; stamps may take a few seconds.
3. On one instance, create `index.mu` with a heading, a bullet list and a link
   (for example ``[Second page`/page/second.mu]``), plus `second.mu`. Turn on
   "Announce my node" and name the node.
4. On the other instance, open Pages → Browse other nodes and open the first
   node. Capture the reader with the back control visible.
5. For the advanced Settings shot, switch the mode toggle to Advanced, then
   scroll to the interface table / transport / delivery sections.
6. Reset when done: stop both daemons and delete `/tmp/meshdeck-shots`.

## Rules

- **Privacy:** no real addresses, peer names, messages, file names or tokens.
  Use the throwaway directories above and check the image before committing.
- **State:** capture at 1440×900 or 1600×1000 with browser zoom at 100%. The app
  has a single dark theme, so no theme switch is needed.
- **Framing:** the app window only, no browser chrome, OS taskbar or desktop.
  Keep the header (address, nav) visible so the shot is recognisably MeshDeck.
- **No mockups:** do not assemble screenshots from parts, and do not capture a
  different app. If the app cannot show something yet, leave the shot out.
- **Format:** PNG, one file per shot, named exactly as in the tables. Keep each
  under roughly 400 KiB if a lossless optimiser is available.
- **Where they go:** `docs/screenshots/<name>.png`. Once the four primary shots
  exist, embed them in `README.md` (hero image after the status paragraph, the
  rest in a two-column table or one per section) and remove the "Screenshots are
  not committed yet" note there.

## Tooling

If Playwright/Chromium is already available, a one-off
`npx playwright screenshot` run is enough; do not add `@playwright/test` to
`frontend/package.json` just for this (it is deliberately not a dependency).
Otherwise capture manually with the browser's screenshot tool and ask a human
for the images. Either way, the images must come from the running app.
