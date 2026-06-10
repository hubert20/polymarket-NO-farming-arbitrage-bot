"use client";

import dynamic from "next/dynamic";
import { useTheme } from "@mui/material/styles";
import { Box, Stack, Typography } from "@mui/material";

import DashboardCard from "@/app/(DashboardLayout)/components/shared/DashboardCard";
import ChartContainer from "@/components/bot/ChartContainer";
import { baseChartOptions } from "@/lib/chartTheme";
import { computePortfolioMetrics } from "@/lib/analytics";
import { fmtUsd } from "@/lib/format";
import { PortfolioMessage } from "@/types/bot";

const Chart = dynamic(() => import("react-apexcharts"), { ssr: false });

type Props = { portfolio: PortfolioMessage | null; fillHeight?: boolean };

export default function PortfolioAllocationChart({ portfolio, fillHeight }: Props) {
  const theme = useTheme();
  const metrics = computePortfolioMetrics(portfolio);
  const cash = portfolio?.cash_balance ?? 0;

  const series = [cash, metrics.positionsValue];
  const total = cash + metrics.positionsValue;

  const options: Record<string, unknown> = {
    ...baseChartOptions(theme),
    chart: { ...baseChartOptions(theme).chart, type: "donut" },
    labels: ["Cash", "Positions"],
    colors: [theme.palette.primary.light, theme.palette.primary.main],
    plotOptions: {
      pie: {
        donut: {
          size: "72%",
          labels: {
            show: true,
            total: {
              show: true,
              label: "Total",
              formatter: () => fmtUsd(total),
            },
          },
        },
      },
    },
    dataLabels: { enabled: false },
    legend: { position: "bottom" },
  };

  return (
    <DashboardCard title="Allocation" fillHeight={fillHeight}>
      {total <= 0 ? (
        <Typography color="textSecondary" py={6} textAlign="center" sx={{ flex: fillHeight ? 1 : undefined }}>
          Waiting for balance data…
        </Typography>
      ) : (
        <>
          <ChartContainer minHeight={240} sx={{ flex: fillHeight ? 1 : undefined }}>
            <Chart type="donut" height={240} width="100%" series={series} options={options} />
          </ChartContainer>
          <Stack direction="row" justifyContent="space-around" mt={1}>
            <Box textAlign="center">
              <Typography variant="caption" color="textSecondary">
                Cash
              </Typography>
              <Typography variant="body2" fontWeight={600}>
                {fmtUsd(cash)}
              </Typography>
            </Box>
            <Box textAlign="center">
              <Typography variant="caption" color="textSecondary">
                Positions
              </Typography>
              <Typography variant="body2" fontWeight={600}>
                {fmtUsd(metrics.positionsValue)}
              </Typography>
            </Box>
          </Stack>
        </>
      )}
    </DashboardCard>
  );
}
