"use client";

import { Box, Chip, Stack, Typography } from "@mui/material";

import DashboardCard from "@/app/(DashboardLayout)/components/shared/DashboardCard";
import PolymarketLink from "@/components/bot/PolymarketLink";
import { fmtTime, fmtUsd } from "@/lib/format";
import { BotTradeMessage } from "@/types/bot";

/** Visible trade rows before scrolling (~5 items). */
const VISIBLE_TRADES = 5;
const TRADE_ROW_HEIGHT_PX = 92;
const TRADE_LIST_GAP_PX = 12;
const SCROLL_HEIGHT_PX =
  VISIBLE_TRADES * TRADE_ROW_HEIGHT_PX + (VISIBLE_TRADES - 1) * TRADE_LIST_GAP_PX;

type Props = {
  trades: BotTradeMessage[];
  resolutions: Record<string, string>;
};

function tradeStatus(msg: BotTradeMessage): string {
  if (msg.error) return msg.error;
  if (msg.order_status) return msg.order_status;
  return "--";
}

function actionColor(action?: string): "success" | "error" | "default" {
  if (action === "buy") return "success";
  if (action === "error") return "error";
  return "default";
}

export default function TradeFeed({ trades, resolutions }: Props) {
  return (
    <DashboardCard title="Recent Activity">
      {trades.length === 0 ? (
        <Box
          sx={{
            height: SCROLL_HEIGHT_PX,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
          }}
        >
          <Typography color="textSecondary" textAlign="center">
            Waiting for bot trades…
          </Typography>
        </Box>
      ) : (
        <Stack
          spacing={1.5}
          sx={{
            height: SCROLL_HEIGHT_PX,
            minWidth: 0,
            overflowY: "auto",
            pr: 0.5,
            scrollbarWidth: "thin",
          }}
        >
          {trades.map((trade, i) => {
            const slug = trade.market_slug || "";
            const resolution = slug ? resolutions[slug] : undefined;
            return (
              <Box
                key={`${trade.ts}-${slug}-${i}`}
                sx={{
                  flexShrink: 0,
                  minHeight: TRADE_ROW_HEIGHT_PX,
                  p: 1.5,
                  borderRadius: 2,
                  bgcolor: "grey.50",
                  border: "1px solid",
                  borderColor: "divider",
                  minWidth: 0,
                  boxSizing: "border-box",
                }}
              >
                <Stack direction="row" justifyContent="space-between" alignItems="center" gap={1}>
                  <Stack direction="row" spacing={0.75} alignItems="center">
                    <Chip
                      label={trade.action || "event"}
                      size="small"
                      color={actionColor(trade.action)}
                      variant="outlined"
                    />
                    {trade.side ? (
                      <Typography variant="caption" color="textSecondary">
                        {trade.side}
                      </Typography>
                    ) : null}
                  </Stack>
                  <Typography variant="caption" color="textSecondary" fontFamily="monospace">
                    {fmtTime(trade.ts)}
                  </Typography>
                </Stack>
                {slug ? (
                  <Box mt={0.75} sx={{ minWidth: 0 }}>
                    <PolymarketLink slug={slug} title={slug} />
                  </Box>
                ) : null}
                <Typography variant="body2" mt={0.75} color="textSecondary" noWrap>
                  Amount {fmtUsd(trade.amount)} · Price {fmtUsd(trade.reference_price, 4)} ·{" "}
                  {tradeStatus(trade)}
                </Typography>
                {resolution ? (
                  <Chip label={`Resolved: ${resolution}`} size="small" sx={{ mt: 1 }} />
                ) : null}
              </Box>
            );
          })}
        </Stack>
      )}
    </DashboardCard>
  );
}
