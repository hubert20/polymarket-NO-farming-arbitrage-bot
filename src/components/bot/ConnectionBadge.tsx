"use client";

import { Chip } from "@mui/material";

import { ConnectionState } from "@/types/bot";

const LABEL: Record<ConnectionState, string> = {
  connected: "Connected",
  connecting: "Connecting…",
  disconnected: "Disconnected",
};

const COLOR: Record<ConnectionState, "success" | "warning" | "error"> = {
  connected: "success",
  connecting: "warning",
  disconnected: "error",
};

export default function ConnectionBadge({ state }: { state: ConnectionState }) {
  return (
    <Chip
      label={LABEL[state]}
      color={COLOR[state]}
      size="small"
      variant="outlined"
      sx={{ fontFamily: "monospace", fontSize: "0.75rem" }}
    />
  );
}
