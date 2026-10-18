<script lang="ts">
  import { api, getToken, uploadFile } from "../lib/api";
  import { clockTime } from "../lib/format";
  import {
    activePeer,
    attachmentUrl,
    attachmentsOf,
    humanSize,
    messages,
    peers,
    peerLabel,
    upsertMessage,
    type ChatMessage,
  } from "../lib/stores";
  import { wsCmd } from "../lib/ws";
  import Tooltip from "./Tooltip.svelte";
  import { TOOLTIPS } from "../lib/copy/tooltips";

  const MAX_ATTACHMENT_BYTES = 1536 * 1024; // must match the backend cap

  let draft = $state("");
  let sending = $state(false);
  let sendError = $state("");
  let scrollBox: HTMLDivElement | undefined = $state();
  let fileInput: HTMLInputElement | undefined = $state();
  let fileSending = $state(false);
  let search = $state("");

  const peer = $derived($peers.find((p) => p.hash === $activePeer) ?? null);
  const allMsgs = $derived($activePeer ? ($messages[$activePeer] ?? []) : []);
  const query = $derived(search.trim().toLowerCase());
  const msgs = $derived(
    query
      ? allMsgs.filter(
          (m) =>
            (m.content ?? "").toLowerCase().includes(query) ||
            (m.title ?? "").toLowerCase().includes(query),
        )
      : allMsgs,
  );

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

  function sendErrorText(code: string): string {
    if (code === "no_path") return TOOLTIPS.no_path_error;
    if (code === "too_large") return "This file is too large for the current transfer limit.";
    if (code === "no_propagation_node")
      return "Propagation delivery selected, but no propagation node is configured (Advanced→Settings).";
    return "Message failed before it could be sent.";
  }

  function optimisticMessage(
    peerHash: string,
    res: { hash: string },
    content: string,
    attachments?: ChatMessage["fields_json"],
  ): ChatMessage {
    return {
      id: -Date.now(),
      hash: res.hash,
      peer_hash: peerHash,
      direction: "out",
      state: "sending",
      title: null,
      content,
      fields_json: attachments ?? null,
      created_ts: Date.now() / 1000,
      delivered_ts: null,
    };
  }

  async function send() {
    if (!draft.trim() || !$activePeer || sending) return;
    sending = true;
    sendError = "";
    const content = draft.trim();
    const targetPeer = $activePeer;
    try {
      const res = await wsCmd<{ hash?: string; __error?: { message: string } }>(
        "send_message",
        { peer: targetPeer, content },
      );
      if (res.__error) {
        sendError = sendErrorText(res.__error.message);
      } else if (res.hash) {
        upsertMessage(
          targetPeer,
          optimisticMessage(targetPeer, { hash: res.hash }, content),
        );
        draft = "";
      }
    } catch {
      sendError = "Not connected to the MeshDeck daemon.";
    } finally {
      sending = false;
    }
  }

  async function sendSelectedFile(e: Event) {
    const input = e.currentTarget as HTMLInputElement;
    const file = input.files?.[0];
    input.value = ""; // allow re-selecting the same file
    if (!file || !$activePeer || fileSending) return;
    if (file.size > MAX_ATTACHMENT_BYTES) {
      sendError = `“${file.name}” is ${humanSize(file.size)} — the current limit is ${humanSize(MAX_ATTACHMENT_BYTES)}.`;
      return;
    }
    fileSending = true;
    sendError = "";
    const targetPeer = $activePeer;
    const caption = draft.trim();
    try {
      const form = new FormData();
      form.append("peer", targetPeer);
      form.append("file", file);
      if (caption) form.append("caption", caption);
      const res = await uploadFile<{ hash: string }>("/api/v1/files", form);
      upsertMessage(
        targetPeer,
        optimisticMessage(
          targetPeer,
          res,
          caption,
          JSON.stringify({
            attachments: [{ index: 0, name: file.name, size: file.size }],
          }),
        ),
      );
      draft = "";
    } catch (err) {
      sendError = sendErrorText(err instanceof Error ? err.message : "");
    } finally {
      fileSending = false;
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
      {#if peer.stamp_cost}
        <span
          class="ml-2 text-[10px] uppercase tracking-wide bg-wp-warn/15 text-wp-warn
                 border border-wp-warn/40 rounded-full px-2 py-0.5"
          >stamp {peer.stamp_cost}</span
        >
        <Tooltip text={TOOLTIPS.stamp_sending} />
      {/if}
      <div class="flex-1"></div>
      <input
        bind:value={search}
        placeholder="Search history…"
        class="w-44 bg-wp-bg border border-wp-border rounded-lg px-3 py-1 text-xs
               focus:outline-none focus:border-wp-accent"
      />
      {#if query}
        <span class="text-[11px] text-wp-dim">{msgs.length} match{msgs.length === 1 ? "" : "es"}</span>
      {/if}
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
            {#if msg.content}
              <p class="whitespace-pre-wrap break-words">{msg.content}</p>
            {/if}
            {#each attachmentsOf(msg) as att (att.index)}
              <a
                href="{attachmentUrl(peer.hash, msg, att.index)}?token={getToken()}"
                class="flex items-center gap-2 mt-1.5 px-3 py-2 rounded-lg bg-wp-bg/60
                       border border-wp-border hover:border-wp-accent transition-colors group"
                title="Download {att.name}"
              >
                <span class="text-base">📎</span>
                <span class="truncate font-mono text-xs">{att.name}</span>
                <span class="text-[11px] text-wp-dim shrink-0">{humanSize(att.size)}</span>
                <span class="text-wp-accent opacity-0 group-hover:opacity-100 transition shrink-0">⬇</span>
              </a>
            {/each}
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
      <div class="px-5 pb-1 text-xs text-wp-danger flex items-center gap-1">
        {sendError}
        {#if sendError === TOOLTIPS.no_path_error}<Tooltip text={TOOLTIPS.announce} />{/if}
      </div>
    {/if}

    <div class="p-4 border-t border-wp-border flex gap-2 items-center">
      <input
        bind:this={fileInput}
        type="file"
        class="hidden"
        onchange={sendSelectedFile}
      />
      <button
        onclick={() => fileInput?.click()}
        disabled={fileSending}
        class="bg-wp-panel2 border border-wp-border rounded-xl px-3.5 py-2.5
               hover:border-wp-accent transition disabled:opacity-40"
        title="Send a file (up to {humanSize(MAX_ATTACHMENT_BYTES)})"
      >
        {fileSending ? "⏳" : "📎"}
      </button>
      <input
        bind:value={draft}
        onkeydown={(e) => e.key === "Enter" && send()}
        placeholder="Type a message… (or attach a file)"
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
