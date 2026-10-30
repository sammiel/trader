"""Historical test of every strategy with the live bot's exact rules, sizing,
costs and circuit breakers. Writes backtests/REPORT.md, backtests/results.json
and state/enabled.json (which strategies may trade paper capital).

Run:  python -m bot.backtest
"""
import json
import math
import os
import traceback
from copy import deepcopy

import pandas as pd

from . import config, data
from .portfolio import Portfolio
from .strategies import Bounce, IndexPullback, Trend

CRYPTO_SPLIT = pd.Timestamp("2025-01-01", tz="UTC")   # out-of-sample from here
STOCK_SPLIT = pd.Timestamp("2020-01-01")
OUT = "backtests"


def simulate(strat, bars: dict, ctx_fn=None, fee_override=None):
    # The 10% drawdown breaker is a live 'stop and review' rule; in the backtest it
    # would end the test at the first 10% dip, so it is off here and DD is reported.
    pf = Portfolio(fee_override=fee_override, drawdown_breaker=False)
    prepared = {s: strat.prepare(df) for s, df in bars.items()}
    step = pd.Timedelta(strat.bar)
    events = []
    rows = {}
    for sym, d in prepared.items():
        rows[sym] = list(d.itertuples(name="Row"))
        events += [(r.Index + step, sym, i) for i, r in enumerate(rows[sym])]
    events.sort(key=lambda e: (e[0], e[1]))
    last_px, curve, last_day = {}, [], None
    for ct, sym, i in events:
        r = rows[sym][i]
        last_px[sym] = r.close
        key = f"{strat.name}:{sym}"
        eq = pf.equity(last_px)
        day = str(pd.Timestamp(ct).date())
        pf.roll_day(day, eq)
        if key in pf.positions:
            pos = pf.positions[key]
            if r.low <= pos["stop"]:
                pf.close(key, min(r.open, pos["stop"]), ct, "stop")
            else:
                new_stop, reason = strat.manage(pos, r)
                if reason:
                    pf.close(key, r.close, ct, reason)
                else:
                    pos["stop"] = new_stop
        else:
            ctx = ctx_fn(sym, r.Index) if ctx_fn else {}
            stop = strat.entry(r, ctx)
            if stop is not None and stop < r.close and pf.gate(eq) is None:
                pct = strat.p.get("position_pct")
                pf.open(key, strat.name, sym, r.close, stop, ct, eq, position_pct=pct)
        if day != last_day:
            curve.append((day, pf.equity(last_px)))
            last_day = day
    curve.append((last_day, pf.equity(last_px)))
    eqs = pd.Series({pd.Timestamp(d): v for d, v in curve})
    return pf.trades, eqs


def stats(trades, eqs, split):
    out = {}
    tdf = pd.DataFrame(trades)

    def block(t):
        if t.empty:
            return {"trades": 0}
        wins, losses = t[t.pnl > 0].pnl.sum(), -t[t.pnl <= 0].pnl.sum()
        return {"trades": int(len(t)), "win_rate": round((t.pnl > 0).mean() * 100, 1),
                "profit_factor": round(wins / losses, 2) if losses > 0 else None,
                "net_pnl": round(t.pnl.sum(), 2),
                "avg_r": round(t.r_multiple.dropna().mean(), 3),
                "avg_hold_hours": round((pd.to_datetime(t.exit_time, utc=True) -
                                         pd.to_datetime(t.entry_time, utc=True)
                                         ).dt.total_seconds().mean() / 3600, 1)}
    out["all"] = block(tdf)
    if not tdf.empty:
        ex = pd.to_datetime(tdf.exit_time, utc=True)
        sp = split if split.tzinfo else split.tz_localize("UTC")
        out["in_sample"] = block(tdf[ex < sp])
        out["out_of_sample"] = block(tdf[ex >= sp])
        out["by_year"] = {str(y): block(g) for y, g in tdf.groupby(ex.dt.year)}
    years = max((eqs.index[-1] - eqs.index[0]).days / 365.25, 1e-9)
    total = eqs.iloc[-1] / config.STARTING_CASH - 1
    dd = (eqs / eqs.cummax() - 1).min()
    out["equity"] = {"start": str(eqs.index[0].date()), "end": str(eqs.index[-1].date()),
                     "net_return_pct": round(float(total) * 100, 2),
                     "cagr_pct": round(float((1 + total) ** (1 / years) - 1) * 100, 2),
                     "max_drawdown_pct": round(float(dd) * 100, 2)}
    return out


def buy_hold(bars: dict, start, split):
    def ret(d, frm):
        d = d[d.index >= frm]
        return d.close.iloc[-1] / d.close.iloc[0] - 1 if len(d) > 1 else float("nan")
    full = sum(ret(d, start) for d in bars.values()) / len(bars)
    oos = sum(ret(d, split) for d in bars.values()) / len(bars)
    curves = [d.close[d.index >= start] / d.close[d.index >= start].iloc[0] for d in bars.values()]
    ew = pd.concat(curves, axis=1).ffill().mean(axis=1)
    return {"net_return_pct": round(float(full) * 100, 2), "oos_return_pct": round(float(oos) * 100, 2),
            "max_drawdown_pct": round(float((ew / ew.cummax() - 1).min()) * 100, 2)}


