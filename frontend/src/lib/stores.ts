// App state stores (svelte/store keeps Svelte 5 code simple and explicit).

import { derived, writable } from "svelte/store";

export interface Peer {
  hash: string;
  identity_hash: string;
  display_name: string | null;
  nickname: string | null;
  stamp_cost: number | null;
  first_seen: number | null;
  last_seen: number | null;
  blocked: number;
}

export interface AttachmentMeta {
  index: number;
  name: string;
  size: number;
  sha256: string;
}

export interface ChatMessage {
  id: number;
  hash: string;
  peer_hash: string;
  direction: "in" | "out";
  state: "sending" | "sent" | "delivered" | "failed" | "received";
  title: string | null;
  content: string | null;
  fields_json: string | null;
  created_ts: number | null;
  delivered_ts: number | null;
}

export function attachmentsOf(msg: ChatMessage): AttachmentMeta[] {
  if (!msg.fields_json) return [];
  try {
    const parsed = JSON.parse(msg.fields_json);
    return Array.isArray(parsed?.attachments) ? parsed.attachments : [];
  } catch {
    return [];
  }
}

export function attachmentUrl(peerHash: string, msg: ChatMessage, index: number): string {
  return `/api/v1/attachments/${peerHash}/${msg.hash}/${index}`;
}

export function humanSize(bytes: number): string {
  if (bytes < 1000) return `${bytes} B`;
  if (bytes < 1_000_000) return `${(bytes / 1000).toFixed(1)} KB`;
  return `${(bytes / 1_000_000).toFixed(2)} MB`;
}

export interface IdentityInfo {
  hash: string;
  identity_hash: string;
  display_name: string;
}

export interface Status {
  version: string;
  mode: "basic" | "advanced";
  rns_running: boolean;
  transport_enabled: boolean;
  interfaces: { name: string; type: string; online: boolean; bitrate: number | null }[];
  peers: number;
  uptime_seconds: number;
}

export const identity = writable<IdentityInfo | null>(null);
export const settings = writable<Record<string, unknown>>({});
export const status = writable<Status | null>(null);
export const peers = writable<Peer[]>([]);
export const messages = writable<Record<string, ChatMessage[]>>({});
export const unread = writable<Record<string, number>>({});
export const activePeer = writable<string | null>(null);
export const connected = writable(false);

export interface PageMeta {
  name: string;
  size: number;
  updated: number;
}

export interface NodeMeta {
  hash: string;
  name: string | null;
  first_seen: number;
  last_seen: number;
}

export interface NodeInfo {
  node_hash: string;
  node_name: string;
  serve_pages: boolean;
}

export interface BrowseResult {
  node_hash: string;
  path: string;
  content: string;
  bytes: number;
  elapsed_ms: number;
}

export const pages = writable<PageMeta[]>([]);
export const nodes = writable<NodeMeta[]>([]);
export const nodeInfo = writable<NodeInfo | null>(null);

export const mode = derived(settings, ($s) =>
  $s.mode === "advanced" ? "advanced" : "basic",
);

export function peerLabel(peer: Peer): string {
  return (
    peer.nickname ||
    peer.display_name ||
    `${peer.hash.slice(0, 8)}…${peer.hash.slice(-4)}`
  );
}

export function upsertMessage(peerHash: string, msg: ChatMessage): void {
  messages.update((all) => {
    const list = [...(all[peerHash] ?? [])];
    const idx = list.findIndex((m) => m.hash === msg.hash);
    if (idx >= 0) list[idx] = { ...list[idx], ...msg };
    else list.push(msg);
    list.sort((a, b) => (a.created_ts ?? 0) - (b.created_ts ?? 0));
    return { ...all, [peerHash]: list };
  });
}

export function markUnread(peerHash: string): void {
  unread.update((u) => ({ ...u, [peerHash]: (u[peerHash] ?? 0) + 1 }));
}

export function clearUnread(peerHash: string): void {
  unread.update((u) => ({ ...u, [peerHash]: 0 }));
}
