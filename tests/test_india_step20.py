"""Attempt 13 big-gap continuation and attempt 14 short swing. Synthetic only."""

import datetime
import os
import unittest

from _load import load

f = load("india/research", "follow")
data = load("india/research", "data")
lab = load("india/research", "signal_lab")
ta = load("india/research", "ta")


def _session(close=100.0, volume=100.0):
    ends = []
    minute = 9 * 60 + 20
    while minute <= 15 * 60 + 25:
        ends.append(minute)
        minute += 5
    n = len(ends)
    return {
        "end": ends,
        "open": [float(close)] * n,
        "high": [float(close)] * n,
        "low": [float(close)] * n,
        "close": [float(close)] * n,
        "volume": [float(volume)] * n,
    }


def _at(session, minute):
    for i, end in enumerate(session["end"]):
        if end == minute:
            return i
    raise AssertionError(minute)


def _set(session, minute, close, high=None, low=None, open_=None, volume=None):
    i = _at(session, minute)
    session["close"][i] = close
    session["high"][i] = close if high is None else high
    session["low"][i] = close if low is None else low
    if open_ is not None:
        session["open"][i] = open_
    if volume is not None:
        session["volume"][i] = volume
    return i


class Seg(object):
    def __init__(self, n):
        self.date = [datetime.date(2010, 1, 1) + datetime.timedelta(days=i) for i in range(n)]
        self.o = [10.0] * n
        self.h = [10.0] * n
        self.l = [9.0] * n
        self.c = [10.0] * n
        self.sma5 = [None] * n
        self.sma200 = [None] * n
        self.rsi2 = [None] * n
        self.low10 = [None] * n
        self.low20 = [None] * n
        self.low55 = [None] * n


def _gap_block(**over):
    base = {
        "name": "gap cont 3",
        "trades": 300,
        "days": 100,
        "avg_before": 0.2,
        "avg_after": 0.10,
        "t": 4.0,
        "t_same": 5.0,
        "early": 0.1,
        "late": 0.1,
        "up": 0.1,
        "down": 0.1,
        "sideways": 0.1,
        "large": 0.1,
        "yearly": {},
        "win": 0.5,
        "kind": "big_gap",
    }
    base.update(over)
    return base


def _swing_block(**over):
    base = {
        "name": "rsi2 < 10",
        "kind": "rsi",
        "trades": 10,
        "days": 10,
        "avg": 0.2,
        "t": 4.0,
        "excess": 0.1,
        "early": 0.1,
        "late": 0.1,
        "up": 0.1,
        "down": 0.1,
        "sideways": 0.1,
        "large": 0.1,
        "yearly": {},
        "hold_days": 3.0,
        "index": False,
    }
    base.update(over)
    return base


