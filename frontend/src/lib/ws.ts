// WebSocket connection with reconnect backoff; feeds the stores.

import { get } from "svelte/store";
import { api, getToken, wsUrl } from "./api";
import {
  activePeer,
  connected,
  markUnread,
  messages,
  peers,
  upsertMessage,
  type Peer,
} from "./stores";

let ws: WebSocket | null = null;
let backoff = 1000;
let cmdSeq = 0;
const pending = new Map<number, (payload: unknown) => void>();

export function wsCmd<T = unknown>(
  cmd: string,
  data: unknown = {},
): Promise<T> {
  return new Promise((resolve, reject) => {
    if (!ws || ws.readyState !== WebSocket.OPEN) {
      reject(new Error("not connected"));
      return;
    }
    const id = ++cmdSeq;
    pending.set(id, resolve as (p: unknown) => void);
    ws.send(JSON.stringify({ type: "cmd", id, cmd, data }));
    setTimeout(() => {
      if (pending.delete(id)) reject(new Error("timeout"));
    }, 15000);
  });
}

function handleEvent(event: string, data: Record<string, unknown>): void {
  switch (event) {
    case "peer_announced": {
      const hash = data.destination_hash as string;
      peers.update((list) => {
        const existing = list.find((p) => p.hash === hash);
        if (existing) return list;
        const peer: Peer = {
          hash,
          identity_hash: data.identity_hash as string,
          display_name: (data.display_name as string | null) ?? null,
          nickname: null,
          stamp_cost: (data.stamp_cost as number | null) ?? null,
          first_seen: null,
          last_seen: Date.now() / 1000,
          blocked: 0,
        };
        return [peer, ...list];
      });
      break;
    }
    case "message_received": {
      const hash = data.peer as string;
      const attachments = data.attachments as unknown[] | undefined;
      upsertMessage(hash, {
        id: -Date.now(),
        hash: data.hash as string,
        peer_hash: hash,
        direction: "in",
        state: "received",
        title: (data.title as string) ?? null,
        content: (data.content as string) ?? null,
        fields_json: attachments?.length
          ? JSON.stringify({ attachments })
          : null,
        created_ts: (data.ts as number) ?? Date.now() / 1000,
        delivered_ts: null,
      });
      if (get(activePeer) !== hash) markUnread(hash);
      break;
    }
    case "message_state": {
      const hash = data.hash as string;
      const state = data.state as string;
      // state updates don't always carry peer info; scanning is fine at this scale
      messages.update((all) => {
        for (const key of Object.keys(all)) {
          const msgs = all[key] ?? [];
          if (msgs.some((m) => m.hash === hash)) {
            return {
              ...all,
              [key]: msgs.map((m) =>
                m.hash === hash
                  ? {
                      ...m,
                      state: state as never,
                      delivered_ts:
                        state === "delivered"
                          ? ((data.ts as number) ?? m.delivered_ts)
                          : m.delivered_ts,
                    }
                  : m,
              ),
            };
          }
        }
        return all;
      });
      break;
    }
    case "peer_updated":
    case "peer_added":
      // refetch peer list for simplicity
      api<Peer[]>("/api/v1/peers").then((p) => peers.set(p));
      break;
  }
}

export function connectWs(): void {
  if (!getToken()) return;
  try {
    ws = new WebSocket(wsUrl());
  } catch {
    scheduleReconnect();
    return;
  }
  ws.onopen = () => {
    backoff = 1000;
    connected.set(true);
  };
  ws.onclose = () => {
    connected.set(false);
    scheduleReconnect();
  };
  ws.onerror = () => ws?.close();
  ws.onmessage = (frame) => {
    let parsed;
    try {
      parsed = JSON.parse(frame.data);
    } catch {
      return;
    }
    if (parsed.type === "ack" && pending.has(parsed.id)) {
      pending.get(parsed.id)?.(parsed.data);
      pending.delete(parsed.id);
    } else if (parsed.type === "error" && pending.has(parsed.id)) {
      pending.get(parsed.id)?.({ __error: parsed.error });
      pending.delete(parsed.id);
    } else if (parsed.type === "event") {
      handleEvent(parsed.event, parsed.data ?? {});
    }
  };
}

function scheduleReconnect(): void {
  const wait = backoff;
  backoff = Math.min(backoff * 2, 15000);
  setTimeout(connectWs, wait);
}
