"""Attempt 15 checks on the RSI(2) pass. Synthetic only."""

import datetime
import inspect
import os
import tempfile
import shutil
import unittest

from _load import load

v = load("india/research", "verify")
f = load("india/research", "follow")
lab = load("india/research", "signal_lab")


class Seg(object):
    def __init__(self, n, start):
        self.date = [start + datetime.timedelta(days=i) for i in range(n)]
        self.o = [100.0] * n
        self.h = [101.0] * n
        self.l = [99.0] * n
        self.c = [100.0] * n
        self.v = [1000.0] * n
        self.sma5 = [None] * n
        self.sma10 = [None] * n
        self.sma100 = [None] * n
        self.sma200 = [None] * n
        self.rsi2 = [None] * n
        self.rsi3 = [None] * n
        self.idx = {}
        for i, day in enumerate(self.date):
            self.idx[day] = i


def _nifty(seg, close=100.0):
    out = {}
    for day in seg.date:
        out[day] = {"open": 100.0, "close": close}
    return out


def _passing():
    return {"name": "rsi2 < 5", "verdict": {"result": "PASS", "reasons": []}}


class IndexAndSignal(unittest.TestCase):
    def test_scan_uses_the_attempt_14_rule_and_2025_stays_out(self):
        seg = Seg(8, datetime.date(2016, 1, 4))
        seg.c[0] = 50.0
        seg.sma200[0] = 40.0
        seg.rsi2[0] = 4.0
        seg.o[1] = 100.0
        seg.o[6] = 110.0
        nifty = _nifty(seg)
        spec = v.rsi_specs()[0]
        found = v.collect_index("NIFTY TEST", [seg], nifty, [spec])
        trades = found[spec["name"]]
        self.assertEqual(len(trades), 1)
        self.assertAlmostEqual(trades[0]["ret"], f.net_return(100.0, 110.0))
        self.assertEqual(trades[0]["date"], seg.date[1])
        later = Seg(8, datetime.date(2025, 1, 2))
        later.c[0] = 50.0
        later.sma200[0] = 40.0
        later.rsi2[0] = 4.0
        later.o[6] = 110.0
        empty = v.collect_index("NIFTY TEST", [later], _nifty(later), [spec])
        self.assertEqual(empty[spec["name"]], [])
        top = {later.date[0]: set(["NIFTY TEST"])}
        trades, orders = v.holdout_trades(
            "NIFTY TEST", [later], top, _nifty(later), v.HOLDOUT, datetime.date(2025, 12, 31))
        self.assertEqual(len(trades), 1)
        self.assertEqual(len(orders), 1)
        self.assertEqual(orders[0]["entry"], 100.0)
        self.assertGreater(orders[0]["entry_date"], datetime.date(2024, 12, 31))

    def test_boundaries_neighbours_and_slippage(self):
        seg = Seg(3, datetime.date(2016, 1, 4))
        seg.c[1] = 60.0
        seg.sma200[1] = 50.0
        seg.rsi2[1] = 10.0
        base = {"rsi_max": 10.0, "down2": False, "rsi": "rsi2", "sma": "sma200"}
        self.assertFalse(v.signal_fires(seg, 1, base))
        seg.rsi2[1] = 9.9
        self.assertTrue(v.signal_fires(seg, 1, base))
        self.assertTrue(f.rsi_fires(seg, 1, 10.0, False))
        seg.rsi3[1] = 10.0
        neighbour = {"rsi_max": 10.0, "down2": False, "rsi": "rsi3", "sma": "sma200"}
        self.assertFalse(v.signal_fires(seg, 1, neighbour))
        seg.rsi3[1] = 9.0
        self.assertTrue(v.signal_fires(seg, 1, neighbour))
        seg.sma100[1] = 70.0
        seg.sma200[1] = 40.0
        filtered = {"rsi_max": 10.0, "down2": False, "rsi": "rsi2", "sma": "sma100"}
        self.assertFalse(v.signal_fires(seg, 1, filtered))
        longer = Seg(8, datetime.date(2016, 1, 4))
        longer.sma10[0] = 90.0
        longer.c[0] = 95.0
        longer.o[1] = 97.0
        found = f.exit_rule(longer, 0, f.RSI_LIMIT, v.exit_hit("sma10"))
        self.assertEqual(found[0], 1)
        self.assertEqual(found[1], 97.0)
        plain = f.net_return(100.0, 110.0)
        worse = f.net_return(*v.slipped(100.0, 110.0, v.SLIP))
        self.assertLess(worse, plain)
        seg.o[0] = 100.0
        seg.c[0] = 104.0
        self.assertEqual(v.bar_px(seg, 0, "c"), 104.0)
        self.assertEqual(v.bar_px(seg, 0, "o"), 100.0)

    def test_pooled_mark_and_the_part_needs_every_variant(self):
        self.assertEqual(v.judge_pooled(0.2, 2.01, 2, 3)["result"], "PASS")
        self.assertEqual(v.judge_pooled(0.2, 2.0, 2, 3)["result"], "FAIL")
        self.assertEqual(v.judge_pooled(0.0, 3.0, 2, 3)["result"], "FAIL")
        self.assertEqual(v.judge_pooled(0.2, 3.0, 1, 3)["result"], "FAIL")
        self.assertEqual(v.judge_pooled(0.2, 3.0, 4, 6)["result"], "PASS")
        passed = _passing()
        failed = {"name": "rsi2 < 10", "verdict": {"result": "FAIL", "reasons": ["t"]}}
        self.assertEqual(v.part_verdict([passed, passed, passed])["result"], "PASS")
        self.assertEqual(v.part_verdict([passed, failed, passed])["result"], "FAIL")
        jan = datetime.date(2016, 1, 4)
        feb = datetime.date(2016, 2, 4)
        stats = v.trade_stats([
            {"date": jan, "ret": 1.0, "mkt": 0.0, "month": (2016, 1)},
            {"date": jan, "ret": 3.0, "mkt": 0.0, "month": (2016, 1)},
            {"date": feb, "ret": 2.0, "mkt": 0.0, "month": (2016, 2)},
        ])
        self.assertAlmostEqual(stats["avg"], 2.0)
        self.assertGreater(stats["t"], 2.0)
        hold = v.judge_holdout(0.1, 2.01)
        self.assertEqual(hold["result"], "PASS")
        self.assertEqual(v.judge_holdout(0.1, 2.0)["result"], "FAIL")
        self.assertNotIn("survivorship", " ".join(hold["reasons"]))


