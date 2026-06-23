"use client";

import Image from "next/image";
import Link from "next/link";
import { Box, Typography } from "@mui/material";

type Props = {
  showSubtitle?: boolean;
  compact?: boolean;
};

export default function AppLogo({ showSubtitle = true, compact = false }: Props) {
  return (
    <Box
      component={Link}
      href="/"
      sx={{
        display: "flex",
        flexDirection: "column",
        alignItems: "flex-start",
        textDecoration: "none",
        color: "inherit",
        minWidth: 0,
      }}
    >
      <Image
        src={compact ? "/images/logos/polymarket-icon.svg" : "/images/logos/polymarket-logo.svg"}
        alt="Polymarket"
        width={compact ? 34 : 168}
        height={32}
        priority
        style={{ height: 32, width: "auto", maxWidth: "100%" }}
      />
      {showSubtitle && !compact ? (
        <Typography variant="caption" color="textSecondary" sx={{ mt: 0.75, pl: 0.25 }}>
          NO Farming Bot
        </Typography>
      ) : null}
    </Box>
  );
}
