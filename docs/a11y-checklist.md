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

- [ ] **Not run in a browser.** This environment has no Chromium/Playwright and no JS DOM harness, and the daemon's Python deps (RNS/LXMF) are not installed, so the app could not be served and driven end-to-end. Behaviour above is implemented and type/compile-checked, not exercised.
- [ ] **Screen-reader pass not performed** — no screen reader (Orca/NVDA/VoiceOver) available here. Role/label choices follow the WAI-ARIA Authoring Practices by inspection only; announcements (especially the always-mounted `role="status"` regions) are untested with assistive tech.

## Follow-ups found but left out of scope

- Focus-trap helper is duplicated in `PeerList.svelte`/`Onboarding.svelte`; extract to `lib/a11y.ts` when new modules are allowed.
- `Settings.svelte`, `Pages.svelte` (`✕`/copy buttons, `saved copy` messages) and `TransferBar.svelte` (transfer progress text) still need the same treatment.
- Every `Tooltip` marker is now a tab stop; in long forms this adds stops — consider skipping tooltip markers in the tab order unless the field is focused.
