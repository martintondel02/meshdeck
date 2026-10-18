<script lang="ts">
  import { api } from "../lib/api";
  import { settings } from "../lib/stores";
  import Tooltip from "./Tooltip.svelte";
  import { TOOLTIPS } from "../lib/copy/tooltips";
  import { t } from "../lib/i18n";
  import {
    kindLabel,
    parseSnippet,
    shareSnippet,
    type InterfaceEntry,
    type InterfaceKind,
  } from "../lib/interfaces";

  let entries: InterfaceEntry[] = $state([]);
  let dirty = $state(false);
  let busy = $state(false);
  let note = $state("");
  let noteIsError = $state(false);
  let snippet = $state("");
  let snippetNote = $state("");
  let snippetOk = $state(false);
  let showPaste = $state(false);

  // seed from settings once they arrive
  let seeded = $state(false);
  $effect(() => {
    if (!seeded && $settings) {
      const list = $settings.interfaces;
      entries = Array.isArray(list) ? JSON.parse(JSON.stringify(list)) : [];
      seeded = true;
    }
  });

  function markDirty() {
    dirty = true;
    note = "";
  }

  function addEntry(kind: InterfaceKind) {
    const base: InterfaceEntry = { kind, name: "", enabled: true };
    if (kind === "tcp_server" || kind === "backbone_server") {
      base.listen_ip = "127.0.0.1";
      base.port = 4242;
      if (kind === "backbone_server") base.gateway_mode = true;
    } else if (kind === "tcp_client" || kind === "backbone_client") {
      base.target_host = "";
      base.target_port = 4242;
    }
    entries = [...entries, base];
    markDirty();
  }

  function removeEntry(i: number) {
    entries = entries.filter((_, j) => j !== i);
    markDirty();
  }

  async function saveAndRestart() {
    busy = true;
    note = "";
    try {
      const updated = await api<Record<string, unknown>>("/api/v1/settings", {
        method: "PUT",
        body: JSON.stringify({ interfaces: entries }),
      });
      settings.set(updated);
      const res = await api<{ restarting: boolean }>("/api/v1/restart", {
        method: "POST",
        body: "{}",
      });
      if (res.restarting) {
        note = t("settings.iface_restarting");
        noteIsError = false;
        dirty = false;
        // reload after the daemon had time to come back up
        setTimeout(() => window.location.reload(), 3500);
      }
    } catch (err) {
      note =
        err instanceof Error && err.message.startsWith("invalid")
          ? t("settings.iface_invalid")
          : t("settings.iface_save_failed");
      noteIsError = true;
    } finally {
      busy = false;
    }
  }

  function importSnippet() {
    const parsed = parseSnippet(snippet);
    if (parsed.length === 0) {
      snippetNote = t("settings.iface_import_none");
      snippetOk = false;
      return;
    }
    entries = [...entries, ...parsed];
    snippetNote = t(
      parsed.length > 1 ? "settings.iface_imported_other" : "settings.iface_imported_one",
      { count: parsed.length },
    );
    snippetOk = true;
    snippet = "";
    showPaste = false;
    markDirty();
  }

  function publicHint(ip: string | undefined): boolean {
    return ip === "0.0.0.0" || ip === "::" || ip === "[::]";
  }
</script>

