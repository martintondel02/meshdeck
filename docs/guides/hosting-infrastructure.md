# Hosting a propagation node

A normal message goes straight from the sender to the recipient, and if the
recipient is offline it waits on the sender's node. A **propagation node**
changes that: senders can hand a message to it, and it holds on to the message
until the recipient comes back online and collects it.

Running one is the simplest way to make your MeshDeck node *infrastructure* —
something other people's messages depend on.

## What a propagation node actually is

It is a store-and-forward service for LXMF messages. When someone sends to an
offline peer using **propagated** delivery, the message goes into your node's
message store instead of bouncing off an unreachable destination. The recipient
syncs with your node when they next connect, downloads anything addressed to
them, and the message is deleted from your store as soon as it has been
collected.

It is not a web server: no accounts, no DNS, no ports to forward beyond what
Reticulum already uses. Your node is reached like any other Reticulum
destination, over whatever interfaces you have configured.

## Turning it on

1. Switch to **Advanced** mode (Settings → Mode).
2. Open **Settings → Host for others**.
3. Turn on the propagation-node toggle.

It applies immediately — no restart. Your node starts accepting messages and
announces itself as a propagation node, with a flag in the announce saying it is
currently accepting store-and-forward traffic.

## The address to share

Settings shows a **propagation node address** next to the toggle. That is the
address to give people, and it is *not* your chat address.

Both are 32-character hashes derived from the same identity, so they look very
much alike — paste the one labelled *propagation node address*, not the one at
the top of Settings. Your chat address is where person-to-person messages are
delivered; the propagation address is a different destination
(`lxmf.propagation`) on the same node.

Like your chat address, the propagation address is stable: it does not change
when you toggle hosting on or off, restart, or move between networks. It only
changes if you lose your identity and start over.

## What it costs

- **Disk.** Every stored message is a file in the LXMF message store under
  MeshDeck's data directory (`lxmf/messagestore`). Growth is proportional to
  how many messages are waiting for offline recipients.
- **Bandwidth.** Each peer that syncs downloads the messages addressed to them.
  On a metered or radio link, that is real traffic you are paying for.
- **Uptime.** A node that is offline cannot accept anything, so the service is
  only useful while the machine is running and reachable.

On storage, MeshDeck uses LXMF's defaults: no size cap is imposed, and messages
that nobody collects expire after 30 days. A busy node therefore needs disk
headroom, and a node on a small SD card should be watched.

## Privacy and trust

You are storing messages you cannot read. They are encrypted to the recipient's
identity before they ever reach you, and your node only ever holds the
ciphertext — you do not need anyone's keys, and you cannot open the contents.

What you *can* see is metadata, and you should be honest with yourself about
that: which destination each message is addressed to, when it arrived, how big
it is, and which peers sync with you. That is roughly what a post office sees on
an envelope. Treat it as information you are responsible for.

Two practical rules: only host on a machine you control and keep updated (the
data directory is yours, and nobody else should have shell access to it), and
tell people you are hosting, so they can make an informed choice about routing
their messages through you.

## How others use your node

They need two things: your propagation node address, and propagated delivery.

- **MeshDeck:** Settings → *Message delivery* → paste the address → set the
  delivery method to **Propagated** (or **Opportunistic**, which tries direct
  first and falls back to the propagation node).
- **Sideband, MeshChat and other LXMF clients:** the same propagation-node field
  in their settings.

Once set, their client syncs with your node and sends offline-bound messages
through it. Nothing else changes for them — they still address messages to the
recipient, not to you.

## Turning it off

Switch the toggle off. Your node stops accepting new store-and-forward messages
and announces that it is no longer hosting, so clients stop routing through it.

Be aware of one thing: **stored messages are not deleted when you turn hosting
off.** They stay in `lxmf/messagestore` on disk. LXMF only expires them during
its maintenance pass, which runs while the node is hosting — so after switching
off, they simply sit there. To remove them, stop MeshDeck and delete that
directory yourself.

If other people rely on your node, give them some warning before you switch it
off, and point them at a different propagation node.

## Compatibility

This is the standard LXMF propagation protocol, provided by the official `lxmf`
library — not a MeshDeck invention. A MeshDeck propagation node can serve
Sideband, MeshChat and LXMF's own `lxmd`, and MeshDeck clients can use theirs.
That also means the behaviour above (expiry, deletion after collection, announce
format) is defined by LXMF, and MeshDeck will follow upstream changes as the
library is updated.

The built-in **Guides** tab has a short version of this page, under *Hosting for
others*.
