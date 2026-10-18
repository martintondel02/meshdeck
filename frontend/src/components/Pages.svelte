<script lang="ts">
  import { onMount } from "svelte";
  import { api, downloadBlob, uploadFile } from "../lib/api";
  import Tooltip from "./Tooltip.svelte";
  import TransferBar from "./TransferBar.svelte";
  import {
    humanSize,
    nodeInfo,
    nodes,
    pages,
    status,
    transfers,
    type BrowseResult,
    type NodeInfo,
    type NodeMeta,
    type PageMeta,
    type SharedFile,
  } from "../lib/stores";
  import { renderMicron } from "../lib/micron";
  import { timeAgo } from "../lib/format";
  import { TOOLTIPS } from "../lib/copy/tooltips";
  import { t } from "../lib/i18n";

  // editor state
  let activePage = $state<string | null>(null);
  let editor = $state("");
  let dirty = $state(false);
  let edMsg = $state("");
  let newName = $state("");
  let showPreview = $state(false);

  // hosting state
  let nodeName = $state("");
  let serve = $state(false);
  let hostMsg = $state("");

  // browser state
  let browseHash = $state("");
  let browsePath = $state("/page/index.mu");
  let browsing = $state(false);
  let browseErr = $state("");
  let pageResult = $state<BrowseResult | null>(null);
  let back = $state<{ hash: string; path: string }[]>([]);
  let transferId = $state<string | null>(null);
  let fileTransferId = $state<string | null>(null);
  let fileBusy = $state(false);

  function newId(): string {
    return crypto.randomUUID?.() ?? Math.random().toString(36).slice(2);
  }

  // Register the transfer locally so the bar is visible before the first
  // progress event arrives over the WebSocket.
  function beginTransfer(kind: "page" | "file", path: string): string {
    const id = newId();
    transfers.update((all) => ({
      ...all,
      [id]: { id, path, kind, progress: 0, done: false },
    }));
    return id;
  }

  onMount(() => {
    loadAll();
    loadShared();
  });

  async function loadAll() {
    try {
      const [p, n, info] = await Promise.all([
        api<PageMeta[]>("/api/v1/pages"),
        api<NodeMeta[]>("/api/v1/nodes"),
        api<NodeInfo>("/api/v1/node"),
      ]);
      pages.set(p);
      nodes.set(n);
      nodeInfo.set(info);
      nodeName = info.node_name;
      serve = info.serve_pages;
    } catch {
      /* offline */
    }
  }

  async function openPage(name: string) {
    try {
      const res = await api<{ name: string; content: string }>(
        `/api/v1/pages/${encodeURIComponent(name)}`,
      );
      activePage = res.name;
      editor = res.content;
      dirty = false;
      edMsg = "";
    } catch {
      edMsg = t("pages.error_load");
    }
  }

  async function createPage() {
    const name = newName.trim().toLowerCase();
    if (!name) return;
    edMsg = "";
    try {
      await api(`/api/v1/pages/${encodeURIComponent(name)}`, {
        method: "PUT",
        body: JSON.stringify({ content: "" }),
      });
      newName = "";
      await openPage(name);
      pages.set(await api<PageMeta[]>("/api/v1/pages"));
    } catch (e) {
      const code = e instanceof Error ? e.message : "";
      edMsg = storageErrorText(code) ?? (code || t("common.failed"));
    }
  }

  async function savePage() {
    if (!activePage) return;
    edMsg = "";
    try {
      await api(`/api/v1/pages/${encodeURIComponent(activePage)}`, {
        method: "PUT",
        body: JSON.stringify({ content: editor }),
      });
      dirty = false;
      edMsg = t("pages.saved");
      pages.set(await api<PageMeta[]>("/api/v1/pages"));
    } catch (e) {
      const code = e instanceof Error ? e.message : "";
      edMsg = storageErrorText(code) ?? (code || t("pages.error_save"));
    }
  }

  async function removePage(name: string) {
    if (!confirm(t("pages.confirm_delete", { name }))) return;
    await api(`/api/v1/pages/${encodeURIComponent(name)}`, { method: "DELETE" });
    if (activePage === name) {
      activePage = null;
      editor = "";
    }
    pages.set(await api<PageMeta[]>("/api/v1/pages"));
  }

  async function publish() {
    hostMsg = "";
    try {
      const info = await api<NodeInfo>("/api/v1/node/publish", {
        method: "POST",
        body: JSON.stringify({ node_name: nodeName, serve }),
      });
      nodeInfo.set(info);
      hostMsg = serve
        ? t("pages.announced")
        : t("pages.saved_serving_off");
    } catch (e) {
      hostMsg = e instanceof Error ? e.message : t("pages.error_announce");
    }
  }

  function normalizePath(raw: string): string {
    let path = raw.trim() || "/page/index.mu";
    if (!path.startsWith("/")) path = "/" + path;
    return path.startsWith("/page/") || path.startsWith("/file/") ? path : "/page/" + path;
  }

  async function fetchPage(node: string, path: string, refresh = false) {
    browsing = true;
    browseErr = "";
    pageResult = null;
    transferId = beginTransfer("page", path);
    const query = `?transfer_id=${encodeURIComponent(transferId)}${
      refresh ? "&refresh=1" : ""
    }`;
    try {
      pageResult = await api<BrowseResult>(
        `/api/v1/browse/${encodeURIComponent(node)}${path}${query}`,
      );
    } catch (e) {
      browseErr = browseErrorText(e);
    } finally {
      browsing = false;
    }
  }

  async function browse() {
    const node = browseHash.trim();
    if (!node) return;
    const path = normalizePath(browsePath);
    browseHash = node;
    browsePath = path;
    back = [];
    await fetchPage(node, path);
  }

  // Internal micron links carry data-node/data-path; navigate in place instead
  // of doing nothing (or jumping to the top with href="#").
  async function followLink(ev: MouseEvent) {
    const target = ev.target;
    if (!(target instanceof Element)) return;
    const anchor = target.closest("a.micron-link");
    if (!(anchor instanceof HTMLAnchorElement)) return;
    ev.preventDefault();
    const node = anchor.dataset.node || browseHash;
    if (!node) return;
    const path = normalizePath(anchor.dataset.path || "/page/index.mu");
    back = [...back, { hash: browseHash, path: browsePath }];
    browseHash = node;
    browsePath = path;
    await fetchPage(node, path);
  }

  async function goBack() {
    const prev = back.at(-1);
    if (!prev) return;
    back = back.slice(0, -1);
    browseHash = prev.hash;
    browsePath = prev.path;
    await fetchPage(prev.hash, prev.path);
  }

  function readerLinks(node: HTMLElement) {
    const handler = (ev: Event) => void followLink(ev as MouseEvent);
    node.addEventListener("click", handler);
    return { destroy: () => node.removeEventListener("click", handler) };
  }

  function browseErrorText(e: unknown): string {
    const code = e instanceof Error ? e.message : "";
    switch (code) {
      case "no_path":
        return t("pages.error_no_path");
      case "link_timeout":
        return t("pages.error_timeout");
      default:
        return code || t("pages.error_fetch");
    }
  }

  // shared files state
  let shared = $state<SharedFile[]>([]);
  let sharedMsg = $state("");
  let dlNode = $state("");
  let dlName = $state("");

  async function loadShared() {
    try {
      shared = await api<SharedFile[]>("/api/v1/shared");
    } catch {
      /* offline */
    }
  }

  async function uploadShared(file: File) {
    sharedMsg = "";
    if (file.size > 32 * 1024 * 1024) {
      sharedMsg = t("pages.error_file_too_big");
      return;
    }
    const form = new FormData();
    form.append("file", file);
    try {
      await uploadFile("/api/v1/shared", form);
      sharedMsg = t("pages.shared_ok");
      await loadShared();
    } catch (e) {
      const code = e instanceof Error ? e.message : "";
      sharedMsg = storageErrorText(code) ?? (code || t("pages.error_upload"));
    }
  }

  async function unshare(name: string) {
    if (!confirm(t("pages.confirm_unshare", { name }))) return;
    await api(`/api/v1/shared/${encodeURIComponent(name)}`, { method: "DELETE" });
    await loadShared();
  }

  async function downloadFromNode() {
    sharedMsg = "";
    if (!dlNode.trim() || !dlName.trim()) return;
    const name = dlName.trim();
    fileBusy = true;
    fileTransferId = beginTransfer("file", `/file/${name}`);
    try {
      await downloadBlob(
        `/api/v1/browse/${encodeURIComponent(dlNode.trim())}/file/${encodeURIComponent(name)}?transfer_id=${encodeURIComponent(fileTransferId)}`,
        name,
      );
      sharedMsg = t("pages.download_started");
    } catch (e) {
      sharedMsg = browseErrorText(e);
    } finally {
      fileBusy = false;
    }
  }

  function copyText(text: string) {
    navigator.clipboard?.writeText(text).then(
      () => (sharedMsg = t("pages.copied")),
      () => (sharedMsg = t("pages.copy_failed")),
    );
  }

  const rendered = $derived(renderMicron(editor));
  const live = $derived($status);

  function binarySize(bytes: number): string {
    if (bytes <= 0) return "0 B";
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  }

  function storageErrorText(code: string): string | null {
    return code === "shared_storage_full" || code === "pages_storage_full"
      ? t("pages.error_storage_full")
      : null;
  }