class GapRules(unittest.TestCase):
    def test_thresholds_direction_and_the_0930_close(self):
        day = datetime.date(2016, 6, 1)
        spec3 = {"name": "gap cont 3", "kind": "big_gap", "min_gap": 0.03, "volume": False}
        spec4 = {"name": "gap cont 4", "kind": "big_gap", "min_gap": 0.04, "volume": False}
        session = _session(104.0)
        _set(session, f.h.M_0920, 103.0, high=104.0, low=102.0, open_=103.0)
        _set(session, f.h.M_0930, 104.0, high=104.5, low=103.0)
        trade3 = f.big_gap_trade(session, day, "AAA", 100.0, "up", True, spec3, None)
        trade4 = f.big_gap_trade(session, day, "AAA", 100.0, "up", True, spec4, None)
        self.assertIsNotNone(trade3)
        self.assertIsNone(trade4)
        wide = _session(105.0)
        _set(wide, f.h.M_0920, 104.0, high=105.0, low=103.0, open_=104.0)
        _set(wide, f.h.M_0930, 105.0, high=105.5, low=104.0)
        self.assertIsNotNone(f.big_gap_trade(wide, day, "AAA", 100.0, "up", True, spec4, None))
        back = _session(100.0)
        _set(back, f.h.M_0920, 103.0, high=104.0, low=102.0, open_=103.0)
        _set(back, f.h.M_0930, 100.0, high=103.0, low=99.0)
        self.assertIsNone(f.big_gap_trade(back, day, "AAA", 100.0, "up", True, spec3, None))

    def test_stop_is_the_opposite_extreme_and_flat_is_1510(self):
        day = datetime.date(2016, 6, 1)
        spec = {"name": "gap cont 3", "kind": "big_gap", "min_gap": 0.03, "volume": False}
        held = _session(104.0)
        _set(held, f.h.M_0920, 103.0, high=104.0, low=102.0, open_=103.0)
        _set(held, f.h.M_1510, 104.0)
        _set(held, f.h.M_1525, 150.0)
        trade = f.big_gap_trade(held, day, "AAA", 100.0, "up", True, spec, None)
        self.assertLess(trade["r_after"], 0.0)
        stopped = _session(104.0)
        _set(stopped, f.h.M_0920, 103.0, high=104.0, low=102.0, open_=103.0)
        _set(stopped, 10 * 60, 101.0, high=101.0, low=101.0, open_=101.0)
        hit = f.big_gap_trade(stopped, day, "AAA", 100.0, "up", True, spec, None)
        self.assertLess(hit["r_before"], -0.5)
        short = _session(96.0)
        _set(short, f.h.M_0920, 97.0, high=99.0, low=96.0, open_=97.0)
        _set(short, f.h.M_0930, 96.0, high=97.0, low=95.5)
        for minute in short["end"]:
            if minute <= f.h.M_0930:
                continue
            _set(short, minute, 96.0, high=99.0, low=95.5)
        _set(short, f.h.M_1510, 96.0, high=99.0, low=95.5)
        sold = f.big_gap_trade(short, day, "AAA", 100.0, "down", False, spec, None)
        self.assertIsNotNone(sold)
        self.assertLess(sold["r_before"], -0.5)

    def test_same_day_window_and_volume_boundary(self):
        session = _session(100.0, volume=10.0)
        window = f.entry_window(session)
        self.assertEqual(session["end"][window[0]], f.h.M_0930)
        self.assertEqual(session["end"][window[-1]], f.h.M_1430)
        self.assertEqual(len(window), 61)
        self.assertNotIn(_at(session, f.h.M_0920), window)
        self.assertNotIn(_at(session, f.h.M_1525), window)
        self.assertAlmostEqual(f.opening_volume(session), 30.0)
        _set(session, f.h.M_0935, 100.0, volume=1000.0)
        self.assertAlmostEqual(f.opening_volume(session), 30.0)
        history = [100.0] * 10
        self.assertAlmostEqual(f.vol_multiple(200.0, history), 2.0)
        self.assertIsNone(f.vol_multiple(200.0, history[:-1]))
        self.assertTrue(f.vol_multiple(200.0, history) >= f.VOLUME_MULT)
        self.assertFalse(f.vol_multiple(199.0, history) >= f.VOLUME_MULT)
        day = datetime.date(2016, 6, 1)
        spec = {"name": "gap cont 3 vol", "kind": "big_gap", "min_gap": 0.03, "volume": True}
        priced = _session(104.0)
        _set(priced, f.h.M_0920, 103.0, high=104.0, low=102.0, open_=103.0)
        self.assertIsNotNone(f.big_gap_trade(priced, day, "AAA", 100.0, "up", True, spec, 2.0))
        self.assertIsNone(f.big_gap_trade(priced, day, "AAA", 100.0, "up", True, spec, 1.99))
        self.assertIsNone(f.big_gap_trade(priced, day, "AAA", 100.0, "up", True, spec, None))

    def test_non_gap_pool_and_the_pass_t_is_the_non_gap_t(self):
        self.assertTrue(f.is_nongap(0.0049))
        self.assertTrue(f.is_nongap(-0.0049))
        self.assertFalse(f.is_nongap(0.005))
        self.assertFalse(f.is_nongap(-0.005))
        jan = datetime.date(2016, 1, 4)
        feb = datetime.date(2016, 2, 4)
        trades = [
            self._trade(jan, 1.0, [0.0]),
            self._trade(feb, 1.0, [0.0]),
        ]
        pools = {"AAA": {(2016, 1): [(1.0, 1.0)], (2016, 2): [(1.0, 1.0)]}}
        spec = f.batch13()[0]
        block = f.score_gap(spec, 0, trades, pools, 5)
        self.assertEqual(block["t"], 0.0)
        self.assertTrue(block["t_same"] > 3)
        self.assertEqual(block["excess_ng"], 0.0)
        self.assertGreater(block["excess_same"], 0.0)
        verdict = f.judge_gap(block, [block, block, block])
        self.assertEqual(verdict["result"], "FAIL")
        self.assertIn("t vs non-gap", " ".join(verdict["reasons"]))

    def _trade(self, day, r_after, window):
        return {
            "date": day,
            "symbol": "AAA",
            "r_before": r_after,
            "r_after": r_after,
            "shares": 1,
            "regime": "up",
            "large": True,
            "window_r": list(window),
        }

    def test_volume_history_uses_the_previous_ten_and_exactly_two_times(self):
        rows = []
        sessions = {}
        start = datetime.date(2016, 1, 4)
        for i in range(11):
            day = start + datetime.timedelta(days=i)
            rows.append({
                "date": day, "open": 100.0, "high": 101.0, "low": 99.0,
                "close": 100.0, "volume": 1000.0,
            })
            vol = 200.0 if i == 10 else 100.0
            session = _session(100.0, volume=vol)
            if i >= 9:
                _set(session, f.h.M_0920, 103.0, high=104.0, low=102.0, open_=103.0)
                _set(session, f.h.M_0930, 104.0, high=104.5, low=103.0)
            sessions[day] = session
        book = f.h.DailyBook([rows])
        member = set(item["date"] for item in rows)
        found, _pool = f.scan_gap_symbol(
            "AAA", sessions, book, member, member, {}, f.batch13())
        vol_days = [trade["date"] for trade in found["gap cont 3 vol"]]
        gap_days = [trade["date"] for trade in found["gap cont 3"]]
        self.assertEqual(vol_days, [start + datetime.timedelta(days=10)])
        self.assertEqual(len(gap_days), 2)
        self.assertEqual(found["gap cont 4"], [])

    def test_judge_boundaries_and_family(self):
        strong = _gap_block(name="a", t=4.0)
        also = _gap_block(name="b", t=2.01)
        weak = _gap_block(name="c", t=1.0, t_same=9.0)
        family = [strong, also, weak]
        self.assertEqual(f.judge_gap(strong, family)["result"], "PASS")
        weak_verdict = f.judge_gap(weak, family)
        self.assertEqual(weak_verdict["result"], "FAIL")
        self.assertIn("t vs non-gap", " ".join(weak_verdict["reasons"]))
        self.assertNotIn("family variants", " ".join(weak_verdict["reasons"]))
        edge = f.judge_gap(_gap_block(t=3.0), [_gap_block(t=3.0)] * 3)
        self.assertIn("t vs non-gap", " ".join(edge["reasons"]))
        exact = f.judge_gap(_gap_block(avg_after=0.10), [_gap_block(t=4.0)] * 3)
        self.assertEqual(exact["result"], "PASS")
        empty = f.judge_gap(_gap_block(large=None), [_gap_block(t=4.0)] * 3)
        self.assertIn("large caps", " ".join(empty["reasons"]))
        short = [_gap_block(t=2.0), _gap_block(t=4.0), _gap_block(t=1.0)]
        self.assertIn("family variants", " ".join(f.judge_gap(short[1], short)["reasons"]))


