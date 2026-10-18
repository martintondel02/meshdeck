<script lang="ts">
  import { onMount } from "svelte";
  import { api, downloadBlob, uploadFile } from "../lib/api";
  import Tooltip from "./Tooltip.svelte";
  import {
    humanSize,
    nodeInfo,
    nodes,
    pages,
    type BrowseResult,
    type NodeInfo,
    type NodeMeta,
    type PageMeta,
    type SharedFile,
  } from "../lib/stores";
  import { renderMicron } from "../lib/micron";
  import { TOOLTIPS } from "../lib/copy/tooltips";

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
      edMsg = "could not load page";
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
      edMsg = e instanceof Error ? e.message : "failed";
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
      edMsg = "saved ✓ — the page is live immediately";
      pages.set(await api<PageMeta[]>("/api/v1/pages"));
    } catch (e) {
      edMsg = e instanceof Error ? e.message : "save failed";
    }
  }

  async function removePage(name: string) {
    if (!confirm(`Delete page ${name}?`)) return;
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
        ? "announced ✓ — other nodes can find your pages"
        : "saved (serving off)";
    } catch (e) {
      hostMsg = e instanceof Error ? e.message : "announce failed";
    }
  }

  async function browse() {
    browsing = true;
    browseErr = "";
    pageResult = null;
    try {
      let path = browsePath.trim() || "/page/index.mu";
      if (!path.startsWith("/")) path = "/" + path;
      pageResult = await api<BrowseResult>(
        `/api/v1/browse/${encodeURIComponent(browseHash.trim())}${path.startsWith("/page/") ? path : "/page/" + path}`,
      );
    } catch (e) {
      browseErr = browseErrorText(e);
    } finally {
      browsing = false;
    }
  }

  function browseErrorText(e: unknown): string {
    const code = e instanceof Error ? e.message : "";
    switch (code) {
      case "no_path":
        return "no route to that node yet — it may be offline; a path request was sent, try again in a minute";
      case "link_timeout":
        return "timed out while connecting to the node";
      default:
        return code || "fetch failed";
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
      sharedMsg = "file is larger than 32 MiB";
      return;
    }
    const form = new FormData();
    form.append("file", file);
    try {
      await uploadFile("/api/v1/shared", form);
      sharedMsg = "shared ✓ — anyone with your node address can download it";
      await loadShared();
    } catch (e) {
      sharedMsg = e instanceof Error ? e.message : "upload failed";
    }
  }

  async function unshare(name: string) {
    if (!confirm(`Stop sharing ${name}?`)) return;
    await api(`/api/v1/shared/${encodeURIComponent(name)}`, { method: "DELETE" });
    await loadShared();
  }

  async function downloadFromNode() {
    sharedMsg = "";
    if (!dlNode.trim() || !dlName.trim()) return;
    try {
      await downloadBlob(
        `/api/v1/browse/${encodeURIComponent(dlNode.trim())}/file/${encodeURIComponent(dlName.trim())}`,
        dlName.trim(),
      );
      sharedMsg = "download started";
    } catch (e) {
      sharedMsg = browseErrorText(e);
    }
  }

  function copyText(text: string) {
    navigator.clipboard?.writeText(text).then(
      () => (sharedMsg = "copied to clipboard"),
      () => (sharedMsg = "could not copy"),
    );
  }

  const rendered = $derived(renderMicron(editor));
</script>

