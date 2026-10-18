# Accessibility checklist — Phase 5.4

Date: 2026-10-18. Strict file scope: `frontend/src/App.svelte`,
`frontend/src/components/PeerList.svelte`, `frontend/src/components/ChatView.svelte`,
`frontend/src/components/Onboarding.svelte`, `frontend/src/components/Tooltip.svelte`,
`frontend/src/app.css`. `Settings.svelte`, `Pages.svelte`, `TransferBar.svelte`,
stores, backend and tests were **not** touched.

Verification run: `cd frontend && pnpm run check` → **0 errors, 0 warnings**;
`pnpm run build` → success (vite build, 128 modules).
A `[x]` means the change is implemented in the scoped files and accepted by
`svelte-check`/the build; only the contrast ratios and the built-CSS rule were
independently computed/observed. `[ ]` means it could not be verified in this
environment (reason on the line). No browser or screen reader was available, so
no item here was exercised by a human or assistive technology.

## 1. Modals and inline add-peer form

- [x] PeerList add-peer form is a `role="dialog"` with `aria-label`, first field (`bind:this`) focused on open via `$effect`, Tab/Shift+Tab trapped inside the form, Escape closes it and returns focus to the `＋` trigger.
- [x] PeerList `＋` trigger exposes `aria-expanded` + `aria-controls="add-peer-form"` and toggles the form instead of only mutating a hidden flag.
- [x] PeerList peer options (`⋯`) is a `role="menu"`; first `role="menuitem"` is focused on open, ArrowUp/ArrowDown cycle items, Escape and Tab close it and restore focus to the trigger.
- [x] Inline rename: `aria-label` on the nickname field, Enter saves, Escape cancels and returns focus to the peer row; focus goes back to the row after saving.
- [x] Onboarding is a first-run dialog: `role="dialog"`, `aria-modal="true"`, `aria-labelledby`/`aria-describedby`, display-name field focused on mount, Tab trapped in the panel, Enter submits.
- [x] Onboarding label is now programmatically associated (`<label for="onboarding-name">` + `id`); previously the label was not linked to the input at all.
- [x] Onboarding Escape returns focus to the display-name field. **Deliberate deviation:** there is no trigger/underlying UI on first run, so Escape does not dismiss setup (dismissing would leave the app unusable).

## 2. Icon-only buttons

- [x] PeerList `＋`: `aria-label="Add a peer by address"` + `title`, glyph marked `aria-hidden`.
- [x] PeerList `⋯`: `aria-label="Options for <peer>"` + `title`, `aria-haspopup="menu"`/`aria-expanded`/`aria-controls`, glyph `aria-hidden`.
- [x] ChatView `📎` attach: `aria-label` includes the size limit (and "Sending attachment…" while busy), `aria-busy`, existing `title` kept, glyph `aria-hidden`.
- [x] ChatView message-state glyphs (`…`, `✓`, `✓✓`, `✗`): `aria-hidden`, with `sr-only` text (sending / sent / delivered / failed to send) and the existing delivery tooltip.
- [x] ChatView attachment download link: `sr-only` "Download attachment:" prefix, `📎`/`⬇` glyphs `aria-hidden`, `title` kept.
- [x] ChatView Send button is not icon-only (visible text "Send"), so its name is already correct.
- [x] ChatView search and composer inputs have `aria-label`s (previously placeholder-only).
- [ ] `✕` close buttons and `copy` buttons: **none exist in the in-scope components** (they live in `Pages.svelte`/`TransferBar.svelte`, out of scope) — nothing to label here; they remain to do in those files.

## 3. Navigation tabs

- [x] App.svelte uses a full tab pattern: `nav aria-label` + `role="tablist"`, buttons `role="tab"` with `aria-selected`/`aria-controls`/roving `tabindex`, panels `role="tabpanel"` with `aria-labelledby`.
- [x] Keyboard: ArrowLeft/ArrowRight/Home/End move selection and focus (roving tabindex); tab order is one stop for the whole tablist.
- [x] Visible focus: global `:focus-visible` rule in `app.css` (accent outline, 2px, offset 2px); focus ring contrast is 8.03:1 on `wp-panel` / 8.63:1 on `wp-bg`, above the 3:1 non-text minimum.

## 4. Live regions

- [x] PeerList "peer added" confirmation **and** add error: always-mounted `role="status" aria-live="polite"` region (visible text still rendered conditionally, so empty regions add no layout).
- [x] ChatView send/attachment errors: always-mounted wrapper `role="status" aria-live="polite" aria-atomic="true"`.
- [x] App.svelte connection state: `sr-only` `role="status" aria-live="polite"` text ("Connected…" / "Daemon connection lost — reconnecting."); the colour dot is `aria-hidden` with a hover `title`.
- [x] App.svelte boot error is `role="alert"`; the initial "Starting…" screen is `role="status"`.
- [x] Onboarding error: always-mounted `role="status"` `sr-only` region.
- [ ] "copied" confirmation: **no copy control exists in scope** (Pages.svelte has one, out of scope) — not applicable in these files.

## 5. Contrast and reduced motion

