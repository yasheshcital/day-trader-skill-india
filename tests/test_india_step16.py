"""Robustness of the attempt-9 signals. Synthetic bars only."""

import datetime
import os
import random
import shutil
import tempfile
import unittest

from _load import load

lab = load("india/research", "signal_lab")
rob = load("india/research", "robustness")
data = load("india/research", "data")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


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


def _passing_block():
    return {
        "name": "20d-high / sma20-close",
        "trades": 10,
        "pairs": 10,
        "months": 4,
        "excess": 0.4,
        "t": 3.0,
        "early": 0.2,
        "early_t": 1.0,
        "early_pairs": 4,
        "late": 0.5,
        "late_t": 2.5,
        "late_pairs": 6,
        "neighbours": [],
        "neighbours_n": 4,
        "neighbours_pass": 3,
        "large_excess": 0.1,
        "large_t": 1.2,
        "large_trades": 5,
        "large_pairs": 5,
        "cagr": 12.0,
        "max_dd": -30.0,
        "worst_year": -8.0,
        "verdict": {"result": "PASS", "reasons": []},
    }


class Attempt9Row(unittest.TestCase):
    def test_the_table_row_names_both_passers(self):
        path = os.path.join(ROOT, "india", "EXPERIMENTS.md")
        row = None
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                if line.startswith("| 9 |"):
                    row = line
                    break
        self.assertIsNotNone(row)
        self.assertIn("20d-high / sma20-close", row)
        self.assertIn("engulf-low / hold-20", row)
        self.assertIn("+1.574%", row)
        self.assertIn("+1.176%", row)
        self.assertIn("17,461", row)
        self.assertIn("2,337", row)
        self.assertNotIn("1.729", row)
        self.assertNotIn("bb-squeeze", row)


class ExcessAndJudge(unittest.TestCase):
    def test_monthly_t_matches_the_hand_arithmetic(self):
        jan = (2010, 1)
        feb = (2010, 2)
        mar = (2010, 3)
        pairs = [(jan, 1.0), (jan, 3.0), (feb, 2.0), (feb, 2.0), (mar, 5.0)]
        stats = rob.cluster_stats(pairs)
        self.assertAlmostEqual(stats["excess"], 2.6)
        self.assertAlmostEqual(stats["t"], 3.0)
        self.assertEqual(stats["months"], 3)
        early, late = rob.split_decades([
            ((2014, 12), 1.5),
            ((2015, 1), -0.5),
        ])
        self.assertAlmostEqual(early["excess"], 1.5)
        self.assertAlmostEqual(late["excess"], -0.5)
        self.assertIsNone(early["t"])

    def test_pass_mark_and_each_miss(self):
        nifty = {"cagr": 10.0, "max_dd": -40.0}
        good = {
            "t": 2.5, "early": 0.1, "late": 0.1,
            "neighbours_pass": 2, "neighbours_n": 4,
            "large_excess": 0.2, "cagr": 13.0, "max_dd": -50.0,
        }
        self.assertEqual(rob.judge(good, nifty)["result"], "PASS")
        exact = dict(good)
        exact["cagr"] = 13.0
        exact["max_dd"] = -50.0
        self.assertEqual(rob.judge(exact, nifty)["result"], "PASS")
        tight = dict(good)
        tight["t"] = 2.0
        self.assertIn("excess t", rob.judge(tight, nifty)["reasons"][0])
        early = dict(good)
        early["early"] = 0.0
        self.assertIn("2005-2014", rob.judge(early, nifty)["reasons"][0])
        late = dict(good)
        late["late"] = -0.1
        self.assertIn("2015-2024", rob.judge(late, nifty)["reasons"][0])
        neigh = dict(good)
        neigh["neighbours_pass"] = 1
        self.assertIn("neighbours 1 of 4, need 2", "; ".join(rob.judge(neigh, nifty)["reasons"]))
        large = dict(good)
        large["large_excess"] = -0.01
        self.assertIn("large-cap", "; ".join(rob.judge(large, nifty)["reasons"]))
        cagr = dict(good)
        cagr["cagr"] = 12.9
        self.assertIn("CAGR", "; ".join(rob.judge(cagr, nifty)["reasons"]))
        dd = dict(good)
        dd["max_dd"] = -50.1
        self.assertIn("max drawdown", "; ".join(rob.judge(dd, nifty)["reasons"]))

    def test_neighbours_are_one_change_and_the_bar_is_two(self):
        found = rob.candidates()
        self.assertEqual([len(item["neighbours"]) for item in found], [4, 4, 4, 2])
        self.assertEqual(rob.NEIGHBOUR_NEED, 2)
        self.assertEqual(found[3]["neighbours"][0]["touch_n"], 10)
        self.assertEqual(found[3]["neighbours"][0]["exit_n"], 10)
        self.assertEqual(found[3]["neighbours"][1]["touch_n"], 50)
        self.assertTrue(rob.neighbour_ok({"excess": 0.1, "t": 2.01}))
        self.assertFalse(rob.neighbour_ok({"excess": 0.1, "t": 2.0}))
        self.assertFalse(rob.neighbour_ok({"excess": 0.0, "t": 3.0}))

    def test_a_matched_pair_repeats_and_nets_to_zero_when_both_match(self):
        rows = [_day(i, 100) for i in range(5)]
        seg = lab.segment_from_rows(rows)
        loaded = [{"name": "AAA", "segments": [seg]}]
        spec = rob.candidates()[0]["base"]
        trade = {
            "pct": lab.delivery(100, 100)[0],
            "entry_date": seg.date[1],
            "exit_date": seg.date[-1],
            "at_open": False,
            "month": (seg.date[1].year, seg.date[1].month),
        }
        nifty = {}
        for i, day in enumerate(seg.date):
            nifty[day] = {"open": 100.0, "close": 100.0, "seg": 0}
        pools = {trade["month"]: [(0, 0, 1)]}
        cache = {}
        first = rob.build_pairs([trade], pools, loaded, spec, nifty, cache, random.Random(1))
        second = rob.build_pairs([trade], pools, loaded, spec, nifty, cache, random.Random(1))
        self.assertEqual(len(first), 1)
        self.assertAlmostEqual(first[0][1], 0.0, places=6)
        self.assertEqual(first, second)


