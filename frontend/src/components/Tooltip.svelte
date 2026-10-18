<script lang="ts">
  let { text, topic }: { text: string; topic?: string } = $props();
</script>

<span class="relative inline-block group cursor-help align-middle select-none">
  <span
    class="inline-flex items-center justify-center w-4 h-4 ml-1 text-[10px] rounded-full
           border border-wp-dim/40 text-wp-dim hover:text-wp-accent hover:border-wp-accent transition-colors"
    >?</span
  >
  <span
    class="invisible opacity-0 group-hover:visible group-hover:opacity-100 transition-all
           absolute z-50 left-1/2 -translate-x-1/2 bottom-6 w-64 p-2.5 rounded-lg
           bg-wp-panel2 border border-wp-border text-xs text-wp-text shadow-xl leading-relaxed"
  >
    {#if topic}<span class="block mb-1 font-semibold text-wp-accent">{topic}</span>{/if}
    {text}
  </span>
</span>
