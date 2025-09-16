## Based Tradebot (Hyperliquid Spot)

A Python-based market-making bot for Hyperliquid Spot markets.
Designed for high-frequency trading (up to dozens of orders per minute),
with range guard, auto-cancel, position closing, and real-time monitoring.

Built with modular architecture (src/mm_bot/) and deployable via Docker + Uvicorn/FastAPI.

---

## 📦 Features
- High-Frequency Market Making
- Place BUY and SELL orders each minute (configurable quota).
- Balance between buys/sells with IMBALANCE_SELL_BOOST.
- Range Guard
- If the mid price goes outside your configured range → auto-cancel all orders + close position.
- Auto Cancel
- Unfilled orders are cancelled automatically after ORDER_TTL_SEC.
- Position Management
- Immediate Close (IOC) when leaving range or shutting down.
- Retry Engine
- Retries with tick-size adjustment on order errors.
- CLI Dashboard
- Clean, fixed-width terminal panel with live stats (orders, volume, imbalance, etc.).
- REST API (via FastAPI)
- Ready for Render or any Dockerized deployment.

---

## ⚙️ Requirements
- Python 3.11+
- Docker 20.10+ and Docker Compose 2.0+
- Hyperliquid account + wallet private key

---

## 🔑 Environment Variables (.env)

Create a .env file at the project root:
```
# Wallet & Network
PRIVATE_KEY=0x...                     # Wallet private key
IS_MAINNET=true                       # true=mainnet, false=testnet
BASE_URL=https://api.hyperliquid.xyz  # Hyperliquid API endpoint

# Builder (optional fee rebates)
INCLUDE_BUILDER=true
BUILDER_ADDR=0x1924b8561eef20e70ede628a296175d358be80e5
BUILDER_FEE_TENTH_BPS=100
CLIENT_ID=0xba5ed11067f2cc08ba5ed10000ba5ed1

# Trading Pair & Size
SPOT_SYMBOL=@223
SIZE=100

# Frequency & Behavior
ORDERS_PER_MINUTE=40
BUY_PER_MIN=20
SELL_PER_MIN=20
START_SIDE=buy
IMBALANCE_SELL_BOOST=1

# Order Settings
POST_ONLY=true
RETRIES=5
ORDER_TTL_SEC=20

# Range Guard (±%)
RANGE_PCT=0.03

# Authentication (optional external service)
USER_ADDR=0x66...
PASSWORD=wa...
AUTH_API_URL=https://script.google.com/macros/s/.../exec
AUTH_API_TOKEN=...
```

---

## 🚀 Run with Docker Compose
```
# Build
docker compose build

# Start
docker compose up -d

# Logs
docker compose logs -f
```

---

## 📊 Example Dashboard
```
┌====================================== Market Maker Bot ======================================┐
│ Pair: @223  Index: 223  AssetID: 10223         Tick: 0.000001  Lot: 1     Uptime: 2m 12s     │
├──────────────────────────────────────────────────────────────────────────────────────────────┤
│ Mid: 0.126985                      Range: [0.123175 … 0.130795]                             │
├──────────────────────────────────────────────────────────────────────────────────────────────┤
│ Orders: 12 (Buy 7 / Sell 5)        Volume (base): 1200   Notional≈ 152.45                   │
│ Cancels: 2   Closes: 1   Imbalance(B-S): +2                                                 │
├──────────────────────────────────────────────────────────────────────────────────────────────┤
│ This minute → Buy 3/20 (rem 17) | Sell 2/20 (rem 18) | Target: 40 ops/min  Size: 100        │
├──────────────────────────────────────────────────────────────────────────────────────────────┤
│ Last: BUY 100 @~0.126980 (±3 ticks)                                                         │
└================================================================================================┘
```

---

## 🛠 Development (Local Run)
```
# Install deps
pip install -r requirements.txt

# Run bot directly
python -m src.mm_bot.main
```
## Or run the API server + bot:
```
export PYTHONPATH=src
python server.py
```
---

## ☁️ Deploy on Render
	•	Use this Github URL
	•	Render will auto-build with Dockerfile
	•	Exposes FastAPI server with /health

---