class Portfolio(unittest.TestCase):
    def test_curve_cagr_drawdown_and_worst_year(self):
        start = datetime.date(2005, 1, 1)
        end = datetime.date(2015, 1, 1)
        stats = rob.curve_stats([start, end], [100.0, 200.0], 100.0)
        years = (end - start).days / 365.25
        expected = (2.0 ** (1.0 / years) - 1.0) * 100.0
        self.assertAlmostEqual(stats["cagr"], expected, places=6)
        self.assertGreater(stats["cagr"], 7.0)
        self.assertLess(stats["cagr"], 7.3)
        dipped = rob.curve_stats(
            [datetime.date(2010, 1, 1), datetime.date(2010, 6, 1), datetime.date(2010, 12, 1)],
            [100.0, 50.0, 80.0], 100.0)
        self.assertAlmostEqual(dipped["max_dd"], -50.0)
        self.assertAlmostEqual(dipped["worst_year"], -20.0)
        years_ = [
            datetime.date(2005, 6, 1),
            datetime.date(2006, 6, 1),
            datetime.date(2007, 6, 1),
        ]
        worst = rob.curve_stats(years_, [100.0, 50.0, 80.0], 100.0)
        self.assertAlmostEqual(worst["worst_year"], -50.0)

    def test_nifty_buy_hold_is_the_price_change(self):
        start = datetime.date(2005, 1, 3)
        mid = datetime.date(2006, 1, 3)
        end = datetime.date(2007, 1, 3)
        nifty = {
            start: {"open": 100.0, "close": 100.0, "seg": 0},
            mid: {"open": 150.0, "close": 150.0, "seg": 0},
            end: {"open": 75.0, "close": 75.0, "seg": 0},
        }
        stats = rob.nifty_buy_hold([start, mid, end], nifty, 100.0)
        self.assertAlmostEqual(stats["max_dd"], -50.0)
        self.assertAlmostEqual(stats["final"], 75.0)

    def test_highest_turnover_gets_the_slot_and_cash_earns_nothing(self):
        rows = [_day(i, 100, open_=100) for i in range(3)]
        seg = lab.segment_from_rows(rows)
        rob.prepare(seg)
        calendar = list(seg.date)

        def trade(name, turnover):
            return {
                "name": name,
                "seg": seg,
                "entry_date": seg.date[0],
                "exit_date": seg.date[1],
                "entry": 100.0,
                "fill": 110.0,
                "at_open": True,
                "turnover": turnover,
            }

        idle = rob.simulate([], calendar, capital=100000.0, slots=1, notional=100000.0)
        self.assertAlmostEqual(idle["final"], 100000.0)
        self.assertAlmostEqual(idle["cagr"], 0.0)
        self.assertEqual(idle["taken"], [])
        picked = rob.simulate(
            [trade("AAA", 5.0), trade("BBB", 9.0)],
            calendar, capital=100000.0, slots=1, notional=100000.0)
        self.assertEqual(picked["taken"], ["BBB"])
        net = lab.delivery(100.0, 110.0)[1]
        self.assertAlmostEqual(picked["final"], 100000.0 + net, places=4)
        tie = rob.simulate(
            [trade("BBB", 4.0), trade("AAA", 4.0)],
            calendar, capital=100000.0, slots=1, notional=100000.0)
        self.assertEqual(tie["taken"], ["AAA"])


