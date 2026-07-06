'use client';

import { Stack } from '@mui/material';

import PageContainer from '@/app/(DashboardLayout)/components/container/PageContainer';
import DashboardCard from '@/app/(DashboardLayout)/components/shared/DashboardCard';
import ConnectionBanner from '@/components/bot/ConnectionBanner';
import WalletSettingsForm from '@/components/bot/WalletSettingsForm';
import { useBot } from '@/context/BotContext';
import { botApiUrl } from '@/lib/format';
import { Button, Chip, CircularProgress, Typography } from '@mui/material';
import { useCallback, useEffect, useState } from 'react';

export default function SettingsPage() {
  const { connection, reconnect } = useBot();
  const [checking, setChecking] = useState(false);
  const [healthOk, setHealthOk] = useState<boolean | null>(null);

  const runHealthCheck = useCallback(async () => {
    setChecking(true);
    try {
      const resp = await fetch(`${botApiUrl()}/health`);
      setHealthOk(resp.ok);
    } catch {
      setHealthOk(false);
    } finally {
      setChecking(false);
    }
  }, []);

  useEffect(() => {
    void runHealthCheck();
  }, [runHealthCheck, connection]);

  return (
    <PageContainer title="Settings" description="Wallet and strategy configuration">
      <Stack spacing={3}>
        <ConnectionBanner />

        <DashboardCard title="Connection">
          <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" mb={2}>
            <Chip
              label={connection === 'connected' ? 'WebSocket connected' : `WebSocket ${connection}`}
              color={connection === 'connected' ? 'success' : 'warning'}
              size="small"
            />
            {healthOk === true && (
              <Chip label="Backend OK" color="success" size="small" variant="outlined" />
            )}
            {healthOk === false && (
              <Chip label="Backend offline" color="error" size="small" variant="outlined" />
            )}
          </Stack>
          <Stack direction="row" spacing={1}>
            <Button
              variant="outlined"
              size="small"
              onClick={() => void runHealthCheck()}
              disabled={checking}
              startIcon={checking ? <CircularProgress size={14} /> : undefined}
            >
              Test
            </Button>
            <Button variant="outlined" size="small" onClick={reconnect}>
              Reconnect
            </Button>
          </Stack>
          <Typography variant="caption" color="textSecondary" display="block" mt={1}>
            API: {botApiUrl()}
          </Typography>
        </DashboardCard>

        <WalletSettingsForm />
      </Stack>
    </PageContainer>
  );
}
