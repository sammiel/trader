# trader — paper-trading bot (no real money)

Runs on GitHub Actions every 15 minutes with a simulated **$10,000** account.

| Path | What it is |
|---|---|
| `bot/config.py` | Universe, costs, risk rules, strategy parameters |
| `bot/strategies.py` | Entry/exit rules (shared by live bot and backtest) |
| `bot/run.py` | One live tick: prices → stops → signals → paper fills → state |
| `bot/backtest.py` | Historical test + kill gate → `state/enabled.json` |
| `state/` | Live portfolio (`state.json`), `trades.csv`, `equity.csv`, `signals.csv`, `events.log`, `health.json` |
| `docs/summary.json` | Current snapshot for the dashboard |
| `backtests/REPORT.md` | Backtest results |

**Strategies**
- `trend` — crypto, 4h: Donchian-20 breakout only in an uptrend (close > EMA200, EMA50 > EMA200; alts also need BTC in an uptrend). Stop 2.5×ATR, chandelier trail 3×ATR.
- `bounce` — crypto, 1h: RSI(2) < 5 and close below the 2.5σ Bollinger band, inside a 1h uptrend. Exit above the 5-bar average or after 36 bars; stop 3×ATR.
- `index_pullback` — SPY/QQQ/IWM, daily (Connors RSI(2)): above the 200-day average and RSI(2) < 10 → buy near the close; sell when the close is above the 5-day average. 8% emergency stop.
- `core` — long-term hold: 10% BTC, 10% SPY, bought at the start.

**Risk rules**: 0.75% of equity at risk per trade, max 20% of equity per position, max 5 active positions, no new entries after a 2% down day (UTC), no new entries at all after a 10% drawdown from peak.

Data: Coinbase (Kraken fallback) for crypto, Yahoo Finance (Stooq fallback) for ETFs. Costs: crypto 0.10% fee + 0.08% slippage per side; ETFs 0.03% slippage.

Test window: Fri 30 Oct → Fri 6 Nov 2026 (`TEST_END` in `bot/run.py`). Nothing here is financial advice.
