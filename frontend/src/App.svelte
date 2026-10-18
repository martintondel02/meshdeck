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
  import Pages from "./components/Pages.svelte";
  import Guides from "./components/Guides.svelte";
  import Settings from "./components/Settings.svelte";
  import { TOOLTIPS } from "./lib/copy/tooltips";
  import { t } from "./lib/i18n";

  type View = "chats" | "pages" | "guides" | "settings";
  const TABS: { id: View; labelKey: string }[] = [
    { id: "chats", labelKey: "common.nav_chats" },
    { id: "pages", labelKey: "common.nav_pages" },
    { id: "guides", labelKey: "common.nav_guides" },
    { id: "settings", labelKey: "common.nav_settings" },
  ];
  let view = $state<View>("chats");
  let needsOnboarding = $state(false);
  let bootError = $state("");
  let booted = $state(false);

  const totalUnread = $derived(
    Object.values($unread).reduce((a: number, b: number) => a + b, 0),
  );

  const connectionText = $derived(
    $connected
      ? t("common.connected_daemon")
      : t("common.daemon_lost"),
  );

  // WAI-ARIA tabs: roving tabindex, arrow keys move between tabs.
  function onTabKeydown(e: KeyboardEvent) {
    const i = TABS.findIndex((item) => item.id === view);
    let next = i;
    if (e.key === "ArrowRight") next = (i + 1) % TABS.length;
    else if (e.key === "ArrowLeft") next = (i - 1 + TABS.length) % TABS.length;
    else if (e.key === "Home") next = 0;
    else if (e.key === "End") next = TABS.length - 1;
    else return;
    e.preventDefault();
    const tab = TABS[next];
    if (!tab) return;
    view = tab.id;
    document.getElementById(`tab-${tab.id}`)?.focus();
  }

  onMount(async () => {
    captureTokenFromUrl();
    if (!getToken()) {
      bootError = t("common.boot_no_token");
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
          ? t("common.boot_bad_token")
          : t("common.boot_unreachable");
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
  <div class="min-h-screen flex items-center justify-center text-wp-dim" role="status">
    {t("common.starting")}
  </div>
{:else if bootError}
  <div class="min-h-screen flex items-center justify-center p-6">
    <div class="max-w-md bg-wp-panel border border-wp-border rounded-2xl p-8 text-center">
      <div class="text-3xl mb-3" aria-hidden="true">🔌</div>
      <p class="text-sm leading-relaxed" role="alert">{bootError}</p>
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
      <span class="font-bold tracking-tight">MeshDeck</span>
      <span
        class="w-2 h-2 rounded-full {$connected ? 'bg-wp-accent' : 'bg-wp-danger'}"
        aria-hidden="true"
        title={$connected
          ? t("common.daemon_connected_title")
          : t("common.daemon_lost_title")}
      ></span>
      <span class="sr-only" role="status" aria-live="polite">{connectionText}</span>

      <div class="flex-1"></div>

      <span class="text-sm text-wp-dim">
        {$identity?.display_name}
      </span>
      <code class="text-xs bg-wp-bg border border-wp-border rounded-md px-2 py-1 font-mono">
        {$identity?.hash.slice(0, 10)}…
      </code>
      <Tooltip text={TOOLTIPS.address} />

      <nav class="ml-2" aria-label={t("common.main_sections")}>
        <div class="flex gap-1" role="tablist">
          {#each TABS as tab (tab.id)}
            <button
              id={`tab-${tab.id}`}
              type="button"
              role="tab"
              aria-selected={view === tab.id}
              aria-controls={`panel-${tab.id}`}
              tabindex={view === tab.id ? 0 : -1}
              class="px-3 py-1.5 rounded-lg text-sm transition-colors
                     {view === tab.id
                ? 'bg-wp-panel2 text-wp-text'
                : 'text-wp-dim hover:text-wp-text'}"
              onclick={() => (view = tab.id)}
              onkeydown={onTabKeydown}
            >
              {t(tab.labelKey)}
              {#if tab.id === "chats" && totalUnread > 0}
                <span
                  class="ml-1 bg-wp-accent text-wp-bg text-xs font-bold rounded-full px-1.5"
                  aria-hidden="true">{totalUnread}</span
                >
                <span class="sr-only"
                  >{t(
                    totalUnread === 1
                      ? "common.unread_messages_one"
                      : "common.unread_messages_other",
                    { count: totalUnread },
                  )}</span
                >
              {/if}
            </button>
          {/each}
        </div>
      </nav>
    </header>

    <main class="flex-1 min-h-0 flex">
      {#if view === "chats"}
        <div
          id="panel-chats"
          role="tabpanel"
          aria-labelledby="tab-chats"
          class="flex-1 min-h-0 flex"
        >
          <aside class="w-72 border-r border-wp-border shrink-0 bg-wp-panel/50">
            <PeerList />
          </aside>
          <section class="flex-1 min-w-0 bg-wp-bg">
            <ChatView />
          </section>
        </div>
      {:else if view === "pages"}
        <div
          id="panel-pages"
          role="tabpanel"
          aria-labelledby="tab-pages"
          class="flex-1 min-w-0 bg-wp-bg overflow-y-auto"
        >
          <Pages />
        </div>
      {:else if view === "guides"}
        <div
          id="panel-guides"
          role="tabpanel"
          aria-labelledby="tab-guides"
          class="flex-1 min-w-0 bg-wp-bg"
        >
          <Guides />
        </div>
      {:else}
        <div
          id="panel-settings"
          role="tabpanel"
          aria-labelledby="tab-settings"
          class="flex-1 min-w-0 bg-wp-bg"
        >
          <Settings />
        </div>
      {/if}
    </main>
  </div>
{/if}
