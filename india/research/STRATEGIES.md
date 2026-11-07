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
