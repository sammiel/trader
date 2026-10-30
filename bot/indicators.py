import numpy as np
import pandas as pd


def ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False, min_periods=n).mean()


def sma(s: pd.Series, n: int) -> pd.Series:
    return s.rolling(n, min_periods=n).mean()


def rsi(s: pd.Series, n: int) -> pd.Series:
    d = s.diff()
    up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    out = 100 - 100 / (1 + up / dn.replace(0, np.nan))
    out = out.where(dn != 0, 100.0)
    return out.where(dn.notna())


def atr(df: pd.DataFrame, n: int) -> pd.Series:
    pc = df["close"].shift(1)
    tr = pd.concat([df["high"] - df["low"], (df["high"] - pc).abs(),
                    (df["low"] - pc).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / n, adjust=False, min_periods=n).mean()


def resample(df: pd.DataFrame, rule: str) -> pd.DataFrame:
    """Resample 1h OHLCV (index = bar-open UTC time) to a bigger timeframe,
    keeping only complete buckets."""
    g = df.resample(rule, label="left", closed="left")
    out = g.agg({"open": "first", "high": "max", "low": "min",
                 "close": "last", "volume": "sum"})
    need = int(pd.Timedelta(rule) / pd.Timedelta("1h"))
    out = out[g["close"].count() >= need]
    return out.dropna(subset=["close"])
