import hashlib
import io
import json
import os
import random
import shutil
import tempfile
import unittest
import urllib.error
from contextlib import redirect_stdout, redirect_stderr

from _load import load, FIX

tm = load("trader-timemachine", "timemachine")

DIR = os.path.join(FIX, "trader-timemachine")
NIFTY = os.path.join(DIR, "NIFTY-60d5m.json")
with open(NIFTY, encoding="utf-8") as _fh:
    TEXT = _fh.read()
NOW = "2026-10-30 09:40"
NOW_UTC = tm.parse_now(NOW)
DAY = "2026-10-30"

# the plan trader-exit writes for this NIFTY opening-range breakout (2R, flat by 15:10)
PLAN = {"created_by": "trader-exit", "symbol": "NIFTY", "side": "buy", "date": DAY, "setup": "orb",
        "entry": 22990.25, "entry_time": "9:35 AM", "entry_bar": 3, "interval": "5m",
        "opening_range": {"high": 22980.35, "low": 22919.85, "minutes": 15},
        "stop": 22950.10, "stop_rule": "or_mid", "stop_label": "opening-range midpoint",
        "target": 23070.55, "target_r": 2.0, "target_label": "2R (two times the risk)",
        "risk_per_share": 40.15, "reward_risk": 2.0, "flat_by": "15:10"}

# seed 19 on this fixture. Two runs match, and these pins catch a drift in the draws.
BANDS = "95786e16c980fc42"
PATHS = "7cc72b2452ad7a09"


def sha(x):
    return hashlib.sha256(json.dumps(x).encode("utf-8")).hexdigest()[:16]


def plan(**kw):
    raw = dict(PLAN)
    raw.update(kw)
    return tm.normalize_plan(raw)


def machine(p=None, text=TEXT, now=NOW_UTC, **kw):
    return tm.time_machine(text, p or plan(), now, source="offline", **kw)


def edited(fn):
    """The fixture's chart JSON, changed by fn(result), back as text."""
    doc = json.loads(TEXT)
    fn(doc["chart"]["result"][0])
    return json.dumps(doc)


def keep_bars(result, keep):
    """Keep only the bars where keep(ts) is true."""
    q = result["indicators"]["quote"][0]
    idx = [i for i, ts in enumerate(result["timestamp"]) if keep(ts)]
    result["timestamp"] = [result["timestamp"][i] for i in idx]
    for k in q:
        q[k] = [q[k][i] for i in idx]


def ist(ts):
    return tm.to_ist(tm.utc_of(ts))


def run(argv):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = tm.main(argv)
    return code, out.getvalue(), err.getvalue()


