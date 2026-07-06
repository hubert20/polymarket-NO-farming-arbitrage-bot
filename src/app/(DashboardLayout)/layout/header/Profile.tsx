'use client';

import Link from 'next/link';
import { IconButton, Tooltip } from '@mui/material';
import { IconSettings } from '@tabler/icons-react';

export default function Profile() {
  return (
    <Tooltip title="Settings">
      <IconButton component={Link} href="/settings" color="inherit" aria-label="settings">
        <IconSettings size={22} stroke={1.5} />
      </IconButton>
    </Tooltip>
  );
}
