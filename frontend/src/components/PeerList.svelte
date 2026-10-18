<script lang="ts">
  import { api } from "../lib/api";
  import { activePeer, clearUnread, peers, peerLabel, unread } from "../lib/stores";
  import { timeAgo } from "../lib/format";
  import type { Peer } from "../lib/stores";
  import Tooltip from "./Tooltip.svelte";
  import { TOOLTIPS } from "../lib/copy/tooltips";

  let showAdd = $state(false);
  let addInput = $state("");
  let addHint = $state("");
  let addError = $state("");
  let addBusy = $state(false);
  let menuFor = $state<string | null>(null);
  let renameFor = $state<string | null>(null);
  let renameValue = $state("");

  let addTrigger: HTMLButtonElement | undefined = $state();
  let addForm: HTMLFormElement | undefined = $state();
  let addField: HTMLInputElement | undefined = $state();
  let menuEl: HTMLDivElement | undefined = $state();
  let menuTrigger: HTMLElement | undefined;
  let renameInput: HTMLInputElement | undefined = $state();

  const FOCUSABLE =
    'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';
  const addStatus = $derived(addHint || addError);

  function isRecentlySeen(hash: string): boolean {
    const peer = $peers.find((p) => p.hash === hash);
    return !!peer?.last_seen && Date.now() / 1000 - peer.last_seen < 600;
  }

  function rowLabel(peer: Peer): string {
    const seen = isRecentlySeen(peer.hash) ? "seen recently" : "not seen recently";
    const unreadCount = $unread[peer.hash] ?? 0;
    return `Open chat with ${peerLabel(peer)} (${seen})${unreadCount > 0 ? `, ${unreadCount} unread` : ""}`;
  }

  // Inline add-peer form behaves as a small dialog: first field on open, Tab
  // cycles inside it, Escape closes and returns focus to the ＋ trigger.
  function openAdd() {
    showAdd = true;
    addHint = "";
    addError = "";
  }

  function closeAdd() {
    showAdd = false;
    addTrigger?.focus();
  }

  function trapTab(e: KeyboardEvent, root: HTMLElement | undefined) {
    if (e.key !== "Tab" || !root) return;
    const items = Array.from(root.querySelectorAll<HTMLElement>(FOCUSABLE)).filter(
      (el) => el.offsetWidth > 0 || el.offsetHeight > 0,
    );
    if (items.length === 0) return;
    const first = items[0];
    const last = items[items.length - 1];
    if (!first || !last) return;
    if (e.shiftKey && document.activeElement === first) {
      e.preventDefault();
      last.focus();
    } else if (!e.shiftKey && document.activeElement === last) {
      e.preventDefault();
      first.focus();
    }
  }

  function onAddKeydown(e: KeyboardEvent) {
    if (e.key === "Escape") {
      e.preventDefault();
      e.stopPropagation();
      closeAdd();
      return;
    }
    trapTab(e, addForm);
  }

  function toggleMenu(hash: string, e: MouseEvent) {
    e.stopPropagation();
    if (menuFor === hash) {
      menuFor = null;
      return;
    }
    menuTrigger = e.currentTarget as HTMLElement;
    menuFor = hash;
  }

  function closeMenu(restoreFocus: boolean) {
    menuFor = null;
    if (restoreFocus) menuTrigger?.focus();
  }

  function onMenuKeydown(e: KeyboardEvent) {
    if (e.key === "Escape") {
      e.preventDefault();
      closeMenu(true);
      return;
    }
    if (e.key === "Tab") {
      // Tab leaves the menu; put focus back on the trigger first so the
      // default Tab action continues from a stable position.
      closeMenu(true);
      return;
    }
    if (e.key !== "ArrowDown" && e.key !== "ArrowUp") return;
    const items = Array.from(
      menuEl?.querySelectorAll<HTMLElement>('[role="menuitem"]') ?? [],
    );
    if (items.length === 0) return;
    e.preventDefault();
    const i = items.indexOf(document.activeElement as HTMLElement);
    const next =
      e.key === "ArrowDown"
        ? (i + 1 + items.length) % items.length
        : (i - 1 + items.length) % items.length;
    items[next]?.focus();
  }

  function openRename(peer: Peer) {
    renameFor = peer.hash;
    renameValue = peer.nickname ?? "";
    closeMenu(false);
  }

  function cancelRename(hash: string) {
    renameFor = null;
    document.getElementById(`peer-row-${hash}`)?.focus();
  }

  $effect(() => {
    if (showAdd) addField?.focus();
  });

  $effect(() => {
    if (!menuFor) return;
    menuEl?.querySelector<HTMLElement>('[role="menuitem"]')?.focus();
  });

  $effect(() => {
    if (renameFor) renameInput?.focus();
  });

  async function submitAdd(e: Event) {
    e.preventDefault();
    addBusy = true;
    addError = "";
    addHint = "";
    try {
      const res = await api<{ known: boolean; path_requested: boolean }>(
        "/api/v1/peers",
        { method: "POST", body: JSON.stringify({ hash: addInput.trim() }) },
      );
      addHint = res.known
        ? "Added — you can message them right away."
        : "Added. We asked the network for a path; you're set once they announce (usually within a minute).";
      addInput = "";
      peers.set(await api<Peer[]>("/api/v1/peers"));
      addField?.focus();
    } catch {
      addError = "Not a valid address. It should be a 32-character hexadecimal hash.";
    } finally {
      addBusy = false;
    }
  }

  async function saveRename(hash: string) {
    await api(`/api/v1/peers/${hash}`, {
      method: "PATCH",
      body: JSON.stringify({ nickname: renameValue.trim() }),
    });
    peers.set(await api<Peer[]>("/api/v1/peers"));
    renameFor = null;
    document.getElementById(`peer-row-${hash}`)?.focus();
  }

  async function blockPeer(hash: string) {
    await api(`/api/v1/peers/${hash}`, {
      method: "PATCH",
      body: JSON.stringify({ blocked: true }),
    });
    if ($activePeer === hash) activePeer.set(null);
    peers.set(await api<Peer[]>("/api/v1/peers"));
    closeMenu(true);
  }
