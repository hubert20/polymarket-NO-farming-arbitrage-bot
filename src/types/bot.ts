export type BotPosition = {
  slug: string;
  title: string;
  outcome: string;
  asset: string;
  condition_id: string;
  size: number;
  avg_price: number;
  initial_value: number;
  current_price: number;
  current_value: number;
  pnl_usd: number;
  pnl_pct: number;
  end_date: string;
  eta_seconds: number;
  source: string;
};

export type PortfolioMessage = {
  type: "portfolio";
  updated_at_us: number;
  monitored_markets: number;
  eligible_markets: number;
  in_range_markets: number;
  cash_balance: number | null;
  last_market_refresh_ts: number;
  last_position_sync_ts: number;
  last_price_cycle_ts: number;
  last_error: string;
  target_open_positions: number | null;
  pending_entry_count: number;
  remaining_position_capacity: number | null;
  opened_this_run: number;
  controls_enabled: boolean;
  positions: BotPosition[];
};

export type SessionPnlMessage = {
  type: "session_pnl";
  starting_balance: number;
  current_balance: number;
  pnl_usd: number;
  pnl_pct: number;
};

export type BotTradeMessage = {
  type: "bot_trade";
  action?: string;
  side?: string;
  market_slug?: string;
  amount?: number;
  reference_price?: number;
  order_status?: string;
  error?: string;
  ts?: number;
};

export type BalancePoint = {
  ts: number;
  balance: number;
};

export type BalanceHistoryMessage = {
  type: "balance_history";
  points: BalancePoint[];
};

export type BalancePointMessage = {
  type: "balance_point";
  ts: number;
  balance: number;
};

export type ResolutionMessage = {
  type: "resolution";
  market_slug: string;
  winner: string;
};

export type BotWsMessage =
  | PortfolioMessage
  | SessionPnlMessage
  | BotTradeMessage
  | BalanceHistoryMessage
  | BalancePointMessage
  | ResolutionMessage;

export type ConnectionState = "connecting" | "connected" | "disconnected";

export type BotDashboardState = {
  connection: ConnectionState;
  portfolio: PortfolioMessage | null;
  sessionPnl: SessionPnlMessage | null;
  trades: BotTradeMessage[];
  balanceHistory: BalancePoint[];
  resolutions: Record<string, string>;
};

export const initialBotState: BotDashboardState = {
  connection: "connecting",
  portfolio: null,
  sessionPnl: null,
  trades: [],
  balanceHistory: [],
  resolutions: {},
};
