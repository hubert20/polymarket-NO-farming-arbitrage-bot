import { Alert, Typography } from "@mui/material";

export default function StrategyIntro() {
  return (
    <Alert severity="info" icon={false} sx={{ "& .MuiAlert-message": { width: "100%" } }}>
      <Typography variant="subtitle1" fontWeight={700} gutterBottom>
        Strategy: Systematic NO Farming
      </Typography>
      <Typography variant="body2" paragraph sx={{ mb: 0 }}>
        Most Polymarket markets resolve <strong>NO</strong> — crowds overpay for hype and unlikely
        “YES” outcomes. This bot scans standalone yes/no markets and buys <strong>NO</strong> when
        the price is below your cap (default 65¢), betting that reality beats narrative. You win
        often with small edges, not moonshots.
      </Typography>
      <Typography variant="body2" sx={{ fontStyle: "italic", color: "text.secondary" }}>
        Example: “Will Bitcoin hit $200k this week?” trades at 12¢ YES / 88¢ NO — the crowd piles
        into YES; you buy NO at 65¢ or less and collect when the deadline passes unchanged.
      </Typography>
    </Alert>
  );
}
