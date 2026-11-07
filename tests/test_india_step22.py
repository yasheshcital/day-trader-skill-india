"""Attempt 16 checks. Synthetic only."""

import datetime
import inspect
import os
import shutil
import tempfile
import unittest

from _load import load

b = load("india/research", "batch16")
f = load("india/research", "follow")


class CostsAndPairs(unittest.TestCase):
    def test_futures_costs_and_a_pair_that_converges(self):
        buy = b.futures_side(100000.0, True)
        sell = b.futures_side(100000.0, False)
        self.assertGreater(sell, buy)
        self.assertAlmostEqual(buy, 20.0 + 1.73 + 0.1 + 2.0 + 0.18 * (20.0 + 1.73 + 0.1))
        self.assertEqual(b.rollover_count(datetime.date(2016, 1, 10), datetime.date(2016, 1, 20)), 0)
        self.assertEqual(b.rollover_count(datetime.date(2016, 1, 10), datetime.date(2016, 2, 2)), 1)
        self.assertEqual(b.rollover_count(datetime.date(2016, 1, 10), datetime.date(2016, 3, 1)), 2)
        same = b.pair_return(100.0, 110.0, 100.0, 110.0, True, 0)
        converged = b.pair_return(100.0, 110.0, 100.0, 90.0, True, 0)
        self.assertLess(same, 0.0)
        self.assertGreater(converged, same)

    def test_same_industry_keeps_the_closer_cross_industry_out(self):
        flat = [1.0, 1.0, 1.0, 1.0]
        near = [1.0, 1.01, 1.0, 1.02]
        far = [1.0, 1.2, 0.8, 1.3]
        series = {"AAA": flat, "BBB": near, "CCC": list(far)}
        industries = {"AAA": "Banks", "BBB": "Banks", "CCC": "IT"}
        same = b.choose_pairs(series, industries, 20, True)
        any_ind = b.choose_pairs(series, industries, 20, False)
        self.assertEqual([(item[1], item[2]) for item in same], [("AAA", "BBB")])
        self.assertEqual((any_ind[0][1], any_ind[0][2]), ("AAA", "BBB"))
        self.assertEqual(len(any_ind), 3)

    def test_distance_and_z_boundaries(self):
        rows = [(datetime.date(2016, 1, 1), 0.0, 0.0)]
        rows.append((datetime.date(2016, 1, 2), 1.0, 0.0))
        rows.append((datetime.date(2016, 1, 3), 0.0, 0.0))
        # mean 0, std 1 would need a real series. Use a hand gap.
        gaps = []
        for i in range(6):
            gaps.append((datetime.date(2016, 1, i + 1), 0.0, 0.0))
        gaps[1] = (gaps[1][0], 3.0, 0.0)
        gaps[2] = (gaps[2][0], 0.0, 0.0)
        trades = b.distance_trades(gaps, 0.0, 1.0)
        self.assertEqual(trades, [(1, 2, False)])
        exact = [(datetime.date(2016, 1, 1), 2.0, 0.0), (datetime.date(2016, 1, 2), 2.0, 0.0)]
        self.assertEqual(b.distance_trades(exact, 0.0, 1.0), [])
        quiet = [0.0] * 5
        quiet[0] = 2.0
        self.assertEqual(b.walk_z(quiet, 20), [])
        held = [3.0] * 20
        found = b.walk_z(held, 20)
        self.assertEqual(found, [(0, 19, False)])
        stopped = [3.0, 4.0, 4.1]
        self.assertEqual(b.walk_z(stopped, 20), [(0, 2, False)])
        crossed = [3.0, 1.0, -0.1]
        self.assertEqual(b.walk_z(crossed, 20), [(0, 2, False)])


