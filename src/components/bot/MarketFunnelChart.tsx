"use client";

import dynamic from "next/dynamic";
import { useTheme } from "@mui/material/styles";
import { Box, Typography } from "@mui/material";

import DashboardCard from "@/app/(DashboardLayout)/components/shared/DashboardCard";
import ChartContainer from "@/components/bot/ChartContainer";
import { baseChartOptions } from "@/lib/chartTheme";
import { computeMarketFunnel } from "@/lib/analytics";
import { PortfolioMessage } from "@/types/bot";

const Chart = dynamic(() => import("react-apexcharts"), { ssr: false });

type Props = { portfolio: PortfolioMessage | null; fillHeight?: boolean };

export default function MarketFunnelChart({ portfolio, fillHeight }: Props) {
  const theme = useTheme();
  const funnel = computeMarketFunnel(portfolio);

  const series = [
    { name: "Markets", data: [funnel.monitored, funnel.eligible, funnel.inRange] },
  ];

  const options: Record<string, unknown> = {
    ...baseChartOptions(theme),
    chart: { ...baseChartOptions(theme).chart, type: "bar" },
    plotOptions: {
      bar: {
        horizontal: true,
        borderRadius: 6,
        distributed: true,
        barHeight: "55%",
      },
    },
    colors: [theme.palette.primary.main, theme.palette.info.main, theme.palette.success.main],
    xaxis: {
      categories: ["Monitored", "Eligible", "In Range (NO cheap)"],
    },
    dataLabels: {
      enabled: true,
      formatter: (val: number) => String(Math.round(val)),
    },
    legend: { show: false },
  };

  return (
    <DashboardCard title="Market Scan Funnel" fillHeight={fillHeight}>
      <ChartContainer minHeight={240} sx={{ flex: fillHeight ? 1 : undefined }}>
        <Chart type="bar" height={240} width="100%" series={series} options={options} />
      </ChartContainer>
      <Box display="flex" justifyContent="space-between" mt={1}>
        <Typography variant="caption" color="textSecondary">
          {funnel.eligiblePct.toFixed(1)}% pass filters
        </Typography>
        <Typography variant="caption" color="textSecondary">
          {funnel.inRangePct.toFixed(1)}% in entry range
        </Typography>
      </Box>
    </DashboardCard>
  );
}