<div class="space-y-3">
  {#if entries.length === 0}
    <p class="text-sm text-wp-dim">
      {t("settings.ifaces_empty_before")}
      {#if Number($settings?.connect_autointerface) === 0}&nbsp;{t("settings.ifaces_auto_off")}{/if}
      {t("settings.ifaces_empty_mid")}
      <a class="text-wp-accent hover:underline" href="https://directory.rns.recipes/" target="_blank" rel="noreferrer">directory.rns.recipes</a>
      {t("settings.ifaces_empty_or")}
      <a class="text-wp-accent hover:underline" href="https://rmap.world/" target="_blank" rel="noreferrer">rmap.world</a>.
    </p>
  {/if}

  {#each entries as entry, i (i)}
    <div class="border border-wp-border rounded-lg p-3 bg-wp-bg space-y-2">
      <div class="flex items-center gap-2">
        <span class="text-xs font-semibold text-wp-dim uppercase">{kindLabel(entry.kind)}</span>
        <div class="flex-1"></div>
        <label class="flex items-center gap-1.5 text-xs text-wp-dim cursor-pointer">
          <input
            type="checkbox"
            bind:checked={entry.enabled}
            onchange={markDirty}
            class="accent-wp-accent"
          />
          {t("settings.iface_enabled")}
        </label>
        <button
          class="text-wp-danger text-xs px-2 py-1 hover:bg-wp-danger/10 rounded"
          onclick={() => removeEntry(i)}>{t("settings.iface_remove")}</button
        >
      </div>
      <input
        bind:value={entry.name}
        oninput={markDirty}
        placeholder={t("settings.iface_name_placeholder")}
        class="w-full bg-wp-panel border border-wp-border rounded px-2.5 py-1.5 text-sm
               focus:outline-none focus:border-wp-accent"
      />
      {#if entry.kind === "tcp_server" || entry.kind === "backbone_server"}
        <div class="flex gap-2">
          <input
            bind:value={entry.listen_ip}
            oninput={markDirty}
            placeholder={t("settings.iface_listen_ip")}
            class="flex-1 bg-wp-panel border border-wp-border rounded px-2.5 py-1.5 text-sm font-mono
                   focus:outline-none focus:border-wp-accent"
          />
          <input
            type="number"
            bind:value={entry.port}
            oninput={markDirty}
            placeholder={t("settings.iface_port")}
            class="w-24 bg-wp-panel border border-wp-border rounded px-2.5 py-1.5 text-sm font-mono
                   focus:outline-none focus:border-wp-accent"
          />
        </div>
        {#if publicHint(entry.listen_ip)}
          <p class="text-xs text-wp-warn flex items-center gap-1">
            ⚠ {t("settings.iface_public_warn")}
            <Tooltip text={TOOLTIPS.hosting_entrypoint} />
          </p>
        {/if}
        {#if entry.kind === "backbone_server"}
          <label class="flex items-center gap-1.5 text-xs text-wp-dim cursor-pointer">
            <input
              type="checkbox"
              bind:checked={entry.gateway_mode}
              onchange={markDirty}
              class="accent-wp-accent"
            />
            {t("settings.iface_gateway")} <Tooltip text={TOOLTIPS.gateway_mode} />
          </label>
        {/if}
      {:else if entry.kind === "tcp_client" || entry.kind === "backbone_client"}
        <div class="flex gap-2">
          <input
            bind:value={entry.target_host}
            oninput={markDirty}
            placeholder={t("settings.iface_host")}
            class="flex-1 bg-wp-panel border border-wp-border rounded px-2.5 py-1.5 text-sm font-mono
                   focus:outline-none focus:border-wp-accent"
          />
          <input
            type="number"
            bind:value={entry.target_port}
            oninput={markDirty}
            placeholder={t("settings.iface_port")}
            class="w-24 bg-wp-panel border border-wp-border rounded px-2.5 py-1.5 text-sm font-mono
                   focus:outline-none focus:border-wp-accent"
          />
        </div>
      {/if}
    </div>
  {/each}

  <div class="flex flex-wrap gap-2">
    <button
      class="bg-wp-panel2 border border-wp-border rounded-lg px-3 py-1.5 text-xs hover:border-wp-accent transition"
      onclick={() => addEntry("tcp_client")}>＋ {t("settings.iface_add_client")}</button
    >
    <button
      class="bg-wp-panel2 border border-wp-border rounded-lg px-3 py-1.5 text-xs hover:border-wp-accent transition"
      onclick={() => addEntry("tcp_server")}>＋ {t("settings.iface_add_server")}</button
    >
    <button
      class="bg-wp-panel2 border border-wp-border rounded-lg px-3 py-1.5 text-xs hover:border-wp-accent transition"
      onclick={() => addEntry("backbone_server")}>＋ {t("settings.iface_add_backbone")}</button
    >
    <button
      class="bg-wp-panel2 border border-wp-border rounded-lg px-3 py-1.5 text-xs hover:border-wp-accent transition"
      onclick={() => addEntry("auto")}>＋ {t("settings.iface_add_auto")}</button
    >
    <button
      class="bg-wp-panel2 border border-wp-border rounded-lg px-3 py-1.5 text-xs hover:border-wp-accent transition"
      onclick={() => (showPaste = !showPaste)}>⤓ {t("settings.iface_paste")}</button
    >
  </div>

  {#if showPaste}
    <div class="space-y-2">
      <textarea
        bind:value={snippet}
        rows="6"
        placeholder={t("settings.iface_paste_placeholder")}
        class="w-full bg-wp-bg border border-wp-border rounded-lg px-3 py-2 text-xs font-mono
               focus:outline-none focus:border-wp-accent"
      ></textarea>
      <div class="flex gap-2 items-center">
        <button
          class="bg-wp-accent text-wp-bg text-xs font-semibold rounded-lg px-3 py-1.5 hover:brightness-110"
          onclick={importSnippet}>{t("settings.iface_import")}</button
        >
        {#if snippetNote}
          <span class="text-xs {snippetOk ? 'text-wp-accent' : 'text-wp-warn'}">{snippetNote}</span>
        {/if}
      </div>
    </div>
  {/if}

  {#if snippetNote && !showPaste}
    <p class="text-xs text-wp-accent">{snippetNote}</p>
  {/if}

  {#if publicServerEntries(entries).length > 0}
    <div class="border-t border-wp-border pt-3 space-y-2">
      <h3 class="text-xs font-semibold text-wp-dim uppercase tracking-wide">
        {t("settings.share_entrypoint_title")}
        <Tooltip text={TOOLTIPS.share_entrypoint} />
      </h3>
      {#each publicServerEntries(entries) as entry (entry.name)}
        <div class="bg-wp-bg border border-wp-border rounded-lg p-3">
          <div class="flex items-center justify-between mb-1">
            <span class="text-sm font-medium">{entry.name || t("settings.entrypoint_default")}</span>
            <button
              class="text-xs text-wp-accent hover:underline"
              onclick={() => navigator.clipboard.writeText(shareSnippet(entry, window.prompt(t("settings.prompt_host"), t("settings.prompt_host_default")) ?? t("settings.prompt_host_default")))}
              >{t("settings.copy_snippet")}</button
            >
          </div>
          <pre class="text-[11px] font-mono text-wp-dim whitespace-pre-wrap">{shareSnippet(entry, t("settings.share_host_placeholder"))}</pre>
        </div>
      {/each}
    </div>
  {/if}

  <div class="flex items-center gap-3 pt-1">
    <button
      onclick={saveAndRestart}
      disabled={busy || !dirty}
      class="bg-wp-accent text-wp-bg font-semibold rounded-lg px-4 py-2 text-sm
             hover:brightness-110 transition disabled:opacity-40"
    >
      {busy ? t("settings.working") : t("settings.save_restart_net")}
    </button>
    {#if dirty && !busy}
      <span class="text-xs text-wp-warn">{t("settings.unsaved")}</span>
    {/if}
  </div>
  {#if note}
    <p class="text-sm {noteIsError ? 'text-wp-danger' : 'text-wp-accent'}">{note}</p>
  {/if}
</div>

<script lang="ts" module>
  function publicServerEntries(entries: InterfaceEntry[]): InterfaceEntry[] {
    return entries.filter(
      (e) =>
        (e.kind === "tcp_server" || e.kind === "backbone_server") && e.enabled,
    );
  }
</script>
