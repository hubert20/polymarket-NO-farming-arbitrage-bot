"use client";

import { Grid, Stack, Typography } from "@mui/material";

import DashboardCard from "@/app/(DashboardLayout)/components/shared/DashboardCard";
import { computePortfolioMetrics } from "@/lib/analytics";
import { fmtPct, fmtUsd, pnlColor } from "@/lib/format";
import { PortfolioMessage, SessionPnlMessage } from "@/types/bot";

type Props = {
  portfolio: PortfolioMessage | null;
  sessionPnl: SessionPnlMessage | null;
};

export default function HeroSummary({ portfolio, sessionPnl }: Props) {
  const metrics = computePortfolioMetrics(portfolio);

  return (
    <DashboardCard>
      <Grid container spacing={3} alignItems="center">
        <Grid size={{ xs: 12, md: 6 }}>
          <Stack spacing={0.5}>
            <Typography variant="overline" color="textSecondary">
              Portfolio value
            </Typography>
            <Typography variant="h3" fontWeight={800}>
              {fmtUsd(metrics.portfolioValue)}
            </Typography>
            <Typography variant="body2" color="textSecondary">
              Cash {fmtUsd(portfolio?.cash_balance)} · Positions {fmtUsd(metrics.positionsValue)} ·{" "}
              {metrics.winningPositions}W / {metrics.losingPositions}L
            </Typography>
          </Stack>
        </Grid>
        <Grid size={{ xs: 12, md: 6 }}>
          <Stack spacing={0.5} sx={{ md: { alignItems: "flex-end", textAlign: "right" } }}>
            <Typography variant="overline" color="textSecondary">
              Session PnL
            </Typography>
            <Typography
              variant="h3"
              fontWeight={800}
              color={sessionPnl ? pnlColor(sessionPnl.pnl_usd) : "text.primary"}
            >
              {sessionPnl
                ? `${sessionPnl.pnl_usd >= 0 ? "+" : ""}${fmtUsd(sessionPnl.pnl_usd)}`
                : "--"}
            </Typography>
            <Typography variant="body2" color="textSecondary">
              {sessionPnl
                ? `${fmtPct(sessionPnl.pnl_pct)} · Balance ${fmtUsd(sessionPnl.current_balance)}`
                : "Awaiting balance poll"}
            </Typography>
          </Stack>
        </Grid>
      </Grid>
    </DashboardCard>
  );
}
