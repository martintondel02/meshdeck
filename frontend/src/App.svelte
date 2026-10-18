<script lang="ts">
  import { onMount } from "svelte";
  import { api, captureTokenFromUrl, getToken } from "./lib/api";
  import {
    activePeer,
    connected,
    identity,
    peers,
    settings,
    status,
    unread,
    type IdentityInfo,
    type Peer,
    type Status,
  } from "./lib/stores";
  import { connectWs } from "./lib/ws";
  import Tooltip from "./components/Tooltip.svelte";
  import Onboarding from "./components/Onboarding.svelte";
  import PeerList from "./components/PeerList.svelte";
  import ChatView from "./components/ChatView.svelte";
  import Settings from "./components/Settings.svelte";
  import { TOOLTIPS } from "./lib/copy/tooltips";

  type View = "chats" | "settings";
  let view = $state<View>("chats");
  let needsOnboarding = $state(false);
  let bootError = $state("");
  let booted = $state(false);

  const totalUnread = $derived(
    Object.values($unread).reduce((a: number, b: number) => a + b, 0),
  );

  onMount(async () => {
    captureTokenFromUrl();
    if (!getToken()) {
      bootError =
        "No API token found. Start Waypoint from the terminal and open the full URL it prints (it contains ?token=…).";
      booted = true;
      return;
    }
    try {
      const [id, st, s, peerList] = await Promise.all([
        api<IdentityInfo>("/api/v1/identity"),
        api<Status>("/api/v1/status"),
        api<Record<string, unknown>>("/api/v1/settings"),
        api<Peer[]>("/api/v1/peers"),
      ]);
      identity.set(id);
      status.set(st);
      settings.set(s);
      peers.set(peerList);
      if (!id.display_name) needsOnboarding = true;
      connectWs();
    } catch (e) {
      bootError =
        e instanceof Error && e.message === "unauthorized"
          ? "The daemon rejected the token. Re-open the exact URL Waypoint printed."
          : "Could not reach the Waypoint daemon. Is it running?";
    }
    booted = true;
  });

  // periodic light status refresh
  $effect(() => {
    if (!booted || needsOnboarding || !getToken()) return;
    const t = setInterval(
      () => api<Status>("/api/v1/status").then((s) => status.set(s)).catch(() => {}),
      5000,
    );
    return () => clearInterval(t);
  });
</script>

{#if !booted}
  <div class="min-h-screen flex items-center justify-center text-wp-dim">
    Starting…
  </div>
{:else if bootError}
  <div class="min-h-screen flex items-center justify-center p-6">
    <div class="max-w-md bg-wp-panel border border-wp-border rounded-2xl p-8 text-center">
      <div class="text-3xl mb-3">🔌</div>
      <p class="text-sm leading-relaxed">{bootError}</p>
    </div>
  </div>
{:else if needsOnboarding}
  <Onboarding onDone={() => (needsOnboarding = false)} />
{:else}
  <div class="h-screen flex flex-col">
    <header
      class="flex items-center gap-3 px-4 py-2.5 border-b border-wp-border bg-wp-panel shrink-0"
    >
      <span class="text-lg">🧭</span>
      <span class="font-bold tracking-tight">Waypoint</span>
      <span
        class="w-2 h-2 rounded-full {$connected ? 'bg-wp-accent' : 'bg-wp-danger'}"
        title={$connected ? 'connected to daemon' : 'daemon connection lost — retrying'}
      ></span>

      <div class="flex-1"></div>

      <span class="text-sm text-wp-dim">
        {$identity?.display_name}
      </span>
      <code class="text-xs bg-wp-bg border border-wp-border rounded-md px-2 py-1 font-mono">
        {$identity?.hash.slice(0, 10)}…
      </code>
      <Tooltip text={TOOLTIPS.address} />

      <nav class="flex gap-1 ml-2">
        <button
          class="px-3 py-1.5 rounded-lg text-sm transition-colors
                 {view === 'chats' ? 'bg-wp-panel2 text-wp-text' : 'text-wp-dim hover:text-wp-text'}"
          onclick={() => (view = "chats")}
        >
          Chats
          {#if totalUnread > 0}
            <span class="ml-1 bg-wp-accent text-wp-bg text-xs font-bold rounded-full px-1.5">
              {totalUnread}
            </span>
          {/if}
        </button>
        <button
          class="px-3 py-1.5 rounded-lg text-sm transition-colors
                 {view === 'settings' ? 'bg-wp-panel2 text-wp-text' : 'text-wp-dim hover:text-wp-text'}"
          onclick={() => (view = "settings")}>Settings</button
        >
      </nav>
    </header>

    <main class="flex-1 min-h-0 flex">
      {#if view === "chats"}
        <aside class="w-72 border-r border-wp-border shrink-0 bg-wp-panel/50">
          <PeerList />
        </aside>
        <section class="flex-1 min-w-0 bg-wp-bg">
          <ChatView />
        </section>
      {:else}
        <section class="flex-1 min-w-0 bg-wp-bg">
          <Settings />
        </section>
      {/if}
    </main>
  </div>
{/if}