class SwingRules(unittest.TestCase):
    def test_rsi_boundary_two_down_closes_and_the_exit(self):
        seg = Seg(8)
        seg.c[2] = 30.0
        seg.sma200[2] = 20.0
        seg.rsi2[2] = 10.0
        self.assertFalse(f.rsi_fires(seg, 2, 10.0, False))
        seg.rsi2[2] = 9.9
        self.assertTrue(f.rsi_fires(seg, 2, 10.0, False))
        self.assertFalse(f.rsi_fires(seg, 2, 5.0, False))
        seg.c[0], seg.c[1], seg.c[2] = 12.0, 11.0, 10.0
        seg.sma200[2] = 9.0
        seg.rsi2[2] = 9.0
        self.assertTrue(f.rsi_fires(seg, 2, 10.0, True))
        seg.c[0], seg.c[1], seg.c[2] = 12.0, 9.0, 10.0
        self.assertFalse(f.rsi_fires(seg, 2, 10.0, True))
        quiet = Seg(8)
        found = f.exit_rule(quiet, 1, f.RSI_LIMIT, f.close_above_sma5)
        self.assertEqual(found[0], 6)
        self.assertEqual(found[1], quiet.o[6])
        self.assertTrue(found[2])
        quiet.sma5[1] = 9.0
        quiet.c[1] = 11.0
        early = f.exit_rule(quiet, 1, f.RSI_LIMIT, f.close_above_sma5)
        self.assertEqual(early[0], 2)
        self.assertEqual(early[1], quiet.o[2])

    def test_ibs_skips_a_flat_bar_and_the_boundary(self):
        self.assertIsNone(f.ibs_value(10.0, 10.0, 10.0))
        seg = Seg(3)
        seg.h[1], seg.l[1], seg.c[1] = 10.0, 10.0, 10.0
        seg.sma200[1] = 9.0
        self.assertFalse(f.ibs_fires(seg, 1, 0.2))
        seg.sma200[1] = 0.5
        seg.h[1], seg.l[1], seg.c[1] = 10.0, 0.0, 2.0
        self.assertAlmostEqual(f.ibs_value(10.0, 0.0, 2.0), 0.2)
        self.assertFalse(f.ibs_fires(seg, 1, 0.2))
        seg.c[1] = 1.9
        self.assertTrue(f.ibs_fires(seg, 1, 0.2))
        self.assertFalse(f.ibs_fires(seg, 1, 0.1))
        self.assertTrue(f.large_flag("NIFTY 50", seg.date[1], {}, True))
        self.assertFalse(f.large_flag("AAA", seg.date[1], {}, False))
        day = seg.date[1]
        trade = f.make_trade(day, "NIFTY 50", 1.25, 0.2, "up", True, 4)
        block = f.summarise_swing("ibs < 0.2 nifty", [trade])
        self.assertAlmostEqual(block["large"], block["avg"])
        self.assertAlmostEqual(block["avg"], 1.25)

    def test_turtle_soup_stop_target_and_prior_low(self):
        lows = [5.0, 4.0, 3.0, 2.0, 1.0, 0.5]
        prior = ta.prior_low_series(lows, 5)
        self.assertEqual(prior[5], 1.0)
        self.assertTrue(f.soup_fires(0.5, 1.5, prior[5]))
        self.assertFalse(f.soup_fires(1.0, 1.5, prior[5]))
        self.assertFalse(f.soup_fires(0.5, 1.0, prior[5]))
        self.assertFalse(f.soup_fires(0.5, 2.0, None))
        seg = Seg(4)
        seg.o[0], seg.h[0], seg.l[0] = 10.0, 12.0, 9.0
        both = f.exit_soup(seg, 0, 9.0)
        self.assertEqual(both[1], 9.0)
        self.assertFalse(both[2])
        seg.l[0] = 9.5
        target = f.exit_soup(seg, 0, 9.0)
        self.assertEqual(target[1], 12.0)
        self.assertFalse(target[2])
        for i in range(4):
            seg.h[i] = 11.0
            seg.l[i] = 9.5
            seg.o[i] = 10.0
        seg.o[3] = 10.4
        held = f.exit_soup(seg, 0, 9.0)
        self.assertEqual(held[0], 3)
        self.assertEqual(held[1], 10.4)
        self.assertTrue(held[2])
        seg.o[1] = 8.0
        gap = f.exit_soup(seg, 0, 9.0)
        self.assertEqual(gap, (1, 8.0, True))
        seg.o[0] = 9.0
        self.assertIsNone(f.exit_soup(seg, 0, 9.0))

    def test_monday_rank_filter_and_bias_is_not_subtracted(self):
        closes = [10.0, 10.0, 10.0, 10.0, 10.0, 8.0]
        self.assertAlmostEqual(f.five_day_return(closes, 5), -0.2)
        eligible = [
            (-0.2, "BBB", 100.0, 110.0),
            (-0.2, "AAA", 100.0, 90.0),
            (0.05, "CCC", 100.0, 100.0),
        ]
        worst = f.pick_worst(eligible, 2)
        self.assertEqual([item[1] for item in worst], ["AAA", "BBB"])
        self.assertFalse(f.week_allowed(False, True))
        self.assertTrue(f.week_allowed(False, False))
        self.assertTrue(f.week_allowed(True, True))
        self.assertAlmostEqual(f.scale_bias(6.377, 365.25), 6.377)
        self.assertEqual(f.scale_bias(6.377, 0), 0.0)
        scaled = f.scale_bias(6.377, 5)
        self.assertGreater(scaled, 0.0)
        self.assertLess(scaled, 0.2)
        note = f.bias_note(6.377, scaled, 5)
        self.assertIn("not subtracted", note)
        block = _swing_block(avg=0.2, bias_year=6.377, bias_hold=scaled)
        verdict = f.judge_swing(block, [block, block, _swing_block(t=4.0)])
        self.assertEqual(verdict["result"], "PASS")
        self.assertNotIn("survivorship", " ".join(verdict["reasons"]))
        zero = f.judge_swing(_swing_block(avg=0.0), [_swing_block(t=4.0)] * 3)
        self.assertIn("not above 0", " ".join(zero["reasons"]))
        tied = f.judge_swing(_swing_block(t=3.0), [_swing_block(t=4.0)] * 3)
        self.assertIn("t vs random", " ".join(tied["reasons"]))
        money = lab.delivery(100.0, 110.0)
        self.assertAlmostEqual(f.net_return(100.0, 110.0), money[0])
        excess = f.adjusted_excess(2.0, 1.0, [(1.0, 1.0), (3.0, 2.0)])
        self.assertAlmostEqual(excess, 0.5)
        day = datetime.date(2010, 6, 7)
        only = [(-0.1, "AAA", 100.0, 110.0)]
        trade = f.make_trade(day, f.BOOK, f.book_return(only), 1.5, "up", False, 7)
        trade["eligible"] = only
        f.apply_book_random([trade], 4, 1, 1)
        self.assertEqual(trade["excess"], 0.0)

    def test_families_and_the_locked_window(self):
        self.assertEqual(len(f.batch13()), 3)
        self.assertEqual(len(f.batch14()), 12)
        kinds = [kind for kind, _specs in f.h.families(f.batch14())]
        self.assertEqual(kinds, ["rsi", "ibs", "soup", "reversal"])
        self.assertEqual(f.SWING_END, datetime.date(2024, 12, 31))
        self.assertLess(f.SWING_END, data.HOLDOUT_START)
        self.assertEqual(f.h.INTRADAY_END, datetime.date(2024, 12, 31))
        path = os.path.join(os.path.dirname(f.__file__), "follow.py")
        with open(path, encoding="utf-8") as fh:
            src = fh.read()
        self.assertNotIn("\u2014", src)
        self.assertNotIn("final=True", src)
        rules = f.gap_rules("2026-11-07") + f.swing_rules("2026-11-07")
        self.assertIn(f.HYPOTHESIS_13, rules)
        self.assertIn("not subtracted", rules)
        self.assertNotIn("\u2014", rules)


