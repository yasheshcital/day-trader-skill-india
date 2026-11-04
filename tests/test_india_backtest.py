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
NIFTY50 = os.path.join(FIX, "india", "nifty50")
# An independent run of 15m or-mid 2R on the six stock files, all 60 sessions.
INDEPENDENT_TRADES = 173
INDEPENDENT_R = -0.13
INDEPENDENT_NET = -0.34
# An independent run of the same rule on tests/fixtures/india/nifty50.
NIFTY50_RULE = {"or_minutes": 15, "stop": "or_mid", "target_r": 2.0}
NIFTY50_BUY = (1457, -0.05, -0.22)
NIFTY50_SELL = (1796, 0.14, -0.04)
# After the market filter waits for NIFTY's own break. 30m or-mid 2R, both sides.
MARKET_RULE = {"or_minutes": 30, "stop": "or_mid", "target_r": 2.0}
MARKET_TRADES = 1618
MARKET_R = 0.18
MARKET_NET = 0.03


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

    def test_summary_prints_only_the_all_block(self):
        code, text, err = _run([STOCKS, "--symbols", "SBIN", "--summary", "--write", os.devnull])
        self.assertEqual(code, 0, err)
        self.assertIn("ALL", text)
        self.assertIn("FAIL:", text)
        self.assertNotIn("short left out", text)
        self.assertNotIn("SBIN  (", text)

    def test_nifty50_15m_or_mid_2r_buy_and_sell(self):
        loaded = bt.load_folder(NIFTY50, self.tm)
        buy = bt.run_loaded(loaded, self.tm, side="buy", ruleset=[NIFTY50_RULE], folder=NIFTY50)
        sell = bt.run_loaded(loaded, self.tm, side="sell", ruleset=[NIFTY50_RULE], folder=NIFTY50)
        _print_side("buy", buy, NIFTY50_BUY)
        _print_side("sell", sell, NIFTY50_SELL)
        _assert_count(self, buy, NIFTY50_BUY[0])
        _assert_count(self, sell, NIFTY50_SELL[0])
        self.assertEqual(len(loaded), 50)

    def test_a_short_is_sized_and_the_buy_is_the_exit(self):
        # Distance to the stop, not entry minus stop: a short stop sits above the entry.
        self.assertEqual(bt.whole_shares(100, 102, 500, 100000), 250)
        self.assertEqual(bt.whole_shares(100, 99, 500, 100000), 500)
        # Sell 1000 to open, buy 1010 to cover. STT stays on the sell, stamp on the buy.
        self.assertEqual(bt.round_trip_for("sell", 1000, 1010, 10), costs.round_trip(1010, 1000, 10))
        self.assertNotEqual(costs.round_trip(1000, 1010, 10), costs.round_trip(1010, 1000, 10))

    def test_pass_mark_names_each_miss(self):
        rule = _fake_rule(trades=149, net=-0.120, first=-0.169, second=-0.082, stock_nets=[-0.1, 0.2])
        got = bt.judge(rule)
        self.assertEqual(got["result"], "FAIL")
        self.assertIn("average R after costs -0.120 < +0.10", got["reasons"])
        self.assertIn("first half -0.169 is not above 0 after costs", got["reasons"])
        self.assertIn("second half -0.082 is not above 0 after costs", got["reasons"])
        self.assertTrue(any("need 60%" in reason for reason in got["reasons"]))
        passed = _fake_rule(trades=100, net=0.10, first=0.01, second=0.20, stock_nets=[0.1, 0.2, 0.3, -0.1, -0.2])
        self.assertEqual(bt.judge(passed)["result"], "PASS")
        self.assertEqual(bt.judge(passed)["reasons"], [])

    def test_inplay_gap_volume_and_warmup(self):
        # Ten flat sessions, then one candidate. Opening range is 15 minutes (3 bars).
        base = [("2026-08-%02d" % (i + 1), 100, 100, 100) for i in range(10)]
        sessions = _sessions(base + [("2026-08-11", 101, 100, 100)])
        dates, skipped = bt.dates_for(sessions, "buy", ["inplay"], 15, {})
        self.assertEqual(skipped, 10)
        self.assertEqual(dates, {"2026-08-11"})  # |101 - 100| / 100 = 1.0% exactly
        # The same gap on a warmup day is skipped, not traded.
        early = _sessions([("2026-08-01", 110, 100, 100)] + base[1:])
        dates, skipped = bt.dates_for(early, "buy", ["inplay"], 15, {})
        self.assertEqual(skipped, 10)
        self.assertEqual(dates, set())
        # 0.5% is not a gap, and 300 volume against a 300 average is not 2x.
        quiet = _sessions(base + [("2026-08-11", 100.5, 100, 100)])
        self.assertEqual(bt.dates_for(quiet, "buy", ["inplay"], 15, {})[0], set())
        # No gap, but today's opening-range volume is exactly twice the previous 10.
        loud = _sessions(base + [("2026-08-11", 100, 100, 200)])
        self.assertEqual(bt.dates_for(loud, "buy", ["inplay"], 15, {})[0], {"2026-08-11"})
        short = _sessions(base + [("2026-08-11", 100, 100, 199)])
        self.assertEqual(bt.dates_for(short, "buy", ["inplay"], 15, {})[0], set())

    def test_market_filter_on_synthetic_days(self):
        up = _flat_bars()
        up[3]["c"] = 102
        up[3]["h"] = 102
        self.assertEqual(bt.market_bias(up, 15, self.tm), ("buy", 9 * 60 + 35))
        down = _flat_bars()
        down[3]["c"] = 98
        down[3]["l"] = 98
        self.assertEqual(bt.market_bias(down, 15, self.tm), ("sell", 9 * 60 + 35))
        late = _flat_bars()
        late[63]["c"] = 110  # 14:35, after the 14:30 cutoff
        late[63]["h"] = 110
        self.assertEqual(bt.market_bias(late, 15, self.tm), (None, None))
        # The first close beyond the range decides, even if the next bar reverses.
        first = _flat_bars()
        first[3]["c"] = 102
        first[4]["c"] = 90
        self.assertEqual(bt.market_bias(first, 15, self.tm)[0], "buy")
        # In play and a down index: shorts only.
        base = [("2026-08-%02d" % (i + 1), 100, 100, 100) for i in range(10)]
        sessions = _sessions(base + [("2026-08-11", 101, 100, 100)])
        bias = {"2026-08-11": ("sell", 13 * 60)}
        self.assertEqual(bt.dates_for(sessions, "buy", ["inplay", "market"], 15, bias)[0], set())
        self.assertEqual(bt.dates_for(sessions, "sell", ["inplay", "market"], 15, bias)[0], {"2026-08-11"})
        self.assertEqual(bt.dates_for(sessions, "buy", ["market"], 15, {"2026-08-11": (None, None)})[0], set())

    def test_a_stock_waits_for_nifty_signal(self):
        # 30-minute range ends 09:45. Bar 6 closes 09:50, bar 44 closes 13:00, bar 45 closes 13:05.
        nifty = _priced({44: 110})
        self.assertEqual(bt.market_bias(nifty, 30, self.tm), ("buy", 13 * 60))
        rule = {"or_minutes": 30, "stop": "or_mid", "target_r": 2.0}
        both = _priced({6: 110, 44: 104})
        _hist, rows = _one_day(self, both, rule, 13 * 60)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["entry_min"], 13 * 60)
        self.assertEqual(rows[0]["entry"], 104)
        later = _priced({6: 110, 45: 104})
        _hist, rows = _one_day(self, later, rule, 13 * 60)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["entry_min"], 13 * 60 + 5)
        early_only = _priced({6: 110})
        _hist, rows = _one_day(self, early_only, rule, 13 * 60)
        self.assertEqual(rows, [])

    def test_daily_cap_uses_only_entry_time(self):
        rows = [
            {"date": "2026-08-11", "entry_min": 600, "symbol": "BBB", "side": "buy", "R": 5},
            {"date": "2026-08-11", "entry_min": 590, "symbol": "ZZZ", "side": "buy", "R": 2},
            {"date": "2026-08-11", "entry_min": 590, "symbol": "AAA", "side": "buy", "R": -1},
            {"date": "2026-08-12", "entry_min": 600, "symbol": "BBB", "side": "buy", "R": 0},
        ]
        kept = bt.cap_per_day(rows, 1)
        self.assertEqual([(row["date"], row["symbol"]) for row in kept],
                         [("2026-08-11", "AAA"), ("2026-08-12", "BBB")])
        self.assertEqual(bt.cap_per_day(rows, None), rows)

    def test_position_size_and_peak_open(self):
        rows = [
            {"date": "2026-08-11", "entry": 100, "shares": 10, "entry_min": 600, "exit_min": 700},
            {"date": "2026-08-11", "entry": 200, "shares": 5, "entry_min": 650, "exit_min": 800},
            {"date": "2026-08-12", "entry": 50, "shares": 4, "entry_min": 600, "exit_min": 650},
            {"date": "2026-08-12", "entry": 50, "shares": 4, "entry_min": 650, "exit_min": 700},
        ]
        stats = bt.position_stats(rows)
        self.assertEqual(stats["avg_rupees"], 600.0)  # (1000 + 1000 + 200 + 200) / 4
        self.assertEqual(stats["peak_open"], 2)  # the second day reuses the slot at 650

    def test_market_30m_or_mid_2r_after_the_fix(self):
        loaded = bt.load_folder(NIFTY50, self.tm)
        _sym, sessions, _short = bt.load_sessions(NIFTY, self.tm)
        report = bt.run_loaded(loaded, self.tm, side="both", filters=["market"],
                               market_sessions=sessions, ruleset=[MARKET_RULE],
                               folder=NIFTY50, market=NIFTY)
        block = report["rules"][0]["combined"]["all"]
        off = 100.0 * (block["trades"] - MARKET_TRADES) / MARKET_TRADES
        print("nifty50 market 30m or-mid 2R: trades %d (independent %d, %+.1f%%), avg R %s (about %s), "
              "avg R after costs %s (about %s)" % (
                  block["trades"], MARKET_TRADES, off, block["avg_R"], MARKET_R,
                  block["avg_R_after_costs"], MARKET_NET))
        self.assertLessEqual(abs(block["trades"] - MARKET_TRADES), 0.02 * MARKET_TRADES,
                             "trade count %d is more than 2%% away from %d" % (block["trades"], MARKET_TRADES))


