export const POLYMARKET_BASE = "https://polymarket.com";

/** Event page — primary link for market slugs from the bot. */
export function polymarketEventUrl(slug: string): string {
  const clean = (slug || "").trim();
  if (!clean) return POLYMARKET_BASE;
  return `${POLYMARKET_BASE}/event/${encodeURIComponent(clean)}`;
}

/** Market page by condition id when available; falls back to event slug. */
export function polymarketMarketUrl(slug: string, conditionId?: string): string {
  const cid = (conditionId || "").trim();
  if (cid && !cid.startsWith("demo-")) {
    return `${POLYMARKET_BASE}/market/${encodeURIComponent(cid)}`;
  }
  return polymarketEventUrl(slug);
}