class Install(unittest.TestCase):
    def _fixture(self, folder):
        path = os.path.join(folder, "EXPERIMENTS.md")
        text = "\n".join([
            "| # | Date | Hypothesis | Rule | Data | Trades | R before costs | R after costs | Result |",
            "| 9 | 2026-11-06 | 20d-high / sma20-close and engulf-low / hold-20 | rule | data | 17,461; 2,337 | +1.574%; +1.176% | +1.574%; +1.176% | PASS |",
            "| 11 | 2026-11-06 | mom 12-1 K20 above200 | rule | data | 3,654 | +35.442% | +4.82 | PASS |",
            "| 12 | 2026-11-07 | gap GO 3 | rule | data | 3,834 | +0.106 | +0.075 | FAIL |",
            "",
            "## Attempt 12",
            "",
            "Variants that pass: 0 of 12.",
            "",
            "### Survivorship calibration",
            "",
            "PASS in-sample, but inflated by survivorship bias; real NIFTY200 Momentum 30 TRI: "
            "18.8% CAGR vs NIFTY 50 TRI 13.6% since Apr 2005 (HDFC MF, Jul 2026)",
            "",
            "## Forward test",
            "",
            "Started 2026-11-04.",
            "",
        ])
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)
        return path

    def test_rules_land_before_results_and_a_second_install_does_not_duplicate(self):
        folder = self._folder()
        path = self._fixture(folder)
        stamp = "2026-11-07"
        f.install_attempt(path, 13, f.gap_rules(stamp), [])
        f.install_attempt(path, 14, f.swing_rules(stamp), [])
        with open(path, encoding="utf-8") as fh:
            early = fh.read()
        self.assertLess(early.find("## Attempt 12"), early.find("## Attempt 13"))
        self.assertLess(early.find("## Attempt 13"), early.find("## Attempt 14"))
        self.assertLess(early.find("## Attempt 14"), early.find("## Forward test"))
        self.assertIn(f.HYPOTHESIS_13, early)
        self.assertIn("HDFC MF, Jul 2026", early)
        self.assertIn("| 9 |", early)
        self.assertIn("| 11 |", early)
        self.assertIn("| 12 |", early)
        self.assertNotIn("| 13 |", early)
        self.assertNotIn("\u2014", early)
        gap = _gap_block(trades=12, avg_before=0.2, avg_after=0.05)
        gap["verdict"] = {"result": "FAIL", "reasons": ["avg R after costs +0.050 is below +0.10"]}
        swing = _swing_block(trades=8, avg=0.4, t=1.5, kind="rsi")
        swing["verdict"] = {"result": "FAIL", "reasons": ["t vs random +1.50 is not above 3"]}
        f.install_attempt(path, 13, f.gap_report(stamp, [gap]), f.gap_rows(stamp, [gap]))
        f.install_attempt(path, 14, f.swing_report(stamp, [swing]), f.swing_rows(stamp, [swing]))
        f.install_attempt(path, 13, f.gap_report(stamp, [gap]), f.gap_rows(stamp, [gap]))
        with open(path, encoding="utf-8") as fh:
            later = fh.read()
        self.assertEqual(later.count("## Attempt 13"), 1)
        self.assertEqual(later.count("## Attempt 14"), 1)
        self.assertEqual(later.count("| 13 |"), 1)
        self.assertEqual(later.count("| 14 |"), 1)
        self.assertLess(later.find("## Attempt 13"), later.find("## Attempt 14"))
        self.assertLess(later.find("## Attempt 14"), later.find("## Forward test"))
        self.assertIn("## Attempt 12", later)
        self.assertIn(f.HYPOTHESIS_13, later)
        self.assertIn("not subtracted", later)
        self.assertIn("HDFC MF, Jul 2026", later)

    def _folder(self):
        import tempfile
        folder = tempfile.mkdtemp(prefix="step20-")
        self.addCleanup(lambda: __import__("shutil").rmtree(folder))
        return folder


if __name__ == "__main__":
    unittest.main()
