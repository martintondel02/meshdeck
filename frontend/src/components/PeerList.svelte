<script lang="ts">
  import { activePeer, clearUnread, peers, peerLabel, unread } from "../lib/stores";
  import { timeAgo } from "../lib/format";
  import Tooltip from "./Tooltip.svelte";
  import { TOOLTIPS } from "../lib/copy/tooltips";

  function isRecentlySeen(hash: string): boolean {
    const peer = $peers.find((p) => p.hash === hash);
    return !!peer?.last_seen && Date.now() / 1000 - peer.last_seen < 600;
  }
</script>

<div class="h-full flex flex-col">
  <div class="px-4 py-3 border-b border-wp-border">
    <h2 class="font-semibold text-sm tracking-wide text-wp-dim uppercase">
      Peers
      <Tooltip text={TOOLTIPS.peer_hash} />
    </h2>
  </div>

  {#if $peers.length === 0}
    <div class="p-4 text-sm text-wp-dim leading-relaxed">
      <p class="mb-2">No peers discovered yet.</p>
      <p>
        Waypoint finds people automatically when they
        <em>announce</em>
        <Tooltip text={TOOLTIPS.announce} />
        themselves. Share your address (top bar) with a friend running Waypoint,
        MeshChat, or Sideband to get started — or test locally with a second
        instance on your network.
      </p>
    </div>
  {:else}
    <ul class="overflow-y-auto flex-1">
      {#each $peers as peer (peer.hash)}
        <li>
          <button
            class="w-full text-left px-4 py-3 hover:bg-wp-panel2 transition-colors
                   border-b border-wp-border/50 flex items-center gap-3
                   {$activePeer === peer.hash ? 'bg-wp-panel2' : ''}"
            onclick={() => {
              activePeer.set(peer.hash);
              clearUnread(peer.hash);
            }}
          >
            <span
              class="w-2 h-2 rounded-full shrink-0
                     {isRecentlySeen(peer.hash) ? 'bg-wp-accent' : 'bg-wp-border'}"
              title={isRecentlySeen(peer.hash) ? 'seen recently' : 'not seen recently'}
            ></span>
            <span class="flex-1 min-w-0">
              <span class="block truncate font-medium">{peerLabel(peer)}</span>
              <span class="block truncate text-xs text-wp-dim"
                >{timeAgo(peer.last_seen)}
                {#if peer.stamp_cost}· stamp {peer.stamp_cost}{/if}</span
              >
            </span>
            {#if ($unread[peer.hash] ?? 0) > 0}
              <span
                class="bg-wp-accent text-wp-bg text-xs font-bold rounded-full px-2 py-0.5"
                >{$unread[peer.hash]}</span
              >
            {/if}
          </button>
        </li>
      {/each}
    </ul>
  {/if}
</div>
