"""Attempt 12 intraday rules, and one holdout line per process. Synthetic only."""

import datetime
import os
import re
import shutil
import tempfile
import unittest

from _load import load

h = load("india/research", "harness")
data = load("india/research", "data")
costs = load("india", "costs")


def _session(close=100.0, volume=1000.0):
    ends = []
    minute = 9 * 60 + 20
    while minute <= 15 * 60 + 25:
        ends.append(minute)
        minute += 5
    n = len(ends)
    return {
        "end": ends,
        "open": [close] * n,
        "high": [close] * n,
        "low": [close] * n,
        "close": [float(close)] * n,
        "volume": [float(volume)] * n,
    }


def _at(session, minute):
    for i, end in enumerate(session["end"]):
        if end == minute:
            return i
    raise AssertionError(minute)


def _set(session, minute, close, high=None, low=None, open_=None):
    i = _at(session, minute)
    session["close"][i] = close
    session["high"][i] = close if high is None else high
    session["low"][i] = close if low is None else low
    if open_ is not None:
        session["open"][i] = open_
    return i


def _block(**over):
    base = {
        "name": "sample",
        "trades": 300,
        "days": 100,
        "avg_before": 0.2,
        "avg_after": 0.10,
        "t": 4.0,
        "early": 0.1,
        "late": 0.1,
        "up": 0.1,
        "down": 0.1,
        "sideways": 0.1,
        "large": 0.1,
        "yearly": {},
        "win": 0.5,
        "kind": "nr",
    }
    base.update(over)
    return base


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


