"""Turn the bot's state into small JSON row files for the dashboard.
Run after `git pull`:  python -m bot.dashboard_export  -> dashboard/*.json"""
import json
import os

import pandas as pd

from . import config

OUT = "dashboard"


def _csv(p):
    return pd.read_csv(p) if os.path.exists(p) else pd.DataFrame()


def _json(p, default=None):
    try:
        with open(p) as f:
            return json.load(f)
    except FileNotFoundError:
        return default


def _rows(df):
    return json.loads(df.to_json(orient="records", date_format="iso")) if len(df) else []


def main():
    os.makedirs(OUT, exist_ok=True)
    s = _json("docs/summary.json", {})
    eq = _csv("state/equity.csv")
    trades = _csv("state/trades.csv")
    sigs = _csv("state/signals.csv")
    bt = _json("backtests/results.json", {})
    enabled = _json("state/enabled.json", {}) or {}
    health = _json("state/health.json", {})

    # Equity vs. simply holding BTC or SPY with the same $10k
    curve = []
    if len(eq):
        e = eq.copy()
        e["time"] = pd.to_datetime(e["time"])
        e = e.set_index("time").resample("1h").last().dropna(subset=["equity"])
        b0, s0 = e["btc"].dropna().iloc[0], e["spy"].dropna().iloc[0]
        e["btc_hold"] = (config.STARTING_CASH * e["btc"] / b0).round(2)
        e["spy_hold"] = (config.STARTING_CASH * e["spy"] / s0).round(2)
        she = _csv("state/shadow_equity.csv")
        if len(she):
            she["time"] = pd.to_datetime(she["time"])
            e["shadow_equity"] = she.set_index("time")["equity"].resample("1h").last().reindex(e.index).ffill()
        else:
            e["shadow_equity"] = None
        e = e.reset_index()[["time", "equity", "btc_hold", "spy_hold", "shadow_equity"]]
        e["time"] = e["time"].dt.strftime("%Y-%m-%dT%H:%M:00Z")
        curve = _rows(e)

    n = len(trades)
    wins = int((trades.pnl > 0).sum()) if n else 0
    kpi = [{
        "updated": s.get("updated", "")[:16].replace(" ", "T") + "Z",
        "equity": s.get("equity"), "return_pct": s.get("return_pct"),
        "max_drawdown_pct": s.get("max_drawdown_pct"),
        "realized_pnl": round(float(trades.pnl.sum()), 2) if n else 0.0,
        "unrealized_pnl": round(sum(p["unrealized"] for p in s.get("open_positions", [])), 2),
        "closed_trades": n, "win_rate_pct": round(100 * wins / n, 1) if n else None,
        "open_positions": len(s.get("open_positions", [])),
        "btc_hold_pct": s.get("benchmark_return_pct", {}).get("BTC-USD"),
        "spy_hold_pct": s.get("benchmark_return_pct", {}).get("SPY"),
        "bot_healthy": bool(health.get("ok")), "last_tick": health.get("time", "")[:16],
        "shadow_equity": s.get("shadow", {}).get("equity"),
        "shadow_return_pct": s.get("shadow", {}).get("return_pct"),
    }]

    strat_rows = []
    live = s.get("by_strategy", {})
    names = {"trend": "Trend breakout (4h)", "trend_daily": "Trend breakout (daily)",
             "bounce": "Oversold bounce",
             "index_pullback": "Index pullback", "core": "Long-term core"}
    for key, label in names.items():
        b = bt.get("strategies", {}).get(key, {})
        a, o, e = b.get("all", {}), b.get("out_of_sample", {}), b.get("equity", {})
        lv = live.get(key, {})
        sv = s.get("shadow", {}).get("by_strategy", {}).get(key, {})
        strat_rows.append({
            "strategy": label,
            "status": "holding" if key == "core" else ("trading" if enabled.get(key) else "off (failed gate)" if enabled else "awaiting backtest"),
            "live_trades": lv.get("trades", 0), "live_realized": lv.get("realized", 0.0),
            "live_unrealized": lv.get("unrealized", 0.0),
            "shadow_trades": None if key == "core" else sv.get("trades", 0),
            "shadow_pnl": None if key == "core" else round(sv.get("realized", 0.0) + sv.get("unrealized", 0.0), 2),
            "bt_trades": a.get("trades"), "bt_win_rate": a.get("win_rate"),
            "bt_profit_factor": a.get("profit_factor"), "bt_cagr_pct": e.get("cagr_pct"),
            "bt_max_dd_pct": e.get("max_drawdown_pct"), "bt_oos_pf": o.get("profit_factor"),
            "bt_return_at_0_4pct_fee": b.get("at_0.4pct_fee", {}).get("net_return_pct"),
        })

    pos = pd.DataFrame(s.get("open_positions", []))
    if len(pos):
        pos["position"] = pos["strategy"] + " · " + pos["symbol"]
        pos = pos[["position", "strategy", "symbol", "entry", "price", "stop", "value",
                   "unrealized", "ret_pct", "since"]]
    tr = trades.iloc[::-1].copy() if n else trades
    if n:
        tr["trade"] = tr["strategy"] + " · " + tr["symbol"] + " · " + tr["exit_time"].astype(str).str[:16]
    sg = sigs.iloc[::-1].head(50).copy() if len(sigs) else sigs
    if len(sg):
        sg["signal"] = sg["strategy"] + " · " + sg["symbol"] + " · " + sg["time"].astype(str).str[:16]

    files = {"kpi": kpi, "equity": curve, "strategies": strat_rows,
             "positions": _rows(pos), "trades": _rows(tr), "signals": _rows(sg)}
    for k, v in files.items():
        with open(f"{OUT}/{k}.json", "w") as f:
            json.dump(v, f, indent=1, default=str)
        print(k, len(v))


if __name__ == "__main__":
    main()
