# Experiments

Every row uses the same pass mark, fixed before attempt 2 and not moved to fit a result.

A rule passes only when all of these hold: at least 100 trades, average R after costs at least +0.10, the first half and the second half both above 0 after costs, and after-cost average R above 0 on at least 60% of the stocks that traded. From attempt 7 the mark also requires at least 30 distinct trading days and the best 5 days at most 50% of total profit. Attempts 1 to 6 were judged on the earlier mark. Anything else is FAIL, with the marks that missed.

The market filter in step 8 chose NIFTY's direction for the whole day, so a stock could enter before NIFTY had broken out. That look-ahead is fixed: NIFTY's signal is a direction and a close time, and a stock may enter only on its first close beyond its own range at or after that time. Attempts 4 and 5 below replace the look-ahead figures (attempt 4 had been 1,677 trades, +0.235 before costs, +0.073 after; attempt 5 had been 215 trades, +0.213, +0.088).

| # | Date | Hypothesis | Rule | Data | Trades | R before costs | R after costs | Result |
|---|------|------------|------|------|--------|----------------|---------------|--------|
| 1 | 2026-11-04 | A long opening-range breakout, stop under the range low and a 2R target, is profitable after NSE costs on six large stocks. This was the best of the 12 long rules. | 30m or-low 2R, long | tests/fixtures/india/stocks (HDFCBANK, ICICIBANK, INFY, RELIANCE, SBIN, TCS; 60 sessions each) | 149 | -0.016 | -0.120 | FAIL |
| 4 | 2026-11-04 | Trading both sides only in the direction of NIFTY's opening-range break, on all 50 stocks, is profitable after costs. | 30m or-mid 2R, long and short | nifty50, market filter, Rs 500 risk, Rs 1,00,000 cap | 1,618 | +0.178 | +0.026 | FAIL |
| 5 | 2026-11-04 | The same NIFTY direction rule, limited to in-play days, is profitable after costs. | 30m or-mid 2R, long and short | nifty50, in-play and market, Rs 500 risk, Rs 1,00,000 cap | 202 | +0.172 | +0.054 | FAIL |
| 6 | 2026-11-04 | With the look-ahead removed, taking only the first 3 entries each day in NIFTY's direction, Rs 2,000 risk and a Rs 5,00,000 cap, a 30-minute opening range with a 2R target clears the same pass mark. Both the midpoint stop and the far-side stop are in this attempt. | 30m or-mid 2R, long and short, at most 3 entries a day | nifty50, market filter, Rs 2,000 risk, Rs 5,00,000 cap | 162 | +0.122 | +0.045 | FAIL |
| 6 | 2026-11-04 | Same attempt, far-side stop. | 30m or-low 2R, long and short, at most 3 entries a day | nifty50, market filter, Rs 2,000 risk, Rs 5,00,000 cap | 162 | +0.041 | -0.014 | FAIL |
| 7 | 2026-11-04 | Trend-day niche (market-aligned, 30m or-mid 2R, NIFTY signal by 10:00). Found by slicing attempt 4's data, so it is a hypothesis, not a pass. Confirmation only on data after 2026-10-30. | 30m or-mid 2R, long and short, NIFTY signal by 10:00 | nifty50, market filter, Rs 2,000 risk, Rs 5,00,000 cap. In sample through 2026-10-30. | 612 | +0.310 | +0.227 | FAIL |
| 8 | 2026-11-06 | Attempt 7's trend-day rule is profitable after costs on 2015-2024 in today's NIFTY 50. This universe has survivorship bias. | 30m or-mid 2R, long and short, NIFTY signal by 10:00, 1 tick slippage | today's NIFTY 50, 2015-01-01 to 2024-12-31, Rs 2,000 risk, Rs 5,00,000 cap | 25,326 | +0.029 | -0.047 | FAIL |
| 8 | 2026-11-06 | The same rule is profitable after costs on 2015-2024 in the 100 names with the highest prior 20-session turnover. | 30m or-mid 2R, long and short, NIFTY signal by 10:00, 1 tick slippage | point-in-time top 100 by prior 20-session turnover, 2015-01-01 to 2024-12-31 | 54,707 | +0.030 | -0.038 | FAIL |
| 9 | 2026-11-06 | Passing combinations on 2005-2024: 20d-high / sma20-close (17,461 trades, +1.574% after costs, beats random 99/100, 14 of 20 years); engulf-low / hold-20 (2,337 trades, +1.176% after costs, beats random 99/100, 15 of 20 years). | 7 entries x 3 exits, delivery costs, Rs 1,00,000 | point-in-time top 200 by prior 60-session turnover, 2005-01-01 to 2024-12-31 | 17,461; 2,337 | +1.574%; +1.176% | +1.574%; +1.176% | PASS |
| 10 | 2026-11-06 | 20d-high / sma20-close keeps a market-adjusted excess over a same-month random entry. | excess vs same-month random, monthly t, top 100, 10-slot portfolio | point-in-time turnover, 2005-01-01 to 2024-12-31, dividends excluded | 17,461 | -0.110% | -2.34 | FAIL |
| 10 | 2026-11-06 | engulf-low / hold-20 keeps a market-adjusted excess over a same-month random entry. | excess vs same-month random, monthly t, top 100, 10-slot portfolio | point-in-time turnover, 2005-01-01 to 2024-12-31, dividends excluded | 2,337 | +0.154% | -0.26 | FAIL |
| 10 | 2026-11-06 | bb-squeeze / sma20-close keeps a market-adjusted excess over a same-month random entry. | excess vs same-month random, monthly t, top 100, 10-slot portfolio | point-in-time turnover, 2005-01-01 to 2024-12-31, dividends excluded | 3,273 | +0.607% | +1.37 | FAIL |
| 10 | 2026-11-06 | sma20-touch / sma20-close keeps a market-adjusted excess over a same-month random entry. | excess vs same-month random, monthly t, top 100, 10-slot portfolio | point-in-time turnover, 2005-01-01 to 2024-12-31, dividends excluded | 36,324 | +0.199% | +0.08 | FAIL |
| 11 | 2026-11-06 | turtle 20/10 clears the attempt 11 pass mark against NIFTY buy-and-hold. | harness batch 1, delivery costs, idle cash in NIFTY except Faber | top 200 by prior 60-session turnover, 2005-01-01 to 2024-12-31, dividends excluded | 15,341 | +12.403% | +0.03 | FAIL |
| 11 | 2026-11-06 | turtle 55/20 clears the attempt 11 pass mark against NIFTY buy-and-hold. | harness batch 1, delivery costs, idle cash in NIFTY except Faber | top 200 by prior 60-session turnover, 2005-01-01 to 2024-12-31, dividends excluded | 8,577 | +13.913% | +0.72 | FAIL |
| 11 | 2026-11-06 | turtle 55/20 up clears the attempt 11 pass mark against NIFTY buy-and-hold. | harness batch 1, delivery costs, idle cash in NIFTY except Faber | top 200 by prior 60-session turnover, 2005-01-01 to 2024-12-31, dividends excluded | 7,265 | +13.586% | +0.51 | FAIL |
| 11 | 2026-11-06 | mom 12-1 K20 clears the attempt 11 pass mark against NIFTY buy-and-hold. | harness batch 1, delivery costs, idle cash in NIFTY except Faber | top 200 by prior 60-session turnover, 2005-01-01 to 2024-12-31, dividends excluded | 4,754 | +34.958% | +4.47 | FAIL |
| 11 | 2026-11-06 | mom 12-1 K30 clears the attempt 11 pass mark against NIFTY buy-and-hold. | harness batch 1, delivery costs, idle cash in NIFTY except Faber | top 200 by prior 60-session turnover, 2005-01-01 to 2024-12-31, dividends excluded | 7,124 | +33.073% | +4.42 | FAIL |
| 11 | 2026-11-06 | mom 12-1 K20 above200 clears the attempt 11 pass mark against NIFTY buy-and-hold. | harness batch 1, delivery costs, idle cash in NIFTY except Faber | top 200 by prior 60-session turnover, 2005-01-01 to 2024-12-31, dividends excluded | 3,654 | +35.442% | +4.82 | PASS |
| 11 | 2026-11-06 | 52w-high K20 clears the attempt 11 pass mark against NIFTY buy-and-hold. | harness batch 1, delivery costs, idle cash in NIFTY except Faber | top 200 by prior 60-session turnover, 2005-01-01 to 2024-12-31, dividends excluded | 4,754 | +21.660% | +2.03 | FAIL |
| 11 | 2026-11-06 | 52w-high K30 clears the attempt 11 pass mark against NIFTY buy-and-hold. | harness batch 1, delivery costs, idle cash in NIFTY except Faber | top 200 by prior 60-session turnover, 2005-01-01 to 2024-12-31, dividends excluded | 7,124 | +21.306% | +2.10 | FAIL |
| 11 | 2026-11-06 | 52w-high K20 above200 clears the attempt 11 pass mark against NIFTY buy-and-hold. | harness batch 1, delivery costs, idle cash in NIFTY except Faber | top 200 by prior 60-session turnover, 2005-01-01 to 2024-12-31, dividends excluded | 3,654 | +21.821% | +2.32 | FAIL |
| 11 | 2026-11-06 | faber 10m clears the attempt 11 pass mark against NIFTY buy-and-hold. | harness batch 1, delivery costs, idle cash in NIFTY except Faber | top 200 by prior 60-session turnover, 2005-01-01 to 2024-12-31, dividends excluded | 183 | +11.128% | -0.84 | FAIL |
| 11 | 2026-11-06 | faber 8m clears the attempt 11 pass mark against NIFTY buy-and-hold. | harness batch 1, delivery costs, idle cash in NIFTY except Faber | top 200 by prior 60-session turnover, 2005-01-01 to 2024-12-31, dividends excluded | 173 | +11.247% | -0.80 | FAIL |
| 11 | 2026-11-06 | faber 12m clears the attempt 11 pass mark against NIFTY buy-and-hold. | harness batch 1, delivery costs, idle cash in NIFTY except Faber | top 200 by prior 60-session turnover, 2005-01-01 to 2024-12-31, dividends excluded | 190 | +10.326% | -1.03 | FAIL |
| 12 | 2026-11-07 | nifty mom always clears the attempt 12 intraday pass mark. | intraday batch 2, costs and 1 tick, Rs 2,000 risk, Rs 5,00,000 cap | NIFTY 50 5-minute, one lot of 75, 2015-01-01 to 2024-12-31 | 2,429 | +0.035 | -0.212 | FAIL |
| 12 | 2026-11-07 | nifty mom abs 0.25 clears the attempt 12 intraday pass mark. | intraday batch 2, costs and 1 tick, Rs 2,000 risk, Rs 5,00,000 cap | NIFTY 50 5-minute, one lot of 75, 2015-01-01 to 2024-12-31 | 1,420 | +0.056 | -0.190 | FAIL |
| 12 | 2026-11-07 | nifty mom same sign clears the attempt 12 intraday pass mark. | intraday batch 2, costs and 1 tick, Rs 2,000 risk, Rs 5,00,000 cap | NIFTY 50 5-minute, one lot of 75, 2015-01-01 to 2024-12-31 | 1,290 | +0.098 | -0.149 | FAIL |
| 12 | 2026-11-07 | NR7 clears the attempt 12 intraday pass mark. | intraday batch 2, costs and 1 tick, Rs 2,000 risk, Rs 5,00,000 cap | top 200 by prior 20-session turnover, 5-minute, 2015-01-01 to 2024-12-31 | 64,448 | +0.031 | -0.019 | FAIL |
| 12 | 2026-11-07 | NR4 clears the attempt 12 intraday pass mark. | intraday batch 2, costs and 1 tick, Rs 2,000 risk, Rs 5,00,000 cap | top 200 by prior 20-session turnover, 5-minute, 2015-01-01 to 2024-12-31 | 110,413 | +0.027 | -0.022 | FAIL |
| 12 | 2026-11-07 | NR7 inside clears the attempt 12 intraday pass mark. | intraday batch 2, costs and 1 tick, Rs 2,000 risk, Rs 5,00,000 cap | top 200 by prior 20-session turnover, 5-minute, 2015-01-01 to 2024-12-31 | 23,994 | +0.038 | -0.012 | FAIL |
| 12 | 2026-11-07 | gap GO 1.5 clears the attempt 12 intraday pass mark. | intraday batch 2, costs and 1 tick, Rs 2,000 risk, Rs 5,00,000 cap | top 200 by prior 20-session turnover, 5-minute, 2015-01-01 to 2024-12-31 | 17,066 | +0.048 | +0.011 | FAIL |
| 12 | 2026-11-07 | gap FADE 1.5 clears the attempt 12 intraday pass mark. | intraday batch 2, costs and 1 tick, Rs 2,000 risk, Rs 5,00,000 cap | top 200 by prior 20-session turnover, 5-minute, 2015-01-01 to 2024-12-31 | 10,636 | +0.048 | +0.007 | FAIL |
| 12 | 2026-11-07 | gap GO 3 clears the attempt 12 intraday pass mark. | intraday batch 2, costs and 1 tick, Rs 2,000 risk, Rs 5,00,000 cap | top 200 by prior 20-session turnover, 5-minute, 2015-01-01 to 2024-12-31 | 3,834 | +0.106 | +0.075 | FAIL |
| 12 | 2026-11-07 | vwap 1.5 sideways clears the attempt 12 intraday pass mark. | intraday batch 2, costs and 1 tick, Rs 2,000 risk, Rs 5,00,000 cap | top 200 by prior 20-session turnover, 5-minute, 2015-01-01 to 2024-12-31 | 22,424 | -0.038 | -0.082 | FAIL |
| 12 | 2026-11-07 | vwap 2.0 sideways clears the attempt 12 intraday pass mark. | intraday batch 2, costs and 1 tick, Rs 2,000 risk, Rs 5,00,000 cap | top 200 by prior 20-session turnover, 5-minute, 2015-01-01 to 2024-12-31 | 11,001 | -0.034 | -0.073 | FAIL |
| 12 | 2026-11-07 | vwap 2.5 sideways clears the attempt 12 intraday pass mark. | intraday batch 2, costs and 1 tick, Rs 2,000 risk, Rs 5,00,000 cap | top 200 by prior 20-session turnover, 5-minute, 2015-01-01 to 2024-12-31 | 5,701 | -0.021 | -0.056 | FAIL |
| 13 | 2026-11-07 | gap cont 3 clears the attempt 13 intraday pass mark. | big-gap continuation, costs and 1 tick, Rs 2,000 risk, Rs 5,00,000 cap | top 200 by prior 20-session turnover, 5-minute, 2015-01-01 to 2024-12-31 | 9,196 | +0.041 | -0.068 | FAIL |
| 13 | 2026-11-07 | gap cont 4 clears the attempt 13 intraday pass mark. | big-gap continuation, costs and 1 tick, Rs 2,000 risk, Rs 5,00,000 cap | top 200 by prior 20-session turnover, 5-minute, 2015-01-01 to 2024-12-31 | 4,866 | -0.004 | -0.103 | FAIL |
| 13 | 2026-11-07 | gap cont 3 vol clears the attempt 13 intraday pass mark. | big-gap continuation, costs and 1 tick, Rs 2,000 risk, Rs 5,00,000 cap | top 200 by prior 20-session turnover, 5-minute, 2015-01-01 to 2024-12-31 | 4,326 | -0.028 | -0.120 | FAIL |
| 14 | 2026-11-07 | rsi2 < 5 clears the attempt 14 swing pass mark. | short swing, delivery costs, Rs 1,00,000, next open | top 200 by prior 60-session turnover, daily, 2005-01-01 to 2024-12-31 | 30,513 | +0.568% | +21.37 | PASS |
| 14 | 2026-11-07 | rsi2 < 10 clears the attempt 14 swing pass mark. | short swing, delivery costs, Rs 1,00,000, next open | top 200 by prior 60-session turnover, daily, 2005-01-01 to 2024-12-31 | 60,373 | +0.403% | +13.63 | PASS |
| 14 | 2026-11-07 | rsi2 < 10 down2 clears the attempt 14 swing pass mark. | short swing, delivery costs, Rs 1,00,000, next open | top 200 by prior 60-session turnover, daily, 2005-01-01 to 2024-12-31 | 52,023 | +0.425% | +13.37 | PASS |
| 14 | 2026-11-07 | ibs < 0.2 clears the attempt 14 swing pass mark. | short swing, delivery costs, Rs 1,00,000, next open | top 200 by prior 60-session turnover, daily, 2005-01-01 to 2024-12-31 | 126,464 | +0.150% | +0.80 | FAIL |
| 14 | 2026-11-07 | ibs < 0.1 clears the attempt 14 swing pass mark. | short swing, delivery costs, Rs 1,00,000, next open | top 200 by prior 60-session turnover, daily, 2005-01-01 to 2024-12-31 | 29,236 | +0.133% | +1.65 | FAIL |
| 14 | 2026-11-07 | ibs < 0.2 nifty clears the attempt 14 swing pass mark. | short swing, delivery costs, Rs 1,00,000, next open | NIFTY 50 daily price, delivery costs, Rs 1,00,000, 2005-01-01 to 2024-12-31 | 727 | -0.035% | -1.88 | FAIL |
| 14 | 2026-11-07 | soup 20 clears the attempt 14 swing pass mark. | short swing, delivery costs, Rs 1,00,000, next open | top 200 by prior 60-session turnover, daily, 2005-01-01 to 2024-12-31 | 39,790 | -0.410% | +12.19 | FAIL |
| 14 | 2026-11-07 | soup 10 clears the attempt 14 swing pass mark. | short swing, delivery costs, Rs 1,00,000, next open | top 200 by prior 60-session turnover, daily, 2005-01-01 to 2024-12-31 | 62,797 | -0.396% | +14.60 | FAIL |
| 14 | 2026-11-07 | soup 55 clears the attempt 14 swing pass mark. | short swing, delivery costs, Rs 1,00,000, next open | top 200 by prior 60-session turnover, daily, 2005-01-01 to 2024-12-31 | 19,269 | -0.447% | +6.21 | FAIL |
| 14 | 2026-11-07 | rev K10 clears the attempt 14 swing pass mark. | short swing, delivery costs, Rs 1,00,000, next open | top 200 by prior 60-session turnover, Monday book, 2005-01-01 to 2024-12-31 | 988 | +0.325% | +1.32 | FAIL |
| 14 | 2026-11-07 | rev K20 clears the attempt 14 swing pass mark. | short swing, delivery costs, Rs 1,00,000, next open | top 200 by prior 60-session turnover, Monday book, 2005-01-01 to 2024-12-31 | 988 | +0.374% | +3.03 | FAIL |
| 14 | 2026-11-07 | rev K10 above200 clears the attempt 14 swing pass mark. | short swing, delivery costs, Rs 1,00,000, next open | top 200 by prior 60-session turnover, Monday book, 2005-01-01 to 2024-12-31 | 753 | +0.236% | +0.14 | FAIL |
| 15 | 2026-11-07 | index rsi2 < 5 pooled, positive on 28 of 39. | delivery costs on the index price, Rs 1,00,000 | every NIFTY daily file, 2005-01-01 to 2024-12-31 | 6,333 | +0.291% | -2.43 | FAIL |
| 15 | 2026-11-07 | index rsi2 < 10 pooled, positive on 25 of 39. | delivery costs on the index price, Rs 1,00,000 | every NIFTY daily file, 2005-01-01 to 2024-12-31 | 11,949 | +0.162% | -3.05 | FAIL |
| 15 | 2026-11-07 | index rsi2 < 10 down2 pooled, positive on 26 of 39. | delivery costs on the index price, Rs 1,00,000 | every NIFTY daily file, 2005-01-01 to 2024-12-31 | 10,632 | +0.145% | -3.05 | FAIL |
| 15 | 2026-11-07 | RSI portfolio, Rs 10,00,000, 10 slots. No pass mark. | harness delivery costs, cash at 0 and cash in NIFTY | top 200 by prior 60-session turnover, 2005-01-01 to 2024-12-31 | see section | see section | see section | REPORT |
| 15 | 2026-11-07 | RSI stress: slippage, next close, RSI3, SMA10, SMA100. No pass mark. | delivery costs, t versus same-month random | top 200 by prior 60-session turnover, 2005-01-01 to 2024-12-31 | see section | see section | see section | REPORT |
| 15 | 2026-11-07 | holdout rsi2 < 5, per trade, through 2026-11-04. | attempt 14 rule, delivery costs, final=True once | top 200, 2025-01-01 to 2026-11-04 | 2,422 | +0.327% | +1.42 | FAIL |
| 16 | 2026-11-07 | pairs same. | attempt 16, rules fixed before the run | 2005-01-01 to 2024-12-31 | 486 | +0.550% | +0.21 | FAIL |
| 16 | 2026-11-07 | pairs any. | attempt 16, rules fixed before the run | 2005-01-01 to 2024-12-31 | 769 | +0.029% | -0.62 | FAIL |
| 16 | 2026-11-07 | pairs z. | attempt 16, rules fixed before the run | 2005-01-01 to 2024-12-31 | 1,070 | +0.493% | +1.28 | FAIL |
| 16 | 2026-11-07 | grail adx30. | attempt 16, rules fixed before the run | 2005-01-01 to 2024-12-31 | 12,888 | -0.430% | -0.11 | FAIL |
| 16 | 2026-11-07 | grail adx25. | attempt 16, rules fixed before the run | 2005-01-01 to 2024-12-31 | 21,758 | -0.515% | -0.19 | FAIL |
| 16 | 2026-11-07 | grail adx30 sma200. | attempt 16, rules fixed before the run | 2005-01-01 to 2024-12-31 | 11,042 | -0.401% | +2.06 | FAIL |
| 16 | 2026-11-07 | tom. | attempt 16, rules fixed before the run | 2005-01-01 to 2024-12-31 | 239 | +0.556% | +2.41 | FAIL |
| 16 | 2026-11-07 | expiry week. | attempt 16, rules fixed before the run | 2005-01-01 to 2024-12-31 | 240 | +0.130% | +0.65 | FAIL |
| 16 | 2026-11-07 | after expiry. | attempt 16, rules fixed before the run | 2005-01-01 to 2024-12-31 | 240 | +0.231% | +0.85 | FAIL |
| 16 | 2026-11-07 | m1 momentum. | attempt 16, rules fixed before the run | 2005-01-01 to 2024-12-31 | 13,604 | +0.798% | +19.53 | FAIL |
| 16 | 2026-11-07 | m2 regime. | attempt 16, rules fixed before the run | 2005-01-01 to 2024-12-31 | 28,851 | +0.600% | +21.17 | PASS |
| 16 | 2026-11-07 | m3 book. | attempt 16, rules fixed before the run | 2005-01-01 to 2024-12-31 | see section | +15.184% | +1.80 | FAIL |
| 16 | 2026-11-07 | holdout m2 regime. | same rule, final=True once | 2025-01-01 to the last NIFTY date | 1,603 | +0.079% | +0.78 | FAIL |

