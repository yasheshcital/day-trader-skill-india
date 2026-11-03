#!/usr/bin/env python3
"""Turn AlgoTest OHLC candles into the Yahoo v8 chart JSON the trader scripts
read with --offline.

    python3 india/algotest_to_yahoo.py INPUT.json --symbol NIFTY --out trader/bars

Input is a file saved from AlgoTest's get_ohlc_by_data_source:

    {"candles": [{"datetime": "2026-10-30T09:20:00", "open": ..., "high": ...,
                  "low": ..., "close": ..., "volume": ...}, ...]}

"datetime" is naive IST. By default it marks the END of the bar (--label end).
Yahoo timestamps are the bar START as UTC epoch seconds: end minus one
interval, then IST minus 5:30. The clock comes from india/nse_market.py.
Standard library only. Nothing here places an order.
"""

import argparse
import datetime
import json
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from india import nse_market

INTERVALS = {"1m": 60, "5m": 300}
EPOCH = datetime.datetime(1970, 1, 1)
OUTSIDE = "outside the session"


class ConvertError(Exception):
    pass


def _epoch(utc_naive):
    return int((utc_naive.replace(tzinfo=None) - EPOCH).total_seconds())


def _parse_ist(text, where):
    try:
        dt = datetime.datetime.fromisoformat(str(text))
    except ValueError:
        raise ConvertError("%s is not a time like 2026-10-30T09:20:00" % where)
    if dt.tzinfo is not None:
        raise ConvertError("%s must be naive IST, not an offset" % where)
    return dt


def _classify(start, interval_sec):
    """'ok', 'outside', or 'off'. Start must sit on the interval grid inside
    09:15 inclusive to 15:30 exclusive (so 5m ends at 15:25, 1m at 15:29)."""
    if start.second or start.microsecond:
        return "off"
    start_min = start.hour * 60 + start.minute
    open_min = nse_market.OPEN.hour * 60 + nse_market.OPEN.minute
    close_min = nse_market.CLOSE.hour * 60 + nse_market.CLOSE.minute
    if start_min < open_min or start_min >= close_min:
        return "outside"
    step = interval_sec // 60
    if (start_min - open_min) % step != 0:
        return "off"
    return "ok"


def _bump(counts, reason):
    counts[reason] = counts.get(reason, 0) + 1


def _candles(payload):
    if isinstance(payload, dict) and isinstance(payload.get("candles"), list):
        return payload["candles"]
    raise ConvertError("expected a JSON object with a candles list")


def _symbol(symbol):
    sym = str(symbol).strip().upper()
    if not sym or "/" in sym or "\\" in sym:
        raise ConvertError("symbol is not a file name: %r" % (symbol,))
    return sym


