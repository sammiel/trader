"""One live paper-trading tick. GitHub Actions runs this every 15 minutes.
Reads state/, pulls live prices, manages stops/exits, takes new entries,
writes state/ and docs/summary.json.

Run:  python -m bot.run
"""
import csv
import json
import os
import traceback

import pandas as pd

from . import config, data
from .portfolio import Portfolio
from .strategies import all_strategies

STATE = "state/state.json"
TEST_START = "2026-10-30"
TEST_END = pd.Timestamp("2026-11-06 21:30", tz="UTC")   # Fri Nov 6, after US close


def log(msg, now):
    line = f"{now:%Y-%m-%d %H:%M}Z  {msg}"
    print(line, flush=True)
    with open("state/events.log", "a") as f:
        f.write(line + "\n")


def append_csv(path, row: dict):
    new = not os.path.exists(path)
    with open(path, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(row))
        if new:
            w.writeheader()
        w.writerow(row)


def load_json(path, default):
    try:
        with open(path) as f:
            return json.load(f)
    except FileNotFoundError:
        return default


def main():
    os.makedirs("state", exist_ok=True)
    os.makedirs("docs", exist_ok=True)
    now = data.now_utc()
    st = load_json(STATE, {})
    if now > TEST_END and st:
        log("test window over: no trading (edit TEST_END in bot/run.py to extend)", now)
        return
    enabled = load_json("state/enabled.json", None)
    pf = Portfolio(state=st.get("portfolio"))
    last_eval = st.get("last_eval", {})
    warnings = []

    # ------------------------------------------------------------ data
    h1, prices = {}, {}
    for sym in config.CRYPTO:
        try:
            df = data.crypto_hourly(sym, hours=1000, end=now)
            h1[sym] = df
            prices[sym] = float(df.close.iloc[-1])
        except Exception as e:  # noqa: BLE001
            warnings.append(f"{sym} data failed: {e}")
    clock = data.us_market_clock(now)
    daily, intraday = {}, {}
    for sym in config.INDEX_ETFS:
        try:
            daily[sym] = data.stock_daily(sym, period="2y")
            intraday[sym] = data.stock_intraday(sym) if clock["open"] else pd.DataFrame()
            last = intraday[sym].close.iloc[-1] if len(intraday[sym]) else daily[sym].close.iloc[-1]
            prices[sym] = float(last)
        except Exception as e:  # noqa: BLE001
            warnings.append(f"{sym} data failed: {e}")

    # ------------------------------------------------- first run: core
    if not st:
        eq0 = config.STARTING_CASH
        for sym, frac in config.CORE.items():
            if sym in prices:
                p = pf.open(f"core:{sym}", "core", sym, prices[sym], 0.0, now, eq0,
                            qty=eq0 * frac / (prices[sym] * 1.002), note="long-term hold")
                log(f"CORE BUY {sym} qty={p['qty']:.6f} @ {p['entry']:.2f}", now)
        st = {"started": str(now)}

    equity = pf.equity(prices)
    pf.roll_day(str(now.date()), equity)

    # ------------------------------------------ 1) protective stops
    last_tick = pd.Timestamp(st.get("last_tick", str(now - pd.Timedelta("15min"))))
    for key, pos in list(pf.positions.items()):
        if pos["strategy"] == "core" or pos["symbol"] not in prices:
            continue
        sym = pos["symbol"]
        entered = pd.Timestamp(pos["entry_time"])
        if sym in h1:   # only hourly bars that started after the entry
            since = max(last_tick.floor("h"), entered.ceil("h"))
            recent = h1[sym][h1[sym].index >= since]
        else:
            ib = intraday.get(sym, pd.DataFrame())
            recent = ib[ib.index >= max(last_tick, entered)] if len(ib) else ib
        fill = None
        if len(recent) and recent.low.min() <= pos["stop"]:
            hit = recent[recent.low <= pos["stop"]].iloc[0]
            fill = min(hit.open, pos["stop"])
        elif prices[sym] <= pos["stop"]:
            fill = prices[sym]
        if fill is not None:
            t = pf.close(key, fill, now, "stop")
            log(f"STOP {key} exit {t['exit']:.4f} pnl {t['pnl']:+.2f} ({t['r_multiple']}R)", now)
            append_csv("state/trades.csv", t)

    # ------------------------------- 2) signals on newly closed bars
    strategies = all_strategies()
    btc_up = None
    if "BTC-USD" in h1:
        b4 = strategies["trend"].prepare(data.closed_bars(h1["BTC-USD"], "1h", now))
        btc_up = bool(b4.uptrend.iloc[-1]) if len(b4) else None

    for name, strat in strategies.items():
        allowed = (enabled or config.DEFAULT_ENABLED).get(name, False) and enabled is not None
        for sym in (config.CRYPTO if strat.asset == "crypto" else config.INDEX_ETFS):
            if sym not in prices:
                continue
            key = f"{name}:{sym}"
            if strat.asset == "crypto":
                d = strat.prepare(data.closed_bars(h1[sym], "1h", now))
                if d.empty:
                    continue
                bar_id = str(d.index[-1])
            else:
                if not clock["closing_window"]:
                    continue                     # decide on daily bars near the close
                dd = daily[sym][daily[sym].index < clock["date"]].copy()
                ib = intraday.get(sym, pd.DataFrame())
                if not len(ib):
                    continue
                dd.loc[clock["date"]] = [ib.open.iloc[0], ib.high.max(), ib.low.min(),
                                         ib.close.iloc[-1], ib.volume.sum()]
                d = strat.prepare(dd)
                bar_id = str(clock["date"].date())
            if last_eval.get(key) == bar_id:
                continue
            last_eval[key] = bar_id
            r = next(d.iloc[[-1]].itertuples(name="Row"))
            px = prices[sym]
            if key in pf.positions:
                pos = pf.positions[key]
                new_stop, reason = strat.manage(pos, r)
                if reason:
                    t = pf.close(key, px, now, reason)
                    log(f"EXIT {key} ({reason}) {t['exit']:.4f} pnl {t['pnl']:+.2f} ({t['r_multiple']}R)", now)
                    append_csv("state/trades.csv", t)
                elif new_stop > pos["stop"]:
                    log(f"TRAIL {key} stop {pos['stop']:.4f} -> {new_stop:.4f}", now)
                    pos["stop"] = new_stop
                continue
            ctx = {"btc_uptrend": btc_up} if (name == "trend" and sym != "BTC-USD") else {}
            stop = strat.entry(r, ctx)
            if stop is None or stop >= px:
                continue
            sig = {"time": str(now), "strategy": name, "symbol": sym, "price": px,
                   "stop": round(stop, 6), "bar": bar_id}
            if not allowed:
                sig["action"] = "skipped: strategy disabled by backtest gate" if enabled else "skipped: awaiting backtest"
                append_csv("state/signals.csv", sig)
                continue
            equity = pf.equity(prices)
            blocked = pf.gate(equity)
            if blocked:
                sig["action"] = f"skipped: {blocked}"
                append_csv("state/signals.csv", sig)
                log(f"SIGNAL {key} skipped ({blocked})", now)
                continue
            pos = pf.open(key, name, sym, px, stop, now, equity,
                          position_pct=strat.p.get("position_pct"))
            if pos:
                sig["action"] = "opened"
                append_csv("state/signals.csv", sig)
                log(f"BUY {key} qty={pos['qty']:.6f} @ {pos['entry']:.4f} stop {stop:.4f} "
                    f"(${pos['qty']*pos['entry']:.0f})", now)

    # ------------------------------------------------------- record
    equity = pf.equity(prices)
    pf.roll_day(str(now.date()), equity)
    append_csv("state/equity.csv", {
        "time": now.strftime("%Y-%m-%d %H:%M"), "equity": round(equity, 2),
        "cash": round(pf.cash, 2), "open_positions": len(pf.positions),
        "btc": prices.get("BTC-USD"), "spy": prices.get("SPY")})
    for w in warnings:
        log(f"WARN {w}", now)
    st.update({"portfolio": pf.to_state(), "last_eval": last_eval, "last_tick": str(now),
               "warnings": warnings, "prices": prices})
    with open(STATE, "w") as f:
        json.dump(st, f, indent=2, default=str)
    from .report import write_summary
    write_summary(st, prices, now)


if __name__ == "__main__":
    try:
        main()
        status = {"ok": True}
    except Exception:
        status = {"ok": False, "error": traceback.format_exc()}
        print(status["error"])
    status["time"] = str(data.now_utc())
    os.makedirs("state", exist_ok=True)
    with open("state/health.json", "w") as f:
        json.dump(status, f, indent=2)
