"""All tunable settings in one place. Parameters come from published rules
(Donchian/Turtle-style breakouts, Connors RSI(2)) rather than curve-fitting."""

STARTING_CASH = 10_000.0

# --- Universe -------------------------------------------------------------
CRYPTO = ["BTC-USD", "ETH-USD", "SOL-USD", "XRP-USD", "LINK-USD", "AVAX-USD"]
INDEX_ETFS = ["SPY", "QQQ", "IWM"]

# --- Costs (per side) -----------------------------------------------------
# Crypto: assumes a low-fee exchange tier (~0.10% taker) plus slippage.
# Retail tiers on some exchanges are 0.4-0.6% taker: the backtest reports
# that scenario too, and most short-term edges do not survive it.
CRYPTO_FEE = 0.0010
CRYPTO_SLIPPAGE = 0.0008
STOCK_FEE = 0.0
STOCK_SLIPPAGE = 0.0003

# --- Portfolio risk rules -------------------------------------------------
RISK_PER_TRADE = 0.0075        # lose at most 0.75% of equity if the stop is hit
MAX_POSITION_PCT = 0.20        # no single active position above 20% of equity
MAX_OPEN_POSITIONS = 5         # active (non-core) positions at once
DAILY_LOSS_HALT = 0.02         # down 2% on the UTC day -> no new entries today
DRAWDOWN_BREAKER = 0.10        # 10% below peak equity -> no new entries at all

# --- Long-term core sleeve (bought once, held) ----------------------------
CORE = {"BTC-USD": 0.10, "SPY": 0.10}   # fraction of starting equity

# --- Strategy parameters --------------------------------------------------
TREND = dict(timeframe="4h", ema_fast=50, ema_slow=200, breakout=20,
             atr=14, stop_atr=2.5, trail_atr=3.0)
BOUNCE = dict(timeframe="1h", rsi_len=2, rsi_entry=5, bb_len=20, bb_std=2.5,
              trend_ema=200, exit_sma=5, atr=14, stop_atr=3.0, max_bars=36,
              require_uptrend=True)
INDEX_PULLBACK = dict(timeframe="1d", sma_long=200, rsi_len=2, rsi_entry=10,
                      exit_sma=5, position_pct=0.20, disaster_stop=0.08)

# Strategies only get paper capital if they pass the backtest kill gate.
# backtest.py rewrites state/enabled.json; these are the fallbacks.
DEFAULT_ENABLED = {"trend": True, "bounce": True, "index_pullback": True}

KILL_GATE = dict(min_trades=30, min_profit_factor=1.15, max_drawdown=0.25)
