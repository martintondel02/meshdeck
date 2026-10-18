<script module lang="ts">
  // One id per tooltip instance; ids stay stable for the component's lifetime.
  let tipCounter = 0;
</script>

<script lang="ts">
  let { text, topic }: { text: string; topic?: string } = $props();
  const tipId = `tooltip-${++tipCounter}`;
</script>

<span class="relative inline-block group align-middle select-none">
  <!-- Keyboard users can focus the "?" marker to read the help text; the
       tooltip shows on hover and on focus-within, not hover only. It stays a
       non-labelable <span> (not a <button>) because callers place it inside
       <label> elements, where a nested button would be invalid HTML. -->
  <span
    class="inline-flex items-center justify-center w-4 h-4 ml-1 text-[10px] rounded-full
           border border-wp-dim/40 text-wp-dim hover:text-wp-accent hover:border-wp-accent
           focus-visible:text-wp-accent focus-visible:border-wp-accent transition-colors
           cursor-help"
    role="button"
    aria-label={topic ? `Help: ${topic}` : "Help"}
    aria-describedby={tipId}
    tabindex="0">?</span
  >
  <span
    id={tipId}
    role="tooltip"
    class="invisible opacity-0 group-hover:visible group-hover:opacity-100
           group-focus-within:visible group-focus-within:opacity-100 transition-all
           absolute z-50 left-1/2 -translate-x-1/2 bottom-6 w-64 p-2.5 rounded-lg
           bg-wp-panel2 border border-wp-border text-xs text-wp-text shadow-xl leading-relaxed"
  >
    {#if topic}<span class="block mb-1 font-semibold text-wp-accent">{topic}</span>{/if}
    {text}
  </span>
</span>