Attempt 6 was specified before the run. The midpoint stop used about Rs 2,93,681 a position and never had more than 3 open. The far-side stop used about Rs 1,74,263 a position, also with 3 open at the peak. Neither clears the pass mark.

Attempt 7 is in sample only: 612 trades on 18 days, 12 of them winning, best 5 days 97.1% of the profit. The stock files end on 2026-10-30, so there is no later sample here to confirm it. The new day clauses are what fail it.

All results use the same pass mark, fixed before attempt 2.

## Attempt 8

Rules fixed on 2026-11-06, before the run.

Hypothesis: attempt 7's trend-day rule, scored on 2015-01-01 through 2024-12-31, clears the pass mark after NSE costs and one tick of slippage. Two universes are scored separately.

Rule: a 30-minute opening range. NIFTY 50's first close beyond that range must be a bar that closes by 10:00. A stock enters on its first close beyond its own 30-minute range, in NIFTY's direction, at or after that signal and by 14:30. The stop is the range midpoint, rounded to the tick (down for a long, up for a short). The target is 2R. Flat at 15:10. Each trade risks Rs 2,000 with a Rs 5,00,000 position cap. The fill is one tick worse than the signal price on the entry and on the exit (tick_for). Costs are india/costs.py on those fill prices. R before costs uses the slipped fills and the planned risk. R after costs subtracts the round trip. A session is used only when it has every bar from 09:15 to 15:10.

Pass mark, the four rules fixed before attempt 2: at least 100 trades; average R after costs at least +0.10; the first half and the second half of the sessions both above 0 after costs; after-cost average R above 0 on at least 60% of the stocks that traded.

Universe A is today's NIFTY 50. It has survivorship bias: the members are the current index, not the members on each past day. Universe B, each day, is the 100 symbols with the highest average daily turnover (close times volume) over the previous 20 sessions, using only sessions before that day and never a turnover that crosses a break.

Winning-day share is days with net rupees above 0, divided by days that had a trade. Profit without the best 10 days drops those days' rupees and sums the rest.

Universe A, today's NIFTY 50
This universe has survivorship bias: members are the current index, not the members of each past day.
overall: trend days 895, trades 25326, avg R before +0.029, avg R after -0.047, winning-day share 41.9%, profit without the best 10 days Rs -3,248,398.50
2015: trend days 65, trades 1638, avg R before +0.059, avg R after -0.017, winning-day share 41.9%, profit without the best 10 days Rs -430,715.39
2016: trend days 75, trades 2100, avg R before +0.085, avg R after +0.008, winning-day share 41.3%, profit without the best 10 days Rs -565,188.83
2017: trend days 84, trades 2068, avg R before +0.045, avg R after -0.038, winning-day share 39.3%, profit without the best 10 days Rs -446,513.45
2018: trend days 101, trades 2820, avg R before -0.016, avg R after -0.089, winning-day share 41.6%, profit without the best 10 days Rs -837,734.40
2019: trend days 76, trades 2220, avg R before -0.005, avg R after -0.080, winning-day share 42.1%, profit without the best 10 days Rs -765,292.60
2020: trend days 93, trades 2569, avg R before -0.014, avg R after -0.077, winning-day share 34.8%, profit without the best 10 days Rs -925,932.72
2021: trend days 91, trades 2666, avg R before +0.037, avg R after -0.034, winning-day share 47.3%, profit without the best 10 days Rs -702,929.68
2022: trend days 107, trades 3183, avg R before +0.041, avg R after -0.032, winning-day share 42.5%, profit without the best 10 days Rs -774,420.50
2023: trend days 98, trades 2756, avg R before -0.036, avg R after -0.124, winning-day share 38.8%, profit without the best 10 days Rs -992,071.08
2024: trend days 105, trades 3306, avg R before +0.100, avg R after +0.023, winning-day share 48.6%, profit without the best 10 days Rs -565,761.94
up: trend days 631, trades 17797, avg R before +0.033, avg R after -0.045, winning-day share 42.5%, profit without the best 10 days Rs -2,409,168.47
down: trend days 117, trades 3274, avg R before +0.023, avg R after -0.044, winning-day share 38.8%, profit without the best 10 days Rs -970,590.55
sideways: trend days 147, trades 4255, avg R before +0.017, avg R after -0.054, winning-day share 41.8%, profit without the best 10 days Rs -1,042,183.74
FAIL: average R after costs -0.047 < +0.10; first half -0.050 is not above 0 after costs; second half -0.044 is not above 0 after costs; after-cost R > 0 on 12 of 48 stocks (25.0%), need 60%

Universe B, point-in-time liquid stocks
Each day is the 100 symbols with the highest average daily turnover over the previous 20 sessions.
overall: trend days 895, trades 54707, avg R before +0.030, avg R after -0.038, winning-day share 38.8%, profit without the best 10 days Rs -6,402,203.90
2015: trend days 65, trades 3855, avg R before +0.047, avg R after -0.023, winning-day share 43.5%, profit without the best 10 days Rs -1,073,117.79
2016: trend days 75, trades 4883, avg R before +0.070, avg R after +0.001, winning-day share 38.7%, profit without the best 10 days Rs -1,408,089.95
2017: trend days 84, trades 4951, avg R before -0.028, avg R after -0.102, winning-day share 33.3%, profit without the best 10 days Rs -1,767,630.28
2018: trend days 101, trades 6388, avg R before +0.005, avg R after -0.061, winning-day share 40.6%, profit without the best 10 days Rs -1,849,887.87
2019: trend days 76, trades 4953, avg R before +0.021, avg R after -0.047, winning-day share 36.8%, profit without the best 10 days Rs -1,441,638.66
2020: trend days 93, trades 5585, avg R before -0.040, avg R after -0.099, winning-day share 29.3%, profit without the best 10 days Rs -2,261,454.10
2021: trend days 91, trades 5613, avg R before +0.021, avg R after -0.043, winning-day share 41.8%, profit without the best 10 days Rs -1,533,168.90
2022: trend days 107, trades 6608, avg R before +0.072, avg R after +0.005, winning-day share 42.5%, profit without the best 10 days Rs -1,292,683.95
2023: trend days 98, trades 5377, avg R before -0.012, avg R after -0.089, winning-day share 35.7%, profit without the best 10 days Rs -1,656,008.31
2024: trend days 105, trades 6494, avg R before +0.127, avg R after +0.061, winning-day share 44.8%, profit without the best 10 days Rs -953,934.25
up: trend days 631, trades 38108, avg R before +0.031, avg R after -0.039, winning-day share 38.5%, profit without the best 10 days Rs -4,996,479.51
down: trend days 117, trades 7330, avg R before +0.031, avg R after -0.031, winning-day share 39.7%, profit without the best 10 days Rs -1,922,411.35
sideways: trend days 147, trades 9269, avg R before +0.025, avg R after -0.039, winning-day share 39.0%, profit without the best 10 days Rs -2,327,786.30
FAIL: average R after costs -0.038 < +0.10; first half -0.050 is not above 0 after costs; second half -0.027 is not above 0 after costs; after-cost R > 0 on 123 of 314 stocks (39.2%), need 60%


## Attempt 9

Rules fixed on 2026-11-06, before the run.

Hypothesis: one of seven long daily signals, with one of three exits, beats a same-month random entry often enough to clear the pass mark on 2005-01-01 through 2024-12-31.

Universe, point in time: each day, the 200 symbols with the highest average daily turnover (close times volume) over the previous 60 sessions, using only sessions before that day and never a turnover that crosses a break. A symbol's first 250 sessions in a segment are skipped, because the indicators need that history. A break starts the count again. Data is read through india/research/data.py. Dates from 2025-01-01 on are not requested.

A signal is decided at the close. The entry is the next session's open. Long only. One open trade per symbol at a time. A trade still open at the end of a segment exits at that segment's last close, so it is not open across a break, and the same close is used at the end of the window.

Entries: (1) close above the prior 252-session high, (2) close above the prior 20-session high, (3) SMA50 crosses above SMA200, (4) close above SMA200, the low touches SMA20 and the close finishes above SMA20, (5) close above SMA200, RSI14 below 30 within the last 3 sessions and the close above yesterday's high, (6) Bollinger width (20, 2, population deviation) at its 126-session low within the last 5 sessions and the close above the upper band, (7) bullish engulfing with the low at or through the prior 20-session low.

Exits: (A) stop at entry minus 2 ATR14 and target at entry plus 3 ATR14, ATR from the signal day, stop first when both are hit the same day, gaps filled at the open, (B) a close below SMA20 exits at the next open, (C) exit at the open 20 sessions after the entry.

Costs, delivery, check your broker: brokerage 0, STT 0.1% of buy value and of sell value, exchange 0.00297% of both sides, SEBI 0.0001% of both sides, stamp duty 0.015% of buy value, GST 18% of exchange plus SEBI, DP charge Rs 15.34 per sell. Each trade is sized at Rs 1,00,000 in whole shares.

Random baseline: for each of the 21 pairs, 100 seeded runs. Each real entry is replaced by an entry on a random eligible symbol and day from the same calendar month, with the same exit. The seed is 20261106.

Market type is the type known before the entry day's open, from NIFTY 50's 200-day average (up, down, or sideways).

Pass mark, fixed before this run and separate from the mark used for attempts 1 to 8: beats the random entry in at least 95 of 100 runs, average percent return after costs above 0, profitable in at least 14 of the 20 years, average return above 0 in up, down and sideways markets, and at least 300 trades. A year is profitable when the sum of net rupees of trades that exit in that year is above 0.

Sorted by how many of the 100 random runs the signal beat.

bb-squeeze / sma20-close: trades 3273, win 37.7%, avg +1.729%, hold 15.1d, beats random 100/100 (random median +1.156%, p95 +1.391%), years 13/20, up +1.358%, down +4.135%, sideways +2.087%, FAIL
  profitable years 13 of 20, need 14
sma20-touch / sma20-close: trades 36324, win 30.8%, avg +0.926%, hold 9.0d, beats random 100/100 (random median +0.660%, p95 +0.737%), years 13/20, up +0.888%, down +0.549%, sideways +1.361%, FAIL
  profitable years 13 of 20, need 14
20d-high / sma20-close: trades 17461, win 39.1%, avg +1.574%, hold 16.8d, beats random 99/100 (random median +1.360%, p95 +1.477%), years 14/20, up +1.158%, down +4.080%, sideways +1.513%, PASS
engulf-low / hold-20: trades 2337, win 52.5%, avg +1.176%, hold 20.0d, beats random 99/100 (random median +0.631%, p95 +0.991%), years 15/20, up +1.049%, down +0.839%, sideways +1.864%, PASS
rsi-reclaim / hold-20: trades 1148, win 50.8%, avg +0.916%, hold 20.0d, beats random 99/100 (random median +0.055%, p95 +0.599%), years 11/20, up +0.338%, down +3.637%, sideways +2.186%, FAIL
  profitable years 11 of 20, need 14
52w-high / sma20-close: trades 6954, win 38.6%, avg +1.216%, hold 17.3d, beats random 94/100 (random median +1.028%, p95 +1.216%), years 13/20, up +1.271%, down +1.078%, sideways +0.596%, FAIL
  beats random 94 of 100, need 95; profitable years 13 of 20, need 14
sma20-touch / atr-stop: trades 21040, win 46.7%, avg +1.071%, hold 17.2d, beats random 91/100 (random median +0.982%, p95 +1.088%), years 13/20, up +0.919%, down +0.916%, sideways +2.167%, FAIL
  beats random 91 of 100, need 95; profitable years 13 of 20, need 14
engulf-low / atr-stop: trades 2398, win 44.1%, avg +0.662%, hold 18.9d, beats random 65/100 (random median +0.587%, p95 +0.953%), years 14/20, up +0.800%, down -0.327%, sideways +1.278%, FAIL
  beats random 65 of 100, need 95; down -0.327% is not above 0
rsi-reclaim / atr-stop: trades 1216, win 42.6%, avg +0.312%, hold 21.8d, beats random 61/100 (random median +0.243%, p95 +0.765%), years 11/20, up -0.854%, down +1.285%, sideways +4.787%, FAIL
  beats random 61 of 100, need 95; profitable years 11 of 20, need 14; up -0.854% is not above 0
sma20-touch / hold-20: trades 20951, win 53.7%, avg +1.757%, hold 20.0d, beats random 30/100 (random median +1.802%, p95 +1.920%), years 15/20, up +1.669%, down +0.587%, sideways +2.957%, FAIL
  beats random 30 of 100, need 95
rsi-reclaim / sma20-close: trades 1266, win 42.3%, avg -0.288%, hold 2.1d, beats random 17/100 (random median -0.123%, p95 +0.207%), years 7/20, up -0.343%, down +0.037%, sideways -0.207%, FAIL
  average after costs -0.288% is not above 0; beats random 17 of 100, need 95; profitable years 7 of 20, need 14; up -0.343% is not above 0; sideways -0.207% is not above 0
bb-squeeze / hold-20: trades 3222, win 53.1%, avg +1.800%, hold 20.0d, beats random 0/100 (random median +2.295%, p95 +2.590%), years 13/20, up +1.666%, down +1.943%, sideways +2.459%, FAIL
  beats random 0 of 100, need 95; profitable years 13 of 20, need 14
20d-high / hold-20: trades 18594, win 52.9%, avg +1.665%, hold 20.0d, beats random 0/100 (random median +2.803%, p95 +2.949%), years 15/20, up +1.342%, down +1.938%, sideways +3.376%, FAIL
  beats random 0 of 100, need 95
52w-high / hold-20: trades 7477, win 52.7%, avg +1.645%, hold 20.0d, beats random 0/100 (random median +2.352%, p95 +2.561%), years 14/20, up +1.686%, down +0.140%, sideways +1.744%, FAIL
  beats random 0 of 100, need 95
sma50-cross / hold-20: trades 2427, win 51.5%, avg +1.075%, hold 20.0d, beats random 0/100 (random median +2.025%, p95 +2.342%), years 12/20, up +1.197%, down +0.517%, sideways +0.960%, FAIL
  beats random 0 of 100, need 95; profitable years 12 of 20, need 14
bb-squeeze / atr-stop: trades 3408, win 46.7%, avg +0.895%, hold 12.7d, beats random 0/100 (random median +1.521%, p95 +1.832%), years 13/20, up +0.735%, down +0.742%, sideways +1.906%, FAIL
  beats random 0 of 100, need 95; profitable years 13 of 20, need 14
20d-high / atr-stop: trades 24727, win 43.9%, avg +0.419%, hold 13.6d, beats random 0/100 (random median +1.887%, p95 +2.000%), years 13/20, up +0.144%, down +1.235%, sideways +1.434%, FAIL
  beats random 0 of 100, need 95; profitable years 13 of 20, need 14
sma50-cross / sma20-close: trades 2454, win 35.0%, avg +0.384%, hold 10.0d, beats random 0/100 (random median +1.107%, p95 +1.494%), years 12/20, up +0.435%, down +0.865%, sideways +0.048%, FAIL
  beats random 0 of 100, need 95; profitable years 12 of 20, need 14
