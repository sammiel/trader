"""Strategy rules. Each strategy:
  prepare(bars)          -> DataFrame of bars + indicator columns
  entry(row, ctx)        -> stop price if a long entry fires on this CLOSED bar, else None
  manage(pos, row)       -> (new_stop, exit_reason or None), called on each new closed bar
Shared by the live bot and the backtester so both run identical logic."""
import math

import pandas as pd

from . import config
from .indicators import atr, ema, resample, rsi, sma


def _ok(*vals):
    return all(v is not None and not (isinstance(v, float) and math.isnan(v)) for v in vals)


class Trend:
    """Donchian breakout in an established uptrend (4h bars). Rides winners with
    an ATR chandelier trail; cuts losers at 2.5 ATR."""
    name, asset, bar = "trend", "crypto", "4h"

    def __init__(self, p=None):
        self.p = p or config.TREND

    def prepare(self, h1: pd.DataFrame) -> pd.DataFrame:
        p, d = self.p, resample(h1, "4h")
        d["ema_fast"] = ema(d["close"], p["ema_fast"])
        d["ema_slow"] = ema(d["close"], p["ema_slow"])
        d["dc_high"] = d["high"].rolling(p["breakout"]).max().shift(1)
        d["atr"] = atr(d, p["atr"])
        d["uptrend"] = (d["close"] > d["ema_slow"]) & (d["ema_fast"] > d["ema_slow"])
        return d

    def entry(self, r, ctx):
        if not _ok(r.ema_slow, r.ema_fast, r.dc_high, r.atr):
            return None
        if ctx.get("btc_uptrend") is False:      # alts only trade when BTC trends up
            return None
        if r.uptrend and r.close > r.dc_high:
            return r.close - self.p["stop_atr"] * r.atr
        return None

    def manage(self, pos, r):
        pos["hh"] = max(pos.get("hh", pos["entry"]), r.high)
        trail = pos["hh"] - self.p["trail_atr"] * r.atr if _ok(r.atr) else pos["stop"]
        return max(pos["stop"], trail), None


class Bounce:
    """Short-term oversold bounce (1h bars): RSI(2) washout below the lower
    Bollinger band, optionally only inside a 1h uptrend. Quick exit."""
    name, asset, bar = "bounce", "crypto", "1h"

    def __init__(self, p=None, name=None):
        self.p = p or config.BOUNCE
        if name:
            self.name = name

    def prepare(self, h1: pd.DataFrame) -> pd.DataFrame:
        p, d = self.p, h1.copy()
        d["rsi"] = rsi(d["close"], p["rsi_len"])
        mid = sma(d["close"], p["bb_len"])
        d["bb_low"] = mid - p["bb_std"] * d["close"].rolling(p["bb_len"]).std()
        d["trend_ema"] = ema(d["close"], p["trend_ema"])
        d["exit_sma"] = sma(d["close"], p["exit_sma"])
        d["atr"] = atr(d, p["atr"])
        return d

    def entry(self, r, ctx):
        if not _ok(r.rsi, r.bb_low, r.trend_ema, r.atr):
            return None
        if self.p["require_uptrend"] and r.close < r.trend_ema:
            return None
        if r.rsi < self.p["rsi_entry"] and r.close < r.bb_low:
            return r.close - self.p["stop_atr"] * r.atr
        return None

    def manage(self, pos, r):
        pos["bars"] = pos.get("bars", 0) + 1
        if _ok(r.exit_sma) and r.close > r.exit_sma:
            return pos["stop"], "target"
        if pos["bars"] >= self.p["max_bars"]:
            return pos["stop"], "time"
        return pos["stop"], None


class IndexPullback:
    """Connors RSI(2) on index ETFs (daily): buy short-term dips while above the
    200-day average, sell into the first bounce above the 5-day average."""
    name, asset, bar = "index_pullback", "stock", "1d"

    def __init__(self, p=None):
        self.p = p or config.INDEX_PULLBACK

    def prepare(self, daily: pd.DataFrame) -> pd.DataFrame:
        p, d = self.p, daily.copy()
        d["sma_long"] = sma(d["close"], p["sma_long"])
        d["rsi"] = rsi(d["close"], p["rsi_len"])
        d["exit_sma"] = sma(d["close"], p["exit_sma"])
        return d

    def entry(self, r, ctx):
        if not _ok(r.sma_long, r.rsi):
            return None
        if r.close > r.sma_long and r.rsi < self.p["rsi_entry"]:
            return r.close * (1 - self.p["disaster_stop"])
        return None

    def manage(self, pos, r):
        if _ok(r.exit_sma) and r.close > r.exit_sma:
            return pos["stop"], "target"
        return pos["stop"], None


def all_strategies():
    return {s.name: s for s in (Trend(), Bounce(), IndexPullback())}
