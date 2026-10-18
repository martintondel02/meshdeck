export function timeAgo(tsSeconds: number | null | undefined): string {
  if (!tsSeconds) return "never";
  const diff = Date.now() / 1000 - tsSeconds;
  if (diff < 60) return "just now";
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return `${Math.floor(diff / 86400)}d ago`;
}

export function clockTime(tsSeconds: number | null | undefined): string {
  if (!tsSeconds) return "";
  return new Date(tsSeconds * 1000).toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
  });
}
