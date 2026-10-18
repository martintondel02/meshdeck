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
  no_path_error:
    "We don't know a network path to this peer yet. This usually fixes itself within a minute once they announce — keep both nodes online and try again.",
  add_peer:
    "Paste a friend's address (their 32-character hash, from their Me page) to add them even if they haven't announced yet. We'll ask the network for a path.",
  delivery_method_label:
    "Direct sends straight to the peer when they're online. Opportunistic tries direct, then falls back to a propagation node. Propagated always uses the propagation node (offline-capable, slower).",
  propagation_node_hash:
    "The hash of an LXMF propagation node that stores messages for offline peers. Ask the node's operator how to reach it, then paste its hash here.",
  attachments:
    "Files ride inside the LXMF message itself — encrypted and signed like chat text. Large files take a while; the message shows delivery status just like chat.",
  hosting_entrypoint:
    "Serving on 0.0.0.0 accepts connections from anywhere the machine is reachable. You must forward/open the port in your firewall or router. Public interfaces get announce-rate limits automatically (see the Reticulum manual).",
  gateway_mode:
    "Gateway interfaces greatly improve convergence for clients connecting through them — recommended for public entrypoints.",
  share_entrypoint:
    "Give friends this snippet so they can add your node as a client interface (or via Paste config snippet).",
  transport_node_setting:
    "A transport node forwards traffic for others, strengthening the mesh. Only enable on machines that stay online and are well connected.",
  stamp_sending:
    "This peer requires anti-spam proof-of-work (a stamp). Your message is generated automatically — the checkmark just takes a few extra seconds.",
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
