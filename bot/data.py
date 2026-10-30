"""Market data from free public endpoints (no API keys).
Crypto: Coinbase Exchange 1h candles, Kraken as fallback.
Stocks/ETFs: Yahoo Finance via yfinance, Stooq daily as fallback."""
import io
import time

import pandas as pd
import requests

UA = {"User-Agent": "sammiel-trader-paper-bot/1.0"}
KRAKEN = {"BTC-USD": "XBTUSD", "ETH-USD": "ETHUSD", "SOL-USD": "SOLUSD",
          "XRP-USD": "XRPUSD", "LINK-USD": "LINKUSD", "AVAX-USD": "AVAXUSD"}
COLS = ["open", "high", "low", "close", "volume"]


def now_utc() -> pd.Timestamp:
    return pd.Timestamp.now(tz="UTC")


def _get(url, params=None, tries=4):
    last = None
    for k in range(tries):
        try:
            r = requests.get(url, params=params, headers=UA, timeout=20)
            if r.status_code == 429:
                time.sleep(2 + 2 * k)
                continue
            r.raise_for_status()
            return r
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(1 + 2 * k)
    raise RuntimeError(f"GET failed {url}: {last}")


def _coinbase_hourly(product: str, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    rows, cur_end = [], end
    while cur_end > start:
        cur_start = max(start, cur_end - pd.Timedelta(hours=300))
        r = _get(f"https://api.exchange.coinbase.com/products/{product}/candles",
                 {"granularity": 3600, "start": cur_start.isoformat(),
                  "end": cur_end.isoformat()})
        rows += r.json()
        cur_end = cur_start
        time.sleep(0.15)
    if not rows:
        raise RuntimeError(f"no coinbase data for {product}")
    df = pd.DataFrame(rows, columns=["time", "low", "high", "open", "close", "volume"])
    df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
    return df.drop_duplicates("time").set_index("time").sort_index()[COLS].astype(float)


def _kraken_hourly(product: str) -> pd.DataFrame:
    r = _get("https://api.kraken.com/0/public/OHLC",
             {"pair": KRAKEN[product], "interval": 60})
    res = r.json()["result"]
    key = [k for k in res if k != "last"][0]
    df = pd.DataFrame(res[key], columns=["time", "open", "high", "low", "close",
                                         "vwap", "volume", "count"])
    df["time"] = pd.to_datetime(df["time"].astype(int), unit="s", utc=True)
    return df.set_index("time").sort_index()[COLS].astype(float)


def crypto_hourly(product: str, hours: int = 1000, end: pd.Timestamp | None = None) -> pd.DataFrame:
    """1h bars indexed by bar-open time. The last row may be the still-forming hour."""
    end = end or now_utc()
    start = end - pd.Timedelta(hours=hours)
    try:
        return _coinbase_hourly(product, start, end)
    except Exception:
        # Kraken only serves the latest 720 hours; enough for live signals.
        return _kraken_hourly(product)


def closed_bars(df: pd.DataFrame, bar: str, now: pd.Timestamp) -> pd.DataFrame:
    return df[df.index + pd.Timedelta(bar) <= now]


# ---------------------------------------------------------------- stocks
def _stooq_daily(sym: str) -> pd.DataFrame:
    r = _get("https://stooq.com/q/d/l/", {"s": f"{sym.lower()}.us", "i": "d"})
    df = pd.read_csv(io.StringIO(r.text))
    df.columns = [c.lower() for c in df.columns]
    df["date"] = pd.to_datetime(df["date"])
    return df.set_index("date")[COLS].astype(float)


def stock_daily(sym: str, period: str = "2y") -> pd.DataFrame:
    """Daily bars indexed by date (naive). Includes today's partial bar if the
    market is open (yfinance behaviour)."""
    try:
        import yfinance as yf
        h = yf.Ticker(sym).history(period=period, interval="1d", auto_adjust=True)
        if h.empty:
            raise RuntimeError("empty")
        h.index = pd.to_datetime(h.index.date)
        h.columns = [c.lower() for c in h.columns]
        return h[COLS].astype(float)
    except Exception:
        return _stooq_daily(sym)


def stock_intraday(sym: str) -> pd.DataFrame:
    """Today's 5-minute bars (UTC index). Empty if unavailable/market closed."""
    try:
        import yfinance as yf
        h = yf.Ticker(sym).history(period="1d", interval="5m", auto_adjust=True)
        h.index = h.index.tz_convert("UTC")
        h.columns = [c.lower() for c in h.columns]
        return h[COLS].astype(float)
    except Exception:
        return pd.DataFrame(columns=COLS)


def us_market_clock(now: pd.Timestamp) -> dict:
    ny = now.tz_convert("America/New_York")
    minutes = ny.hour * 60 + ny.minute
    weekday = ny.weekday() < 5
    return {"ny": ny, "date": pd.Timestamp(ny.date()),
            "open": weekday and 570 <= minutes < 960,          # 09:30-16:00
            "closing_window": weekday and 925 <= minutes < 960}  # 15:25-16:00
