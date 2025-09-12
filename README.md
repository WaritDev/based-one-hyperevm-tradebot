Based Tradebot (HyperEVM)

Python bot for trading on Based One HyperEVM.
Supports automatic Take Profit / Stop Loss, partial TP, trailing stop, and risk management.
Includes real-time monitoring of position status and PnL, with easy deployment via Docker.

⸻

📦 Features
- Supports both Long / Short (configurable via env)
- Order entry modes: Maker / Taker / Maker-Chase
- Save fees by using maker mode
- Auto TP / SL calculation based on ROE%, Leverage, and Volatility
- Partial Take Profit (TP1 / TP2)
- Dynamic Trailing Stop (adjust SL as ROE increases)
- Risk Management
- Risk per trade (%)
- Minimum Risk/Reward filter
- Daily Drawdown Limit (stop trading for the day when exceeded)
- Cooldown after consecutive losses
- Equity Tracker monitors balance, daily PnL, and high-water mark
- Clean CLI dashboard with color output
- Runs on both mainnet and testnet
- Fully containerized with Docker

⸻

⚙️ Requirements
- Docker (>= 20.10)
- Docker Compose (>= 2.0)
- Your Wallet Web3 Private Key
- Python 3.10+ (for local run)

⸻

🔑 Environment Variables

Create a .env file at the project root:
```
# API key
PRIVATE_KEY=0x....

# Network
IS_MAINNET=true

# Trading settings
SYMBOL=BTC
SIZE=0.01
LEVERAGE=20

# TP/SL base (ROE%)
TP_ROE_PCT=2
SL_ROE_PCT=1

# Risk Management
RISK_PER_TRADE_PCT=0.4
RR_MIN=1.2
DAILY_DD_LIMIT_PCT=3
COOLDOWN_SEC=60

# Entry / Exit mode
ENTRY_MODE=taker        # maker | maker_chase | taker
EXIT_FALLBACK_TAKER=true
MAKER_OFFSET_PCT=0.0002

# Partial TP
PARTIAL_TP_RATIO=0.5
TP2_EXTRA_MULT=0.8

# Builder / Client ID
INCLUDE_BUILDER=true
BUILDER_ADDR=0x1924b8561eef20e70ede628a296175d358be80e5
BUILDER_FEE_TENTH_BPS=25
CLIENT_ID=0xba5ed11067f2cc08ba5ed1
```

⸻

🚀 Run with Docker Compose
```
# Build image
docker compose build

# Start container
docker compose up -d

# View logs
docker compose logs -f
```

⸻

📊 Example Log
```
✅ Bot started | symbol=BTC aid=0 size=0.01 tif=Gtc/Ioc | lev=20x
Targets: TP≥2% SL≥1% + VOL dyn (RR≥1.2x)

>> ENTER LONG 0.01@115200
🟩 TP1=115345.7 | TP2=115347.1 | SL=115172.8
[hold] mid=115220 | entry=115200 | ROE=0.35% | equity=5000.00
```

⸻

🛠 Development (Local Run)
```
# Install dependencies
pip install -r requirements.txt

# Run the bot
python based-tradebot.py
```