// Centralized copy: every tooltip/guide blurb lives here, keyed by area.
// Rule: no Reticulum jargon appears on screen without an explanation nearby.
// `as const` keeps keys literal so missing keys fail type-checking.

export const TOOLTIPS = {
  address:
    "Your Reticulum address. Anyone on the network can reach you with it — share it like a phone number. It never changes and belongs only to you.",
  display_name:
    "A friendly name others see next to your address. You can change it anytime; it is announced to the network.",
  announce:
    "Broadcasting your address to the network so others can find you and messages can route to you. This happens automatically, but you can trigger it manually.",
  peer_hash:
    "This person's unique address on Reticulum, derived from their cryptographic identity. It is how messages find them.",
  stamp_cost:
    "An anti-spam measure: the sender must do a small amount of computation before their message is accepted. Higher means stricter.",
  delivery_sent:
    "Your message has left your node and is crossing the network.",
  delivery_delivered:
    "The recipient's node confirmed it received your message.",
  delivery_failed:
    "The message could not be delivered right now. The peer may be offline — try again later.",
  mode_toggle:
    "Advanced mode unlocks interface configuration, network diagnostics, and infrastructure hosting. Basic mode keeps things simple.",
  autointerface:
    "Automatically finds other Reticulum users on your local network (Wi‑Fi/LAN). No configuration needed — great for testing.",
  announce_interval:
    "How often your address is re-broadcast so the network keeps a fresh path to you.",
} as const;

export const GLOSSARY = {
  identity:
    "Your cryptographic keypair in Reticulum. It proves messages are really from you. Keep a backup — losing it means losing your address.",
  transport_node:
    "A node set up to carry traffic for others. Running one strengthens the whole network.",
  propagation_node:
    "A store-and-forward server for LXMF messages. If a peer is offline, a propagation node holds their messages until they return.",
  entrypoint:
    "A publicly reachable node that helps you join the wider network over the Internet.",
} as const;
