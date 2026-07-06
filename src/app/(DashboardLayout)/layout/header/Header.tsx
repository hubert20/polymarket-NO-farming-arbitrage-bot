'use client';

import React from 'react';
import { Box, AppBar, Toolbar, styled, Stack, IconButton, Chip } from '@mui/material';
import Link from 'next/link';
import Profile from './Profile';
import { IconMenu } from '@tabler/icons-react';
import ConnectionBadge from '@/components/bot/ConnectionBadge';
import AppLogo from '@/components/bot/AppLogo';
import { useBot } from '@/context/BotContext';
import { tradingModeLabel } from '@/lib/analytics';

interface ItemType {
  toggleMobileSidebar: (event: React.MouseEvent<HTMLElement>) => void;
}

const AppBarStyled = styled(AppBar)(({ theme }) => ({
  boxShadow: 'none',
  background: theme.palette.background.paper,
  justifyContent: 'center',
  backdropFilter: 'blur(4px)',
  [theme.breakpoints.up('lg')]: {
    minHeight: '70px',
  },
}));

const ToolbarStyled = styled(Toolbar)(({ theme }) => ({
  width: '100%',
  color: theme.palette.text.secondary,
}));

const Header = ({ toggleMobileSidebar }: ItemType) => {
  const { connection, health } = useBot();
  const mode = tradingModeLabel(health);
  const isLive =
    !health?.demo_mode &&
    health?.bot_mode === 'live' &&
    !health?.dry_run &&
    health?.live_trading_enabled;
  const modeColor = health?.demo_mode ? 'info' : isLive ? 'error' : 'default';

  return (
    <AppBarStyled position="sticky" color="default">
      <ToolbarStyled>
        <IconButton
          color="inherit"
          aria-label="menu"
          onClick={toggleMobileSidebar}
          sx={{ display: { lg: 'none', xs: 'inline' } }}
        >
          <IconMenu width="20" height="20" />
        </IconButton>

        <Box sx={{ display: { xs: 'inline-flex', lg: 'none' }, ml: 0.5 }}>
          <AppLogo showSubtitle={false} compact />
        </Box>

        <Chip
          label={mode}
          size="small"
          color={modeColor}
          variant="outlined"
          component={Link}
          href="/settings"
          clickable
          sx={{ ml: { xs: 0, lg: 1 } }}
        />

        <Box flexGrow={1} />

        <Stack spacing={1} direction="row" alignItems="center">
          <ConnectionBadge state={connection} />
          <Profile />
        </Stack>
      </ToolbarStyled>
    </AppBarStyled>
  );
};

export default Header;
