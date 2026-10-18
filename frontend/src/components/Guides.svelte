<script lang="ts">
  import Tooltip from "./Tooltip.svelte";
  import { TOOLTIPS, GLOSSARY } from "../lib/copy/tooltips";
  import { t, tList } from "../lib/i18n";

  // Section ids index into `guides.sections` in lib/i18n/en.ts. Titles are
  // single keys; bodies are paragraph lists read with tList().
  const SECTIONS = [
    "getting_started",
    "messaging",
    "sending_files",
    "adding_someone",
    "peer_offline",
    "hosting_for_others",
    "hosting_pages",
    "browsing_nodes",
  ];
</script>

<div class="h-full overflow-y-auto p-6 max-w-2xl">
  <h1 class="text-xl font-bold mb-1">{t("guides.title")}</h1>
  <p class="text-sm text-wp-dim mb-6">{t("guides.subtitle")}</p>

  {#each SECTIONS as id (id)}
    <section class="bg-wp-panel border border-wp-border rounded-xl p-5 mb-4">
      <h2 class="font-semibold mb-2">{t(`guides.sections.${id}.title`)}</h2>
      {#each tList(`guides.sections.${id}.body`) as para}
        <p class="text-sm text-wp-dim leading-relaxed mb-2 last:mb-0">{para}</p>
      {/each}
    </section>
  {/each}

  <section class="bg-wp-panel border border-wp-border rounded-xl p-5 mb-4">
    <h2 class="font-semibold mb-2">{t("guides.glossary")}</h2>
    <dl class="text-sm space-y-2">
      {#each Object.entries(GLOSSARY) as [term, def] (term)}
        <div>
          <dt class="font-medium capitalize">{term.replace("_", " ")}</dt>
          <dd class="text-wp-dim">{def}</dd>
        </div>
      {/each}
      <div>
        <dt class="font-medium">
          {t("guides.announce_term")} <Tooltip text={TOOLTIPS.announce} />
        </dt>
        <dd class="text-wp-dim">{TOOLTIPS.announce}</dd>
      </div>
    </dl>
  </section>

  <p class="text-xs text-wp-dim mt-6">
    {t("guides.manuals")} <a class="text-wp-accent hover:underline" href="https://reticulum.network/manual/" target="_blank" rel="noreferrer">Reticulum manual</a>
    · <a class="text-wp-accent hover:underline" href="https://github.com/markqvist/LXMF" target="_blank" rel="noreferrer">LXMF</a>
  </p>
</div>
