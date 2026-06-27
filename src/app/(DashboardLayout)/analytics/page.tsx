'use client';

import { Grid, Stack, Typography } from '@mui/material';

import PageContainer from '@/app/(DashboardLayout)/components/container/PageContainer';
import BalanceChart from '@/components/bot/BalanceChart';
import ConnectionBanner from '@/components/bot/ConnectionBanner';
import MarketFunnelChart from '@/components/bot/MarketFunnelChart';
import PositionPnlChart from '@/components/bot/PositionPnlChart';
import PositionsTable from '@/components/bot/PositionsTable';
import ResolutionStats from '@/components/bot/ResolutionStats';
import TradeActivityChart from '@/components/bot/TradeActivityChart';
import { useBot } from '@/context/BotContext';
import {
  computePortfolioMetrics,
  computeTradeStats,
  computeResolutionStats,
} from '@/lib/analytics';
import DashboardCard from '@/app/(DashboardLayout)/components/shared/DashboardCard';
import { fmtPct, fmtUsd } from '@/lib/format';

export default function AnalyticsPage() {
  const { portfolio, trades, balanceHistory, resolutions } = useBot();
  const metrics = computePortfolioMetrics(portfolio);
  const tradeStats = computeTradeStats(trades);
  const resolutionStats = computeResolutionStats(trades, resolutions);

  return (
    <PageContainer title="Analytics" description="Deep dive into bot performance">
      <Stack spacing={3}>
        <Typography variant="h4" fontWeight={700}>
          Analytics
        </Typography>
        <ConnectionBanner />

        <Grid container spacing={3}>
          <Grid size={{ xs: 6, sm: 3 }}>
            <DashboardCard>
              <Typography variant="caption" color="textSecondary">
                Unrealized PnL
              </Typography>
              <Typography variant="h5" fontWeight={700}>
                {fmtUsd(metrics.unrealizedPnl)}
              </Typography>
            </DashboardCard>
          </Grid>
          <Grid size={{ xs: 6, sm: 3 }}>
            <DashboardCard>
              <Typography variant="caption" color="textSecondary">
                Avg position return
              </Typography>
              <Typography variant="h5" fontWeight={700}>
                {fmtPct(metrics.avgPnlPct)}
              </Typography>
            </DashboardCard>
          </Grid>
          <Grid size={{ xs: 6, sm: 3 }}>
            <DashboardCard>
              <Typography variant="caption" color="textSecondary">
                Buy volume
              </Typography>
              <Typography variant="h5" fontWeight={700}>
                {fmtUsd(tradeStats.totalBuyVolume)}
              </Typography>
            </DashboardCard>
          </Grid>
          <Grid size={{ xs: 6, sm: 3 }}>
            <DashboardCard>
              <Typography variant="caption" color="textSecondary">
                NO win rate
              </Typography>
              <Typography variant="h5" fontWeight={700}>
                {resolutionStats.resolved > 0
                  ? `${resolutionStats.winRate.toFixed(1)}%`
                  : '—'}
              </Typography>
            </DashboardCard>
          </Grid>
        </Grid>

        <PositionsTable positions={portfolio?.positions ?? []} />

        <Grid container spacing={3} sx={{ width: '100%' }}>
          <Grid size={{ xs: 12, lg: 6 }}>
            <PositionPnlChart positions={portfolio?.positions ?? []} />
          </Grid>
          <Grid size={{ xs: 12, lg: 6 }}>
            <TradeActivityChart trades={trades} />
          </Grid>
          <Grid size={{ xs: 12, md: 6 }}>
            <MarketFunnelChart portfolio={portfolio} />
          </Grid>
          <Grid size={{ xs: 12, md: 6 }}>
            <ResolutionStats trades={trades} resolutions={resolutions} />
          </Grid>
          <Grid size={12}>
            <BalanceChart points={balanceHistory} />
          </Grid>
        </Grid>
      </Stack>
    </PageContainer>
  );
}