sma50-cross / atr-stop: trades 2438, win 43.8%, avg +0.347%, hold 16.1d, beats random 0/100 (random median +1.092%, p95 +1.383%), years 12/20, up +0.285%, down +1.461%, sideways +0.070%, FAIL
  beats random 0 of 100, need 95; profitable years 12 of 20, need 14
52w-high / atr-stop: trades 10320, win 43.1%, avg +0.169%, hold 12.4d, beats random 0/100 (random median +1.285%, p95 +1.468%), years 13/20, up +0.150%, down -0.417%, sideways +0.645%, FAIL
  beats random 0 of 100, need 95; profitable years 13 of 20, need 14; down -0.417% is not above 0
engulf-low / sma20-close: trades 2483, win 37.1%, avg -0.281%, hold 2.6d, beats random 0/100 (random median +0.118%, p95 +0.431%), years 6/20, up -0.035%, down -0.274%, sideways -0.933%, FAIL
  average after costs -0.281% is not above 0; beats random 0 of 100, need 95; profitable years 6 of 20, need 14; up -0.035% is not above 0; down -0.274% is not above 0; sideways -0.933% is not above 0

Combinations that pass: 2 of 21. They are 20d-high / sma20-close (17,461 trades, +1.574% after costs, beats random 99/100, 14 of 20 years) and engulf-low / hold-20 (2,337 trades, +1.176% after costs, beats random 99/100, 15 of 20 years).


## Attempt 10

Rules fixed on 2026-11-06, before the run.

Hypothesis: the attempt-9 signals that beat a random entry still do so after a market adjustment, and the edge is not an artifact of one decade, one parameter, the smaller names, or of ignoring how many positions fit in a book.

Candidates, long only, same entry and exit as attempt 9: (a) 20d-high / sma20-close, (b) engulf-low / hold-20, (c) bb-squeeze / sma20-close, (d) sma20-touch / sma20-close. A signal is decided at the close and the entry is the next session's open. One open trade per symbol inside a segment for the excess study. A break closes the trade at the segment's last close. The first 250 sessions of a segment are skipped, and a break starts that count again. Costs are the delivery schedule in signal_lab.py (check your broker), sized at Rs 1,00,000. Data is read through india/research/data.py. The window is 2005-01-01 through 2024-12-31. Dates from 2025-01-01 on are not requested.

1. Market-adjusted excess. For each signal trade, excess is its percent return after costs minus NIFTY 50's percent price change over the same dates: from NIFTY's open on the entry date to NIFTY's open on the exit date when the trade exits at the open, otherwise to NIFTY's close on the exit date. A pair whose dates sit in different NIFTY segments is skipped, because that return would cross a break. Each signal trade is matched to one seeded random eligible entry from the same calendar month, with the same exit, and that random trade is measured the same way. The paired difference is the signal excess minus the random excess. The average excess per trade is the mean of those differences. The t-statistic averages the differences inside each entry month, then takes the mean of those monthly averages divided by their sample standard error. The seed is 20261106 plus a fixed offset per candidate, per neighbour and for the large-cap rerun.

2. Decades. The same average excess, split by the entry date, for 2005-2014 and for 2015-2024.

3. Neighbours change one parameter at a time. A neighbour passes when its average excess is above 0 and its t-statistic is above 2. (a) prior 15-session high with the SMA20 exit; prior 30-session high with the SMA20 exit; prior 20-session high with the SMA10 exit; prior 20-session high with the SMA30 exit. (b) bullish engulfing at the prior 10-session low, held 20 sessions; at the prior 30-session low, held 20 sessions; at the prior 20-session low, held 15 sessions; at the prior 20-session low, held 30 sessions. (c) Bollinger width lookback 63 with the SMA20 exit; lookback 252 with the SMA20 exit; lookback 126 with the SMA10 exit; lookback 126 with the SMA30 exit. The close must still finish above the upper band, and the width low must still fall within the last 5 sessions. (d) a touch of SMA10 with the exit on a close below SMA10; a touch of SMA50 with the exit on a close below SMA50. The close must still be above SMA200. At least 2 neighbours must pass. (a), (b) and (c) have four neighbours. (d) has two, so both must pass.

4. Large caps. The same excess as (1), with the daily universe cut to the 100 names with the highest average turnover over the previous 60 sessions.

5. Portfolio. Capital Rs 10,00,000. At most 10 positions, each reserved at Rs 1,00,000. When more signals are due on an entry date than there are free slots, take the highest average turnover over the 60 sessions before that entry, and break ties by symbol name. A symbol already open is skipped, and a symbol that exits at the open is not re-entered the same day. Cash earns 0. Report CAGR, max drawdown and the worst calendar year. CAGR uses 365.25-day years from the first NIFTY session in the window to the last. Drawdown is the worst peak-to-trough on the daily equity, in percent. The same three numbers are reported for buying NIFTY 50 at the first close and holding to the last close. Dividends are excluded for the portfolio and for NIFTY. The portfolio still pays the delivery costs. NIFTY is the price change only, with no costs.

Pass mark, fixed before this run and separate from attempts 1 to 9: excess t above 2 on the whole window; average excess above 0 in both decades; at least 2 neighbours passing; average excess above 0 in the top 100; portfolio CAGR at least NIFTY's CAGR plus 3 percentage points; and max drawdown no more than 10 percentage points worse than NIFTY's. A drawdown exactly 10 points worse still passes. A CAGR exactly 3 points above NIFTY still passes.

Dividends are excluded. The table columns are average excess and the monthly t, not R.

NIFTY 50 buy and hold, price only: CAGR +12.835%, max DD -59.856%, worst year -51.794%.

20d-high / sma20-close
  trades 17461, pairs 17461, months 240, excess -0.110%, t -2.34
  2005-2014 excess +0.089%, t -0.44, pairs 8119
  2015-2024 excess -0.283%, t -3.25, pairs 9342
  neighbours 0 of 4: 15d-high / sma20-close excess -0.009% t -1.21 FAIL; 30d-high / sma20-close excess -0.051% t -1.69 FAIL; 20d-high / sma10-close excess -0.111% t -2.53 FAIL; 20d-high / sma30-close excess +0.139% t -0.82 FAIL
  large caps: trades 9323, pairs 9323, excess -0.243%, t -3.32
  portfolio CAGR -0.507%, max DD -70.244%, worst year -42.674%
  NIFTY CAGR +12.835%, max DD -59.856%, worst year -51.794%
  dividends excluded
  FAIL: excess t -2.34 is not above 2; 2015-2024 excess -0.283% is not above 0; neighbours 0 of 4, need 2; large-cap excess -0.243% is not above 0; CAGR -0.507% is below NIFTY +12.835% plus 3; max drawdown -70.244% is more than 10 points worse than NIFTY -59.856%

engulf-low / hold-20
  trades 2337, pairs 2337, months 233, excess +0.154%, t -0.26
  2005-2014 excess -0.452%, t -0.88, pairs 1222
  2015-2024 excess +0.817%, t +0.64, pairs 1115
  neighbours 0 of 4: engulf-10 / hold-20 excess -0.068% t -0.29 FAIL; engulf-30 / hold-20 excess -0.013% t +0.17 FAIL; engulf-20 / hold-15 excess +0.135% t +0.73 FAIL; engulf-20 / hold-30 excess -0.196% t -0.55 FAIL
  large caps: trades 1143, pairs 1143, excess +0.526%, t +1.88
  portfolio CAGR +5.145%, max DD -42.048%, worst year -33.884%
  NIFTY CAGR +12.835%, max DD -59.856%, worst year -51.794%
  dividends excluded
  FAIL: excess t -0.26 is not above 2; 2005-2014 excess -0.452% is not above 0; neighbours 0 of 4, need 2; CAGR +5.145% is below NIFTY +12.835% plus 3

bb-squeeze / sma20-close
  trades 3273, pairs 3273, months 234, excess +0.607%, t +1.37
  2005-2014 excess +1.200%, t +1.97, pairs 1697
  2015-2024 excess -0.032%, t -0.80, pairs 1576
  neighbours 0 of 4: squeeze-63 / sma20-close excess +0.302% t +0.85 FAIL; squeeze-252 / sma20-close excess +0.589% t -0.00 FAIL; squeeze-126 / sma10-close excess +0.176% t -0.10 FAIL; squeeze-126 / sma30-close excess +1.077% t +1.43 FAIL
  large caps: trades 1619, pairs 1619, excess +0.186%, t +0.01
  portfolio CAGR +6.540%, max DD -12.781%, worst year -5.737%
  NIFTY CAGR +12.835%, max DD -59.856%, worst year -51.794%
  dividends excluded
  FAIL: excess t +1.37 is not above 2; 2015-2024 excess -0.032% is not above 0; neighbours 0 of 4, need 2; CAGR +6.540% is below NIFTY +12.835% plus 3

sma20-touch / sma20-close
  trades 36324, pairs 36324, months 240, excess +0.199%, t +0.08
  2005-2014 excess +0.349%, t -0.21, pairs 17720
  2015-2024 excess +0.056%, t +0.61, pairs 18604
  neighbours 0 of 2: sma10-touch / sma10-close excess +0.251% t +1.98 FAIL; sma50-touch / sma50-close excess -0.025% t -0.87 FAIL
  large caps: trades 18734, pairs 18734, excess +0.088%, t -0.67
  portfolio CAGR +4.374%, max DD -45.231%, worst year -38.311%
  NIFTY CAGR +12.835%, max DD -59.856%, worst year -51.794%
  dividends excluded
  FAIL: excess t +0.08 is not above 2; neighbours 0 of 2, need 2; CAGR +4.374% is below NIFTY +12.835% plus 3

Candidates that pass: 0 of 4.


## Attempt 11

Rules fixed on 2026-11-06, before the run.

Hypothesis: one of twelve published variants, run through the shared harness, beats buying NIFTY 50 on the pass mark below. The catalogue is india/research/STRATEGIES.md. Attempts 1 to 10 already tested the opening-range family and the single technical-signal family.

Common rules. Universe each day: the 200 symbols with the highest average close times volume over the previous 60 sessions, using only earlier bars and never a window that crosses a break. A trade or a holding that would cross a break is closed at the last close of the old segment. The last session of the window is the end of the loaded segment, so open holdings are sold at that close. The first 250 sessions of a segment produce no trade signal. Market type is india/research/regime.py, known before the open. Data is read through india/research/data.py. The window is 2005-01-01 through 2024-12-31. Dates from 2025-01-01 on are not requested. Dividends are excluded for every book and for NIFTY. The book and the NIFTY benchmark both start by buying at the first session's open, with no cost on that initial buy, and are marked at the close.

Idle cash is held in the NIFTY 50 price series, not at 0, so a book that is only partly invested is still compared with the market. Delivery costs from signal_lab.py (check your broker) are charged on stock buys and stock sells. They are not charged on the idle sleeve. A trade strategy has a Rs 10,00,000 book and at most 10 positions of Rs 1,00,000. When more signals than free slots fall on one open, the highest 60-session turnover before that open is taken, ties broken by symbol name. One position per symbol. A portfolio strategy puts the whole book into the selected names in equal weight at the next session's open after the month-end close. Costs are charged only on the shares that are actually bought or sold. Rounding residual stays in NIFTY.

Turtle, trade. Enter the next open after a close above the prior 20-session or 55-session high (today is not inside that high). The stop is the entry minus 2 ATR20 from the signal day: a gap through it fills at the open, and a low through it fills at the stop. A close below the prior 10-session or 20-session low exits at the next open. The stop is taken first when both happen on the same day. Variants: turtle 20/10, turtle 55/20, and turtle 55/20 up. The up variant is an entry filter only: the regime of the entry day must be up, and a later change of regime does not close the trade.

Cross-sectional momentum, portfolio, monthly. Rank by the close 21 sessions before the month-end divided by the close 252 sessions before it, minus one, inside one segment. Variants: K=20, K=30, and K=20 only when the NIFTY month-end close is above its 200-day average of closes through that day (otherwise the whole book is NIFTY). That average test is not the regime slope. Variant names: mom 12-1 K20, mom 12-1 K30, mom 12-1 K20 above200. When fewer than K names qualify, those names share the book equally.

52-week-high momentum, portfolio, monthly. Rank by the month-end close divided by the prior 252-session high. Variant names: 52w-high K20, 52w-high K30, and 52w-high K20 above200, the last with the same 200-day NIFTY filter.

Faber timing, portfolio on NIFTY 50 itself. Hold NIFTY when the month-end close is above the average of the last N month-end closes, including that close. Otherwise cash at 0, which is the exception to the idle-NIFTY rule. Buying or selling that index position pays delivery costs. Variant names: faber 10m, faber 8m, faber 12m. Before a full average exists the book stays in cash. Faber has no stock universe, so its large-cap excess is its own excess.

Reports. CAGR over 365.25-day years, max drawdown, CAGR divided by the absolute max drawdown, worst calendar year, and each year's return. The same figures for NIFTY 50 buy-and-hold, price only. Monthly excess is the book's month-end to month-end percent return minus NIFTY's over the same dates, and the t-statistic is the one-sample t of those monthly excesses. Decades are 2005-2014 and 2015-2024 by the month-end year. Market type is the regime of the first session of the month. Large caps rerun the variant on the top 100 by the same 60-session turnover; Faber has no stock book, so its large-cap excess is its own excess.

Random baseline, 100 seeded runs, seed 20261106 plus an offset per variant. A portfolio run keeps the same rebalance dates, the same K, and the same NIFTY filter, and draws random members of that day's universe who can be bought on the rebalance open in the same segment. A turtle run replaces each real entry with one random eligible entry from the same calendar month and applies the same stop and channel exit; the up-only variant draws only from entry days whose regime is up. A Faber run, each month, holds NIFTY or cash with equal probability. The book beats a run when its CAGR is strictly higher.

Pass mark, fixed before this run and used from attempt 11 on, separate from attempts 1 to 10: monthly excess t above 3; average excess above 0 in both decades and in up, down, and sideways months; beats at least 95 of 100 random runs; large-cap excess above 0; and either CAGR at least NIFTY plus 3 percentage points with max drawdown no more than 10 percentage points worse than NIFTY, or CAGR at least NIFTY's with CAGR / |max drawdown| at least 1.5 times NIFTY's. A value sitting on the boundary still passes.

Dividends are excluded. The summary columns are CAGR, max drawdown, CAGR / |max drawdown|, worst year, monthly excess, t, both decades, each market type, the large-cap excess, and random beats. In the experiments table the two return columns are CAGR and the monthly t, not R. A portfolio trades cell counts selected names across rebalance dates. A Faber trades cell counts months held.

variant | CAGR | max DD | CAGR/|DD| | worst year | excess | t | 2005-14 | 2015-24 | up | down | sideways | large | beats | result
NIFTY 50 | +12.929% | -59.856% | 0.216 | -51.794% | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | 
turtle 20/10 | +12.403% | -66.708% | 0.186 | -61.866% | +0.005% | +0.03 | +0.120% | -0.111% | +0.047% | -0.493% | +0.238% | -0.074% | 33/100 | FAIL
turtle 55/20 | +13.913% | -65.032% | 0.214 | -56.775% | +0.096% | +0.72 | +0.272% | -0.080% | +0.191% | -0.660% | +0.308% | -0.006% | 19/100 | FAIL
turtle 55/20 up | +13.586% | -61.591% | 0.221 | -53.437% | +0.057% | +0.51 | +0.167% | -0.052% | +0.085% | -0.024% | -0.003% | +0.051% | 25/100 | FAIL
mom 12-1 K20 | +34.958% | -73.213% | 0.477 | -68.898% | +1.667% | +4.47 | +1.805% | +1.528% | +2.142% | -1.134% | +1.892% | +0.753% | 100/100 | FAIL
mom 12-1 K30 | +33.073% | -71.287% | 0.464 | -66.104% | +1.520% | +4.42 | +1.674% | +1.367% | +1.926% | -0.812% | +1.664% | +0.657% | 100/100 | FAIL
mom 12-1 K20 above200 | +35.442% | -70.072% | 0.506 | -63.093% | +1.661% | +4.82 | +1.959% | +1.362% | +2.124% | +0.006% | +0.950% | +0.795% | 100/100 | PASS
52w-high K20 | +21.660% | -59.526% | 0.364 | -52.855% | +0.635% | +2.03 | +0.782% | +0.489% | +0.836% | -0.618% | +0.792% | +0.088% | 89/100 | FAIL
52w-high K30 | +21.306% | -60.641% | 0.351 | -53.252% | +0.608% | +2.10 | +0.773% | +0.443% | +0.774% | -0.416% | +0.725% | +0.185% | 90/100 | FAIL
52w-high K20 above200 | +21.821% | -65.517% | 0.333 | -57.633% | +0.678% | +2.32 | +0.961% | +0.396% | +0.844% | -0.011% | +0.509% | +0.221% | 85/100 | FAIL
faber 10m | +11.128% | -29.871% | 0.373 | -22.935% | -0.218% | -0.84 | -0.005% | -0.430% | +0.020% | -1.074% | -0.574% | -0.218% | 96/100 | FAIL
faber 8m | +11.247% | -29.871% | 0.377 | -16.345% | -0.214% | -0.80 | -0.070% | -0.359% | -0.022% | -0.943% | -0.473% | -0.214% | 97/100 | FAIL
faber 12m | +10.326% | -38.082% | 0.271 | -28.891% | -0.288% | -1.03 | -0.302% | -0.275% | -0.022% | -1.074% | -0.840% | -0.288% | 98/100 | FAIL

turtle 20/10 | +12.403% | -66.708% | 0.186 | -61.866% | +0.005% | +0.03 | +0.120% | -0.111% | +0.047% | -0.493% | +0.238% | -0.074% | 33/100 | FAIL
  2005-2014 +0.120%, 2015-2024 -0.111%, up +0.047%, down -0.493%, sideways +0.238%, large -0.074%, months 240
  years: 2005 +41.519%, 2006 +24.263%, 2007 +60.255%, 2008 -61.866%, 2009 +152.283%, 2010 +15.723%, 2011 -25.964%, 2012 +17.949%, 2013 +9.072%, 2014 +39.605%, 2015 -5.321%, 2016 -0.616%, 2017 +30.180%, 2018 -0.236%, 2019 +9.154%, 2020 +13.580%, 2021 +24.850%, 2022 -0.708%, 2023 +21.345%, 2024 +8.898%
  FAIL: excess t +0.03 is not above 3; 2015-2024 excess -0.111% is not above 0; down -0.493% is not above 0; beats random 33 of 100, need 95; large-cap excess -0.074% is not above 0; neither path clears: CAGR +12.403% vs NIFTY +12.929%, max DD -66.708% vs -59.856%, ratio 0.186 vs 0.216

