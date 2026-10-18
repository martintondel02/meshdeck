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
        "MeshDeck creates a Reticulum identity for you on first start. Your 32-character address (Settings → Your address) is what friends use to reach you — it never changes, even if your network does.",
        "Tell friends your address. When they announce, they appear in your Peers list automatically and stay there forever.",
        "If you both run MeshDeck (or MeshChat, or Sideband) on the same local network, discovery is automatic thanks to the LAN interface.",
      ],
    },
    {
      title: "Messaging",
      body: [
        "Type and press Enter. The tick icons tell you the delivery state: … = sending, ✓ = left your node, ✓✓ = the peer's node confirmed delivery, ✗ = failed.",
        "Nothing routes through MeshDeck servers. Your message travels via whatever Reticulum interfaces are available on both sides — LAN, internet entrypoints, LoRa, anything.",
      ],
    },
    {
      title: "Sending files",
      body: [
        "Open a chat and press the 📎 paperclip. Files up to about 1.5 MB (per message) travel inside the LXMF message itself — encrypted and signed exactly like chat text.",
        "Delivery may take a little longer than plain text, and the tick icons work the same way.",
        "Received files appear as download chips inside the bubble. MeshDeck stores them in its data directory under files/<peer>/<message>/.",
      ],
    },
    {
      title: "Adding someone directly",
      body: [
        "If you know a friend's address, press ＋ in the Peers panel and paste it. MeshDeck asks the network for a path to them.",
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
      title: "Hosting for others",
      body: [
        "A propagation node is a store-and-forward relay: senders hand it messages for people who are offline, and it holds them until the recipient reconnects and collects them. Hosting one turns your node into infrastructure other people rely on.",
        "Advanced mode → Settings → Host for others, then switch the propagation-node toggle on. It takes effect immediately, no restart. The propagation node address shown right there is the one to share.",
        "That address is not your chat address. Both are 32-character hashes made from the same identity, so they look almost identical — share the one labelled propagation node address. It is stable: turning hosting on or off, restarting, or changing networks never changes it.",
        "What it costs you: disk for the message store (no size cap by default; uncollected messages expire after 30 days), bandwidth whenever a peer syncs, and simply keeping the machine online and reachable. Messages are encrypted to the recipient, so you store data you cannot read — but you can see which address a message is for, when it arrived, and how big it is. Only host on a machine you control.",
        "Others use your node by pasting your propagation address into their Message delivery settings and choosing Propagated (or Opportunistic) delivery. Switching hosting off does not delete messages already stored — they stay on disk until you remove them yourself from lxmf/messagestore in the data directory.",
      ],
    },
    {
      title: "Hosting pages",
      body: [
        "MeshDeck can host NomadNet-compatible pages right from your node — think a tiny encrypted web-site that needs no server, no DNS, and works over any transport Reticulum supports.",
        "Pages tab → create index.mu, write in micron markup (> heading, `*bold`*, • bullets, [label`/page/other.mu] links). Pages are live the moment you save.",
        "Switch on Announce my node to make your node discoverable, or share the node address directly with friends.",
      ],
    },
    {
      title: "Browsing nodes",
      body: [
        "In Pages → Browse other nodes, discovered nodes appear as chips. Or paste any node address and press Open — the page comes over an encrypted, resumable link.",
        "Anything another NomadNet or Sideband node hosts, MeshDeck can browse. Everything MeshDeck hosts, they can browse too.",
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
