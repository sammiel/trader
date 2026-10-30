"""Paper portfolio: cash, positions, fills with fees + slippage, risk sizing,
and the portfolio-level circuit breakers. Used by live bot and backtester."""
from . import config


def costs(symbol: str):
    if symbol.endswith("-USD"):
        return config.CRYPTO_FEE, config.CRYPTO_SLIPPAGE
    return config.STOCK_FEE, config.STOCK_SLIPPAGE


class Portfolio:
    def __init__(self, cash=config.STARTING_CASH, state=None, fee_override=None,
                 drawdown_breaker=True):
        s = state or {}
        self.cash = s.get("cash", cash)
        self.positions = s.get("positions", {})     # key -> dict
        self.trades = []                            # closed trades this session
        self.peak = s.get("peak", cash)
        self.day = s.get("day")
        self.day_start = s.get("day_start", cash)
        self.fee_override = fee_override
        self.drawdown_breaker = drawdown_breaker

    # ------------------------------------------------------------- helpers
    def _costs(self, sym):
        fee, slip = costs(sym)
        if self.fee_override is not None and sym.endswith("-USD"):
            fee = self.fee_override
        return fee, slip

    def equity(self, prices: dict) -> float:
        return self.cash + sum(p["qty"] * prices.get(p["symbol"], p["entry"])
                               for p in self.positions.values())

    def active_count(self):
        return sum(1 for p in self.positions.values() if p["strategy"] != "core")

    def to_state(self):
        return {"cash": self.cash, "positions": self.positions, "peak": self.peak,
                "day": self.day, "day_start": self.day_start}

    # --------------------------------------------------------- risk gates
    def roll_day(self, day: str, equity: float):
        if self.day != day:
            self.day, self.day_start = day, equity
        self.peak = max(self.peak, equity)

    def gate(self, equity: float):
        """Return None if new entries are allowed, else the reason they are not."""
        if self.drawdown_breaker and equity < self.peak * (1 - config.DRAWDOWN_BREAKER):
            return "drawdown_breaker"
        if equity < self.day_start * (1 - config.DAILY_LOSS_HALT):
            return "daily_loss_halt"
        if self.active_count() >= config.MAX_OPEN_POSITIONS:
            return "max_positions"
        return None

    # -------------------------------------------------------------- fills
    def size(self, equity, price, stop, position_pct=None):
        if position_pct:
            notional = equity * position_pct
        else:
            risk_per_unit = price - stop
            if risk_per_unit <= 0:
                return 0.0
            notional = min(equity * config.RISK_PER_TRADE / risk_per_unit * price,
                           equity * config.MAX_POSITION_PCT)
        notional = min(notional, self.cash * 0.995)
        return max(notional, 0.0) / price

    def open(self, key, strategy, symbol, price, stop, when, equity, position_pct=None,
             qty=None, note=""):
        fee, slip = self._costs(symbol)
        fill = price * (1 + slip)
        qty = qty if qty is not None else self.size(equity, fill, stop, position_pct)
        if qty * fill < 10:          # ignore dust-sized orders
            return None
        cost = qty * fill * (1 + fee)
        if cost > self.cash:
            qty = self.cash / (fill * (1 + fee))
            cost = self.cash
        self.cash -= cost
        pos = {"key": key, "strategy": strategy, "symbol": symbol, "qty": qty,
               "entry": fill, "stop": stop, "init_stop": stop, "entry_time": str(when),
               "entry_fee": qty * fill * fee, "hh": fill, "bars": 0, "note": note}
        self.positions[key] = pos
        return pos

    def close(self, key, price, when, reason):
        pos = self.positions.pop(key)
        fee, slip = self._costs(pos["symbol"])
        fill = price * (1 - slip)
        proceeds = pos["qty"] * fill * (1 - fee)
        self.cash += proceeds
        pnl = proceeds - pos["qty"] * pos["entry"] - pos["entry_fee"]
        risk = pos["qty"] * (pos["entry"] - pos["init_stop"])
        t = {"strategy": pos["strategy"], "symbol": pos["symbol"],
             "entry_time": pos["entry_time"], "exit_time": str(when),
             "entry": round(pos["entry"], 6), "exit": round(fill, 6),
             "qty": pos["qty"], "pnl": round(pnl, 2),
             "ret_pct": round((fill / pos["entry"] - 1) * 100, 3),
             "r_multiple": round(pnl / risk, 3) if risk > 0 else None,
             "reason": reason}
        self.trades.append(t)
        return t
