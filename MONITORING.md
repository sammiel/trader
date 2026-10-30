# Check-in runbook (for Claude's scheduled check-ins)

The bot runs itself on GitHub Actions. The main engine is `loop.yml`: one job
ticks every 15 minutes for ~5h40m, then starts the next loop (repo is public, so
Actions minutes are free). `tick.yml` on cron is a backup and skips itself while
a loop is running. A check-in
verifies it is healthy, refreshes the dashboard, and alerts Samuel only when
something needs him.

IDs
- Repo: `sammiel/trader` (clone to `/home/claude/trader`)
- Dashboard artifact (Dashboard type): slug `84cd4588-7137-4a7e-9e64-15532e175f52`
  — https://claude.ai/artifact/HQ92XFrsMg2bJwys4dKNgR
- Framework doc (Claude Docs): doc `8d07cd4c-f7b3-4d0c-a3fb-5067a31f56a1`, body node `6083ac32-17bc`
  — https://claude.ai/artifact/JR5DA5kDirRpMWmNsPD19J
- Live public status page (GitHub Pages from /docs, rebuilt on every tick): https://sammiel.github.io/trader/ — include this link in any message to Samuel; if "pages build and deployment" runs are failing, say so.
- Test window ends Fri 6 Nov 2026 21:30 UTC (`TEST_END` in `bot/run.py`).

## Steps

1. Attach the repo (`add_repo` sammiel/trader, access push), clone it, `pip install -r requirements.txt --break-system-packages`.
2. Health
   - `state/health.json` → `ok` must be true; if not, read `error`.
   - A `loop` run should be `in_progress` (`curl -s "https://api.github.com/repos/sammiel/trader/actions/runs?per_page=10"`).
     If none is, start one (before 6 Nov 22:00 UTC):
     `curl -s -X POST -H "Accept: application/vnd.github+json" -H "Content-Type: application/json" https://api.github.com/repos/sammiel/trader/actions/workflows/loop.yml/dispatches -d '{"ref":"main"}'`
   - Last row of `state/equity.csv` must be < 45 min old. If stale and a loop is running, cancel that run
     (`POST .../actions/runs/<id>/cancel`) and start a new loop as above.
     and look at recent runs: `curl -s "https://api.github.com/repos/sammiel/trader/actions/runs?per_page=10"`.
   - Count scheduled (`event: schedule`) runs in the last 6 h; GitHub sometimes drops cron runs.
3. Sanity-check numbers: recompute each book's equity from `state/state.json` (cash + qty × `prices`) and compare with `docs/summary.json`; every trade in `state/trades.csv` must have a matching BUY and EXIT/STOP in `state/events.log`.
4. Refresh the dashboard: `python -m bot.dashboard_export` → `dashboard/*.json`.
   `upload_asset` the six files (kpi, equity, strategies, positions, trades, signals) to the dashboard slug,
   then for each `datasets/<name>`: `db_get` (for its version) and `db_write` op `update` with
   `{source: {kind: "file", url: <new url>, name: "<name>.json"}, updated: {at: <now ISO>, by: "Claude check-in"}}` and `ifVersion`.
5. Append one line to `monitoring/log.md` (time, equity of each book, trades since last check, issues), commit, `git pull --rebase`, push.
6. Tell Samuel (push notification / message) ONLY if: the bot is unhealthy or stale and the re-run did not fix it; a trade opened or closed in normal or Berkshire mode; normal-mode drawdown passed 3%; Berkshire hit its floor; a risk halt fired. Otherwise stay quiet.

## Final check-in (after 21:30 UTC Fri 6 Nov)
Do steps 1–5, then:
- Write the results into the framework doc: replace the paragraph that starts "Results will be filled in" in the "This week's paper test" section with a results table (normal, Berkshire, shadow, BTC hold, SPY hold: return, trades, win rate, max drawdown) and a verdict against the decision criteria listed there.
- Cancel any in-progress `loop` run (it also stops itself after 6 Nov 21:30 UTC), and comment out the `schedule:` block in `.github/workflows/tick.yml`; commit and push.
- Send Samuel a short summary with links to the doc and dashboard.
