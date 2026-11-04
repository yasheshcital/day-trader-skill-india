"""Paper runner for the trend-day rule. Replays the nifty50 fixtures through signals and close."""

import datetime
import io
import os
import tempfile
import unittest
from contextlib import redirect_stdout

from _load import FIX, load

bt = load("india", "backtest")
td = load("india", "trend_day")

NIFTY = os.path.join(FIX, "india", "NIFTY-2026-08-05_2026-11-03-5m.algotest.json")
NIFTY50 = os.path.join(FIX, "india", "nifty50")
SELL_DAY = "2026-10-23"


def _bar(c, h, l):
    return {"o": c, "h": h, "l": l, "c": c, "v": 1}


def _flat_session(break_at=None):
    """75 bars. The 30-minute range is 90 to 100. One bar may close above it."""
    bars = []
    for i in range(75):
        c, h, l = 95.0, 100.0, 90.0
        if i == break_at:
            c, h = 101.0, 101.0
        bars.append(_bar(c, h, l))
    return bars


def _logged(date, symbol, r, net_r, rupees, side="sell"):
    return {
        "date": date, "symbol": symbol, "side": side, "time": "9:50 AM",
        "entry": "100.00", "stop": "101.00", "target": "98.00", "shares": "10",
        "R": "%.2f" % r, "net_R": "%.6f" % net_r, "rupees": "%.2f" % rupees,
    }


class ForwardReport(unittest.TestCase):
    def test_empty_log_is_in_progress(self):
        lines = td.report_text([])
        self.assertIn("IN PROGRESS: 0 of 30 days", lines)

    def test_under_thirty_days_does_not_pass(self):
        rows = [_logged("2026-01-%02d" % day, "RELIANCE", 0.30, 0.20, 100) for day in range(1, 30)]
        lines = td.report_text(rows)
        self.assertIn("IN PROGRESS: 29 of 30 days", lines)
        self.assertNotIn("PASS", lines[-1])

    def test_pass_and_the_failing_marks(self):
        good = [_logged("2026-01-%02d" % day, "RELIANCE", 0.30, 0.20, 100) for day in range(1, 31)]
        self.assertEqual(td.report_text(good)[-1], "PASS")

        thin = [_logged("2026-01-%02d" % day, "RELIANCE", 0.30, 0.05, 100) for day in range(1, 31)]
        self.assertIn("average R after costs", td.report_text(thin)[-1])

        days = []
        for day in range(1, 31):
            rupees = 10 if day <= 16 else -1
            days.append(_logged("2026-01-%02d" % day, "RELIANCE", 0.30, 0.20, rupees))
        self.assertIn("need above 55%", td.report_text(days)[-1])
        days[16]["rupees"] = "10.00"
        self.assertEqual(td.report_text(days)[-1], "PASS")

        skewed = []
        for day in range(1, 31):
            if day <= 2:
                rupees = 1000
            elif day <= 19:
                rupees = 10
            else:
                rupees = -100
            skewed.append(_logged("2026-01-%02d" % day, "RELIANCE", 0.30, 0.20, rupees))
        self.assertIn("not profitable without the best 2 days", td.report_text(skewed)[-1])

        mixed = []
        for day in range(1, 31):
            mixed.append(_logged("2026-01-%02d" % day, "AAA", 0.30, 0.20, 100))
            mixed.append(_logged("2026-01-%02d" % day, "BBB", 0.30, 0.20, -10))
        self.assertIn("need 60%", td.report_text(mixed)[-1])

    def test_report_command_reads_the_log(self):
        path = os.path.join(tempfile.mkdtemp(), "paper_log.csv")
        td.write_log(path, [_logged("2026-01-01", "RELIANCE", 0.30, 0.20, 100)])
        with redirect_stdout(io.StringIO()):
            self.assertEqual(td.main(["report", "--log", path]), 0)


