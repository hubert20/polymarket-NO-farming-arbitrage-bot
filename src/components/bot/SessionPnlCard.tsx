"use client";

import dynamic from "next/dynamic";
import { useTheme } from "@mui/material/styles";
import { Box, Stack, Typography } from "@mui/material";

import DashboardCard from "@/app/(DashboardLayout)/components/shared/DashboardCard";
import { computePnlSparkline } from "@/lib/analytics";
import { fmtPct, fmtUsd, pnlColor } from "@/lib/format";
import { BalancePoint, SessionPnlMessage } from "@/types/bot";

const Chart = dynamic(() => import("react-apexcharts"), { ssr: false });

type Props = {
  sessionPnl: SessionPnlMessage | null;
  balanceHistory: BalancePoint[];
};

export default function SessionPnlCard({ sessionPnl, balanceHistory }: Props) {
  const theme = useTheme();
  const spark = computePnlSparkline(balanceHistory, sessionPnl);
  const pnl = sessionPnl?.pnl_usd ?? 0;
  const pnlPct = sessionPnl?.pnl_pct ?? 0;

  const sparkOptions: Record<string, unknown> = {
    chart: {
      type: "area",
      sparkline: { enabled: true },
      animations: { enabled: true },
    },
    stroke: { curve: "smooth", width: 2 },
    fill: {
      type: "gradient",
      gradient: {
        shadeIntensity: 0.5,
        opacityFrom: 0.4,
        opacityTo: 0.05,
        colorStops: [
          { offset: 0, color: pnl >= 0 ? theme.palette.success.main : theme.palette.error.main, opacity: 0.5 },
          { offset: 100, color: pnl >= 0 ? theme.palette.success.main : theme.palette.error.main, opacity: 0.05 },
        ],
      },
    },
    colors: [pnl >= 0 ? theme.palette.success.main : theme.palette.error.main],
    tooltip: { enabled: false },
  };

  return (
    <DashboardCard title="Session Performance">
      {!sessionPnl ? (
        <Typography color="textSecondary" py={4} textAlign="center">
          Session PnL tracks after first balance poll
        </Typography>
      ) : (
        <Stack spacing={2}>
          <Box>
            <Typography variant="h3" fontWeight={700} color={pnlColor(pnl)}>
              {pnl >= 0 ? "+" : ""}
              {fmtUsd(pnl)}
            </Typography>
            <Typography variant="body2" color={pnlColor(pnlPct)}>
              {fmtPct(pnlPct)} this session
            </Typography>
          </Box>
          {spark.length >= 2 && (
            <Chart
              type="area"
              height={80}
              series={[{ data: spark }]}
              options={sparkOptions}
            />
          )}
          <Stack direction="row" justifyContent="space-between">
            <Box>
              <Typography variant="caption" color="textSecondary">
                Start
              </Typography>
              <Typography variant="body2">{fmtUsd(sessionPnl.starting_balance)}</Typography>
            </Box>
            <Box textAlign="right">
              <Typography variant="caption" color="textSecondary">
                Current
              </Typography>
              <Typography variant="body2">{fmtUsd(sessionPnl.current_balance)}</Typography>
            </Box>
          </Stack>
        </Stack>
      )}
    </DashboardCard>
  );
}
