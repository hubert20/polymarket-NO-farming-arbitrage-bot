"use client";

import { useCallback, useEffect, useState } from "react";
import {
  Alert,
  Box,
  Button,
  CircularProgress,
  FormControl,
  FormControlLabel,
  Grid,
  InputLabel,
  MenuItem,
  Select,
  Stack,
  Switch,
  TextField,
  Typography,
} from "@mui/material";

import DashboardCard from "@/app/(DashboardLayout)/components/shared/DashboardCard";
import { fetchSettings, saveSettings } from "@/lib/settingsApi";
import { BotSettingsPayload, defaultSettingsPayload } from "@/types/settings";

export default function WalletSettingsForm() {
  const [form, setForm] = useState<BotSettingsPayload>(defaultSettingsPayload());
  const [preview, setPreview] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<{ type: "success" | "error"; text: string } | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await fetchSettings();
      setPreview(data.private_key_preview);
      setForm({
        bot_mode: data.bot_mode,
        live_trading_enabled: data.live_trading_enabled,
        dry_run: data.dry_run,
        demo_mode: data.demo_mode ?? true,
        private_key: "",
        funder_address: data.funder_address,
        database_url: "",
        polygon_rpc_url: "",
        connection: { signature_type: data.connection.signature_type },
        strategy: { ...data.strategy },
      });
    } catch (e) {
      setMessage({ type: "error", text: e instanceof Error ? e.message : "Load failed" });
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const update = <K extends keyof BotSettingsPayload>(key: K, value: BotSettingsPayload[K]) => {
    setForm((prev) => ({ ...prev, [key]: value }));
  };

  const handleSave = async () => {
    setSaving(true);
    setMessage(null);
    try {
      const payload = { ...form };
      if (!payload.private_key) delete payload.private_key;
      if (!payload.database_url) delete payload.database_url;
      if (!payload.polygon_rpc_url) delete payload.polygon_rpc_url;
      const result = await saveSettings(payload);
      setMessage({ type: "success", text: result.message || "Saved" });
      await load();
    } catch (e) {
      setMessage({ type: "error", text: e instanceof Error ? e.message : "Save failed" });
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <DashboardCard title="Wallet & Strategy">
        <Box display="flex" justifyContent="center" py={4}>
          <CircularProgress size={28} />
        </Box>
      </DashboardCard>
    );
  }

  return (
    <DashboardCard title="Wallet & Strategy">
      <Stack spacing={3}>
        {message && <Alert severity={message.type}>{message.text}</Alert>}

        <Alert severity="info" variant="outlined">
          <strong>Demo mode</strong> uses a simulated wallet (default $7,535 balance, +$732 session
          PnL) and does not send real orders. Market data is still live from Polymarket.
          Turn off demo mode and configure a wallet for real trading.
        </Alert>

        <FormControlLabel
          control={
            <Switch
              checked={form.demo_mode}
              onChange={(e) => update("demo_mode", e.target.checked)}
            />
          }
          label="Demo mode (simulated balance, no real bets)"
        />

        <Typography variant="subtitle2" color="textSecondary">
          Trading mode
        </Typography>
        <Grid container spacing={2}>
          <Grid size={{ xs: 12, sm: 4 }}>
            <FormControl fullWidth size="small">
              <InputLabel>Mode</InputLabel>
              <Select
                label="Mode"
                value={form.bot_mode}
                onChange={(e) => update("bot_mode", e.target.value)}
              >
                <MenuItem value="paper">Paper</MenuItem>
                <MenuItem value="live">Live</MenuItem>
              </Select>
            </FormControl>
          </Grid>
          <Grid size={{ xs: 6, sm: 4 }}>
            <FormControlLabel
              control={
                <Switch
                  checked={form.live_trading_enabled}
                  onChange={(e) => update("live_trading_enabled", e.target.checked)}
                />
              }
              label="Live trading enabled"
            />
          </Grid>
          <Grid size={{ xs: 6, sm: 4 }}>
            <FormControlLabel
              control={
                <Switch
                  checked={form.dry_run}
                  onChange={(e) => update("dry_run", e.target.checked)}
                />
              }
              label="Dry run"
            />
          </Grid>
        </Grid>

        <Typography variant="subtitle2" color="textSecondary">
          Wallet (stored in project root `.env`)
        </Typography>
        <Grid container spacing={2}>
          <Grid size={12}>
            <TextField
              fullWidth
              size="small"
              type="password"
              label="Private key"
              placeholder={preview ? `Current: ${preview}` : "0x…"}
              value={form.private_key}
              onChange={(e) => update("private_key", e.target.value)}
              helperText="Leave blank to keep existing key"
            />
          </Grid>
          <Grid size={{ xs: 12, md: 6 }}>
            <TextField
              fullWidth
              size="small"
              label="Funder / proxy address"
              value={form.funder_address}
              onChange={(e) => update("funder_address", e.target.value)}
            />
          </Grid>
          <Grid size={{ xs: 12, md: 6 }}>
            <FormControl fullWidth size="small">
              <InputLabel>Signature type</InputLabel>
              <Select
                label="Signature type"
                value={form.connection.signature_type}
                onChange={(e) =>
                  update("connection", { signature_type: Number(e.target.value) })
                }
              >
                <MenuItem value={0}>EOA (0)</MenuItem>
                <MenuItem value={1}>Poly proxy (1)</MenuItem>
                <MenuItem value={2}>Gnosis Safe (2)</MenuItem>
              </Select>
            </FormControl>
          </Grid>
          <Grid size={12}>
            <TextField
              fullWidth
              size="small"
              type="password"
              label="Database URL (live mode)"
              placeholder="Leave blank to keep existing"
              value={form.database_url}
              onChange={(e) => update("database_url", e.target.value)}
            />
          </Grid>
          <Grid size={12}>
            <TextField
              fullWidth
              size="small"
              label="Polygon RPC URL"
              placeholder="Leave blank to keep existing"
              value={form.polygon_rpc_url}
              onChange={(e) => update("polygon_rpc_url", e.target.value)}
            />
          </Grid>
        </Grid>

        <Typography variant="subtitle2" color="textSecondary">
          Strategy parameters
        </Typography>
        <Grid container spacing={2}>
          <Grid size={{ xs: 6, md: 4 }}>
            <TextField
              fullWidth
              size="small"
              type="number"
              label="Max NO entry price"
              inputProps={{ step: 0.01, min: 0.01, max: 1 }}
              value={form.strategy.max_entry_price}
              onChange={(e) =>
                update("strategy", {
                  ...form.strategy,
                  max_entry_price: parseFloat(e.target.value) || 0.65,
                })
              }
            />
          </Grid>
          <Grid size={{ xs: 6, md: 4 }}>
            <TextField
              fullWidth
              size="small"
              type="number"
              label="Cash % per trade"
              inputProps={{ step: 0.01, min: 0.01, max: 1 }}
              value={form.strategy.cash_pct_per_trade}
              onChange={(e) =>
                update("strategy", {
                  ...form.strategy,
                  cash_pct_per_trade: parseFloat(e.target.value) || 0.02,
                })
              }
            />
          </Grid>
          <Grid size={{ xs: 6, md: 4 }}>
            <TextField
              fullWidth
              size="small"
              type="number"
              label="Min trade ($)"
              value={form.strategy.min_trade_amount}
              onChange={(e) =>
                update("strategy", {
                  ...form.strategy,
                  min_trade_amount: parseFloat(e.target.value) || 5,
                })
              }
            />
          </Grid>
        </Grid>

        <Stack direction="row" spacing={1}>
          <Button variant="contained" onClick={() => void handleSave()} disabled={saving}>
            {saving ? "Saving…" : "Save settings"}
          </Button>
          <Button variant="outlined" onClick={() => void load()} disabled={saving}>
            Reset
          </Button>
        </Stack>

        <Alert severity="warning" variant="outlined">
          Live orders require Mode=live, Live trading enabled, and Dry run off. Strategy changes
          apply immediately to config; restart the bot process if behavior does not update.
        </Alert>
      </Stack>
    </DashboardCard>
  );
}
