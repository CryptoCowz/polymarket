> Relocated into this repository. The original note referred to paths under `/workspace/polymarket-aroon-trend-bot` and `/workspace/quant-research/report.md`. The code now lives in `src/aroonbot/` and the tables below match `research/results/`. The numbers were not re-estimated when the files were moved.

# Quant research: short-horizon BTC "Up or Down" signals vs. real Polymarket prices
Prepared 2026-10-19 for James Smith. Paper research only: no live trading, keys, or wallets.
Code: `/workspace/polymarket-aroon-trend-bot` (scripts `build_long.py`, `research.py`, `fetch_pm_short.py`, `fetch_polymarket.py`, `pm_check.py`). Raw outputs are in that repo's `data/` folder.

## TL;DR
- **On Binance prices alone, short-term mean reversion is real and holds up out of sample.** The RSI(14) 30/70 contrarian rule was picked on validation data only, then run once on an untouched 2026 test period. It hit **55.7% on 15-minute windows (2,415 trades, z = 5.6)** and **54.0% on 5-minute windows (7,906 trades, z = 7.1)**, against a 51% to 53% break-even at an assumed $0.50 entry.
- **But Polymarket already prices it in.** I pulled real market prices at window open for 2,409 fired 15-minute markets, 2,030 fired 5-minute markets and 370 fired hourly markets in 2026. When the signal says UP, the market's Up price is already about 0.535 (control windows: about 0.50). Buying the predicted side at the real market price, after Polymarket's taker fee, **every horizon is negative**:
  - 15 min: −0.9¢/share (SE 1.0¢)
  - 5 min: −2.4¢ (SE 1.1¢)
  - hourly: −4.7¢ (SE 2.6¢)
- **Verdict: no tradable edge for a small taker on Polymarket.** The predictable part of BTC's next 5 to 60 minutes is already in the price.

## Part 1: What is publicly known about the firms (secret models stay secret)
| Firm | Public picture | Sources |
|---|---|---|
| Renaissance / Medallion | 1988-2018: 63.3% gross compound return, no losing year, negative market beta. The models are secret. Public accounts describe many small, short-horizon statistical signals (pattern recognition, early HMM/speech-recognition hires such as Mercer and Brown), heavy data cleaning, leverage, and fanatical cost and execution control. Capacity-capped (about $10B), employees only. | Cornell, "Medallion Fund: The Ultimate Counterexample?" https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3504766 ; G. Zuckerman, *The Man Who Solved the Market* (2019), whose appendix is the source of the return data Cornell uses |
| AQR | Published factor investing: time-series momentum, value plus momentum "everywhere", carry, defensive / betting-against-beta. Monthly horizons, many assets, volatility targeting. | Moskowitz, Ooi, Pedersen (2012) https://www.aqr.com/Insights/Research/Journal-Article/Time-Series-Momentum ; Hurst, Ooi, Pedersen, "A Century of Evidence on Trend-Following" https://www.aqr.com/Insights/Research/Journal-Article/A-Century-of-Evidence-on-Trend-Following-Investing |
| Man AHL, Winton | Classic CTA trend-following on diversified futures, with returns from 1- to 12-month trends across 50+ markets. The evidence behind it is the TSMOM literature above. It works at weekly-to-monthly horizons, not minutes. | Same TSMOM papers. Firm-specific model details are not public. |
| Two Sigma, D.E. Shaw | Large-scale data and ML, statistical arbitrage, many diversified models. Little verifiable detail is public. | No primary technical disclosures. Not described further here to avoid inventing specifics. |
| Citadel Securities, Jane Street | Market makers. They earn the spread and manage inventory using speed, order-flow and microstructure signals. Short-horizon price moves are driven mainly by order-flow imbalance at the best bid and ask. | Cont, Kukanov, Stoikov, "The Price Impact of Order Book Events" https://arxiv.org/abs/1011.6402 |

**Crypto short-horizon evidence:**
- Wen, Bouri, Xu, Zhao (2022) find both intraday momentum and *reversal* in BTC, with the reversal tied to overreaction. https://doi.org/10.1016/j.najef.2022.101733
- Shen (2022) studies Bitcoin intraday time-series momentum. https://onlinelibrary.wiley.com/doi/10.1111/fire.12290
- Liu & Tsyvinski find that crypto momentum and attention predict returns at daily-to-weekly horizons. https://www.nber.org/papers/w24877

**Multiple-testing discipline:** Bailey & López de Prado, "The Deflated Sharpe Ratio". https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2460551

**What a small trader can't copy:**
- The big firms' edge is mostly structural: cost (they *earn* spread rather than pay it), speed, capacity management, proprietary data, and decades of infrastructure.
- On Polymarket the equivalent is being the **maker**. Takers pay a dynamic fee of about 0.07·p·(1−p) per share, roughly 1.75¢ at p = 0.50, while makers get rebates. https://docs.polymarket.com/trading/fees
- The "amalgamation" that is actually transferable is the *process*: many weak signals, strict out-of-sample testing, cost-first accounting, and small sizing. There is no secret formula to copy.