class GrailAndCalendar(unittest.TestCase):
    def _seg(self):
        class Seg(object):
            pass
        seg = Seg()
        n = 12
        seg.date = [datetime.date(2016, 1, 4) + datetime.timedelta(days=i) for i in range(n)]
        seg.o = [100.0] * n
        seg.h = [101.0] * n
        seg.l = [99.0] * n
        seg.c = [100.0] * n
        seg.adx = [40.0] * n
        seg.plus_di = [30.0] * n
        seg.minus_di = [10.0] * n
        seg.ema20 = [100.0] * n
        seg.sma200 = [90.0] * n
        return seg

    def test_signal_fill_and_stop_before_target(self):
        seg = self._seg()
        seg.adx[0] = 30.0
        self.assertFalse(b.grail_signal(seg, 0, 30.0, False))
        seg.adx[0] = 30.1
        seg.l[0] = 100.0
        seg.h[0] = 100.0
        self.assertTrue(b.grail_signal(seg, 0, 30.0, False))
        seg.h[1] = 100.0
        self.assertIsNone(b.grail_fill(seg, 0, "AAA"))
        seg.h[1] = 100.0 + 0.01
        filled = b.grail_fill(seg, 0, "AAA")
        self.assertEqual(filled[1], 100.01)
        seg.o[1] = 100.5
        gapped = b.grail_fill(seg, 0, "AAA")
        self.assertEqual(gapped[1], 100.5)
        seg.o[1] = 100.2
        seg.l[1] = 90.0
        seg.h[1] = 130.0
        found = b.grail_exit(seg, 1, 99.0, 120.0)
        self.assertEqual(found[1], 99.0)
        up = []
        for i in range(40):
            up.append(100.0 + i)
        adx, plus, minus = b.dmi_adx(up, [item - 1 for item in up], up, 14)
        self.assertGreater(plus[-1], minus[-1])
        self.assertIsNone(adx[0])

    def test_expiry_and_the_turn_of_the_month(self):
        self.assertEqual(b.last_thursday(2024, 11), datetime.date(2024, 11, 28))
        days = []
        day = datetime.date(2016, 1, 4)
        while day < datetime.date(2016, 3, 1):
            if day.weekday() < 5 and day != datetime.date(2016, 1, 28):
                days.append(day)
            day += datetime.timedelta(days=1)
        # 28 Jan 2016 was a Thursday. Removing it moves expiry to the previous session.
        self.assertEqual(b.expiry_day(2016, 1, days), datetime.date(2016, 1, 27))
        nifty = {}
        for i, item in enumerate(days):
            nifty[item] = {"open": 100.0 + i, "close": 101.0 + i}
        events = b.calendar_events(days, nifty)
        self.assertTrue(events["tom"])
        entry, exit_day, entry_px, exit_px = events["tom"][0]
        self.assertEqual(entry_px, nifty[entry]["close"])
        self.assertEqual(exit_px, nifty[exit_day]["close"])
        jan = [item for item in days if item.month == 1]
        feb = [item for item in days if item.month == 2]
        self.assertEqual(entry, jan[-2])
        self.assertEqual(exit_day, feb[2])
        exp = events["expiry week"][0]
        self.assertEqual(exp[1], datetime.date(2016, 1, 27))
        self.assertEqual(exp[2], nifty[exp[0]]["open"])
        after = events["after expiry"][0]
        self.assertGreater(after[0], exp[1])
        self.assertEqual(after[0].weekday(), 0)


