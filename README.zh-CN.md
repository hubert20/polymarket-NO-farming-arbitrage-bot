# Polymarket NO Farming 机器人

**Polymarket 系统化 NO 策略** — 实时仪表盘 + Python 交易引擎。

> 仅供学习娱乐，非投资建议。交易风险自负。

![NO Farming Dashboard](./public/no-farmimg-dashboard.gif)

实战参考：同类 NO 农场策略见 Polymarket 用户 [**@filthybera**](https://polymarket.com/@filthybera)。

## 运行

```bash
npm install
pip install -r backend/requirements.txt
cp .env.example .env.local
cp backend/config.example.json backend/config.json
cp backend/.env.example backend/.env
```

终端 1：`cd backend && python -m bot.main`  
终端 2：`npm run dev` → http://localhost:3000

完整说明见 [README.md](./README.md)。

## 打赏

`0xc6D6a8f2D2f42C29a9a50E292BCAF3Dd1b6FE581`
