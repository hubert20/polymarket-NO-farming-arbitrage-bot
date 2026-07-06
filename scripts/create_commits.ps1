# Creates 56 conventional commits — each file committed exactly once.
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
Set-Location ..

function Commit-Files($Message, [string[]]$Files) {
    $existing = @($Files | Where-Object { Test-Path $_ })
    if ($existing.Count -eq 0) {
        Write-Warning "Skip (no files): $Message"
        return
    }
    git add -- $existing
    git commit -m $Message
    if ($LASTEXITCODE -ne 0) { throw "Commit failed: $Message" }
}

Commit-Files "chore: add root gitignore and eslint config" @(".gitignore", ".eslintrc.json")
Commit-Files "chore: add project license files" @("LICENSE.md", "backend/LICENSE")
Commit-Files "chore: add npm package manifest and lockfile" @("package.json", "package-lock.json")
Commit-Files "chore: add TypeScript and Next.js configuration" @("tsconfig.json", "next.config.js", "react-mui-sidebar.d.ts")
Commit-Files "feat(backend): add core bot models and utilities" @(
    "backend/bot/__init__.py", "backend/bot/models.py", "backend/bot/time_utils.py",
    "backend/bot/utils.py", "backend/bot/market.py", "backend/bot/proxy_wallet.py"
)
Commit-Files "feat(backend): add paper trading exchange client" @(
    "backend/bot/exchange/__init__.py", "backend/bot/exchange/base.py", "backend/bot/exchange/paper.py"
)
Commit-Files "feat(backend): add Polymarket CLOB exchange client" @("backend/bot/exchange/polymarket_clob.py")
Commit-Files "feat(backend): add exchange holder and latency helpers" @("backend/bot/exchange_holder.py", "backend/bot/latency.py")
Commit-Files "feat(backend): add configuration loader" @("backend/bot/config.py")
Commit-Files "feat(backend): add environment bootstrap loader" @("backend/bot/env_loader.py")
Commit-Files "feat(backend): add portfolio state tracker" @("backend/bot/portfolio_state.py")
Commit-Files "feat(backend): add strategy control state" @("backend/bot/nothing_happens_control.py")
Commit-Files "feat(backend): add standalone markets scanner with Gamma pagination handling" @("backend/bot/standalone_markets.py")
Commit-Files "feat(backend): add nothing happens NO farming strategy" @("backend/bot/strategy/__init__.py", "backend/bot/strategy/nothing_happens.py")
Commit-Files "feat(backend): add risk controls module" @("backend/bot/risk_controls.py")
Commit-Files "feat(backend): add database store and trade ledger" @("backend/bot/db.py", "backend/bot/trade_ledger.py", "backend/bot/store.py")
Commit-Files "feat(backend): add order status and reconcile helpers" @("backend/bot/order_status.py", "backend/bot/reconcile.py")
Commit-Files "feat(backend): add live recovery coordinator" @("backend/bot/live_recovery.py")
Commit-Files "feat(backend): add position redeemer" @("backend/bot/redeemer.py")
Commit-Files "feat(backend): add venue state synchronization" @("backend/bot/venue_state.py")
Commit-Files "feat(backend): add structured logging configuration" @("backend/bot/logging_config.py")
Commit-Files "feat(backend): add async runtime supervisor with Windows signal support" @("backend/bot/main.py")
Commit-Files "feat(backend): add REST and WebSocket API with CORS support" @("backend/bot/api_server.py")
Commit-Files "feat(backend): add settings manager with hot reload" @("backend/bot/settings_manager.py")
Commit-Files "feat(backend): add demo mode paper balance configuration" @("backend/bot/demo_mode.py")
Commit-Files "test(backend): add config utils and strategy tests" @("backend/tests/test_config.py", "backend/tests/test_utils.py", "backend/tests/test_nothing_happens.py", "backend/pytest.ini")
Commit-Files "test(backend): add API server and settings tests" @("backend/tests/test_api_server.py", "backend/tests/test_settings_api.py", "backend/tests/test_main_runtime.py")
Commit-Files "test(backend): add exchange recovery and ledger tests" @(
    "backend/tests/test_polymarket_clob.py", "backend/tests/test_live_recovery.py",
    "backend/tests/test_reconcile.py", "backend/tests/test_redeemer.py",
    "backend/tests/test_risk_controls.py", "backend/tests/test_store.py",
    "backend/tests/test_trade_ledger.py", "backend/tests/test_venue_state.py"
)
Commit-Files "chore(backend): add requirements and operational shell scripts" @(
    "backend/requirements.txt", "backend/Procfile", "backend/.python-version", "backend/.gitignore",
    "backend/alive.sh", "backend/kill.sh", "backend/live_disabled.sh", "backend/live_enabled.sh",
    "backend/logs.sh", "backend/logshtml.sh"
)
Commit-Files "chore(backend): add config example and maintenance scripts" @(
    "backend/config.example.json", "backend/docs/dashboard.jpg",
    "backend/scripts/db_stats.py", "backend/scripts/export_db.py",
    "backend/scripts/parse_logs.py", "backend/scripts/wallet_history.py"
)
Commit-Files "feat(frontend): add Next.js root layout and global styles" @("src/app/layout.tsx", "src/app/global.css", "src/app/loading.tsx", "src/app/favicon.ico", "src/app/icon.svg")
Commit-Files "feat(frontend): add dashboard layout shell" @("src/app/(DashboardLayout)/layout.tsx", "src/app/(DashboardLayout)/loading.tsx")
Commit-Files "feat(frontend): add sidebar navigation" @(
    "src/app/(DashboardLayout)/layout/sidebar/Sidebar.tsx",
    "src/app/(DashboardLayout)/layout/sidebar/SidebarItems.tsx",
    "src/app/(DashboardLayout)/layout/sidebar/MenuItems.tsx"
)
Commit-Files "feat(frontend): add dashboard header and profile menu" @(
    "src/app/(DashboardLayout)/layout/header/Header.tsx",
    "src/app/(DashboardLayout)/layout/header/Profile.tsx",
    "src/app/(DashboardLayout)/layout/header/data.tsx",
    "src/app/(DashboardLayout)/layout/shared/logo/Logo.tsx"
)
Commit-Files "feat(frontend): add shared dashboard UI components" @(
    "src/app/(DashboardLayout)/components/container/PageContainer.tsx",
    "src/app/(DashboardLayout)/components/shared/DashboardCard.tsx",
    "src/app/(DashboardLayout)/components/shared/BlankCard.tsx",
    "src/app/(DashboardLayout)/components/forms/theme-elements/CustomTextField.tsx"
)
Commit-Files "feat(frontend): add MUI theme and emotion cache" @("src/utils/theme.ts", "src/utils/theme/DefaultColors.tsx", "src/utils/createEmotionCache.ts")
Commit-Files "feat(frontend): add bot WebSocket context provider" @("src/context/BotContext.tsx", "src/hooks/useBotWebSocket.ts")
Commit-Files "feat(frontend): add bot types and analytics helpers" @("src/types/bot.ts", "src/lib/analytics.ts", "src/lib/format.ts", "src/lib/chartTheme.ts")
Commit-Files "feat(frontend): add settings types and API client" @("src/types/settings.ts", "src/lib/settingsApi.ts")
Commit-Files "feat(frontend): add hero summary and strategy intro" @("src/components/bot/HeroSummary.tsx", "src/components/bot/StrategyIntro.tsx")
Commit-Files "feat(frontend): add open positions table and Polymarket links" @("src/components/bot/PositionsTable.tsx", "src/lib/polymarket.ts", "src/components/bot/PolymarketLink.tsx")
Commit-Files "feat(frontend): add market funnel and allocation charts" @("src/components/bot/MarketFunnelChart.tsx", "src/components/bot/PortfolioAllocationChart.tsx", "src/components/bot/ChartContainer.tsx")
Commit-Files "feat(frontend): add balance history and session performance charts" @("src/components/bot/BalanceChart.tsx", "src/components/bot/SessionPnlCard.tsx")
Commit-Files "feat(frontend): add trade feed with fixed-height scroll" @("src/components/bot/TradeFeed.tsx")
Commit-Files "feat(frontend): add bot activity and stats panels" @("src/components/bot/BotActivityPanel.tsx", "src/components/bot/BotStatsCards.tsx")
Commit-Files "feat(frontend): add resolution and trade activity charts" @("src/components/bot/ResolutionStats.tsx", "src/components/bot/TradeActivityChart.tsx", "src/components/bot/PositionPnlChart.tsx")
Commit-Files "feat(frontend): add wallet and strategy settings form" @("src/components/bot/WalletSettingsForm.tsx")
Commit-Files "feat(frontend): add connection status banner and badge" @("src/components/bot/ConnectionBanner.tsx", "src/components/bot/ConnectionBadge.tsx")
Commit-Files "feat(frontend): add sync status card and equal-height card layout" @("src/components/bot/SyncStatusCard.tsx")
Commit-Files "ui: add Polymarket branding logo components" @("src/components/bot/AppLogo.tsx", "public/images/logos/polymarket-logo.svg", "public/images/logos/polymarket-icon.svg")
Commit-Files "feat(frontend): add main dashboard page layout" @("src/app/(DashboardLayout)/page.tsx")
Commit-Files "feat(frontend): add analytics and settings pages" @("src/app/(DashboardLayout)/analytics/page.tsx", "src/app/(DashboardLayout)/settings/page.tsx")
Commit-Files "chore(frontend): add dashboard preview gif" @("public/no-farmimg-dashboard.gif")
Commit-Files "chore(frontend): add public SVG, background, and template images" @(
    "public/next.svg", "public/vercel.svg",
    "public/images/backgrounds/login-bg.svg", "public/images/backgrounds/404-error-idea.gif",
    "public/images/backgrounds/rocket.png", "public/images/products/empty-shopping-bag.gif",
    "public/images/products/s11.jpg", "public/images/products/s4.jpg", "public/images/products/s5.jpg",
    "public/images/products/s7.jpg", "public/images/profile/user-1.jpg"
)
Commit-Files "doc: add README and Chinese documentation" @("README.md", "README.zh-CN.md")
Commit-Files "chore: add environment variable examples" @(".env.example", "backend/.env.example")

$count = [int](git rev-list --count HEAD)
Write-Host "Total commits on HEAD: $count"
