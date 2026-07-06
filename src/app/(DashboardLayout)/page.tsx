"use client";

import type { ReactNode } from "react";
import { Box, Grid, Stack, Typography } from "@mui/material";

import PageContainer from "@/app/(DashboardLayout)/components/container/PageContainer";
import BalanceChart from "@/components/bot/BalanceChart";
import BotActivityPanel from "@/components/bot/BotActivityPanel";
import ConnectionBanner from "@/components/bot/ConnectionBanner";
import HeroSummary from "@/components/bot/HeroSummary";
import MarketFunnelChart from "@/components/bot/MarketFunnelChart";
import PortfolioAllocationChart from "@/components/bot/PortfolioAllocationChart";
import PositionsTable from "@/components/bot/PositionsTable";
import ResolutionStats from "@/components/bot/ResolutionStats";
import StrategyIntro from "@/components/bot/StrategyIntro";
import SyncStatusCard from "@/components/bot/SyncStatusCard";
import TradeFeed from "@/components/bot/TradeFeed";
import { useBot } from "@/context/BotContext";

function RowGrid({ children }: { children: ReactNode }) {
  return (
    <Grid container spacing={3} sx={{ width: "100%", alignItems: "stretch" }}>
      {children}
    </Grid>
  );
}

function RowCell({ children }: { children: ReactNode }) {
  return (
    <Grid size={{ xs: 12, md: 4 }} sx={{ display: "flex", minWidth: 0 }}>
      <Box sx={{ flex: 1, width: "100%", minWidth: 0 }}>{children}</Box>
    </Grid>
  );
}

export default function DashboardPage() {
  const { portfolio, sessionPnl, trades, balanceHistory, resolutions, lastUpdated } = useBot();

  return (
    <PageContainer title="NO Farming Bot" description="Polymarket systematic NO strategy">
      <Stack spacing={3} sx={{ width: "100%", minWidth: 0 }}>
        <Box sx={{ minWidth: 0 }}>
          <Typography variant="h4" fontWeight={700}>
            NO Farming Dashboard
          </Typography>
          {lastUpdated && (
            <Typography variant="caption" color="textSecondary" display="block" mt={0.5}>
              Last update {lastUpdated.toLocaleTimeString()}
            </Typography>
          )}
        </Box>

        <ConnectionBanner />
        <StrategyIntro />
        <HeroSummary portfolio={portfolio} sessionPnl={sessionPnl} />
        <PositionsTable positions={portfolio?.positions ?? []} />

        <RowGrid>
          <RowCell>
            <MarketFunnelChart portfolio={portfolio} fillHeight />
          </RowCell>
          <RowCell>
            <PortfolioAllocationChart portfolio={portfolio} fillHeight />
          </RowCell>
          <RowCell>
            <BotActivityPanel portfolio={portfolio} fillHeight />
          </RowCell>
        </RowGrid>

        <RowGrid>
          <RowCell>
            <ResolutionStats trades={trades} resolutions={resolutions} fillHeight />
          </RowCell>
          <RowCell>
            <TradeFeed trades={trades} resolutions={resolutions} />
          </RowCell>
          <RowCell>
            <SyncStatusCard portfolio={portfolio} fillHeight />
          </RowCell>
        </RowGrid>

        <BalanceChart points={balanceHistory} />
      </Stack>
    </PageContainer>
  );
}