class BookAndWindows(unittest.TestCase):
    def test_lowest_rsi_then_turnover_fills_the_free_slots(self):
        orders = [
            {"name": "BBB", "rsi": 5.0, "turnover": 10.0},
            {"name": "AAA", "rsi": 5.0, "turnover": 50.0},
            {"name": "CCC", "rsi": 1.0, "turnover": 1.0},
        ]
        held = set(["ZZZ"])
        chosen = v.take_slots(orders, 2, held)
        self.assertEqual([item["name"] for item in chosen], ["CCC", "AAA"])
        self.assertEqual(held, set(["ZZZ"]))
        only = v.take_slots(orders, 1, set(["CCC"]))
        self.assertEqual([item["name"] for item in only], ["AAA"])

    def test_cash_earns_nifty_or_nothing_and_the_lower_rsi_is_bought(self):
        d0 = datetime.date(2016, 1, 4)
        d1 = datetime.date(2016, 1, 14)
        seg = Seg(2, d0)
        seg.o = [100.0, 110.0]
        seg.c = [100.0, 110.0]
        nifty = {
            d0: {"open": 100.0, "close": 100.0},
            d1: {"open": 100.0, "close": 200.0},
        }
        calendar = [d0, d1]
        quiet = v.simulate_book([], calendar, nifty, False, capital=100000.0, slots=1)
        parked = v.simulate_book([], calendar, nifty, True, capital=100000.0, slots=1)
        self.assertAlmostEqual(quiet["cagr"], 0.0)
        self.assertEqual(quiet["invested"], 0.0)
        self.assertGreater(parked["cagr"], 0.0)
        self.assertEqual(parked["invested"], 0.0)
        orders = [
            {"name": "HIGH", "rsi": 9.0, "turnover": 5.0, "entry_date": d0, "exit_date": d1,
             "entry": 100.0, "fill": 110.0, "at_open": True, "seg": seg},
            {"name": "LOW", "rsi": 1.0, "turnover": 1.0, "entry_date": d0, "exit_date": d1,
             "entry": 100.0, "fill": 110.0, "at_open": True, "seg": seg},
        ]
        book = v.simulate_book(orders, calendar, nifty, False, capital=1000000.0, slots=1)
        self.assertEqual(book["bought"], ["LOW"])
        self.assertEqual(book["entries"], 1)
        self.assertGreater(book["invested"], 0.0)

    def test_index_names_and_the_locked_calls(self):
        folder = tempfile.mkdtemp(prefix="step21-")
        self.addCleanup(lambda: shutil.rmtree(folder))
        day = os.path.join(folder, "day")
        os.makedirs(day)
        for name in ("AAA.csv.gz", "NIFTY BANK.csv.gz", "NIFTY.part.csv.gz"):
            open(os.path.join(day, name), "wb").close()
        self.assertEqual(v.index_names(folder), ["NIFTY BANK"])
        self.assertNotIn("final=True", inspect.getsource(v.run_indices))
        self.assertIn("final=False", inspect.getsource(v.run_indices))
        self.assertEqual(inspect.getsource(v.run_holdout).count("final=True)"), 1)
        rules = v.rules_text("2026-11-07")
        self.assertIn("at least 2/3", rules)
        self.assertIn("above 2", rules)
        self.assertNotIn("\u2014", rules)
        self.assertIn("No pass mark", rules)
        plain = lab.delivery(100.0, 110.0)
        self.assertAlmostEqual(f.net_return(100.0, 110.0), plain[0])


