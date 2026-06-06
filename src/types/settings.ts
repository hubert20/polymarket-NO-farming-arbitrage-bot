export type BotSettings = {
  bot_mode: string;
  live_trading_enabled: boolean;
  dry_run: boolean;
  demo_mode: boolean;
  private_key_set: boolean;
  private_key_preview: string;
  funder_address: string;
  database_url_set: boolean;
  polygon_rpc_url_set: boolean;
  connection: {
    host: string;
    chain_id: number;
    signature_type: number;
  };
  strategy: {
    max_entry_price: number;
    cash_pct_per_trade: number;
    min_trade_amount: number;
    fixed_trade_amount: number;
    allowed_slippage: number;
    max_new_positions: number;
  };
};

export type BotSettingsPayload = {
  bot_mode: string;
  live_trading_enabled: boolean;
  dry_run: boolean;
  demo_mode: boolean;
  private_key?: string;
  funder_address: string;
  database_url?: string;
  polygon_rpc_url?: string;
  connection: {
    signature_type: number;
  };
  strategy: BotSettings["strategy"];
};

export const defaultSettingsPayload = (): BotSettingsPayload => ({
  bot_mode: "paper",
  live_trading_enabled: false,
  dry_run: true,
  demo_mode: true,
  private_key: "",
  funder_address: "",
  database_url: "",
  polygon_rpc_url: "",
  connection: { signature_type: 2 },
  strategy: {
    max_entry_price: 0.65,
    cash_pct_per_trade: 0.02,
    min_trade_amount: 5,
    fixed_trade_amount: 0,
    allowed_slippage: 0.3,
    max_new_positions: -1,
  },
});