</script>

<div class="p-6 max-w-5xl mx-auto space-y-8">
  <h1 class="text-xl font-bold text-wp-text">{t("pages.title")}</h1>
  <p class="text-wp-dim text-sm -mt-4">
    {t("pages.subtitle")}
    <Tooltip text={TOOLTIPS.hosting_pages} />
  </p>

  <div class="grid md:grid-cols-3 gap-6">
    <!-- editor column -->
    <div class="bg-wp-panel border border-wp-border rounded-xl p-4 space-y-3">
      <h2 class="text-sm font-semibold text-wp-dim uppercase tracking-wide">
        {t("pages.my_pages")}
      </h2>
      {#if $nodeInfo}
        <div class="text-xs bg-wp-bg border border-wp-border rounded-lg p-2 break-all">
          {t("pages.node_address")}
          <code class="select-all">{$nodeInfo.node_hash}</code>
        </div>
      {/if}
      <p class="text-xs text-wp-dim" role="status" aria-live="polite">
        {#if live?.pages_storage_max_bytes}
          {t("pages.my_pages_usage", {
            used: binarySize(live.pages_bytes ?? 0),
            limit: binarySize(live.pages_storage_max_bytes),
            count: live.pages_entries ?? 0,
          })}
        {:else}
          {t("pages.my_pages_usage_unlimited", {
            used: binarySize(live?.pages_bytes ?? 0),
            count: live?.pages_entries ?? 0,
          })}
        {/if}
      </p>

      <div class="flex gap-2">
        <input
          bind:value={newName}
          placeholder={t("common.page_name_placeholder")}
          class="flex-1 bg-wp-bg border border-wp-border rounded-lg px-2 py-1 text-sm"
        />
        <button
          onclick={createPage}
          aria-label={t("pages.create_page")}
          title={t("pages.create_page")}
          class="bg-wp-accent text-wp-bg text-sm font-semibold px-3 py-1 rounded-lg"
          >＋</button
        >
      </div>

      {#if $pages.length === 0}
        <p class="text-wp-dim text-sm">
          {t("pages.no_pages_before")} <code>index.mu</code> {t("pages.no_pages_after")}
        </p>
      {:else}
        <ul class="space-y-1">
          {#each $pages as p (p.name)}
            <li class="flex items-center gap-2 text-sm">
              <button
                class="flex-1 text-left hover:text-wp-text {activePage === p.name
                  ? 'text-wp-accent'
                  : 'text-wp-dim'}"
                onclick={() => openPage(p.name)}>{p.name}</button
              >
              <button
                class="text-wp-dim hover:text-wp-danger text-xs"
                aria-label={t("pages.delete_page_aria", { name: p.name })}
                title={t("common.delete")}
                onclick={() => removePage(p.name)}>✕</button
              >
            </li>
          {/each}
        </ul>
      {/if}
    </div>

    <!-- editor -->
    <div class="md:col-span-2 bg-wp-panel border border-wp-border rounded-xl p-4 space-y-2">
      <div class="flex items-center justify-between">
        <h2 class="text-sm font-semibold text-wp-dim uppercase tracking-wide">
          {activePage ?? t("pages.select_or_create")}
        </h2>
        {#if activePage}
          <div class="flex gap-2 items-center">
            <button
              class="text-xs text-wp-dim hover:text-wp-text"
              onclick={() => (showPreview = !showPreview)}
              >{showPreview ? t("pages.edit") : t("pages.preview")}</button
            >
            <button
              onclick={savePage}
              class="bg-wp-accent text-wp-bg text-sm font-semibold px-3 py-1 rounded-lg"
              disabled={!dirty}>{t("common.save")}</button
            >
          </div>
        {/if}
      </div>
      {#if activePage}
        {#if showPreview}
          <div class="micron bg-wp-bg rounded-lg p-4 min-h-64 text-sm">
            {@html rendered}
          </div>
        {:else}
          <textarea
            bind:value={editor}
            oninput={() => (dirty = true)}
            rows="18"
            spellcheck="false"
            class="w-full bg-wp-bg border border-wp-border rounded-lg p-3 text-sm font-mono"
            placeholder={t("pages.editor_placeholder")}
          ></textarea>
        {/if}
      {/if}
      {#if edMsg}
        <p class="text-xs text-wp-dim" role="status" aria-live="polite">{edMsg}</p>
      {/if}
    </div>
  </div>

  <!-- hosting toggle -->
  <section class="bg-wp-panel border border-wp-border rounded-xl p-4 space-y-3">
    <h2 class="text-sm font-semibold text-wp-dim uppercase tracking-wide">
      {t("pages.host_my_node")}
      <Tooltip text={TOOLTIPS.hosting_pages} />
    </h2>
    <div class="flex flex-wrap items-center gap-3">
      <label class="text-sm text-wp-text">
        {t("pages.node_name")}
        <input
          bind:value={nodeName}
          placeholder={t("pages.node_name_placeholder")}
          class="ml-2 bg-wp-bg border border-wp-border rounded-lg px-2 py-1 text-sm"
        />
      </label>
      <label class="flex items-center gap-2 text-sm text-wp-text">
        <input type="checkbox" bind:checked={serve} />
        {t("pages.announce_toggle")}
        <Tooltip text={TOOLTIPS.node_announce} />
      </label>
      <button
        onclick={publish}
        class="bg-wp-accent text-wp-bg text-sm font-semibold px-4 py-1.5 rounded-lg"
        >{t("pages.apply_announce")}</button
      >
      {#if hostMsg}
        <span class="text-xs text-wp-dim" role="status" aria-live="polite">{hostMsg}</span>
      {/if}
    </div>
  </section>

  <!-- browser -->
  <section class="bg-wp-panel border border-wp-border rounded-xl p-4 space-y-3">
    <h2 class="text-sm font-semibold text-wp-dim uppercase tracking-wide">
      {t("pages.browse_nodes")}
      <Tooltip text={TOOLTIPS.node_browse} />
    </h2>

    {#if $nodes.length > 0}
      <div class="flex flex-wrap gap-2">
        {#each $nodes as n (n.hash)}
          <button
            class="text-xs bg-wp-bg border border-wp-border rounded-full px-3 py-1 hover:border-wp-accent"
            onclick={() => {
              browseHash = n.hash;
              browsePath = "/page/index.mu";
            }}>{n.name ?? n.hash.slice(0, 10) + "…"}</button
          >
        {/each}
      </div>
    {:else}
      <p class="text-xs text-wp-dim">
        {t("pages.no_nodes")}
      </p>
    {/if}

    <div class="flex flex-wrap gap-2 items-center">
      <input
        bind:value={browseHash}
        placeholder={t("common.node_address_placeholder")}
        class="flex-1 min-w-64 bg-wp-bg border border-wp-border rounded-lg px-2 py-1 text-sm font-mono"
      />
      <input
        bind:value={browsePath}
        placeholder="/page/index.mu"
        class="w-44 bg-wp-bg border border-wp-border rounded-lg px-2 py-1 text-sm font-mono"
      />
      <button
        onclick={browse}
        disabled={browsing || !browseHash.trim()}
        class="bg-wp-accent text-wp-bg text-sm font-semibold px-4 py-1.5 rounded-lg"
        >{browsing ? t("pages.fetching") : t("pages.open")}</button
      >
    </div>
    {#if browsing && transferId}
      <TransferBar transfer={$transfers[transferId]} />
    {/if}
    {#if browseErr}
      <p class="text-xs text-wp-danger">{browseErr}</p>
    {/if}

    {#if pageResult || browseErr || back.length > 0}
      <div class="border-t border-wp-border pt-3">
        <div class="flex flex-wrap items-center gap-2 mb-2 text-xs text-wp-dim">
          {#if back.length > 0}
            <button
              class="hover:text-wp-accent"
              onclick={goBack}
              title={t("pages.back_title")}>← {t("pages.back")}</button
            >
          {/if}
          {#if pageResult}
            <span class="font-mono break-all">{pageResult.path}</span>
            {#if pageResult.served_from_cache}
              <span
                class="rounded-full border border-wp-border px-2 py-0.5 {pageResult.stale
                  ? 'text-wp-danger'
                  : 'text-wp-dim'}"
              >
                {pageResult.stale
                  ? t("pages.cached_stale")
                  : t("pages.cached_ago", { ago: timeAgo(pageResult.cached_ts) })}
              </span>
            {:else}
              <span
                >{t("pages.link_stats", {
                  bytes: pageResult.bytes,
                  ms: pageResult.elapsed_ms,
                })}</span
              >
            {/if}
            <button
              class="hover:text-wp-accent"
              disabled={browsing}
              onclick={() =>
                fetchPage(browseHash, pageResult?.path ?? browsePath, true)}
              >{t("pages.refresh")}</button
            >
          {/if}
        </div>
        {#if pageResult}
          <div class="micron bg-wp-bg rounded-lg p-4 text-sm" use:readerLinks>
            {@html renderMicron(pageResult.content)}
          </div>
        {/if}
      </div>
    {/if}
  </section>

  <!-- shared files -->
  <section class="bg-wp-panel border border-wp-border rounded-xl p-4 space-y-3">
    <h2 class="text-sm font-semibold text-wp-dim uppercase tracking-wide">
      {t("pages.shared_files")}
      <Tooltip text={TOOLTIPS.shared_files} />
    </h2>
    <p class="text-xs text-wp-dim">
      {t("pages.shared_intro")}
    </p>
    <p class="text-xs text-wp-dim" role="status" aria-live="polite">
      {#if live?.shared_storage_max_bytes}
        {t("pages.shared_usage", {
          used: binarySize(live.shared_bytes ?? 0),
          limit: binarySize(live.shared_storage_max_bytes),
          count: live.shared_files ?? 0,
        })}
      {:else}
        {t("pages.shared_usage_unlimited", {
          used: binarySize(live?.shared_bytes ?? 0),
          count: live?.shared_files ?? 0,
        })}
      {/if}
    </p>

    <div class="flex flex-wrap items-center gap-3">
      <label
        class="bg-wp-bg border border-wp-border rounded-lg px-3 py-1.5 text-sm cursor-pointer hover:border-wp-accent"
      >
        ＋ {t("pages.share_file")}
        <input
          type="file"
          class="hidden"
          onchange={(e) => {
            const f = e.currentTarget.files?.[0];
            if (f) uploadShared(f);
            e.currentTarget.value = "";
          }}
        />
      </label>
      {#if $nodeInfo}
        <button
          class="text-xs text-wp-dim hover:text-wp-accent"
          onclick={() =>
            copyText(`${$nodeInfo.node_hash} — /file/<name>`)}
          >{t("pages.copy_node_address")}</button
        >
      {/if}
    </div>

    {#if shared.length === 0}
      <p class="text-xs text-wp-dim">{t("pages.nothing_shared")}</p>
    {:else}
      <ul class="space-y-1">
        {#each shared as f (f.name)}
          <li class="flex items-center gap-3 text-sm">
            <span class="flex-1 text-wp-text">{f.name}</span>
            <span class="text-xs text-wp-dim">{humanSize(f.size)}</span>
            <button
              class="text-xs text-wp-dim hover:text-wp-accent"
              onclick={() => downloadBlob(`/api/v1/shared/${encodeURIComponent(f.name)}`, f.name)}
              >{t("pages.download")}</button
            >
            <button
              class="text-wp-dim hover:text-wp-danger text-xs"
              aria-label={t("pages.stop_sharing_aria", { name: f.name })}
              title={t("pages.stop_sharing")}
              onclick={() => unshare(f.name)}>✕</button
            >
          </li>
        {/each}
      </ul>
    {/if}

    <div class="border-t border-wp-border pt-3 space-y-2">
      <p class="text-xs text-wp-dim">{t("pages.download_from_node")}</p>
      <div class="flex flex-wrap gap-2 items-center">
        <input
          bind:value={dlNode}
          placeholder={t("common.node_address_placeholder")}
          class="flex-1 min-w-56 bg-wp-bg border border-wp-border rounded-lg px-2 py-1 text-sm font-mono"
        />
        <input
          bind:value={dlName}
          placeholder={t("common.filename_placeholder")}
          class="w-48 bg-wp-bg border border-wp-border rounded-lg px-2 py-1 text-sm font-mono"
        />
        <button
          onclick={downloadFromNode}
          disabled={fileBusy || !dlNode.trim() || !dlName.trim()}
          class="bg-wp-accent text-wp-bg text-sm font-semibold px-4 py-1.5 rounded-lg"
          >{t("pages.get_file")}</button
        >
      </div>
      {#if fileBusy && fileTransferId}
        <TransferBar transfer={$transfers[fileTransferId]} />
      {/if}
    </div>
    {#if sharedMsg}
      <p class="text-xs text-wp-dim" role="status" aria-live="polite">{sharedMsg}</p>
    {/if}
  </section>
</div>

<style>
  .micron :global(h1),
  .micron :global(.micron-h1) {
    font-size: 1.25rem;
    font-weight: 700;
    margin: 0.5rem 0;
    color: var(--color-wp-accent);
  }
  .micron :global(h2),
  .micron :global(.micron-h2) {
    font-size: 1.1rem;
    font-weight: 600;
    margin: 0.5rem 0;
    color: var(--color-wp-text);
  }
  .micron :global(h3),
  .micron :global(.micron-h3) {
    font-size: 1rem;
    font-weight: 600;
    margin: 0.4rem 0;
  }
  .micron :global(p) {
    margin: 0.3rem 0;
  }
  .micron :global(.micron-code) {
    background: rgba(255, 255, 255, 0.06);
    border: 1px solid var(--color-wp-border);
    border-radius: 0.5rem;
    padding: 0.5rem 0.75rem;
    font-family: monospace;
    font-size: 0.85rem;
    overflow-x: auto;
    margin: 0.5rem 0;
  }
  .micron :global(a) {
    color: var(--color-wp-accent);
    text-decoration: underline;
  }
  .micron :global(.micron-link) {
    cursor: pointer;
  }
  .micron :global(.micron-inline-code) {
    background: rgba(255, 255, 255, 0.08);
    border-radius: 0.25rem;
    padding: 0 0.25rem;
    font-family: monospace;
    font-size: 0.85em;
  }
  .micron :global(.micron-notice) {
    color: var(--color-wp-danger);
  }
  .micron :global(hr) {
    border-color: var(--color-wp-border);
    margin: 0.6rem 0;
  }
  .micron :global(.micron-bullet) {
    padding-left: 0.5rem;
  }
</style>
