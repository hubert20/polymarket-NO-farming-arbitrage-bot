"use client";

import OpenInNewIcon from "@mui/icons-material/OpenInNew";
import { Link, Stack, Typography } from "@mui/material";

import { polymarketMarketUrl } from "@/lib/polymarket";

type Props = {
  slug: string;
  title?: string;
  conditionId?: string;
  showIcon?: boolean;
};

export default function PolymarketLink({
  slug,
  title,
  conditionId,
  showIcon = true,
}: Props) {
  const href = polymarketMarketUrl(slug, conditionId);
  const label = title || slug || "View on Polymarket";

  if (!slug) {
    return (
      <Typography variant="body2" color="textSecondary">
        —
      </Typography>
    );
  }

  return (
    <Link
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      underline="hover"
      color="inherit"
      sx={{ display: "block", minWidth: 0 }}
    >
      <Stack direction="row" alignItems="flex-start" spacing={0.5} sx={{ minWidth: 0 }}>
        <Typography
          variant="body2"
          fontWeight={600}
          sx={{
            overflow: "hidden",
            textOverflow: "ellipsis",
            display: "-webkit-box",
            WebkitLineClamp: 2,
            WebkitBoxOrient: "vertical",
          }}
        >
          {label}
        </Typography>
        {showIcon ? (
          <OpenInNewIcon sx={{ fontSize: 14, mt: 0.25, flexShrink: 0, color: "primary.main" }} />
        ) : null}
      </Stack>
    </Link>
  );
}
