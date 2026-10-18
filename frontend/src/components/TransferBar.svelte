<script lang="ts">
  import type { Transfer } from "../lib/stores";
  import { t } from "../lib/i18n";

  let { transfer }: { transfer: Transfer | undefined } = $props();

  const pct = $derived(Math.round((transfer?.progress ?? 0) * 100));
  const label = $derived(
    transfer?.done
      ? t("common.transfer_complete")
      : t("common.downloading_percent", { percent: pct }),
  );
</script>

{#if transfer}
  <div class="w-full" role="status" aria-live="polite">
    <div class="h-1.5 w-full overflow-hidden rounded bg-wp-panel2">
      <div
        class="h-1.5 bg-wp-accent transition-[width] duration-150"
        style={`width:${pct}%`}
      ></div>
    </div>
    <p class="mt-1 text-xs text-wp-dim">{label}</p>
  </div>
{/if}
