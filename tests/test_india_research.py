"""Holdout guard, listing window, breaks, and the daily versus 5-minute check."""

import csv
import datetime
import gzip
import io
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout

from _load import load

data = load("india/research", "data")
audit = load("india/research", "audit")
bt = load("india", "backtest")

FIELDS = ["datetime_start_ist", "open", "high", "low", "close", "volume"]


def _write(path, rows):
    folder = os.path.dirname(path)
    if folder and not os.path.isdir(folder):
        os.makedirs(folder)
    with gzip.open(path, "wt", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=FIELDS, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _day(day, close):
    return {
        "datetime_start_ist": "%s 00:00:00" % day.isoformat(),
        "open": close, "high": close, "low": close, "close": close, "volume": 1,
    }


def _minute(day, n, last_close):
    start = datetime.datetime(day.year, day.month, day.day, 9, 15)
    rows = []
    for i in range(n):
        stamp = start + datetime.timedelta(minutes=5 * i)
        close = last_close if i == n - 1 else last_close - 1
        rows.append({
            "datetime_start_ist": stamp.strftime("%Y-%m-%d %H:%M:%S"),
            "open": close, "high": close, "low": close, "close": close, "volume": 1,
        })
    return rows


def _daily(root, symbol, closes, start):
    rows = []
    for i, close in enumerate(closes):
        rows.append(_day(start + datetime.timedelta(days=i), close))
    _write(data.bar_path(root, "day", symbol), rows)


class ResearchData(unittest.TestCase):
    def test_holdout_blocks_bars_on_and_after_2025(self):
        root = tempfile.mkdtemp()
        start = datetime.date(2024, 12, 1)
        days = [start + datetime.timedelta(days=i) for i in range(20)]
        days.append(data.HOLDOUT_START)
        rows = [_day(day, 10) for day in days]
        _write(data.bar_path(root, "day", "AAA"), rows)
        with self.assertRaises(data.HoldoutError) as caught:
            data.load_daily(root, "AAA")
        message = str(caught.exception)
        self.assertIn("2025-01-01", message)
        self.assertIn("final=True", message)

        log_path = os.path.join(root, "HOLDOUT_LOG.md")
        buf = io.StringIO()
        with redirect_stdout(buf):
            series = data.load_daily(root, "AAA", final=True, log_path=log_path)
        self.assertEqual(series.dates(), [data.HOLDOUT_START])
        self.assertIn("HOLDOUT", buf.getvalue())
        self.assertIn("2025-01-01", buf.getvalue())
        with open(log_path, encoding="utf-8") as fh:
            text = fh.read()
        self.assertIn(sys.argv[0], text)
        self.assertRegex(text, r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}")
        self.assertEqual(len(series.excluded["listing"]), 20)

        quiet = tempfile.mkdtemp()
        _daily(quiet, "BBB", [10] * 25, datetime.date(2024, 6, 1))
        before = data.load_daily(quiet, "BBB")
        self.assertTrue(all(day < data.HOLDOUT_START for day in before.dates()))
        self.assertFalse(os.path.isfile(data.HOLDOUT_LOG))

    def test_first_20_sessions_are_excluded(self):
        root = tempfile.mkdtemp()
        start = datetime.date(2024, 6, 1)
        _daily(root, "AAA", [10] * 25, start)
        series = data.load_daily(root, "AAA")
        self.assertEqual(len(series.excluded["listing"]), 20)
        self.assertEqual(series.excluded["listing"][0], start)
        self.assertEqual(series.excluded["listing"][-1], start + datetime.timedelta(days=19))
        self.assertEqual(series.dates()[0], start + datetime.timedelta(days=20))
        self.assertEqual(len(series.dates()), 5)
        self.assertEqual(series.excluded["breaks"], [])

    def test_breaks_split_the_series_and_block_a_holding_across_them(self):
        root = tempfile.mkdtemp()
        start = datetime.date(2024, 1, 1)
        closes = [100] * 23
        closes.append(210)
        closes.extend([210, 210])
        closes.append(39)
        closes.append(39)
        _daily(root, "AAA", closes, start)
        series = data.load_daily(root, "AAA")
        self.assertEqual(len(series.segments), 3)
        self.assertEqual([item["date"] for item in series.segments[0]], [
            start + datetime.timedelta(days=20),
            start + datetime.timedelta(days=21),
            start + datetime.timedelta(days=22),
        ])
        up = start + datetime.timedelta(days=23)
        down = start + datetime.timedelta(days=26)
        self.assertEqual(series.segments[1][0]["date"], up)
        self.assertEqual(series.segments[2][0]["date"], down)
        changes = [round(item["change"], 4) for item in series.excluded["breaks"]]
        self.assertEqual(changes, [1.1, round((39 - 210) / 210.0, 4)])
        with self.assertRaises(data.BreakError) as crossed:
            data.holding_return(series, up - datetime.timedelta(days=1), up)
        self.assertIn("crosses a break", str(crossed.exception))
        self.assertEqual(data.holding_return(series, start + datetime.timedelta(days=20), up - datetime.timedelta(days=1)), 0)
        self.assertEqual(data.holding_return(series, up, up + datetime.timedelta(days=2)), 0)

        flat = tempfile.mkdtemp()
        exact = [50] * 20 + [100, 200, 80]
        _daily(flat, "BBB", exact, start)
        same = data.load_daily(flat, "BBB")
        self.assertEqual(len(same.segments), 1)
        self.assertEqual(same.excluded["breaks"], [])
        self.assertEqual(data.holding_return(same, start + datetime.timedelta(days=20), start + datetime.timedelta(days=21)), 1)
        self.assertAlmostEqual(
            data.holding_return(same, start + datetime.timedelta(days=21), start + datetime.timedelta(days=22)),
            -0.6)

    def test_session_end_label_matches_the_backtest_shift(self):
        root = tempfile.mkdtemp()
        start = datetime.date(2024, 6, 1)
        rows = []
        for i in range(21):
            day = start + datetime.timedelta(days=i)
            if i < 20:
                rows.extend(_minute(day, 1, 10))
            else:
                rows.append({
                    "datetime_start_ist": "2024-06-21 09:15:00",
                    "open": 11, "high": 12, "low": 10, "close": 11.5, "volume": 3,
                })
        _write(data.bar_path(root, "5minute", "AAA"), rows)
        series = data.load_sessions(root, "AAA")
        self.assertEqual(len(series.segments), 1)
        bar = series.segments[0][0]["bars"][0]
        self.assertEqual(bar["end"], datetime.datetime(2024, 6, 21, 9, 20))
        self.assertEqual(bar["end"], bt.kite_end_label(datetime.datetime(2024, 6, 21, 9, 15)))
        self.assertEqual(series.segments[0][0]["close"], 11.5)


class Audit(unittest.TestCase):
    def test_consistency_counts_days_off_by_more_than_half_a_percent(self):
        root = tempfile.mkdtemp()
        day_a = datetime.date(2024, 6, 3)
        day_b = datetime.date(2024, 6, 4)
        day_c = datetime.date(2024, 6, 5)
        _write(data.bar_path(root, "day", "AAA"), [
            _day(day_a, 100),
            _day(day_b, 100),
            _day(day_c, 200),
        ])
        rows = []
        rows.extend(_minute(day_a, 75, 100.5))
        rows.extend(_minute(day_b, 75, 101))
        rows.extend(_minute(day_c, 10, 200))
        _write(data.bar_path(root, "5minute", "AAA"), rows)
        row = audit.symbol_row(root, "AAA")
        self.assertEqual(row["day_sessions"], "3")
        self.assertEqual(row["minute_sessions"], "3")
        self.assertEqual(row["unusable_sessions"], "1")
        self.assertEqual(row["close_differs"], "1")
        self.assertEqual(row["day_first"], "2024-06-03")
        self.assertEqual(row["minute_last"], "2024-06-05")
        self.assertFalse(data.off_by_more_than_half_percent(100, 100.5))
        self.assertTrue(data.off_by_more_than_half_percent(100, 101))

        out = os.path.join(root, "reports", "audit.csv")
        written = audit.write_report(root, out)
        self.assertEqual(len(written), 1)
        with open(out, encoding="utf-8", newline="") as fh:
            loaded = list(csv.DictReader(fh))
        self.assertEqual(loaded[0]["symbol"], "AAA")
        self.assertEqual(loaded[0]["close_differs"], "1")
        text = "\n".join(audit.summary_lines(written))
        self.assertIn("symbols: 1", text)
        self.assertIn("close differs from NSE official close: 1", text)
        self.assertIn("30-minute weighted average", text)
        self.assertIn("breaks: 0", text)
        self.assertIn("RELIANCE: not in the folder", text)