## Part 2: Signal tests
**Data:**
- Binance BTC/USDT 1-minute klines, 2022-01-01 to 2026-10-18 UTC: 2,522,800 bars from data.binance.vision monthly files plus the public REST API for October, including taker-buy volume.
- Windows: 5, 15 and 60 minutes. Outcome is Up if close ≥ open, matching Polymarket.
- Features come from the last closed bar before the window opens (lookahead is covered by unit tests).

**Splits:**
- train: 2022 to 2024
- validation: 2025
- test: 2026-01-01 to 2026-10-18, untouched until each horizon's single selected signal was chosen

**Signals tested (27 per horizon, 81 variants on validation in total):**
- Aroon trend and Aroon reversal
- Reversal over 1, 5, 15 and 60 minutes
- Time-series momentum over 60, 240 and 1,440 minutes, plus a multi-horizon vote
- RSI 30/70 and Bollinger 2-SD mean reversion
- Volatility-regime-filtered reversal and momentum
- Taker-buy imbalance, follow and fade (5, 15, 60 minutes)
- Hour-of-week seasonality (train-fitted)
- Logistic-regression ensemble on 13 features, at 4 confidence margins
- An oriented vote of all base signals

**Selection and testing rules:**
- Selection rule: best validation hit rate among signals with train hit rate above 50% and at least 500 validation trades.
- Bonferroni one-sided z threshold for 81 trials at p = 0.05: **3.23**.
- Break-even hit rate at $0.50 entry: **51%** (1¢ fee), **53%** (3¢ fee).

**Selected signal, untouched test (Binance outcome, assumed $0.50 entry):**
| Window | Signal | Trades | Hit | z vs 50% | PnL/share @1¢ | z vs break-even @1¢ | PnL/share @3¢ |
|---|---|---|---|---|---|---|---|
| 5m | RSI 30/70 contrarian | 7,906 | 54.0% | 7.13 | +3.0¢ | 5.35 | +1.0¢ |
| 15m | RSI 30/70 contrarian | 2,415 | 55.7% | 5.64 | +4.7¢ | 4.65 | +2.7¢ |
| 60m | RSI 30/70 contrarian | 512 | 52.9% | 1.33 | +1.9¢ | 0.87 | −0.1¢ |

**Other validation (2025) results:**
- **Mean reversion wins.** The 5- and 15-minute RSI rules pass Bonferroni comfortably.
- **Trend loses.** Aroon trend hit 47.2% to 48.8% and 1-day momentum 47.8% to 49.2%; both are worse than a coin flip.
- **Fading taker-buy imbalance beats following it**: 50.7% to 52.2%.
- **Seasonality did nothing**: about 50%.
- **The ensemble didn't beat the simple RSI rule.** At margin 0.05 the logit model reached 54.9% (15 min) and 54.5% (5 min) on validation, and 54.1% / 54.5% on post-hoc test, with more trades.

**The real test: actual Polymarket prices** (2026 test period, public gamma-api plus clob prices-history, settled outcomes):
| Window | Fired markets | Hit (real settlement) | Avg cost of predicted side | Up price when signal = UP / DOWN / no signal | PnL/share after taker fee | +1¢ spread |
|---|---|---|---|---|---|---|
| 5m (sampled) | 2,030 | 51.3% | 0.520 | 0.522 / 0.481 / 0.502 | −2.4¢ ± 1.1 | −3.4¢ |
| 15m | 2,409 | 54.3% | 0.534 | 0.536 / 0.467 / 0.498 | −0.9¢ ± 1.0 | −1.9¢ |
| 60m | 370 | 50.3% | 0.532 | 0.534 / 0.470 / 0.501 | −4.7¢ ± 2.6 | −5.7¢ |

Notes on the Polymarket data:
- Price is the last recorded point at or before the window open (1-minute fidelity). Prices one minute after the open give the same conclusion.
- Prices-history points are not guaranteed executable asks, so real fills would likely be worse.
- 5- and 15-minute markets settle on Chainlink BTC/USD, not Binance. That probably explains why the 5-minute hit rate falls from 54% to 51%.

## Verdict
- **The signal is real but already priced in.** The mean-reversion effect is statistically robust on exchange data across 4.8 years and an untouched test period. Polymarket participants (largely market makers) already shade prices 3 to 4¢ in the signal's direction, so a taker pays away the edge and then the fee.
- **The +$268k claim isn't supported by anything I can reproduce.** The original post's figure (+$268k over 177 days) came from an Aroon *trend* rule, which tested at 47% to 49%, below a coin flip. The only plausible route to profits like that is maker-side liquidity provision with rebates, real infrastructure and inventory risk, not the signal.
- **Recommendation: don't put money into this.** If James wants to keep exploring, the only honest next step is a paper-traded **maker** study: post limit orders shaded by the RSI signal and log hypothetical fills against the real order book for several weeks before risking any capital. Expect it to be marginal.
