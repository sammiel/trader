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

    # Shadow book: every strategy, gated or not, on its own $10k
    sh = st.get("shadow") or {"cash": config.STARTING_CASH, "positions": {}}
    sh_eq = sh["cash"] + sum(p["qty"] * prices.get(p["symbol"], p["entry"]) for p in sh["positions"].values())
    sh_tr = _read_csv("state/shadow_trades.csv")
    sh_by = {}
    if not sh_tr.empty:
        for name, g in sh_tr.groupby("strategy"):
            sh_by[name] = {"trades": int(len(g)), "wins": int((g.pnl > 0).sum()),
                           "realized": round(g.pnl.sum(), 2)}
    for p in sh["positions"].values():
        b = sh_by.setdefault(p["strategy"], {"trades": 0, "wins": 0, "realized": 0.0})
        b["unrealized"] = round(b.get("unrealized", 0) + p["qty"] * (prices.get(p["symbol"], p["entry"]) - p["entry"]), 2)
        b["open"] = b.get("open", 0) + 1
    shadow = {"equity": round(sh_eq, 2),
              "return_pct": round((sh_eq / config.STARTING_CASH - 1) * 100, 2),
              "by_strategy": sh_by,
              "open_positions": [{"strategy": p["strategy"], "symbol": p["symbol"], "entry": p["entry"],
                                  "stop": p["stop"], "price": prices.get(p["symbol"])}
                                 for p in sh["positions"].values()]}

    bk = st.get("berkshire") or {"cash": config.STARTING_CASH, "positions": {}}
    bk_eq = bk["cash"] + sum(p["qty"] * prices.get(p["symbol"], p["entry"]) for p in bk["positions"].values())
    bk_tr = _read_csv("state/berkshire_trades.csv")
    b = config.BERKSHIRE
    start = bk.get("start_cash", config.STARTING_CASH)
    floor = start * b["floor_pct"] + b["lock_in"] * max(0.0, bk.get("peak", start) - start)
    berkshire = {"equity": round(bk_eq, 2),
                 "return_pct": round((bk_eq / config.STARTING_CASH - 1) * 100, 3),
                 "floor": round(floor, 2), "cushion": round(bk_eq - floor, 2),
                 "interest": round(bk.get("interest", 0.0), 2),
                 "trades": int(len(bk_tr)), "realized": round(float(bk_tr.pnl.sum()), 2) if len(bk_tr) else 0.0,
                 "open_positions": [{"strategy": p["strategy"], "symbol": p["symbol"], "entry": p["entry"],
                                     "stop": p["stop"], "price": prices.get(p["symbol"])}
                                    for p in bk["positions"].values()]}

    # 15-minute curves for the live page: all books + $10k held in BTC / SPY
    curves = []
    if not eq.empty:
        c = eq.copy()
        c["time"] = pd.to_datetime(c["time"])
        c = c.set_index("time").resample("15min").last().dropna(subset=["equity"])
        for name, path in (("shadow", "state/shadow_equity.csv"), ("berkshire", "state/berkshire_equity.csv")):
            o = _read_csv(path)
            if len(o):
                o["time"] = pd.to_datetime(o["time"])
                c[name] = o.set_index("time")["equity"].resample("15min").last().reindex(c.index).ffill()
            else:
                c[name] = None
        b0, s0 = c["btc"].dropna().iloc[0], c["spy"].dropna().iloc[0]
        c["btc_hold"] = config.STARTING_CASH * c["btc"] / b0
        c["spy_hold"] = config.STARTING_CASH * c["spy"] / s0
        for t, r in c.iterrows():
            curves.append({"t": t.strftime("%Y-%m-%dT%H:%MZ"),
                           **{k: (None if pd.isna(r.get(k)) else round(float(r[k]), 2))
                              for k in ("equity", "berkshire", "shadow", "btc_hold", "spy_hold")}})

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
        "shadow": shadow, "berkshire": berkshire, "curves": curves, "active_mode": config.ACTIVE_MODE,
    }
    with open("docs/summary.json", "w") as f:
        json.dump(summary, f, indent=2, default=str)
    return summary