class MixesJudgesAndCatalogue(unittest.TestCase):
    def test_momentum_cut_regime_and_correlation(self):
        scored = [(1.0, "BBB"), (3.0, "AAA"), (2.0, "CCC"), (4.0, "DDD")]
        self.assertEqual(b.top_fraction(scored, 30, 100), ["DDD"])
        self.assertEqual(len(b.top_fraction([(float(i), "S%d" % i) for i in range(10)], 30, 100)), 3)
        self.assertAlmostEqual(b.pearson([1, 2, 3, 4], [1, 2, 3, 4]), 1.0)
        self.assertLess(b.pearson([1, 2, 3, 4], [4, 3, 2, 1]), 0.0)

    def test_pass_marks_and_tiers(self):
        good = {
            "name": "pairs same", "avg": 0.2, "t": 3.1,
            "early": 0.1, "late": 0.1, "up": 0.1, "down": 0.1, "sideways": 0.1,
        }
        family = [dict(good), dict(good), dict(good)]
        family[2]["t"] = 2.1
        self.assertEqual(b.judge_event(good, family, "monthly t")["result"], "PASS")
        thin = dict(good)
        thin["t"] = 3.0
        self.assertEqual(b.judge_event(thin, family, "monthly t")["result"], "FAIL")
        short = [dict(good), dict(good, t=1.0), dict(good, t=1.0)]
        self.assertEqual(b.judge_event(good, short, "monthly t")["result"], "FAIL")
        mix = dict(good)
        mix["large"] = 0.2
        self.assertEqual(b.judge_mix(mix, True)["result"], "PASS")
        mix["down"] = None
        self.assertEqual(b.judge_mix(mix, False)["result"], "PASS")
        self.assertEqual(b.judge_mix(mix, True)["result"], "FAIL")
        self.assertEqual(b.judge_holdout(0.1, 2.0)["result"], "FAIL")
        self.assertEqual(b.judge_holdout(0.1, 2.01)["result"], "PASS")
        self.assertEqual(b.tier_of("PASS", 0.2, 2.5), "Bucket")
        self.assertEqual(b.tier_of("PASS", 0.2, 1.4), "Watch")
        self.assertEqual(b.tier_of("FAIL", 0.2, 4.0), "Closed")
        self.assertEqual(b.tier_of("PASS", -0.1, 3.0), "Closed")

    def test_catalogue_keeps_the_source_table_and_places_a_new_pass(self):
        folder = tempfile.mkdtemp(prefix="step22-cat-")
        self.addCleanup(lambda: shutil.rmtree(folder))
        path = os.path.join(folder, "STRATEGIES.md")
        b.update_tiers(path, [])
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        self.assertLess(text.find("## Watch"), text.find("## Sources"))
        self.assertIn("rsi2 < 5", text)
        self.assertIn(b.HDFC, text)
        self.assertIn("rev K20", text)
        self.assertIn("Faber timing", text)
        self.assertIn("None yet.", text)
        self.assertIn("full TSMOM not started", text)
        self.assertIn("opening-range breakout", text)
        self.assertIn("Attempts 1 to 10", text)
        turtle = [line for line in text.splitlines() if line.startswith("| Turtle breakout |")][0]
        self.assertIn("| 11 |", turtle)
        self.assertNotIn("\u2014", text)
        b.update_tiers(path, [{
            "name": "grail adx30",
            "attempt": 16,
            "in_sample": "PASS",
            "holdout": {"avg": 0.4, "t": 2.4},
            "note": "Holdout PASS.",
        }])
        with open(path, encoding="utf-8") as fh:
            later = fh.read()
        self.assertEqual(later.count("grail adx30"), 1)
        self.assertIn("| grail adx30 | 16 | Holdout PASS. |", later)
        bucket = later.split("## Watch")[0]
        self.assertIn("grail adx30", bucket)
        self.assertIn("rsi2 < 5", later.split("## Watch")[1].split("## Investing")[0])

    def test_rules_are_installed_before_results(self):
        folder = tempfile.mkdtemp(prefix="step22-exp-")
        self.addCleanup(lambda: shutil.rmtree(folder))
        path = os.path.join(folder, "EXPERIMENTS.md")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("\n".join([
                "| 15 | 2026-11-07 | holdout rsi2 < 5. | rule | data | 1 | +0.327% | +1.42 | FAIL |",
                "",
                "## Attempt 15",
                "",
                "Kept.",
                "",
                "## Forward test",
                "",
                "Started 2026-11-04.",
                "",
            ]))
        rules = b.rules_text("2026-11-07")
        self.assertIn("before the run", rules)
        self.assertIn("check your broker", rules)
        self.assertIn("Spot prices are the futures proxy", rules)
        self.assertIn("Hypothesis from attempt 14", rules)
        self.assertIn("at least 2 of the 3", rules)
        self.assertNotIn("\u2014", rules)
        f.install_attempt(path, 16, rules, [])
        with open(path, encoding="utf-8") as fh:
            early = fh.read()
        self.assertLess(early.find("## Attempt 15"), early.find("## Attempt 16"))
        self.assertLess(early.find("## Attempt 16"), early.find("## Forward test"))
        self.assertNotIn("| 16 |", early)
        self.assertEqual(inspect.getsource(b.run_holdout).count("final=True)"), 1)
        self.assertNotIn("final=True", inspect.getsource(b.prepare_context))


if __name__ == "__main__":
    unittest.main()
