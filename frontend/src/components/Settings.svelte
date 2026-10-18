<script lang="ts">
  import { api } from "../lib/api";
  import { identity, mode, settings, status } from "../lib/stores";
  import { wsCmd } from "../lib/ws";
  import Tooltip from "./Tooltip.svelte";
  import InterfacesCard from "./InterfacesCard.svelte";
  import { GLOSSARY, TOOLTIPS } from "../lib/copy/tooltips";
  import { t } from "../lib/i18n";

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

  let deliveryBusy = $state(false);
  let deliveryNote = $state("");
  let propNode = $state("");
  let hostBusy = $state(false);
  let hostNote = $state("");
  let propAddrCopied = $state(false);

  // seed local form state when settings load
  $effect(() => {
    if ($settings && typeof $settings.propagation_node_hash === "string" && propNode === "") {
      propNode = $settings.propagation_node_hash;
    }
  });

  async function setDeliveryMethod(e: Event) {
    const value = (e.currentTarget as HTMLSelectElement).value;
    deliveryBusy = true;
    deliveryNote = "";
    try {
      const updated = await api<Record<string, unknown>>("/api/v1/settings", {
        method: "PUT",
        body: JSON.stringify({ delivery_method: value }),
      });
      settings.set(updated);
      deliveryNote = t("settings.delivery_updated");
    } catch {
      deliveryNote = t("settings.delivery_error");
    } finally {
      deliveryBusy = false;
    }
  }

  async function togglePropagationHosting(e: Event) {
    const value = (e.currentTarget as HTMLInputElement).checked;
    hostBusy = true;
    hostNote = "";
    try {
      const updated = await api<Record<string, unknown>>("/api/v1/settings", {
        method: "PUT",
        body: JSON.stringify({ host_propagation_node: value }),
      });
      settings.set(updated);
      hostNote = value
        ? t("settings.hosting_enabled")
        : t("settings.hosting_disabled");
    } catch {
      hostNote = t("settings.hosting_error");
    } finally {
      hostBusy = false;
    }
  }

  async function copyPropagationAddress() {
    const hash = $status?.propagation_node_hash;
    if (!hash) return;
    await navigator.clipboard.writeText(hash);
    propAddrCopied = true;
    setTimeout(() => (propAddrCopied = false), 1500);
  }

  async function savePropagationNode() {
    deliveryBusy = true;
    deliveryNote = "";
    try {
      const updated = await api<Record<string, unknown>>("/api/v1/settings", {
        method: "PUT",
        body: JSON.stringify({ propagation_node_hash: propNode.trim().toLowerCase() }),
      });
      settings.set(updated);
      deliveryNote = t("settings.prop_node_saved");
    } catch {
      deliveryNote = t("settings.prop_node_invalid");
    } finally {
      deliveryBusy = false;
    }
  }
</script>

