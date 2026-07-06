"use client";

import dynamic from "next/dynamic";
import { useTheme } from "@mui/material/styles";
import { Typography } from "@mui/material";

import DashboardCard from "@/app/(DashboardLayout)/components/shared/DashboardCard";
import ChartContainer from "@/components/bot/ChartContainer";
import { baseChartOptions } from "@/lib/chartTheme";
import { computeTradeStats } from "@/lib/analytics";
import { BotTradeMessage } from "@/types/bot";

const Chart = dynamic(() => import("react-apexcharts"), { ssr: false });

type Props = { trades: BotTradeMessage[] };

export default function TradeActivityChart({ trades }: Props) {
  const theme = useTheme();
  const buys = trades
    .filter((t) => t.action === "buy" && t.ts)
    .slice(0, 50)
    .reverse();

  const series = [
    {
      name: "Buy size",
      data: buys.map((t) => [t.ts! * 1000, t.amount ?? 0]),
    },
  ];

  const stats = computeTradeStats(trades);

  const options: Record<string, unknown> = {
    ...baseChartOptions(theme),
    chart: { ...baseChartOptions(theme).chart, type: "bar", zoom: { enabled: true } },
    plotOptions: {
      bar: { borderRadius: 4, columnWidth: "60%" },
    },
    colors: [theme.palette.secondary.main],
    xaxis: { type: "datetime" },
    yaxis: {
      labels: { formatter: (v: number) => "$" + Number(v).toFixed(0) },
    },
    dataLabels: { enabled: false },
  };

  return (
    <DashboardCard
      title="Trade Activity"
      action={
        <Typography variant="caption" color="textSecondary">
          {stats.buys} buys · {stats.successRate.toFixed(0)}% fill rate
        </Typography>
      }
    >
      {buys.length === 0 ? (
        <Typography color="textSecondary" py={6} textAlign="center">
          Buy events will appear here as the bot trades
        </Typography>
      ) : (
        <ChartContainer minHeight={260}>
          <Chart type="bar" height={260} width="100%" series={series} options={options} />
        </ChartContainer>
      )}
    </DashboardCard>
  );
}
