# BTC Up/Down Lab

Paper-only research and simulation for Polymarket's short-horizon Bitcoin "Up or Down" markets (5, 15, and 60 minutes).

**Live trading is not implemented.** There is no order placement, no wallet creation, and no private-key handling. `config.yaml` accepts only `mode: paper`. The web UI says so on every page.

The committed study found a real short-horizon mean-reversion pattern on Binance prices and no taker edge once real Polymarket prices and fees are included.

## What the study found

Artifacts, not a fresh estimate: [`research/results/research_results.csv`](research/results/research_results.csv) and [`research/results/pm_check.csv`](research/results/pm_check.csv). The write-up is [`docs/research-report.md`](docs/research-report.md). The UI reads those files and recomputes the selection rule and the Bonferroni threshold from them.

Data was Binance BTC/USDT 1-minute bars, 2022-01-01 through 2026-10-18 UTC. The outcome is Up when the window close is greater than or equal to the open. Features are taken from the last closed minute before the window opens.

| Split | Period | Role |
|---|---|---|
| Train | 2022 through 2024 | Fit the seasonality map and the logistic ensemble only |
| Validation | 2025 | Pick one signal per horizon |
| Test | 2026-01-01 to 2026-10-18 | Scored once, after selection |

81 variants were scored on validation. The one-sided Bonferroni z for p = 0.05 is **3.23**. The selection rule does not use that screen: it takes the best validation hit rate among signals with a train hit rate above 50% and at least 500 validation trades. The screen is reported next to the pick so a weak winner is not dressed up as a discovery.

Selected rule on the untouched test, Binance outcome, assumed **$0.50** entry:

| Window | Signal | Trades | Hit | z vs 50% | PnL/share @ 1¢ | PnL/share @ 3¢ | Validation clears Bonferroni? |
|---|---|---:|---:|---:|---:|---:|---|
| 5m | RSI(14) 30/70 mean reversion | 7,906 | 54.0% | 7.13 | +3.0¢ | +1.0¢ | Yes |
| 15m | RSI(14) 30/70 mean reversion | 2,415 | 55.7% | 5.64 | +4.7¢ | +2.7¢ | Yes |
| 60m | RSI(14) 30/70 mean reversion | 512 | 52.9% | 1.33 | +1.9¢ | −0.1¢ | No (validation z = 2.86) |

Trend rules lost. Aroon trend and multi-hour momentum sit below 50% on the 2025 validation set. The leaderboard in the UI is the full table, including post-hoc 2026 rows, which are labeled as not a clean test.

Real Polymarket prints in the 2026 test (public gamma API and CLOB `prices-history`, last print at or before the window open, taker fee `0.07 · p · (1 − p)`):

| Window | Fired markets | Settlement hit | Avg cost of the predicted side | Up price when signal is UP / DOWN / flat | PnL/share after taker fee |
|---|---:|---:|---:|---|---:|
| 5m (sampled) | 2,030 | 51.3% | 0.520 | 0.522 / 0.481 / 0.502 | −2.4¢ (SE 1.1¢) |
| 15m | 2,409 | 54.3% | 0.534 | 0.536 / 0.467 / 0.498 | −0.9¢ (SE 1.0¢) |
| 60m | 370 | 50.3% | 0.532 | 0.534 / 0.470 / 0.501 | −4.7¢ (SE 2.6¢) |

When the signal says Up, the market is already about 53–54¢, not 50¢. The break-even hit rate at that entry, plus about 1.75¢ of taker fee, is above the settlement hit rate. **A small taker does not have a tradable edge in this study.** Adding another 1¢ of spread makes it worse (see the same CSV, `extra_spread = 0.01`).

An earlier Aroon-trend paper run on 180 days of 2026 (2026-04-22 to 2026-10-19, 259,201 bars) is stored in [`research/results/aroon_180d_backtest.txt`](research/results/aroon_180d_backtest.txt). Hit rates were 48.1% (60m), 47.8% (15m), and 48.9% (5m). The risk-managed bankroll hit the 15% drawdown stop in every fee setting. That run counts a tie as Down; the research harness counts close ≥ open as Up.

