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

  function isRecentlySeen(hash: string): boolean {
    const peer = $peers.find((p) => p.hash === hash);
    return !!peer?.last_seen && Date.now() / 1000 - peer.last_seen < 600;
  }

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
  }

  async function blockPeer(hash: string) {
    await api(`/api/v1/peers/${hash}`, {
      method: "PATCH",
      body: JSON.stringify({ blocked: true }),
    });
    if ($activePeer === hash) activePeer.set(null);
    peers.set(await api<Peer[]>("/api/v1/peers"));
    menuFor = null;
  }
</script>

<div class="h-full flex flex-col">
  <div class="px-4 py-3 border-b border-wp-border flex items-center justify-between">
    <h2 class="font-semibold text-sm tracking-wide text-wp-dim uppercase">
      Peers
      <Tooltip text={TOOLTIPS.peer_hash} />
    </h2>
    <button
      class="text-wp-dim hover:text-wp-accent text-lg leading-none px-2"
      title="Add peer by address"
      onclick={() => {
        showAdd = !showAdd;
        addHint = "";
        addError = "";
      }}>＋</button
    >
  </div>

  {#if showAdd}
    <form class="px-3 py-3 border-b border-wp-border/50 space-y-2" onsubmit={submitAdd}>
      <div class="flex items-center gap-1 text-xs text-wp-dim font-semibold">
        Add by address <Tooltip text={TOOLTIPS.add_peer} />
      </div>
      <input
        bind:value={addInput}
        placeholder="32-character hash…"
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
    </form>
  {/if}

  {#if $peers.length === 0}
    <div class="p-4 text-sm text-wp-dim leading-relaxed">
      <p class="mb-2">No peers discovered yet.</p>
      <p class="mb-2">
        Waypoint finds people automatically when they
        <em>announce</em>
        <Tooltip text={TOOLTIPS.announce} />
        themselves. Share your address (top bar) with a friend running Waypoint,
        MeshChat, or Sideband to get started — or press ＋ to add someone directly.
      </p>
    </div>
  {:else}
    <ul class="overflow-y-auto flex-1">
      {#each $peers as peer (peer.hash)}
        <li class="relative">
          <div
            class="w-full text-left px-4 py-3 hover:bg-wp-panel2 transition-colors
                   border-b border-wp-border/50 flex items-center gap-3 cursor-pointer
                   {$activePeer === peer.hash ? 'bg-wp-panel2' : ''}"
            role="button"
            tabindex="0"
            onclick={() => {
              activePeer.set(peer.hash);
              clearUnread(peer.hash);
              menuFor = null;
            }}
            onkeydown={(e) => {
              if (e.key === "Enter") {
                activePeer.set(peer.hash);
                clearUnread(peer.hash);
              }
            }}
          >
            <span
              class="w-2 h-2 rounded-full shrink-0
                     {isRecentlySeen(peer.hash) ? 'bg-wp-accent' : 'bg-wp-border'}"
              title={isRecentlySeen(peer.hash) ? 'seen recently' : 'not seen recently'}
            ></span>
            <span class="flex-1 min-w-0">
              {#if renameFor === peer.hash}
                <input
                  bind:value={renameValue}
                  onkeydown={(e) => {
                    e.stopPropagation();
                    if (e.key === "Enter") void saveRename(peer.hash);
                    if (e.key === "Escape") renameFor = null;
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
                >{$unread[peer.hash]}</span
              >
            {/if}
            <button
              class="text-wp-dim hover:text-wp-text px-1 shrink-0"
              title="Peer options"
              onclick={(e) => {
                e.stopPropagation();
                menuFor = menuFor === peer.hash ? null : peer.hash;
              }}>⋯</button
            >
          </div>
          {#if menuFor === peer.hash}
            <div
              class="absolute right-2 top-9 z-20 bg-wp-panel2 border border-wp-border
                     rounded-lg shadow-xl text-xs py-1 min-w-32"
            >
              <button
                class="block w-full text-left px-3 py-1.5 hover:bg-wp-bg"
                onclick={() => {
                  renameFor = peer.hash;
                  renameValue = peer.nickname ?? "";
                  menuFor = null;
                }}>Rename…</button
              >
              <button
                class="block w-full text-left px-3 py-1.5 hover:bg-wp-bg text-wp-danger"
                onclick={() => blockPeer(peer.hash)}>Block</button
              >
            </div>
          {/if}
        </li>
      {/each}
    </ul>
  {/if}
</div>