class SignalsAndRules(unittest.TestCase):
    def test_entry_is_the_next_open_and_matches_the_base_signal(self):
        rows = [_day(i, 10, high=10, low=10, open_=10) for i in range(25)]
        rows[20]["close"] = 20
        rows[20]["high"] = 20
        rows[21]["open"] = 11
        seg = lab.segment_from_rows(rows)
        spec = rob.candidates()[0]["base"]
        for i in range(len(seg.c)):
            self.assertEqual(rob.signal_fires(seg, i, spec), lab.entry_hit(seg, i, "20d-high"))
        symbol = {"name": "AAA", "segments": [seg]}
        universe = dict((row["date"], set(["AAA"])) for row in rows)
        _pools, thinned, raw = rob.scan(
            [symbol], universe, [spec], 5, rows[0]["date"], rows[-1]["date"])
        self.assertEqual(len(thinned[0]), 1)
        self.assertEqual(thinned[0][0]["entry"], 11)
        self.assertNotEqual(thinned[0][0]["entry"], 20)
        self.assertTrue(raw[0])

    def test_rules_are_written_before_the_results(self):
        text = rob.rules_text("2026-11-06")
        self.assertIn("Rules fixed on 2026-11-06, before the run.", text)
        self.assertIn("Results are filled in after the run.", text)
        self.assertIn("excess t", text)
        self.assertIn("both decades", text)
        self.assertIn("At least 2 neighbours", text)
        self.assertIn("top 100", text)
        self.assertIn("plus 3", text)
        self.assertIn("10 percentage points", text)
        self.assertIn("Dividends are excluded", text)
        self.assertNotIn("\u2014", text)
        folder = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, folder)
        path = os.path.join(folder, "EXPERIMENTS.md")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("\n".join([
                "| 9 | 2026-11-06 | two passers | r | d | 1 | +1.574% | +1.176% | PASS |",
                "",
                "## Forward test",
                "",
                "Started.",
                "",
            ]))
        rob.install(path, rob.rules_text("2026-11-06"), [])
        with open(path, encoding="utf-8") as fh:
            early = fh.read()
        self.assertIn("Results are filled in after the run.", early)
        self.assertNotIn("| 10 |", early)
        self.assertIn("| 9 |", early)
        block = _passing_block()
        nifty = {"cagr": 8.0, "max_dd": -40.0, "worst_year": -20.0}
        rob.install(path, rob.results_text("2026-11-06", [block], nifty), rob.table_rows("2026-11-06", [block]))
        with open(path, encoding="utf-8") as fh:
            later = fh.read()
        self.assertNotIn("Results are filled in after the run.", later)
        self.assertIn("| 10 |", later)
        self.assertIn("| 9 |", later)
        self.assertLess(later.find("## Attempt 10"), later.find("## Forward test"))
        self.assertIn("20d-high / sma20-close", later)

    def test_loader_stops_before_the_holdout(self):
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
        _write_daily(data.bar_path(kite, "day", "NIFTY 50"), rows)
        loaded, _books, nifty = rob.load_market(kite, datetime.date(2024, 12, 31), log=lambda line: None)
        names = [symbol["name"] for symbol in loaded]
        self.assertNotIn("NIFTY 50", names)
        dates = []
        for symbol in loaded:
            for seg in symbol["segments"]:
                dates.extend(seg.date)
        self.assertTrue(dates)
        self.assertTrue(all(day < data.HOLDOUT_START for day in dates))
        self.assertTrue(all(day < data.HOLDOUT_START for day in nifty))
        self.assertNotIn(99, [seg.c[-1] for symbol in loaded for seg in symbol["segments"]])