def _print_side(side, report, independent):
    block = report["rules"][0]["combined"]["all"]
    trades, before, after = independent
    off = 100.0 * (block["trades"] - trades) / trades
    print("nifty50 15m or-mid 2R %s: trades %d (independent %d, %+.1f%%), avg R %s (about %s), "
          "avg R after costs %s (about %s)" % (
              side, block["trades"], trades, off, block["avg_R"], before,
              block["avg_R_after_costs"], after))


def _assert_count(case, report, expect):
    got = report["rules"][0]["combined"]["all"]["trades"]
    case.assertLessEqual(abs(got - expect), 0.02 * expect,
                         "trade count %d is more than 2%% away from %d" % (got, expect))


def _fake_rule(trades, net, first, second, stock_nets):
    def block(n, value):
        return {"trades": n, "win_rate": None, "avg_R": value, "avg_R_after_costs": value, "rupees": 0.0}
    symbols = {}
    for i, value in enumerate(stock_nets):
        symbols["S%d" % i] = {"summary": {"all": block(1, value), "first_half": block(0, None),
                                           "second_half": block(0, None)}}
    return {
        "combined": {"all": block(trades, net), "first_half": block(trades // 2, first),
                     "second_half": block(trades - trades // 2, second)},
        "symbols": symbols,
    }


def _bar(price, volume):
    return {"o": price, "h": price, "l": price, "c": price, "v": volume}


def _sessions(spec):
    """spec rows are (date, open, close, volume on each of the first 3 bars)."""
    out = []
    for date, opened, close, volume in spec:
        bars = [_bar(close, volume) for _i in range(3)]
        bars[0]["o"] = opened
        out.append((date, bars))
    return out


def _priced(closes):
    """75 bars at 100, with a few closes replaced. The 30-minute range is bars 0 to 5."""
    bars = []
    for i in range(75):
        close = closes.get(i, 100)
        bars.append({"o": 100, "h": max(100, close), "l": min(100, close), "c": close, "v": 0})
    return bars


def _one_day(case, bars, rule, not_before):
    return bt.score_symbol(
        case.tm, [("2026-08-11", bars)], "RELIANCE", rule, 500, 100000, "buy",
        keep={"2026-08-11"}, not_before={"2026-08-11": not_before})


def _flat_bars():
    # 75 bars inside a 99-101 opening range, so a later close can leave it.
    bars = []
    for _i in range(75):
        bars.append({"o": 100, "h": 101, "l": 99, "c": 100, "v": 0})
    return bars


def _run(argv):
    import io
    from contextlib import redirect_stderr, redirect_stdout
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = bt.main(argv)
    return code, out.getvalue(), err.getvalue()


if __name__ == "__main__":
    unittest.main()
