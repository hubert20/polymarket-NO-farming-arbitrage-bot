"use client";

import { Alert, Button, Stack } from "@mui/material";

import { useBot } from "@/context/BotContext";

export default function ConnectionBanner() {
  const { connection, reconnect, portfolio, health } = useBot();

  if (connection === "connected" && portfolio) return null;

  if (connection === "connected" && health?.demo_mode && !portfolio) {
    return (
      <Alert severity="info">
        Connected in demo mode — loading live Polymarket market data…
      </Alert>
    );
  }

  if (connection === "connected" && !portfolio) {
    return (
      <Alert severity="warning" action={<Button color="inherit" size="small" onClick={reconnect}>Retry</Button>}>
        Backend connected but no portfolio data yet. Enable <strong>Demo mode</strong> in Settings
        or connect a wallet for live paper trading.
      </Alert>
    );
  }

  if (connection === "connected") return null;

  return (
    <Alert
      severity={connection === "connecting" ? "info" : "warning"}
      action={
        connection === "disconnected" ? (
          <Button color="inherit" size="small" onClick={reconnect}>
            Retry
          </Button>
        ) : undefined
      }
    >
      <Stack direction="row" spacing={1} alignItems="center">
        <span>
          {connection === "connecting"
            ? "Connecting to bot backend…"
            : "Backend disconnected — start the Python bot or check NEXT_PUBLIC_BOT_WS_URL"}
        </span>
      </Stack>
    </Alert>
  );
}
