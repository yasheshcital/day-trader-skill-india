"""Hand-worked indicators and the daily signal lab. Synthetic bars only."""

import datetime
import os
import shutil
import tempfile
import unittest

from _load import load

ta = load("india/research", "ta")
lab = load("india/research", "signal_lab")
data = load("india/research", "data")


def _day(i, price, high=None, low=None, open_=None, volume=1):
    base = datetime.date(2010, 1, 1)
    return {
        "date": base + datetime.timedelta(days=i),
        "open": price if open_ is None else open_,
        "high": price if high is None else high,
        "low": price if low is None else low,
        "close": price,
        "volume": volume,
    }


def _write_daily(path, rows):
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
            writer.writerow({
                "datetime_start_ist": "%s 00:00:00" % row["date"].isoformat(),
                "open": row["open"], "high": row["high"], "low": row["low"],
                "close": row["close"], "volume": row["volume"],
            })


class Indicators(unittest.TestCase):
    def test_sma_and_ema_match_the_hand_arithmetic(self):
        self.assertIsNone(ta.sma([1, 2], 3))
        self.assertEqual(ta.sma([1, 2, 3, 4, 5], 3), 4)
        series = ta.sma_series([1, 2, 3, 4, 5], 3)
        self.assertEqual(series, [None, None, 2, 3, 4])
        ema = ta.ema_series([1, 2, 3, 4], 3)
        self.assertEqual(ema[2], 2)
        self.assertEqual(ema[3], 3)

    def test_true_range_and_wilder_atr(self):
        self.assertEqual(ta.true_range(14, 13, 10), 4)
        high = [11, 12, 15, 15]
        low = [9, 10, 13, 13]
        close = [10, 11, 13, 14]
        # TRs: bar1 max(2, 2, 0)=2, bar2 max(2, 4, 2)=4, bar3 max(2, 2, 0)=2
        atr = ta.atr_series(high, low, close, 2)
        self.assertIsNone(atr[1])
        self.assertEqual(atr[2], 3)
        self.assertEqual(atr[3], 2.5)

    def test_wilder_rsi(self):
        flat = [10, 11, 10, 11, 10, 11, 10, 11, 10, 11, 10, 11, 10, 11, 10]
        rsi = ta.rsi_series(flat, 14)
        self.assertEqual(rsi[14], 50)
        nxt = flat + [12]
        again = ta.rsi_series(nxt, 14)
        self.assertAlmostEqual(again[15], 170.0 / 3.0)
        climb = list(range(1, 17))
        self.assertEqual(ta.rsi_series(climb, 14)[14], 100)

    def test_bollinger_population_width(self):
        closes = [1] * 19 + [21]
        _mid, upper, lower, width = ta.bollinger_series(closes, 20, 2)
        std = 19 ** 0.5
        self.assertAlmostEqual(_mid[19], 2)
        self.assertAlmostEqual(upper[19], 2 + 2 * std)
        self.assertAlmostEqual(lower[19], 2 - 2 * std)
        self.assertAlmostEqual(width[19], (upper[19] - lower[19]) / 2)

    def test_prior_extremes_exclude_today(self):
        highs = ta.prior_high_series([1, 3, 2, 5, 4], 2)
        self.assertEqual(highs, [None, None, 3, 3, 5])
        lows = ta.prior_low_series([5, 1, 4, 2, 3], 2)
        self.assertEqual(lows, [None, None, 1, 1, 2])
        flags = ta.trailing_is_min([5, 4, 3, 2, 1], 3)
        self.assertEqual(flags, [False, False, True, True, True])
        self.assertFalse(ta.trailing_is_min([1, 3, 2], 3)[2])

    def test_bullish_engulfing_covers_the_prior_body(self):
        self.assertTrue(ta.bullish_engulfing(10, 8, 7, 11))
        self.assertFalse(ta.bullish_engulfing(10, 8, 9, 11))
        self.assertFalse(ta.bullish_engulfing(8, 10, 7, 11))


