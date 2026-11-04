#!/usr/bin/env python3
"""60 synthetic NSE sessions of 5-minute NIFTY-like bars, then the real
2026-10-30 candles.

Prices wander around 23,000. Each 5-minute move is a few points, on the
0.05 tick. The random seed is 19, so the file is the same every time.
Weekends and NSE holidays are skipped. Datetimes are the bar END, naive IST,
which is the AlgoTest shape.

    python3 tests/fixtures/india/make_nifty_synthetic.py

Writes tests/fixtures/india/NIFTY-60d5m.algotest.json and, through
india/algotest_to_yahoo.py, tests/fixtures/trader-timemachine/NIFTY-60d5m.json.
"""

import datetime
import json
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from india import nse_market
from india.algotest_to_yahoo import to_yahoo

SEED = 19
SESSIONS = 60
PLAN_DAY = datetime.date(2026, 10, 30)
TICK = 0.05
REAL = os.path.join(HERE, "NIFTY-2026-10-30-5m.algotest.json")
ALGOTEST = os.path.join(HERE, "NIFTY-60d5m.algotest.json")
YAHOO = os.path.join(ROOT, "tests", "fixtures", "trader-timemachine", "NIFTY-60d5m.json")


def on_tick(x):
    return round(round(float(x) / TICK) * TICK, 2)


def trading_days_before(end, n):
    days = []
    d = end - datetime.timedelta(days=1)
    while len(days) < n:
        ok, _ = nse_market.trading_day(d)
        if ok:
            days.append(d)
        d -= datetime.timedelta(days=1)
    days.reverse()
    return days


def session(rng, day, price):
    """75 candles, 09:20 through 15:30 IST, each datetime the bar end."""
    gap = rng.uniform(-40.0, 40.0)
    price = on_tick(price + gap)
    candles = []
    start = datetime.datetime.combine(day, datetime.time(9, 15))
    for _ in range(75):
        end = start + datetime.timedelta(minutes=5)
        o = price
        c = on_tick(o + rng.gauss(0.15, 12.0))
        hi = on_tick(max(o, c) + abs(rng.gauss(0.0, 6.0)))
        lo = on_tick(min(o, c) - abs(rng.gauss(0.0, 6.0)))
        candles.append({
            "datetime": end.strftime("%Y-%m-%dT%H:%M:%S"),
            "open": o,
            "high": hi,
            "low": lo,
            "close": c,
            "volume": int(rng.randint(0, 5000)),
        })
        price = c
        start = end
    return candles, price


def main():
    rng = random.Random(SEED)
    price = 23000.0
    candles = []
    for day in trading_days_before(PLAN_DAY, SESSIONS):
        made, price = session(rng, day, price)
        candles.extend(made)
    with open(REAL, encoding="utf-8") as fh:
        real = json.load(fh)["candles"]
    candles.extend(real)
    payload = {"candles": candles}
    with open(ALGOTEST, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, separators=(",", ":"))
        fh.write("\n")
    doc, report = to_yahoo(payload, "NIFTY", "5m", "end", None)
    os.makedirs(os.path.dirname(YAHOO), exist_ok=True)
    with open(YAHOO, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, separators=(",", ":"))
        fh.write("\n")
    print("%s: %d candles, %s to %s" % (
        ALGOTEST, len(candles), candles[0]["datetime"], candles[-1]["datetime"]))
    print("%s: %d bars, %s to %s IST" % (
        YAHOO, report["bars"],
        report["first"].strftime("%Y-%m-%d %H:%M"),
        report["last"].strftime("%Y-%m-%d %H:%M")))
    if report["skipped"] or report["warnings"]:
        print("skipped %s" % report["skipped"])
        print("warnings %s" % report["warnings"])
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
