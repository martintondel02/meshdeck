<script lang="ts">
  import { api } from "../lib/api";
  import { clockTime } from "../lib/format";
  import {
    activePeer,
    messages,
    peers,
    peerLabel,
    upsertMessage,
    type ChatMessage,
  } from "../lib/stores";
  import { wsCmd } from "../lib/ws";
  import Tooltip from "./Tooltip.svelte";
  import { TOOLTIPS } from "../lib/copy/tooltips";

  let draft = $state("");
  let sending = $state(false);
  let sendError = $state("");
  let scrollBox: HTMLDivElement | undefined = $state();

  const peer = $derived($peers.find((p) => p.hash === $activePeer) ?? null);
  const msgs = $derived($activePeer ? ($messages[$activePeer] ?? []) : []);

  $effect(() => {
    if ($activePeer) void loadHistory($activePeer);
  });

  $effect(() => {
    msgs.length; // scroll on new content
    scrollBox?.scrollTo({ top: scrollBox.scrollHeight, behavior: "smooth" });
  });

  async function loadHistory(peerHash: string) {
    const list = await api<ChatMessage[]>(
      `/api/v1/messages?peer=${peerHash}&limit=100`,
    );
    // REST returns newest-first; store keeps chronological
    for (const m of [...list].reverse()) upsertMessage(peerHash, m);
  }

  function stateIcon(msg: ChatMessage): string {
    switch (msg.state) {
      case "sending":
        return "…";
      case "sent":
        return "✓";
      case "delivered":
        return "✓✓";
      case "failed":
        return "✗";
      default:
        return "";
    }
  }

  function stateTooltip(msg: ChatMessage): string {
    switch (msg.state) {
      case "sent":
        return TOOLTIPS.delivery_sent;
      case "delivered":
        return TOOLTIPS.delivery_delivered;
      case "failed":
        return TOOLTIPS.delivery_failed;
      default:
        return "";
    }
  }

  async function send() {
    if (!draft.trim() || !$activePeer || sending) return;
    sending = true;
    sendError = "";
    const content = draft.trim();
    try {
      const res = await wsCmd<{ hash?: string; __error?: { message: string } }>(
        "send_message",
        { peer: $activePeer, content },
      );
      if (res.__error) {
        sendError =
          res.__error.message ??
          "Message failed before it could be sent (peer not reachable yet?)";
      } else if (res.hash) {
        upsertMessage($activePeer, {
          id: -Date.now(),
          hash: res.hash,
          peer_hash: $activePeer,
          direction: "out",
          state: "sending",
          title: null,
          content,
          created_ts: Date.now() / 1000,
          delivered_ts: null,
        });
        draft = "";
      }
    } catch {
      sendError = "Not connected to the Waypoint daemon.";
    } finally {
      sending = false;
    }
  }
</script>

{#if !peer}
  <div class="h-full flex items-center justify-center text-wp-dim text-sm p-8 text-center">
    <div>
      <div class="text-4xl mb-3">🛰️</div>
      Select a peer to start chatting,<br />or share your address and wait for someone to say hi.
    </div>
  </div>
{:else}
  <div class="h-full flex flex-col">
    <div class="px-5 py-3 border-b border-wp-border flex items-baseline gap-2">
      <span class="font-semibold">{peerLabel(peer)}</span>
      <span class="text-xs text-wp-dim font-mono">{peer.hash}</span>
      <Tooltip text={TOOLTIPS.peer_hash} />
    </div>

    <div bind:this={scrollBox} class="flex-1 overflow-y-auto px-5 py-4 space-y-3">
      {#each msgs as msg (msg.hash)}
        <div class="flex {msg.direction === 'out' ? 'justify-end' : 'justify-start'}">
          <div
            class="max-w-[75%] rounded-2xl px-4 py-2.5 text-sm leading-relaxed shadow
                   {msg.direction === 'out'
              ? 'bg-wp-accent2/20 border border-wp-accent2/30'
              : 'bg-wp-panel2 border border-wp-border'}"
          >
            <p class="whitespace-pre-wrap break-words">{msg.content}</p>
            <div class="flex items-center gap-1.5 justify-end mt-1 text-[11px] text-wp-dim">
              <span>{clockTime(msg.created_ts)}</span>
              {#if msg.direction === "out"}
                <span class={msg.state === "failed" ? "text-wp-danger" : msg.state === "delivered" ? "text-wp-accent" : ""}>
                  {stateIcon(msg)}
                </span>
                {#if stateTooltip(msg)}<Tooltip text={stateTooltip(msg)} />{/if}
              {/if}
            </div>
          </div>
        </div>
      {/each}
    </div>

    {#if sendError}
      <div class="px-5 pb-1 text-xs text-wp-danger">{sendError}</div>
    {/if}

    <div class="p-4 border-t border-wp-border flex gap-2">
      <input
        bind:value={draft}
        onkeydown={(e) => e.key === "Enter" && send()}
        placeholder="Type a message…"
        class="flex-1 bg-wp-bg border border-wp-border rounded-xl px-4 py-2.5
               focus:outline-none focus:border-wp-accent transition-colors"
      />
      <button
        onclick={send}
        disabled={sending || !draft.trim()}
        class="bg-wp-accent text-wp-bg font-semibold rounded-xl px-5
               hover:brightness-110 transition disabled:opacity-40"
        >Send</button
      >
    </div>
  </div>
{/if}
