export function fmtUsd(value: number | null | undefined, digits = 2): string {
  if (value == null || Number.isNaN(Number(value))) return "--";
  return (
    "$" +
    Number(value).toLocaleString("en-US", {
      minimumFractionDigits: digits,
      maximumFractionDigits: digits,
    })
  );
}

export function fmtPct(value: number | null | undefined): string {
  if (value == null || Number.isNaN(Number(value))) return "--";
  const num = Number(value);
  const sign = num >= 0 ? "+" : "";
  return sign + num.toFixed(2) + "%";
}

export function fmtShares(value: number | null | undefined): string {
  if (value == null || Number.isNaN(Number(value))) return "--";
  return Number(value).toLocaleString("en-US", { maximumFractionDigits: 4 });
}

export function fmtTime(epochSec: number | undefined): string {
  if (!epochSec) return "--";
  const d = new Date(epochSec * 1000);
  return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

export function fmtEta(seconds: number | undefined): string {
  const remaining = Math.max(0, Math.floor(Number(seconds || 0)));
  const days = Math.floor(remaining / 86400);
  const hours = Math.floor((remaining % 86400) / 3600);
  const minutes = Math.floor((remaining % 3600) / 60);
  if (days > 0) return `${days}d ${hours}h`;
  if (hours > 0) return `${hours}h ${minutes}m`;
  return `${minutes}m`;
}

export function fmtAgo(tsSec: number | undefined): string {
  if (!tsSec) return "--";
  const delta = Math.max(0, Math.floor(Date.now() / 1000 - tsSec));
  if (delta < 60) return `${delta}s ago`;
  if (delta < 3600) return `${Math.floor(delta / 60)}m ago`;
  return `${Math.floor(delta / 3600)}h ago`;
}

export function pnlColor(value: number): "success.main" | "error.main" {
  return value >= 0 ? "success.main" : "error.main";
}

export function botWsUrl(): string {
  return process.env.NEXT_PUBLIC_BOT_WS_URL || "ws://localhost:8080/ws";
}

export function botApiUrl(): string {
  return process.env.NEXT_PUBLIC_BOT_API_URL || "http://localhost:8080";
}
