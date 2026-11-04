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

Attempt 6 was specified before the run. The midpoint stop used about Rs 2,93,681 a position and never had more than 3 open. The far-side stop used about Rs 1,74,263 a position, also with 3 open at the peak. Neither clears the pass mark.

Attempt 7 is in sample only: 612 trades on 18 days, 12 of them winning, best 5 days 97.1% of the profit. The stock files end on 2026-10-30, so there is no later sample here to confirm it. The new day clauses are what fail it.

All results use the same pass mark, fixed before attempt 2.
