"use client";

import dynamic from "next/dynamic";
import { useTheme } from "@mui/material/styles";
import { Box, Chip, Grid, LinearProgress, Stack, Typography } from "@mui/material";

import DashboardCard from "@/app/(DashboardLayout)/components/shared/DashboardCard";
import { PortfolioMessage } from "@/types/bot";

type Props = { portfolio: PortfolioMessage | null; fillHeight?: boolean };

function fmtTarget(value: number | null | undefined): string {
  return value == null ? "Unlimited" : String(value);
}

export default function BotActivityPanel({ portfolio, fillHeight }: Props) {
  const openCount = portfolio?.positions?.length ?? 0;
  const pending = portfolio?.pending_entry_count ?? 0;
  const opened = portfolio?.opened_this_run ?? 0;
  const target = portfolio?.target_open_positions;
  const remaining = portfolio?.remaining_position_capacity;

  const capacityPct =
    target != null && target > 0 ? Math.min(100, (openCount / target) * 100) : null;

  return (
    <DashboardCard title="Bot Activity" fillHeight={fillHeight}>
      <Stack spacing={2.5} sx={{ height: fillHeight ? "100%" : undefined, justifyContent: "space-between" }}>
        <Grid container spacing={2}>
          <Grid size={6}>
            <Typography variant="caption" color="textSecondary" textTransform="uppercase">
              Pending entries
            </Typography>
            <Typography variant="h5" fontWeight={700}>
              {pending}
            </Typography>
          </Grid>
          <Grid size={6}>
            <Typography variant="caption" color="textSecondary" textTransform="uppercase">
              Opened this run
            </Typography>
            <Typography variant="h5" fontWeight={700}>
              {opened}
            </Typography>
          </Grid>
          <Grid size={12}>
            <Typography variant="caption" color="textSecondary" textTransform="uppercase">
              Remaining capacity
            </Typography>
            <Typography variant="h5" fontWeight={700}>
              {fmtTarget(remaining)}
            </Typography>
          </Grid>
        </Grid>

        {capacityPct != null && (
          <Box>
            <Stack direction="row" justifyContent="space-between" mb={0.5}>
              <Typography variant="caption" color="textSecondary">
                Target {fmtTarget(target)}
              </Typography>
              <Typography variant="caption" color="textSecondary">
                {capacityPct.toFixed(0)}%
              </Typography>
            </Stack>
            <LinearProgress
              variant="determinate"
              value={capacityPct}
              sx={{ height: 8, borderRadius: 4 }}
            />
          </Box>
        )}

        <Stack direction="row" flexWrap="wrap" gap={1}>
          <Chip
            label={portfolio?.controls_enabled ? "Controls active" : "Controls off"}
            size="small"
            color={portfolio?.controls_enabled ? "primary" : "default"}
            variant="outlined"
          />
          {pending > 0 && (
            <Chip label={`${pending} queued`} size="small" color="warning" variant="outlined" />
          )}
        </Stack>
      </Stack>
    </DashboardCard>
  );
}