class SignalCutoff(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tm = bt.load_timemachine()

    def test_a_close_at_10_00_counts_and_10_05_does_not(self):
        # Bar index 8 closes at 10:00. Index 9 closes at 10:05.
        side, minute = td.trend_signal(_flat_session(8), self.tm, 15 * 60 + 30)
        self.assertEqual((side, minute), ("buy", 10 * 60))
        side, minute = td.trend_signal(_flat_session(9), self.tm, 15 * 60 + 30)
        self.assertEqual((side, minute), (None, None))

    def test_a_bar_that_has_not_closed_is_ignored(self):
        side, minute = td.trend_signal(_flat_session(8), self.tm, 10 * 60 - 1)
        self.assertEqual((side, minute), (None, None))
        side, minute = td.trend_signal(_flat_session(8), self.tm, 10 * 60)
        self.assertEqual((side, minute), ("buy", 10 * 60))


class Replay(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tm = bt.load_timemachine()
        cls.loaded = bt.load_folder(NIFTY50, cls.tm)
        _symbol, cls.nifty, _short = bt.load_sessions(NIFTY, cls.tm)

    def _attempt7(self):
        side, minute = td.trend_signal(dict(self.nifty)[SELL_DAY], self.tm, 15 * 60 + 30)
        self.assertEqual(side, "sell")
        self.assertEqual(minute, 9 * 60 + 50)
        before, after = bt.entry_window(30)
        last = bt.flat_slot(self.tm)
        rows = []
        for item in self.loaded:
            bars = dict(item["sessions"]).get(SELL_DAY)
            if not bars:
                continue
            _hist, trades = bt._collect_trades(
                self.tm, [(SELL_DAY, bars)], item["symbol"], td.RULE, last, side,
                before, after, {SELL_DAY}, {SELL_DAY: minute})
            for trade in trades:
                row = dict(trade)
                row["symbol"] = item["symbol"]
                row["side"] = side
                row["entry_min"] = self.tm.parse_clock(trade["time"], "entry")
                rows.append(row)
        rows.sort(key=lambda row: (row["entry_min"], row["symbol"], row["side"]))
        return rows

    def test_sell_day_matches_attempt_7_and_a_quiet_day_does_not_trade(self):
        attempt = self._attempt7()
        self.assertGreater(len(attempt), td.EXPECTED_ENTRIES)
        kept = attempt[:td.EXPECTED_ENTRIES]
        path = os.path.join(tempfile.mkdtemp(), "paper_log.csv")
        lines = td.signals_day(self.loaded, self.nifty, SELL_DAY, 15 * 60 + 10, path, self.tm)
        self.assertIn("2026-10-23 is a trend day: sell, signal 9:50 AM.", lines)
        logged = td.read_log(path)
        self.assertEqual(len(logged), td.EXPECTED_ENTRIES)
        for got, want in zip(logged, kept):
            self.assertEqual(got["symbol"], want["symbol"])
            self.assertEqual(got["side"], "sell")
            self.assertEqual(got["time"], self.tm.clock12(want["entry_min"]))
            self.assertEqual(got["entry"], "%.2f" % want["entry"])
            self.assertEqual(got["stop"], "%.2f" % want["stop"])
            self.assertEqual(got["target"], "%.2f" % want["target"])
            shares = bt.whole_shares(want["entry"], want["stop"], td.slice_risk(), td.CAPITAL)
            self.assertEqual(int(got["shares"]), shares)
        dropped = attempt[td.EXPECTED_ENTRIES]
        self.assertNotIn(dropped["symbol"], [row["symbol"] for row in logged])

        again = td.signals_day(self.loaded, self.nifty, SELL_DAY, 15 * 60 + 10, path, self.tm)
        self.assertIn("No new entries.", again)
        self.assertEqual(len(td.read_log(path)), td.EXPECTED_ENTRIES)

        early = os.path.join(tempfile.mkdtemp(), "early.csv")
        early_lines = td.signals_day(self.loaded, self.nifty, SELL_DAY, 9 * 60 + 49, early, self.tm)
        self.assertIn("no signal yet. Watching until 10:00.", early_lines[0])
        self.assertEqual(td.read_log(early), [])

        quiet = None
        stock_dates = set(date for item in self.loaded for date, _bars in item["sessions"])
        for date, bars in self.nifty:
            if date not in stock_dates:
                continue
            if td.trend_signal(bars, self.tm, 15 * 60 + 30)[0] is None:
                quiet = date
                break
        self.assertIsNotNone(quiet)
        quiet_lines = td.signals_day(self.loaded, self.nifty, quiet, 15 * 60 + 10, path, self.tm)
        self.assertIn("no signal by 10:00: no trades today", quiet_lines[0])
        self.assertEqual(len(td.read_log(path)), td.EXPECTED_ENTRIES)

        filled = td.close_day(self.loaded, self.nifty, SELL_DAY, path, self.tm)
        self.assertIn("filled 35 trades.", filled[0])
        closed = td.read_log(path)
        scored = dict(((row["symbol"], row["entry_min"]), row) for row in td._score_kept(
            self.loaded, self.tm, SELL_DAY, "sell", 9 * 60 + 50))
        for got, want in zip(closed, kept):
            self.assertEqual(got["R"], "%.2f" % want["R"])
            check = scored[(got["symbol"], self.tm.parse_clock(got["time"], "entry"))]
            self.assertEqual(got["rupees"], "%.2f" % check["net"])
            self.assertEqual(got["net_R"], "%.6f" % check["R_after"])
        report = td.report_text(closed)
        self.assertIn("IN PROGRESS: 1 of 30 days", report)
        self.assertIn("Qualifying days: 1", report)
        self.assertIn("Trades: 35", report)

        with self.assertRaises(td.TrendError) as early_close:
            td.close_day(self.loaded, self.nifty, SELL_DAY, path, self.tm,
                         today=SELL_DAY, now=datetime.datetime(2026, 10, 23, 15, 0))
        self.assertIn("15:10", str(early_close.exception))