class Reel(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.doc = machine()
        cls.again = machine()

    def test_seed_19_is_the_same_twice(self):
        self.assertEqual(self.doc["mc"], self.again["mc"])
        self.assertEqual(self.doc["history"], self.again["history"])
        self.assertEqual(self.doc["verdict"], self.again["verdict"])

    def test_the_nifty_odds(self):
        m = self.doc["mc"]
        self.assertEqual((m["replays"], m["seed"], m["window"], m["until"]), (10000, 19, 2, "15:10"))
        self.assertEqual(m["pool_sessions"], 60)
        self.assertEqual(m["bars_left"], 67)
        self.assertEqual((m["pool_from"], m["pool_to"]), ("2026-08-04", "2026-10-29"))
        self.assertEqual(m["p_target"], 0.3644)
        self.assertEqual(m["p_stop"], 0.5844)
        self.assertEqual(m["p_neither"], 0.0512)
        self.assertEqual(m["p_green"], 0.4053)
        self.assertEqual(m["median_close"], 23012.35)
        self.assertEqual(m["p5_close"], 22860.48)
        self.assertEqual(m["p95_close"], 23167.16)
        self.assertEqual(m["avg_R"], 0.173)
        self.assertEqual(m["r_at_target"], 2.0)

    def test_the_draws_do_not_drift(self):
        m = self.doc["mc"]
        self.assertEqual(sha(m["bands"]), BANDS)
        self.assertEqual(len(m["sample_paths"]), 160)
        self.assertEqual(sha(m["sample_paths"]), PATHS)
        self.assertEqual(m["bands"][0], [22990.25] * 5)

    def test_the_history_replay(self):
        h = self.doc["history"]
        self.assertEqual((h["sessions"], h["triggered"]), (60, 49))
        self.assertEqual((h["target"], h["stop"], h["close"], h["green"]), (23, 26, 0, 23))
        self.assertEqual(h["avg_R"], 0.408)
        self.assertEqual(h["rule"], {"setup": "orb", "or_minutes": 15, "stop_rule": "or_mid", "target_r": 2.0})
        first = h["trades"][0]
        self.assertEqual((first["date"], first["entry"], first["stop"], first["target"], first["outcome"]),
                         ("2026-08-04", 23041.9, 23018.0, 23089.7, "target"))

    def test_the_2r_verdict_leans_toward_the_target(self):
        self.assertEqual(self.doc["verdict"],
                         "Leans toward the target: at 2R the target has to come first in 33 % of the replays "
                         "that hit one side; it did in 38 % (target first 36.4 % vs stop first 58.4 %).")
        self.assertEqual(self.doc["verdict_notes"], [])

    def test_bands_start_at_the_entry(self):
        m = self.doc["mc"]
        self.assertEqual(len(m["bands"]), 68)
        self.assertEqual((m["band_times"][0], m["band_times"][-1], len(m["band_times"])), ("09:35", "15:10", 68))
        self.assertTrue(all(p[0] == 22990.25 and len(p) == 68 for p in m["sample_paths"]))

    def test_the_plan_is_carried_through(self):
        p = self.doc["plan"]
        self.assertEqual((p["symbol"], p["entry"], p["stop"], p["target"], p["entry_bar"], p["entry_time"]),
                         ("NIFTY", 22990.25, 22950.10, 23070.55, 3, "9:35 AM"))
        self.assertEqual((p["risk_per_share"], p["target_r"], p["flat_by"]), (40.15, 2.0, "15:10"))
        self.assertEqual(self.doc["warnings"], [])
        self.assertEqual(self.doc["source"], "offline")

    def test_the_text_report(self):
        text = "\n".join(tm.report(self.doc))
        for line in ("NIFTY buy, Friday 2026-10-30: entry ₹22,990.25 at 9:35 AM (bar 3), stop ₹22,950.10, "
                     "target ₹23,070.55 (2R, risk ₹40.15 a share) (saved file).",
                     "10,000 replays", "67 five-minute bars", "seed 19", "60 full sessions",
                     "target first   36.4 %", "stop first     58.4 %", "neither        5.1 %    still open at 3:10 PM",
                     "green          40.5 %", "median ₹23,012.35, 90 % of replays between ₹22,860.48 and ₹23,167.16",
                     "Average R: +0.173", "fired 49 times: 23 target, 26 stop, 0 neither. Average R +0.408",
                     "not a prediction", "--seed 19"):
            self.assertIn(line, text, line)
        self.assertNotIn(" ET", text)
        self.assertNotIn("$", text)
        for word in ("profit", "P&L", "guarantee", "real time", "tick by tick"):
            self.assertNotIn(word, text)


class Seeds(unittest.TestCase):
    def test_same_seed_same_numbers(self):
        a = machine(replays=2000, seed=5)["mc"]
        b = machine(replays=2000, seed=5)["mc"]
        self.assertEqual(a, b)

    def test_another_seed_gives_other_numbers(self):
        m = machine(seed=7)["mc"]
        self.assertNotEqual((m["p_target"], m["p_stop"], m["median_close"]), (0.3644, 0.5844, 23012.35))
        self.assertAlmostEqual(m["p_target"] + m["p_stop"] + m["p_neither"], 1.0, places=6)
        self.assertNotEqual(sha(m["bands"]), BANDS)

    def test_the_draws_are_stable_across_pythons(self):
        r = random.Random(19)
        self.assertEqual([r.randint(-2, 2) for _ in range(8)], [-2, 2, -2, 2, -1, 1, 0, 2])
        self.assertEqual(r.choice(range(60)), 18)

    def test_window_and_replays(self):
        a = machine(replays=500, window=0)["mc"]
        self.assertEqual((a["replays"], a["window"]), (500, 0))
        self.assertNotEqual(a["bands"], machine(replays=500)["mc"]["bands"])
        with self.assertRaises(tm.TMError):
            machine(replays=0)
        with self.assertRaises(tm.TMError):
            machine(window=11)


class Bars(unittest.TestCase):
    def setUp(self):
        self.result = tm.chart_result(TEXT, "NIFTY")

    def test_a_full_session_has_75_bars_and_a_tick_is_dropped(self):
        meta, bars, dropped = tm.parse_bars(self.result, tm.parse_now("2026-10-30 16:00"))
        self.assertEqual(dropped, {"no_price": 0, "off_grid": 0, "not_complete": 0, "outside_hours": 0})
        last = bars[-1]
        self.assertEqual((last["date"], last["start"], last["slot"]), (DAY, "15:25", 74))
        today = [b for b in bars if b["date"] == DAY]
        self.assertEqual(len(today), 75)
        entry = [b for b in today if b["slot"] == 3][0]
        self.assertEqual((entry["start"], entry["c"]), ("09:30", 22990.25))

        def add_tick(res):
            res["timestamp"].append(res["timestamp"][-1] + 45)
            q = res["indicators"]["quote"][0]
            for k in q:
                q[k].append(q[k][-1])

        ticked = tm.parse_bars(tm.chart_result(edited(add_tick), "NIFTY"), tm.parse_now("2026-10-30 16:00"))[2]
        self.assertEqual(ticked["off_grid"], 1)

    def test_now_pins_the_clock(self):
        bars = tm.parse_bars(self.result, tm.parse_now("2026-10-30 09:32"))[1]
        today = [b for b in bars if b["date"] == DAY]
        self.assertEqual(len(today), 3)
        with self.assertRaises(tm.TMError) as cm:
            machine(now=tm.parse_now("2026-10-30 09:32"))
        self.assertIn("not in the data", str(cm.exception))
        self.assertIn("09:25 bar", str(cm.exception))
        self.assertEqual(machine(now=tm.parse_now("2026-10-30 09:35"), replays=200)["mc"]["pool_sessions"], 60)
        later = tm.parse_bars(self.result, NOW_UTC)
        self.assertEqual(later[2]["not_complete"], 70)
        self.assertEqual(later[1][-1]["start"], "09:35")

    def test_ist_is_the_same_offset_all_year(self):
        def stamp(year, month, day, hour, minute):
            local = tm.datetime.datetime(year, month, day, hour, minute)
            return int((tm.ist_to_utc(local) - tm.EPOCH).total_seconds())

        stamps = [stamp(2026, 10, 30, 9, 15),
                  stamp(2026, 12, 7, 9, 15),
                  stamp(2026, 12, 7, 9, 0),
                  stamp(2026, 12, 7, 15, 25)]
        res = {"meta": {"symbol": "NIFTY"}, "timestamp": stamps,
               "indicators": {"quote": [{"open": [1] * 4, "high": [1] * 4, "low": [1] * 4, "close": [1] * 4,
                                         "volume": [0] * 4}]}}
        meta, bars, dropped = tm.parse_bars(res, tm.parse_now("2026-12-08T00:00Z"))
        self.assertEqual([(b["date"], b["start"], b["slot"]) for b in bars],
                         [("2026-10-30", "09:15", 0), ("2026-12-07", "09:15", 0), ("2026-12-07", "15:25", 74)])
        self.assertEqual(dropped["outside_hours"], 1)
        self.assertEqual(tm.to_ist(tm.utc_of(stamps[0])).hour, 9)
        self.assertEqual(tm.to_ist(tm.utc_of(stamps[1])).hour, 9)
        self.assertEqual(tm.IST, tm.datetime.timedelta(hours=5, minutes=30))

    def test_a_session_missing_a_bar_is_not_full(self):
        def cut(res):
            keep_bars(res, lambda ts: not (ist(ts).date().isoformat() == "2026-08-04"
                                           and ist(ts).hour == 9 and ist(ts).minute == 15))
        doc = machine(text=edited(cut), replays=300)
        self.assertEqual(doc["mc"]["pool_sessions"], 59)
        self.assertEqual(doc["data"]["short_sessions_left_out"], [{"date": "2026-08-04", "bars": 74}])
        self.assertEqual(doc["history"]["sessions"], 59)
        self.assertNotIn("2026-08-04", [t["date"] for t in doc["history"]["trades"]])
        self.assertIn("Left out 1 short session", "\n".join(tm.report(doc)))

    def test_the_plan_day_is_not_in_the_pool(self):
        doc = machine(replays=200)
        self.assertEqual(doc["mc"]["pool_to"], "2026-10-29")
        self.assertEqual(doc["mc"]["pool_sessions"], 60)
        self.assertNotIn(DAY, [t["date"] for t in doc["history"]["trades"]])

    def test_a_missing_price_is_dropped(self):
        def hole(res):
            res["indicators"]["quote"][0]["close"][5] = None
        doc = machine(text=edited(hole), replays=200)
        self.assertEqual(doc["data"]["dropped"]["no_price"], 1)
        self.assertEqual(doc["mc"]["pool_sessions"], 59)

    def test_empty_and_broken_data(self):
        empty = json.dumps({"chart": {"result": [{"meta": {"symbol": "NIFTY"}, "timestamp": [],
                                                  "indicators": {"quote": [{}]}}], "error": None}})
        with self.assertRaises(tm.TMError) as cm:
            machine(text=empty)
        self.assertIn("no complete 5-minute bars", str(cm.exception))
        gone = json.dumps({"chart": {"result": None, "error": {"code": "Not Found",
                                                               "description": "No data found, symbol may be delisted"}}})
        with self.assertRaises(tm.TMError) as cm:
            machine(text=gone)
        self.assertIn("No data found", str(cm.exception))
        with self.assertRaises(tm.TMError):
            machine(text="<html>rate limited</html>")

    def test_fewer_than_20_sessions_is_refused(self):
        def trim(res):
            keep_bars(res, lambda ts: ist(ts).date().isoformat() >= "2026-10-01")
        with self.assertRaises(tm.TMError) as cm:
            machine(text=edited(trim))
        self.assertIn("only 19 full session(s)", str(cm.exception))
        self.assertIn("at least 20", str(cm.exception))

        def twenty(res):
            keep_bars(res, lambda ts: ist(ts).date().isoformat() >= "2026-09-30")
        self.assertEqual(machine(text=edited(twenty), replays=200)["mc"]["pool_sessions"], 20)

    def test_until_at_the_close_and_a_holiday_are_refused(self):
        for bad in ("15:30", "15:35", "4:00 PM"):
            with self.assertRaises(tm.TMError) as cm:
                machine(until=bad, replays=10)
            self.assertIn("no later than 3:25 PM", str(cm.exception), bad)
        with self.assertRaises(tm.TMError) as cm:
            plan(date="2026-11-10")
        self.assertIn("Diwali Balipratipada", str(cm.exception))
        self.assertIn("NSE is closed", str(cm.exception))

    def test_the_data_must_be_the_plans_ticker(self):
        with self.assertRaises(tm.TMError) as cm:
            machine(plan(symbol="AAPL"))
        self.assertIn("data is for NIFTY", str(cm.exception))


class Plans(unittest.TestCase):
    def test_an_entry_not_in_the_data_is_refused(self):
        with self.assertRaises(tm.TMError) as cm:
            machine(plan(date="2026-08-03"))
        self.assertIn("no bars for that day", str(cm.exception))
        with self.assertRaises(tm.TMError) as cm:
            machine(plan(entry_time="9:40 AM", entry_bar=None), now=tm.parse_now("2026-10-30 09:36"))
        self.assertIn("not in the data", str(cm.exception))

    def test_plan_checks(self):
        cases = [
            (dict(entry_time="9:32 AM", entry_bar=None), "5-minute grid"),
            (dict(entry_time="3:30 PM", entry_bar=None), "between 9:20 AM and 3:25 PM"),
            (dict(entry_bar=9), "disagrees with itself"),
            (dict(entry_time=None, entry_bar=None), "entry_time"),
            (dict(interval="1m"), "7 days of 1-min bars"),
            (dict(stop=23000.0), "stop < entry < target"),
            (dict(side="short"), "buy or sell"),
            (dict(symbol=""), "ticker"),
            (dict(entry="abc"), "number for entry"),
            (dict(date="Oct 30"), "date like"),
            (dict(opening_range={"minutes": 7}), "multiple of 5"),
        ]
        for change, words in cases:
            with self.assertRaises(tm.TMError, msg=change) as cm:
                plan(**change)
            self.assertIn(words, str(cm.exception), change)

    def test_entry_bar_or_entry_time_alone(self):
        self.assertEqual(plan(entry_time=None)["entry_time"], "9:35 AM")
        self.assertEqual(plan(entry_bar=None)["entry_bar"], 3)
        self.assertEqual(plan(entry_time="9:35", entry_bar=None)["entry_bar"], 3)
        self.assertEqual(plan(entry_time="9:35am", entry_bar=None)["entry_bar"], 3)

    def test_until_cuts_the_replay(self):
        doc = machine(until="15:00", replays=500)
        m = doc["mc"]
        self.assertEqual((m["until"], m["bars_left"], m["band_times"][-1]), ("15:00", 65, "15:00"))
        self.assertIn("still open at 3:00 PM", "\n".join(tm.report(doc)))
        self.assertEqual(machine(until="3:00 PM", replays=500)["mc"], m)
        for bad, words in (("9:35 AM", "nothing to replay"), ("15:30", "no later than 3:25 PM"),
                           ("15:27", "5-minute grid"), ("noon", "India time")):
            with self.assertRaises(tm.TMError) as cm:
                machine(until=bad, replays=10)
            self.assertIn(words, str(cm.exception), bad)

    def test_an_entry_outside_its_bar_is_flagged(self):
        doc = machine(plan(entry=23100.0, stop=22950.0, target=23200.0), replays=200)
        self.assertIn("outside that bar's range", doc["warnings"][0])

    def test_stop_rounds_away_from_the_entry(self):
        self.assertEqual(tm.ticks_away(22950.125, True), 22950.10)
        self.assertEqual(tm.ticks_away(22950.125, False), 22950.15)
        self.assertEqual(tm.ticks_away(22950.100000000002, True), 22950.10)
        self.assertEqual(tm.ticks_away(22949.999999999998, True), 22949.95)

    def test_the_stop_rule_is_worked_out_when_not_given(self):
        rule = machine(plan(stop_rule=None), replays=100)["history"]["rule"]
        self.assertEqual(rule["stop_rule"], "or_mid")
        rule = machine(plan(stop_rule=None, stop=22919.85, target=23131.05), replays=100)["history"]["rule"]
        self.assertEqual((rule["stop_rule"], rule["target_r"]), ("or_low", 2.0))
        rule = machine(plan(stop_rule="atr", stop=22970.0, target=23030.75), replays=100)["history"]["rule"]
        self.assertEqual((rule["stop_rule"], rule["stop_pct"], rule["target_r"]), ("pct", 0.0881, 2.0))

    def test_a_setup_other_than_orb_skips_the_history(self):
        doc = machine(plan(setup="flag"), replays=200)
        self.assertIsNone(doc["history"]["rule"])
        self.assertIn("orb", doc["history"]["note"])
        self.assertEqual(doc["mc"]["pool_sessions"], 60)
        self.assertIn("History: skipped", "\n".join(tm.report(doc)))

    def test_a_sell_plan_mirrors_the_rules(self):
        doc = machine(plan(side="sell", stop=23070.55, target=22950.10, stop_rule="or_high"), replays=2000)
        m = doc["mc"]
        self.assertAlmostEqual(m["p_target"] + m["p_stop"] + m["p_neither"], 1.0, places=6)
        self.assertEqual(doc["history"]["rule"]["stop_rule"], "or_high")
        for t in doc["history"]["trades"]:
            self.assertTrue(t["target"] < t["entry"] < t["stop"], t)
        self.assertIn("below the entry", "\n".join(tm.report(doc)))

    def test_the_verdict_thresholds_at_1r(self):
        self.assertTrue(tm.verdict({"p_target": 0.30, "p_stop": 0.26}).startswith("Close to a coin flip"))
        self.assertTrue(tm.verdict({"p_target": 0.40, "p_stop": 0.30}).startswith("Leans toward the target"))
        self.assertTrue(tm.verdict({"p_target": 0.20, "p_stop": 0.30}).startswith("Leans toward the stop"))
        self.assertTrue(tm.verdict({"p_target": 0.60, "p_stop": 0.30}).startswith("Strongly toward the target"))
        self.assertEqual(tm.verdict({"p_target": 0.10, "p_stop": 0.60, "r_at_target": 1.0}),
                         "Strongly toward the stop: target first 10.0 % vs stop first 60.0 %.")
        self.assertEqual(tm.verdict({"p_target": 0.0, "p_stop": 0.0, "until": "15:10"}),
                         "No replay reached the target or the stop by 3:10 PM: the price at 3:10 PM decides every one.")

    def test_a_2r_target_is_judged_against_its_break_even(self):
        mc = {"p_target": 0.241, "p_stop": 0.505, "p_neither": 0.254, "r_at_target": 2.0, "avg_R": 0.095}
        self.assertEqual(tm.verdict(mc), "Close to break-even: at 2R the target has to come first in 33 % of the "
                                         "replays that hit one side; it did in 32 % (target first 24.1 % vs stop "
                                         "first 50.5 %).")
        self.assertEqual(tm.verdict_notes(mc), [])
        lean = dict(mc, p_target=0.15, p_stop=0.55)
        self.assertTrue(tm.verdict(lean).startswith("Leans toward the stop: at 2R the target has to come first in "
                                                    "33 % of the replays that hit one side; it did in 21 %"))
        self.assertEqual(tm.verdict_notes(lean), ["Average R is +0.095 all the same: the replays that hit neither "
                                                  "pull it the other way."])
        self.assertTrue(tm.verdict(dict(mc, p_target=0.30, p_stop=0.40)).startswith("Leans toward the target"))
        self.assertTrue(tm.verdict(dict(mc, p_target=0.40, p_stop=0.40)).startswith("Strongly toward the target"))
        self.assertIn("at 1.5R the target has to come first in 40 %", tm.verdict(dict(mc, r_at_target=1.5)))

    def test_1r_on_the_fixture_is_close_to_a_coin_flip(self):
        doc = machine(plan(target=23030.40))
        m = doc["mc"]
        self.assertEqual((m["r_at_target"], m["p_target"], m["p_stop"], m["p_neither"], m["avg_R"]),
                         (1.0, 0.5441, 0.4548, 0.0011, 0.089))
        self.assertEqual(doc["verdict"], "Close to a coin flip: target first 54.4 % vs stop first 45.5 %.")
        self.assertEqual(doc["verdict_notes"], [])


class Network(unittest.TestCase):
    def setUp(self):
        self.calls, self.sleeps = [], []
        self._get, self._sleep = tm._get, tm._sleep
        tm._sleep = self.sleeps.append

    def tearDown(self):
        tm._get, tm._sleep = self._get, self._sleep

    def answer(self, codes):
        codes = list(codes)

        def fake(url, timeout=20):
            self.calls.append(url.split(".finance")[0].split("//")[1])
            code = codes.pop(0)
            if code != 200:
                raise urllib.error.HTTPError(url, code, "x", {}, io.BytesIO(b""))
            return TEXT
        tm._get = fake

    def test_url_and_user_agent(self):
        self.assertEqual(tm.chart_url("nifty"),
                         "https://query2.finance.yahoo.com/v8/finance/chart/NIFTY?range=60d&interval=5m")
        self.assertIn("/chart/BRK-B?", tm.chart_url("brk.b", "query1"))
        self.assertEqual(tm.UA, "Mozilla/5.0 (compatible; day-trader-skill/2.0; "
                                "+https://github.com/Jakeschincariol/day-trader-skill)")

    def test_429_waits_retries_then_falls_back_to_query1(self):
        self.answer([429, 429, 200])
        self.assertEqual(tm.fetch_chart("NIFTY"), TEXT)
        self.assertEqual(self.calls, ["query2", "query2", "query1"])
        self.assertEqual(self.sleeps, [tm.BACKOFF, tm.PAUSE])

    def test_one_429_then_ok(self):
        self.answer([429, 200])
        self.assertEqual(tm.fetch_chart("NIFTY"), TEXT)
        self.assertEqual(self.calls, ["query2", "query2"])

    def test_5xx_falls_back(self):
        self.answer([503, 200])
        self.assertEqual(tm.fetch_chart("NIFTY"), TEXT)
        self.assertEqual(self.calls, ["query2", "query1"])

    def test_rate_limited_everywhere_is_one_plain_line(self):
        self.answer([429, 429, 429, 429])
        with self.assertRaises(tm.TMError) as cm:
            tm.fetch_chart("NIFTY")
        self.assertIn("rate limiting", str(cm.exception))

    def test_404(self):
        self.answer([404])
        with self.assertRaises(tm.TMError) as cm:
            tm.fetch_chart("ZZZZ")
        self.assertIn("check the ticker", str(cm.exception))

    def test_run_over_the_network_path(self):
        self.answer([200])
        d = tempfile.mkdtemp()
        try:
            p = os.path.join(d, "plan.json")
            with open(p, "w") as fh:
                json.dump(PLAN, fh)
            code, text, err = run(["run", "--plan", p, "--now", NOW, "--replays", "300"])
            self.assertEqual(code, 0, err)
            self.assertEqual(self.calls, ["query2"])
            self.assertIn("(Yahoo, free, can lag)", text)
        finally:
            shutil.rmtree(d)


class Cli(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.plan = os.path.join(self.d, "trader", "plan.json")
        os.makedirs(os.path.dirname(self.plan))
        with open(self.plan, "w") as fh:
            json.dump(PLAN, fh, indent=2)
        self.out = os.path.join(self.d, "trader", "timemachine.json")

    def tearDown(self):
        shutil.rmtree(self.d)

    def test_run_with_the_plan_end_to_end(self):
        code, text, err = run(["run", "--plan", self.plan, "--offline", NIFTY, "--now", NOW, "--write", self.out])
        self.assertEqual(code, 0, err)
        self.assertIn("target first   36.4 %", text)
        self.assertIn("Leans toward the target", text)
        self.assertIn("(saved file)", text)
        self.assertIn("Wrote %s." % self.out, text)
        self.assertIn("/trader-budget", text)
        with open(self.out) as fh:
            doc = json.load(fh)
        self.assertEqual(sorted(k for k in ("plan", "mc", "history") if k in doc), ["history", "mc", "plan"])
        self.assertEqual(doc["created_by"], "trader-timemachine")
        self.assertEqual(doc["source"], "offline")
        self.assertEqual((doc["mc"]["p_target"], doc["mc"]["avg_R"], doc["mc"]["pool_sessions"]), (0.3644, 0.173, 60))
        self.assertEqual(sha(doc["mc"]["sample_paths"]), PATHS)
        self.assertEqual((doc["history"]["triggered"], doc["history"]["avg_R"]), (49, 0.408))
        self.assertEqual(doc["plan"]["from"], self.plan)

    def test_json_output(self):
        code, text, _ = run(["run", "--plan", self.plan, "--offline", NIFTY, "--now", NOW, "--json"])
        self.assertEqual(code, 0)
        doc = json.loads(text)
        self.assertEqual(doc["mc"]["p_stop"], 0.5844)
        self.assertNotIn("sample_paths", doc["mc"])
        self.assertTrue(doc["verdict"].startswith("Leans toward the target"))
        self.assertFalse(os.path.exists(self.out))

    def test_the_plan_as_flags_matches_the_file(self):
        code, text, err = run(["run", "--symbol", "nifty", "--date", DAY, "--entry", "22990.25",
                               "--stop", "22950.10", "--target", "23070.55", "--entry-time", "9:35 AM",
                               "--offline", NIFTY, "--now", NOW, "--json"])
        self.assertEqual(code, 0, err)
        doc = json.loads(text)
        self.assertEqual((doc["mc"]["p_target"], doc["mc"]["pool_sessions"]), (0.3644, 60))
        self.assertEqual(doc["plan"]["stop_rule"], "or_mid")
        self.assertEqual((doc["history"]["target"], doc["history"]["stop"], doc["history"]["avg_R"]), (23, 26, 0.408))
        code, _, err = run(["run", "--symbol", "NIFTY", "--entry", "22990.25", "--offline", NIFTY])
        self.assertEqual(code, 1)
        self.assertIn("--stop", err)

    def test_offline_folder_and_default_paths(self):
        shutil.copy(NIFTY, self.d)
        cwd = os.getcwd()
        os.chdir(self.d)
        try:
            code, text, err = run(["run", "--offline", ".", "--now", NOW, "--replays", "500", "--write"])
            self.assertEqual(code, 0, err)
            self.assertTrue(os.path.exists(os.path.join("trader", "timemachine.json")))
            code, text, err = run(["chart", "--from"])
            self.assertEqual(code, 0, err)
            self.assertIn("* median", text)
            with open(os.path.join("trader", "timemachine.json")) as fh:
                self.assertEqual(json.load(fh)["mc"]["replays"], 500)
        finally:
            os.chdir(cwd)

    def test_errors_are_one_plain_line(self):
        for argv in (["run", "--plan", os.path.join(self.d, "nope.json")],
                     ["run", "--plan", self.plan, "--offline", os.path.join(self.d, "missing.json")],
                     ["run", "--plan", self.plan, "--offline", NIFTY, "--until", "9:00"],
                     ["chart", "--from", os.path.join(self.d, "nope.json")]):
            code, text, err = run(argv)
            self.assertEqual(code, 1, argv)
            self.assertEqual(len(err.strip().splitlines()), 1, err)
            self.assertTrue(err.startswith("timemachine.py: "), err)
            self.assertNotIn("Traceback", err)
        self.assertEqual(run([])[0], 1)

    def test_chart(self):
        run(["run", "--plan", self.plan, "--offline", NIFTY, "--now", NOW, "--write", self.out])
        code, text, _ = run(["chart", "--from", self.out])
        self.assertEqual(code, 0)
        lines = text.splitlines()
        self.assertIn("2,000 replay paths from the 9:35 AM entry (seed 19)", lines[0])
        self.assertTrue(any("23070.55" in l and l.endswith("  target") for l in lines))
        self.assertTrue(any("22950.10" in l and l.endswith("  stop") for l in lines))
        self.assertTrue(any("22990.25" in l and l.endswith("  entry") for l in lines))
        self.assertIn("9:35", text)
        self.assertIn("3:10", text)
        self.assertTrue(lines[-1].startswith("Leans toward the target"))
        code, again, _ = run(["chart", "--plan", self.plan, "--offline", NIFTY, "--now", NOW])
        self.assertEqual(again, text)


if __name__ == "__main__":
    unittest.main()
