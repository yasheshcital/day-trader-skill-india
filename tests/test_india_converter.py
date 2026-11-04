"""AlgoTest candles -> the Yahoo chart JSON entry.py reads with --offline."""

import datetime
import io
import json
import os
import shutil
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout

from _load import FIX, load

conv = load("india", "algotest_to_yahoo")
entry = load("trader-entry", "entry")

FIXTURE = os.path.join(FIX, "india", "NIFTY-2026-10-30-5m.algotest.json")


def run(argv):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = conv.main(argv)
    return code, out.getvalue(), err.getvalue()


def candle(when, o, h, lo, c, v=0):
    return {"datetime": when, "open": o, "high": h, "low": lo, "close": c, "volume": v}


def result_of(doc):
    return doc["chart"]["result"][0]


class Converter(unittest.TestCase):
    def test_nifty_day_writes_seventy_five_bars(self):
        tmp = tempfile.mkdtemp()
        try:
            code, out, err = run([FIXTURE, "--symbol", "NIFTY", "--out", tmp])
            self.assertEqual(code, 0, err)
            self.assertEqual(err, "")
            path = os.path.join(tmp, "NIFTY.json")
            twin = os.path.join(tmp, "NIFTY-60d5m.json")
            with open(path, encoding="utf-8") as fh:
                doc = json.load(fh)
            with open(twin, encoding="utf-8") as fh:
                self.assertEqual(json.load(fh), doc)
            r = result_of(doc)
            q = r["indicators"]["quote"][0]
            ts = r["timestamp"]
            self.assertEqual(len(ts), 75)
            self.assertEqual(ts[0], 1793331900)          # 09:15 IST = 03:45 UTC
            self.assertEqual(ts[-1], 1793354100)         # 15:25 IST
            self.assertEqual(r["meta"]["regularMarketTime"], 1793354400)  # 15:30 IST
            self.assertEqual(q["open"][0], 22965.9)
            self.assertEqual(q["close"][-1], 23053.1)
            self.assertEqual(r["meta"]["regularMarketPrice"], 23053.1)
            self.assertEqual([t % 300 for t in ts], [0] * 75)
            self.assertEqual([ts[i + 1] - ts[i] for i in range(74)], [300] * 74)
            self.assertEqual(q["volume"], [0] * 75)
            meta = r["meta"]
            self.assertEqual(meta["symbol"], "NIFTY")
            self.assertEqual(meta["currency"], "INR")
            self.assertEqual(meta["exchangeName"], "NSE")
            self.assertEqual(meta["exchangeTimezoneName"], "Asia/Kolkata")
            self.assertEqual(meta["gmtoffset"], 19800)
            self.assertEqual(meta["timezone"], "IST")
            self.assertNotIn("previousClose", meta)
            self.assertNotIn("chartPreviousClose", meta)
            lines = out.splitlines()
            self.assertEqual(len(lines), 2)
            self.assertIn("75 bars", lines[0])
            self.assertIn("2026-10-30 09:15", lines[0])
            self.assertIn("2026-10-30 15:25", lines[0])
            self.assertTrue(lines[0].startswith(path + ":"))
            self.assertTrue(lines[1].startswith(twin + ":"))
        finally:
            shutil.rmtree(tmp)

    def test_parse_chart_reads_seventy_five_bars(self):
        with open(FIXTURE, encoding="utf-8") as fh:
            doc, _ = conv.to_yahoo(json.load(fh), "NIFTY")
        chart = entry.parse_chart(json.dumps(doc), "NIFTY")
        self.assertEqual(len(chart["bars"]), 75)
        self.assertEqual(chart["bars"][0]["t"], 1793331900)
        self.assertEqual(chart["bars"][0]["o"], 22965.9)
        self.assertEqual(chart["bars"][-1]["c"], 23053.1)
        self.assertEqual(chart["symbol"], "NIFTY")

    def test_two_days_set_previous_close_from_day_one(self):
        payload = {"candles": [
            candle("2026-10-29T09:20:00", 100, 101, 99, 100.5),
            candle("2026-10-29T15:30:00", 108, 111, 107, 110),
            candle("2026-10-30T09:20:00", 111, 112, 110, 111.5),
            candle("2026-10-30T15:30:00", 112, 121, 112, 120),
        ]}
        doc, report = conv.to_yahoo(payload, "NIFTY")
        meta = result_of(doc)["meta"]
        self.assertEqual(meta["previousClose"], 110)
        self.assertEqual(meta["chartPreviousClose"], 110)
        self.assertEqual(meta["regularMarketPrice"], 120)
        self.assertEqual(len(result_of(doc)["timestamp"]), 4)
        self.assertEqual(report["warnings"], [])
        self.assertEqual(report["skipped"], [])

    def test_a_weekend_date_is_skipped(self):
        payload = {"candles": [
            candle("2026-10-30T09:20:00", 1, 2, 1, 1.5),
            candle("2026-10-31T09:20:00", 9, 9, 9, 9),   # Saturday
            candle("2026-11-01T10:00:00", 8, 8, 8, 8),   # Sunday
        ]}
        doc, report = conv.to_yahoo(payload, "NIFTY")
        self.assertEqual(report["skipped"], [("weekend", 2)])
        self.assertEqual(result_of(doc)["indicators"]["quote"][0]["close"], [1.5])
        tmp = tempfile.mkdtemp()
        try:
            src = os.path.join(tmp, "in.json")
            with open(src, "w", encoding="utf-8") as fh:
                json.dump(payload, fh)
            code, out, err = run([src, "--symbol", "NIFTY", "--out", os.path.join(tmp, "out")])
            self.assertEqual(code, 0, err)
            self.assertIn("skipped 2 bars: weekend", err)
            self.assertIn("1 bar, 2026-10-30 09:15 to 2026-10-30 09:15 IST", out)
        finally:
            shutil.rmtree(tmp)

    def test_a_holiday_is_skipped_once_added(self):
        key = "2026-10-30"
        saved = conv.nse_market.NSE_HOLIDAYS.get(key)
        conv.nse_market.NSE_HOLIDAYS[key] = "Diwali Laxmi Pujan"
        try:
            doc, report = conv.to_yahoo({"candles": [
                candle("2026-10-29T15:30:00", 1, 1, 1, 3),
                candle("2026-10-30T09:20:00", 9, 9, 9, 9),
            ]}, "NIFTY")
            self.assertEqual(report["skipped"], [("NSE holiday: Diwali Laxmi Pujan", 1)])
            self.assertEqual(result_of(doc)["indicators"]["quote"][0]["close"], [3.0])
            self.assertNotIn("previousClose", result_of(doc)["meta"])
        finally:
            if saved is None:
                conv.nse_market.NSE_HOLIDAYS.pop(key, None)
            else:
                conv.nse_market.NSE_HOLIDAYS[key] = saved

    def test_prev_close_fills_a_one_day_file(self):
        doc, _ = conv.to_yahoo(
            {"candles": [candle("2026-10-30T09:20:00", 1, 1, 1, 2)]},
            "NIFTY", prev_close=50)
        meta = result_of(doc)["meta"]
        self.assertEqual(meta["previousClose"], 50)
        self.assertEqual(meta["chartPreviousClose"], 50)

    def test_a_bar_that_starts_at_the_close_is_left_out(self):
        # 15:35 IST is the end of a bar that starts at 15:30, which is not a session bar.
        doc, report = conv.to_yahoo({"candles": [
            candle("2026-10-30T09:20:00", 1, 1, 1, 1),
            candle("2026-10-30T15:35:00", 2, 2, 2, 2),
        ]}, "NIFTY")
        self.assertEqual(len(result_of(doc)["timestamp"]), 1)
        self.assertEqual(report["skipped"], [(conv.OUTSIDE, 1)])

    def test_one_minute_keeps_the_bar_that_starts_at_1529(self):
        doc, report = conv.to_yahoo({"candles": [
            candle("2026-10-30T09:16:00", 1, 1, 1, 1),
            candle("2026-10-30T15:30:00", 2, 2, 2, 4),
            candle("2026-10-30T15:31:00", 3, 3, 3, 3),
        ]}, "NIFTY", interval="1m")
        self.assertEqual(result_of(doc)["timestamp"], [1793331900, 1793354340])
        self.assertEqual(result_of(doc)["indicators"]["quote"][0]["close"], [1, 4])
        self.assertEqual(result_of(doc)["meta"]["regularMarketTime"], 1793354400)
        self.assertEqual(report["skipped"], [(conv.OUTSIDE, 1)])
        self.assertEqual(conv.output_names("NIFTY", "1m"), ["NIFTY.json"])

    def test_an_nse_underlying_name_drops_the_prefix(self):
        payload = {"underlying": "NSE_RELIANCE", "candles": [
            candle("2026-10-30T09:20:00", 1, 1, 1, 1),
        ]}
        doc, report = conv.to_yahoo(payload, None)
        self.assertEqual(report["symbol"], "RELIANCE")
        self.assertEqual(result_of(doc)["meta"]["symbol"], "RELIANCE")
        doc, _ = conv.to_yahoo({"candles": payload["candles"]}, "NSE_RELIANCE")
        self.assertEqual(result_of(doc)["meta"]["symbol"], "RELIANCE")
        tmp = tempfile.mkdtemp()
        try:
            src = os.path.join(tmp, "in.json")
            with open(src, "w", encoding="utf-8") as fh:
                json.dump(payload, fh)
            code, out, err = run([src, "--interval", "5m", "--out", os.path.join(tmp, "out")])
            self.assertEqual(code, 0, err)
            self.assertTrue(os.path.exists(os.path.join(tmp, "out", "RELIANCE.json")))
            self.assertIn("RELIANCE.json", out)
        finally:
            shutil.rmtree(tmp)

    def test_daily_bars_are_stamped_at_the_open(self):
        payload = {"underlying": "NSE_RELIANCE", "candles": [
            {"datetime": "2026-10-27T15:40:00", "open": 1195.2, "high": 1202.6, "low": 1184.0,
             "close": 1196.2, "volume": 23484423.0},
            {"datetime": "2026-10-28T15:40:00", "open": 1194.5, "high": 1204.3, "low": 1156.4,
             "close": 1158.0, "volume": 42777865.0},
            {"datetime": "2026-10-29T15:40:00", "open": 1159.2, "high": 1182.1, "low": 1155.6,
             "close": 1167.4, "volume": 39866205.0},
            {"datetime": "2026-10-30T15:40:00", "open": 1170.6, "high": 1174.6, "low": 1152.5,
             "close": 1164.9, "volume": 27134835.0},
        ]}
        doc, report = conv.to_yahoo(payload, None, interval="1d")
        r = result_of(doc)
        q = r["indicators"]["quote"][0]

        def epoch(day, hour, minute):
            utc = conv.nse_market.ist_to_utc(datetime.datetime(2026, 10, day, hour, minute))
            return int((utc - conv.EPOCH).total_seconds())

        self.assertEqual(r["timestamp"], [epoch(d, 9, 15) for d in (27, 28, 29, 30)])
        self.assertEqual(r["meta"]["regularMarketTime"], epoch(30, 15, 30))
        self.assertEqual(r["meta"]["dataGranularity"], "1d")
        self.assertEqual(r["meta"]["symbol"], "RELIANCE")
        self.assertEqual(q["open"], [1195.2, 1194.5, 1159.2, 1170.6])
        self.assertEqual(q["high"], [1202.6, 1204.3, 1182.1, 1174.6])
        self.assertEqual(q["low"], [1184.0, 1156.4, 1155.6, 1152.5])
        self.assertEqual(q["close"], [1196.2, 1158.0, 1167.4, 1164.9])
        self.assertEqual(q["volume"], [23484423, 42777865, 39866205, 27134835])
        self.assertEqual(r["meta"]["previousClose"], 1167.4)
        self.assertEqual(report["skipped"], [])
        self.assertEqual(report["warnings"], [])
        self.assertEqual(report["bars"], 4)

    def test_a_late_open_warns_and_still_writes(self):
        doc, report = conv.to_yahoo(
            {"candles": [candle("2026-10-30T10:05:00", 1, 2, 1, 2)]}, "NIFTY")
        self.assertEqual(len(result_of(doc)["timestamp"]), 1)
        self.assertEqual(report["warnings"], ["2026-10-30 starts at 10:00 IST, not 09:15"])


if __name__ == "__main__":
    unittest.main()
