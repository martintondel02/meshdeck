// Every user-facing string in the app lives here. Nothing else may inline UI
// copy — see docs/i18n.md for the rule, key naming, plurals and fallback.
//
// Key naming: <area>.<thing>[_<variant>]. Placeholders use {braces} and are
// filled by `t(key, vars)`. Plurals use explicit `_one` / `_other` keys.
// Symbols/glyphs that carry meaning inside markup (＋, ←, ⚠, 📎) stay in the
// components; words stay here.

export const en = {
  common: {
    nav_chats: "Chats",
    nav_pages: "Pages",
    nav_guides: "Guides",
    nav_settings: "Settings",
    main_sections: "Main sections",
    starting: "Starting…",
    connected_daemon: "Connected to the MeshDeck daemon.",
    daemon_lost: "Daemon connection lost — reconnecting.",
    daemon_connected_title: "connected to daemon",
    daemon_lost_title: "daemon connection lost — retrying",
    boot_no_token:
      "No API token found. Start MeshDeck from the terminal and open the full URL it prints (it contains ?token=…).",
    boot_bad_token:
      "The daemon rejected the token. Re-open the exact URL MeshDeck printed.",
    boot_unreachable: "Could not reach the MeshDeck daemon. Is it running?",
    unread_messages_one: "{count} unread message",
    unread_messages_other: "{count} unread messages",
    help: "Help",
    help_topic: "Help: {topic}",
    copy: "Copy",
    copied: "Copied!",
    save: "Save",
    delete: "delete",
    failed: "failed",
    hash_placeholder: "32-character hash…",
    node_address_placeholder: "node address (hash)",
    filename_placeholder: "filename.bin",
    page_name_placeholder: "page-name.mu",
    transfer_complete: "transfer complete",
    downloading_percent: "downloading… {percent}%",
    seen_recently: "seen recently",
    not_seen_recently: "not seen recently",
    never: "never",
    just_now: "just now",
    minutes_ago: "{count}m ago",
    hours_ago: "{count}h ago",
    days_ago: "{count}d ago",
  },

  chats: {
    peers_title: "Peers",
    row_label: "Open chat with {peer} ({seen})",
    row_label_unread: "Open chat with {peer} ({seen}), {count} unread",
    add_peer_aria: "Add a peer by address",
    add_peer_title: "Add peer by address",
    add_by_address: "Add by address",
    add_hash_aria: "Peer address, 32-character hexadecimal hash",
    add_peer_submit: "Add peer",
    add_ok_known: "Added — you can message them right away.",
    add_ok_pending:
      "Added. We asked the network for a path; you're set once they announce (usually within a minute).",
    add_invalid:
      "Not a valid address. It should be a 32-character hexadecimal hash.",
    no_peers: "No peers discovered yet.",
    no_peers_body_before: "MeshDeck finds people automatically when they",
    no_peers_body_announce: "announce",
    no_peers_body_after:
      "themselves. Share your address (top bar) with a friend running MeshDeck, MeshChat, or Sideband to get started — or press ＋ to add someone directly.",
    nickname_aria: "Nickname for {peer}",
    nickname_placeholder: "Nickname…",
    options_aria: "Options for {peer}",
    options_title: "Peer options",
    rename: "Rename…",
    block: "Block",
    stamp_suffix: "· stamp {cost}",
    empty_first: "Select a peer to start chatting,",
    empty_second:
      "or share your address and wait for someone to say hi.",
    stamp_badge: "stamp {cost}",
    search_aria: "Search message history",
    search_placeholder: "Search history…",
    matches_one: "{count} match",
    matches_other: "{count} matches",
    download_title: "Download {name}",
    download_attachment: "Download attachment:",
    attachment_pruned: "attachment no longer stored",
    state_sending: "sending",
    state_sent: "sent",
    state_delivered: "delivered",
    state_failed: "failed to send",
    error_too_large:
      "This file is too large for the current transfer limit.",
    error_no_propagation_node:
      "Propagation delivery selected, but no propagation node is configured (Advanced→Settings).",
    error_generic: "Message failed before it could be sent.",
    error_not_connected: "Not connected to the MeshDeck daemon.",
    error_file_too_large:
      "“{name}” is {size} — the current limit is {limit}.",
    attaching: "Sending attachment…",
    attach_aria: "Attach a file (up to {limit})",
    attach_title: "Send a file (up to {limit})",
    message_aria: "Message text (Enter to send)",
    message_placeholder: "Type a message… (or attach a file)",
    send: "Send",
  },

  pages: {
    title: "Pages & Node",
    subtitle:
      "Host NomadNet-compat­ible `.mu` pages right from your node — anyone with the node address can browse them, no web server involved.",
    my_pages: "My pages",
    node_address: "node address:",
    create_page: "Create page",
    no_pages_before: "No pages yet — create",
    no_pages_after:
      "to give your node a home page, otherwise visitors see a placeholder.",
    delete_page_aria: "Delete page {name}",
    select_or_create: "select or create a page",
    edit: "edit",
    preview: "preview",
    editor_placeholder:
      ">My first page\n\nWrite in micron markup. Quick guide: > heading, - rule, • bullets, `*bold`*, _underline_, [label`link]…",
    saved: "saved ✓ — the page is live immediately",
    error_load: "could not load page",
    error_save: "save failed",
    confirm_delete: "Delete page {name}?",
    host_my_node: "Host my node",
    node_name: "Node name:",
    node_name_placeholder: "My MeshDeck Node",
    announce_toggle: "Announce my node to the network",
    apply_announce: "Apply & announce",
    announced: "announced ✓ — other nodes can find your pages",
    saved_serving_off: "saved (serving off)",
    error_announce: "announce failed",
    browse_nodes: "Browse other nodes",
    no_nodes:
      "No nodes discovered yet — discovered nodes appear here automatically after they announce.",
    fetching: "fetching…",
    open: "Open",
    back: "back",
    back_title: "back to the previous page",
    cached_stale: "saved copy — node unreachable",
    cached_ago: "cached · {ago}",
    link_stats: "— {bytes} bytes, {ms} ms via on-network link",
    refresh: "Refresh",
    error_no_path:
      "no route to that node yet — it may be offline; a path request was sent, try again in a minute",
    error_timeout: "timed out while connecting to the node",
    error_fetch: "fetch failed",
    shared_files: "Shared files",
    shared_intro:
      "Host files on your node (up to 32 MiB each) — anyone who knows your node address can download them, no chat message needed.",
    share_file: "Share a file",
    copy_node_address: "copy node address",
    nothing_shared: "Nothing shared yet.",
    download: "download",
    stop_sharing: "stop sharing",
    stop_sharing_aria: "Stop sharing {name}",
    confirm_unshare: "Stop sharing {name}?",
    download_from_node: "Download from another node:",
    get_file: "Get file",
    error_file_too_big: "file is larger than 32 MiB",
    shared_ok: "shared ✓ — anyone with your node address can download it",
    error_upload: "upload failed",
    error_storage_full:
      "Storage is full for this kind of content — raise the limit in Settings → Storage or remove something.",
    shared_usage: "Shared: {used} of {limit} ({count} files)",
    shared_usage_unlimited: "Shared: {used} ({count} files, no limit)",
    my_pages_usage: "Pages: {used} of {limit} ({count} pages)",
    my_pages_usage_unlimited: "Pages: {used} ({count} pages, no limit)",
    download_started: "download started",
    copied: "copied to clipboard",
    copy_failed: "could not copy",
  },

  settings: {
    title: "Settings",
    your_address: "Your address",
    share_hint: "Share this with people you want to talk to.",
    copy_aria: "Copy your chat address",
    signed_in_as: "Signed in as",
    unnamed: "(unnamed)",
    mode: "Mode",
    mode_basic_name: "Basic",
    mode_advanced_name: "Advanced",
    mode_basic_hint: "Basic mode is on: a clean, guided experience.",
    mode_advanced_hint:
      "Advanced mode is on: network controls and diagnostics unlocked.",
    switch_mode: "Switch to {mode} mode",
    network: "Network",
    connected_via_one: "Connected via {count} interface.",
    connected_via_other: "Connected via {count} interfaces.",
    rns_not_running: "Reticulum is not running.",
    announcing: "Announcing…",
    announce_now: "Announce myself now",
    reach_beyond:
      "To reach beyond your local network, enable advanced mode and use the interfaces wizard — or ask a friend for their connection snippet. Community directories:",
    interfaces: "Interfaces",
    col_name: "Name",
    col_type: "Type",
    col_state: "State",
    col_bitrate: "Bitrate",
    iface_online: "online",
    iface_offline: "offline",
    bitrate_kbps: "{kbps} kbps",
    transport_node: "Transport node",
    transport_carry: "Carry traffic for other nodes (enable_transport)",
    transport_warn:
      "Transport nodes serve the mesh; run one on stable, well-connected machines only.",
    message_delivery: "Message delivery",
    delivery_method: "Delivery method",
    delivery_direct: "Direct (fastest — peer must be online)",
    delivery_opportunistic: "Opportunistic (direct, propagation fallback)",
    delivery_propagated: "Propagated (via a propagation node)",
    delivery_updated: "Delivery method updated.",
    delivery_error: "Could not update delivery method.",
    prop_node_address: "Propagation node address",
    prop_node_saved: "Propagation node saved. A message sync was attempted.",
    prop_node_invalid: "Invalid hash — 32 hex characters expected.",
    host_section: "Host for others (propagation node)",
    host_intro:
      "Store-and-forward for LXMF: when a peer is offline, your node holds their encrypted messages until they return. This is infrastructure other people can rely on — it costs disk, bandwidth and uptime.",
    host_toggle: "Host a propagation node",
    prop_address_label:
      "Your propagation node address (share this — not your chat address):",
    copy_prop_aria: "Copy propagation node address",
    hosting_enabled: "Hosting enabled — peers can now use the address below.",
    hosting_disabled: "Hosting disabled.",
    hosting_error: "Could not change propagation hosting.",
    host_warn:
      "Keep this machine online. Messages are stored encrypted, but their timing and size are visible to you as the operator.",
    propagation_store_usage: "Store usage: {used} of {limit}",
    propagation_store_usage_unlimited: "Store usage: {used} (no limit)",
    propagation_store_not_hosting: "Not hosting — no messages are stored on disk.",
    propagation_limit_label: "Store limit (MB, 0 = unlimited)",
    propagation_limit_hint:
      "LXMF removes the oldest messages once the store is over this limit; it checks about every two minutes.",
    propagation_limit_saved: "Storage limit saved.",
    propagation_limit_invalid: "Enter a whole number from 0 to 10240.",
    prop_dashboard_title: "Operator dashboard",
    prop_dashboard_refresh: "Refresh",
    prop_dashboard_refreshed: "Dashboard refreshed.",
    prop_dashboard_failed: "Could not load propagation status.",
    prop_hosting_label: "Hosting",
    prop_store_label: "Store",
    prop_stored_label: "Stored messages",
    prop_served_label: "Served / received",
    prop_unpeered_label: "Unpeered incoming",
    prop_peers_label: "Peers",
    prop_uptime_label: "Uptime",
    prop_transfer_label: "Transfer state",
    prop_hosting_state: "Hosting: {state}",
    prop_state_on: "on",
    prop_state_off: "off",
    prop_stored_messages: "Stored messages: {count}",
    prop_served_received: "Served / received: {served} / {received}",
    prop_unpeered: "Unpeered incoming: {count}",
    prop_uptime: "Uptime: {value}",
    prop_transfer_state: "Transfer state: {state}",
    prop_peers: "Peers: {count}",
    prop_unknown: "—",
    storage_section: "Storage",
    page_cache_usage: "Page cache: {used} of {limit}",
    page_cache_usage_unlimited: "Page cache: {used} (no limit set)",
    page_cache_hint:
      "Pages you visit are cached so you can still read them when a node goes offline. The oldest pages are dropped first when the cache is full.",
    clear_cache: "Clear cache",
    cache_cleared_one: "Cache cleared — {count} page removed.",
    cache_cleared_other: "Cache cleared — {count} pages removed.",
    cache_clear_failed: "Could not clear the cache.",
    page_cache_limit_label: "Page cache limit (bytes, 0 = unlimited)",
    page_cache_limit_hint:
      "The whole cache stays under this many bytes; the oldest pages are dropped first.",
    page_cache_limit_saved: "Page-cache limit saved.",
    page_cache_limit_invalid: "Enter a whole number from 0 to 1073741824 (1 GiB).",
    attachments_usage: "Chat attachments: {used} of {limit} ({count} files)",
    attachments_usage_unlimited:
      "Chat attachments: {used} ({count} files, no limit)",
    attachment_limit_label: "Attachment storage limit (MB, 0 = unlimited)",
    attachment_retention_label:
      "Delete attachment files older than (days, 0 = keep forever)",
    attachment_retention_warn:
      "Saving a non-zero retention deletes matching attachment files now. Message rows and their metadata are kept, and their chips become “attachment no longer stored”.",
    attachments_saved:
      "Attachment limits saved — {removed} file(s) removed, {freed} freed.",
    attachments_invalid: "Enter a whole number in the shown range.",
    shared_usage: "Shared files: {used} of {limit} ({count} files)",
    shared_usage_unlimited: "Shared files: {used} ({count} files, no limit)",
    shared_limit_label: "Shared-files storage limit (MB, 0 = unlimited)",
    shared_hint:
      "Node-shared files are user content and are never deleted automatically. New uploads are refused once this limit would be exceeded.",
    shared_limit_saved: "Shared-storage limit saved.",
    shared_limit_invalid: "Enter a whole number from 0 to 102400.",
    pages_usage: "Hosted pages: {used} of {limit} ({count} pages)",
    pages_usage_unlimited: "Hosted pages: {used} ({count} pages, no limit)",
    pages_limit_label: "Hosted-pages storage limit (MB, 0 = unlimited)",
    pages_hint:
      "Hosted pages are user content and are never deleted automatically. New saves are refused once this limit would be exceeded.",
    pages_limit_saved: "Pages-storage limit saved.",
    pages_limit_invalid: "Enter a whole number from 0 to 10240.",
    messages_usage: "Message history: {count} messages",
    messages_retention_label:
      "Delete messages older than (days, 0 = keep forever)",
    messages_retention_warn:
      "Saving a non-zero retention deletes older messages now and then once a day. Peers and discovered nodes are kept. The database file is not compacted automatically.",
    messages_saved: "Retention saved — {removed} message(s) removed.",
    messages_invalid: "Enter a whole number from 0 to 3650.",
    logs_usage: "Logs: {used} of {limit}",
    logs_usage_unlimited: "Logs: {used} (no limit)",
    log_limit_label: "Log limit (MB, 0 = unlimited)",
    log_limit_hint:
      "Applied at the next start: an oversized log is renamed to .1 (one backup kept) before Reticulum starts.",
    log_limit_saved: "Log limit saved — applied at the next start.",
    log_limit_invalid: "Enter a whole number from 0 to 1024.",
    glossary: "Glossary",
    restart_required: "Restart required for connection changes.",
    footer: "MeshDeck v{version} · uptime {seconds}s",
    ifaces_empty_before:
      "No manual interfaces yet — MeshDeck is using its automatic setup (LAN discovery",
    ifaces_auto_off: "off",
    ifaces_empty_mid:
      "). Add entries below to take full control, or paste a snippet from",
    ifaces_empty_or: "or",
    iface_enabled: "enabled",
    iface_remove: "Remove",
    iface_name_placeholder: "Friendly name…",
    iface_listen_ip: "Listen IP (127.0.0.1 local, 0.0.0.0 all)",
    iface_port: "Port",
    iface_public_warn:
      "Public listener — port must be reachable through your firewall/router. Announce-rate limits will be set automatically.",
    iface_gateway: "Gateway mode",
    iface_host: "Host to connect to (e.g. mesh.example.org)",
    iface_add_client: "Connect out (TCP client)",
    iface_add_server: "Host for others (TCP server)",
    iface_add_backbone: "Public entrypoint (backbone)",
    iface_add_auto: "LAN auto-discovery",
    iface_paste: "Paste config snippet…",
    iface_paste_placeholder:
      "Paste a block like:\n[[Dublin Node]]\n  type = TCPClientInterface\n  enabled = yes\n  target_host = dublin.example\n  target_port = 4965",
    iface_import: "Import",
    iface_restarting:
      "Restarting… the page will reconnect to the daemon in a few seconds.",
    iface_invalid:
      "The wizard values are incomplete — fix the highlighted fields. (Details are in the daemon log / API error.)",
    iface_save_failed: "Couldn't save or restart. Is the daemon running?",
    iface_import_none:
      'I couldn\'t find any interface blocks in that text. Paste the whole "[[Name]] … type = …" block.',
    iface_imported_one:
      "Imported {count} interface. Press “Save & restart” to apply.",
    iface_imported_other:
      "Imported {count} interfaces. Press “Save & restart” to apply.",
    share_entrypoint_title: "Share your entrypoint",
    entrypoint_default: "Entrypoint",
    prompt_host: "Public hostname/IP friends should reach you at:",
    prompt_host_default: "mesh.example.org",
    copy_snippet: "Copy connection snippet",
    share_host_placeholder: "<your-hostname-or-ip>",
    working: "Working…",
    save_restart_net: "Save & restart networking",
    unsaved:
      "Unsaved changes — applying restarts the daemon briefly.",
  },

  guides: {
    title: "Guides",
    subtitle: "Built-in help. No internet required.",
    glossary: "Glossary",
    announce_term: "Announce",
    manuals: "Full manuals:",
    sections: {
      getting_started: {
        title: "Getting started",
        body: [
          "MeshDeck creates a Reticulum identity for you on first start. Your 32-character address (Settings → Your address) is what friends use to reach you — it never changes, even if your network does.",
          "Tell friends your address. When they announce, they appear in your Peers list automatically and stay there forever.",
          "If you both run MeshDeck (or MeshChat, or Sideband) on the same local network, discovery is automatic thanks to the LAN interface.",
        ],
      },
      messaging: {
        title: "Messaging",
        body: [
          "Type and press Enter. The tick icons tell you the delivery state: … = sending, ✓ = left your node, ✓✓ = the peer's node confirmed delivery, ✗ = failed.",
          "Nothing routes through MeshDeck servers. Your message travels via whatever Reticulum interfaces are available on both sides — LAN, internet entrypoints, LoRa, anything.",
        ],
      },
      sending_files: {
        title: "Sending files",
        body: [
          "Open a chat and press the 📎 paperclip. Files up to about 1.5 MB (per message) travel inside the LXMF message itself — encrypted and signed exactly like chat text.",
          "Delivery may take a little longer than plain text, and the tick icons work the same way.",
          "Received files appear as download chips inside the bubble. MeshDeck stores them in its data directory under files/<peer>/<message>/.",
        ],
      },
      adding_someone: {
        title: "Adding someone directly",
        body: [
          "If you know a friend's address, press ＋ in the Peers panel and paste it. MeshDeck asks the network for a path to them.",
          "The first message you send might show “no path yet” — that's normal. It resolves automatically, usually within a minute, once the peer announces.",
        ],
      },
      peer_offline: {
        title: "When a peer is offline",
        body: [
          "Reticulum is asynchronous: if they're offline, messages can be ferried by a propagation node — a store-and-forward service run by the community.",
          "Advanced mode → Settings → Message delivery lets you set a propagation node address and switch your default delivery method.",
        ],
      },
      hosting_for_others: {
        title: "Hosting for others",
        body: [
          "A propagation node is a store-and-forward relay: senders hand it messages for people who are offline, and it holds them until the recipient reconnects and collects them. Hosting one turns your node into infrastructure other people rely on.",
          "Advanced mode → Settings → Host for others, then switch the propagation-node toggle on. It takes effect immediately, no restart. The propagation node address shown right there is the one to share.",
          "That address is not your chat address. Both are 32-character hashes made from the same identity, so they look almost identical — share the one labelled propagation node address. It is stable: turning hosting on or off, restarting, or changing networks never changes it.",
          "What it costs you: disk for the message store (no size cap by default; uncollected messages expire after 30 days), bandwidth whenever a peer syncs, and simply keeping the machine online and reachable. Messages are encrypted to the recipient, so you store data you cannot read — but you can see which address a message is for, when it arrived, and how big it is. Only host on a machine you control.",
          "Others use your node by pasting your propagation address into their Message delivery settings and choosing Propagated (or Opportunistic) delivery. Switching hosting off does not delete messages already stored — they stay on disk until you remove them yourself from lxmf/messagestore in the data directory.",
        ],
      },
      hosting_pages: {
        title: "Hosting pages",
        body: [
          "MeshDeck can host NomadNet-compatible pages right from your node — think a tiny encrypted web-site that needs no server, no DNS, and works over any transport Reticulum supports.",
          "Pages tab → create index.mu, write in micron markup (> heading, `*bold`*, • bullets, [label`/page/other.mu] links). Pages are live the moment you save.",
          "Switch on Announce my node to make your node discoverable, or share the node address directly with friends.",
        ],
      },
      browsing_nodes: {
        title: "Browsing nodes",
        body: [
          "In Pages → Browse other nodes, discovered nodes appear as chips. Or paste any node address and press Open — the page comes over an encrypted, resumable link.",
          "Anything another NomadNet or Sideband node hosts, MeshDeck can browse. Everything MeshDeck hosts, they can browse too.",
        ],
      },
    },
  },

  onboarding: {
    title: "Welcome to MeshDeck",
    intro:
      "MeshDeck runs your own node on the Reticulum network — fully encrypted, decentralized, and owned by you. Let's set you up in two seconds.",
    name_label: "What should others call you?",
    name_placeholder: "e.g. Ada",
    default_name: "Wanderer",
    busy: "Creating your identity…",
    submit: "Enter the network",
    footnote:
      "A cryptographic identity is created for you automatically — no accounts, no phone numbers, no servers to sign up for.",
  },

  interfaces: {
    kind_auto: "Local network (auto-discover)",
    kind_tcp_server: "TCP server (host for others)",
    kind_tcp_client: "TCP client (connect out)",
    kind_backbone_server: "Backbone gateway (public entrypoint)",
    kind_backbone_client: "Backbone client (fast connect)",
    imported_tcp_server: "Imported TCP server",
    imported_backbone_client: "Imported backbone client",
    imported_backbone_gateway: "Imported backbone gateway",
    imported_generic: "Imported {type}",
  },

  tooltips: {
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
    hosting_pages:
      'Your node can host "pages" (micron markup — think a tiny encrypted web site) directly through Reticulum. Visitors need only your node address: no DNS, no web server, works over radio links too.',
    node_announce:
      "Announcing tells the network your node exists and publishes its name. Pages are served even without announcing, but then only people who already know your address can find you.",
    node_browse:
      "Paste the address of any node that hosts pages (NomadNet node, Sideband, or another MeshDeck instance) — Open fetches its home page over an encrypted, resumable link.",
    shared_files:
      "Files hosted on your node and fetched on demand over an RNS link (NomadNet's /file scheme). Unlike chat attachments they don't ride inside messages — anyone with your node address can download them while your node is online.",
    propagation_hosting:
      "A propagation node stores and forwards LXMF messages for people who are offline. Hosting one makes your node infrastructure others can rely on — it uses disk for the message store and bandwidth when peers sync. Share the propagation address below, not your chat address.",
  },

  glossary: {
    identity:
      "Your cryptographic keypair in Reticulum. It proves messages are really from you. Keep a backup — losing it means losing your address.",
    transport_node:
      "A node set up to carry traffic for others. Running one strengthens the whole network.",
    propagation_node:
      "A store-and-forward server for LXMF messages. If a peer is offline, a propagation node holds their messages until they return.",
    entrypoint:
      "A publicly reachable node that helps you join the wider network over the Internet.",
  },
};