turtle 55/20 | +13.913% | -65.032% | 0.214 | -56.775% | +0.096% | +0.72 | +0.272% | -0.080% | +0.191% | -0.660% | +0.308% | -0.006% | 19/100 | FAIL
  2005-2014 +0.272%, 2015-2024 -0.080%, up +0.191%, down -0.660%, sideways +0.308%, large -0.006%, months 240
  years: 2005 +61.206%, 2006 +32.746%, 2007 +49.777%, 2008 -56.775%, 2009 +123.062%, 2010 +19.441%, 2011 -25.549%, 2012 +22.054%, 2013 +11.013%, 2014 +39.776%, 2015 -3.400%, 2016 +1.436%, 2017 +28.259%, 2018 +0.583%, 2019 +9.191%, 2020 +13.775%, 2021 +24.455%, 2022 +0.045%, 2023 +21.598%, 2024 +9.257%
  FAIL: excess t +0.72 is not above 3; 2015-2024 excess -0.080% is not above 0; down -0.660% is not above 0; beats random 19 of 100, need 95; large-cap excess -0.006% is not above 0; neither path clears: CAGR +13.913% vs NIFTY +12.929%, max DD -65.032% vs -59.856%, ratio 0.214 vs 0.216

turtle 55/20 up | +13.586% | -61.591% | 0.221 | -53.437% | +0.057% | +0.51 | +0.167% | -0.052% | +0.085% | -0.024% | -0.003% | +0.051% | 25/100 | FAIL
  2005-2014 +0.167%, 2015-2024 -0.052%, up +0.085%, down -0.024%, sideways -0.003%, large +0.051%, months 240
  years: 2005 +61.206%, 2006 +32.746%, 2007 +49.777%, 2008 -53.437%, 2009 +75.436%, 2010 +24.447%, 2011 -23.386%, 2012 +21.357%, 2013 +16.968%, 2014 +34.376%, 2015 -2.780%, 2016 +3.181%, 2017 +26.017%, 2018 +0.752%, 2019 +6.475%, 2020 +16.031%, 2021 +23.186%, 2022 +2.439%, 2023 +22.745%, 2024 +9.994%
  FAIL: excess t +0.51 is not above 3; 2015-2024 excess -0.052% is not above 0; down -0.024% is not above 0; sideways -0.003% is not above 0; beats random 25 of 100, need 95; neither path clears: CAGR +13.586% vs NIFTY +12.929%, max DD -61.591% vs -59.856%, ratio 0.221 vs 0.216

mom 12-1 K20 | +34.958% | -73.213% | 0.477 | -68.898% | +1.667% | +4.47 | +1.805% | +1.528% | +2.142% | -1.134% | +1.892% | +0.753% | 100/100 | FAIL
  2005-2014 +1.805%, 2015-2024 +1.528%, up +2.142%, down -1.134%, sideways +1.892%, large +0.753%, months 240
  years: 2005 +123.756%, 2006 +128.519%, 2007 +133.480%, 2008 -68.898%, 2009 +83.669%, 2010 +29.386%, 2011 -14.789%, 2012 +62.898%, 2013 +11.876%, 2014 +102.917%, 2015 +1.958%, 2016 +6.879%, 2017 +95.854%, 2018 -4.978%, 2019 +12.399%, 2020 +38.706%, 2021 +97.839%, 2022 +3.412%, 2023 +65.431%, 2024 +34.696%
  FAIL: down -1.134% is not above 0

mom 12-1 K30 | +33.073% | -71.287% | 0.464 | -66.104% | +1.520% | +4.42 | +1.674% | +1.367% | +1.926% | -0.812% | +1.664% | +0.657% | 100/100 | FAIL
  2005-2014 +1.674%, 2015-2024 +1.367%, up +1.926%, down -0.812%, sideways +1.664%, large +0.657%, months 240
  years: 2005 +116.997%, 2006 +123.009%, 2007 +122.681%, 2008 -66.104%, 2009 +84.532%, 2010 +27.674%, 2011 -19.205%, 2012 +55.300%, 2013 +13.842%, 2014 +100.875%, 2015 +8.920%, 2016 +5.061%, 2017 +79.551%, 2018 -4.547%, 2019 +11.892%, 2020 +34.856%, 2021 +85.803%, 2022 +0.319%, 2023 +65.282%, 2024 +34.378%
  FAIL: down -0.812% is not above 0

mom 12-1 K20 above200 | +35.442% | -70.072% | 0.506 | -63.093% | +1.661% | +4.82 | +1.959% | +1.362% | +2.124% | +0.006% | +0.950% | +0.795% | 100/100 | PASS
  2005-2014 +1.959%, 2015-2024 +1.362%, up +2.124%, down +0.006%, sideways +0.950%, large +0.795%, months 240
  years: 2005 +123.756%, 2006 +128.519%, 2007 +133.480%, 2008 -63.093%, 2009 +93.046%, 2010 +29.396%, 2011 -17.578%, 2012 +74.544%, 2013 +6.269%, 2014 +102.915%, 2015 -12.663%, 2016 +24.036%, 2017 +78.785%, 2018 +0.112%, 2019 +10.393%, 2020 +44.240%, 2021 +97.843%, 2022 +0.725%, 2023 +52.165%, 2024 +34.694%
  PASS

52w-high K20 | +21.660% | -59.526% | 0.364 | -52.855% | +0.635% | +2.03 | +0.782% | +0.489% | +0.836% | -0.618% | +0.792% | +0.088% | 89/100 | FAIL
  2005-2014 +0.782%, 2015-2024 +0.489%, up +0.836%, down -0.618%, sideways +0.792%, large +0.088%, months 240
  years: 2005 +59.606%, 2006 +97.275%, 2007 +107.647%, 2008 -52.855%, 2009 +57.388%, 2010 +20.078%, 2011 -16.529%, 2012 +29.071%, 2013 +16.843%, 2014 +40.541%, 2015 -0.273%, 2016 +16.291%, 2017 +27.113%, 2018 -5.242%, 2019 -0.195%, 2020 +45.344%, 2021 +56.511%, 2022 -12.956%, 2023 +36.218%, 2024 +30.007%
  FAIL: excess t +2.03 is not above 3; down -0.618% is not above 0; beats random 89 of 100, need 95

52w-high K30 | +21.306% | -60.641% | 0.351 | -53.252% | +0.608% | +2.10 | +0.773% | +0.443% | +0.774% | -0.416% | +0.725% | +0.185% | 90/100 | FAIL
  2005-2014 +0.773%, 2015-2024 +0.443%, up +0.774%, down -0.416%, sideways +0.725%, large +0.185%, months 240
  years: 2005 +59.775%, 2006 +94.212%, 2007 +91.597%, 2008 -53.252%, 2009 +62.752%, 2010 +19.548%, 2011 -16.838%, 2012 +35.957%, 2013 +20.427%, 2014 +38.427%, 2015 +2.110%, 2016 +19.308%, 2017 +30.765%, 2018 -4.501%, 2019 +3.673%, 2020 +30.448%, 2021 +47.226%, 2022 -9.743%, 2023 +38.583%, 2024 +23.068%
  FAIL: excess t +2.10 is not above 3; down -0.416% is not above 0; beats random 90 of 100, need 95

52w-high K20 above200 | +21.821% | -65.517% | 0.333 | -57.633% | +0.678% | +2.32 | +0.961% | +0.396% | +0.844% | -0.011% | +0.509% | +0.221% | 85/100 | FAIL
  2005-2014 +0.961%, 2015-2024 +0.396%, up +0.844%, down -0.011%, sideways +0.509%, large +0.221%, months 240
  years: 2005 +59.606%, 2006 +97.275%, 2007 +107.647%, 2008 -57.633%, 2009 +73.351%, 2010 +20.084%, 2011 -17.833%, 2012 +50.664%, 2013 +18.967%, 2014 +40.488%, 2015 -5.929%, 2016 +14.445%, 2017 +24.996%, 2018 -4.001%, 2019 -2.241%, 2020 +35.397%, 2021 +56.485%, 2022 -8.240%, 2023 +35.819%, 2024 +30.021%
  FAIL: excess t +2.32 is not above 3; down -0.011% is not above 0; beats random 85 of 100, need 95

faber 10m | +11.128% | -29.871% | 0.373 | -22.935% | -0.218% | -0.84 | -0.005% | -0.430% | +0.020% | -1.074% | -0.574% | -0.218% | 96/100 | FAIL
  2005-2014 -0.005%, 2015-2024 -0.430%, up +0.020%, down -1.074%, sideways -0.574%, large -0.218%, months 240
  years: 2005 +36.209%, 2006 +39.834%, 2007 +54.765%, 2008 -22.935%, 2009 +49.334%, 2010 +17.947%, 2011 -14.254%, 2012 +1.930%, 2013 -2.167%, 2014 +31.388%, 2015 -8.625%, 2016 -0.038%, 2017 +22.964%, 2018 -7.652%, 2019 -0.357%, 2020 +18.066%, 2021 +24.119%, 2022 -2.988%, 2023 +14.708%, 2024 +8.805%
  FAIL: excess t -0.84 is not above 3; 2005-2014 excess -0.005% is not above 0; 2015-2024 excess -0.430% is not above 0; down -1.074% is not above 0; sideways -0.574% is not above 0; large-cap excess -0.218% is not above 0; neither path clears: CAGR +11.128% vs NIFTY +12.929%, max DD -29.871% vs -59.856%, ratio 0.373 vs 0.216

faber 8m | +11.247% | -29.871% | 0.377 | -16.345% | -0.214% | -0.80 | -0.070% | -0.359% | -0.022% | -0.943% | -0.473% | -0.214% | 97/100 | FAIL
  2005-2014 -0.070%, 2015-2024 -0.359%, up -0.022%, down -0.943%, sideways -0.473%, large -0.214%, months 240
  years: 2005 +23.881%, 2006 +27.842%, 2007 +54.765%, 2008 -16.345%, 2009 +49.334%, 2010 +17.947%, 2011 -11.080%, 2012 +5.221%, 2013 -4.988%, 2014 +31.388%, 2015 -7.974%, 2016 +5.151%, 2017 +22.728%, 2018 -6.962%, 2019 -0.151%, 2020 +18.066%, 2021 +24.119%, 2022 -2.988%, 2023 +14.708%, 2024 +10.972%
  FAIL: excess t -0.80 is not above 3; 2005-2014 excess -0.070% is not above 0; 2015-2024 excess -0.359% is not above 0; up -0.022% is not above 0; down -0.943% is not above 0; sideways -0.473% is not above 0; large-cap excess -0.214% is not above 0; neither path clears: CAGR +11.247% vs NIFTY +12.929%, max DD -29.871% vs -59.856%, ratio 0.377 vs 0.216

faber 12m | +10.326% | -38.082% | 0.271 | -28.891% | -0.288% | -1.03 | -0.302% | -0.275% | -0.022% | -1.074% | -0.840% | -0.288% | 98/100 | FAIL
  2005-2014 -0.302%, 2015-2024 -0.275%, up -0.022%, down -1.074%, sideways -0.840%, large -0.288%, months 240
  years: 2005 +36.209%, 2006 +39.834%, 2007 +54.765%, 2008 -28.891%, 2009 +16.729%, 2010 +17.947%, 2011 -14.254%, 2012 +1.929%, 2013 -2.168%, 2014 +31.388%, 2015 -4.624%, 2016 -0.038%, 2017 +28.646%, 2018 -1.682%, 2019 -0.437%, 2020 +18.066%, 2021 +24.119%, 2022 +0.180%, 2023 +14.708%, 2024 +8.805%
  FAIL: excess t -1.03 is not above 3; 2005-2014 excess -0.302% is not above 0; 2015-2024 excess -0.275% is not above 0; up -0.022% is not above 0; down -1.074% is not above 0; sideways -0.840% is not above 0; large-cap excess -0.288% is not above 0; neither path clears: CAGR +10.326% vs NIFTY +12.929%, max DD -38.082% vs -59.856%, ratio 0.271 vs 0.216

Variants that pass: 1 of 12.


### Survivorship calibration

PASS in-sample, but inflated by survivorship bias; real NIFTY200 Momentum 30 TRI: 18.8% CAGR vs NIFTY 50 TRI 13.6% since Apr 2005 (HDFC MF, Jul 2026)

Price indices only. Dividends are excluded. Our momentum book is monthly and equal weight, with no volatility scaling and no 5% caps. The published NIFTY200 Momentum 30 index is a different portfolio. CAGR below is close-to-close on the shared sessions, annualised with 365.25-day years. The attempt 11 pass mark is unchanged.

Random K=30 books: 100 runs, seed 20265106. These are the attempt 11 random draws for mom 12-1 K30.
NIFTY 200 overlap: 2005-01-03 to 2024-12-31 (4960 sessions).
Random K=30 mean CAGR +19.388%. NIFTY 200 CAGR +13.010%. Survivorship bias (random minus NIFTY 200) +6.377%.

mom 12-1 K30 overlap with NIFTY200MOMENTM30: 2005-05-02 to 2024-12-31 (4865 sessions).
mom 12-1 K30 CAGR +32.365%. NIFTY200MOMENTM30 price CAGR +19.852%.
mom 12-1 K30 CAGR minus the NIFTY 200 survivorship bias: +25.987%, next to NIFTY200MOMENTM30 +19.852%.

year | bias (random K=30 minus NIFTY 200) | mom 12-1 K30 | that year minus the bias | NIFTY200MOMENTM30
2005 | +21.037% | +78.021% | +56.985% | +49.759%
2006 | +61.277% | +123.009% | +61.733% | +42.596%
2007 | +5.864% | +122.681% | +116.817% | +99.260%
2008 | -2.889% | -66.104% | -63.215% | -60.354%
2009 | +55.961% | +84.532% | +28.571% | +67.219%
2010 | +6.489% | +27.674% | +21.185% | +18.362%
2011 | -2.968% | -19.205% | -16.236% | -17.311%
2012 | +8.570% | +55.300% | +46.730% | +37.141%
2013 | -6.157% | +13.842% | +19.999% | +11.584%
2014 | +23.471% | +100.875% | +77.404% | +47.905%
2015 | -2.645% | +8.920% | +11.565% | +9.918%
2016 | +8.833% | +5.061% | -3.772% | +8.506%
2017 | +8.843% | +79.551% | +70.708% | +54.472%
2018 | -11.693% | -4.547% | +7.146% | -2.446%
2019 | -12.198% | +11.892% | +24.090% | +9.737%
2020 | +8.434% | +34.856% | +26.422% | +18.831%
2021 | +14.225% | +85.803% | +71.578% | +52.143%
2022 | -5.202% | +0.319% | +5.521% | -6.401%
2023 | +20.661% | +65.282% | +44.621% | +40.667%
2024 | +6.111% | +34.378% | +28.268% | +20.006%


### Holdout of mom 12-1 K20 above200

One holdout run of mom 12-1 K20 above200, logged with final=True. Window 2025-01-01 to 2026-11-04 (457 sessions). The book is the attempt 11 rule: monthly 12-1 momentum, K=20, held only when the NIFTY month-end close is above its 200-day average, otherwise the book is NIFTY 50. Idle cash is in the NIFTY 50 price. Delivery costs apply to stock buys and sells. Dividends are excluded. CAGR is annualised with 365.25-day years. The attempt 11 rule is unchanged.

mom 12-1 K20 above200: CAGR +1.865%, max drawdown -15.816%, mean monthly excess vs NIFTY 50 +0.115% over 23 months.
NIFTY 50 over the same dates: CAGR +0.740%, max drawdown -15.560%.
NIFTY200MOMENTM30 over 2025-01-01 to 2026-11-04 (457 sessions): CAGR -5.057%, max drawdown -22.412%, mean monthly excess of the book vs this index +0.506%.

The same survivorship comparison on this window:

Price indices only. Dividends are excluded. Our momentum book is monthly and equal weight, with no volatility scaling and no 5% caps. The published NIFTY200 Momentum 30 index is a different portfolio. CAGR below is close-to-close on the shared sessions, annualised with 365.25-day years. The attempt 11 pass mark is unchanged.

Random K=30 books: 100 runs, seed 20265106. These are the attempt 11 random draws for mom 12-1 K30.
NIFTY 200 overlap: 2025-01-01 to 2026-11-04 (457 sessions).
Random K=30 mean CAGR +1.161%. NIFTY 200 CAGR +1.006%. Survivorship bias (random minus NIFTY 200) +0.155%.

mom 12-1 K30 overlap with NIFTY200MOMENTM30: 2025-01-01 to 2026-11-04 (457 sessions).
mom 12-1 K30 CAGR +6.182%. NIFTY200MOMENTM30 price CAGR -5.197%.
mom 12-1 K30 CAGR minus the NIFTY 200 survivorship bias: +6.027%, next to NIFTY200MOMENTM30 -5.197%.

year | bias (random K=30 minus NIFTY 200) | mom 12-1 K30 | that year minus the bias | NIFTY200MOMENTM30
2025 | -5.227% | -2.373% | +2.854% | -5.359%
2026 | +5.205% | +14.382% | +9.177% | -4.218%


## Attempt 12

Rules fixed on 2026-11-07, before the run.

Hypothesis: one of twelve intraday variants clears the pass mark below on 2015-2024. Entry and exit are 5-minute bars whose labels are the bar end. Nothing is held overnight.

Common rules. A session is used only when every bar from 09:15 to 15:10 is present, using the bar start. The position is flat at the 15:10 bar close unless the rule exits earlier. Gao exits at the 15:25 bar close, which is the one later exit. R is |entry - stop|. A stock trade risks Rs 2,000 and is capped at Rs 5,00,000 of entry value, in whole shares. One tick of slippage, from nse_market.tick_for, is charged against the trade on the entry and on the exit. NIFTY 50 uses tick_for with symbol NIFTY, so the index tick is 0.05. Stock costs use the india/costs.py intraday schedule. R before is after the tick and before charges. R after is after the tick and the charges. A later bar that opens through the stop fills at the open. Otherwise a touch fills at the stop. The stop is taken before the target when both can fill on the same bar. The entry bar is not scanned for the stop.

NIFTY trades use the NIFTY 50 index bars as the price and one lot of 75 units, not the Rs 2,000 sizer. Futures costs, check your broker: brokerage Rs 20 per order, STT 0.05% on the sell side, exchange 0.00173% on both sides, SEBI 0.0001% on both sides, stamp 0.002% on the buy, GST 18% on brokerage + exchange + SEBI.

Universe for the stock strategies: each day, the 200 symbols with the highest average close times volume over the previous 20 sessions, and the 20 sessions must sit in one segment. Large caps are the top 100 by that same average. NIFTY has no stock book, so its large-cap average is its own average R. Market type is india/research/regime.py, known before the open. The window is 2015-01-01 through 2024-12-31. Dates from 2025-01-01 on are not requested.

Random baseline, 100 seeded runs, seed 20261106 plus an offset per variant. Each run keeps the symbol, the day, the direction, the stop distance and the target distance, and enters at a random bar inside that rule's entry window. Gao's window is the 15:00 bar only. Excess R for a trade is its R after costs minus the mean R of those random entries. The t-statistic is the one-sample t of the mean excess in each calendar month.

