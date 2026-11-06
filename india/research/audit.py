#!/usr/bin/env python3
"""Audit data/kite, one symbol at a time.

Writes data/kite/reports/audit.csv. Each row is one symbol: the first and last
date of the daily file and of the 5-minute file, how many sessions each has,
how many 5-minute sessions are missing a bar from 09:15 to 15:10, how many
daily breaks there are, and how many days the last 5-minute close differs
from the NSE official close by more than 0.5%. That official close is a
30-minute weighted average, so it is not the last trade.

    python3 india/research/audit.py
    python3 india/research/audit.py --root data/kite
"""

import csv
import datetime
import os
import statistics
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from india.research import data

COLUMNS = [
    "symbol",
    "day_first",
    "day_last",
    "day_sessions",
    "minute_first",
    "minute_last",
    "minute_sessions",
    "unusable_sessions",
    "breaks",
    "break_dates",
    "close_differs",
]


def _iso(day):
    if day is None:
        return ""
    return day.isoformat()


def symbol_row(root, symbol):
    """One symbol. Streams its daily file and its 5-minute file, then drops them."""
    day_path = data.bar_path(root, "day", symbol)
    minute_path = data.bar_path(root, "5minute", symbol)
    day_first = day_last = None
    day_sessions = 0
    daily_points = []
    if os.path.isfile(day_path):
        day_first, day_last, day_sessions, daily_points = data.scan_daily_symbol(root, symbol)
    minute_first = minute_last = None
    counts = {}
    last_close = {}
    masks = {}
    if os.path.isfile(minute_path):
        minute_first, minute_last, counts, last_close, masks = data.scan_minute_symbol(root, symbol)
    break_points = daily_points
    if not break_points and last_close:
        break_points = [(day, last_close[day]) for day in sorted(last_close)]
    breaks = data.find_breaks(break_points)
    unusable = 0
    for day in counts:
        if not data.session_usable(masks.get(day, 0)):
            unusable += 1
    differs = 0
    daily_close = dict(daily_points)
    if os.path.isfile(day_path) and os.path.isfile(minute_path):
        for day in sorted(set(daily_close) & set(last_close)):
            if data.off_by_more_than_half_percent(daily_close[day], last_close[day]):
                differs += 1
    return {
        "symbol": symbol,
        "day_first": _iso(day_first),
        "day_last": _iso(day_last),
        "day_sessions": str(day_sessions),
        "minute_first": _iso(minute_first),
        "minute_last": _iso(minute_last),
        "minute_sessions": str(len(counts)),
        "unusable_sessions": str(unusable),
        "breaks": str(len(breaks)),
        "break_dates": ";".join(item["date"].isoformat() for item in breaks),
        "close_differs": str(differs),
    }


def summary_lines(rows):
    """Symbols, 5-minute years, breaks, official-close gaps, and the RELIANCE row."""
    lines = ["symbols: %d" % len(rows)]
    years = []
    for row in rows:
        if not row["minute_first"] or not row["minute_last"]:
            continue
        first = datetime.date.fromisoformat(row["minute_first"])
        last = datetime.date.fromisoformat(row["minute_last"])
        years.append((last - first).days / 365.25)
    if years:
        lines.append("5-minute years: median %.2f, min %.2f" % (statistics.median(years), min(years)))
    else:
        lines.append("5-minute years: median none, min none")
    breaks = 0
    failures = 0
    reliance = None
    for row in rows:
        breaks += int(row["breaks"] or 0)
        failures += int(row["close_differs"] or 0)
        if row["symbol"] == "RELIANCE":
            reliance = row
    lines.append("breaks: %d" % breaks)
    lines.append("close differs from NSE official close: %d" % failures)
    lines.append("NSE's close is a 30-minute weighted average.")
    if reliance is None:
        lines.append("RELIANCE: not in the folder")
    else:
        lines.append("RELIANCE: %s" % " ".join("%s=%s" % (key, reliance[key]) for key in COLUMNS))
    return lines


def write_report(root, out_path):
    """One row per symbol. Symbols are streamed; the report holds only the rows."""
    rows = []
    for symbol in data.symbols_in(root):
        rows.append(symbol_row(root, symbol))
    folder = os.path.dirname(out_path)
    if folder and not os.path.isdir(folder):
        os.makedirs(folder)
    with open(out_path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=COLUMNS, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    return rows


def main(argv=None, log=None):
    import argparse
    parser = argparse.ArgumentParser(description="Audit Kite day and 5-minute files. Nothing is placed.")
    parser.add_argument("--root", default=os.path.join("data", "kite"))
    parser.add_argument("--out", default=None, help="audit csv (default ROOT/reports/audit.csv)")
    args = parser.parse_args(argv)
    out_path = args.out or os.path.join(args.root, "reports", "audit.csv")
    emit = log or (lambda line: print(line))
    rows = write_report(args.root, out_path)
    for line in summary_lines(rows):
        emit(line)
    emit("wrote %s" % out_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