def passes(s):
    g, a, o = config.KILL_GATE, s.get("all", {}), s.get("out_of_sample", {})
    reasons = []
    if a.get("trades", 0) < g["min_trades"]:
        reasons.append(f"only {a.get('trades', 0)} trades (< {g['min_trades']})")
    if (a.get("profit_factor") or 0) < g["min_profit_factor"]:
        reasons.append(f"profit factor {a.get('profit_factor')} < {g['min_profit_factor']}")
    if (o.get("profit_factor") or 0) < 1.0:
        reasons.append(f"out-of-sample profit factor {o.get('profit_factor')} < 1.0")
    if -s["equity"]["max_drawdown_pct"] / 100 > g["max_drawdown"]:
        reasons.append(f"max drawdown {s['equity']['max_drawdown_pct']}%")
    return not reasons, reasons


def main():
    os.makedirs(OUT, exist_ok=True)
    end = data.now_utc().floor("h")
    start = pd.Timestamp("2022-11-01", tz="UTC")
    hours = int((end - start) / pd.Timedelta("1h"))
    crypto = {}
    for sym in config.CRYPTO:
        df = data.crypto_hourly(sym, hours=hours, end=end)
        crypto[sym] = data.closed_bars(df, "1h", end)
        print(sym, len(crypto[sym]), crypto[sym].index[0], crypto[sym].index[-1], flush=True)
    stocks = {}
    for sym in config.INDEX_ETFS:
        d = data.stock_daily(sym, period="max")
        stocks[sym] = d[d.index >= "2005-01-01"]
        print(sym, len(stocks[sym]), flush=True)

    trend = Trend()
    btc4 = trend.prepare(crypto["BTC-USD"])["uptrend"]

    def btc_ctx(sym, t):
        if sym == "BTC-USD":
            return {}
        v = btc4.get(t)
        return {"btc_uptrend": bool(v) if v is not None else None}

    bounce_any_p = deepcopy(config.BOUNCE)
    bounce_any_p["require_uptrend"] = False
    runs = {
        "trend": (trend, crypto, btc_ctx, CRYPTO_SPLIT),
        "bounce": (Bounce(), crypto, None, CRYPTO_SPLIT),
        "bounce_no_trend_filter": (Bounce(bounce_any_p, name="bounce_any"), crypto, None, CRYPTO_SPLIT),
        "index_pullback": (IndexPullback(), stocks, None, STOCK_SPLIT),
    }
    results = {"generated": str(end), "costs": {
        "crypto_fee": config.CRYPTO_FEE, "crypto_slippage": config.CRYPTO_SLIPPAGE,
        "stock_slippage": config.STOCK_SLIPPAGE}, "strategies": {}}
    for name, (strat, bars, ctx, split) in runs.items():
        trades, eqs = simulate(strat, bars, ctx)
        s = stats(trades, eqs, split)
        if strat.asset == "crypto":
            t_hi, e_hi = simulate(strat, bars, ctx, fee_override=0.004)
            s["at_0.4pct_fee"] = stats(t_hi, e_hi, split)["equity"]
        ok, why = passes(s)
        s["passes_kill_gate"], s["fail_reasons"] = ok, why
        results["strategies"][name] = s
        eqs.to_csv(f"{OUT}/equity_{name}.csv", header=["equity"])
        pd.DataFrame(trades).to_csv(f"{OUT}/trades_{name}.csv", index=False)
        print(name, json.dumps(s["all"]), s["equity"], ok, why, flush=True)
    results["buy_hold"] = {
        "crypto_equal_weight": buy_hold(crypto, start, CRYPTO_SPLIT),
        "index_equal_weight": buy_hold(stocks, pd.Timestamp("2005-01-01"), STOCK_SPLIT)}

    enabled = {k: results["strategies"][k]["passes_kill_gate"]
               for k in ("trend", "bounce", "index_pullback")}
    enabled["source"] = f"backtest {end}"
    os.makedirs("state", exist_ok=True)
    with open("state/enabled.json", "w") as f:
        json.dump(enabled, f, indent=2)
    with open(f"{OUT}/results.json", "w") as f:
        json.dump(results, f, indent=2, default=str)
    write_report(results, enabled)


def write_report(res, enabled):
    L = [f"# Backtest report\n\nGenerated {res['generated']}. Costs per side: crypto fee "
         f"{res['costs']['crypto_fee']*100:.2f}% + slippage {res['costs']['crypto_slippage']*100:.2f}%; "
         f"ETF slippage {res['costs']['stock_slippage']*100:.2f}%.\n",
         "| Strategy | Trades | Win % | Profit factor | Avg R | Net return | CAGR | Max DD | OOS trades | OOS PF | @0.4% fee | Gate |",
         "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for n, s in res["strategies"].items():
        a, o, e = s["all"], s.get("out_of_sample", {}), s["equity"]
        hi = s.get("at_0.4pct_fee", {}).get("net_return_pct", "n/a")
        L.append(f"| {n} | {a.get('trades')} | {a.get('win_rate')} | {a.get('profit_factor')} | "
                 f"{a.get('avg_r')} | {e['net_return_pct']}% | {e['cagr_pct']}% | {e['max_drawdown_pct']}% | "
                 f"{o.get('trades')} | {o.get('profit_factor')} | {hi}{'%' if hi != 'n/a' else ''} | "
                 f"{'PASS' if s['passes_kill_gate'] else 'FAIL: ' + '; '.join(s['fail_reasons'])} |")
    bh = res["buy_hold"]
    L.append(f"\nBuy & hold, crypto equal-weight: {bh['crypto_equal_weight']}  \n"
             f"Buy & hold, index ETFs equal-weight (2005+): {bh['index_equal_weight']}\n")
    L.append(f"\nEnabled for paper trading: `{json.dumps(enabled)}`\n")
    with open(f"{OUT}/REPORT.md", "w") as f:
        f.write("\n".join(L))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        os.makedirs(OUT, exist_ok=True)
        with open(f"{OUT}/error.txt", "w") as f:
            f.write(traceback.format_exc())
        raise
