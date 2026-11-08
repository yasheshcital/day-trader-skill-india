"""Attempt 17 checks. Synthetic only."""

import datetime
import os
import shutil
import tempfile
import unittest

from _load import load

b = load("india/research", "batch17")
f = load("india/research", "follow")


class MapAndSignal(unittest.TestCase):
    def test_sector_map_skips_an_industry_with_no_near_index(self):
        self.assertEqual(b.sector_for("Power"), "NIFTY ENERGY")
        self.assertEqual(b.sector_for("Financial Services"), "NIFTY FIN SERVICE")
        self.assertEqual(b.sector_for("Healthcare"), "NIFTY HEALTHCARE")
        self.assertIsNone(b.sector_for("Chemicals"))
        self.assertIsNone(b.sector_for("Capital Goods"))
        self.assertIsNone(b.sector_for(""))
        self.assertIsNone(b.sector_for(None))

    def test_relative_rsi_restarts_when_the_sector_is_missing(self):
        seg = type("Seg", (), {})()
        seg.date = [datetime.date(2020, 1, d) for d in range(1, 8)]
        seg.c = [10.0, 10.0, 10.0, 5.0, 10.0, 10.0, 10.0]
        sector = {seg.date[i]: 10.0 for i in range(7)}
        del sector[seg.date[3]]
        out = b.relative_rsi(seg, sector)
        self.assertIsNone(out[0])
        self.assertIsNone(out[1])
        self.assertIsNotNone(out[2])
        self.assertIsNone(out[3])
        self.assertIsNone(out[4])
        self.assertIsNone(out[5])
        self.assertIsNotNone(out[6])

    def test_signal_boundaries(self):
        seg = type("Seg", (), {})()
        seg.c = [101.0]
        seg.sma200 = [100.0]
        seg.rel_rsi = [4.9]
        seg.rsi2 = [9.9]
        self.assertTrue(b.rel_fires(seg, 0, 5.0, None))
        seg.rel_rsi = [5.0]
        self.assertFalse(b.rel_fires(seg, 0, 5.0, None))
        seg.rel_rsi = [4.9]
        seg.c = [100.0]
        self.assertFalse(b.rel_fires(seg, 0, 5.0, None))
        seg.c = [101.0]
        seg.rsi2 = [10.0]
        self.assertFalse(b.rel_fires(seg, 0, 5.0, 10.0))
        seg.rsi2 = [9.9]
        self.assertTrue(b.rel_fires(seg, 0, 5.0, 10.0))

    def test_picks_and_a_five_session_turn_window(self):
        self.assertEqual(b.pick_high([(3.0, "CCC"), (3.0, "AAA"), (1.0, "BBB")], 2), ["AAA", "CCC"])
        self.assertEqual(b.pick_low([(3.0, "CCC"), (3.0, "AAA"), (1.0, "BBB")], 2), ["BBB", "AAA"])
        self.assertEqual(
            [item[1] for item in b.choose_two([(0.2, "BBB"), (0.2, "AAA"), (0.1, "CCC")])],
            ["AAA", "BBB"])
        self.assertEqual(b.choose_two([(0.2, "AAA")]), [])
        closes = [1.0] * 20 + [2.0]
        self.assertAlmostEqual(b.session_return(closes, 20, 20), 1.0)
        self.assertIsNone(b.session_return(closes, 19, 20))

        def month(year, mon):
            days = []
            day = datetime.date(year, mon, 1)
            while day.month == mon:
                if day.weekday() < 5:
                    days.append(day)
                day += datetime.timedelta(days=1)
            return days

        january = month(2016, 1)
        february = month(2016, 2)
        calendar = january + february
        nifty = {}
        for day in calendar:
            nifty[day] = {"open": 100.0, "close": 100.0}
        windows = b.tom_windows(calendar, nifty)
        self.assertEqual(windows[0][0], january[-2])
        self.assertEqual(windows[0][1], february[2])
        self.assertEqual(calendar.index(windows[0][1]) - calendar.index(windows[0][0]), 4)

    def test_basket_drops_a_missing_leg(self):
        one = b.basket_return([(100.0, 110.0), None])
        both = b.basket_return([(100.0, 110.0), (100.0, 110.0)])
        self.assertAlmostEqual(one, both)
        self.assertIsNone(b.basket_return([None, None]))