<div class="p-6 max-w-5xl mx-auto space-y-8">
  <h1 class="text-xl font-bold text-wp-text">Pages & Node</h1>
  <p class="text-wp-dim text-sm -mt-4">
    Host NomadNet-compat­ible `.mu` pages right from your node — anyone with the
    node address can browse them, no web server involved.
    <Tooltip text={TOOLTIPS.hosting_pages} />
  </p>

  <div class="grid md:grid-cols-3 gap-6">
    <!-- editor column -->
    <div class="bg-wp-panel border border-wp-border rounded-xl p-4 space-y-3">
      <h2 class="text-sm font-semibold text-wp-dim uppercase tracking-wide">
        My pages
      </h2>
      {#if $nodeInfo}
        <div class="text-xs bg-wp-bg border border-wp-border rounded-lg p-2 break-all">
          node address:
          <code class="select-all">{$nodeInfo.node_hash}</code>
        </div>
      {/if}

      <div class="flex gap-2">
        <input
          bind:value={newName}
          placeholder="page-name.mu"
          class="flex-1 bg-wp-bg border border-wp-border rounded-lg px-2 py-1 text-sm"
        />
        <button
          onclick={createPage}
          class="bg-wp-accent text-wp-bg text-sm font-semibold px-3 py-1 rounded-lg"
          >＋</button
        >
      </div>

      {#if $pages.length === 0}
        <p class="text-wp-dim text-sm">
          No pages yet — create <code>index.mu</code> to give your node a home
          page, otherwise visitors see a placeholder.
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
                title="delete"
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
          {activePage ?? "select or create a page"}
        </h2>
        {#if activePage}
          <div class="flex gap-2 items-center">
            <button
              class="text-xs text-wp-dim hover:text-wp-text"
              onclick={() => (showPreview = !showPreview)}
              >{showPreview ? "edit" : "preview"}</button
            >
            <button
              onclick={savePage}
              class="bg-wp-accent text-wp-bg text-sm font-semibold px-3 py-1 rounded-lg"
              disabled={!dirty}>Save</button
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
            placeholder=">My first page&#10;&#10;Write in micron markup. Quick guide: > heading, - rule, • bullets, `*bold`*, _underline_, [label`link]…"
          ></textarea>
        {/if}
      {/if}
      {#if edMsg}
        <p class="text-xs text-wp-dim">{edMsg}</p>
      {/if}
    </div>
  </div>

  <!-- hosting toggle -->
  <section class="bg-wp-panel border border-wp-border rounded-xl p-4 space-y-3">
    <h2 class="text-sm font-semibold text-wp-dim uppercase tracking-wide">
      Host my node
      <Tooltip text={TOOLTIPS.hosting_pages} />
    </h2>
    <div class="flex flex-wrap items-center gap-3">
      <label class="text-sm text-wp-text">
        Node name:
        <input
          bind:value={nodeName}
          placeholder="My MeshDeck Node"
          class="ml-2 bg-wp-bg border border-wp-border rounded-lg px-2 py-1 text-sm"
        />
      </label>
      <label class="flex items-center gap-2 text-sm text-wp-text">
        <input type="checkbox" bind:checked={serve} />
        Announce my node to the network
        <Tooltip text={TOOLTIPS.node_announce} />
      </label>
      <button
        onclick={publish}
        class="bg-wp-accent text-wp-bg text-sm font-semibold px-4 py-1.5 rounded-lg"
        >Apply & announce</button
      >
      {#if hostMsg}<span class="text-xs text-wp-dim">{hostMsg}</span>{/if}
    </div>
  </section>

  <!-- browser -->
  <section class="bg-wp-panel border border-wp-border rounded-xl p-4 space-y-3">
    <h2 class="text-sm font-semibold text-wp-dim uppercase tracking-wide">
      Browse other nodes
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
        No nodes discovered yet — discovered nodes appear here automatically
        after they announce.
      </p>
    {/if}

    <div class="flex flex-wrap gap-2 items-center">
      <input
        bind:value={browseHash}
        placeholder="node address (hash)"
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
        >{browsing ? "fetching…" : "Open"}</button
      >
    </div>
    {#if browseErr}
      <p class="text-xs text-wp-danger">{browseErr}</p>
    {/if}

    {#if pageResult}
      <div class="border-t border-wp-border pt-3">
        <p class="text-xs text-wp-dim mb-2">
          {pageResult.path} — {pageResult.bytes} bytes, {pageResult.elapsed_ms}
          ms via on-network link
        </p>
        <div class="micron bg-wp-bg rounded-lg p-4 text-sm">
          {@html renderMicron(pageResult.content)}
        </div>
      </div>
    {/if}
  </section>

  <!-- shared files -->
  <section class="bg-wp-panel border border-wp-border rounded-xl p-4 space-y-3">
    <h2 class="text-sm font-semibold text-wp-dim uppercase tracking-wide">
      Shared files
      <Tooltip text={TOOLTIPS.shared_files} />
    </h2>
    <p class="text-xs text-wp-dim">
      Host files on your node (up to 32 MiB each) — anyone who knows your node
      address can download them, no chat message needed.
    </p>

    <div class="flex flex-wrap items-center gap-3">
      <label
        class="bg-wp-bg border border-wp-border rounded-lg px-3 py-1.5 text-sm cursor-pointer hover:border-wp-accent"
      >
        ＋ Share a file
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
          >copy node address</button
        >
      {/if}
    </div>

    {#if shared.length === 0}
      <p class="text-xs text-wp-dim">Nothing shared yet.</p>
    {:else}
      <ul class="space-y-1">
        {#each shared as f (f.name)}
          <li class="flex items-center gap-3 text-sm">
            <span class="flex-1 text-wp-text">{f.name}</span>
            <span class="text-xs text-wp-dim">{humanSize(f.size)}</span>
            <button
              class="text-xs text-wp-dim hover:text-wp-accent"
              onclick={() => downloadBlob(`/api/v1/shared/${encodeURIComponent(f.name)}`, f.name)}
              >download</button
            >
            <button
              class="text-wp-dim hover:text-wp-danger text-xs"
              title="stop sharing"
              onclick={() => unshare(f.name)}>✕</button
            >
          </li>
        {/each}
      </ul>
    {/if}

    <div class="border-t border-wp-border pt-3 space-y-2">
      <p class="text-xs text-wp-dim">Download from another node:</p>
      <div class="flex flex-wrap gap-2 items-center">
        <input
          bind:value={dlNode}
          placeholder="node address (hash)"
          class="flex-1 min-w-56 bg-wp-bg border border-wp-border rounded-lg px-2 py-1 text-sm font-mono"
        />
        <input
          bind:value={dlName}
          placeholder="filename.bin"
          class="w-48 bg-wp-bg border border-wp-border rounded-lg px-2 py-1 text-sm font-mono"
        />
        <button
          onclick={downloadFromNode}
          disabled={!dlNode.trim() || !dlName.trim()}
          class="bg-wp-accent text-wp-bg text-sm font-semibold px-4 py-1.5 rounded-lg"
          >Get file</button
        >
      </div>
    </div>
    {#if sharedMsg}
      <p class="text-xs text-wp-dim">{sharedMsg}</p>
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
  .micron :global(hr) {
    border-color: var(--color-wp-border);
    margin: 0.6rem 0;
  }
  .micron :global(.micron-bullet) {
    padding-left: 0.5rem;
  }
</style>
