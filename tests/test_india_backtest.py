"""Costs and the opening-range batch backtest. The time machine is loaded, not copied."""

import os
import shutil
import tempfile
import unittest
from decimal import Decimal

from _load import FIX, load

costs = load("india", "costs")
bt = load("india", "backtest")

NIFTY = os.path.join(FIX, "india", "NIFTY-2026-08-05_2026-11-03-5m.algotest.json")
STOCKS = os.path.join(FIX, "india", "stocks")
# An independent run of 15m or-mid 2R on the six stock files, all 60 sessions.
INDEPENDENT_TRADES = 173
INDEPENDENT_R = -0.13
INDEPENDENT_NET = -0.34


class Costs(unittest.TestCase):
    def test_a_hand_worked_round_trip(self):
        # buy 1000 x 10 = 10,000; sell 1010 x 10 = 10,100; turnover 20,100.
        # brokerage: min(10,000 x 0.03%, 20) + min(10,100 x 0.03%, 20) = 3 + 3.03 = 6.03
        # STT: 10,100 x 0.025% = 2.525
        # exchange: 20,100 x 0.00297% = 0.59697
        # SEBI: 20,100 x 0.0001% = 0.0201
        # stamp: 10,000 x 0.003% = 0.3
        # GST: 18% of (6.03 + 0.59697 + 0.0201) = 18% of 6.64707 = 1.1964726
        # total = 6.03 + 2.525 + 0.59697 + 0.0201 + 0.3 + 1.1964726 = 10.6685426
        got = costs.breakdown(1000, 1010, 10)
        self.assertEqual(got["brokerage"], Decimal("6.03"))
        self.assertEqual(got["stt"], Decimal("2.525"))
        self.assertEqual(got["exchange"], Decimal("0.59697"))
        self.assertEqual(got["sebi"], Decimal("0.0201"))
        self.assertEqual(got["stamp"], Decimal("0.3"))
        self.assertEqual(got["gst"], Decimal("1.1964726"))
        self.assertEqual(got["total"], Decimal("10.6685426"))
        self.assertEqual(costs.round_trip(1000, 1010, 10), Decimal("10.6685426"))

    def test_brokerage_caps_at_20_per_order(self):
        # 200,000 a side: 0.03% is 60, so each order pays the Rs 20 cap.
        got = costs.breakdown(2000, 2000, 100)
        self.assertEqual(got["brokerage"], Decimal("40"))
        self.assertEqual(costs.breakdown(1000, 1010, 0)["total"], Decimal("0"))


class Backtest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tm = bt.load_timemachine()

    def test_nifty_before_30_oct_matches_the_time_machine(self):
        sym, sessions, _short = bt.load_sessions(NIFTY, self.tm, before="2026-10-30")
        self.assertEqual(sym, "NIFTY")
        hist, _rows = bt.score_symbol(self.tm, sessions, sym, {
            "or_minutes": 15, "stop": "or_mid", "target_r": 2.0,
        }, 500, 100000)
        self.assertEqual((hist["triggered"], hist["target"], hist["stop"], hist["close"]), (31, 6, 14, 11))
        self.assertEqual(hist["avg_R"], -0.091)
        self.assertEqual(len(sessions), 59)

    def test_six_stocks_15m_or_mid_2r(self):
        report = bt.run_folder(STOCKS, tm=self.tm)
        rule = [item for item in report["rules"] if item["name"] == "15m or-mid 2R"][0]
        block = rule["combined"]["all"]
        per = [(sym, item["summary"]["all"]["trades"], item["sessions"])
               for sym, item in sorted(rule["symbols"].items())]
        print("stocks 15m or-mid 2R: trades %d (independent %d), avg R %s (about %s), "
              "avg R after costs %s (about %s)" % (
                  block["trades"], INDEPENDENT_TRADES, block["avg_R"], INDEPENDENT_R,
                  block["avg_R_after_costs"], INDEPENDENT_NET))
        print("per stock (trades, sessions): %s" % per)
        self.assertLessEqual(abs(block["trades"] - INDEPENDENT_TRADES), 3,
                             "trade count %d is more than 3 away from %d" % (block["trades"], INDEPENDENT_TRADES))
        self.assertEqual(len(report["symbols"]), 6)
        for item in rule["symbols"].values():
            self.assertEqual(item["sessions"], 60)

    def test_the_table_and_json_write(self):
        tmp = tempfile.mkdtemp()
        try:
            code, text, err = _run([STOCKS, "--symbols", "SBIN", "--write", os.path.join(tmp, "out.json")])
            self.assertEqual(code, 0, err)
            self.assertIn("15m or-mid 2R", text)
            self.assertIn("first half", text)
            self.assertIn("second half", text)
            self.assertIn("SBIN", text)
            self.assertNotIn("RELIANCE", text)
            self.assertTrue(os.path.exists(os.path.join(tmp, "out.json")))
        finally:
            shutil.rmtree(tmp)


def _run(argv):
    import io
    from contextlib import redirect_stderr, redirect_stdout
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = bt.main(argv)
    return code, out.getvalue(), err.getvalue()


if __name__ == "__main__":
    unittest.main()
