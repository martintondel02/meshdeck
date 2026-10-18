import { t } from "./i18n";

export function timeAgo(tsSeconds: number | null | undefined): string {
  if (!tsSeconds) return t("common.never");
  const diff = Date.now() / 1000 - tsSeconds;
  if (diff < 60) return t("common.just_now");
  if (diff < 3600) return t("common.minutes_ago", { count: Math.floor(diff / 60) });
  if (diff < 86400) return t("common.hours_ago", { count: Math.floor(diff / 3600) });
  return t("common.days_ago", { count: Math.floor(diff / 86400) });
}

export function clockTime(tsSeconds: number | null | undefined): string {
  if (!tsSeconds) return "";
  return new Date(tsSeconds * 1000).toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
  });
}
