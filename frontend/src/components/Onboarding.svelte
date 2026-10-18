<script lang="ts">
  import { api } from "../lib/api";
  import { identity } from "../lib/stores";
  import Tooltip from "./Tooltip.svelte";
  import { TOOLTIPS } from "../lib/copy/tooltips";

  let { onDone }: { onDone: () => void } = $props();

  let name = $state("");
  let busy = $state(false);
  let error = $state("");

  async function start() {
    error = "";
    busy = true;
    try {
      const info = await api<typeof $identity>("/api/v1/identity/display_name", {
        method: "POST",
        body: JSON.stringify({ display_name: name.trim() || "Wanderer" }),
      });
      identity.set(info);
      onDone();
    } catch (e) {
      error = e instanceof Error ? e.message : "failed";
    } finally {
      busy = false;
    }
  }
</script>

<div class="min-h-screen flex items-center justify-center p-6">
  <div class="w-full max-w-md bg-wp-panel border border-wp-border rounded-2xl p-8 shadow-2xl">
    <div class="text-3xl mb-1">🧭</div>
    <h1 class="text-2xl font-bold mb-2">Welcome to MeshDeck</h1>
    <p class="text-wp-dim text-sm mb-6 leading-relaxed">
      MeshDeck runs your own node on the Reticulum network — fully encrypted,
      decentralized, and owned by you. Let's set you up in two seconds.
    </p>

    <label class="block text-sm font-medium mb-1.5">
      What should others call you?
      <Tooltip text={TOOLTIPS.display_name} />
    </label>
    <input
      bind:value={name}
      onkeydown={(e) => e.key === "Enter" && start()}
      placeholder="e.g. Ada"
      class="w-full bg-wp-bg border border-wp-border rounded-lg px-3 py-2.5 mb-4
             focus:outline-none focus:border-wp-accent transition-colors"
      maxlength="64"
    />

    {#if error}
      <p class="text-wp-danger text-sm mb-3">{error}</p>
    {/if}

    <button
      onclick={start}
      disabled={busy}
      class="w-full bg-wp-accent text-wp-bg font-semibold rounded-lg py-2.5
             hover:brightness-110 active:scale-[0.99] transition disabled:opacity-50"
    >
      {busy ? "Creating your identity…" : "Enter the network"}
    </button>

    <p class="text-xs text-wp-dim mt-4 leading-relaxed">
      A cryptographic identity is created for you automatically — no accounts, no
      phone numbers, no servers to sign up for.
      <Tooltip text={TOOLTIPS.address} />
    </p>
  </div>
</div>