class HoldoutOnce(unittest.TestCase):
    def test_one_line_per_process_and_the_real_log_stays(self):
        root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, root)
        start = datetime.date(2024, 12, 1)
        days = [start + datetime.timedelta(days=i) for i in range(20)]
        days.append(data.HOLDOUT_START)
        for symbol in ("AAA", "BBB"):
            rows = []
            for day in days:
                rows.append({
                    "date": day, "open": 10, "high": 10, "low": 10, "close": 10, "volume": 1,
                })
            _write_daily(data.bar_path(root, "day", symbol), rows)
        log_path = os.path.join(root, "HOLDOUT_LOG.md")
        real = data.HOLDOUT_LOG
        self.assertNotEqual(os.path.abspath(log_path), os.path.abspath(real))
        if os.path.isfile(real):
            with open(real, encoding="utf-8") as fh:
                before = fh.read()
        else:
            before = None
        data.load_daily(root, "AAA", final=True, log_path=log_path)
        data.load_daily(root, "BBB", final=True, log_path=log_path)
        with open(log_path, encoding="utf-8") as fh:
            text = fh.read()
        self.assertEqual(len(re.findall(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}", text)), 1)
        if os.path.isfile(real):
            with open(real, encoding="utf-8") as fh:
                after = fh.read()
        else:
            after = None
        self.assertEqual(before, after)


class IntradayRules(unittest.TestCase):
    def test_batch_shape_and_costs(self):
        specs = h.batch2()
        self.assertEqual(len(specs), 12)
        self.assertEqual(len(h.families(specs)), 4)
        self.assertEqual(h.batch1()[0]["name"], "turtle 20/10")
        self.assertEqual(h.intraday_shares(100, 2), 1000)
        self.assertEqual(h.intraday_shares(2000, 1), 250)
        hand = 40.0 + 3.75 + 0.2595 + 0.015 + 0.15 + (40.0 + 0.2595 + 0.015) * 0.18
        self.assertAlmostEqual(h.nifty_round_trip(100, 100, 75), hand, places=6)
        self.assertAlmostEqual(
            h.equity_cost(100, 101, 10), float(costs.round_trip(100, 101, 10)), places=4)
        text = h.intraday_rules("2026-11-07")
        self.assertIn("check your broker", text)
        self.assertIn("0.25%", text)
        self.assertIn("Rs 20 per order", text)
        self.assertNotIn("Results.", text)
        self.assertNotIn("\u2014", text)

    def test_gao_lot_slippage_and_filters(self):
        day = datetime.date(2016, 1, 4)
        session = _session(100)
        _set(session, h.M_0945, 101)
        _set(session, h.M_1430, 100)
        _set(session, h.M_1500, 102)
        _set(session, h.M_1525, 104)
        always, wide, same = h.batch2()[:3]
        trade = h.gao_trade(session, 100.0, always, day, "up")
        self.assertEqual(trade["date"], day)
        self.assertEqual(trade["shares"], h.NIFTY_LOT)
        self.assertTrue(trade["large"])
        risk = 0.0025 * 102
        self.assertAlmostEqual(trade["r_before"], (103.95 - 102.05) / risk, places=6)
        self.assertLess(trade["r_after"], trade["r_before"])
        self.assertIsNotNone(h.gao_trade(session, 100.0, wide, day, "up"))
        self.assertIsNotNone(h.gao_trade(session, 100.0, same, day, "up"))
        exact = _session(100)
        _set(exact, h.M_0945, 100.25)
        _set(exact, h.M_1430, 100)
        _set(exact, h.M_1500, 100)
        _set(exact, h.M_1525, 100)
        self.assertIsNone(h.gao_trade(exact, 100.0, wide, day, "up"))
        self.assertIsNotNone(h.gao_trade(exact, 100.0, always, day, "up"))
        split = _session(100)
        _set(split, h.M_0945, 101)
        _set(split, h.M_1430, 100)
        _set(split, h.M_1500, 99)
        _set(split, h.M_1525, 99)
        self.assertIsNone(h.gao_trade(split, 100.0, same, day, "down"))
        self.assertEqual(h.gao_trade(split, 100.0, always, day, "down")["symbol"], "NIFTY 50")
        broken = _session(100)
        i = _at(broken, h.M_1510)
        del broken["end"][i]
        self.assertFalse(h._session_usable(broken))

    def test_nr_stop_and_flat(self):
        session = _session(9.5)
        for minute in range(h.M_0920, h.M_0945 + 1, 5):
            _set(session, minute, 9.5, high=10, low=9)
        _set(session, h.M_1000, 11, high=11, low=11)
        for minute in range(h.M_1000 + 5, h.M_1525 + 1, 5):
            _set(session, minute, 12, high=12, low=11)
        trade = h.nr_trade(session, datetime.date(2016, 1, 5), "ABC", "up", True)
        self.assertEqual(trade["shares"], 1000)
        self.assertAlmostEqual(trade["r_before"], (11.99 - 11.01) / 2.0, places=6)
        stopped = _session(9.5)
        for minute in range(h.M_0920, h.M_0945 + 1, 5):
            _set(stopped, minute, 9.5, high=10, low=9)
        _set(stopped, h.M_1000, 11, high=11, low=11)
        _set(stopped, h.M_1000 + 5, 11, high=12, low=8, open_=11)
        trade = h.nr_trade(stopped, datetime.date(2016, 1, 5), "ABC", "up", False)
        self.assertAlmostEqual(trade["r_before"], (8.99 - 11.01) / 2.0, places=6)
        gapped = _session(9.5)
        for minute in range(h.M_0920, h.M_0945 + 1, 5):
            _set(gapped, minute, 9.5, high=10, low=9)
        _set(gapped, h.M_1000, 11, high=11, low=11)
        _set(gapped, h.M_1000 + 5, 8, high=8, low=8, open_=8)
        trade = h.nr_trade(gapped, datetime.date(2016, 1, 5), "ABC", "down", False)
        self.assertAlmostEqual(trade["r_before"], (7.99 - 11.01) / 2.0, places=6)

    def test_nr_flags_gap_and_vwap(self):
        rows = []
        for i, width in enumerate([5, 5, 5, 5, 5, 5, 1, 5]):
            rows.append({
                "high": 100 + width, "low": 100, "seg": 0, "i": i,
                "close": 100, "open": 100,
                "date": datetime.date(2016, 1, 1) + datetime.timedelta(days=i),
            })
        self.assertTrue(h.is_nr(rows, 6, 7, False))
        self.assertTrue(h.is_nr(rows, 6, 4, False))
        self.assertFalse(h.is_nr(rows, 5, 7, False))
        rows[5]["high"] = 110
        rows[5]["low"] = 90
        rows[6]["high"] = 102
        rows[6]["low"] = 101
        self.assertTrue(h.is_nr(rows, 6, 7, True))
        rows[6]["low"] = 90
        self.assertFalse(h.is_nr(rows, 6, 7, True))

        day0 = datetime.date(2016, 2, 1)
        day1 = datetime.date(2016, 2, 2)
        book = h.DailyBook([[
            {"date": day0, "open": 100, "high": 110, "low": 90, "close": 100, "volume": 10},
            {"date": day1, "open": 103, "high": 104, "low": 102, "close": 103, "volume": 10},
        ]])
        session = _session(103)
        session["open"][_at(session, h.M_0920)] = 103
        for minute in range(h.M_0920, h.M_0930 + 1, 5):
            _set(session, minute, 103, high=103.5, low=102.5)
            session["open"][_at(session, minute)] = 103
        _set(session, h.M_1000, 104, high=104, low=104)
        for minute in range(h.M_1000 + 5, h.M_1510 + 1, 5):
            _set(session, minute, 104, high=104, low=103)
        specs = [spec for spec in h.batch2() if spec["kind"] == "gap"]
        found = h.scan_symbol(
            "ABC", {day1: session}, book, set([day1]), set(), {"up": day1}, specs)
        self.assertEqual(len(found["gap GO 1.5"]), 1)
        self.assertEqual(len(found["gap GO 3"]), 1)
        self.assertEqual(found["gap FADE 1.5"], [])
        small = _session(101.5)
        small["open"][_at(small, h.M_0920)] = 101.5
        self.assertLess(abs(h.gap_size(small, 100)[0]), 0.03)
        self.assertGreaterEqual(abs(h.gap_size(session, 100)[0]), 0.03)

        fade = _session(110)
        fade["open"][_at(fade, h.M_0920)] = 110
        for minute in range(h.M_0920, h.M_0930 + 1, 5):
            _set(fade, minute, 110, high=110, low=109)
            fade["open"][_at(fade, minute)] = 110
        _set(fade, h.M_1000, 104, high=110, low=104)
        for minute in range(h.M_1000 + 5, h.M_1510 + 1, 5):
            _set(fade, minute, 104, high=110, low=104)
        trade = h.fade_trade(fade, day1, "ABC", 110, 105, 95, 100, "down", False)
        self.assertIsNotNone(trade)
        self.assertLess(trade["r_before"], 0)

        quiet = _session(100, volume=100)
        _set(quiet, h.M_1000, 98.2, high=98.2, low=98.2)
        self.assertIsNotNone(h.vwap_trade(quiet, day1, "ABC", 1.5, "sideways", True))
        self.assertIsNone(h.vwap_trade(quiet, day1, "ABC", 2.0, "sideways", True))
        self.assertIsNone(h.vwap_trade(quiet, day1, "ABC", 1.5, "up", True))

    def test_random_excess_and_the_pass_mark(self):
        day = datetime.date(2016, 3, 2)
        trades = [{
            "date": day, "symbol": "ABC", "r_before": 1.0, "r_after": 1.0,
            "regime": "up", "large": True, "window_r": [1.0, 3.0],
        }]
        h.apply_random(trades, 2, 20261106)
        again = [{
            "date": day, "symbol": "ABC", "r_before": 1.0, "r_after": 1.0,
            "regime": "up", "large": True, "window_r": [1.0, 3.0],
        }]
        h.apply_random(again, 2, 20261106)
        self.assertEqual(trades[0]["excess"], again[0]["excess"])
        self.assertIn(trades[0]["excess"], (1.0 - 1.0, 1.0 - 3.0, 1.0 - 2.0))
        flat = [{
            "date": day, "symbol": "NIFTY 50", "r_before": 0.2, "r_after": 0.2,
            "regime": "up", "large": True, "window_r": [0.2],
        }]
        h.apply_random(flat, 5, 1)
        self.assertEqual(flat[0]["excess"], 0.0)
        dust = [{
            "date": day, "symbol": "NIFTY 50", "r_before": 0.2, "r_after": 0.2,
            "regime": "up", "large": True, "window_r": [0.2 + 1e-15],
        }]
        h.apply_random(dust, 4, 1)
        self.assertEqual(dust[0]["excess"], 0.0)

        good = _block()
        family = [_block(t=4.0), _block(t=2.5), _block(t=2.01)]
        self.assertEqual(h.judge_intraday(good, family)["result"], "PASS")
        edge = _block(avg_after=0.10, t=3.0)
        reasons = h.judge_intraday(edge, family)["reasons"]
        self.assertTrue(any("t vs random" in reason for reason in reasons))
        self.assertFalse(any("below +0.10" in reason for reason in reasons))
        thin = [_block(t=4.0), _block(t=2.0), _block(t=2.0)]
        self.assertTrue(any("family" in reason for reason in h.judge_intraday(good, thin)["reasons"]))
        empty = _block(up=None)
        self.assertTrue(any(reason.startswith("up ") for reason in h.judge_intraday(empty, family)["reasons"]))

    def test_install_leaves_attempt_11_and_the_forward_test(self):
        folder = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, folder)
        path = os.path.join(folder, "EXPERIMENTS.md")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("\n".join([
                "| 11 | 2026-11-06 | mom 12-1 K20 above200 | r | d | 1 | +35% | +4.82 | PASS |",
                "",
                "## Attempt 11",
                "",
                "Rules fixed on 2026-11-06, before the run.",
                "",
                "### Survivorship calibration",
                "",
                "PASS in-sample, but inflated by survivorship bias",
                "",
                "## Forward test",
                "",
                "Started.",
                "",
            ]))
        h.install_intraday(path, h.intraday_rules("2026-11-07"), [])
        with open(path, encoding="utf-8") as fh:
            early = fh.read()
        self.assertIn("| 11 |", early)
        self.assertIn("PASS in-sample, but inflated by survivorship bias", early)
        self.assertLess(early.find("## Attempt 12"), early.find("## Forward test"))
        self.assertIn("Started.", early)
        self.assertNotIn("| 12 |", early)
        block = _block(name="NR7")
        block["verdict"] = {"result": "FAIL", "reasons": ["trades 300 is below 300"]}
        block["trades"] = 10
        block["days"] = 4
        h.install_intraday(path, h.intraday_report("2026-11-07", [block]), h.intraday_rows("2026-11-07", [block]))
        h.install_intraday(path, h.intraday_report("2026-11-07", [block]), h.intraday_rows("2026-11-07", [block]))
        with open(path, encoding="utf-8") as fh:
            later = fh.read()
        self.assertEqual(later.count("| 12 |"), 1)
        self.assertEqual(later.count("## Attempt 12"), 1)
        self.assertIn("| 11 |", later)
        self.assertIn("## Forward test", later)
        self.assertNotIn("\u2014", later)