Pass mark, fixed before this run: average R after costs and slippage at least +0.10; at least 300 trades on at least 100 distinct days; t vs random above 3; average R after costs above 0 in 2015-2019 and in 2020-2024; above 0 on up, down, and sideways days; above 0 in large caps; and at least 2 of that strategy's 3 variants have t above 2. A value on a stated boundary passes. An empty bucket does not. The attempt 11 mark is unchanged.

1. NIFTY intraday momentum. r1 is the 09:45 close divided by the previous session's last close, minus 1. At the 15:00 bar close, go long if r1 > 0 and short if r1 < 0. Exit at the 15:25 close. There is no stop. R is 0.25% of the entry, for reporting only. Variants: nifty mom always; nifty mom abs 0.25, which also requires |r1| > 0.25%; nifty mom same sign, which also requires r1 and the 15:00 close divided by the 14:30 close, minus 1, to be strictly the same sign.

2. Crabel NR. The signal day is the strict narrowest daily high-low of the last 7 days, or 4, including that day, inside one segment. The next session trades. The opening range is the high and low of bars ending 09:20 through 09:45. Enter on the first 5-minute close beyond that range, either side, on a bar ending 09:50 through 14:30. The stop is the other side of the range. Exit at the 15:10 close. Variants: NR7; NR4; NR7 inside, which also requires the signal day's high to be strictly below the prior high and its low strictly above the prior low.

3. Gaps. The gap is the 09:20 bar's open divided by the previous session's daily close, minus 1. A gap of exactly the threshold counts. gap GO 1.5 and gap GO 3 enter on the first close beyond the 15-minute range (bars ending 09:20 through 09:30) in the gap's direction, on a bar ending 09:35 through 15:05. The stop is the other side of that range. gap FADE 1.5 requires the open to be outside yesterday's high-low. After the first 15 minutes, the first close back inside that range is a fade: short after a gap up, long after a gap down, toward yesterday's close. The stop is the day's extreme through the signal bar. The target is yesterday's close, and the trade is skipped when that target is not beyond the entry. Exit at 15:10 at the latest. Thresholds: 1.5% for GO and FADE, 3% for the third GO.

4. VWAP reversion, only on sideways days. VWAP starts at the 09:20 bar and uses bar volume times typical price (high + low + close) / 3, including the current bar. Between bars ending 10:00 and 14:00, the first close at least X percent below VWAP is a long, and the first close at least X percent above is a short. The target is that bar's VWAP. The stop is the same distance beyond the entry. Exit at 15:10. Variants: vwap 1.5 sideways, vwap 2.0 sideways, vwap 2.5 sideways. A strategy that trades only sideways days has empty up and down buckets.

Reports: trades, distinct days, win rate (share of trades with R after costs above 0), average R before and after costs, t vs random, 2015-2019, 2020-2024, up, down, sideways, large caps, and each year.

Results.
variant | trades | days | win | R before | R after | t | 2015-19 | 2020-24 | up | down | sideways | large | result
nifty mom always | 2,429 | 2429 | 38.1% | +0.035 | -0.212 | +0.00 | -0.213 | -0.210 | -0.206 | -0.186 | -0.253 | -0.212 | FAIL
nifty mom abs 0.25 | 1,420 | 1420 | 40.1% | +0.056 | -0.190 | +0.00 | -0.164 | -0.212 | -0.183 | -0.164 | -0.233 | -0.190 | FAIL
nifty mom same sign | 1,290 | 1290 | 41.2% | +0.098 | -0.149 | +0.00 | -0.138 | -0.160 | -0.166 | -0.044 | -0.154 | -0.149 | FAIL
NR7 | 64,448 | 2386 | 44.4% | +0.031 | -0.019 | -22.11 | -0.011 | -0.027 | -0.017 | -0.004 | -0.037 | -0.003 | FAIL
NR4 | 110,413 | 2409 | 44.4% | +0.027 | -0.022 | -28.39 | -0.017 | -0.028 | -0.022 | -0.006 | -0.036 | -0.007 | FAIL
NR7 inside | 23,994 | 2307 | 44.8% | +0.038 | -0.012 | -14.46 | -0.005 | -0.019 | -0.006 | +0.016 | -0.057 | +0.008 | FAIL
gap GO 1.5 | 17,066 | 2229 | 45.8% | +0.048 | +0.011 | -14.35 | +0.010 | +0.011 | +0.014 | -0.031 | +0.042 | +0.043 | FAIL
gap FADE 1.5 | 10,636 | 2059 | 62.6% | +0.048 | +0.007 | -0.67 | +0.027 | -0.010 | +0.005 | +0.028 | -0.012 | +0.024 | FAIL
gap GO 3 | 3,834 | 1234 | 50.0% | +0.106 | +0.075 | -6.84 | +0.095 | +0.064 | +0.064 | +0.013 | +0.156 | +0.098 | FAIL
vwap 1.5 sideways | 22,424 | 429 | 48.1% | -0.038 | -0.082 | +29.08 | -0.084 | -0.079 | n/a | n/a | -0.082 | -0.100 | FAIL
vwap 2.0 sideways | 11,001 | 429 | 48.5% | -0.034 | -0.073 | +23.91 | -0.084 | -0.062 | n/a | n/a | -0.073 | -0.082 | FAIL
vwap 2.5 sideways | 5,701 | 423 | 48.8% | -0.021 | -0.056 | +24.34 | -0.076 | -0.036 | n/a | n/a | -0.056 | -0.064 | FAIL

nifty mom always FAIL: avg R after costs -0.212 is below +0.10; t vs random +0.00 is not above 3; 2015-2019 -0.213 is not above 0; 2020-2024 -0.210 is not above 0; up -0.206 is not above 0; down -0.186 is not above 0; sideways -0.253 is not above 0; large caps -0.212 is not above 0; family variants with t above 2: 0 of 3, need 2
  years: 2015 -0.123, 2016 -0.184, 2017 -0.249, 2018 -0.207, 2019 -0.292, 2020 -0.264, 2021 -0.154, 2022 -0.182, 2023 -0.230, 2024 -0.222
nifty mom abs 0.25 FAIL: avg R after costs -0.190 is below +0.10; t vs random +0.00 is not above 3; 2015-2019 -0.164 is not above 0; 2020-2024 -0.212 is not above 0; up -0.183 is not above 0; down -0.164 is not above 0; sideways -0.233 is not above 0; large caps -0.190 is not above 0; family variants with t above 2: 0 of 3, need 2
  years: 2015 -0.107, 2016 -0.165, 2017 -0.252, 2018 -0.146, 2019 -0.155, 2020 -0.240, 2021 -0.088, 2022 -0.232, 2023 -0.250, 2024 -0.269
nifty mom same sign FAIL: avg R after costs -0.149 is below +0.10; t vs random +0.00 is not above 3; 2015-2019 -0.138 is not above 0; 2020-2024 -0.160 is not above 0; up -0.166 is not above 0; down -0.044 is not above 0; sideways -0.154 is not above 0; large caps -0.149 is not above 0; family variants with t above 2: 0 of 3, need 2
  years: 2015 +0.058, 2016 -0.089, 2017 -0.225, 2018 -0.142, 2019 -0.262, 2020 -0.209, 2021 -0.097, 2022 -0.007, 2023 -0.178, 2024 -0.305
NR7 FAIL: avg R after costs -0.019 is below +0.10; t vs random -22.11 is not above 3; 2015-2019 -0.011 is not above 0; 2020-2024 -0.027 is not above 0; up -0.017 is not above 0; down -0.004 is not above 0; sideways -0.037 is not above 0; large caps -0.003 is not above 0; family variants with t above 2: 0 of 3, need 2
  years: 2015 +0.005, 2016 +0.019, 2017 -0.013, 2018 -0.011, 2019 -0.049, 2020 -0.040, 2021 +0.002, 2022 -0.001, 2023 -0.061, 2024 -0.035
NR4 FAIL: avg R after costs -0.022 is below +0.10; t vs random -28.39 is not above 3; 2015-2019 -0.017 is not above 0; 2020-2024 -0.028 is not above 0; up -0.022 is not above 0; down -0.006 is not above 0; sideways -0.036 is not above 0; large caps -0.007 is not above 0; family variants with t above 2: 0 of 3, need 2
  years: 2015 -0.002, 2016 +0.004, 2017 -0.017, 2018 -0.020, 2019 -0.044, 2020 -0.045, 2021 -0.012, 2022 -0.005, 2023 -0.055, 2024 -0.024
NR7 inside FAIL: avg R after costs -0.012 is below +0.10; t vs random -14.46 is not above 3; 2015-2019 -0.005 is not above 0; 2020-2024 -0.019 is not above 0; up -0.006 is not above 0; sideways -0.057 is not above 0; family variants with t above 2: 0 of 3, need 2
  years: 2015 +0.002, 2016 +0.031, 2017 -0.008, 2018 +0.003, 2019 -0.047, 2020 -0.028, 2021 -0.003, 2022 +0.005, 2023 -0.036, 2024 -0.031
gap GO 1.5 FAIL: avg R after costs +0.011 is below +0.10; t vs random -14.35 is not above 3; down -0.031 is not above 0; family variants with t above 2: 0 of 3, need 2
  years: 2015 +0.048, 2016 +0.016, 2017 +0.041, 2018 -0.020, 2019 -0.037, 2020 +0.014, 2021 -0.029, 2022 +0.033, 2023 -0.018, 2024 +0.025
gap FADE 1.5 FAIL: avg R after costs +0.007 is below +0.10; t vs random -0.67 is not above 3; 2020-2024 -0.010 is not above 0; sideways -0.012 is not above 0; family variants with t above 2: 0 of 3, need 2
  years: 2015 -0.010, 2016 -0.014, 2017 +0.023, 2018 +0.111, 2019 +0.009, 2020 -0.003, 2021 -0.014, 2022 -0.021, 2023 -0.029, 2024 +0.004
gap GO 3 FAIL: avg R after costs +0.075 is below +0.10; t vs random -6.84 is not above 3; family variants with t above 2: 0 of 3, need 2
  years: 2015 +0.280, 2016 +0.007, 2017 +0.158, 2018 -0.087, 2019 +0.095, 2020 +0.071, 2021 -0.013, 2022 +0.176, 2023 -0.037, 2024 +0.019
vwap 1.5 sideways FAIL: avg R after costs -0.082 is below +0.10; 2015-2019 -0.084 is not above 0; 2020-2024 -0.079 is not above 0; up n/a is not above 0; down n/a is not above 0; sideways -0.082 is not above 0; large caps -0.100 is not above 0
  years: 2015 -0.107, 2016 -0.074, 2017 -0.158, 2018 -0.066, 2019 -0.081, 2020 -0.093, 2022 -0.070, 2023 -0.105, 2024 +0.083
vwap 2.0 sideways FAIL: avg R after costs -0.073 is below +0.10; 2015-2019 -0.084 is not above 0; 2020-2024 -0.062 is not above 0; up n/a is not above 0; down n/a is not above 0; sideways -0.073 is not above 0; large caps -0.082 is not above 0
  years: 2015 -0.103, 2016 -0.080, 2017 -0.013, 2018 -0.065, 2019 -0.085, 2020 -0.079, 2022 -0.044, 2023 -0.108, 2024 +0.108
vwap 2.5 sideways FAIL: avg R after costs -0.056 is below +0.10; 2015-2019 -0.076 is not above 0; 2020-2024 -0.036 is not above 0; up n/a is not above 0; down n/a is not above 0; sideways -0.056 is not above 0; large caps -0.064 is not above 0
  years: 2015 -0.090, 2016 -0.067, 2017 -0.139, 2018 -0.017, 2019 -0.100, 2020 -0.048, 2022 -0.019, 2023 -0.121, 2024 +0.126

Variants that pass: 0 of 12.


## Attempt 13

Rules fixed on 2026-11-07, before the run.

hypothesis found in attempt 12 data (gap GO 3 lost to random same-day entries); must clear the full pass mark.

Hypothesis: one of the three big-gap continuation variants clears the attempt 12 pass mark on 2015-2024. The attempt 12 gap GO 3 rule entered on the first close beyond the opening range and lost to a random bar on the same day. This attempt enters only at the 09:30 close, in the gap's direction, and it must beat a non-gap day as well as a random bar. The full pass mark applies. It is not lowered because the idea came from the earlier sample.

Common rules. Bar labels are the bar end, same as attempt 12. A session is used only when every bar from 09:15 to 15:10 is present. The gap is the 09:20 bar's open divided by the previous session's daily close, minus 1, and the previous close is the previous daily row in the same segment. A threshold uses >=, so a gap of exactly 3% or exactly 4% counts. Direction is long when the gap is positive and short when it is negative. A gap of zero does not trade. The entry is the 09:30 bar's close, and only when that close is still strictly beyond the previous close in the gap's direction. The stop is the opposite extreme of the bars ending 09:20, 09:25 and 09:30: the low for a long, the high for a short. The entry bar is inside that range, and it is not scanned for the stop. Exit at the 15:10 close. There is no target.

R is |entry - stop|. A trade risks Rs 2,000 and is capped at Rs 5,00,000 of entry value, in whole shares. One tick of slippage, from nse_market.tick_for, is charged on the entry and on the exit. Costs are the india/costs.py intraday schedule. R before is after the tick and before charges. R after is after the tick and the charges. A later bar that opens through the stop fills at the open. Otherwise a touch fills at the stop.

Universe: each day, the 200 symbols with the highest average close times volume over the previous 20 sessions, and those 20 sessions must sit in one segment. Large caps are the top 100 by that same average. Market type is india/research/regime.py, known before the open. The window is 2015-01-01 through 2024-12-31. Dates from 2025-01-01 on are not requested.

Volume variant. The opening volume is the sum of volume on bars ending 09:20 through 09:30. It must be at least 2 times the average opening volume of the previous 10 usable sessions in the same segment. Exactly 2 times passes. Fewer than 10 prior sessions in the segment skips the day. A new segment starts the count again.

Two baselines, 100 seeded runs. The same-day baseline keeps the symbol, the day, the direction and the stop distance, and enters at a random bar ending 09:30 through 14:30. Its seed is 20261106 + variant index * 1000 + the run index. The non-gap baseline uses the same symbol on a random usable day in the same calendar month whose absolute gap is strictly below 0.5%. Exactly 0.5% is not eligible. The entry is that day's 09:30 close, the direction is random, the stop is that day's own 09:15-09:30 extreme, and the exit is 15:10. Its seed is the same-day seed plus 500. A month with no non-gap day leaves that trade out of the non-gap t. The trade still counts in the average R. Excess R is R after costs minus the mean of the random Rs. The t-statistic is the one-sample t of the mean excess in each calendar month. Both excesses and both t values are reported. The pass mark uses the non-gap t.

Pass mark, the same as attempt 12, fixed before this run: average R after costs and slippage at least +0.10; at least 300 trades on at least 100 distinct days; t versus the non-gap baseline above 3; average R after costs above 0 in 2015-2019 and in 2020-2024; above 0 on up, down, and sideways days; above 0 in large caps; and at least 2 of the 3 variants have non-gap t above 2. A value on a stated boundary passes. An empty bucket does not.

Variants. (a) gap cont 3, absolute gap at least 3%. (b) gap cont 4, absolute gap at least 4%. (c) gap cont 3 vol, the 3% rule plus the opening-volume multiple. A day can qualify for more than one variant. Each variant is scored on its own trades.

Results.
variant | trades | days | win | R before | R after | excess same | t same | excess non-gap | t non-gap | 2015-19 | 2020-24 | up | down | sideways | large | result
gap cont 3 | 9,196 | 1918 | 25.9% | +0.041 | -0.068 | +0.019 | -0.24 | +0.022 | -0.25 | -0.162 | -0.012 | -0.065 | -0.154 | +0.019 | +0.040 | FAIL
gap cont 4 | 4,866 | 1444 | 25.2% | -0.004 | -0.103 | -0.016 | +0.39 | -0.014 | +1.07 | -0.196 | -0.050 | -0.022 | -0.374 | +0.039 | +0.040 | FAIL
gap cont 3 vol | 4,326 | 1692 | 28.3% | -0.028 | -0.120 | +0.029 | +0.38 | +0.024 | +0.23 | -0.185 | -0.069 | -0.087 | -0.370 | -0.034 | +0.008 | FAIL

gap cont 3 FAIL: avg R after costs -0.068 is below +0.10; t vs non-gap -0.25 is not above 3; 2015-2019 -0.162 is not above 0; 2020-2024 -0.012 is not above 0; up -0.065 is not above 0; down -0.154 is not above 0; family variants with t above 2: 0 of 3, need 2
  years: 2015 +0.039, 2016 -0.312, 2017 -0.104, 2018 -0.514, 2019 +0.275, 2020 -0.033, 2021 -0.173, 2022 +0.121, 2023 -0.151, 2024 +0.106
gap cont 4 FAIL: avg R after costs -0.103 is below +0.10; t vs non-gap +1.07 is not above 3; 2015-2019 -0.196 is not above 0; 2020-2024 -0.050 is not above 0; up -0.022 is not above 0; down -0.374 is not above 0; family variants with t above 2: 0 of 3, need 2
  years: 2015 +0.084, 2016 -0.367, 2017 -0.106, 2018 -0.628, 2019 +0.216, 2020 -0.238, 2021 +0.036, 2022 +0.290, 2023 -0.098, 2024 +0.200
gap cont 3 vol FAIL: avg R after costs -0.120 is below +0.10; t vs non-gap +0.23 is not above 3; 2015-2019 -0.185 is not above 0; 2020-2024 -0.069 is not above 0; up -0.087 is not above 0; down -0.370 is not above 0; sideways -0.034 is not above 0; family variants with t above 2: 0 of 3, need 2
  years: 2015 -0.387, 2016 -0.250, 2017 -0.096, 2018 -0.428, 2019 +0.214, 2020 -0.175, 2021 +0.032, 2022 -0.258, 2023 -0.132, 2024 +0.164

Variants that pass: 0 of 3.


## Attempt 14

Rules fixed on 2026-11-07, before the run.

Hypothesis: one short-swing family clears the pass mark below on 2005-2024. Signals use the close. The buy is the next session's open, in the same segment. Every signal is its own round trip, including one that overlaps another open trade. Long only. Delivery costs are signal_lab.delivery on a Rs 1,00,000 notional, in whole shares. A price that does not fit one share is skipped. Dividends are excluded.

Universe for the stock rules: the 200 names with the highest average close times volume over the 60 sessions before the signal day, one segment only. Large caps are the top 100 by that average on the signal day. A random entry instead requires the name to be in the top 200 on the entry day, because that is what is known at the open, and the signal condition is not required. Market type is india/research/regime.py on the entry date, from earlier NIFTY closes only. The window is 2005-01-01 through 2024-12-31. An exit that would need a session after 2024-12-31 is skipped. Dates from 2025-01-01 on are not requested.

RSI(2). Wilder RSI from ta.rsi_series, period 2. SMA200 and SMA5 are ta.sma_series on the same segment. Buy when the close is strictly above SMA200 and RSI(2) is strictly below the threshold. Exit at the next open after a close strictly above that session's SMA5. The entry session's close can be the trigger, which sells at the following open. If no close does that, sell at the open five sessions after the entry session. Variants: rsi2 < 5; rsi2 < 10; rsi2 < 10 down2, which also requires the signal close and the close before it to each be strictly below the close before them.