</script>

<div class="h-full flex flex-col">
  <div class="px-4 py-3 border-b border-wp-border flex items-center justify-between">
    <h2 class="font-semibold text-sm tracking-wide text-wp-dim uppercase">
      Peers
      <Tooltip text={TOOLTIPS.peer_hash} />
    </h2>
    <button
      bind:this={addTrigger}
      class="text-wp-dim hover:text-wp-accent text-lg leading-none px-2"
      type="button"
      aria-label="Add a peer by address"
      aria-expanded={showAdd}
      aria-controls="add-peer-form"
      title="Add peer by address"
      onclick={() => (showAdd ? closeAdd() : openAdd())}
    >
      <span aria-hidden="true">＋</span>
    </button>
  </div>

  {#if showAdd}
    <div
      id="add-peer-form"
      class="border-b border-wp-border/50"
      role="dialog"
      aria-label="Add a peer by address"
      tabindex="-1"
      onkeydown={onAddKeydown}
    >
      <form bind:this={addForm} class="px-3 py-3 space-y-2" onsubmit={submitAdd}>
        <div class="flex items-center gap-1 text-xs text-wp-dim font-semibold">
          Add by address
          <Tooltip text={TOOLTIPS.add_peer} />
        </div>
        <input
          bind:this={addField}
          bind:value={addInput}
          aria-label="Peer address, 32-character hexadecimal hash"
          placeholder="32-character hash…"
          autocomplete="off"
          spellcheck="false"
          class="w-full bg-wp-bg border border-wp-border rounded-lg px-3 py-2 font-mono text-xs
                 focus:outline-none focus:border-wp-accent"
        />
        <button
          type="submit"
          disabled={addBusy || addInput.trim().length < 10}
          class="w-full bg-wp-accent text-wp-bg text-xs font-semibold rounded-lg py-2
                 hover:brightness-110 transition disabled:opacity-40"
          >Add peer</button
        >
        {#if addHint}<div class="text-[11px] text-wp-accent">{addHint}</div>{/if}
        {#if addError}<div class="text-[11px] text-wp-danger">{addError}</div>{/if}
        <!-- Always-mounted live region so confirmations/errors are announced
             even though the visible text is rendered conditionally. -->
        <div class="sr-only" role="status" aria-live="polite">{addStatus}</div>
      </form>
    </div>
  {/if}

  {#if $peers.length === 0}
    <div class="p-4 text-sm text-wp-dim leading-relaxed">
      <p class="mb-2">No peers discovered yet.</p>
      <p class="mb-2">
        MeshDeck finds people automatically when they
        <em>announce</em>
        <Tooltip text={TOOLTIPS.announce} />
        themselves. Share your address (top bar) with a friend running MeshDeck,
        MeshChat, or Sideband to get started — or press ＋ to add someone directly.
      </p>
    </div>
  {:else}
    <ul class="overflow-y-auto flex-1">
      {#each $peers as peer (peer.hash)}
        <li class="relative">
          <div
            id={`peer-row-${peer.hash}`}
            class="w-full text-left px-4 py-3 hover:bg-wp-panel2 transition-colors
                   border-b border-wp-border/50 flex items-center gap-3 cursor-pointer
                   {$activePeer === peer.hash ? 'bg-wp-panel2' : ''}"
            role="button"
            tabindex="0"
            aria-label={rowLabel(peer)}
            aria-current={$activePeer === peer.hash ? "true" : undefined}
            onclick={() => {
              activePeer.set(peer.hash);
              clearUnread(peer.hash);
              menuFor = null;
            }}
            onkeydown={(e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                activePeer.set(peer.hash);
                clearUnread(peer.hash);
              }
            }}
          >
            <span
              class="w-2 h-2 rounded-full shrink-0
                     {isRecentlySeen(peer.hash) ? 'bg-wp-accent' : 'bg-wp-border'}"
              aria-hidden="true"
              title={isRecentlySeen(peer.hash) ? 'seen recently' : 'not seen recently'}
            ></span>
            <span class="flex-1 min-w-0">
              {#if renameFor === peer.hash}
                <input
                  bind:this={renameInput}
                  bind:value={renameValue}
                  aria-label={`Nickname for ${peerLabel(peer)}`}
                  onkeydown={(e) => {
                    e.stopPropagation();
                    if (e.key === "Enter") void saveRename(peer.hash);
                    if (e.key === "Escape") cancelRename(peer.hash);
                  }}
                  onclick={(e) => e.stopPropagation()}
                  placeholder="Nickname…"
                  class="w-full bg-wp-bg border border-wp-accent rounded px-2 py-0.5 text-xs
                         focus:outline-none"
                />
              {:else}
                <span class="block truncate font-medium">{peerLabel(peer)}</span>
                <span class="block truncate text-xs text-wp-dim"
                  >{timeAgo(peer.last_seen)}
                  {#if peer.stamp_cost}· stamp {peer.stamp_cost}{/if}</span
                >
              {/if}
            </span>
            {#if ($unread[peer.hash] ?? 0) > 0}
              <span
                class="bg-wp-accent text-wp-bg text-xs font-bold rounded-full px-2 py-0.5"
                aria-hidden="true">{$unread[peer.hash]}</span
              >
            {/if}
            <button
              class="text-wp-dim hover:text-wp-text px-1 shrink-0"
              type="button"
              aria-label={`Options for ${peerLabel(peer)}`}
              aria-haspopup="menu"
              aria-expanded={menuFor === peer.hash}
              aria-controls={`peer-menu-${peer.hash}`}
              title="Peer options"
              onkeydown={(e) => e.stopPropagation()}
              onclick={(e) => toggleMenu(peer.hash, e)}
            >
              <span aria-hidden="true">⋯</span>
            </button>
          </div>
          {#if menuFor === peer.hash}
            <div
              id={`peer-menu-${peer.hash}`}
              bind:this={menuEl}
              class="absolute right-2 top-9 z-20 bg-wp-panel2 border border-wp-border
                     rounded-lg shadow-xl text-xs py-1 min-w-32"
              role="menu"
              aria-label={`Options for ${peerLabel(peer)}`}
              tabindex="-1"
              onkeydown={onMenuKeydown}
            >
              <button
                class="block w-full text-left px-3 py-1.5 hover:bg-wp-bg"
                type="button"
                role="menuitem"
                tabindex="-1"
                onclick={() => openRename(peer)}>Rename…</button
              >
              <button
                class="block w-full text-left px-3 py-1.5 hover:bg-wp-bg text-wp-danger"
                type="button"
                role="menuitem"
                tabindex="-1"
                onclick={() => blockPeer(peer.hash)}>Block</button
              >
            </div>
          {/if}
        </li>
      {/each}
    </ul>
  {/if}
</div>