The +$268k figure in the original idea thread is not something this code reproduces. That thread is kept, unedited apart from a banner, in [`docs/original-transcript.md`](docs/original-transcript.md). Passages in it about keys and live orders are not implemented here.

## Run the lab

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest
python -m aroonbot
```

Open http://localhost:8000. The same process serves the UI and the JSON API.

Docker:

```bash
docker compose up --build
```

`data/` is mounted so kline and paper-log caches survive restarts. That directory is gitignored. Nothing in it is required to read the published study.

### CLI

```bash
python scripts/backtest.py --days 14 --minutes 15 --signal rsi_mr_30_70 --fee 0.01
python scripts/backtest.py --days 30 --legacy-aroon
python scripts/paper_live.py --once          # print the current RSI signal; loops without --once
python scripts/maker_replay.py --minutes 15 --windows 16 --shade 0.02
python scripts/build_data.py --start 2022-01-01 --end 2026-10-19   # full study cache, large download
python scripts/research.py                   # re-run only after build_data.py
```

`scripts/research.py` writes `data/research_results_rerun.csv`. It does not overwrite the committed study. Re-running the logistic ensemble will not match the published file bit for bit unless the input bars match the original build.

The web backtest is capped at 120 days so a mis-click cannot download the full history. The CLI is not capped. First use downloads Binance Vision monthly or daily zips into `data/cache/` and uses the public REST API only for the forming day.

## UI

- **Overview.** Headline and per-horizon numbers computed from the committed CSVs.
- **Backtest.** Pick a fixed signal and a 5/15/60-minute window. Equity curve of per-share PnL, hit rate against the break-even implied by your entry, fee, and spread, and the risk-managed paper bankroll. The published Polymarket check for that horizon is shown beside the run and labeled as a different sample.
- **Leaderboard.** Validation table, Bonferroni pass/fail, the three precommitted test rows, and a collapsed post-hoc 2026 table.
- **Polymarket prices.** Every row of `pm_check.csv`, including the +1¢ spread variants.
- **Paper tape.** Current signal from public BTC klines. "Log this window" appends a simulated decision to `data/paper_log.jsonl`. Entry is either an assumed $0.50 or the public print at the open. If the print is missing, no price is invented.
- **Maker test.** Experimental paper quote: when the signal fires, a hypothetical bid is shaded below the public print (or below $0.50). A fill is marked only if a later `prices-history` print on that token, strictly inside the window, trades at or below the limit. Resolution prints at the window end are ignored. Marketable quotes are excluded. The rebate defaults to 0. Results append to `data/maker_log.jsonl`.

## Layout

```
src/aroonbot/     indicators, signal library, agents, backtest, study loader, read-only Polymarket client, maker and paper logs, web UI
research/results/ committed study outputs
docs/             research report and the original idea transcript
scripts/          CLI entry points
tests/            unit tests, including a scan that the package has no order or key paths
.github/workflows/ci.yml
```

## Tests

GitHub Actions installs the package, runs Ruff, and runs pytest. The tests do not download market data and do not hit Polymarket. They check the committed artifacts for internal consistency (selection rule, z-scores, negative Polymarket PnL) and the paper/maker fill rules on synthetic prints.

## Fees and assumptions worth not skimming

- Exchange backtests are not fills. A $0.50 entry is an assumption.
- The Polymarket taker fee used here is `0.07 * p * (1 - p)` per share (1.75¢ at p = 0.50), which is the schedule cited in the study.
- `prices-history` is not the order book. A print at or through a hypothetical bid is an upper bound on a fill, not an execution.
- 5- and 15-minute Polymarket markets settle on Chainlink BTC/USD. The Binance hit rate and the Polymarket settlement hit rate are not the same number; the 5-minute one drops from about 54% to about 51% in the study.
- Maker rebates are not assumed. Put a number in the maker form only as a sensitivity, and the log will show that you did.