IBS. IBS is (close - low) / (high - low). A bar with high equal to low has no IBS and no signal. Buy when the close is strictly above SMA200 and IBS is strictly below the threshold. Exit at the next open after a close strictly above the prior session's high, or at the open five sessions after the entry. Variants: ibs < 0.2; ibs < 0.1; ibs < 0.2 nifty. The third trades the NIFTY 50 index itself, price only, no futures and no futures charges. The same delivery cost and Rs 1,00,000 notional are applied to the index points, as a NIFTYBEES-like cash book. Its large-cap average is its own average return. Its random entries are other NIFTY sessions in the same month.

Turtle soup. The prior low is the lowest low of the N sessions before the signal day, today not included. Buy when today's low is strictly below that prior low and today's close is strictly back above it. The stop is the signal day's low. The next open must be strictly above that low, otherwise the trade is skipped. The target is the entry plus 2 times (entry - stop). On the entry day and the two following sessions, a gap through the stop fills at the open, a low through the stop fills at the stop, and a high through the target fills at the target. The stop is taken before the target on the same day. If neither is hit, sell at the open three sessions after the entry. Variants: soup 20, soup 10, soup 55.

Short-term reversal, a portfolio. Every Monday, rank the top 200 by the 5-session return ending at the previous session: that close divided by the close five sessions before it, minus 1. Monday's own close is not in the rank. Buy the K worst at Monday's open, equal weight, each name sized by delivery() at Rs 1,00,000. Sell at the next Monday's open. The next Monday is the next session that falls on a Monday. A name must have both opens in the same segment. When fewer than K names qualify, those names are the book. A week with no name is skipped. Each week is its own round trip: the book is sold and, if it qualifies again, bought again, so costs apply both times. Variants: rev K10; rev K20; rev K10 above200, which is taken only when the previous session's NIFTY close is strictly above the 200-day average of NIFTY closes through that previous session. This is a level test, not the regime slope. When the filter fails, the week is omitted, not scored as zero. The average return is the mean of the weekly book returns. The large-cap figure is the mean of those weekly returns computed from only the picked names that were in the top 100 that Monday. A week with no large-cap name stays out of that bucket.

Random baseline, 100 seeded runs, seed 20261106 + variant index * 1000 + the run index. For a stock or index trade, each run picks a random eligible entry in the same calendar month and applies that variant's own exit. A turtle draw whose previous-day low is not below the open is dropped from the mean. For the Monday book, each run picks K random eligible names that Monday and holds them to the same next Monday. The market adjustment is the NIFTY price return over the same window: entry open to the exit open when the exit is an open, and entry open to the NIFTY close of the exit day when the exit is a stop or a target. Excess is (trade return - NIFTY return) minus the mean of that figure on the random entries. On the Monday book the window matches, so NIFTY cancels and the excess is the book minus the random book. The t-statistic is the one-sample t of the mean excess in each calendar month of the entry date.

Pass mark, fixed before this run: average raw return after costs above 0; t versus random above 3, on the market-adjusted excess; raw return above 0 in 2005-2014 and in 2015-2024; above 0 on up, down, and sideways entries; above 0 in large caps; and at least 2 of the 3 variants in the family have t above 2. A value on a stated boundary passes where the word is 'at least'. The averages here are strict. An empty bucket does not. The survivorship bias is not subtracted. Next to each result, the measured annual survivorship bias (random K=30 CAGR minus the NIFTY 200 price CAGR, from survivorship.py on this same 2005-2024 window) is scaled to the variant's average holding length in calendar days: (1 + annual) ** (days / 365.25) - 1. The scaled figure is printed and is not used in the pass test.

In the experiments table, the two return columns are the average percent return after costs and the market-adjusted t. The printed summary is the long table.

Results.
variant | trades | days | avg return | excess | t | 2005-14 | 2015-24 | up | down | sideways | large | hold days | bias over hold | result
rsi2 < 5 | 30,513 | 4027 | +0.568% | +1.057% | +21.37 | +0.555% | +0.581% | +0.558% | +0.023% | +0.875% | +0.641% | 4.71 | +0.080% | PASS
rsi2 < 10 | 60,373 | 4568 | +0.403% | +0.741% | +13.63 | +0.415% | +0.392% | +0.388% | +0.129% | +0.628% | +0.446% | 4.71 | +0.080% | PASS
rsi2 < 10 down2 | 52,023 | 4472 | +0.425% | +0.755% | +13.37 | +0.436% | +0.415% | +0.406% | +0.160% | +0.677% | +0.472% | 4.73 | +0.080% | PASS
ibs < 0.2 | 126,464 | 4854 | +0.150% | +0.048% | +0.80 | +0.189% | +0.110% | +0.122% | -0.002% | +0.440% | +0.146% | 5.56 | +0.094% | FAIL
ibs < 0.1 | 29,236 | 4394 | +0.133% | +0.084% | +1.65 | +0.089% | +0.185% | +0.096% | +0.073% | +0.466% | +0.145% | 5.68 | +0.096% | FAIL
ibs < 0.2 nifty | 727 | 727 | -0.035% | -0.000% | -1.88 | -0.046% | -0.025% | -0.053% | n/a | +0.263% | -0.035% | 4.89 | +0.083% | FAIL
soup 20 | 39,790 | 4312 | -0.410% | +0.330% | +12.19 | -0.580% | -0.244% | -0.370% | -0.707% | -0.285% | -0.357% | 2.18 | +0.037% | FAIL
soup 10 | 62,797 | 4725 | -0.396% | +0.295% | +14.60 | -0.548% | -0.246% | -0.370% | -0.636% | -0.285% | -0.342% | 2.11 | +0.036% | FAIL
soup 55 | 19,269 | 3236 | -0.447% | +0.359% | +6.21 | -0.589% | -0.308% | -0.367% | -0.774% | -0.314% | -0.360% | 2.24 | +0.038% | FAIL
rev K10 | 988 | 988 | +0.325% | +0.117% | +1.32 | +0.472% | +0.176% | +0.164% | +0.691% | +0.729% | +0.375% | 7.39 | +0.125% | FAIL
rev K20 | 988 | 988 | +0.374% | +0.173% | +3.03 | +0.481% | +0.267% | +0.225% | +0.551% | +0.902% | +0.349% | 7.39 | +0.125% | FAIL
rev K10 above200 | 753 | 753 | +0.236% | +0.025% | +0.14 | +0.497% | -0.030% | +0.164% | n/a | +1.125% | +0.195% | 7.39 | +0.125% | FAIL

rsi2 < 5 PASS. survivorship bias +6.377% a year, +0.080% over 4.71 holding days (not subtracted).
  years: 2005 +0.378%, 2006 +0.109%, 2007 +0.987%, 2008 -1.219%, 2009 +1.798%, 2010 +0.742%, 2011 -0.423%, 2012 +0.378%, 2013 +0.243%, 2014 +1.176%, 2015 +0.783%, 2016 -0.167%, 2017 +0.915%, 2018 -0.138%, 2019 +0.353%, 2020 -0.217%, 2021 +1.083%, 2022 +0.452%, 2023 +0.862%, 2024 +0.793%
rsi2 < 10 PASS. survivorship bias +6.377% a year, +0.080% over 4.71 holding days (not subtracted).
  years: 2005 +0.320%, 2006 -0.065%, 2007 +0.952%, 2008 -1.499%, 2009 +1.434%, 2010 +0.574%, 2011 -0.601%, 2012 +0.441%, 2013 +0.088%, 2014 +0.919%, 2015 +0.544%, 2016 -0.104%, 2017 +0.665%, 2018 -0.217%, 2019 +0.218%, 2020 -0.060%, 2021 +0.740%, 2022 +0.088%, 2023 +0.787%, 2024 +0.538%
rsi2 < 10 down2 PASS. survivorship bias +6.377% a year, +0.080% over 4.73 holding days (not subtracted).
  years: 2005 +0.288%, 2006 +0.007%, 2007 +0.998%, 2008 -1.280%, 2009 +1.517%, 2010 +0.579%, 2011 -0.639%, 2012 +0.407%, 2013 +0.116%, 2014 +0.879%, 2015 +0.577%, 2016 -0.141%, 2017 +0.657%, 2018 -0.242%, 2019 +0.251%, 2020 +0.012%, 2021 +0.771%, 2022 +0.109%, 2023 +0.846%, 2024 +0.548%
ibs < 0.2 FAIL: t vs random +0.80 is not above 3; down -0.002% is not above 0; family variants with t above 2: 0 of 3, need 2. survivorship bias +6.377% a year, +0.094% over 5.56 holding days (not subtracted).
  years: 2005 +0.348%, 2006 +0.030%, 2007 +0.837%, 2008 -2.586%, 2009 +0.978%, 2010 +0.019%, 2011 -1.075%, 2012 +0.165%, 2013 -0.144%, 2014 +0.480%, 2015 -0.024%, 2016 -0.193%, 2017 +0.297%, 2018 -0.617%, 2019 -0.032%, 2020 +0.347%, 2021 +0.359%, 2022 -0.391%, 2023 +0.549%, 2024 +0.153%
ibs < 0.1 FAIL: t vs random +1.65 is not above 3; family variants with t above 2: 0 of 3, need 2. survivorship bias +6.377% a year, +0.096% over 5.68 holding days (not subtracted).
  years: 2005 +0.335%, 2006 -0.328%, 2007 +0.701%, 2008 -2.354%, 2009 +0.686%, 2010 -0.107%, 2011 -1.351%, 2012 +0.318%, 2013 -0.132%, 2014 +0.505%, 2015 +0.171%, 2016 -0.043%, 2017 +0.459%, 2018 -0.868%, 2019 +0.256%, 2020 +0.414%, 2021 +0.361%, 2022 -0.072%, 2023 +0.524%, 2024 +0.106%
ibs < 0.2 nifty FAIL: avg return after costs -0.035% is not above 0; t vs random -1.88 is not above 3; 2005-2014 -0.046% is not above 0; 2015-2024 -0.025% is not above 0; up -0.053% is not above 0; down n/a is not above 0; large caps -0.035% is not above 0; family variants with t above 2: 0 of 3, need 2. survivorship bias +6.377% a year, +0.083% over 4.89 holding days (not subtracted).
  years: 2005 -0.373%, 2006 +0.076%, 2007 +0.692%, 2008 -3.364%, 2009 +0.209%, 2010 -0.182%, 2011 -0.768%, 2012 +0.180%, 2013 -0.254%, 2014 +0.339%, 2015 -0.194%, 2016 -0.379%, 2017 +0.073%, 2018 -0.617%, 2019 +0.084%, 2020 -0.494%, 2021 +0.826%, 2022 -0.434%, 2023 -0.006%, 2024 +0.206%
soup 20 FAIL: avg return after costs -0.410% is not above 0; 2005-2014 -0.580% is not above 0; 2015-2024 -0.244% is not above 0; up -0.370% is not above 0; down -0.707% is not above 0; sideways -0.285% is not above 0; large caps -0.357% is not above 0. survivorship bias +6.377% a year, +0.037% over 2.18 holding days (not subtracted).
  years: 2005 -0.081%, 2006 -0.642%, 2007 -1.306%, 2008 -1.441%, 2009 +0.051%, 2010 -0.157%, 2011 -0.541%, 2012 -0.361%, 2013 -0.486%, 2014 -0.009%, 2015 +0.062%, 2016 -0.339%, 2017 +0.148%, 2018 -0.401%, 2019 -0.403%, 2020 -1.036%, 2021 -0.124%, 2022 -0.028%, 2023 -0.123%, 2024 -0.040%
soup 10 FAIL: avg return after costs -0.396% is not above 0; 2005-2014 -0.548% is not above 0; 2015-2024 -0.246% is not above 0; up -0.370% is not above 0; down -0.636% is not above 0; sideways -0.285% is not above 0; large caps -0.342% is not above 0. survivorship bias +6.377% a year, +0.036% over 2.11 holding days (not subtracted).
  years: 2005 -0.366%, 2006 -0.672%, 2007 -0.911%, 2008 -1.330%, 2009 -0.108%, 2010 -0.271%, 2011 -0.630%, 2012 -0.357%, 2013 -0.444%, 2014 +0.021%, 2015 -0.057%, 2016 -0.311%, 2017 +0.034%, 2018 -0.345%, 2019 -0.422%, 2020 -0.586%, 2021 -0.196%, 2022 -0.239%, 2023 -0.013%, 2024 -0.209%
soup 55 FAIL: avg return after costs -0.447% is not above 0; 2005-2014 -0.589% is not above 0; 2015-2024 -0.308% is not above 0; up -0.367% is not above 0; down -0.774% is not above 0; sideways -0.314% is not above 0; large caps -0.360% is not above 0. survivorship bias +6.377% a year, +0.038% over 2.24 holding days (not subtracted).
  years: 2005 +0.156%, 2006 -0.611%, 2007 -1.498%, 2008 -1.357%, 2009 +0.116%, 2010 +0.041%, 2011 -0.344%, 2012 -0.388%, 2013 -0.545%, 2014 +0.156%, 2015 +0.095%, 2016 -0.520%, 2017 +0.370%, 2018 -0.275%, 2019 -0.397%, 2020 -2.015%, 2021 -0.018%, 2022 +0.096%, 2023 -0.011%, 2024 +0.105%
rev K10 FAIL: t vs random +1.32 is not above 3; family variants with t above 2: 1 of 3, need 2. survivorship bias +6.377% a year, +0.125% over 7.39 holding days (not subtracted).
  years: 2005 +1.339%, 2006 +0.841%, 2007 +0.953%, 2008 -1.714%, 2009 +2.786%, 2010 +0.456%, 2011 -0.290%, 2012 +0.143%, 2013 -0.693%, 2014 +1.126%, 2015 +0.175%, 2016 +0.033%, 2017 +0.418%, 2018 -0.139%, 2019 -1.100%, 2020 +1.043%, 2021 +0.447%, 2022 +0.049%, 2023 +0.535%, 2024 +0.268%
rev K20 FAIL: family variants with t above 2: 1 of 3, need 2. survivorship bias +6.377% a year, +0.125% over 7.39 holding days (not subtracted).
  years: 2005 +1.149%, 2006 +0.752%, 2007 +1.018%, 2008 -1.704%, 2009 +2.461%, 2010 +0.346%, 2011 -0.528%, 2012 +0.453%, 2013 -0.193%, 2014 +1.238%, 2015 +0.123%, 2016 +0.353%, 2017 +0.625%, 2018 -0.078%, 2019 -0.744%, 2020 +0.780%, 2021 +0.561%, 2022 +0.121%, 2023 +0.612%, 2024 +0.313%
rev K10 above200 FAIL: t vs random +0.14 is not above 3; 2015-2024 -0.030% is not above 0; down n/a is not above 0; family variants with t above 2: 1 of 3, need 2. survivorship bias +6.377% a year, +0.125% over 7.39 holding days (not subtracted).
  years: 2005 +1.339%, 2006 +0.287%, 2007 +0.953%, 2008 -3.848%, 2009 +3.400%, 2010 +0.480%, 2011 -0.809%, 2012 -0.438%, 2013 -1.559%, 2014 +1.126%, 2015 -0.394%, 2016 -0.399%, 2017 +0.344%, 2018 -0.975%, 2019 -1.395%, 2020 +0.621%, 2021 +0.447%, 2022 +0.217%, 2023 +0.502%, 2024 +0.225%

The survivorship figure is printed beside each result and is not subtracted.
Variants that pass: 3 of 12.


## Attempt 15

Rules fixed on 2026-11-07, before the run.

This attempt checks the three RSI(2) variants that passed attempt 14. The signal, the exit, and the delivery cost are the attempt 14 functions. Nothing in the pass mark is moved to fit a result. Parts 2 and 3 have no pass mark. They are reports. Parts 1 and 4 are judged.

1. Survivorship-free index test, 2005-01-01 through 2024-12-31. Every daily file in data/kite/day whose symbol starts with NIFTY is a series: NIFTY 50, NIFTY BANK, the sector indices, and the factor indices. A file that does not load is omitted. A file that loads and never trades counts as not positive. There is no stock universe. Each index is traded as its own price, with signal_lab.delivery on Rs 1,00,000, as a cash ETF. The three variants are rsi2 < 5, rsi2 < 10, and rsi2 < 10 down2, through follow.scan_signals. The market adjustment is the NIFTY 50 price return from the entry open to the exit open, minus nothing else. Excess for a trade is its percent return after costs minus that NIFTY return. A trade with no NIFTY bar on an end date stays in the average and stays out of the t. The t is the one-sample t of the mean excess in each calendar month. Pooled avg is the equal-weight mean of every trade of that variant across indices. Pooled t groups those same trades by month, averages inside the month, then takes the t across months. Positive means the index average after costs is strictly above 0. Each variant is judged on its own. A variant passes when its pooled average is above 0, its pooled excess t is above 2, and the average is positive on at least 2/3 of the loaded indices. Exactly 2/3 passes. Part 1 passes only when all three variants pass. Dates from 2025-01-01 on are not requested.

2. Portfolio, same window, the attempt 14 stock universe (top 200 by prior 60-session turnover on the signal day). Capital is Rs 10,00,000. At most 10 positions. Each new order is sized so the buy plus the buy-side delivery costs fit in Rs 1,00,000, using harness.shares_for. The book then pays harness.trade_cost on the buy and on the sell, which is the same delivery schedule as signal_lab.delivery (STT on both sides, stamp on the buy, the DP charge on the sell). When more new signals share an entry day than there are free slots, the lowest RSI(2) is taken first, then the highest 60-session turnover inside the signal segment, then the symbol name. A name already held is not a new slot. A name sold at the open is not bought again that day. The exit is the attempt 14 exit, so it is an open. Turnover that is missing inside the segment sorts after every name that has one. An exit that is not a NIFTY session is sold on the next NIFTY session at the same stock fill. Two books: idle cash earns 0, and idle cash is the NIFTY 50 price sleeve (funded with no cost, the harness Book). The invested share is the stock mark at the close divided by total equity, averaged over sessions. The NIFTY sleeve is not counted as invested. Trades per year are entries divided by the calendar span in 365.25-day years. NIFTY 50 buy-and-hold is the price path from the first open to each close, no costs and no dividends. Reported for each variant and each cash treatment: CAGR, max drawdown, worst year, yearly returns, average invested share, trades per year, and the NIFTY path on the same dates.

