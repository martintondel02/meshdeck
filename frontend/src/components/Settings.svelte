<script lang="ts">
  import { api } from "../lib/api";
  import { identity, mode, settings, status } from "../lib/stores";
  import { wsCmd } from "../lib/ws";
  import Tooltip from "./Tooltip.svelte";
  import { GLOSSARY, TOOLTIPS } from "../lib/copy/tooltips";

  let announceBusy = $state(false);
  let copied = $state(false);
  let restartNote = $state(false);

  async function copyAddress() {
    const hash = $identity?.hash;
    if (!hash) return;
    await navigator.clipboard.writeText(hash);
    copied = true;
    setTimeout(() => (copied = false), 1500);
  }

  async function toggleMode() {
    const next = $mode === "basic" ? "advanced" : "basic";
    const updated = await api<Record<string, unknown>>("/api/v1/settings", {
      method: "PUT",
      body: JSON.stringify({ mode: next }),
    });
    settings.set(updated);
  }

  async function announceNow() {
    announceBusy = true;
    try {
      await wsCmd("announce");
    } catch {
      /* offline is fine */
    } finally {
      setTimeout(() => (announceBusy = false), 800);
    }
  }
</script>

<div class="h-full overflow-y-auto p-6 max-w-2xl">
  <h1 class="text-xl font-bold mb-6">Settings</h1>

  <section class="bg-wp-panel border border-wp-border rounded-xl p-5 mb-4">
    <h2 class="font-semibold mb-1">Your address</h2>
    <p class="text-sm text-wp-dim mb-3">
      Share this with people you want to talk to.
      <Tooltip text={TOOLTIPS.address} />
    </p>
    <div class="flex items-center gap-2">
      <code class="flex-1 bg-wp-bg border border-wp-border rounded-lg px-3 py-2 text-sm font-mono truncate">
        {$identity?.hash ?? "…"}
      </code>
      <button
        onclick={copyAddress}
        class="bg-wp-panel2 border border-wp-border rounded-lg px-3 py-2 text-sm hover:border-wp-accent transition-colors"
        >{copied ? "Copied!" : "Copy"}</button
      >
    </div>
    <p class="text-xs text-wp-dim mt-2">
      Signed in as <b>{$identity?.display_name || "(unnamed)"}</b> ·
      <Tooltip text={TOOLTIPS.display_name} />
    </p>
  </section>

  <section class="bg-wp-panel border border-wp-border rounded-xl p-5 mb-4">
    <h2 class="font-semibold mb-1">
      Mode
      <Tooltip text={TOOLTIPS.mode_toggle} />
    </h2>
    <p class="text-sm text-wp-dim mb-3">
      {$mode === "basic"
        ? "Basic mode is on: a clean, guided experience."
        : "Advanced mode is on: network controls and diagnostics unlocked."}
    </p>
    <button
      onclick={toggleMode}
      class="rounded-lg px-4 py-2 text-sm font-medium border transition-colors
             {$mode === 'advanced'
        ? 'bg-wp-warn/15 border-wp-warn text-wp-warn'
        : 'bg-wp-accent/15 border-wp-accent text-wp-accent'}"
    >
      Switch to {$mode === "basic" ? "Advanced" : "Basic"} mode
    </button>
  </section>

  <section class="bg-wp-panel border border-wp-border rounded-xl p-5 mb-4">
    <h2 class="font-semibold mb-1">Network</h2>
    <p class="text-sm text-wp-dim mb-3">
      {$status?.rns_running
        ? `Connected via ${$status.interfaces.length} interface(s).`
        : "Reticulum is not running."}
    </p>
    <button
      onclick={announceNow}
      disabled={announceBusy}
      class="bg-wp-panel2 border border-wp-border rounded-lg px-4 py-2 text-sm hover:border-wp-accent transition-colors disabled:opacity-40"
    >
      {announceBusy ? "Announcing…" : "Announce myself now"}
    </button>
    <Tooltip text={TOOLTIPS.announce} />

    {#if $mode === "advanced" && $status}
      <div class="mt-4 border-t border-wp-border pt-4">
        <h3 class="text-sm font-semibold mb-2 text-wp-dim uppercase tracking-wide">Interfaces</h3>
        <table class="w-full text-sm">
          <thead>
            <tr class="text-left text-wp-dim text-xs">
              <th class="pb-1">Name</th>
              <th class="pb-1">Type</th>
              <th class="pb-1">State</th>
              <th class="pb-1 text-right">Bitrate</th>
            </tr>
          </thead>
          <tbody>
            {#each $status.interfaces as iface (iface.name)}
              <tr class="border-t border-wp-border/50">
                <td class="py-1.5 pr-2 font-mono text-xs">{iface.name}</td>
                <td class="py-1.5 pr-2">{iface.type}</td>
                <td class="py-1.5 pr-2">
                  <span class={iface.online ? "text-wp-accent" : "text-wp-danger"}
                    >{iface.online ? "online" : "offline"}</span
                  >
                </td>
                <td class="py-1.5 text-right text-wp-dim">
                  {iface.bitrate ? `${Math.round(iface.bitrate / 1000)} kbps` : "—"}
                </td>
              </tr>
            {/each}
          </tbody>
        </table>
      </div>
    {/if}
  </section>

  {#if $mode === "advanced"}
    <section class="bg-wp-panel border border-wp-border rounded-xl p-5 mb-4">
      <h2 class="font-semibold mb-1">Glossary</h2>
      <dl class="text-sm space-y-2 mt-2">
        {#each Object.entries(GLOSSARY) as [term, def] (term)}
          <div>
            <dt class="font-medium capitalize">{term.replace("_", " ")}</dt>
            <dd class="text-wp-dim">{def}</dd>
          </div>
        {/each}
      </dl>
    </section>
  {/if}

  {#if restartNote}
    <p class="text-sm text-wp-warn">Restart required for connection changes.</p>
  {/if}

  <p class="text-xs text-wp-dim mt-6">
    Waypoint v{$status?.version ?? "…"} · uptime {$status ? Math.round($status.uptime_seconds) : 0}s
  </p>
</div>
