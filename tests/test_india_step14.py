"""Cache, regime, usable sessions, and the trend-day study. Synthetic files only."""

import datetime
import os
import shutil
import tempfile
import unittest

from _load import load

data = load("india/research", "data")
cache = load("india/research", "cache")
regime = load("india/research", "regime")
audit = load("india/research", "audit")
study = load("india/research", "trend_day_study")

def _bars(day, n, close=99.5, high=100.0, low=99.0, volume=1):
    start = datetime.datetime(day.year, day.month, day.day, 9, 15)
    rows = []
    for i in range(n):
        stamp = start + datetime.timedelta(minutes=5 * i)
        rows.append({
            "start": stamp, "date": day, "open": close, "high": high,
            "low": low, "close": close, "volume": volume,
        })
    return rows


def _breakout(day):
    rows = _bars(day, 72)
    rows[6]["close"] = 101
    rows[6]["high"] = 101
    rows[6]["low"] = 99.5
    for row in rows[7:]:
        row["open"] = 101
        row["high"] = 110
        row["low"] = 100
        row["close"] = 105
    return rows


def _write_gz(path, rows, daily=False):
    import csv
    import gzip
    folder = os.path.dirname(path)
    if folder and not os.path.isdir(folder):
        os.makedirs(folder)
    fields = ["datetime_start_ist", "open", "high", "low", "close", "volume"]
    with gzip.open(path, "wt", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            if daily:
                stamp = "%s 00:00:00" % row.isoformat() if not isinstance(row, dict) else row["datetime_start_ist"]
            if isinstance(row, dict) and "start" in row:
                stamp = row["start"].strftime("%Y-%m-%d %H:%M:%S")
                out = {
                    "datetime_start_ist": stamp,
                    "open": row["open"], "high": row["high"], "low": row["low"],
                    "close": row["close"], "volume": row["volume"],
                }
            else:
                out = row
            writer.writerow(out)


def _daily_rows(start, closes, volume=1):
    rows = []
    for i, close in enumerate(closes):
        day = start + datetime.timedelta(days=i)
        rows.append({
            "datetime_start_ist": "%s 00:00:00" % day.isoformat(),
            "open": close, "high": close, "low": close, "close": close, "volume": volume,
        })
    return rows


class CacheAndUsable(unittest.TestCase):
    def test_cache_is_used_only_when_it_is_newer(self):
        root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, root)
        kite = os.path.join(root, "kite")
        start = datetime.date(2024, 6, 1)
        closes = [10] * 21
        _write_gz(data.bar_path(kite, "day", "AAA"), _daily_rows(start, closes), daily=True)
        text = []
        cache.build_all(kite, workers=0, log=text.append)
        self.assertIn("1 / 1 symbols", text)
        self.assertTrue(text[-1].startswith("build time:"))
        series = data.load_daily(kite, "AAA")
        self.assertEqual(series.dates(), [start + datetime.timedelta(days=20)])
        self.assertEqual(series.segments[0][0]["close"], 10)

        _write_gz(data.bar_path(kite, "day", "AAA"), _daily_rows(start, [12] * 21), daily=True)
        fresh = data.load_daily(kite, "AAA")
        self.assertEqual(fresh.segments[0][0]["close"], 12)

        cached = data.cache_file(kite, "day", "AAA")
        os.utime(cached, (os.path.getmtime(cached) + 50, os.path.getmtime(cached) + 50))
        again = data.load_daily(kite, "AAA")
        self.assertEqual(again.segments[0][0]["close"], 10)

    def test_pool_builds_two_symbols(self):
        root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, root)
        kite = os.path.join(root, "kite")
        start = datetime.date(2024, 6, 1)
        for symbol, close in (("AAA", 10), ("BBB", 20)):
            _write_gz(data.bar_path(kite, "day", symbol), _daily_rows(start, [close] * 21), daily=True)
        text = []
        cache.build_all(kite, workers=2, log=text.append)
        self.assertIn("2 / 2 symbols", text)
        elapsed, payloads = cache.load_all(kite, "day")
        self.assertEqual(len(payloads), 2)
        self.assertGreaterEqual(elapsed, 0)
        names = []
        for payload in payloads:
            self.assertEqual(payload["version"], 1)
            self.assertEqual(payload["sessions"][0]["close"].typecode, "d")

    def test_a_session_needs_every_bar_from_0915_to_1510(self):
        root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, root)
        kite = os.path.join(root, "kite")
        day_full = datetime.date(2024, 6, 3)
        day_short = datetime.date(2024, 6, 4)
        rows = _bars(day_full, 72) + _bars(day_short, 71)
        _write_gz(data.bar_path(kite, "5minute", "AAA"), rows)
        _write_gz(data.bar_path(kite, "day", "AAA"), _daily_rows(day_full, [100, 100]))
        row = audit.symbol_row(kite, "AAA")
        self.assertEqual(row["minute_sessions"], "2")
        self.assertEqual(row["unusable_sessions"], "1")
        full = data.pack_bars(_bars(day_full, 72), "5minute")["sessions"][0]
        short = data.pack_bars(_bars(day_short, 71), "5minute")["sessions"][0]
        self.assertTrue(data.session_usable(data.mask_from_starts(
            minute - 5 for minute in full["end"])))
        self.assertFalse(data.session_usable(data.mask_from_starts(
            minute - 5 for minute in short["end"])))

    def test_window_stops_before_the_holdout(self):
        root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, root)
        kite = os.path.join(root, "kite")
        start = datetime.date(2024, 12, 1)
        rows = _daily_rows(start, [10] * 40)
        rows.append({
            "datetime_start_ist": "2025-01-02 00:00:00",
            "open": 10, "high": 10, "low": 10, "close": 10, "volume": 1,
        })
        _write_gz(data.bar_path(kite, "day", "AAA"), rows)
        kept = data.load_arrays(kite, "AAA", "day", end=datetime.date(2024, 12, 31))
        self.assertTrue(kept.dates())
        self.assertTrue(all(day < data.HOLDOUT_START for day in kept.dates()))
        with self.assertRaises(data.HoldoutError):
            data.load_arrays(kite, "AAA", "day")


