# Getting started with Waypoint

> This guide ships inside the app (Help section) and lives in the repo at
> `docs/guides/`. Keep both audiences in mind when editing.

## The 60-second version

1. Start Waypoint. On first run it creates your **identity** — a cryptographic
   keypair that *is* your presence on the network. No signup, no server
   account.
2. Pick a **display name**. Others see it next to your address.
3. Share your **address** (top bar) with a friend who runs Waypoint, MeshChat,
   or Sideband — or run a second Waypoint on your machine/network for a
   self-test.
4. When you see them appear under **Peers**, click and say hi.

## What just happened?

- Your node **announced** itself: a signed broadcast saying "this address
  exists, and here's how to reach it". Announces travel hop-to-hop; no central
  directory exists.
- Your friend's node did the same. Once you've both announced, messages route
  over the best known path — local Wi-Fi, the Internet, LoRa radios, whatever
  interfaces either of you have configured.

## Basic vs advanced mode

Everything works in **basic mode**: announcements, interfaces and
encryption are handled for you. Switch to **advanced** in Settings when you
want to control interfaces, host infrastructure, or inspect how traffic
flows. You can switch back and forth freely; nothing breaks.

## Privacy facts worth knowing

- Messages are end-to-end encrypted between identities. There is no server to
  breach; history lives in a local database on your machine.
- Your address is a hash of your public key — pseudonymous by default.
- Announce frequency and network footprint become configurable in advanced
  mode.
