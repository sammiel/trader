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
# Added after the first backtest (30 Oct): same rules on daily candles. The
# research says crypto momentum held up at multi-day horizons but faded at
# short ones, and daily bars trade far less, so costs bite less. Treat it as
# a second look at the data: it must pass the same gate AND the paper test.
TREND_DAILY = dict(timeframe="1D", ema_fast=50, ema_slow=200, breakout=20,
                   atr=14, stop_atr=2.5, trail_atr=3.0)
BOUNCE = dict(timeframe="1h", rsi_len=2, rsi_entry=5, bb_len=20, bb_std=2.5,
              trend_ema=200, exit_sma=5, atr=14, stop_atr=3.0, max_bars=36,
              require_uptrend=True)
INDEX_PULLBACK = dict(timeframe="1d", sma_long=200, rsi_len=2, rsi_entry=10,
                      exit_sma=5, position_pct=0.20, disaster_stop=0.08)

# Strategies only get paper capital if they pass the backtest kill gate.
# backtest.py rewrites state/enabled.json; these are the fallbacks.
DEFAULT_ENABLED = {"trend": True, "trend_daily": True, "bounce": True, "index_pullback": True}

KILL_GATE = dict(min_trades=30, min_profit_factor=1.15, max_drawdown=0.25)

# --- Operating modes --------------------------------------------------------
# normal    : the rules above.
# berkshire : capital preservation ("Rule No. 1: never lose money"). Idle cash
#             earns a T-bill yield; the starting capital is a floor; only the
#             cushion above the floor (interest + profits) is ever put at risk,
#             sized so that every open position gapping far beyond its stop at
#             once still leaves the account above the floor. If equity touches
#             the floor, everything is sold to cash.
# Both run side by side on paper. ACTIVE_MODE is the book a future live
# broker connection would follow.
ACTIVE_MODE = "normal"
BERKSHIRE = dict(
    floor_pct=1.00,          # floor = 100% of starting capital
    lock_in=0.50,            # half of every new high above start raises the floor
    cash_yield=0.039,        # T-bill yield on idle cash (Fed funds 3.75-4.00%)
    risk_of_cushion=0.25,    # one trade may lose at most 25% of the cushion at its stop
    gap_share=0.50,          # ...and at most 50% of the cushion in the gap scenario
    gap_crypto=0.15,         # assume crypto can gap 15% beyond its stop...
    gap_stock=0.08,          # ...and ETFs 8%, all at the same time
    strategies=("trend", "trend_daily", "index_pullback"),  # never the fee-heavy bounce
)
