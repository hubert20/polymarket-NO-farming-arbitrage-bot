"use client";

import dynamic from "next/dynamic";
import { useTheme } from "@mui/material/styles";
import { Box, Grid, Stack, Typography } from "@mui/material";

import DashboardCard from "@/app/(DashboardLayout)/components/shared/DashboardCard";
import ChartContainer from "@/components/bot/ChartContainer";
import { computeResolutionStats } from "@/lib/analytics";
import { BotTradeMessage } from "@/types/bot";

const Chart = dynamic(() => import("react-apexcharts"), { ssr: false });

type Props = {
  trades: BotTradeMessage[];
  resolutions: Record<string, string>;
  fillHeight?: boolean;
};

export default function ResolutionStats({ trades, resolutions, fillHeight }: Props) {
  const theme = useTheme();
  const stats = computeResolutionStats(trades, resolutions);

  const series = [stats.noWins, stats.noLosses, stats.pending];
  const hasData = stats.resolved > 0 || stats.pending > 0;

  const options: Record<string, unknown> = {
    chart: { type: "donut", fontFamily: theme.typography.fontFamily },
    labels: ["NO wins", "NO losses", "Pending"],
    colors: [theme.palette.success.main, theme.palette.error.main, theme.palette.grey[400]],
    plotOptions: {
      pie: {
        donut: {
          size: "68%",
          labels: {
            show: true,
            total: {
              show: true,
              label: "Win rate",
              formatter: () =>
                stats.resolved > 0 ? `${stats.winRate.toFixed(0)}%` : "—",
            },
          },
        },
      },
    },
    dataLabels: { enabled: false },
    legend: { position: "bottom" },
  };

  return (
    <DashboardCard title="NO Resolution Outcomes" fillHeight={fillHeight}>
      {!hasData ? (
        <Typography color="textSecondary" py={6} textAlign="center" sx={{ flex: fillHeight ? 1 : undefined }}>
          Resolved markets appear after positions settle
        </Typography>
      ) : (
        <Stack spacing={2} sx={{ height: fillHeight ? "100%" : undefined }}>
          <ChartContainer minHeight={240} sx={{ flex: fillHeight ? 1 : undefined }}>
            <Chart type="donut" height={240} width="100%" series={series} options={options} />
          </ChartContainer>
          <Grid container spacing={1}>
            <Grid size={4}>
              <Box textAlign="center">
                <Typography variant="h6" color="success.main" fontWeight={700}>
                  {stats.noWins}
                </Typography>
                <Typography variant="caption" color="textSecondary">
                  Wins
                </Typography>
              </Box>
            </Grid>
            <Grid size={4}>
              <Box textAlign="center">
                <Typography variant="h6" color="error.main" fontWeight={700}>
                  {stats.noLosses}
                </Typography>
                <Typography variant="caption" color="textSecondary">
                  Losses
                </Typography>
              </Box>
            </Grid>
            <Grid size={4}>
              <Box textAlign="center">
                <Typography variant="h6" fontWeight={700}>
                  {stats.pending}
                </Typography>
                <Typography variant="caption" color="textSecondary">
                  Pending
                </Typography>
              </Box>
            </Grid>
          </Grid>
        </Stack>
      )}
    </DashboardCard>
  );
}
