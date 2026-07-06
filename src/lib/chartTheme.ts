import { Theme } from "@mui/material/styles";

export type ApexBaseOptions = {
  chart: {
    fontFamily: string;
    foreColor: string;
    toolbar: { show: boolean };
    type?: string;
    sparkline?: { enabled: boolean };
    zoom?: { enabled: boolean };
  };
  grid: { borderColor: string; strokeDashArray: number };
  legend: { labels: { colors: string }; position?: string; show?: boolean };
  tooltip: { theme: string; y?: { formatter: (v: number) => string } };
};

export function baseChartOptions(theme: Theme): ApexBaseOptions {
  return {
    chart: {
      fontFamily: String(theme.typography.fontFamily ?? "inherit"),
      foreColor: theme.palette.text.secondary,
      toolbar: { show: false },
    },
    grid: { borderColor: theme.palette.divider, strokeDashArray: 4 },
    legend: { labels: { colors: theme.palette.text.secondary } },
    tooltip: { theme: theme.palette.mode },
  };
}