3. Stress, in sample, on rsi2 < 5 and rsi2 < 10, plus three neighbours of rsi2 < 10. (a) 0.1% extra slippage: the buy fill is the entry times 1.001 and the sell fill is the exit times 0.999, then delivery costs on those fills. (b) The entry is the close of the next session instead of its open. The exit walk is unchanged, so a close above SMA5 on the entry session sells at the following open, and the time stop is still the open five sessions after that entry session. The NIFTY return for a close entry starts at the NIFTY close of the entry day. (c) Each neighbour changes one piece of rsi2 < 10 and leaves the other pieces: RSI(3) below 10 with SMA200 and the SMA5 exit; RSI(2) below 10 with the exit on a close above SMA10; RSI(2) below 10 with the trend filter SMA100 instead of SMA200. The random baseline is 100 runs, seed 20261106 + 30000 + variant index times 1000 + the run index. Each run picks a same-month entry of the same symbol that was in the top 200 that day, and applies that variant's own entry price, slippage, and exit. The t is the attempt 14 t: market-adjusted excess versus those random entries, one mean per month. No pass mark.

4. One holdout, after parts 1 to 3. final=True, logged once. The rule is rsi2 < 5 exactly as in attempt 14: same signal, next-open entry, SMA5 exit or the open after five sessions, delivery costs, top 200 on the signal day. Entries from 2025-01-01 through the last date in the NIFTY 50 daily file. Indicator warmup before 2025 is used and is not a trade. A signal whose entry open falls on or after 2025-01-01 is a holdout trade even when the signal close was in 2024. The per-trade excess is the return after costs minus the NIFTY 50 price return over the same entry open to exit open. It is not versus a random entry. The t is the one-sample t of the monthly mean excess. The portfolio in part 2 is run on the same entries, starting from fresh cash on the first holdout session, both cash treatments. PASS, on the per-trade series only: average return after costs above 0, and that market-adjusted excess t above 2. The portfolio numbers are recorded beside it and are not part of the pass line. The rule is not changed after this run.

Results.

Part 1. Index files, one table per variant.

index | trades | avg after costs | excess vs NIFTY | t
NIFTY 200 | 188 | +0.295% | -0.120% | -1.68
NIFTY 50 | 209 | +0.152% | -0.239% | -1039.18
NIFTY 500 | 189 | +0.247% | -0.161% | -2.56
NIFTY ALPHA 50 | 164 | +0.319% | +0.124% | -0.11
NIFTY ALPHALOWVOL | 172 | +0.231% | -0.152% | -1.72
NIFTY AUTO | 150 | +0.228% | -0.039% | -0.65
NIFTY BANK | 205 | +0.741% | +0.168% | +1.96
NIFTY CONSR DURBL | 188 | -0.004% | +0.008% | -0.64
NIFTY ENERGY | 168 | +0.113% | -0.074% | -0.23
NIFTY FIN SERVICE | 196 | +0.883% | +0.279% | +0.83
NIFTY FMCG | 162 | -0.123% | -0.329% | -1.31
NIFTY HEALTHCARE | 138 | -0.045% | +0.012% | -0.14
NIFTY IT | 123 | +0.173% | -0.064% | +0.47
NIFTY LOW VOL 50 | 199 | -0.246% | -0.275% | -3.80
NIFTY MEDIA | 140 | -0.017% | -0.138% | -0.31
NIFTY METAL | 143 | +0.073% | -0.493% | -0.56
NIFTY MIDCAP 100 | 168 | +0.525% | +0.066% | +0.20
NIFTY MIDCAP 150 | 178 | +0.314% | -0.090% | -1.03
NIFTY OIL AND GAS | 155 | +0.586% | +0.358% | +0.28
NIFTY PHARMA | 154 | -0.591% | -0.529% | -1.59
NIFTY PSU BANK | 173 | +0.623% | +0.045% | +0.68
NIFTY PVT BANK | 168 | +0.818% | +0.496% | +1.40
NIFTY REALTY | 117 | +1.661% | +1.150% | +2.54
NIFTY SMLCAP 100 | 160 | +0.290% | -0.039% | -0.54
NIFTY SMLCAP 250 | 172 | +0.394% | +0.004% | -0.62
NIFTY100 ALPHA 30 | 172 | +0.314% | -0.105% | -1.51
NIFTY100 EQL WGT | 183 | +0.313% | +0.005% | -0.59
NIFTY100 LOWVOL30 | 192 | -0.167% | -0.318% | -3.63
NIFTY100 QUALTY30 | 140 | -0.274% | -0.400% | -4.27
NIFTY200 ALPHA 30 | 170 | +0.646% | +0.277% | +0.58
NIFTY200 QUALTY30 | 173 | -0.342% | -0.223% | -2.31
NIFTY200 VALUE 30 | 120 | +1.039% | -0.192% | -0.85
NIFTY200MOMENTM30 | 162 | +0.800% | +0.388% | +2.19
NIFTY50 EQL WGT | 39 | +0.661% | -0.361% | -2.46
NIFTY50 VALUE 20 | 157 | -0.061% | -0.301% | -3.23
NIFTY500 LMS EQL | 167 | +0.316% | -0.181% | -1.23
NIFTY500 LOWVOL50 | 194 | -0.108% | -0.474% | -4.07
NIFTY500 VALUE 50 | 133 | +0.861% | -0.110% | -0.19
NIFTY500MOMENTM50 | 152 | +0.513% | +0.124% | -0.22
POOLED rsi2 < 5 | 6,333 | +0.291% | -0.050% | -2.43 | positive 28 of 39 | FAIL

index | trades | avg after costs | excess vs NIFTY | t
NIFTY 200 | 373 | +0.093% | -0.150% | -2.75
NIFTY 50 | 388 | -0.011% | -0.239% | -1471.94
NIFTY 500 | 366 | +0.007% | -0.226% | -4.33
NIFTY ALPHA 50 | 312 | +0.232% | +0.132% | +0.27
NIFTY ALPHALOWVOL | 327 | +0.087% | -0.150% | -2.27
NIFTY AUTO | 324 | +0.207% | -0.095% | -0.60
NIFTY BANK | 378 | +0.546% | +0.082% | +1.11
NIFTY CONSR DURBL | 329 | -0.236% | -0.236% | -1.32
NIFTY ENERGY | 306 | +0.068% | -0.130% | -1.57
NIFTY FIN SERVICE | 377 | +0.508% | +0.040% | -0.01
NIFTY FMCG | 339 | -0.086% | -0.411% | -2.03
NIFTY HEALTHCARE | 273 | -0.042% | -0.049% | -0.44
NIFTY IT | 282 | +0.262% | -0.113% | -0.17
NIFTY LOW VOL 50 | 355 | -0.198% | -0.258% | -4.24
NIFTY MEDIA | 261 | -0.126% | -0.166% | -0.31
NIFTY METAL | 276 | +0.387% | +0.007% | +1.36
NIFTY MIDCAP 100 | 328 | +0.024% | -0.235% | -1.89
NIFTY MIDCAP 150 | 320 | +0.077% | -0.126% | -1.25
NIFTY OIL AND GAS | 296 | +0.288% | +0.041% | -0.68
NIFTY PHARMA | 303 | -0.489% | -0.450% | -1.74
NIFTY PSU BANK | 298 | +0.682% | +0.074% | +0.61
NIFTY PVT BANK | 330 | +0.648% | +0.391% | +1.66
NIFTY REALTY | 218 | +0.825% | +0.398% | +1.36
NIFTY SMLCAP 100 | 311 | -0.129% | -0.353% | -1.73
NIFTY SMLCAP 250 | 293 | -0.048% | -0.272% | -1.71
NIFTY100 ALPHA 30 | 315 | +0.367% | -0.052% | -1.52
NIFTY100 EQL WGT | 342 | +0.257% | -0.005% | -0.84
NIFTY100 LOWVOL30 | 334 | -0.129% | -0.261% | -3.42
NIFTY100 QUALTY30 | 260 | -0.144% | -0.327% | -4.34
NIFTY200 ALPHA 30 | 304 | +0.661% | +0.292% | +0.73
NIFTY200 QUALTY30 | 336 | -0.102% | -0.219% | -3.46
NIFTY200 VALUE 30 | 234 | +0.714% | +0.040% | -0.82
NIFTY200MOMENTM30 | 305 | +0.621% | +0.269% | +1.23
NIFTY50 EQL WGT | 77 | +0.461% | -0.322% | -3.17
NIFTY50 VALUE 20 | 295 | -0.065% | -0.254% | -3.65
NIFTY500 LMS EQL | 304 | +0.210% | -0.074% | -0.70
NIFTY500 LOWVOL50 | 339 | -0.160% | -0.314% | -3.52
NIFTY500 VALUE 50 | 242 | +0.506% | -0.046% | -0.33
NIFTY500MOMENTM50 | 299 | +0.156% | +0.054% | +0.38
POOLED rsi2 < 10 | 11,949 | +0.162% | -0.097% | -3.05 | positive 25 of 39 | FAIL

index | trades | avg after costs | excess vs NIFTY | t
NIFTY 200 | 333 | +0.056% | -0.187% | -3.16
NIFTY 50 | 344 | +0.040% | -0.239% | -1505.54
NIFTY 500 | 326 | +0.005% | -0.248% | -4.70
NIFTY ALPHA 50 | 272 | +0.302% | +0.163% | +0.52
NIFTY ALPHALOWVOL | 295 | +0.091% | -0.180% | -2.15
NIFTY AUTO | 285 | +0.105% | -0.090% | -0.18
NIFTY BANK | 340 | +0.482% | +0.068% | +1.14
NIFTY CONSR DURBL | 285 | -0.202% | -0.231% | -1.61
NIFTY ENERGY | 276 | +0.021% | -0.156% | -1.66
NIFTY FIN SERVICE | 334 | +0.461% | +0.041% | +0.12
NIFTY FMCG | 302 | -0.121% | -0.420% | -1.91
NIFTY HEALTHCARE | 249 | -0.122% | -0.086% | -0.07
NIFTY IT | 252 | +0.194% | -0.175% | -1.01
NIFTY LOW VOL 50 | 323 | -0.155% | -0.247% | -3.88
NIFTY MEDIA | 234 | -0.107% | -0.275% | -0.91
NIFTY METAL | 242 | +0.346% | -0.128% | +0.81
NIFTY MIDCAP 100 | 288 | +0.091% | -0.167% | -1.70
NIFTY MIDCAP 150 | 286 | +0.085% | -0.159% | -1.31
NIFTY OIL AND GAS | 257 | +0.199% | +0.016% | -0.88
NIFTY PHARMA | 276 | -0.542% | -0.452% | -1.66
NIFTY PSU BANK | 264 | +0.700% | +0.021% | +0.46
NIFTY PVT BANK | 294 | +0.637% | +0.440% | +1.30
NIFTY REALTY | 199 | +0.701% | +0.317% | +1.09
NIFTY SMLCAP 100 | 273 | -0.154% | -0.336% | -1.71
NIFTY SMLCAP 250 | 255 | -0.141% | -0.318% | -1.91
NIFTY100 ALPHA 30 | 280 | +0.337% | -0.039% | -1.54
NIFTY100 EQL WGT | 313 | +0.246% | -0.016% | -0.89
NIFTY100 LOWVOL30 | 307 | -0.159% | -0.249% | -2.95
NIFTY100 QUALTY30 | 236 | -0.188% | -0.383% | -4.44
NIFTY200 ALPHA 30 | 266 | +0.636% | +0.309% | +1.08
NIFTY200 QUALTY30 | 304 | -0.163% | -0.230% | -3.37
NIFTY200 VALUE 30 | 210 | +0.793% | +0.081% | -0.34
NIFTY200MOMENTM30 | 272 | +0.641% | +0.323% | +1.82
NIFTY50 EQL WGT | 70 | +0.430% | -0.293% | -2.90
NIFTY50 VALUE 20 | 255 | -0.137% | -0.274% | -3.87
NIFTY500 LMS EQL | 264 | +0.219% | -0.078% | -0.73
NIFTY500 LOWVOL50 | 297 | -0.149% | -0.431% | -3.82
NIFTY500 VALUE 50 | 202 | +0.622% | -0.070% | -0.47
NIFTY500MOMENTM50 | 272 | +0.187% | +0.096% | +0.28
POOLED rsi2 < 10 down2 | 10,632 | +0.145% | -0.111% | -3.05 | positive 26 of 39 | FAIL

Part 1 FAIL: rsi2 < 5: pooled excess t -2.43 is not above 2; rsi2 < 10: pooled excess t -3.05 is not above 2; positive on 25 of 39 indices, need at least 2/3; rsi2 < 10 down2: pooled excess t -3.05 is not above 2

Part 2. Portfolio. No pass mark.
variant | cash | CAGR | max DD | worst year | invested | trades/year
rsi2 < 5 | cash 0 | +6.924% | -28.698% | -14.226% | +25.518% | +423.02
rsi2 < 5 | cash in NIFTY | +14.782% | -60.269% | -52.505% | +15.943% | +423.02
rsi2 < 10 | cash 0 | +6.333% | -37.244% | -32.561% | +40.719% | +576.34
rsi2 < 10 | cash in NIFTY | +12.134% | -63.273% | -55.536% | +30.353% | +576.34
rsi2 < 10 down2 | cash 0 | +6.779% | -30.327% | -25.495% | +34.826% | +556.88
rsi2 < 10 down2 | cash in NIFTY | +13.300% | -62.366% | -54.449% | +24.368% | +556.88
NIFTY 50 | price only | +12.929% | -59.856% | -51.794% | +100.000% | n/a
rsi2 < 5, cash 0 years: 2005 +17.263%, 2006 -2.521%, 2007 +38.640%, 2008 -14.226%, 2009 +40.541%, 2010 +14.086%, 2011 -8.167%, 2012 +6.115%, 2013 +4.744%, 2014 +16.061%, 2015 +8.882%, 2016 +4.209%, 2017 +9.745%, 2018 -3.016%, 2019 +4.319%, 2020 -1.323%, 2021 +4.285%, 2022 -1.047%, 2023 +13.735%, 2024 +1.219%
rsi2 < 5, cash in NIFTY years: 2005 +38.584%, 2006 +20.793%, 2007 +71.163%, 2008 -52.505%, 2009 +102.724%, 2010 +24.207%, 2011 -25.087%, 2012 +28.225%, 2013 +7.744%, 2014 +37.131%, 2015 +0.897%, 2016 +3.658%, 2017 +31.446%, 2018 +1.745%, 2019 +13.096%, 2020 +17.406%, 2021 +24.609%, 2022 +4.159%, 2023 +23.372%, 2024 +8.834%
rsi2 < 10, cash 0 years: 2005 +20.797%, 2006 -12.769%, 2007 +33.686%, 2008 -32.561%, 2009 +54.984%, 2010 +17.220%, 2011 -14.065%, 2012 +10.367%, 2013 +3.238%, 2014 +24.970%, 2015 +8.677%, 2016 +6.370%, 2017 +16.545%, 2018 -8.352%, 2019 +4.966%, 2020 -0.387%, 2021 +6.522%, 2022 -4.134%, 2023 +19.398%, 2024 +2.677%
rsi2 < 10, cash in NIFTY years: 2005 +34.844%, 2006 +0.164%, 2007 +57.300%, 2008 -55.536%, 2009 +80.651%, 2010 +24.832%, 2011 -26.367%, 2012 +28.156%, 2013 +3.988%, 2014 +42.404%, 2015 +3.903%, 2016 +4.768%, 2017 +34.879%, 2018 -1.390%, 2019 +12.437%, 2020 +17.015%, 2021 +23.395%, 2022 +2.103%, 2023 +26.554%, 2024 +9.175%
rsi2 < 10 down2, cash 0 years: 2005 +25.851%, 2006 -7.844%, 2007 +33.558%, 2008 -25.495%, 2009 +46.773%, 2010 +19.661%, 2011 -10.373%, 2012 +5.775%, 2013 +4.174%, 2014 +18.846%, 2015 +9.447%, 2016 +4.924%, 2017 +14.434%, 2018 -6.455%, 2019 +5.633%, 2020 -0.795%, 2021 +7.535%, 2022 -2.593%, 2023 +14.470%, 2024 +0.992%
rsi2 < 10 down2, cash in NIFTY years: 2005 +45.550%, 2006 +7.776%, 2007 +60.309%, 2008 -54.449%, 2009 +85.487%, 2010 +26.993%, 2011 -25.425%, 2012 +25.262%, 2013 +6.001%, 2014 +38.001%, 2015 +3.783%, 2016 +3.901%, 2017 +33.667%, 2018 +0.148%, 2019 +13.121%, 2020 +16.397%, 2021 +24.437%, 2022 +2.810%, 2023 +24.411%, 2024 +8.821%
NIFTY 50 years: 2005 +36.370%, 2006 +39.834%, 2007 +54.765%, 2008 -51.794%, 2009 +75.762%, 2010 +17.947%, 2011 -24.618%, 2012 +27.697%, 2013 +6.755%, 2014 +31.388%, 2015 -4.061%, 2016 +3.013%, 2017 +28.646%, 2018 +3.151%, 2019 +12.022%, 2020 +14.902%, 2021 +24.119%, 2022 +4.329%, 2023 +20.028%, 2024 +8.805%
Part 2 report. No pass mark was set.

Part 3. Stress. No pass mark.
variant | trades | avg after costs | t vs random
rsi2 < 5 slip | 30,513 | +0.367% | +20.87
rsi2 < 10 slip | 60,373 | +0.202% | +13.63
rsi2 < 5 close | 30,513 | +0.591% | +21.51
rsi2 < 10 close | 60,373 | +0.503% | +17.24
rsi3 < 10 | 20,007 | +0.639% | +21.32
exit sma10 | 60,373 | +0.488% | +14.64
sma100 filter | 48,940 | +0.480% | +13.63
Part 3 report. No pass mark was set.

Part 4. Holdout rsi2 < 5, 2025-01-01 to 2026-11-04.
per trade | 2,422 | +0.327% | +0.236% | +1.42
variant | cash | CAGR | max DD | worst year | invested | trades/year
rsi2 < 5 | cash 0 | +1.956% | -17.249% | +1.717% | +57.253% | +437.00
rsi2 < 5 | cash in NIFTY | -0.889% | -19.189% | -3.496% | +58.819% | +437.00
NIFTY 50 | price only | +0.740% | -15.560% | -8.301% | +100.000% | n/a
rsi2 < 5, cash 0 years: 2025 +1.717%, 2026 +1.878%
rsi2 < 5, cash in NIFTY years: 2025 +1.935%, 2026 -3.496%
NIFTY 50 years: 2025 +10.542%, 2026 -8.301%
Part 4 FAIL: market-adjusted excess t +1.42 is not above 2
The holdout rule was not changed after the run.


## Attempt 16

Rules fixed on 2026-11-07, before the run.

Four families on 2005-01-01 through 2024-12-31. No 5-minute bars are used. Dates from 2025-01-01 on are not requested until a variant passes, and then only in the one holdout load. Dividends are excluded. Nothing is placed. Spot prices are the futures proxy for every futures rule, and the report says so.

Futures costs, check your broker. Brokerage Rs 20 an order. STT 0.05% of sell value. Exchange 0.00173% of both sides. SEBI 0.0001% of both sides. Stamp 0.002% of buy value. GST 18% of brokerage plus exchange plus SEBI. STT and stamp are outside the GST base. One extra round trip per leg is charged for each month-end strictly after the entry date and on or before the exit date. A pair that opens and closes in the same month pays no rollover.

