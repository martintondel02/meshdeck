// Structured interface model shared with the backend renderer + validation.

export type InterfaceKind =
  | "auto"
  | "tcp_server"
  | "tcp_client"
  | "backbone_server"
  | "backbone_client";

export interface InterfaceEntry {
  kind: InterfaceKind;
  name: string;
  enabled: boolean;
  listen_ip?: string;
  port?: number;
  target_host?: string;
  target_port?: number;
  gateway_mode?: boolean;
}

export const KIND_LABELS: Record<InterfaceKind, string> = {
  auto: "Local network (auto-discover)",
  tcp_server: "TCP server (host for others)",
  tcp_client: "TCP client (connect out)",
  backbone_server: "Backbone gateway (public entrypoint)",
  backbone_client: "Backbone client (fast connect)",
};

/** Parse a pasted Reticulum config fragment into interface entries. */
export function parseSnippet(text: string): InterfaceEntry[] {
  const entries: InterfaceEntry[] = [];
  let current: Record<string, string> | null = null;
  let currentName = "";

  const flush = () => {
    if (!current) return;
    const type = (current.type ?? "").trim();
    const enabled = !["no", "false", "0"].includes(
      (current.enabled ?? "yes").toLowerCase(),
    );
    const port = parseInt(current.port ?? current.listen_port ?? "", 10);
    const targetPort = parseInt(current.target_port ?? current.port ?? "", 10);
    const host =
      current.target_host ?? current.remote ?? current.host ?? "";
    const listenIp = current.listen_ip ?? current.listen_on ?? "";

    if (type === "TCPClientInterface" || type === "BackboneClientInterface") {
      if (host && targetPort)
        entries.push({
          kind:
            type === "TCPClientInterface" ? "tcp_client" : "backbone_client",
          name: currentName || `Imported ${type}`,
          enabled,
          target_host: host,
          target_port: targetPort,
        });
    } else if (type === "TCPServerInterface") {
      if (listenIp && port)
        entries.push({
          kind: "tcp_server",
          name: currentName || "Imported TCP server",
          enabled,
          listen_ip: listenIp,
          port,
        });
    } else if (type === "BackboneInterface") {
      if (host && targetPort) {
        entries.push({
          kind: "backbone_client",
          name: currentName || "Imported backbone client",
          enabled,
          target_host: host,
          target_port: targetPort,
        });
      } else if (listenIp && port) {
        entries.push({
          kind: "backbone_server",
          name: currentName || "Imported backbone gateway",
          enabled,
          listen_ip: listenIp,
          port,
          gateway_mode: (current.mode ?? "").trim() === "gateway",
        });
      }
    }
    current = null;
    currentName = "";
  };

  for (const rawLine of text.split("\n")) {
    const line = rawLine.trim();
    if (!line || line.startsWith("#") || line.startsWith(";")) continue;
    if (line.startsWith("[[")) {
      flush();
      currentName = line.replace(/^\[+|\]+$/g, "").trim();
      current = {};
    } else if (line.startsWith("[")) {
      flush();
    } else if (current && line.includes("=")) {
      const idx = line.indexOf("=");
      const key = line.slice(0, idx).trim();
      const value = (line.slice(idx + 1).split("#")[0] ?? "").split(";")[0]?.trim() ?? "";
      current[key] = value;
    }
  }
  flush();
  return entries;
}

/** Render a shareable Reticulum config snippet for a server-kind entry. */
export function shareSnippet(entry: InterfaceEntry, hostnameHint: string): string {
  const name = entry.name || "Waypoint Entrypoint";
  if (entry.kind === "tcp_server" || entry.kind === "backbone_server") {
    const itype =
      entry.kind === "backbone_server" ? "BackboneInterface" : "TCPServerInterface";
    const lines = [
      `# Connect to ${name}`,
      "[interfaces]",
      `  [[${name}]]`,
      `    type = ${itype === "BackboneInterface" ? "BackboneClientInterface" : "TCPClientInterface"}`,
      "    enabled = Yes",
      `    target_host = ${hostnameHint}`,
      `    target_port = ${entry.port ?? 4242}`,
    ];
    return lines.join("\n");
  }
  return "";
}
