# Polymarket NO Farming 机器人

**Polymarket 系统化 NO 策略** — 实时仪表盘 + Python 交易引擎。

> 仅供学习娱乐，非投资建议。交易风险自负。

![NO Farming Dashboard](./public/no-farmimg-dashboard.gif)

## 策略说明（新手向）

**Polymarket**（https://polymarket.com）是预测市场。每个市场是一个是/否问题，例如：“本周比特币会到 20 万美元吗？”

- **YES（是）** = 你认为会发生  
- **NO（否）** = 你认为**不会**发生  

**NO 农场策略：** 很多市场 YES 被炒高，NO 反而便宜。机器人自动扫描市场，在 NO 低于上限（默认 **65¢**）时买入，每笔只用约 **2%** 资金，分散风险，等市场结算。

**示例：** YES 12¢、NO 88¢ — 不追 YES，在 NO ≤ 65¢ 时小仓位买入，结算为 NO 时获利。

**实战参考（完整链接）：** https://polymarket.com/@filthybera  

完整英文说明见 [README.md](./README.md)。

## 运行

```bash
npm install
pip install -r backend/requirements.txt
cp .env.example .env
cp backend/config.example.json backend/config.json
```

终端 1：`cd backend && python -m bot.main`  
终端 2：`npm run dev` → http://localhost:3000

完整说明见 [README.md](./README.md)。

## 打赏

`0xc6D6a8f2D2f42C29a9a50E292BCAF3Dd1b6FE581`
