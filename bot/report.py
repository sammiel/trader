"""Builds docs/summary.json (read by the dashboard and the check-ins)."""
import json
import os

import pandas as pd

from . import config


def _read_csv(path):
    return pd.read_csv(path) if os.path.exists(path) else pd.DataFrame()


def write_summary(st, prices, now):
    pos = st["portfolio"]["positions"]
    cash = st["portfolio"]["cash"]
    equity = cash + sum(p["qty"] * prices.get(p["symbol"], p["entry"]) for p in pos.values())
    trades = _read_csv("state/trades.csv")
    eq = _read_csv("state/equity.csv")
    sigs = _read_csv("state/signals.csv")

    open_pos = []
    for p in pos.values():
        px = prices.get(p["symbol"], p["entry"])
        open_pos.append({"strategy": p["strategy"], "symbol": p["symbol"],
                         "entry": p["entry"], "price": px, "stop": p["stop"],
                         "value": round(p["qty"] * px, 2),
                         "unrealized": round(p["qty"] * (px - p["entry"]), 2),
                         "ret_pct": round((px / p["entry"] - 1) * 100, 2),
                         "since": p["entry_time"]})

    by_strat = {}
    if not trades.empty:
        for name, g in trades.groupby("strategy"):
            w, l = g[g.pnl > 0].pnl.sum(), -g[g.pnl <= 0].pnl.sum()
            by_strat[name] = {"trades": int(len(g)), "wins": int((g.pnl > 0).sum()),
                              "realized": round(g.pnl.sum(), 2),
                              "profit_factor": round(w / l, 2) if l > 0 else None,
                              "avg_r": round(g.r_multiple.dropna().mean(), 2)}
    for p in open_pos:
        b = by_strat.setdefault(p["strategy"], {"trades": 0, "wins": 0, "realized": 0.0})
        b["unrealized"] = round(b.get("unrealized", 0) + p["unrealized"], 2)

    curve = []
    if not eq.empty:
        e = eq.copy()
        e["time"] = pd.to_datetime(e["time"])
        e = e.set_index("time")["equity"].resample("1h").last().dropna()
        curve = [[str(t), round(v, 2)] for t, v in e.items()]
        peak = eq.equity.cummax()
        max_dd = round(((eq.equity / peak) - 1).min() * 100, 2)
    else:
        max_dd = 0.0

    bench = {}
    first = eq.iloc[0] if not eq.empty else None
    if first is not None:
        for col, sym in (("btc", "BTC-USD"), ("spy", "SPY")):
            if pd.notna(first.get(col)) and prices.get(sym):
                bench[sym] = round((prices[sym] / first[col] - 1) * 100, 2)

    summary = {
        "updated": str(now), "started": st.get("started"),
        "starting_cash": config.STARTING_CASH, "equity": round(equity, 2),
        "cash": round(cash, 2),
        "return_pct": round((equity / config.STARTING_CASH - 1) * 100, 2),
        "max_drawdown_pct": max_dd, "benchmark_return_pct": bench,
        "by_strategy": by_strat, "open_positions": open_pos,
        "recent_trades": trades.tail(25).to_dict("records") if not trades.empty else [],
        "recent_signals": sigs.tail(25).to_dict("records") if not sigs.empty else [],
        "enabled": json.load(open("state/enabled.json")) if os.path.exists("state/enabled.json") else None,
        "warnings": st.get("warnings", []), "equity_curve": curve, "prices": prices,
    }
    with open("docs/summary.json", "w") as f:
        json.dump(summary, f, indent=2, default=str)
    return summary