class ExitsAndCosts(unittest.TestCase):
    def test_delivery_costs_match_the_hand_total(self):
        pct, rupees = lab.delivery(100, 110)
        self.assertEqual(int(lab.NOTIONAL // 100), 1000)
        self.assertAlmostEqual(rupees, 9752.05254, places=4)
        self.assertAlmostEqual(pct, 9.75205254, places=4)

    def test_stop_is_first_and_a_gap_fills_at_the_open(self):
        rows = [
            _day(0, 100, high=100, low=100, open_=100),
            _day(1, 100, high=110, low=97, open_=100),
        ]
        seg = lab.segment_from_rows(rows)
        found = lab.exit_atr(seg, 1, 1, 1)
        self.assertEqual(found[1], 98)
        gap = [
            _day(0, 100, open_=100),
            _day(1, 100, high=100, low=100, open_=100),
            _day(2, 90, high=90, low=90, open_=97),
        ]
        gseg = lab.segment_from_rows(gap)
        self.assertEqual(lab.exit_atr(gseg, 1, 2, 1)[1], 97)
        through = [
            _day(0, 100, open_=100),
            _day(1, 100, high=100, low=100, open_=100),
            _day(2, 110, high=110, low=110, open_=110),
        ]
        tseg = lab.segment_from_rows(through)
        self.assertEqual(lab.exit_atr(tseg, 1, 2, 1)[1], 110)

    def test_sma_exit_is_the_next_open_and_the_time_exit_is_20_sessions(self):
        rows = []
        for i in range(25):
            rows.append(_day(i, 100, high=101, low=99, open_=100))
        rows[1]["close"] = 90
        rows[2]["open"] = 95
        seg = lab.segment_from_rows(rows)
        seg.sma20 = [100] * 25
        found = lab.exit_sma20(seg, 1, 24)
        self.assertEqual(found[0], 2)
        self.assertEqual(found[1], 95)
        held = lab.exit_hold(seg, 1, 24, 20)
        self.assertEqual(held[0], 21)
        self.assertEqual(held[1], seg.o[21])
        self.assertEqual(lab._hold(1, 21, True), 20)

    def test_a_break_closes_the_trade_at_the_segment_close(self):
        rows = []
        for i in range(26):
            rows.append(_day(i, 10, high=10, low=10, open_=10))
        rows[20]["close"] = 20
        rows[20]["high"] = 20
        seg = lab.segment_from_rows(rows[:26])
        symbol = {"name": "AAA", "segments": [seg]}
        start = rows[0]["date"]
        end = rows[-1]["date"]
        universe = {}
        for row in rows:
            universe[row["date"]] = set(["AAA"])
        slots, _months = lab._build_slots([symbol], universe, {}, 5, start, end)
        trades = lab.real_trades(slots, 1, 2)
        self.assertTrue(trades)
        self.assertEqual(trades[0]["entry"], rows[21]["open"])
        self.assertNotEqual(trades[0]["entry"], rows[20]["close"])
        self.assertEqual(trades[0]["fill"], rows[-1]["close"])


class UniverseAndBaseline(unittest.TestCase):
    def test_turnover_uses_earlier_sessions_and_stops_at_a_break(self):
        days = [datetime.date(2010, 1, 1) + datetime.timedelta(days=i) for i in range(4)]
        book = lab.Turnover(days, [10, 10, 10, 1000], [0, 0, 0, 0], 3)
        self.assertEqual(book.average_before(days[3]), 10)
        broken = lab.Turnover(days, [10, 10, 10, 10], [0, 0, 1, 1], 3)
        self.assertIsNone(broken.average_before(days[3]))
        names = lab.liquid_names(days[3], [("QUIET", book), ("BUSY", lab.Turnover(
            days, [50, 50, 50, 1], [0, 0, 0, 0], 3))], 1)
        self.assertEqual(names, ["BUSY"])

    def test_warmup_and_one_open_trade(self):
        self.assertEqual(lab.WARMUP, 250)
        self.assertEqual(lab.UNIVERSE_N, 200)
        self.assertEqual(lab.RANDOM_RUNS, 100)
        self.assertEqual(lab.take_one_at_a_time([(0, 5), (3, 6), (6, 8)]), [0, 6])
        rows = [_day(i, 10) for i in range(30)]
        rows[20]["close"] = 20
        rows[20]["high"] = 20
        seg = lab.segment_from_rows(rows)
        symbol = {"name": "AAA", "segments": [seg]}
        universe = dict((row["date"], set(["AAA"])) for row in rows)
        slots, _months = lab._build_slots(
            [symbol], universe, {}, 250, rows[0]["date"], rows[-1]["date"])
        self.assertEqual(slots, [])

    def test_random_entries_stay_in_the_month_and_repeat(self):
        march = datetime.date(2010, 3, 10)
        april = datetime.date(2010, 4, 10)
        def slot(day, pct):
            outcome = {
                "pct": pct, "rupees": pct, "hold": 1, "exit_i": 2,
                "exit_date": day, "entry": 10, "fill": 11,
            }
            return {
                "outcomes": [outcome, outcome, outcome],
                "entry_date": day, "regime": "up", "entry_i": 1, "sym": 0, "seg": 0,
            }
        slots = [slot(march, 5), slot(april, -40)]
        trade = {"entry_date": march, "pct": 5}
        pools = {(2010, 3): [0], (2010, 4): [1]}
        import random
        first = lab.random_average([trade], pools, slots, 0, random.Random(1))
        second = lab.random_average([trade], pools, slots, 0, random.Random(1))
        self.assertEqual(first, 5)
        self.assertEqual(second, 5)

    def test_pass_mark_and_the_rules_are_written_first(self):
        good = {
            "trades": 300, "avg": 0.2, "beats": 95, "years": 14,
            "up": 0.1, "down": 0.1, "sideways": 0.1,
        }
        self.assertEqual(lab.judge(good)["result"], "PASS")
        bad = dict(good)
        bad["beats"] = 94
        self.assertEqual(lab.judge(bad)["result"], "FAIL")
        folder = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, folder)
        path = os.path.join(folder, "EXPERIMENTS.md")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("\n".join([
                "# Experiments",
                "",
                "| 8 | 2026-11-06 | The same rule is profitable after costs on 2015-2024 in the liquid book. | r | d | 1 | +0.1 | +0.1 | FAIL |",
                "",
                "## Forward test",
                "",
                "Started.",
                "",
            ]))
        lab.install(path, lab.rules_text("2026-11-06"), [])
        with open(path, encoding="utf-8") as fh:
            early = fh.read()
        self.assertIn("Rules fixed on 2026-11-06, before the run.", early)
        self.assertIn("at least 95 of 100", early)
        self.assertIn("Results are filled in after the run.", early)
        self.assertNotIn("| 9 |", early)
        row = {
            "name": "20d-high / hold-20", "entry": "20d-high", "exit": "hold-20",
            "trades": 10, "win_rate": 0.5, "avg": 1.0, "hold": 4,
            "beats": 10, "random_median": 0.0, "random_p95": 0.5,
            "years": 1, "up": 1.0, "down": -1.0, "sideways": None,
            "verdict": lab.judge(bad),
        }
        lab.install(path, lab.results_text("2026-11-06", [row]), lab.table_rows("2026-11-06", [row]))
        with open(path, encoding="utf-8") as fh:
            later = fh.read()
        self.assertNotIn("Results are filled in after the run.", later)
        self.assertIn("| 9 |", later)
        self.assertLess(later.find("## Attempt 9"), later.find("## Forward test"))

    def test_loader_stops_at_the_window_and_does_not_open_the_holdout(self):
        root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, root)
        kite = os.path.join(root, "kite")
        rows = []
        start = datetime.date(2024, 11, 1)
        for i in range(40):
            day = start + datetime.timedelta(days=i)
            rows.append({
                "date": day, "open": 10, "high": 10, "low": 10, "close": 10, "volume": 1,
            })
        rows.append({
            "date": datetime.date(2025, 1, 2),
            "open": 99, "high": 99, "low": 99, "close": 99, "volume": 1,
        })
        _write_daily(data.bar_path(kite, "day", "AAA"), rows)
        segments = lab.load_symbol(kite, "AAA", end=datetime.date(2024, 12, 31))
        dates = []
        for seg in segments:
            dates.extend(seg.date)
        self.assertTrue(dates)
        self.assertTrue(all(day < data.HOLDOUT_START for day in dates))
        self.assertNotIn(99, [seg.c[-1] for seg in segments])