class RegimeTests(unittest.TestCase):
    def test_up_down_sideways_and_a_short_history(self):
        self.assertIsNone(regime.classify([100] * 219))
        up = [100] * 200 + [110] * 20
        self.assertEqual(regime.classify(up), "up")
        down = [100] * 200 + [90] * 20
        self.assertEqual(regime.classify(down), "down")
        sideways = [100] * 219 + [101]
        sideways[0] = 200
        self.assertEqual(regime.classify(sideways), "sideways")
        flat = [100] * 220
        self.assertEqual(regime.classify(flat), "sideways")

    def test_the_type_uses_only_earlier_closes(self):
        points = []
        day = datetime.date(2024, 1, 1)
        closes = [100] * 220
        for close in closes:
            points.append((day, close))
            day += datetime.timedelta(days=1)
        points.append((day, 1000))
        kinds = regime.by_date(points)
        self.assertNotIn(points[0][0], kinds)
        self.assertEqual(kinds[points[220][0]], "sideways")
        self.assertNotEqual(kinds.get(points[-1][0]), "up")


class TrendStudy(unittest.TestCase):
    def test_signal_by_1000_and_one_tick_of_slippage(self):
        day = datetime.date(2024, 6, 21)
        session = data.pack_bars(_breakout(day), "5minute")["sessions"][0]
        signal = study.nifty_signal(session)
        self.assertIsNotNone(signal)
        side, minute, _oh, _ol, _origin = signal
        self.assertEqual(side, "buy")
        self.assertEqual(minute, 9 * 60 + 50)
        trade = study.stock_trade(session, side, minute, "AAA", 2000, 500000)
        self.assertEqual(trade["outcome"], "target")
        self.assertAlmostEqual(trade["r_before"], 2.98 / 1.5, places=6)
        self.assertLess(trade["r_after"], trade["r_before"])

        late = _bars(day, 72)
        late[9]["close"] = 101
        late[9]["high"] = 101
        session = data.pack_bars(late, "5minute")["sessions"][0]
        self.assertIsNone(study.nifty_signal(session))

    def test_liquid_rank_ignores_today_and_a_break(self):
        root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, root)
        kite = os.path.join(root, "kite")
        trade = datetime.date(2024, 8, 1)
        start = trade - datetime.timedelta(days=40)
        quiet = _daily_rows(start, [10] * 41, volume=1)
        quiet[-1]["volume"] = 1000
        busy = _daily_rows(start, [10] * 41, volume=5)
        _write_gz(data.bar_path(kite, "day", "QUIET"), quiet)
        _write_gz(data.bar_path(kite, "day", "BUSY"), busy)
        books = []
        for symbol in ("QUIET", "BUSY"):
            books.append((symbol, study.book_from_series(
                data.load_arrays(kite, symbol, "day", end=trade))))
        names = study.liquid_names(trade, books, 1)
        self.assertEqual(names, ["BUSY"])

    def test_four_rules_fail_a_short_book_and_pass_a_broad_one(self):
        day = datetime.date(2024, 6, 1)
        later = datetime.date(2024, 7, 1)
        small = [{"date": day, "symbol": "AAA", "r_after": 0.2, "r_before": 0.3, "rupees": 1}]
        verdict = study.judge(small, {day})
        self.assertEqual(verdict["result"], "FAIL")
        self.assertIn("trades 1 < 100", verdict["reasons"][0])

        trades = []
        first = set()
        for i in range(60):
            one = day + datetime.timedelta(days=i)
            first.add(one)
            trades.append({"date": one, "symbol": "AAA", "r_after": 0.2, "r_before": 0.3, "rupees": 1})
        for i in range(60):
            one = later + datetime.timedelta(days=i)
            trades.append({"date": one, "symbol": "BBB", "r_after": 0.2, "r_before": 0.3, "rupees": 1})
        passed = study.judge(trades, first)
        self.assertEqual(passed["result"], "PASS")
        lines = study.format_universe(
            "Universe A, today's NIFTY 50",
            "This universe has survivorship bias: members are the current index, not the members of each past day.",
            [("overall", study.block_for(trades, [day, later]))],
            passed)
        self.assertIn("survivorship bias", "\n".join(lines))
        self.assertIn("PASS", lines[-1])

    def test_rules_are_written_before_the_results(self):
        folder = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, folder)
        path = os.path.join(folder, "EXPERIMENTS.md")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("\n".join([
                "# Experiments",
                "",
                "| 7 | 2026-11-04 | Trend-day niche (market-aligned) | rule | data | 1 | +0.1 | +0.1 | FAIL |",
                "",
                "## Forward test",
                "",
                "Started.",
                "",
            ]))
        stamp = "2026-11-06"
        study.install(path, study.rules_text(stamp), [])
        with open(path, encoding="utf-8") as fh:
            early = fh.read()
        self.assertIn("Rules fixed on 2026-11-06, before the run.", early)
        self.assertIn("at least 100 trades", early)
        self.assertIn("Results are filled in after the run.", early)
        self.assertNotIn("| 8 |", early)
        trades = []
        first = set()
        day = datetime.date(2024, 6, 1)
        for i in range(120):
            one = day + datetime.timedelta(days=i)
            if i < 60:
                first.add(one)
            trades.append({
                "date": one, "symbol": "AAA" if i < 80 else "BBB",
                "r_after": 0.2, "r_before": 0.3, "rupees": 1, "regime": "up",
            })
        regimes = {}
        for trade in trades:
            regimes[trade["date"]] = "up"
        blocks = study.report_blocks(trades, list(regimes), regimes, [2024])
        verdict = study.judge(trades, first)
        universes = [(
            "Universe A, today's NIFTY 50",
            "This universe has survivorship bias: members are the current index, not the members of each past day.",
            blocks, verdict,
        )]
        study.install(path, study.results_text(stamp, universes), study.table_rows(stamp, universes))
        with open(path, encoding="utf-8") as fh:
            later = fh.read()
        self.assertIn("Rules fixed on 2026-11-06, before the run.", later)
        self.assertNotIn("Results are filled in after the run.", later)
        self.assertIn("| 8 |", later)
        self.assertLess(later.find("## Attempt 8"), later.find("## Forward test"))

    def test_a_synthetic_folder_scores_one_trend_day(self):
        root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, root)
        kite = os.path.join(root, "kite")
        trade = datetime.date(2024, 1, 1) + datetime.timedelta(days=240)
        nifty_closes = [100 + i for i in range(241)]
        _write_gz(data.bar_path(kite, "day", "NIFTY 50"), _daily_rows(datetime.date(2024, 1, 1), nifty_closes))
        aaa_start = trade - datetime.timedelta(days=40)
        _write_gz(data.bar_path(kite, "day", "AAA"), _daily_rows(aaa_start, [50] * 41, volume=3))
        for symbol in ("NIFTY 50", "AAA"):
            rows = []
            for i in range(20, 0, -1):
                rows.extend(_bars(trade - datetime.timedelta(days=i), 1))
            rows.extend(_breakout(trade))
            _write_gz(data.bar_path(kite, "5minute", symbol), rows)
        universes = study.run(
            kite, start=trade, end=trade, members=("AAA",), liquid_count=1, log=lambda _line: None)
        self.assertEqual(len(universes), 2)
        title, note, blocks, verdict = universes[0]
        self.assertIn("survivorship bias", note)
        overall = blocks[0][1]
        self.assertEqual(overall["trend_days"], 1)
        self.assertEqual(overall["trades"], 1)
        self.assertGreater(overall["avg_before"], 0)
        self.assertEqual(verdict["result"], "FAIL")
        liquid = universes[1][2][0][1]
        self.assertEqual(liquid["trades"], 1)