- [x] `wp-dim` (#8ca3b2) measured with the WCAG 2.1 relative-luminance formula — **before = after, no token change needed**:

  | Pair | Ratio | Requirement |
  |---|---|---|
  | `#8ca3b2` on `wp-bg` `#0b0f14` | **7.32:1** | ≥ 4.5:1 (AA normal text) |
  | `#8ca3b2` on `wp-panel` `#11181f` | **6.81:1** | ≥ 4.5:1 |
  | `#8ca3b2` on `wp-panel2` `#182430` | **6.00:1** | ≥ 4.5:1 |

  Because all pairs already pass, the minimal-change rule was satisfied by leaving the token as-is (before/after identical); the measured values are recorded beside the token in `app.css`.
- [x] `@media (prefers-reduced-motion: reduce)` disables transitions/animations (including `scroll-behavior`) for all elements; ChatView's autoscroll switches `behavior` to `auto` when the media query matches.
- [x] `border-wp-dim/40` on the tooltip marker is decorative (the `?` glyph itself is 6:1); no non-text contrast failure introduced.

## 6. Keyboard-only walkthrough (onboarding → add peer → chat → attach → pages → save → settings → restart note)

**Phase 7.3 rerun (2026-10-19): exercised.** Two real daemons were started on a
loopback TCP pair, and a one-off Playwright 1.56 + cached Chromium 1248 run
(`/tmp/pw/kb.mjs`, not a project dependency) drove the flow **keyboard-only**
(Tab/Shift+Tab, Enter/Space, arrow keys for the roving-tabindex tablist). No
mouse clicks were used. Results (`/tmp/kb-results.json`): **all 9 steps passed,
0 console errors**, 0.9 s of UI actions; a cross-daemon check confirmed B
received the text and the separate attachment message (`attachment_files=1`),
and A persisted the typed page + `transport_enabled=true`.

- [x] Onboarding: name field auto-focused, typed, Enter submitted.
- [x] Add peer: Tab to `＋` (4 tabs), Enter opened the dialog with the field focused, typed hash, Enter submitted, peer row appeared.
- [x] Open chat: Escape closed the dialog (focus returned to `＋`), Tab to the peer row (1 tab), Enter opened it.
- [x] Send message: Tab to the composer (5 tabs), typed text, Enter sent; B received it over the real link.
- [x] Attach a file: Tab to `📎` (11 tabs), Enter opened the file chooser; Playwright supplied the payload **because a native OS dialog cannot be typed into headlessly** (recorded exception, not a mouse interaction); the chip appeared and B stored the blob.
- [x] Pages: Tab to the selected `Chats` tab (4 tabs), **ArrowRight** selected/focused `Pages` (ARIA tab pattern; non-selected tabs are `tabindex=-1` and are not Tab stops), Tab to name (2), typed `index.mu`, Tab to `＋` Create (1), Enter; Tab to editor (4), typed content, Tab to Save (22), Enter; `saved ✓`.
- [x] Settings: Tab to selected `Pages` tab (16), **End** jumped to `Settings`; Tab to `Switch to Advanced mode` (5), Enter; Storage card showed every usage line (page cache, attachments, shared files, hosted pages, message history, logs).
- [x] Restart note: Tab to the transport checkbox (17), Space toggled it, `Restart required for connection changes.` appeared.
- [x] No console/page errors during the run.

Earlier Phase 5.4 note (kept for history): at that time this environment had no
Chromium/Playwright and no JS DOM harness, so the walkthrough was not run then.

## 7. Screen reader — Orca attempt (Phase 7.3, 2026-10-19)

Orca **is installed** (`Orca version 50.3`, AT-SPI2 2.60.7) and runs in this
GNOME/Wayland session. A headed Chromium (Playwright, `--force-renderer-accessibility`)
was navigated through MeshDeck with Orca active and `--debug-file` logging.

- [x] Orca started (`orca --replace --debug-file /tmp/orca-run.out`), exit 0.
- [x] `orca --list-apps` showed the desktop's accessible applications; Orca attached to Chromium and activated its Chromium script **154 times**.
- [x] Orca's debug log records MeshDeck's accessible content and generated speech-dispatcher utterances, e.g. `SAY ALL PRESENTER: Speaking … 'Ada'`, the identity hash, `'Help'`, and `SPEECH DISPATCHER: Speaking '<speak>…Ada</speak>'` (8 `SAY ALL PRESENTER: Speaking` lines).
- [ ] **Announcement heard/validated by a listener: NOT VERIFIED.** The agent has no audio perception; no human listener was present. The log proves Orca produced utterances for MeshDeck's accessible tree, not that they were intelligible or correct in context.
- [ ] Focus-order/announcement quality review with a screen-reader user: **NOT VERIFIED**.

## Follow-ups found but left out of scope

- Focus-trap helper is duplicated in `PeerList.svelte`/`Onboarding.svelte`; extract to `lib/a11y.ts` when new modules are allowed.
- `Settings.svelte`, `Pages.svelte` (`✕`/copy buttons, `saved copy` messages) and `TransferBar.svelte` (transfer progress text) still need the same treatment.
- Every `Tooltip` marker is now a tab stop; in long forms this adds stops — consider skipping tooltip markers in the tab order unless the field is focused.
