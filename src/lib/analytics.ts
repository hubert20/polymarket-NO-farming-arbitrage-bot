import {
  BotDashboardState,
  BotPosition,
  BotTradeMessage,
  PortfolioMessage,
  SessionPnlMessage,
} from "@/types/bot";

export type PortfolioMetrics = {
  positionsValue: number;
  portfolioValue: number | null;
  unrealizedPnl: number;
  avgPnlPct: number;
  winningPositions: number;
  losingPositions: number;
  largestWinner: BotPosition | null;
  largestLoser: BotPosition | null;
};

export type TradeStats = {
  total: number;
  buys: number;
  errors: number;
  totalBuyVolume: number;
  avgBuySize: number;
  successRate: number;
};

export type ResolutionStats = {
  resolved: number;
  noWins: number;
  noLosses: number;
  winRate: number;
  pending: number;
};

export type MarketFunnel = {
  monitored: number;
  eligible: number;
  inRange: number;
  eligiblePct: number;
  inRangePct: number;
};

export function computePortfolioMetrics(
  portfolio: PortfolioMessage | null,
): PortfolioMetrics {
  const positions = portfolio?.positions ?? [];
  const positionsValue = positions.reduce((sum, p) => sum + (p.current_value || 0), 0);
  const cash = portfolio?.cash_balance;
  const portfolioValue = cash == null ? null : cash + positionsValue;
  const unrealizedPnl = positions.reduce((sum, p) => sum + (p.pnl_usd || 0), 0);
  const avgPnlPct =
    positions.length > 0
      ? positions.reduce((sum, p) => sum + (p.pnl_pct || 0), 0) / positions.length
      : 0;
  const winningPositions = positions.filter((p) => p.pnl_usd > 0).length;
  const losingPositions = positions.filter((p) => p.pnl_usd < 0).length;

  let largestWinner: BotPosition | null = null;
  let largestLoser: BotPosition | null = null;
  for (const p of positions) {
    if (!largestWinner || p.pnl_usd > largestWinner.pnl_usd) largestWinner = p;
    if (!largestLoser || p.pnl_usd < largestLoser.pnl_usd) largestLoser = p;
  }

  return {
    positionsValue,
    portfolioValue,
    unrealizedPnl,
    avgPnlPct,
    winningPositions,
    losingPositions,
    largestWinner: largestWinner && largestWinner.pnl_usd > 0 ? largestWinner : null,
    largestLoser: largestLoser && largestLoser.pnl_usd < 0 ? largestLoser : null,
  };
}

export function computeTradeStats(trades: BotTradeMessage[]): TradeStats {
  const buys = trades.filter((t) => t.action === "buy");
  const errors = trades.filter((t) => t.action === "error");
  const filled = buys.filter(
    (t) => !t.error && t.order_status !== "rejected" && t.order_status !== "failed",
  );
  const totalBuyVolume = buys.reduce((sum, t) => sum + (t.amount || 0), 0);

  return {
    total: trades.length,
    buys: buys.length,
    errors: errors.length,
    totalBuyVolume,
    avgBuySize: buys.length > 0 ? totalBuyVolume / buys.length : 0,
    successRate: buys.length > 0 ? (filled.length / buys.length) * 100 : 0,
  };
}

export function computeResolutionStats(
  trades: BotTradeMessage[],
  resolutions: Record<string, string>,
): ResolutionStats {
  const tradedSlugs = new Set(
    trades.filter((t) => t.action === "buy" && t.market_slug).map((t) => t.market_slug!),
  );
  let noWins = 0;
  let noLosses = 0;

  for (const slug of Array.from(tradedSlugs)) {
    const winner = resolutions[slug];
    if (!winner) continue;
    const normalized = winner.toLowerCase();
    if (normalized === "no") noWins += 1;
    else if (normalized === "yes") noLosses += 1;
  }

  const resolved = noWins + noLosses;
  return {
    resolved,
    noWins,
    noLosses,
    winRate: resolved > 0 ? (noWins / resolved) * 100 : 0,
    pending: tradedSlugs.size - resolved,
  };
}

export function computeMarketFunnel(portfolio: PortfolioMessage | null): MarketFunnel {
  const monitored = portfolio?.monitored_markets ?? 0;
  const eligible = portfolio?.eligible_markets ?? 0;
  const inRange = portfolio?.in_range_markets ?? 0;
  return {
    monitored,
    eligible,
    inRange,
    eligiblePct: monitored > 0 ? (eligible / monitored) * 100 : 0,
    inRangePct: eligible > 0 ? (inRange / eligible) * 100 : 0,
  };
}

export function computePnlSparkline(
  balanceHistory: { ts: number; balance: number }[],
  sessionPnl: SessionPnlMessage | null,
): number[] {
  if (balanceHistory.length >= 2) {
    return balanceHistory.slice(-24).map((p) => p.balance);
  }
  if (sessionPnl) {
    return [sessionPnl.starting_balance, sessionPnl.current_balance];
  }
  return [];
}

export type BotHealth = {
  status: string;
  bot_mode: string;
  dry_run: boolean;
  live_trading_enabled: boolean;
  demo_mode?: boolean;
};

export function tradingModeLabel(health: BotHealth | null): string {
  if (!health) return "Unknown";
  if (health.demo_mode) return "Demo";
  if (health.bot_mode === "live" && health.live_trading_enabled && !health.dry_run) {
    return "Live";
  }
  if (health.bot_mode === "live") return "Live (guarded)";
  return "Paper";
}