class Marks(unittest.TestCase):
    def _block(self, name, tstat, family):
        return {
            "name": name,
            "family": family,
            "avg": 0.2,
            "t": tstat,
            "early": 0.1,
            "late": 0.1,
            "up": 0.1,
            "down": 0.1,
            "sideways": 0.1,
            "verdict": {"result": "PASS", "reasons": []},
        }

    def test_week_judge_and_the_holdout_plan(self):
        good = self._block("sector 4w", 3.1, "sector rotation")
        also = self._block("sector 8w", 3.1, "sector rotation")
        thin = self._block("sector 13w", 2.1, "sector rotation")
        self.assertEqual(b.judge_weeks(good, [good, also, thin])["result"], "PASS")
        exact = self._block("sector 4w", 3.0, "sector rotation")
        self.assertEqual(b.judge_weeks(exact, [exact, also, thin])["result"], "FAIL")
        self.assertNotIn("large", " ".join(b.judge_weeks(good, [good, also, thin])["reasons"]))
        used = {"rsi2": "yes", "sector-relative rsi": "no", "turn of the month": "no"}
        passed = self._block("old", 4.0, "rsi2")
        fresh = self._block("rel rsi5", 4.0, "sector-relative rsi")
        run, waiting = b.holdout_plan([passed, fresh], used)
        self.assertEqual([item["name"] for item in run], ["rel rsi5"])
        self.assertEqual([item["name"] for item in waiting], ["old"])
        called = []

        def boom(*args, **kwargs):
            called.append(1)
            raise AssertionError("holdout opened")

        real = b.h.load_context
        b.h.load_context = boom
        try:
            out = b.run_holdout("data/kite", [passed], {}, 0, lambda line: None, used)
        finally:
            b.h.load_context = real
        self.assertEqual(called, [])
        self.assertEqual(out, [])
        self.assertEqual(passed["mark"], "needs new data")

    def test_catalogue_keeps_sources_and_moves_tom(self):
        folder = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, folder)
        path = os.path.join(folder, "STRATEGIES.md")
        flags = dict(b.FAMILY_USED)
        b.update_catalogue(path, [], flags)
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        self.assertIn("opening-range breakout", text)
        self.assertIn("| Family | Holdout used |", text)
        self.assertIn("| momentum | yes |", text)
        self.assertIn("| rsi2 | yes |", text)
        self.assertIn("| sector rotation | no |", text)
        self.assertIn("one holdout look", text)
        near = text.split("## Near-miss")[1].split("## Closed")[0]
        closed = text.split("## Closed")[1].split("## Sources")[0]
        self.assertIn("tom (turn of the month)", near)
        self.assertNotIn("| tom |", closed)
        line = [row for row in text.splitlines() if row.startswith("| Turtle breakout |")][0]
        self.assertIn("| 11 |", line)
        faber = [row for row in text.splitlines() if "Faber 10-month" in row][0]
        self.assertIn("full TSMOM not started", faber)
        passed = {
            "name": "rel rsi5",
            "attempt": 17,
            "in_sample": "PASS",
            "holdout": {"avg": 0.4, "t": 3.0},
            "note": "PASS Holdout PASS, avg +0.400%, t +3.00.",
        }
        b.update_catalogue(path, [passed], flags)
        with open(path, encoding="utf-8") as fh:
            later = fh.read()
        self.assertIn("rel rsi5", later.split("## Watch")[0])
        waiting = {
            "name": "rsi2 again",
            "attempt": 17,
            "in_sample": "PASS",
            "mark": "needs new data",
            "holdout": None,
            "note": "Needs new data.",
        }
        b.update_catalogue(path, [passed, waiting], flags)
        with open(path, encoding="utf-8") as fh:
            again = fh.read()
        watch = again.split("## Watch")[1].split("## Investing")[0]
        self.assertIn("rsi2 again", watch)
        self.assertNotIn("rsi2 again", again.split("## Bucket")[1].split("## Watch")[0])

    def test_rules_land_before_a_result_row(self):
        folder = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, folder)
        path = os.path.join(folder, "EXPERIMENTS.md")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("| 16 | old |\n\n## Forward test\n\nkept\n")
        rules = b.rules_text("2026-11-07")
        self.assertIn("before the run", rules)
        self.assertIn("stock-specific", rules)
        self.assertIn("needs new data", rules)
        self.assertIn("5-session", rules)
        self.assertIn("NIFTY ENERGY", rules)
        f.install_attempt(path, 17, rules, [])
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        self.assertLess(text.find("## Attempt 17"), text.find("## Forward test"))
        self.assertIn("## Forward test", text)
        self.assertNotIn("| 17 |", text)
        source = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "india", "research", "batch17.py")
        with open(source, encoding="utf-8") as fh:
            self.assertEqual(fh.read().count("final=True)"), 1)


if __name__ == "__main__":
    unittest.main()