<div class="h-full overflow-y-auto p-6 max-w-2xl">
  <h1 class="text-xl font-bold mb-6">{t("settings.title")}</h1>

  <section class="bg-wp-panel border border-wp-border rounded-xl p-5 mb-4">
    <h2 class="font-semibold mb-1">{t("settings.your_address")}</h2>
    <p class="text-sm text-wp-dim mb-3">
      {t("settings.share_hint")}
      <Tooltip text={TOOLTIPS.address} />
    </p>
    <div class="flex items-center gap-2">
      <code class="flex-1 bg-wp-bg border border-wp-border rounded-lg px-3 py-2 text-sm font-mono truncate">
        {$identity?.hash ?? "…"}
      </code>
      <button
        onclick={copyAddress}
        aria-label={t("settings.copy_aria")}
        class="bg-wp-panel2 border border-wp-border rounded-lg px-3 py-2 text-sm hover:border-wp-accent transition-colors"
        >{copied ? t("common.copied") : t("common.copy")}</button
      >
    </div>
    <p class="text-xs text-wp-dim mt-2">
      {t("settings.signed_in_as")} <b>{$identity?.display_name || t("settings.unnamed")}</b> ·
      <Tooltip text={TOOLTIPS.display_name} />
    </p>
  </section>

  <section class="bg-wp-panel border border-wp-border rounded-xl p-5 mb-4">
    <h2 class="font-semibold mb-1">
      {t("settings.mode")}
      <Tooltip text={TOOLTIPS.mode_toggle} />
    </h2>
    <p class="text-sm text-wp-dim mb-3">
      {$mode === "basic"
        ? t("settings.mode_basic_hint")
        : t("settings.mode_advanced_hint")}
    </p>
    <button
      onclick={toggleMode}
      class="rounded-lg px-4 py-2 text-sm font-medium border transition-colors
             {$mode === 'advanced'
        ? 'bg-wp-warn/15 border-wp-warn text-wp-warn'
        : 'bg-wp-accent/15 border-wp-accent text-wp-accent'}"
    >
      {t("settings.switch_mode", {
        mode:
          $mode === "basic"
            ? t("settings.mode_advanced_name")
            : t("settings.mode_basic_name"),
      })}
    </button>
  </section>

  <section class="bg-wp-panel border border-wp-border rounded-xl p-5 mb-4">
    <h2 class="font-semibold mb-1">{t("settings.network")}</h2>
    <p class="text-sm text-wp-dim mb-3">
      {$status?.rns_running
        ? t(
            $status.interfaces.length === 1
              ? "settings.connected_via_one"
              : "settings.connected_via_other",
            { count: $status.interfaces.length },
          )
        : t("settings.rns_not_running")}
    </p>
    <button
      onclick={announceNow}
      disabled={announceBusy}
      class="bg-wp-panel2 border border-wp-border rounded-lg px-4 py-2 text-sm hover:border-wp-accent transition-colors disabled:opacity-40"
    >
      {announceBusy ? t("settings.announcing") : t("settings.announce_now")}
    </button>
    <Tooltip text={TOOLTIPS.announce} />

    {#if $mode === "basic"}
      <p class="text-xs text-wp-dim mt-3">
        {t("settings.reach_beyond")}
        <a class="text-wp-accent hover:underline" href="https://directory.rns.recipes/" target="_blank" rel="noreferrer">directory.rns.recipes</a>,
        <a class="text-wp-accent hover:underline" href="https://rmap.world/" target="_blank" rel="noreferrer">rmap.world</a>.
      </p>
    {/if}

    {#if $mode === "advanced" && $status}
      <div class="mt-4 border-t border-wp-border pt-4">
        <h3 class="text-sm font-semibold mb-2 text-wp-dim uppercase tracking-wide">{t("settings.interfaces")}</h3>
        <table class="w-full text-sm">
          <thead>
            <tr class="text-left text-wp-dim text-xs">
              <th class="pb-1">{t("settings.col_name")}</th>
              <th class="pb-1">{t("settings.col_type")}</th>
              <th class="pb-1">{t("settings.col_state")}</th>
              <th class="pb-1 text-right">{t("settings.col_bitrate")}</th>
            </tr>
          </thead>
          <tbody>
            {#each $status.interfaces as iface (iface.name)}
              <tr class="border-t border-wp-border/50">
                <td class="py-1.5 pr-2 font-mono text-xs">{iface.name}</td>
                <td class="py-1.5 pr-2">{iface.type}</td>
                <td class="py-1.5 pr-2">
                  <span class={iface.online ? "text-wp-accent" : "text-wp-danger"}
                    >{iface.online
                      ? t("settings.iface_online")
                      : t("settings.iface_offline")}</span
                  >
                </td>
                <td class="py-1.5 text-right text-wp-dim">
                  {iface.bitrate
                    ? t("settings.bitrate_kbps", {
                        kbps: Math.round(iface.bitrate / 1000),
                      })
                    : "—"}
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
      <h2 class="font-semibold mb-1">
        {t("settings.interfaces")}
        <Tooltip text={TOOLTIPS.hosting_entrypoint} />
      </h2>
      <InterfacesCard />
    </section>

    <section class="bg-wp-panel border border-wp-border rounded-xl p-5 mb-4">
      <h2 class="font-semibold mb-1">
        {t("settings.transport_node")}
        <Tooltip text={TOOLTIPS.transport_node_setting} />
      </h2>
      <label class="flex items-center gap-2 mt-2 text-sm cursor-pointer">
        <input
          type="checkbox"
          class="accent-wp-accent w-4 h-4"
          checked={Boolean($settings.transport_enabled)}
          onchange={async (e) => {
            const value = (e.currentTarget as HTMLInputElement).checked;
            const updated = await api<Record<string, unknown>>("/api/v1/settings", {
              method: "PUT",
              body: JSON.stringify({ transport_enabled: value }),
            });
            settings.set(updated);
            restartNote = true;
          }}
        />
        {t("settings.transport_carry")}
      </label>
      {#if Boolean($settings.transport_enabled)}
        <p class="text-xs text-wp-warn mt-2">
          {t("settings.transport_warn")}
        </p>
      {/if}
    </section>
  {/if}

  {#if $mode === "advanced"}
    <section class="bg-wp-panel border border-wp-border rounded-xl p-5 mb-4">
      <h2 class="font-semibold mb-1">
        {t("settings.message_delivery")}
        <Tooltip text={TOOLTIPS.delivery_method_label} />
      </h2>
      <div class="space-y-3 mt-2">
        <label class="block">
          <span class="text-sm text-wp-dim">{t("settings.delivery_method")}</span>
          <select
            class="mt-1 w-full bg-wp-bg border border-wp-border rounded-lg px-3 py-2 text-sm"
            value={$settings.delivery_method ?? "direct"}
            onchange={setDeliveryMethod}
            disabled={deliveryBusy}
          >
            <option value="direct">{t("settings.delivery_direct")}</option>
            <option value="opportunistic">{t("settings.delivery_opportunistic")}</option>
            <option value="propagated">{t("settings.delivery_propagated")}</option>
          </select>
        </label>
        <label class="block">
          <span class="text-sm text-wp-dim">
            {t("settings.prop_node_address")}
            <Tooltip text={TOOLTIPS.propagation_node_hash} />
          </span>
          <div class="flex gap-2 mt-1">
            <input
              bind:value={propNode}
              placeholder={t("common.hash_placeholder")}
              class="flex-1 bg-wp-bg border border-wp-border rounded-lg px-3 py-2 font-mono text-xs
                     focus:outline-none focus:border-wp-accent"
            />
            <button
              onclick={savePropagationNode}
              disabled={deliveryBusy}
              class="bg-wp-panel2 border border-wp-border rounded-lg px-3 text-sm
                     hover:border-wp-accent transition disabled:opacity-40"
              >{t("common.save")}</button
            >
          </div>
        </label>
        {#if deliveryNote}
          <p class="text-xs text-wp-accent" role="status" aria-live="polite">{deliveryNote}</p>
        {/if}
      </div>
    </section>
  {/if}

  {#if $mode === "advanced"}
    <section class="bg-wp-panel border border-wp-border rounded-xl p-5 mb-4">
      <h2 class="font-semibold mb-1">
        {t("settings.host_section")}
        <Tooltip text={TOOLTIPS.propagation_hosting} />
      </h2>
      <p class="text-sm text-wp-dim mb-3">
        {t("settings.host_intro")}
      </p>
      <label class="flex items-center gap-2 text-sm cursor-pointer">
        <input
          type="checkbox"
          class="accent-wp-accent w-4 h-4"
          checked={Boolean($settings.host_propagation_node)}
          disabled={hostBusy}
          onchange={togglePropagationHosting}
        />
        {t("settings.host_toggle")}
      </label>
      <div class="mt-3">
        <p class="text-sm text-wp-dim mb-1">
          {t("settings.prop_address_label")}
        </p>
        <div class="flex items-center gap-2">
          <code
            class="flex-1 bg-wp-bg border border-wp-border rounded-lg px-3 py-2 text-xs font-mono truncate"
          >
            {$status?.propagation_node_hash || "…"}
          </code>
          <button
            onclick={copyPropagationAddress}
            class="bg-wp-panel2 border border-wp-border rounded-lg px-3 py-2 text-sm hover:border-wp-accent transition-colors"
            aria-label={t("settings.copy_prop_aria")}
            >{propAddrCopied ? t("common.copied") : t("common.copy")}</button
          >
        </div>
      </div>
      {#if Boolean($settings.host_propagation_node)}
        <p class="text-xs text-wp-warn mt-2">
          {t("settings.host_warn")}
        </p>
      {/if}
      {#if hostNote}
        <p class="text-xs text-wp-accent mt-2" role="status" aria-live="polite">{hostNote}</p>
      {/if}
    </section>
  {/if}

  {#if $mode === "advanced"}
    <section class="bg-wp-panel border border-wp-border rounded-xl p-5 mb-4">
      <h2 class="font-semibold mb-1">{t("settings.glossary")}</h2>
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
    <p class="text-sm text-wp-warn">{t("settings.restart_required")}</p>
  {/if}

  <p class="text-xs text-wp-dim mt-6">
    {t("settings.footer", {
      version: $status?.version ?? "…",
      seconds: $status ? Math.round($status.uptime_seconds) : 0,
    })}
  </p>
</div>
