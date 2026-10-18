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

  // Phase 6.3 disk-usage fields are part of the shared Status type.
  const live = $derived($status);

  // Page cache sizes are binary (the cap is 64 MiB); the propagation store is
  // decimal because LXMF's limit is decimal MB.
  function binarySize(bytes: number): string {
    if (bytes <= 0) return "0 B";
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  }
  function decimalSize(bytes: number): string {
    if (bytes <= 0) return "0 B";
    if (bytes < 1_000_000) return `${(bytes / 1000).toFixed(1)} KB`;
    return `${(bytes / 1_000_000).toFixed(1)} MB`;
  }

  let storageLimit = $state<number | string>("");
  let storageLimitBusy = $state(false);
  let storageLimitNote = $state("");
  let cacheBusy = $state(false);
  let cacheNote = $state("");

  // Phase 7.1: the remaining bounded stores.
  let pageCacheLimit = $state<number | string>("");
  let pageCacheNote = $state("");
  let attachmentLimit = $state<number | string>("");
  let attachmentDays = $state<number | string>("");
  let attachmentNote = $state("");
  let sharedLimit = $state<number | string>("");
  let sharedNote = $state("");
  let pagesLimit = $state<number | string>("");
  let pagesNote = $state("");
  let messageDays = $state<number | string>("");
  let messageNote = $state("");
  let logLimit = $state<number | string>("");
  let logNote = $state("");
  let storageBusy = $state(false);

  $effect(() => {
    const s = $settings ?? {};
    if (typeof s.page_cache_max_bytes === "number") pageCacheLimit = s.page_cache_max_bytes;
    if (typeof s.attachment_storage_max_mb === "number") attachmentLimit = s.attachment_storage_max_mb;
    if (typeof s.attachment_retention_days === "number") attachmentDays = s.attachment_retention_days;
    if (typeof s.shared_storage_max_mb === "number") sharedLimit = s.shared_storage_max_mb;
    if (typeof s.pages_storage_max_mb === "number") pagesLimit = s.pages_storage_max_mb;
    if (typeof s.message_retention_days === "number") messageDays = s.message_retention_days;
    if (typeof s.log_max_mb === "number") logLimit = s.log_max_mb;
  });

  function wholeNumber(raw: number | string, min: number, max: number): number | null {
    const text = String(raw ?? "").trim();
    const value = Number(text);
    if (text === "" || !Number.isInteger(value) || value < min || value > max) return null;
    return value;
  }

  async function putSettings(payload: Record<string, unknown>) {
    try {
      const updated = await api<Record<string, unknown>>("/api/v1/settings", {
        method: "PUT",
        body: JSON.stringify(payload),
      });
      settings.set(updated);
      await refreshStatus();
      return updated;
    } catch {
      return null;
    }
  }

  async function savePageCacheLimit() {
    const value = wholeNumber(pageCacheLimit, 0, 1073741824);
    if (value === null) {
      pageCacheNote = t("settings.page_cache_limit_invalid");
      return;
    }
    storageBusy = true;
    const updated = await putSettings({ page_cache_max_bytes: value });
    pageCacheNote = updated
      ? t("settings.page_cache_limit_saved")
      : t("settings.page_cache_limit_invalid");
    storageBusy = false;
  }

  async function saveAttachmentLimits() {
    const limit = wholeNumber(attachmentLimit, 0, 102400);
    const days = wholeNumber(attachmentDays, 0, 3650);
    if (limit === null || days === null) {
      attachmentNote = t("settings.attachments_invalid");
      return;
    }
    storageBusy = true;
    const updated = await putSettings({
      attachment_storage_max_mb: limit,
      attachment_retention_days: days,
    });
    if (!updated) {
      attachmentNote = t("settings.attachments_invalid");
    } else {
      const effects = (updated.effects ?? {}) as Record<string, number>;
      attachmentNote = t("settings.attachments_saved", {
        removed: Number(effects.attachment_removed ?? 0),
        freed: binarySize(Number(effects.attachment_freed_bytes ?? 0)),
      });
    }
    storageBusy = false;
  }

  async function saveSharedLimit() {
    const value = wholeNumber(sharedLimit, 0, 102400);
    if (value === null) {
      sharedNote = t("settings.shared_limit_invalid");
      return;
    }
    storageBusy = true;
    const updated = await putSettings({ shared_storage_max_mb: value });
    sharedNote = updated
      ? t("settings.shared_limit_saved")
      : t("settings.shared_limit_invalid");
    storageBusy = false;
  }

  async function savePagesLimit() {
    const value = wholeNumber(pagesLimit, 0, 10240);
    if (value === null) {
      pagesNote = t("settings.pages_limit_invalid");
      return;
    }
    storageBusy = true;
    const updated = await putSettings({ pages_storage_max_mb: value });
    pagesNote = updated
      ? t("settings.pages_limit_saved")
      : t("settings.pages_limit_invalid");
    storageBusy = false;
  }

  async function saveMessageRetention() {
    const days = wholeNumber(messageDays, 0, 3650);
    if (days === null) {
      messageNote = t("settings.messages_invalid");
      return;
    }
    storageBusy = true;
    const updated = await putSettings({ message_retention_days: days });
    if (!updated) {
      messageNote = t("settings.messages_invalid");
    } else {
      const effects = (updated.effects ?? {}) as Record<string, number>;
      messageNote = t("settings.messages_saved", {
        removed: Number(effects.messages_pruned ?? 0),
      });
    }
    storageBusy = false;
  }

  async function saveLogLimit() {
    const value = wholeNumber(logLimit, 0, 1024);
    if (value === null) {
      logNote = t("settings.log_limit_invalid");
      return;
    }
    storageBusy = true;
    const updated = await putSettings({ log_max_mb: value });
    logNote = updated ? t("settings.log_limit_saved") : t("settings.log_limit_invalid");
    storageBusy = false;
  }

  $effect(() => {
    const value = $settings?.propagation_storage_limit_mb;
    if (typeof value === "number") storageLimit = value;
  });

  async function refreshStatus() {
    try {
      status.set(await api("/api/v1/status"));
    } catch {
      /* the 5 s status poll in App.svelte will catch up */
    }
  }

  async function saveStorageLimit() {
    // bind:value on <input type="number"> yields a number, but a cleared or
    // partially typed field can still be a string — normalise both.
    const raw = String(storageLimit ?? "").trim();
    const value = Number(raw);
    if (raw === "" || !Number.isInteger(value) || value < 0 || value > 10240) {
      storageLimitNote = t("settings.propagation_limit_invalid");
      return;
    }
    storageLimitBusy = true;
    storageLimitNote = "";
    try {
      const updated = await api<Record<string, unknown>>("/api/v1/settings", {
        method: "PUT",
        body: JSON.stringify({ propagation_storage_limit_mb: value }),
      });
      settings.set(updated);
      storageLimitNote = t("settings.propagation_limit_saved");
      // The usage line shows the limit LXMF actually holds; refresh it now
      // instead of waiting for the next status poll.
      await refreshStatus();
    } catch {
      storageLimitNote = t("settings.propagation_limit_invalid");
    } finally {
      storageLimitBusy = false;
    }
  }

  async function clearCache() {
    cacheBusy = true;
    cacheNote = "";
    try {
      const result = await api<{ cleared: number }>("/api/v1/page_cache", {
        method: "DELETE",
      });
      const count = result.cleared ?? 0;
      cacheNote = t(
        count === 1 ? "settings.cache_cleared_one" : "settings.cache_cleared_other",
        { count },
      );
      await refreshStatus();
    } catch {
      cacheNote = t("settings.cache_clear_failed");
    } finally {
      cacheBusy = false;
    }
  }

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

      <div class="mt-4 border-t border-wp-border pt-4" data-testid="propagation-storage">
        <p class="text-sm" role="status" aria-live="polite">
          {#if !Boolean($settings.host_propagation_node) || live?.propagation_store_bytes == null}
            {t("settings.propagation_store_not_hosting")}
          {:else if live?.propagation_storage_limit_bytes}
            {t("settings.propagation_store_usage", {
              used: decimalSize(live.propagation_store_bytes),
              limit: decimalSize(live.propagation_storage_limit_bytes),
            })}
          {:else}
            {t("settings.propagation_store_usage_unlimited", {
              used: decimalSize(live.propagation_store_bytes),
            })}
          {/if}
        </p>
        <label class="block mt-3">
          <span class="text-sm text-wp-dim">{t("settings.propagation_limit_label")}</span>
          <div class="flex gap-2 mt-1">
            <input
              type="number"
              min="0"
              max="10240"
              step="1"
              inputmode="numeric"
              bind:value={storageLimit}
              class="w-32 bg-wp-bg border border-wp-border rounded-lg px-3 py-2 text-sm
                     focus:outline-none focus:border-wp-accent"
              aria-label={t("settings.propagation_limit_label")}
            />
            <button
              onclick={saveStorageLimit}
              disabled={storageLimitBusy}
              class="bg-wp-panel2 border border-wp-border rounded-lg px-3 text-sm
                     hover:border-wp-accent transition disabled:opacity-40"
              >{t("common.save")}</button
            >
          </div>
        </label>
        <p class="text-xs text-wp-dim mt-1">{t("settings.propagation_limit_hint")}</p>
        {#if storageLimitNote}
          <p class="text-xs text-wp-accent mt-1" role="status" aria-live="polite">
            {storageLimitNote}
          </p>
        {/if}
      </div>

      {#if hostNote}
        <p class="text-xs text-wp-accent mt-2" role="status" aria-live="polite">{hostNote}</p>
      {/if}
    </section>
  {/if}

  {#if $mode === "advanced"}
    <section class="bg-wp-panel border border-wp-border rounded-xl p-5 mb-4" data-testid="page-cache">
      <h2 class="font-semibold mb-1">{t("settings.storage_section")}</h2>

      <!-- Page cache (bounded automatically; safe to clear) -->
      <div data-testid="page-cache-usage">
        <p class="text-sm" role="status" aria-live="polite">
          {#if live?.page_cache_max_bytes}
            {t("settings.page_cache_usage", {
              used: binarySize(live.page_cache_bytes ?? 0),
              limit: binarySize(live.page_cache_max_bytes),
            })}
          {:else}
            {t("settings.page_cache_usage_unlimited", {
              used: binarySize(live?.page_cache_bytes ?? 0),
            })}
          {/if}
        </p>
        <label class="block mt-2">
          <span class="text-sm text-wp-dim">{t("settings.page_cache_limit_label")}</span>
          <div class="flex gap-2 mt-1">
            <input
              type="number"
              min="0"
              max="1073741824"
              step="1"
              inputmode="numeric"
              bind:value={pageCacheLimit}
              class="w-40 bg-wp-bg border border-wp-border rounded-lg px-3 py-2 text-sm
                     focus:outline-none focus:border-wp-accent"
              aria-label={t("settings.page_cache_limit_label")}
            />
            <button
              onclick={savePageCacheLimit}
              disabled={storageBusy}
              class="bg-wp-panel2 border border-wp-border rounded-lg px-3 text-sm
                     hover:border-wp-accent transition disabled:opacity-40"
              >{t("common.save")}</button
            >
          </div>
        </label>
        <p class="text-xs text-wp-dim mt-1">{t("settings.page_cache_limit_hint")}</p>
        {#if pageCacheNote}
          <p class="text-xs text-wp-accent mt-1" role="status" aria-live="polite">
            {pageCacheNote}
          </p>
        {/if}
        <button
          onclick={clearCache}
          disabled={cacheBusy}
          class="mt-3 bg-wp-panel2 border border-wp-border rounded-lg px-4 py-2 text-sm
                 hover:border-wp-accent transition-colors disabled:opacity-40"
          >{t("settings.clear_cache")}</button
        >
        {#if cacheNote}
          <p class="text-xs text-wp-accent mt-2" role="status" aria-live="polite">{cacheNote}</p>
        {/if}
      </div>

      <!-- Chat attachment blobs (pruning keeps the message rows) -->
      <div class="mt-4 border-t border-wp-border pt-4" data-testid="attachment-storage">
        <p class="text-sm" role="status" aria-live="polite">
          {#if live?.attachment_storage_max_bytes}
            {t("settings.attachments_usage", {
              used: binarySize(live.attachment_bytes ?? 0),
              limit: binarySize(live.attachment_storage_max_bytes),
              count: live.attachment_files ?? 0,
            })}
          {:else}
            {t("settings.attachments_usage_unlimited", {
              used: binarySize(live?.attachment_bytes ?? 0),
              count: live?.attachment_files ?? 0,
            })}
          {/if}
        </p>
        <div class="grid sm:grid-cols-2 gap-3 mt-2">
          <label class="block">
            <span class="text-sm text-wp-dim">{t("settings.attachment_limit_label")}</span>
            <input
              type="number"
              min="0"
              max="102400"
              step="1"
              inputmode="numeric"
              bind:value={attachmentLimit}
              class="mt-1 w-full bg-wp-bg border border-wp-border rounded-lg px-3 py-2 text-sm
                     focus:outline-none focus:border-wp-accent"
              aria-label={t("settings.attachment_limit_label")}
            />
          </label>
          <label class="block">
            <span class="text-sm text-wp-dim">{t("settings.attachment_retention_label")}</span>
            <input
              type="number"
              min="0"
              max="3650"
              step="1"
              inputmode="numeric"
              bind:value={attachmentDays}
              class="mt-1 w-full bg-wp-bg border border-wp-border rounded-lg px-3 py-2 text-sm
                     focus:outline-none focus:border-wp-accent"
              aria-label={t("settings.attachment_retention_label")}
            />
          </label>
        </div>
        <p class="text-xs text-wp-warn mt-2">{t("settings.attachment_retention_warn")}</p>
        <button
          onclick={saveAttachmentLimits}
          disabled={storageBusy}
          class="mt-2 bg-wp-panel2 border border-wp-border rounded-lg px-3 py-1.5 text-sm
                 hover:border-wp-accent transition disabled:opacity-40"
          >{t("common.save")}</button
        >
        {#if attachmentNote}
          <p class="text-xs text-wp-accent mt-1" role="status" aria-live="polite">
            {attachmentNote}
          </p>
        {/if}
      </div>

      <!-- Node-shared files: user content, never auto-deleted -->
      <div class="mt-4 border-t border-wp-border pt-4" data-testid="shared-storage">
        <p class="text-sm" role="status" aria-live="polite">
          {#if live?.shared_storage_max_bytes}
            {t("settings.shared_usage", {
              used: binarySize(live.shared_bytes ?? 0),
              limit: binarySize(live.shared_storage_max_bytes),
              count: live.shared_files ?? 0,
            })}
          {:else}
            {t("settings.shared_usage_unlimited", {
              used: binarySize(live?.shared_bytes ?? 0),
              count: live?.shared_files ?? 0,
            })}
          {/if}
        </p>
        <label class="block mt-2">
          <span class="text-sm text-wp-dim">{t("settings.shared_limit_label")}</span>
          <div class="flex gap-2 mt-1">
            <input
              type="number"
              min="0"
              max="102400"
              step="1"
              inputmode="numeric"
              bind:value={sharedLimit}
              class="w-40 bg-wp-bg border border-wp-border rounded-lg px-3 py-2 text-sm
                     focus:outline-none focus:border-wp-accent"
              aria-label={t("settings.shared_limit_label")}
            />
            <button
              onclick={saveSharedLimit}
              disabled={storageBusy}
              class="bg-wp-panel2 border border-wp-border rounded-lg px-3 text-sm
                     hover:border-wp-accent transition disabled:opacity-40"
              >{t("common.save")}</button
            >
          </div>
        </label>
        <p class="text-xs text-wp-dim mt-1">{t("settings.shared_hint")}</p>
        {#if sharedNote}
          <p class="text-xs text-wp-accent mt-1" role="status" aria-live="polite">{sharedNote}</p>
        {/if}
      </div>

      <!-- Hosted pages: user content, never auto-deleted -->
      <div class="mt-4 border-t border-wp-border pt-4" data-testid="pages-storage">
        <p class="text-sm" role="status" aria-live="polite">
          {#if live?.pages_storage_max_bytes}
            {t("settings.pages_usage", {
              used: binarySize(live.pages_bytes ?? 0),
              limit: binarySize(live.pages_storage_max_bytes),
              count: live.pages_entries ?? 0,
            })}
          {:else}
            {t("settings.pages_usage_unlimited", {
              used: binarySize(live?.pages_bytes ?? 0),
              count: live?.pages_entries ?? 0,
            })}
          {/if}
        </p>
        <label class="block mt-2">
          <span class="text-sm text-wp-dim">{t("settings.pages_limit_label")}</span>
          <div class="flex gap-2 mt-1">
            <input
              type="number"
              min="0"
              max="10240"
              step="1"
              inputmode="numeric"
              bind:value={pagesLimit}
              class="w-40 bg-wp-bg border border-wp-border rounded-lg px-3 py-2 text-sm
                     focus:outline-none focus:border-wp-accent"
              aria-label={t("settings.pages_limit_label")}
            />
            <button
              onclick={savePagesLimit}
              disabled={storageBusy}
              class="bg-wp-panel2 border border-wp-border rounded-lg px-3 text-sm
                     hover:border-wp-accent transition disabled:opacity-40"
              >{t("common.save")}</button
            >
          </div>
        </label>
        <p class="text-xs text-wp-dim mt-1">{t("settings.pages_hint")}</p>
        {#if pagesNote}
          <p class="text-xs text-wp-accent mt-1" role="status" aria-live="polite">{pagesNote}</p>
        {/if}
      </div>

      <!-- SQLite message history retention -->
      <div class="mt-4 border-t border-wp-border pt-4" data-testid="message-history">
        <p class="text-sm" role="status" aria-live="polite">
          {t("settings.messages_usage", { count: live?.message_count ?? 0 })}
        </p>
        <label class="block mt-2">
          <span class="text-sm text-wp-dim">{t("settings.messages_retention_label")}</span>
          <div class="flex gap-2 mt-1">
            <input
              type="number"
              min="0"
              max="3650"
              step="1"
              inputmode="numeric"
              bind:value={messageDays}
              class="w-32 bg-wp-bg border border-wp-border rounded-lg px-3 py-2 text-sm
                     focus:outline-none focus:border-wp-accent"
              aria-label={t("settings.messages_retention_label")}
            />
            <button
              onclick={saveMessageRetention}
              disabled={storageBusy}
              class="bg-wp-panel2 border border-wp-border rounded-lg px-3 text-sm
                     hover:border-wp-accent transition disabled:opacity-40"
              >{t("common.save")}</button
            >
          </div>
        </label>
        <p class="text-xs text-wp-warn mt-1">{t("settings.messages_retention_warn")}</p>
        {#if messageNote}
          <p class="text-xs text-wp-accent mt-1" role="status" aria-live="polite">{messageNote}</p>
        {/if}
      </div>

      <!-- MeshDeck/Reticulum logs (rotated at startup) -->
      <div class="mt-4 border-t border-wp-border pt-4" data-testid="log-storage">
        <p class="text-sm" role="status" aria-live="polite">
          {#if live?.log_max_bytes}
            {t("settings.logs_usage", {
              used: binarySize(live.log_bytes ?? 0),
              limit: binarySize(live.log_max_bytes),
            })}
          {:else}
            {t("settings.logs_usage_unlimited", { used: binarySize(live?.log_bytes ?? 0) })}
          {/if}
        </p>
        <label class="block mt-2">
          <span class="text-sm text-wp-dim">{t("settings.log_limit_label")}</span>
          <div class="flex gap-2 mt-1">
            <input
              type="number"
              min="0"
              max="1024"
              step="1"
              inputmode="numeric"
              bind:value={logLimit}
              class="w-32 bg-wp-bg border border-wp-border rounded-lg px-3 py-2 text-sm
                     focus:outline-none focus:border-wp-accent"
              aria-label={t("settings.log_limit_label")}
            />
            <button
              onclick={saveLogLimit}
              disabled={storageBusy}
              class="bg-wp-panel2 border border-wp-border rounded-lg px-3 text-sm
                     hover:border-wp-accent transition disabled:opacity-40"
              >{t("common.save")}</button
            >
          </div>
        </label>
        <p class="text-xs text-wp-dim mt-1">{t("settings.log_limit_hint")}</p>
        {#if logNote}
          <p class="text-xs text-wp-accent mt-1" role="status" aria-live="polite">{logNote}</p>
        {/if}
      </div>
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