class Install(unittest.TestCase):
    def test_rules_land_before_results_and_do_not_eat_the_forward_test(self):
        folder = tempfile.mkdtemp(prefix="step21-exp-")
        self.addCleanup(lambda: shutil.rmtree(folder))
        path = os.path.join(folder, "EXPERIMENTS.md")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("\n".join([
                "| 14 | 2026-11-07 | rsi2 < 5 clears the attempt 14 swing pass mark. | rule | data | 1 | +0.568% | +21.37 | PASS |",
                "",
                "## Attempt 14",
                "",
                "Variants that pass: 3 of 12.",
                "",
                "hypothesis found in attempt 12 data (gap GO 3 lost to random same-day entries); must clear the full pass mark.",
                "",
                "## Forward test",
                "",
                "Started 2026-11-04.",
                "",
            ]))
        stamp = "2026-11-07"
        f.install_attempt(path, 15, v.rules_text(stamp), [])
        with open(path, encoding="utf-8") as fh:
            early = fh.read()
        self.assertLess(early.find("## Attempt 14"), early.find("## Attempt 15"))
        self.assertLess(early.find("## Attempt 15"), early.find("## Forward test"))
        self.assertNotIn("| 15 |", early)
        self.assertIn("at least 2/3", early)
        hold = {
            "last": datetime.date(2026, 11, 4),
            "trades": 3,
            "avg": 0.2,
            "t": 2.5,
            "verdict": {"result": "PASS", "reasons": []},
        }
        block = {
            "name": "rsi2 < 5",
            "trades": 10,
            "avg": 0.4,
            "t": 3.0,
            "positive": 8,
            "indices": 9,
            "verdict": {"result": "PASS", "reasons": []},
            "rows": [],
            "excess": 0.1,
        }
        rows = v.table_rows(stamp, [block], hold)
        f.install_attempt(path, 15, v.rules_text(stamp) + "\n\nResults.\n", rows)
        f.install_attempt(path, 15, v.rules_text(stamp) + "\n\nResults.\n", rows)
        with open(path, encoding="utf-8") as fh:
            later = fh.read()
        self.assertEqual(later.count("## Attempt 15"), 1)
        self.assertEqual(later.count("| 15 |"), 4)
        self.assertIn("## Forward test", later)
        self.assertIn("hypothesis found in attempt 12 data", later)
        self.assertLess(later.find("## Attempt 15"), later.find("## Forward test"))
        self.assertNotIn("\u2014", later)


if __name__ == "__main__":
    unittest.main()