1. Pairs. Market-neutral, both legs treated as stock futures. Universe on the formation date: the top 200 by prior 60-session turnover. Industry is the Industry column of india/universe/nifty500.csv. A blank industry is not a match. Rs 1,00,000 notional per leg, so the per-trade average is on Rs 2,00,000 gross. Every 6 months, on the first NIFTY session of January and of July, form on the sessions from the same month a year earlier up to the session before the formation date. A name must have a close on every one of those sessions, inside one segment, and there must be at least 120 of them. Both prices are divided by their first formation close. The score is the sum of squared differences. The formation mean and the population standard deviation of that normalised gap are saved. The next window runs until the day before the next formation date. Marks use sessions where both names have a close. (a) The 20 same-industry pairs with the smallest score. Open when the live gap is strictly more than 2 standard deviations from the formation mean. Long the cheaper normalised price, short the dearer, at that close. Close when the raw normalised gap crosses zero, or at the last common close of the window. A standard deviation of 0 opens nothing. Exactly 2 standard deviations does not open. (b) The same rule with any industry allowed. (c) The same 20 same-industry pairs as (a). The z-score is the population z-score of the log price ratio over the 60 closes ending that day. Enter at the close when the absolute z is strictly above 2, short the richer name. Exit at the close when the absolute z is strictly above 4 (checked first), or when z crosses 0, or at the close of day 20 counting the entry session as day 1. One position per pair. The portfolio funds 20 slots from Rs 10,00,000, so each leg of each slot is Rs 25,000, including a slot that is flat. Idle cash earns 0. The market beta is the OLS slope, with an intercept, of the book's daily percent change on NIFTY's close-to-close percent change, using only days when a pair is open. The monthly t is the one-sample t of the book's month-end percent returns. Decades and market types are the mean per-trade return by the entry date. Large caps, both legs in the top 100 that day, are reported and are not a pass clause.

2. Holy Grail, stocks, daily, delivery costs, Rs 1,00,000 a trade, top 200 on the pullback day. ADX(14) and +DI and -DI are Wilder. EMA20 is ta.ema_series. The pullback day has ADX strictly above the threshold, +DI strictly above -DI, and a low at or below EMA20 with a high at or above it. The next session buys on a stop one tick, from nse_market.tick_for, above that day's high. An open at or above the stop fills at the open. Otherwise a high at or above the stop fills at the stop. No fill, no trade. The protective stop is the pullback day's low. The target is the fill plus 2 times (fill minus that low). A gap through the stop fills at the open, a low through the stop fills at the stop, and the stop is taken before the target. If neither is hit, sell at the close of the 10th session, counting the entry session as day 1. A trade that would need a later session is skipped. Variants: ADX above 30; ADX above 25; ADX above 30 and the pullback close strictly above SMA200. Exactly 30 fails the first and the third. Random entries, 100 runs, seed 20261106 + 50000 + variant index times 1000 + the run index, are same-month top-200 days of the same symbol. The signal is not required. The same stop, target and 10-day exit are applied from that day. The t is the attempt 14 market-adjusted t versus those entries.

3. Calendar on NIFTY 50, futures costs, one lot of 75. The return is the rupee P&L divided by 75 times the entry price. (a) Turn of the month: long from the close of the session before the last session of the month to the close of the third session of the next month. (b) Expiry week: long from the Monday open of the expiry week to the expiry close. Expiry is the last Thursday, or the previous NIFTY session when that Thursday is not a session. The Monday, when it is not a session, moves to the next session that is still on or before the expiry. Expiry-day changes after 2024 are outside this window, and a holdout of this rule keeps the last-Thursday definition. (c) The week after expiry: long from that next Monday's open to that Friday's close, moving either end onto a NIFTY session inside the week. The baseline is 100 other windows in the same calendar year with the same session count, not starting on the real entry date. Seed 20261106 + 70000 + variant index times 1000, then the event index. The average that must be above 0 is the trade's own return after costs. The monthly t is the one-sample t of (that return minus the mean of the same-year random windows). A year with no other window leaves the trade in the average and out of the t. Decades and market types use the trade's own return and the entry date's regime.

4. Mixes. (m1) rsi2 < 5, the attempt 14 rule, and the signal-day name is in the top 30% of that day's top 200 by 12-1 momentum. 12-1 is the close 21 sessions before the signal divided by the close 252 sessions before it, minus 1, inside one segment. The count is n times 30 divided by 100, truncating. Ties break on the symbol name. (m2) rsi2 < 5 only when the entry date's market type is up or sideways. Hypothesis from attempt 14's weak down bucket: the down average was the weak one, so this mix does not trade a down entry. An empty down bucket is reported and is not a failure. (m3) One Rs 10,00,000 book in two halves of Rs 5,00,000. The first half is rsi2 < 5 with 5 slots of Rs 1,00,000, lowest RSI then highest turnover, and a name sold at the open is not bought again that day. The second half is rev K20: every Monday, the 20 worst 5-session returns in the top 200, sold and bought again the next Monday so both costs apply. Each half parks idle cash in the NIFTY price with no funding cost. The same name may sit in both halves. The correlation is the Pearson correlation of the two halves' month-end percent returns.

Pass marks, fixed before this run. Holy Grail uses the attempt 14 judge: average after costs above 0, t versus random above 3, both decades, up, down, sideways, large caps, and at least 2 of the 3 variants with t above 2. Pairs and calendar: average after costs above 0, monthly t above 3, above 0 in both decades and in each market type, and at least 2 of the 3 variants with t above 2. Large caps and the pairs beta are not pass clauses. m1 and m2 use the attempt 14 trade clauses and are not a three-variant family, so the 2-of-3 count is not applied. m2 does not require a down average. m3 uses the attempt 11 path against NIFTY 50 buy-and-hold: excess t above 3, both decades, each market type, large-cap excess above 0, beats 95 of 100 random books, and either the drawdown path or the calmar path. The m3 random book keeps the same dates and replaces the names. A boundary stated as above is strict. At least 2 of 3 passes when the count is exactly 2. An empty required bucket fails.

5. Every variant that PASSES gets one automatic holdout, after the in-sample run. One load_context with final=True, logged once, from 2025-01-01 through the last NIFTY 50 daily date. Warmup before 2025 is used and is not a trade. An entry on or after 2025-01-01 counts. The signal rules are unchanged. Holdout PASS is average after costs above 0 and t above 2, and nothing else. For Holy Grail, m1 and m2 the holdout t is the one-sample t of the monthly mean of (return after costs minus the NIFTY price return over the trade), not versus a random entry. For pairs the holdout t is the same monthly book t. For calendar it is the same excess t versus same-year random windows. For m3 the average is the mean monthly book return and the t is the t of monthly excess versus NIFTY. The rule is not changed after the holdout. STRATEGIES.md is updated from these results at the end.

Results.

Spot prices are the futures proxy.

Pairs. Per-trade average on Rs 2,00,000. Beta is not a pass clause.
variant | trades | avg | beta | t | 2005-2014 | 2015-2024 | up | down | sideways | large | CAGR | max DD | result
pairs same | 486 | +0.550% | +0.01 | +0.21 | +1.037% | +0.254% | -0.112% | +2.577% | +0.819% | +0.995% | +0.094% | -10.567% | FAIL
pairs any | 769 | +0.029% | +0.01 | -0.62 | -0.054% | +0.091% | -0.377% | +0.623% | +1.336% | -0.151% | -0.938% | -20.849% | FAIL
pairs z | 1,070 | +0.493% | +0.01 | +1.28 | +1.183% | +0.062% | -0.148% | +1.117% | +1.761% | +0.578% | +0.664% | -6.692% | FAIL
pairs same FAIL: monthly t +0.21 is not above 3; up -0.112% is not above 0; family variants with t above 2: 0 of 3, need 2
pairs any FAIL: monthly t -0.62 is not above 3; 2005-2014 -0.054% is not above 0; up -0.377% is not above 0; family variants with t above 2: 0 of 3, need 2
pairs z FAIL: monthly t +1.28 is not above 3; up -0.148% is not above 0; family variants with t above 2: 0 of 3, need 2

Holy Grail.
variant | trades | avg | t | 2005-2014 | 2015-2024 | up | down | sideways | large | result
grail adx30 | 12,888 | -0.430% | -0.11 | -0.611% | -0.193% | -0.506% | -0.426% | +0.016% | -0.488% | FAIL
grail adx25 | 21,758 | -0.515% | -0.19 | -0.691% | -0.297% | -0.568% | -0.597% | -0.156% | -0.516% | FAIL
grail adx30 sma200 | 11,042 | -0.401% | +2.06 | -0.623% | -0.121% | -0.440% | -0.417% | -0.116% | -0.450% | FAIL
grail adx30 FAIL: avg return after costs -0.430% is not above 0; t vs random -0.11 is not above 3; 2005-2014 -0.611% is not above 0; 2015-2024 -0.193% is not above 0; up -0.506% is not above 0; down -0.426% is not above 0; large caps -0.488% is not above 0; family variants with t above 2: 1 of 3, need 2
grail adx25 FAIL: avg return after costs -0.515% is not above 0; t vs random -0.19 is not above 3; 2005-2014 -0.691% is not above 0; 2015-2024 -0.297% is not above 0; up -0.568% is not above 0; down -0.597% is not above 0; sideways -0.156% is not above 0; large caps -0.516% is not above 0; family variants with t above 2: 1 of 3, need 2
grail adx30 sma200 FAIL: avg return after costs -0.401% is not above 0; t vs random +2.06 is not above 3; 2005-2014 -0.623% is not above 0; 2015-2024 -0.121% is not above 0; up -0.440% is not above 0; down -0.417% is not above 0; sideways -0.116% is not above 0; large caps -0.450% is not above 0; family variants with t above 2: 1 of 3, need 2

Calendar. The t is versus same-year random windows.
variant | trades | avg | t | 2005-2014 | 2015-2024 | up | down | sideways | result
tom | 239 | +0.556% | +2.41 | +0.810% | +0.301% | +0.499% | +1.188% | +0.260% | FAIL
expiry week | 240 | +0.130% | +0.65 | +0.323% | -0.064% | -0.007% | +0.997% | -0.042% | FAIL
after expiry | 240 | +0.231% | +0.85 | +0.328% | +0.135% | +0.240% | +0.541% | -0.097% | FAIL
tom FAIL: monthly t +2.41 is not above 3; family variants with t above 2: 1 of 3, need 2
expiry week FAIL: monthly t +0.65 is not above 3; 2015-2024 -0.064% is not above 0; up -0.007% is not above 0; sideways -0.042% is not above 0; family variants with t above 2: 1 of 3, need 2
after expiry FAIL: monthly t +0.85 is not above 3; sideways -0.097% is not above 0; family variants with t above 2: 1 of 3, need 2

Mixes.
variant | trades | avg | t | 2005-2014 | 2015-2024 | up | down | sideways | large | result
m1 momentum | 13,604 | +0.798% | +19.53 | +0.806% | +0.790% | +0.849% | -0.009% | +0.969% | +0.930% | FAIL
m2 regime | 28,851 | +0.600% | +21.17 | +0.584% | +0.615% | +0.558% | n/a | +0.875% | +0.656% | PASS
m3 book | CAGR +15.184% | max DD -65.143% | excess +0.201% | t +1.80 | beats 100 | corr +0.94 | FAIL
m1 momentum FAIL: down -0.009% is not above 0
m2 regime PASS.
m3 book FAIL: excess t +1.80 is not above 3; neither path clears: CAGR +15.184% vs NIFTY +12.929%, max DD -65.143% vs -59.856%, ratio 0.233 vs 0.216

Holdout.
m2 regime | avg +0.079% | t +0.78 | FAIL
m2 regime FAIL: t +0.78 is not above 2

Bucket list.
# Strategy catalogue

Attempts 1 to 10 tested two families. Attempts 1 to 8 are the opening-range breakout family. Attempts 9 and 10 are the single technical-signal family (one entry rule, one exit rule, scored one trade at a time and then as a 10-slot book). Attempt 11 is the first batch on the shared harness in `harness.py`. A later batch keeps the same pass mark.

Dividends are excluded. Nothing here places an order.

Tiers are filled from the attempt results. Bucket means an in-sample PASS and a holdout PASS. Watch means an in-sample PASS whose holdout average after costs is positive and whose holdout t is not above 2. Investing is a real edge kept for the later investing phase. Near-miss is close and closed is the rest. The source table below is the bibliography.

## Bucket

In-sample PASS and holdout PASS.

None yet.

## Watch

In-sample PASS, holdout average after costs above 0, t not above 2.

| Name | Attempt | Note |
|---|---|---|
| rsi2 < 5 | 14, 15 | In-sample PASS. Holdout average after costs +0.327% and excess t +1.42. |
| m2 regime | 16 | PASS Holdout FAIL, avg +0.079%, t +0.78. |

## Investing

A real edge, for the later investing phase.

| Name | Attempt | Note |
|---|---|---|
| mom 12-1 K20 above200 | 11 | PASS in-sample, but inflated by survivorship bias; real NIFTY200 Momentum 30 TRI: 18.8% CAGR vs NIFTY 50 TRI 13.6% since Apr 2005 (HDFC MF, Jul 2026) |

## Near-miss

Close to a pass, and not in the buckets above.

| Name | Attempt | Note |
|---|---|---|
| rev K20 | 14 | Cleared every attempt 14 clause except the family gate, 1 of 3 with t above 2. |
| Faber timing | 11 | faber 10m, faber 8m and faber 12m. The monthly t was negative. |

## Closed

Tested and not in a bucket above.

| Name | Attempt | Note |
|---|---|---|
| Opening-range breakout | 1-8 | The intraday opening-range family. |
| 20d-high / sma20-close and engulf-low / hold-20 | 9 | In-sample PASS. No 2025 holdout was run. |
| Attempt 10 single signals | 10 | The remaining entry and exit pairs. |
| Turtle, 52-week high, mom 12-1 K20, mom 12-1 K30 | 11 | Failed the attempt 11 path. The above-200 momentum book is in Investing. |
| Attempt 12 intraday batch | 12 | 0 of 12 passed. |
| Big-gap continuation | 13 | 0 of 3 passed. |
| rsi2 < 10 and rsi2 < 10 down2 | 14, 15 | In-sample PASS. The holdout was rsi2 < 5 only, and the index test failed. |
| IBS, turtle soup, rev K10, rev K10 above200 | 14 | Failed the attempt 14 mark. rev K20 is the near-miss. |
| Index RSI(2) | 15 | The survivorship-free index test failed on the pooled excess t. |
| pairs same | 16 | FAIL |
| pairs any | 16 | FAIL |
| pairs z | 16 | FAIL |
| grail adx30 | 16 | FAIL |
| grail adx25 | 16 | FAIL |
| grail adx30 sma200 | 16 | FAIL |
| tom | 16 | FAIL |
| expiry week | 16 | FAIL |
| after expiry | 16 | FAIL |
| m1 momentum | 16 | FAIL |
| m3 book | 16 | FAIL |

## Sources

| Strategy | Source | Horizon | Status | Attempt |
|---|---|---|---|---|
| Turtle breakout | Richard Dennis and William Eckhardt, the 1983 rules, published by Curtis Faith, Way of the Turtle (2007) | daily | batch 1 | 11 |
| Cross-sectional momentum | Jegadeesh and Titman (1993), Journal of Finance, "Returns to Buying Winners and Selling Losers" | monthly | batch 1 | 11 |
| 52-week-high momentum | George and Hwang (2004), Journal of Finance | monthly | batch 1 | 11 |
| Minervini trend template + VCP | Mark Minervini, Trade Like a Stock Market Wizard (2013), trend template and volatility contraction | daily | not started | |
| Weinstein stage analysis | Stan Weinstein, Secrets for Profiting in Bull and Bear Markets (1988) | weekly and daily | not started | |
| Darvas box | Nicolas Darvas, How I Made $2,000,000 in the Stock Market (1960) | daily | not started | |
| Time-series momentum / Faber 10-month timing | Moskowitz, Ooi and Pedersen (2012) for time-series momentum; Meb Faber, "A Quantitative Approach to Tactical Asset Allocation" (2007), for the 10-month average | monthly | batch 1 (Faber timing); full TSMOM not started | 11 |
| Connors RSI(2) | Larry Connors, Short Term Trading Strategies That Work (2008) | daily | not started | |
| IBS | (close - low) / (high - low). Larry Connors, and the 2013 Pagonidis note "The IBS Effect" | daily | not started | |
| Short-term reversal | Jegadeesh (1990), Journal of Finance | daily to monthly | not started | |
| Pairs trading | Gatev, Goetzmann and Rouwenhorst (2006), Review of Financial Studies | daily | not started | |
| Turtle Soup | Raschke and Connors, Street Smarts (1996) | daily | not started | |
| Crabel NR7/NR4 | Toby Crabel, Day Trading with Short Term Price Patterns and Opening Range Breakout (1990) | daily | not started | |
| Raschke Holy Grail | Linda Raschke, Street Smarts (1996), the ADX pullback | daily | not started | |
| Intraday momentum (Gao et al. 2018) | Gao, Han, Li and Zhou (2018), Journal of Financial Economics, "Market intraday momentum" | intraday | not started | |
| Gap and go vs gap fade | Practitioner opening-gap pattern. No single paper | intraday | not started | |
| VWAP reversion | Berkowitz, Logue and Noser (1988) introduced VWAP. Reversion to it is a practitioner intraday strategy | intraday | not started | |
| Turn of the month | Ariel (1987), Journal of Financial Economics | daily, around month-end | not started | |
| F&O expiry week | NSE monthly derivatives expiry, the last Thursday. An India calendar effect | daily, expiry week | not started | |
| Volatility-regime switching | Hamilton (1989); Moreira and Muir (2017), "Volatility-Managed Portfolios" | daily to monthly | not started | |


## Forward test

Started 2026-11-04, before any forward data. This section records the live paper rule. It is not an in-sample result, and no forward numbers are filled in here.

The entry rule matches attempt 7. A trend day is a day when NIFTY's first 5-minute close beyond its own 30-minute range is a bar that closes at or before 10:00. Each stock in the folder enters on its first close beyond its own 30-minute range, in NIFTY's direction, at or after that signal bar and by 14:30. The stop is the range midpoint, rounded to the tick (down for a long, up for a short). The target is 2R. Flat at 15:10.

Sizing is not attempt 7's Rs 2,000 a trade. The paper book risks Rs 6,000 a day, split into 35 equal slices, with a position cap of Rs 5,00,000 and whole shares. A later signal is not opened once the day's committed risk reaches Rs 6,000.

The forward test passes only when all of these hold: at least 30 qualifying days, average R after costs at least +0.10, winning days above 55%, still profitable in rupees without the best 2 days, and net rupees above 0 on at least 60% of the stocks that traded. Until 30 qualifying days the report says IN PROGRESS. Confirmation uses only sessions after 2026-10-30.
