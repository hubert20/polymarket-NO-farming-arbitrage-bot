"use client";

import dynamic from "next/dynamic";
import { useTheme } from "@mui/material/styles";
import { Typography } from "@mui/material";

import DashboardCard from "@/app/(DashboardLayout)/components/shared/DashboardCard";
import ChartContainer from "@/components/bot/ChartContainer";
import { baseChartOptions } from "@/lib/chartTheme";
import { fmtUsd } from "@/lib/format";
import { BotPosition } from "@/types/bot";

const Chart = dynamic(() => import("react-apexcharts"), { ssr: false });

type Props = { positions: BotPosition[] };

export default function PositionPnlChart({ positions }: Props) {
  const theme = useTheme();
  const sorted = [...positions]
    .sort((a, b) => Math.abs(b.pnl_usd) - Math.abs(a.pnl_usd))
    .slice(0, 8);

  const categories = sorted.map((p) => {
    const name = p.title || p.slug;
    return name.length > 28 ? name.slice(0, 26) + "…" : name;
  });
  const data = sorted.map((p) => p.pnl_usd);
  const colors = data.map((v) =>
    v >= 0 ? theme.palette.success.main : theme.palette.error.main,
  );

  const options: Record<string, unknown> = {
    ...baseChartOptions(theme),
    chart: { ...baseChartOptions(theme).chart, type: "bar" },
    plotOptions: {
      bar: {
        horizontal: true,
        borderRadius: 4,
        distributed: true,
        barHeight: "65%",
      },
    },
    colors,
    xaxis: {
      categories,
      labels: {
        formatter: (v: number) => fmtUsd(v),
      },
    },
    dataLabels: { enabled: false },
    legend: { show: false },
    tooltip: {
      y: { formatter: (v: number) => fmtUsd(v) },
    },
  };

  return (
    <DashboardCard title="Position PnL">
      {positions.length === 0 ? (
        <Typography color="textSecondary" py={6} textAlign="center">
          No open positions to chart
        </Typography>
      ) : (
        <ChartContainer>
          <Chart
            type="bar"
            height={Math.max(180, sorted.length * 42)}
            width="100%"
            series={[{ data }]}
            options={options}
          />
        </ChartContainer>
      )}
    </DashboardCard>
  );
}
