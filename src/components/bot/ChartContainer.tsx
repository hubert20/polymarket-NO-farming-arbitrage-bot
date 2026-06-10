"use client";

import { Box } from "@mui/material";
import type { ReactNode } from "react";

type Props = {
  children: ReactNode;
  minHeight?: number;
  sx?: object;
};

/** Keeps Apex charts inside card bounds on narrow viewports. */
export default function ChartContainer({ children, minHeight, sx }: Props) {
  return (
    <Box
      sx={{
        width: "100%",
        minWidth: 0,
        overflow: "hidden",
        minHeight,
        "& .apexcharts-canvas svg": { maxWidth: "100%" },
        ...sx,
      }}
    >
      {children}
    </Box>
  );
}
