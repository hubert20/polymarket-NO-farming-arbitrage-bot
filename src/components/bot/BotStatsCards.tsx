"use client";

import { Chip, Grid, Stack, Typography } from "@mui/material";

import DashboardCard from "@/app/(DashboardLayout)/components/shared/DashboardCard";
import { fmtAgo, fmtUsd, pnlColor } from "@/lib/format";
import { PortfolioMessage, SessionPnlMessage } from "@/types/bot";

type Props = {
  portfolio: PortfolioMessage | null;
  sessionPnl: SessionPnlMessage | null;
};

function StatCard({
  label,
  value,
  meta,
  valueColor,
}: {
  label: string;
  value: string;
  meta?: string;
  valueColor?: string;
}) {
  return (
    <DashboardCard>
      <Typography variant="subtitle2" color="textSecondary" textTransform="uppercase" gutterBottom>
        {label}
      </Typography>
      <Typography variant="h4" fontWeight={700} color={valueColor}>
        {value}
      </Typography>
      {meta ? (
        <Typography variant="caption" color="textSecondary" display="block" mt={1}>
          {meta}
        </Typography>
      ) : null}
    </DashboardCard>
  );
}

export default function BotStatsCards({ portfolio, sessionPnl }: Props) {
  const positions = portfolio?.positions ?? [];
  const positionsValue = positions.reduce((sum, p) => sum + (p.current_value || 0), 0);
  const cash = portfolio?.cash_balance;
  const portfolioValue = cash == null ? null : cash + positionsValue;

  return (
    <Grid container spacing={3} sx={{ width: "100%" }}>
      <Grid size={{ xs: 6, sm: 4, md: 3 }}>
        <StatCard label="Monitored" value={String(portfolio?.monitored_markets ?? "--")} />
      </Grid>
      <Grid size={{ xs: 6, sm: 4, md: 3 }}>
        <StatCard label="Eligible" value={String(portfolio?.eligible_markets ?? "--")} />
      </Grid>
      <Grid size={{ xs: 6, sm: 4, md: 3 }}>
        <StatCard label="In Range" value={String(portfolio?.in_range_markets ?? "--")} />
      </Grid>
      <Grid size={{ xs: 6, sm: 4, md: 3 }}>
        <StatCard label="Cash" value={fmtUsd(cash)} />
      </Grid>
      <Grid size={{ xs: 6, sm: 4, md: 3 }}>
        <StatCard
          label="Portfolio Value"
          value={fmtUsd(portfolioValue)}
          meta={`cash ${fmtUsd(cash)} · positions ${fmtUsd(positionsValue)}`}
        />
      </Grid>
      <Grid size={{ xs: 6, sm: 4, md: 3 }}>
        <StatCard
          label="Session PnL"
          value={
            sessionPnl
              ? `${sessionPnl.pnl_usd >= 0 ? "+" : ""}${fmtUsd(sessionPnl.pnl_usd)}`
              : "--"
          }
          meta={sessionPnl ? fmtUsd(sessionPnl.current_balance) + " balance" : undefined}
          valueColor={sessionPnl ? pnlColor(sessionPnl.pnl_usd) : undefined}
        />
      </Grid>
      <Grid size={{ xs: 12, sm: 12, md: 3 }}>
        <DashboardCard>
          <Typography variant="subtitle2" color="textSecondary" textTransform="uppercase" gutterBottom>
            Sync Status
          </Typography>
          <Stack spacing={0.5}>
            <Typography variant="body2" color="textSecondary">
              Market refresh {fmtAgo(portfolio?.last_market_refresh_ts)}
            </Typography>
            <Typography variant="body2" color="textSecondary">
              Position sync {fmtAgo(portfolio?.last_position_sync_ts)}
            </Typography>
            <Typography variant="body2" color="textSecondary">
              Price cycle {fmtAgo(portfolio?.last_price_cycle_ts)}
            </Typography>
            {portfolio?.last_error ? (
              <Chip label={portfolio.last_error} color="error" size="small" sx={{ mt: 1 }} />
            ) : (
              <Chip label="No errors" color="success" size="small" variant="outlined" sx={{ mt: 1 }} />
            )}
          </Stack>
        </DashboardCard>
      </Grid>
    </Grid>
  );
}
