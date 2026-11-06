"""Strategy harness, batch 1. Synthetic bars only. No kite cache is read."""

import datetime
import os
import random
import shutil
import tempfile
import unittest

from _load import load

lab = load("india/research", "signal_lab")
h = load("india/research", "harness")
data = load("india/research", "data")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

NAMES = [
    "turtle 20/10", "turtle 55/20", "turtle 55/20 up",
    "mom 12-1 K20", "mom 12-1 K30", "mom 12-1 K20 above200",
    "52w-high K20", "52w-high K30", "52w-high K20 above200",
    "faber 10m", "faber 8m", "faber 12m",
]


def _day(i, price, high=None, low=None, open_=None, volume=1, close=None):
    return {
        "date": datetime.date(2010, 1, 1) + datetime.timedelta(days=i),
        "open": price if open_ is None else open_,
        "high": price if high is None else high,
        "low": price if low is None else low,
        "close": price if close is None else close,
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


def _good():
    return {
        "t": 3.1, "early": 0.2, "late": 0.3,
        "up": 0.1, "down": 0.2, "sideways": 0.3,
        "beats": 95, "large_excess": 0.4,
        "cagr": 13.0, "max_dd": -50.0, "calmar": 13.0 / 50.0,
    }


class CostsAndBook(unittest.TestCase):
    def test_round_trip_matches_the_delivery_schedule(self):
        buy = 100.0 * 1000
        sell = 110.0 * 1000
        cost = h.trade_cost(buy, True) + h.trade_cost(sell, False)
        net = sell - buy - cost
        self.assertAlmostEqual(net, 9752.05254, places=4)
        _pct, rupees = lab.delivery(100, 110)
        self.assertAlmostEqual(rupees, net, places=4)
        # Buy-side costs come out of the rupee slot, so 100 is not a full 1,000 shares.
        self.assertEqual(h.shares_for(100000, 100), 998)
        self.assertLess(998 * 100 + h.trade_cost(998 * 100, True), 100000)

    def test_idle_cash_earns_nifty_and_a_quiet_book_has_no_excess(self):
        start = datetime.date(2010, 1, 4)
        mid = datetime.date(2010, 1, 29)
        end = datetime.date(2010, 2, 26)
        calendar = [start, mid, end]
        nifty = {
            start: {"open": 100.0, "close": 110.0},
            mid: {"open": 110.0, "close": 120.0},
            end: {"open": 120.0, "close": 150.0},
        }
        equity = h.simulate_trades([], calendar, nifty, capital=100000.0)
        self.assertEqual(equity, h.nifty_path(calendar, nifty, 100000.0))
        self.assertAlmostEqual(equity[-1], 150000.0)
        regimes = {start: "up", end: "down"}
        stats = h.path_stats(calendar, equity, 100000.0, nifty, regimes)
        self.assertAlmostEqual(stats["excess"], 0.0, places=8)
        self.assertEqual(stats["t"], 0.0)

    def test_faber_cash_earns_nothing_and_the_average_includes_this_close(self):
        self.assertIs(h.faber_on([100.0, 100.0], 2), False)
        self.assertIs(h.faber_on([100.0, 130.0], 2), True)
        start = datetime.date(2010, 1, 4)
        end = datetime.date(2011, 1, 4)
        calendar = [start, end]
        nifty = {
            start: {"open": 100.0, "close": 100.0},
            end: {"open": 200.0, "close": 200.0},
        }
        equity = h.simulate_faber([], {}, calendar, nifty, capital=1000.0)
        self.assertEqual(equity, [1000.0, 1000.0])
        self.assertEqual(h.cagr_of(calendar, equity, 1000.0), 0.0)
        signal = datetime.date(2004, 12, 31)
        reb = datetime.date(2005, 1, 3)
        ends = [(datetime.date(2004, 3, 31), 100.0)]
        # Nine more month-ends at 100, then the signal at 130. Average of the last 10 is 103.
        for month in range(4, 12):
            ends.append((datetime.date(2004, month, 28), 100.0))
        ends.append((signal, 130.0))
        holds = h.faber_holds([(signal, reb)], ends, 10, None)
        self.assertTrue(holds[signal])
        flat = list(ends)
        flat[-1] = (signal, 100.0)
        self.assertFalse(h.faber_holds([(signal, reb)], flat, 10, None)[signal])
        coin_a = h.faber_holds([(signal, reb), (reb, end)], [], 10, random.Random(3))
        coin_b = h.faber_holds([(signal, reb), (reb, end)], [], 10, random.Random(3))
        self.assertEqual(coin_a, coin_b)


class TurtleRules(unittest.TestCase):
    def test_stop_beats_the_channel_and_a_gap_fills_at_the_open(self):
        seg = lab.segment_from_rows([
            _day(0, 100, high=101, low=97, open_=100, close=96),
            _day(1, 90),
        ])
        # Entry 100, ATR 1, stop 98. The low trades through the stop.
        self.assertEqual(h.turtle_exit(seg, 0, 1, 1.0, [100, 100]), (0, 98.0, False))
        gap = lab.segment_from_rows([
            _day(0, 100, high=101, low=99, open_=100, close=100),
            _day(1, 90, high=90, low=80, open_=90, close=90),
        ])
        self.assertEqual(h.turtle_exit(gap, 0, 1, 1.0, [100, 100]), (1, 90.0, True))
        channel = lab.segment_from_rows([
            _day(0, 100, high=101, low=99, open_=100, close=95),
            _day(1, 94, open_=94),
        ])
        self.assertEqual(h.turtle_exit(channel, 0, 1, 1.0, [100, 100]), (1, 94.0, True))
        self.assertEqual(seg.date[0], datetime.date(2010, 1, 1))
        self.assertEqual(channel.date[1], datetime.date(2010, 1, 2))

    def test_entry_is_the_next_open(self):
        rows = [_day(i, 10, high=10, low=10, open_=10) for i in range(25)]
        rows[20]["close"] = 20
        rows[20]["high"] = 20
        rows[21]["open"] = 11
        seg = lab.segment_from_rows(rows)
        h.prepare(seg)
        symbol = {"name": "AAA", "segments": [seg]}
        universe = dict((row["date"], set(["AAA"])) for row in rows)
        trades = h.collect_turtle(
            [symbol], universe, {}, 20, 10, False, 5, rows[0]["date"], rows[-1]["date"])
        self.assertEqual(len(trades), 1)
        self.assertEqual(trades[0]["entry"], 11)
        self.assertNotEqual(trades[0]["entry"], 20)
        self.assertEqual(trades[0]["entry_date"], rows[21]["date"])

    def test_a_down_day_does_not_use_up_the_symbol(self):
        rows = [_day(i, 10, high=10, low=10, open_=10) for i in range(30)]
        rows[20]["close"] = 20
        rows[20]["high"] = 20
        rows[21]["open"] = 11
        rows[21]["close"] = 11
        rows[21]["high"] = 11
        rows[21]["low"] = 11
        rows[22]["open"] = 21
        rows[22]["close"] = 21
        rows[22]["high"] = 21
        rows[22]["low"] = 11
        rows[23]["open"] = 12
        rows[23]["high"] = 15
        rows[23]["low"] = 12
        rows[23]["close"] = 15
        for row in rows[24:]:
            row["open"] = 15
            row["high"] = 15
            row["low"] = 15
            row["close"] = 15
        seg = lab.segment_from_rows(rows)
        h.prepare(seg)
        symbol = {"name": "AAA", "segments": [seg]}
        universe = dict((row["date"], set(["AAA"])) for row in rows)
        start, end = rows[0]["date"], rows[-1]["date"]
        blocked = h.collect_turtle(
            [symbol], universe, {rows[21]["date"]: "sideways", rows[23]["date"]: "up"},
            20, 10, True, 5, start, end)
        self.assertEqual(len(blocked), 1)
        self.assertEqual(blocked[0]["entry"], 12)
        plain = h.collect_turtle([symbol], universe, {}, 20, 10, False, 5, start, end)
        self.assertEqual(plain[0]["entry"], 11)
        self.assertEqual(len(plain), 1)

    def test_the_higher_turnover_gets_the_only_slot(self):
        rows = [_day(i, 100) for i in range(3)]
        seg = lab.segment_from_rows(rows)
        h.prepare(seg)
        calendar = [row["date"] for row in rows]
        nifty = dict((day, {"open": 100.0, "close": 100.0}) for day in calendar)

        def trade(name, turnover, fill):
            return {
                "name": name, "seg": seg, "entry_date": calendar[0], "exit_date": calendar[1],
                "entry": 100.0, "fill": fill, "at_open": True, "turnover": turnover,
            }

        winner = h.simulate_trades(
            [trade("AAA", 1.0, 100.0), trade("BBB", 9.0, 200.0)],
            calendar, nifty, capital=100000.0, slots=1)
        self.assertGreater(winner[-1], 150000.0)
        tie = h.simulate_trades(
            [trade("BBB", 5.0, 200.0), trade("AAA", 5.0, 100.0)],
            calendar, nifty, capital=100000.0, slots=1)
        self.assertLess(tie[-1], 100000.0)


class PortfolioRules(unittest.TestCase):
    def test_scores_and_the_top_name(self):
        rows = [_day(i, 1.0) for i in range(253)]
        rows[0]["close"] = 50
        rows[0]["high"] = 50
        rows[231]["close"] = 80
        rows[231]["high"] = 80
        mom = lab.segment_from_rows(rows)
        self.assertAlmostEqual(h.momentum_score(mom, 252), 80.0 / 50.0 - 1.0)
        high_rows = [_day(i, 10, high=10) for i in range(253)]
        high_rows[252]["high"] = 100
        high_rows[252]["close"] = 12
        high = lab.segment_from_rows(high_rows)
        self.assertAlmostEqual(h.high_score(high, 252), 1.2)

        signal = datetime.date(2010, 6, 1)
        reb = datetime.date(2010, 6, 2)
        weak = lab.segment_from_rows([_day(0, 8), _day(1, 8)])
        strong = lab.segment_from_rows([_day(0, 10), _day(1, 10)])
        weak.date = [signal, reb]
        strong.date = [signal, reb]
        weak.high252 = [10.0, 10.0]
        strong.high252 = [10.0, 10.0]
        weak.c[0] = 8.0
        strong.c[0] = 10.0
        by_name = {
            "BBB": {signal: (strong, 0), reb: (strong, 1)},
            "AAA": {signal: (weak, 0), reb: (weak, 1)},
        }
        universe = {signal: set(["AAA", "BBB"])}
        spec = {"kind": "high", "k": 1, "filter": False}
        self.assertEqual(h.select_names(spec, signal, reb, universe, by_name, {}, None), ["BBB"])
        weak.c[0] = 10.0
        self.assertEqual(h.select_names(spec, signal, reb, universe, by_name, {}, None), ["AAA"])
        spec["filter"] = True
        self.assertEqual(h.select_names(spec, signal, reb, universe, by_name, {signal: False}, None), [])
        self.assertEqual(
            h.select_names(spec, signal, reb, universe, by_name, {signal: False}, random.Random(1)),
            [])
        first = h._sample(random.Random(7), ["CCC", "AAA", "BBB"], 2)
        second = h._sample(random.Random(7), ["BBB", "CCC", "AAA"], 2)
        self.assertEqual(first, second)

    def test_an_unchanged_holding_is_not_traded_again(self):
        day = datetime.date(2010, 6, 2)
        seg = lab.segment_from_rows([_day(0, 100)])
        seg.date = [day]
        seg.idx = {day: 0}
        price = 100.0
        budget = 10020.0
        shares = h.shares_for(budget, price)
        book = h.Book(budget, park=True)
        book.cash = budget - shares * price
        book.nifty_shares = 0.0
        book.pos["AAA"] = {"shares": shares, "seg": seg, "last": price}
        before = book.cash + book.nifty_shares * price + shares * price
        h._rebalance(book, ["AAA"], day, 100.0, {"AAA": {day: (seg, 0)}})
        after = book.value(day, 100.0, "c")
        self.assertEqual(book.pos["AAA"]["shares"], shares)
        self.assertAlmostEqual(after, before, places=6)

    def test_december_rebalances_on_the_first_session_of_january(self):
        dec = datetime.date(2004, 12, 31)
        jan = datetime.date(2005, 1, 3)
        month_end = datetime.date(2005, 1, 31)
        feb = datetime.date(2005, 2, 1)
        pairs = h.month_pairs([dec, jan, month_end, feb], [jan, month_end, feb])
        self.assertEqual(pairs, [(dec, jan), (month_end, feb)])


class StatsAndPassMark(unittest.TestCase):
    def test_cagr_drawdown_and_worst_year(self):
        start = datetime.date(2005, 1, 1)
        end = datetime.date(2015, 1, 1)
        nifty = {
            start: {"open": 100.0, "close": 100.0},
            end: {"open": 200.0, "close": 200.0},
        }
        stats = h.path_stats([start, end], [100.0, 200.0], 100.0, nifty, {})
        years = (end - start).days / 365.25
        expected = (2.0 ** (1.0 / years) - 1.0) * 100.0
        self.assertAlmostEqual(stats["cagr"], expected, places=6)
        self.assertGreater(stats["cagr"], 7.0)
        self.assertLess(stats["cagr"], 7.3)
        dipped_dates = [
            datetime.date(2010, 1, 4), datetime.date(2010, 6, 1), datetime.date(2010, 12, 31)]
        dipped_nifty = dict((day, {"open": 100.0, "close": 100.0}) for day in dipped_dates)
        dipped = h.path_stats(dipped_dates, [100.0, 50.0, 80.0], 100.0, dipped_nifty, {})
        self.assertAlmostEqual(dipped["max_dd"], -50.0)
        self.assertAlmostEqual(dipped["worst_year"], -20.0)
        values = [1.0, 3.0, 2.0]
        self.assertAlmostEqual(h.t_stat(values), 2.0 * (3.0 ** 0.5))

    def test_the_pass_mark_and_each_miss(self):
        nifty = {"cagr": 10.0, "max_dd": -40.0, "calmar": 0.25}
        self.assertEqual(h.judge(_good(), nifty)["result"], "PASS")
        path2 = _good()
        path2["cagr"] = 10.0
        path2["max_dd"] = -20.0
        path2["calmar"] = 0.5
        self.assertEqual(h.judge(path2, nifty)["result"], "PASS")
        neither = _good()
        neither["cagr"] = 10.0
        neither["max_dd"] = -40.0
        neither["calmar"] = 0.25
        self.assertIn("neither path", h.judge(neither, nifty)["reasons"][-1])
        tight = _good()
        tight["t"] = 3.0
        self.assertIn("excess t", h.judge(tight, nifty)["reasons"][0])
        early = _good()
        early["early"] = 0.0
        self.assertIn("2005-2014 excess", h.judge(early, nifty)["reasons"][0])
        late = _good()
        late["late"] = -0.1
        self.assertIn("2015-2024 excess", h.judge(late, nifty)["reasons"][0])
        side = _good()
        side["sideways"] = None
        self.assertIn("sideways", "; ".join(h.judge(side, nifty)["reasons"]))
        short = _good()
        short["beats"] = 94
        self.assertIn("beats random 94 of 100, need 95", "; ".join(h.judge(short, nifty)["reasons"]))
        large = _good()
        large["large_excess"] = 0.0
        self.assertIn("large-cap excess", "; ".join(h.judge(large, nifty)["reasons"]))
        exact = _good()
        exact["beats"] = 95
        exact["max_dd"] = -50.0
        self.assertEqual(h.judge(exact, nifty)["result"], "PASS")

    def test_batch_is_twelve_variants_in_fours_of_three(self):
        specs = h.batch1()
        self.assertEqual([spec["name"] for spec in specs], NAMES)
        self.assertEqual([len(group) for _kind, group in h.families(specs)], [3, 3, 3, 3])
        self.assertEqual(h.RUNS, 100)
        self.assertEqual(h.CAPITAL, 1000000.0)
        self.assertEqual(h.SLOTS, 10)
        self.assertEqual(h.SEED, 20261106)


class RulesCatalogueAndHoldout(unittest.TestCase):
    def test_rules_name_every_variant_and_the_pass_mark(self):
        text = h.rules_text("2026-11-06")
        self.assertIn("Rules fixed on 2026-11-06, before the run.", text)
        self.assertIn("Results are filled in after the run.", text)
        self.assertIn("t above 3", text)
        self.assertIn("both decades", text)
        self.assertIn("at least 95", text)
        self.assertIn("large-cap", text)
        self.assertIn("plus 3", text)
        self.assertIn("10 percentage points", text)
        self.assertIn("1.5", text)
        self.assertIn("Idle cash is held in the NIFTY 50", text)
        self.assertIn("cash at 0", text)
        self.assertIn("Dividends are excluded", text)
        for name in NAMES:
            self.assertIn(name, text)
        self.assertNotIn("\u2014", text)

    def test_install_writes_rules_before_results_and_keeps_attempt_10(self):
        folder = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, folder)
        path = os.path.join(folder, "EXPERIMENTS.md")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("\n".join([
                "| 10 | 2026-11-06 | old row | r | d | 1 | +0.1% | +0.10 | FAIL |",
                "",
                "## Attempt 10",
                "",
                "Kept.",
                "",
                "## Forward test",
                "",
                "Started.",
                "",
            ]))
        h.install(path, h.rules_text("2026-11-06"), [])
        with open(path, encoding="utf-8") as fh:
            early = fh.read()
        self.assertIn("Results are filled in after the run.", early)
        self.assertNotIn("| 11 |", early)
        self.assertIn("| 10 |", early)
        self.assertIn("Kept.", early)
        self.assertLess(early.find("## Attempt 11"), early.find("## Forward test"))
        block = _good()
        block.update({
            "name": "turtle 20/10", "trades": 4, "verdict": {"result": "FAIL", "reasons": ["no"]},
            "kind": "turtle", "n_months": 2, "yearly": {2010: 1.0},
        })
        nifty = {"cagr": 10.0, "max_dd": -40.0, "calmar": 0.25, "worst_year": -20.0, "name": "NIFTY 50"}
        h.install(path, h.results_text("2026-11-06", [block], nifty), h.table_rows("2026-11-06", [block]))
        with open(path, encoding="utf-8") as fh:
            later = fh.read()
        self.assertNotIn("Results are filled in after the run.", later)
        self.assertIn("| 11 |", later)
        self.assertIn("| 10 |", later)
        self.assertIn("turtle 20/10", later)
        self.assertLess(later.find("## Attempt 11"), later.find("## Forward test"))
        self.assertLess(later.find("| 10 |"), later.find("| 11 |"))
        self.assertIn("CAGR and the monthly t, not R", later)

    def test_the_catalogue_lists_twenty_strategies(self):
        path = os.path.join(ROOT, "india", "research", "STRATEGIES.md")
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        for name in (
            "Turtle breakout",
            "Cross-sectional momentum",
            "52-week-high momentum",
            "Minervini trend template + VCP",
            "Weinstein stage analysis",
            "Darvas box",
            "Time-series momentum / Faber 10-month timing",
            "Connors RSI(2)",
            "IBS",
            "Short-term reversal",
            "Pairs trading",
            "Turtle Soup",
            "Crabel NR7/NR4",
            "Raschke Holy Grail",
            "Intraday momentum (Gao et al. 2018)",
            "Gap and go vs gap fade",
            "VWAP reversion",
            "Turn of the month",
            "F&O expiry week",
            "Volatility-regime switching",
        ):
            self.assertIn(name, text)
        self.assertIn("opening-range breakout", text)
        self.assertIn("single technical-signal", text)
        self.assertIn("Attempts 1 to 10", text)
        for row_name in ("Turtle breakout", "Cross-sectional momentum", "52-week-high momentum"):
            line = [line for line in text.splitlines() if line.startswith("| %s |" % row_name)][0]
            self.assertIn("| 11 |", line)
        faber = [line for line in text.splitlines() if "Faber 10-month" in line][0]
        self.assertIn("full TSMOM not started", faber)
        self.assertIn("| 11 |", faber)
        self.assertNotIn("\u2014", text)

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
        ctx = h.load_context(kite, end=datetime.date(2024, 12, 31), log=lambda line: None)
        names = [symbol["name"] for symbol in ctx["loaded"]]
        self.assertNotIn("NIFTY 50", names)
        dates = []
        for symbol in ctx["loaded"]:
            for seg in symbol["segments"]:
                dates.extend(seg.date)
        self.assertTrue(dates)
        self.assertTrue(all(day < data.HOLDOUT_START for day in dates))
        self.assertTrue(all(day < data.HOLDOUT_START for day in ctx["nifty"]))
        self.assertNotIn(99, [seg.c[-1] for symbol in ctx["loaded"] for seg in symbol["segments"]])

    def test_a_small_book_scores_without_the_disk(self):
        rows = [_day(i, 10, high=10, low=10, open_=10) for i in range(25)]
        rows[20]["close"] = 20
        rows[20]["high"] = 20
        rows[21]["open"] = 11
        seg = lab.segment_from_rows(rows)
        h.prepare(seg)
        calendar = [row["date"] for row in rows]
        nifty = dict((day, {"open": 10.0, "close": 10.0}) for day in calendar)
        ctx = {
            "loaded": [{"name": "AAA", "segments": [seg]}],
            "nifty": nifty,
            "regimes": {},
            "top200": dict((day, set(["AAA"])) for day in calendar),
            "top100": dict((day, set(["AAA"])) for day in calendar),
            "by_name": {},
            "calendar": calendar,
            "pairs": [],
            "above": {},
            "month_ends": [],
            "pools": None,
            "start": calendar[0],
            "end": calendar[-1],
            "warmup": 5,
        }
        blocks, bench = h.run(ctx=ctx, runs=1, specs=h.batch1()[:1], log=lambda line: None)
        self.assertEqual(len(blocks), 1)
        self.assertEqual(blocks[0]["name"], "turtle 20/10")
        self.assertIn(blocks[0]["verdict"]["result"], ("PASS", "FAIL"))
        self.assertIn("cagr", bench)
        self.assertGreaterEqual(blocks[0]["trades"], 1)
