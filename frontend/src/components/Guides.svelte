<script lang="ts">
  import Tooltip from "./Tooltip.svelte";
  import { TOOLTIPS, GLOSSARY } from "../lib/copy/tooltips";

  interface GuideSection {
    title: string;
    body: string[];
  }

  const SECTIONS: GuideSection[] = [
    {
      title: "Getting started",
      body: [
        "Waypoint creates a Reticulum identity for you on first start. Your 32-character address (Settings → Your address) is what friends use to reach you — it never changes, even if your network does.",
        "Tell friends your address. When they announce, they appear in your Peers list automatically and stay there forever.",
        "If you both run Waypoint (or MeshChat, or Sideband) on the same local network, discovery is automatic thanks to the LAN interface.",
      ],
    },
    {
      title: "Messaging",
      body: [
        "Type and press Enter. The tick icons tell you the delivery state: … = sending, ✓ = left your node, ✓✓ = the peer's node confirmed delivery, ✗ = failed.",
        "Nothing routes through Waypoint servers. Your message travels via whatever Reticulum interfaces are available on both sides — LAN, internet entrypoints, LoRa, anything.",
      ],
    },
    {
      title: "Sending files",
      body: [
        "Open a chat and press the 📎 paperclip. Files up to about 1.5 MB (per message) travel inside the LXMF message itself — encrypted and signed exactly like chat text.",
        "Delivery may take a little longer than plain text, and the tick icons work the same way.",
        "Received files appear as download chips inside the bubble. Waypoint stores them in its data directory under files/<peer>/<message>/.",
      ],
    },
    {
      title: "Adding someone directly",
      body: [
        "If you know a friend's address, press ＋ in the Peers panel and paste it. Waypoint asks the network for a path to them.",
        "The first message you send might show “no path yet” — that's normal. It resolves automatically, usually within a minute, once the peer announces.",
      ],
    },
    {
      title: "When a peer is offline",
      body: [
        "Reticulum is asynchronous: if they're offline, messages can be ferried by a propagation node — a store-and-forward service run by the community.",
        "Advanced mode → Settings → Message delivery lets you set a propagation node address and switch your default delivery method.",
      ],
    },
    {
      title: "Hosting pages",
      body: [
        "Waypoint can host NomadNet-compatible pages right from your node — think a tiny encrypted web-site that needs no server, no DNS, and works over any transport Reticulum supports.",
        "Pages tab → create index.mu, write in micron markup (> heading, `*bold`*, • bullets, [label`/page/other.mu] links). Pages are live the moment you save.",
        "Switch on Announce my node to make your node discoverable, or share the node address directly with friends.",
      ],
    },
    {
      title: "Browsing nodes",
      body: [
        "In Pages → Browse other nodes, discovered nodes appear as chips. Or paste any node address and press Open — the page comes over an encrypted, resumable link.",
        "Anything another NomadNet or Sideband node hosts, Waypoint can browse. Everything Waypoint hosts, they can browse too.",
      ],
    },
  ];
</script>

<div class="h-full overflow-y-auto p-6 max-w-2xl">
  <h1 class="text-xl font-bold mb-1">Guides</h1>
  <p class="text-sm text-wp-dim mb-6">Built-in help. No internet required.</p>

  {#each SECTIONS as section (section.title)}
    <section class="bg-wp-panel border border-wp-border rounded-xl p-5 mb-4">
      <h2 class="font-semibold mb-2">{section.title}</h2>
      {#each section.body as para}
        <p class="text-sm text-wp-dim leading-relaxed mb-2 last:mb-0">{para}</p>
      {/each}
    </section>
  {/each}

  <section class="bg-wp-panel border border-wp-border rounded-xl p-5 mb-4">
    <h2 class="font-semibold mb-2">Glossary</h2>
    <dl class="text-sm space-y-2">
      {#each Object.entries(GLOSSARY) as [term, def] (term)}
        <div>
          <dt class="font-medium capitalize">{term.replace("_", " ")}</dt>
          <dd class="text-wp-dim">{def}</dd>
        </div>
      {/each}
      <div>
        <dt class="font-medium">
          Announce <Tooltip text={TOOLTIPS.announce} />
        </dt>
        <dd class="text-wp-dim">{TOOLTIPS.announce}</dd>
      </div>
    </dl>
  </section>

  <p class="text-xs text-wp-dim mt-6">
    Full manuals: <a class="text-wp-accent hover:underline" href="https://reticulum.network/manual/" target="_blank" rel="noreferrer">Reticulum manual</a>
    · <a class="text-wp-accent hover:underline" href="https://github.com/markqvist/LXMF" target="_blank" rel="noreferrer">LXMF</a>
  </p>
</div>
