"use client";

import dynamic from "next/dynamic";
import { useTheme } from "@mui/material/styles";

import DashboardCard from "@/app/(DashboardLayout)/components/shared/DashboardCard";
import ChartContainer from "@/components/bot/ChartContainer";
import { BalancePoint } from "@/types/bot";

const Chart = dynamic(() => import("react-apexcharts"), { ssr: false });

type Props = {
  points: BalancePoint[];
};

export default function BalanceChart({ points }: Props) {
  const theme = useTheme();
  const primary = theme.palette.primary.main;

  const series = [
    {
      name: "Balance",
      data: points.map((p) => [p.ts, p.balance]),
    },
  ];

  const options: Record<string, unknown> = {
    chart: {
      type: "area",
      fontFamily: theme.typography.fontFamily,
      foreColor: theme.palette.text.secondary,
      toolbar: { show: false },
      zoom: { enabled: false },
    },
    colors: [primary],
    dataLabels: { enabled: false },
    stroke: { curve: "smooth", width: 2 },
    fill: {
      type: "gradient",
      gradient: { shadeIntensity: 0.4, opacityFrom: 0.45, opacityTo: 0.05 },
    },
    xaxis: { type: "datetime" },
    yaxis: {
      labels: {
        formatter: (v: number) => "$" + Number(v).toFixed(0),
      },
    },
    tooltip: {
      x: { format: "MMM dd HH:mm" },
      y: { formatter: (v: number) => "$" + Number(v).toFixed(2) },
    },
    grid: { borderColor: theme.palette.divider },
  };

  return (
    <DashboardCard title="Balance History">
      <ChartContainer minHeight={280}>
        {points.length < 2 ? (
          <Chart
            type="area"
            height={280}
            width="100%"
            series={[{ name: "Balance", data: [] }]}
            options={{ ...options, noData: { text: "Balance data appears after first poll" } }}
          />
        ) : (
          <Chart type="area" height={280} width="100%" series={series} options={options} />
        )}
      </ChartContainer>
    </DashboardCard>
  );
}