def to_yahoo(payload, symbol, interval="5m", label="end", prev_close=None):
    """AlgoTest payload -> (Yahoo chart doc, report).

    previousClose is the last close of the session before the last one in the
    file. With only one session, --prev-close fills it in. Otherwise both
    previousClose and chartPreviousClose are left out. A day whose first kept
    bar does not start at 09:15 is a warning, not an error.
    """
    if interval not in INTERVALS:
        raise ConvertError("interval wants 1m or 5m, not %r" % (interval,))
    if label not in ("end", "start"):
        raise ConvertError("label wants end or start, not %r" % (label,))
    sym = _symbol(symbol)
    step = INTERVALS[interval]
    shift = datetime.timedelta(seconds=step if label == "end" else 0)
    counts = {}
    kept = {}
    for i, candle in enumerate(_candles(payload)):
        where = "candle %d" % (i + 1,)
        if not isinstance(candle, dict):
            raise ConvertError("%s is not an object" % where)
        mark = _parse_ist(candle.get("datetime"), where)
        start = mark - shift
        ok, reason = nse_market.trading_day(start.date())
        if not ok:
            _bump(counts, reason)
            continue
        kind = _classify(start, step)
        if kind == "outside":
            _bump(counts, OUTSIDE)
            continue
        if kind == "off":
            _bump(counts, "off the %s grid" % interval)
            continue
        try:
            o = float(candle["open"])
            h = float(candle["high"])
            lo = float(candle["low"])
            c = float(candle["close"])
            vol = int(float(candle.get("volume") or 0))
        except (KeyError, TypeError, ValueError):
            _bump(counts, "missing price")
            continue
        if start in kept:
            _bump(counts, "duplicate bar")
        kept[start] = {"start": start, "o": o, "h": h, "l": lo, "c": c, "v": vol}

    bars = [kept[k] for k in sorted(kept)]
    if not bars:
        why = ", ".join("%d %s (%s)" % (n, "bar" if n == 1 else "bars", reason)
                        for reason, n in counts.items())
        raise ConvertError("no session bars to write%s" % (": " + why if why else ""))

    days = []
    for bar in bars:
        day = bar["start"].date()
        if not days or days[-1][0] != day:
            days.append((day, [bar]))
        else:
            days[-1][1].append(bar)

    warnings = []
    for day, day_bars in days:
        opened = day_bars[0]["start"]
        if opened.time() != nse_market.OPEN:
            warnings.append("%s starts at %s IST, not 09:15" % (day.isoformat(), opened.strftime("%H:%M")))

    if len(days) >= 2:
        prev = days[-2][1][-1]["c"]
    elif prev_close is not None:
        prev = float(prev_close)
    else:
        prev = None

    last = bars[-1]
    meta = {
        "currency": "INR",
        "symbol": sym,
        "exchangeName": "NSE",
        "exchangeTimezoneName": "Asia/Kolkata",
        "timezone": "IST",
        "gmtoffset": 19800,
        "dataGranularity": interval,
        "regularMarketTime": _epoch(nse_market.ist_to_utc(last["start"] + datetime.timedelta(seconds=step))),
        "regularMarketPrice": last["c"],
    }
    if prev is not None:
        meta["previousClose"] = prev
        meta["chartPreviousClose"] = prev

    doc = {
        "chart": {
            "result": [{
                "meta": meta,
                "timestamp": [_epoch(nse_market.ist_to_utc(b["start"])) for b in bars],
                "indicators": {"quote": [{
                    "open": [b["o"] for b in bars],
                    "high": [b["h"] for b in bars],
                    "low": [b["l"] for b in bars],
                    "close": [b["c"] for b in bars],
                    "volume": [b["v"] for b in bars],
                }]},
            }],
            "error": None,
        }
    }
    report = {
        "symbol": sym,
        "bars": len(bars),
        "first": bars[0]["start"],
        "last": last["start"],
        "skipped": [(reason, n) for reason, n in counts.items()],
        "warnings": warnings,
    }
    return doc, report


def _bar_word(n):
    return "bar" if n == 1 else "bars"


def report_lines(report):
    """Lines for stderr: skips, then warnings. Empty when there is nothing to say."""
    lines = ["skipped %d %s: %s" % (n, _bar_word(n), reason) for reason, n in report["skipped"]]
    lines.extend("warning: " + w for w in report["warnings"])
    return lines


def describe(path, report):
    """One stdout line: path, bars written, first and last bar start in IST."""
    return "%s: %d %s, %s to %s IST" % (
        path, report["bars"], _bar_word(report["bars"]),
        report["first"].strftime("%Y-%m-%d %H:%M"),
        report["last"].strftime("%Y-%m-%d %H:%M"))


def output_names(symbol, interval):
    names = ["%s.json" % symbol]
    if interval == "5m":
        names.append("%s-60d5m.json" % symbol)
    return names


def write_chart(doc, out_dir, symbol, interval):
    os.makedirs(out_dir, exist_ok=True)
    text = json.dumps(doc, separators=(",", ":")) + "\n"
    paths = []
    for name in output_names(symbol, interval):
        path = os.path.join(out_dir, name)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)
        paths.append(path)
    return paths


def main(argv=None):
    p = argparse.ArgumentParser(description="Convert AlgoTest candles to Yahoo chart JSON.")
    p.add_argument("input", help="JSON file from get_ohlc_by_data_source")
    p.add_argument("--symbol", required=True, help="ticker, for example NIFTY")
    p.add_argument("--interval", default="5m", choices=sorted(INTERVALS))
    p.add_argument("--label", default="end", choices=("end", "start"),
                   help="datetime is the bar end (default) or the bar start")
    p.add_argument("--prev-close", type=float, default=None,
                   help="previousClose when the file holds only one session")
    p.add_argument("--out", default=os.path.join("trader", "bars"),
                   help="folder for <SYMBOL>.json (default trader/bars)")
    args = p.parse_args(argv)
    try:
        with open(args.input, encoding="utf-8") as fh:
            payload = json.load(fh)
        doc, report = to_yahoo(payload, args.symbol, args.interval, args.label, args.prev_close)
        paths = write_chart(doc, args.out, report["symbol"], args.interval)
    except (OSError, ValueError, ConvertError) as e:
        print("algotest_to_yahoo: %s" % e, file=sys.stderr)
        return 1
    for line in report_lines(report):
        print(line, file=sys.stderr)
    for path in paths:
        print(describe(path, report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
