<script lang="ts">
  import { onMount } from "svelte";
  import { api } from "../lib/api";
  import { identity } from "../lib/stores";
  import Tooltip from "./Tooltip.svelte";
  import { TOOLTIPS } from "../lib/copy/tooltips";
  import { t } from "../lib/i18n";

  let { onDone }: { onDone: () => void } = $props();

  let name = $state("");
  let busy = $state(false);
  let error = $state("");
  let panel: HTMLDivElement | undefined = $state();
  let nameField: HTMLInputElement | undefined = $state();

  const FOCUSABLE =
    'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

  onMount(() => {
    nameField?.focus();
  });

  // First run has no underlying UI to return to, so Escape only moves focus
  // back to the display-name field instead of dismissing setup.
  function onKeydown(e: KeyboardEvent) {
    if (e.key === "Escape") {
      e.preventDefault();
      nameField?.focus();
      return;
    }
    if (e.key !== "Tab" || !panel) return;
    const items = Array.from(panel.querySelectorAll<HTMLElement>(FOCUSABLE)).filter(
      (el) => el.offsetWidth > 0 || el.offsetHeight > 0,
    );
    if (items.length === 0) return;
    const first = items[0];
    const last = items[items.length - 1];
    if (!first || !last) return;
    if (e.shiftKey && document.activeElement === first) {
      e.preventDefault();
      last.focus();
    } else if (!e.shiftKey && document.activeElement === last) {
      e.preventDefault();
      first.focus();
    }
  }

  async function start() {
    error = "";
    busy = true;
    try {
      const info = await api<typeof $identity>("/api/v1/identity/display_name", {
        method: "POST",
        body: JSON.stringify({
          display_name: name.trim() || t("onboarding.default_name"),
        }),
      });
      identity.set(info);
      onDone();
    } catch (e) {
      error = e instanceof Error ? e.message : t("common.failed");
    } finally {
      busy = false;
    }
  }
</script>

<div class="min-h-screen flex items-center justify-center p-6">
  <div
    bind:this={panel}
    role="dialog"
    aria-modal="true"
    aria-labelledby="onboarding-title"
    aria-describedby="onboarding-intro"
    tabindex="-1"
    class="w-full max-w-md bg-wp-panel border border-wp-border rounded-2xl p-8 shadow-2xl"
    onkeydown={onKeydown}
  >
    <div class="text-3xl mb-1" aria-hidden="true">🧭</div>
    <h1 id="onboarding-title" class="text-2xl font-bold mb-2">{t("onboarding.title")}</h1>
    <p id="onboarding-intro" class="text-wp-dim text-sm mb-6 leading-relaxed">
      {t("onboarding.intro")}
    </p>

    <div class="flex items-center mb-1.5">
      <label for="onboarding-name" class="text-sm font-medium">
        {t("onboarding.name_label")}
      </label>
      <Tooltip text={TOOLTIPS.display_name} />
    </div>
    <input
      id="onboarding-name"
      bind:this={nameField}
      bind:value={name}
      onkeydown={(e) => e.key === "Enter" && start()}
      placeholder={t("onboarding.name_placeholder")}
      autocomplete="nickname"
      class="w-full bg-wp-bg border border-wp-border rounded-lg px-3 py-2.5 mb-4
             focus:outline-none focus:border-wp-accent transition-colors"
      maxlength="64"
    />

    <div class="sr-only" role="status" aria-live="polite">{error}</div>
    {#if error}
      <p class="text-wp-danger text-sm mb-3">{error}</p>
    {/if}

    <button
      onclick={start}
      disabled={busy}
      aria-busy={busy}
      class="w-full bg-wp-accent text-wp-bg font-semibold rounded-lg py-2.5
             hover:brightness-110 active:scale-[0.99] transition disabled:opacity-50"
    >
      {busy ? t("onboarding.busy") : t("onboarding.submit")}
    </button>

    <p class="text-xs text-wp-dim mt-4 leading-relaxed">
      {t("onboarding.footnote")}
      <Tooltip text={TOOLTIPS.address} />
    </p>
  </div>
</div>
