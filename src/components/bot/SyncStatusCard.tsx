"use client";

import { Chip, Stack, Typography } from "@mui/material";

import DashboardCard from "@/app/(DashboardLayout)/components/shared/DashboardCard";
import { fmtAgo } from "@/lib/format";
import { PortfolioMessage } from "@/types/bot";

type Props = {
  portfolio: PortfolioMessage | null;
  fillHeight?: boolean;
};

export default function SyncStatusCard({ portfolio, fillHeight }: Props) {
  return (
    <DashboardCard title="Sync Status" fillHeight={fillHeight}>
      <Stack spacing={1} justifyContent="space-between" sx={{ height: fillHeight ? "100%" : undefined }}>
        <Stack spacing={0.75}>
          <Typography variant="body2" color="textSecondary">
            Market refresh {fmtAgo(portfolio?.last_market_refresh_ts)}
          </Typography>
          <Typography variant="body2" color="textSecondary">
            Position sync {fmtAgo(portfolio?.last_position_sync_ts)}
          </Typography>
          <Typography variant="body2" color="textSecondary">
            Price cycle {fmtAgo(portfolio?.last_price_cycle_ts)}
          </Typography>
        </Stack>
        {portfolio?.last_error ? (
          <Chip label={portfolio.last_error} color="error" size="small" sx={{ alignSelf: "flex-start" }} />
        ) : (
          <Chip label="No errors" color="success" size="small" variant="outlined" sx={{ alignSelf: "flex-start" }} />
        )}
      </Stack>
    </DashboardCard>
  );
}
