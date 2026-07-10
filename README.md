# Ondo Perps Market Maker Bot

Professional-style **two-sided market maker** for [Ondo Perps](https://ondoperps.xyz) — quotes **gold (XAU)** and **silver (XAG)** perpetuals.

Places **bid + ask** limit orders near the live book, earns spread + maker rebates, and manages inventory with skew and portfolio hedging.

> **Risk warning:** This bot trades real money. You can lose your deposit. No profit is guaranteed. Use only funds you can afford to lose.

---

## What this bot does

| Feature | Description |
|---------|-------------|
| **Touch quoting** | Posts 1 tick from best bid / best ask (competes for fills) |
| **Two-sided MM** | Bid + ask at the same time |
| **Inventory skew** | Shifts quotes when position builds (classic MM behavior) |
| **Portfolio hedge** | Net XAU + XAG exposure management |
| **Vol spreads** | Slightly wider quotes in volatile markets |
| **Risk limits** | Daily loss cap, min margin, vol pause |
| **Shared account** | Uses `pmm_` order prefix — safe to run with other bots on same API key |

---

## Requirements

- **Windows 10/11** (or Linux/macOS with minor path tweaks)
- **Python 3.11+** — [python.org/downloads](https://www.python.org/downloads/)
- **Ondo Perps account** with USDC deposited
- **API keys** from Ondo (Settings → API Keys)

---

## Install (Windows PowerShell)

### 1. Clone the repo

```powershell
git clone https://github.com/ItzJulkar/ondo-perps-mm-bot.git
cd ondo-perps-mm-bot
```

### 2. Install dependencies

```powershell
python -m pip install -r requirements.txt
```

### 3. Create your config

```powershell
copy config.example.yaml config.yaml
copy .env.example .env
```

Edit `.env` with your API keys:

```env
ONDO_KEY_ID=ondoKeyId_xxxxxxxx
ONDO_API_SECRET=ondoApiSecret_xxxxxxxx
```

**Never share or commit `.env`** — it is gitignored.

### 4. Test connection

```powershell
python scripts/check_connection.py
```

You should see your balance and sample MM bid/ask prices near the live book.

---

## Run the bot

```powershell
# Start (background, 24/7 while PC is on)
python -m src.main start

# Check status + last log lines
python -m src.main status

# Stop
python -m src.main stop
```

Logs: `logs/mm-bot.log`

### After PC restart

The bot does **not** auto-start with Windows. Run again:

```powershell
cd ondo-perps-mm-bot
python -m src.main start
```

---

## Configuration (`config.yaml`)

| Setting | Default | What it does |
|---------|---------|--------------|
| `mm.touch_offset_ticks` | `1` | Ticks from BBO (lower = closer to fills) |
| `mm.margin_budget_pct` | `40` | % of available margin this bot uses |
| `mm.quote_refresh_sec` | `8` | Min seconds before cancel/replace |
| `portfolio.max_portfolio_delta_usd` | `18` | Max net metals exposure |
| `risk.daily_loss_limit_usd` | `0.75` | Pause quoting after this session loss |
| `bot.order_prefix` | `pmm_` | Order ID prefix (don't change if sharing account) |

Copy `config.example.yaml` → `config.yaml` and tune for your account size.

---

## Running with another bot

This bot only manages orders starting with `pmm_`. Another bot (e.g. single-maker) can use a different prefix (`single_`) on the **same API key**.

- MM bot uses **40%** of available margin by default
- Set `risk.shared_account_mode: true` (default) so it doesn't fight the other bot for margin ratio limits

---

## How pro MM works (simplified)

1. **Join the queue** at best bid / best ask (+1 tick for post-only safety)
2. **Earn spread** when both sides fill (buy lower, sell higher)
3. **Skew quotes** when inventory grows — discourage adding to a losing side
4. **Hedge portfolio** — if net long gold+silver, shift quotes to reduce exposure
5. **Requote** only when the book moves — let orders rest and fill

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `Missing ONDO_KEY_ID` | Create `.env` from `.env.example` |
| `forbidden_country` | Ondo blocks some regions — use a VPS in allowed country or trade from PC at home |
| No fills | Normal in quiet markets; bot quotes at touch but needs counterparty flow |
| `insufficient_margin` | Deposit more USDC or lower `margin_budget_pct` |
| Orders not cancelling | Run `python -m src.main stop` |

---

## Project structure

```
ondo-perps-mm-bot/
├── config.yaml          # your live settings (create from example)
├── config.example.yaml
├── .env                 # API keys (create from example, never commit)
├── requirements.txt
├── scripts/
│   └── check_connection.py
└── src/
    ├── main.py          # start | stop | status | run
    ├── bot.py
    ├── daemon.py
    ├── exchange/ondo.py # Ondo REST API
    └── mm/
        ├── engine.py    # main MM loop
        ├── quoter.py    # touch pricing + skew
        ├── inventory.py
        ├── portfolio.py
        └── risk.py
```

---

## Disclaimer

This software is provided **as-is** with no warranty. Trading perpetual futures involves substantial risk of loss. The authors are not responsible for any financial losses. Always test with small size first.

---

## Links

- [Ondo Perps](https://ondoperps.xyz)
- [Ondo API Docs](https://docs.ondoperps.xyz)