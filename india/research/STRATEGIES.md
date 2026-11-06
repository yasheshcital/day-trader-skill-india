# Strategy catalogue

Attempts 1 to 10 tested two families. Attempts 1 to 8 are the opening-range breakout family. Attempts 9 and 10 are the single technical-signal family (one entry rule, one exit rule, scored one trade at a time and then as a 10-slot book). Attempt 11 is the first batch on the shared harness in `harness.py`. A later batch keeps the same pass mark.

Dividends are excluded. Nothing here places an order.

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
