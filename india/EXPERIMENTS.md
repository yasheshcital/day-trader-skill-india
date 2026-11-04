# Experiments

Every row uses the same pass mark, fixed before attempt 2 and not moved to fit a result.

A rule passes only when all of these hold: at least 100 trades, average R after costs at least +0.10, the first half and the second half both above 0 after costs, and after-cost average R above 0 on at least 60% of the stocks that traded. Anything else is FAIL, with the marks that missed.

| # | Date | Hypothesis | Rule | Data | Trades | R before costs | R after costs | Result |
|---|------|------------|------|------|--------|----------------|---------------|--------|
| 1 | 2026-11-04 | A long opening-range breakout, stop under the range low and a 2R target, is profitable after NSE costs on six large stocks. This was the best of the 12 long rules. | 30m or-low 2R, long | tests/fixtures/india/stocks (HDFCBANK, ICICIBANK, INFY, RELIANCE, SBIN, TCS; 60 sessions each) | 149 | -0.016 | -0.120 | FAIL |

All results use the same pass mark, fixed before attempt 2.
