"use client";

import { useMemo, useState } from "react";
import {
  Box,
  Chip,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  TableSortLabel,
  Typography,
} from "@mui/material";

import DashboardCard from "@/app/(DashboardLayout)/components/shared/DashboardCard";
import PolymarketLink from "@/components/bot/PolymarketLink";
import { fmtEta, fmtPct, fmtShares, fmtUsd, pnlColor } from "@/lib/format";
import { BotPosition } from "@/types/bot";

type SortKey = keyof BotPosition | "pot_win";

type Props = {
  positions: BotPosition[];
};

function potWin(p: BotPosition) {
  return p.size - p.initial_value;
}

function sortValue(p: BotPosition, col: SortKey): string | number {
  if (col === "title") return (p.title || p.slug || "").toLowerCase();
  if (col === "pot_win") return potWin(p);
  return Number(p[col as keyof BotPosition] ?? 0);
}

export default function PositionsTable({ positions }: Props) {
  const [sortBy, setSortBy] = useState<SortKey>("eta_seconds");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("asc");

  const sorted = useMemo(() => {
    return [...positions].sort((a, b) => {
      const va = sortValue(a, sortBy);
      const vb = sortValue(b, sortBy);
      let cmp = 0;
      if (typeof va === "string" && typeof vb === "string") cmp = va.localeCompare(vb);
      else cmp = Number(va) - Number(vb);
      return sortDir === "desc" ? -cmp : cmp;
    });
  }, [positions, sortBy, sortDir]);

  const handleSort = (col: SortKey) => {
    if (sortBy === col) setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    else {
      setSortBy(col);
      setSortDir("asc");
    }
  };

  const columns: { key: SortKey; label: string; align?: "right" | "center"; minWidth?: number }[] =
    [
      { key: "title", label: "Market", minWidth: 220 },
      { key: "outcome", label: "Side", align: "center", minWidth: 72 },
      { key: "size", label: "Shares", align: "right", minWidth: 80 },
      { key: "avg_price", label: "Avg", align: "right", minWidth: 72 },
      { key: "current_price", label: "Mark", align: "right", minWidth: 72 },
      { key: "current_value", label: "Value", align: "right", minWidth: 88 },
      { key: "pnl_usd", label: "PnL", align: "right", minWidth: 96 },
      { key: "pot_win", label: "Pot. Win", align: "right", minWidth: 96 },
      { key: "eta_seconds", label: "ETA", align: "right", minWidth: 100 },
    ];

  const positionsValue = positions.reduce((sum, p) => sum + (p.current_value || 0), 0);

  return (
    <DashboardCard
      title="Open Positions"
      subtitle={
        positions.length > 0
          ? `${positions.length} active NO position${positions.length === 1 ? "" : "s"} · ${fmtUsd(positionsValue)} deployed`
          : "Open NO positions appear here when the bot enters markets"
      }
    >
      {positions.length === 0 ? (
        <Typography color="textSecondary" py={4} textAlign="center">
          No open positions — bot is scanning for NO entries below your price cap
        </Typography>
      ) : (
        <TableContainer
          sx={{
            width: "100%",
            maxWidth: "100%",
            overflowX: "auto",
            border: "1px solid",
            borderColor: "divider",
            borderRadius: 2,
          }}
        >
          <Table size="small" stickyHeader sx={{ minWidth: 960, tableLayout: "auto" }}>
            <TableHead>
              <TableRow>
                {columns.map((col) => (
                  <TableCell
                    key={col.key}
                    align={col.align}
                    sx={{ minWidth: col.minWidth, whiteSpace: "nowrap", fontWeight: 700 }}
                  >
                    <TableSortLabel
                      active={sortBy === col.key}
                      direction={sortBy === col.key ? sortDir : "asc"}
                      onClick={() => handleSort(col.key)}
                    >
                      {col.label}
                    </TableSortLabel>
                  </TableCell>
                ))}
              </TableRow>
            </TableHead>
            <TableBody>
              {sorted.map((p) => {
                const win = potWin(p);
                const winPct = p.initial_value > 0 ? (win / p.initial_value) * 100 : 0;
                const showSlug =
                  p.slug && p.title && p.slug.toLowerCase() !== p.title.toLowerCase();
                return (
                  <TableRow key={p.asset || p.slug} hover>
                    <TableCell sx={{ maxWidth: 360 }}>
                      <PolymarketLink slug={p.slug} title={p.title || p.slug} conditionId={p.condition_id} />
                      {showSlug ? (
                        <Typography variant="caption" color="textSecondary" display="block" noWrap>
                          {p.slug}
                        </Typography>
                      ) : null}
                    </TableCell>
                    <TableCell align="center">
                      <Chip
                        label={p.outcome || "NO"}
                        size="small"
                        color={p.outcome === "No" || p.outcome === "NO" ? "primary" : "default"}
                        variant="outlined"
                      />
                    </TableCell>
                    <TableCell align="right" sx={{ whiteSpace: "nowrap" }}>
                      {fmtShares(p.size)}
                    </TableCell>
                    <TableCell align="right" sx={{ whiteSpace: "nowrap" }}>
                      {fmtUsd(p.avg_price, 4)}
                    </TableCell>
                    <TableCell align="right" sx={{ whiteSpace: "nowrap" }}>
                      {fmtUsd(p.current_price, 4)}
                    </TableCell>
                    <TableCell align="right" sx={{ whiteSpace: "nowrap" }}>
                      {fmtUsd(p.current_value)}
                    </TableCell>
                    <TableCell align="right" sx={{ whiteSpace: "nowrap" }}>
                      <Typography variant="body2" color={pnlColor(p.pnl_usd)}>
                        {fmtUsd(p.pnl_usd)}
                      </Typography>
                      <Typography variant="caption" color={pnlColor(p.pnl_pct)}>
                        {fmtPct(p.pnl_pct)}
                      </Typography>
                    </TableCell>
                    <TableCell align="right" sx={{ whiteSpace: "nowrap" }}>
                      <Typography variant="body2" color={pnlColor(win)}>
                        {fmtUsd(win)}
                      </Typography>
                      <Typography variant="caption" color={pnlColor(winPct)}>
                        {fmtPct(winPct)}
                      </Typography>
                    </TableCell>
                    <TableCell align="right" sx={{ whiteSpace: "nowrap" }}>
                      <Typography variant="body2">{fmtEta(p.eta_seconds)}</Typography>
                      <Typography variant="caption" color="textSecondary">
                        {p.end_date ? new Date(p.end_date).toLocaleDateString() : "--"}
                      </Typography>
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </TableContainer>
      )}
    </DashboardCard>
  );
}
