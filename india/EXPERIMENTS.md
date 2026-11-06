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


## Forward test

Started 2026-11-04, before any forward data. This section records the live paper rule. It is not an in-sample result, and no forward numbers are filled in here.

The entry rule matches attempt 7. A trend day is a day when NIFTY's first 5-minute close beyond its own 30-minute range is a bar that closes at or before 10:00. Each stock in the folder enters on its first close beyond its own 30-minute range, in NIFTY's direction, at or after that signal bar and by 14:30. The stop is the range midpoint, rounded to the tick (down for a long, up for a short). The target is 2R. Flat at 15:10.

Sizing is not attempt 7's Rs 2,000 a trade. The paper book risks Rs 6,000 a day, split into 35 equal slices, with a position cap of Rs 5,00,000 and whole shares. A later signal is not opened once the day's committed risk reaches Rs 6,000.

The forward test passes only when all of these hold: at least 30 qualifying days, average R after costs at least +0.10, winning days above 55%, still profitable in rupees without the best 2 days, and net rupees above 0 on at least 60% of the stocks that traded. Until 30 qualifying days the report says IN PROGRESS. Confirmation uses only sessions after 2026-10-30.
