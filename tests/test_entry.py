"""trader-entry tests. Fixtures in tests/fixtures/trader-entry/:

NIFTY-2026-10-30-5m.json  NIFTY's Oct 30 2026 five-minute bars, converted from
                          AlgoTest candles (Yahoo chart JSON v8). A full NSE
                          session, 09:15 to 15:25 IST, volume 0.
DEMO-1m-synthetic.json    SYNTHETIC one-minute bars (not market data): a wick above the
                          range high, a close AT the high, a null bar, a live tick.
                          NSE session, open 09:15 IST.
"""

import copy
import datetime
import gzip
import io
import json
import os
import shutil
import tempfile
import unittest
import urllib.error
from contextlib import redirect_stdout, redirect_stderr

from _load import load, FIX, ROOT

entry = load("trader-entry", "entry")

EDIR = os.path.join(FIX, "trader-entry")
NIFTY = os.path.join(EDIR, "NIFTY-2026-10-30-5m.json")
DEMO = os.path.join(EDIR, "DEMO-1m-synthetic.json")
OPEN_TS = 1793331900       # 2026-10-30 09:15 IST
DT = datetime.datetime
DAY = "2026-10-30"


def ist(text):
    return entry.parse_now(text)


def doc(path=NIFTY):
    with open(path) as fh:
        return json.load(fh)


def chart(d=None, sym="NIFTY"):
    return entry.parse_chart(json.dumps(d if d is not None else doc()), sym)


def at(text, d=None, **kw):
    return entry.evaluate(chart(d), ist(text), **kw)


def shift_to(d, day):
    """The same session moved to another date. 09:15 IST is always 03:45 UTC."""
    d = copy.deepcopy(d)
    r = d["chart"]["result"][0]
    new_open = int((DT.combine(day, datetime.time(3, 45)) - DT(1970, 1, 1)).total_seconds())
    delta = new_open - OPEN_TS
    r["timestamp"] = [t + delta for t in r["timestamp"]]
    r["meta"]["regularMarketTime"] += delta
    r["meta"]["timezone"] = "IST"
    return d


def no_breakout(d=None):
    """Every bar after the range stays under the 22980.35 high."""
    d = copy.deepcopy(d if d is not None else doc())
    q = d["chart"]["result"][0]["indicators"]["quote"][0]
    for i in range(3, len(q["close"])):
        q["close"][i] = min(q["close"][i], 22980.00)
        q["high"][i] = min(q["high"][i], 22980.10)
        q["open"][i] = min(q["open"][i], 22980.00)
    return d


def run(argv):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = entry.main(argv)
    return code, out.getvalue(), err.getvalue()


class TheReel(unittest.TestCase):
    def test_triggers_at_0935_on_the_0930_bar(self):
        r = at(DAY + " 09:40")
        self.assertEqual(r["status"], "triggered")
        self.assertEqual(r["opening_range"]["high"], 22980.35)
        self.assertEqual(r["opening_range"]["low"], 22919.85)
        self.assertEqual(r["opening_range"]["bars"], 3)
        t = r["trigger"]
        self.assertEqual(t["time"], "9:35 AM")
        self.assertEqual(t["bar_start"], "09:30")
        self.assertEqual(t["bar_index"], 3)
        self.assertEqual(t["price"], 22990.25)
        self.assertEqual(t["close"], 22990.25)
        self.assertEqual(t["pct_over"], 0.04)
        self.assertEqual(r["level"], 22980.35)
        self.assertIsNone(r["prev_close"])

    def test_at_0932_the_0930_bar_is_still_forming(self):
        r = at(DAY + " 09:32")
        self.assertEqual(r["status"], "waiting")
        self.assertEqual(r["phase"], "open")          # the 15-minute range was set at 09:30
        self.assertIsNone(r["trigger"])
        self.assertEqual(r["opening_range"]["bars"], 3)
        self.assertTrue(r["opening_range"]["complete"])
        self.assertEqual(r["last"]["bar_start"], "09:25")
        self.assertEqual(r["last"]["close"], 22963.5)
        self.assertEqual(r["forming"]["bar_start"], "09:30")
        self.assertIn("under the range high ₹22980.35", r["reason"])
        self.assertEqual(at(DAY + " 09:34:59")["status"], "waiting")

    def test_before_the_open_and_while_the_range_forms(self):
        r = at(DAY + " 09:00")
        self.assertEqual((r["status"], r["phase"]), ("waiting", "pre-open"))
        self.assertEqual(r["opens"], "09:15")
        self.assertIn("opens at 9:15", r["reason"])
        r = at(DAY + " 09:29")
        self.assertEqual((r["status"], r["phase"]), ("waiting", "forming"))
        self.assertEqual(r["opening_range"]["bars"], 2)
        self.assertFalse(r["opening_range"]["complete"])
        r = at(DAY + " 09:31")
        self.assertEqual((r["status"], r["phase"]), ("waiting", "open"))
        self.assertEqual(r["opening_range"]["bars"], 3)

    def test_a_live_tick_and_an_in_progress_bar_are_dropped(self):
        d = doc()
        r0 = d["chart"]["result"][0]
        keep = [i for i, t in enumerate(r0["timestamp"]) if t <= OPEN_TS + 15 * 300]  # through the 10:30 bar
        r0["timestamp"] = [r0["timestamp"][i] for i in keep]
        q = r0["indicators"]["quote"][0]
        for k in q:
            q[k] = [q[k][i] for i in keep]
        tick = OPEN_TS + 79 * 60 + 45                                             # 10:34:45
        r0["timestamp"].append(tick)
        for k in q:
            q[k].append(q[k][-1])
        r0["meta"]["regularMarketTime"] = tick
        c = chart(d)
        self.assertEqual(c["bars"][-1]["t"], tick)
        r = entry.evaluate(c, entry.utc_of(c["data_time"]))
        self.assertEqual(r["now"], DAY + " 10:34:45")
        self.assertEqual(r["_bars"][-1]["slot"], 14)                              # the 10:25 bar
        self.assertEqual(r["forming"]["bar_start"], "10:30")
        self.assertEqual(r["bars_closed"], 15)
        r = at(DAY + " 10:35", d)
        self.assertEqual(r["_bars"][-1]["slot"], 14)
        self.assertIn("Yahoo's last trade is 10:34:45", r["lag_note"])
        r = at(DAY + " 10:36", d)
        self.assertEqual(r["_bars"][-1]["slot"], 15)
        self.assertEqual(r["bars_closed"], 16)
        self.assertTrue(all(b["t"] % 300 == 0 for b in r["_bars"]))

    def test_after_the_close_it_stays_triggered_and_says_it_is_late(self):
        r = at(DAY + " 15:35")
        self.assertEqual((r["status"], r["phase"]), ("triggered", "after-close"))
        self.assertEqual(r["trigger"]["time"], "9:35 AM")
        text = "\n".join(entry.describe(r))
        self.assertIn("minutes ago", text)
        self.assertNotIn("This is the moment", text)


class Rules(unittest.TestCase):
    def test_zero_volume_skips_the_check(self):
        r = at(DAY + " 09:40", min_volume_x=2)
        self.assertEqual(r["status"], "triggered")
        self.assertEqual(r["trigger"]["bar_start"], "09:30")
        self.assertEqual(r["volume_note"], "volume check skipped: no volume data")
        self.assertIn("volume check skipped: no volume data", "\n".join(entry.describe(r)))

    def test_volume_confirmation_moves_the_trigger(self):
        d = doc()
        q = d["chart"]["result"][0]["indicators"]["quote"][0]
        q["volume"] = [100] * len(q["volume"])
        for i in range(3):
            q["volume"][i] = 1000
        q["volume"][6] = 5000
        r = at(DAY + " 09:35", d, min_volume_x=1)
        self.assertEqual(r["status"], "waiting")
        self.assertEqual(r["opening_range"]["avg_volume"], 1000)
        self.assertIn("0.10x the range's volume, under your 1.00x", r["reason"])
        r = at(DAY + " 09:50", d, min_volume_x=1)
        t = r["trigger"]
        self.assertEqual((t["time"], t["bar_index"], t["price"]), ("9:50 AM", 6, 22980.45))
        self.assertEqual(t["volume_x"], 5.0)

    def test_level_setup(self):
        r = at(DAY + " 10:00", setup="level", level=22970)
        self.assertEqual(r["trigger"]["time"], "9:35 AM")
        self.assertEqual(r["trigger"]["bar_index"], 3)
        self.assertEqual(r["trigger"]["price"], 22990.25)
        # a level under every close: the first eligible close is the 09:25 bar's, at 09:30
        r = at(DAY + " 10:00", setup="level", level=20000)
        self.assertEqual((r["trigger"]["time"], r["trigger"]["bar_index"]), ("9:30 AM", 2))
        with self.assertRaises(entry.EntryError):
            at(DAY + " 10:00", setup="level")

    def test_no_breakout_waits_then_expires_at_the_cutoff(self):
        d = no_breakout()
        r = at(DAY + " 10:00", d)
        self.assertEqual(r["status"], "waiting")
        self.assertEqual(at(DAY + " 14:29", d)["status"], "waiting")
        r = at(DAY + " 14:30", d)
        self.assertEqual(r["status"], "expired")
        self.assertIn("by 14:30", r["reason"])
        self.assertEqual(at(DAY + " 15:30", d)["phase"], "after-close")

    def test_the_bar_closing_at_the_cutoff_still_counts_when_yahoo_lags(self):
        d = no_breakout()
        r0 = d["chart"]["result"][0]
        keep = [i for i, t in enumerate(r0["timestamp"]) if t <= OPEN_TS + 14 * 300]  # up to the 10:25 bar
        r0["timestamp"] = [r0["timestamp"][i] for i in keep]
        q = r0["indicators"]["quote"][0]
        for k in q:
            q[k] = [q[k][i] for i in keep]
        r0["meta"]["regularMarketTime"] = OPEN_TS + 74 * 60 + 40                    # last trade 10:29:40
        cfg = {"no_entries_before": "09:45", "no_entries_after": "10:30"}
        r = at(DAY + " 10:30:10", d, cfg=cfg)
        self.assertEqual(r["status"], "waiting")
        self.assertIn("Yahoo's last trade is 10:29:40", r["lag_note"])
        self.assertEqual(at(DAY + " 10:31", d, cfg=cfg)["status"], "expired")

    def test_config_cutoff(self):
        cfg = {"no_entries_before": "09:45", "no_entries_after": "09:30"}
        r = at(DAY + " 09:40", cfg=cfg)
        self.assertEqual(r["status"], "expired")
        cfg = {"no_entries_before": "09:50", "no_entries_after": "14:30"}
        r = at(DAY + " 10:00", cfg=cfg)
        self.assertEqual(r["trigger"]["time"], "9:50 AM")       # the 09:45 bar, first to close at 09:50

    def test_bad_inputs(self):
        with self.assertRaises(entry.EntryError):
            at(DAY + " 09:40", or_minutes=7)
        with self.assertRaises(entry.EntryError):
            at(DAY + " 09:40", interval="15m")
        with self.assertRaises(entry.EntryError):
            entry.parse_now("tomorrow")
        with self.assertRaises(entry.EntryError):
            entry.parse_hhmm("25:00", "x")
        self.assertEqual(entry.parse_now(DAY + " 09:40"), DT(2026, 10, 30, 4, 10))
        self.assertEqual(entry.parse_now(DAY + " 09:40 IST"), DT(2026, 10, 30, 4, 10))
        self.assertEqual(entry.parse_now("2026-10-30T04:10:00Z"), DT(2026, 10, 30, 4, 10))

    def test_or_minutes_30(self):
        r = at(DAY + " 11:15", or_minutes=30)
        self.assertEqual(r["opening_range"]["bars"], 6)
        self.assertEqual(r["opening_range"]["high"], 22994.7)
        self.assertEqual(r["trigger"]["time"], "11:10 AM")
        self.assertEqual(r["trigger"]["bar_index"], 22)


class OneMinute(unittest.TestCase):
    def c(self):
        return entry.parse_chart(json.dumps(doc(DEMO)), "DEMO")

    def test_wick_and_close_at_the_high_do_not_trigger(self):
        c = self.c()
        r = entry.evaluate(c, entry.utc_of(c["data_time"]), interval="1m")
        self.assertEqual(r["now"], DAY + " 09:51:30")
        self.assertEqual(r["opening_range"], {"high": 100.5, "low": 99.0, "minutes": 15, "bars": 15, "of": 15,
                                              "complete": True, "avg_volume": 10667})
        t = r["trigger"]
        self.assertEqual((t["time"], t["bar_start"], t["bar_index"], t["price"]), ("9:44 AM", "09:43", 28, 100.62))
        r = entry.evaluate(c, ist(DAY + " 09:43:59"), interval="1m")
        self.assertEqual(r["status"], "waiting")
        self.assertEqual(r["forming"]["bar_start"], "09:43")
        self.assertEqual(r["last"]["close"], 100.5)             # the 09:42 bar closed AT the high

    def test_null_bar_tick_and_volume(self):
        c = self.c()
        r = entry.evaluate(c, entry.utc_of(c["data_time"]), interval="1m", min_volume_x=2)
        self.assertEqual((r["trigger"]["time"], r["trigger"]["bar_index"]), ("9:47 AM", 31))
        slots = [b["slot"] for b in r["_bars"]]
        self.assertNotIn(19, slots)                               # 09:34 came as nulls
        self.assertEqual(slots[-1], 35)                           # 09:51 still forming, 09:51:30 tick dropped
        self.assertEqual(r["forming"]["bar_start"], "09:51")

    def test_the_file_and_the_interval_must_agree(self):
        code, _, err = run(["check", "DEMO", "--offline", DEMO])
        self.assertEqual(code, 1)
        self.assertIn("1m bars, not 5m", err)


class Calendar(unittest.TestCase):
    def test_ist_is_the_same_offset_all_year(self):
        for day in (datetime.date(2026, 12, 7), datetime.date(2026, 11, 2),
                    datetime.date(2026, 10, 30), datetime.date(2026, 3, 9)):
            d = shift_to(doc(), day)
            r = entry.evaluate(chart(d), ist("%s 09:40" % day))
            self.assertEqual(r["status"], "triggered", day)
            self.assertEqual(r["trigger"]["time"], "9:35 AM", day)
            self.assertEqual(r["trigger"]["bar_index"], 3, day)
            self.assertEqual(entry.evaluate(chart(d), ist("%s 09:32" % day))["status"], "waiting", day)
        # 09:35 IST is 04:05 UTC in June and in December
        self.assertEqual(ist("2026-12-07 09:35"), DT(2026, 12, 7, 4, 5))
        self.assertEqual(ist("2026-06-15 09:35"), DT(2026, 6, 15, 4, 5))
        self.assertEqual(ist("2026-12-07 09:35 IST"), DT(2026, 12, 7, 4, 5))

    def test_there_is_no_early_close(self):
        d = shift_to(no_breakout(), datetime.date(2026, 11, 27))
        r = entry.evaluate(chart(d), ist("2026-11-27 14:29"))
        self.assertEqual(r["status"], "waiting")
        self.assertEqual((r["closes"], r["no_entries_after"]), ("15:30", "14:30"))
        r = entry.evaluate(chart(d), ist("2026-11-27 14:30"))
        self.assertEqual(r["status"], "expired")
        self.assertNotIn("early close", r["reason"])
        text = "\n".join(entry.describe(entry.evaluate(chart(shift_to(doc(), datetime.date(2026, 11, 27))),
                                                       ist("2026-11-27 09:40"))))
        self.assertNotIn("Early close", text)
        self.assertFalse(hasattr(entry, "early_cutoff"))
        self.assertFalse(hasattr(entry, "NYSE_EARLY_CLOSE"))

    def test_weekend_holiday_and_empty_data(self):
        r = at("2026-10-31 10:00")
        self.assertEqual((r["status"], r["phase"]), ("no-data", "closed"))
        self.assertIn("weekend", r["reason"])
        self.assertEqual(r["next_open"], "2026-11-02 09:15")
        r = at("2026-11-10 10:00")
        self.assertIn("Diwali Balipratipada", r["reason"])
        self.assertEqual(r["next_open"], "2026-11-11 09:15")
        empty = copy.deepcopy(doc())
        res = empty["chart"]["result"][0]
        del res["timestamp"]
        res["indicators"] = {"quote": [{}]}
        r = at(DAY + " 09:40", empty)
        self.assertEqual((r["status"], r["phase"]), ("no-data", "open"))
        r = at("2026-11-02 10:15")                                # the file holds Oct 30 only
        self.assertEqual(r["status"], "no-data")
        self.assertFalse(at("2028-03-01 10:30")["calendar_known"])
        self.assertIn("NSE holiday circular", "\n".join(entry.describe(at("2028-03-01 10:30"))))

    def test_yahoo_errors(self):
        bad = json.dumps({"chart": {"result": None, "error": {"code": "Not Found",
                                                              "description": "No data found, symbol may be delisted"}}})
        with self.assertRaises(entry.EntryError) as cm:
            entry.parse_chart(bad, "ZZZZ")
        self.assertIn("No data found", str(cm.exception))
        with self.assertRaises(entry.EntryError):
            entry.parse_chart("<html>", "NIFTY")


class Network(unittest.TestCase):
    """Yahoo is never called: _open_url and _sleep are swapped for fakes."""

    def setUp(self):
        self.calls, self.sleeps = [], []
        self._open, self._sleep = entry._open_url, entry._sleep
        entry._sleep = lambda s: self.sleeps.append(s)
        with open(NIFTY) as fh:
            self.body = fh.read()

    def tearDown(self):
        entry._open_url, entry._sleep = self._open, self._sleep

    def answers(self, *codes):
        seq = list(codes)

        def fake(url, timeout=20):
            self.calls.append(url)
            code = seq.pop(0)
            if code == 200:
                return self.body
            raise urllib.error.HTTPError(url, code, "x", {}, io.BytesIO(b'{"chart":{"result":null,'
                                                                           b'"error":{"description":"No data found"}}}'))
        entry._open_url = fake

    def test_url_and_429_retry_once_after_a_pause(self):
        self.answers(429, 200)
        c = entry.get_chart("NIFTY", "5m", datetime.date(2026, 10, 30), today=datetime.date(2026, 10, 30))
        self.assertEqual(len(c["bars"]), 75)
        self.assertEqual(self.calls, ["https://query2.finance.yahoo.com/v8/finance/chart/NIFTY?range=1d&interval=5m"] * 2)
        self.assertEqual(self.sleeps, [entry.BACKOFF])

    def test_429_twice_falls_back_to_query1(self):
        self.answers(429, 429, 200)
        entry.get_chart("NIFTY", "5m", datetime.date(2026, 10, 30), today=datetime.date(2026, 10, 30))
        self.assertEqual([u.split("/")[2] for u in self.calls],
                         ["query2.finance.yahoo.com", "query2.finance.yahoo.com", "query1.finance.yahoo.com"])

    def test_5xx_falls_back_without_waiting(self):
        self.answers(503, 200)
        entry.get_chart("NIFTY", "5m", datetime.date(2026, 10, 30), today=datetime.date(2026, 10, 30))
        self.assertEqual(self.sleeps, [])
        self.assertIn("query1", self.calls[1])

    def test_still_busy_is_one_plain_error(self):
        self.answers(429, 429, 429, 429)
        code, out, err = run(["check", "NIFTY", "--now", DAY + " 09:40"])
        self.assertEqual(code, 1)
        self.assertIn("HTTP 429", err)
        self.assertNotIn("Traceback", err)

    def test_unknown_ticker_404(self):
        self.answers(404)
        with self.assertRaises(entry.EntryError) as cm:
            entry.get_chart("ZZZZ", "5m", datetime.date(2026, 10, 30), today=datetime.date(2026, 10, 30))
        self.assertIn("No data found", str(cm.exception))

    def test_ranges_for_past_sessions(self):
        today = datetime.date(2026, 10, 20)
        self.assertEqual(entry.chart_range(today, today, "5m"), "1d")
        self.assertEqual(entry.chart_range(datetime.date(2026, 10, 19), today, "5m"), "5d")
        self.assertEqual(entry.chart_range(datetime.date(2026, 10, 1), today, "5m"), "1mo")
        self.assertEqual(entry.chart_range(datetime.date(2026, 8, 31), today, "5m"), "60d")
        with self.assertRaises(entry.EntryError):
            entry.chart_range(datetime.date(2026, 10, 1), today, "1m")
        self.assertIn("/chart/BRK-B?", entry.chart_path("brk.b", "1d", "5m"))
        self.assertIn("/chart/NIFTY.NS?", entry.chart_path("nifty.ns", "1d", "5m"))
        self.assertIn("/chart/RELIANCE.BO?", entry.chart_path("reliance.bo", "1d", "5m"))


def live_provider(d, lag_until=None, calls=None):
    """Bars the way Yahoo serves them at `now`: closed bars final, the in-progress bar
    showing a spike above the range high, plus a live tick.
    lag_until: before this UTC time Yahoo's last trade lags 30 seconds behind."""
    base = chart(d)

    def provider(now):
        if calls is not None:
            calls.append(now)
        nts = entry.ts_of(now)
        lagging = lag_until is not None and now < lag_until
        data_ts = nts - 30 if lagging else nts
        bars = []
        for b in base["bars"]:
            if b["t"] % 300 or b["t"] > data_ts:
                continue
            b = dict(b)
            if b["t"] + 300 > data_ts:
                b["c"], b["h"] = 23000.00, max(b["h"], 23000.00)
            bars.append(b)
        if data_ts % 300:
            bars.append({"t": data_ts, "o": 23000.0, "h": 23000.0, "l": 23000.0, "c": 23000.0, "v": 0})
        return {"symbol": "NIFTY", "meta": {}, "bars": bars, "prev_close": None, "data_time": data_ts}
    return provider


class Watch(unittest.TestCase):
    OPTS = {"setup": "orb", "or_minutes": 15, "interval": "5m", "level": None, "min_volume_x": None, "cfg": None}

    def loop(self, provider, start, **kw):
        clock = entry.SimClock(ist(start))
        lines, fired = [], []
        code, res = entry.watch_loop(provider, clock.now, clock.sleep, lines.append, dict(self.OPTS),
                                     on_trigger=lambda r, now: fired.append((r, now)), **kw)
        return code, res, lines, fired, clock

    def test_fires_on_the_first_closed_bar_not_the_spike_in_progress(self):
        calls = []
        code, res, lines, fired, clock = self.loop(live_provider(doc(), calls=calls), DAY + " 09:32", every=60)
        self.assertEqual(code, 0)
        self.assertEqual(len(fired), 1)
        self.assertEqual(fired[0][0]["trigger"]["time"], "9:35 AM")
        self.assertEqual(fired[0][0]["trigger"]["price"], 22990.25)
        self.assertEqual([entry.to_ist(c).strftime("%H:%M:%S") for c in calls], ["09:32:00", "09:35:02"])
        text = "\n".join(lines)
        self.assertIn(" 9:30 bar  closed ₹22990.25  TRIGGERED", text)
        self.assertEqual(text.count("TRIGGERED"), 1)
        # a bar that closed under the high is worded that way
        code, res, lines, fired, clock = self.loop(live_provider(no_breakout()), DAY + " 09:36", every=60,
                                                   until=DT(2026, 10, 30, 9, 40))
        self.assertIn(" 9:30 bar  closed ₹22980.00  ₹0.35 under ₹22980.35", "\n".join(lines))

    def test_waits_for_yahoo_to_catch_up(self):
        lag = ist(DAY + " 09:35:30")
        calls = []
        code, res, lines, fired, clock = self.loop(live_provider(doc(), lag_until=lag, calls=calls),
                                                   DAY + " 09:32", every=30)
        self.assertEqual(code, 0)
        times = [entry.to_ist(c).strftime("%H:%M:%S") for c in calls]
        self.assertEqual(times, ["09:32:00", "09:35:02", "09:35:32"])   # 09:35:02: Yahoo still 30s behind
        self.assertEqual(fired[0][0]["trigger"]["time"], "9:35 AM")

    def test_from_before_the_open_prints_the_range_bar_by_bar(self):
        code, res, lines, fired, clock = self.loop(live_provider(doc()), DAY + " 09:00", every=30)
        self.assertEqual(code, 0)
        text = "\n".join(lines)
        self.assertIn("not open yet", lines[0])
        self.assertIn(" 9:25 bar  closed ₹22963.50  opening range set: high ₹22980.35, low ₹22919.85", text)
        self.assertEqual(sum(1 for x in lines if " bar  closed " in x), 4)    # 09:15 ... 09:30

    def test_a_computer_that_dozes_off_catches_up_when_it_wakes(self):
        class Dozing(entry.SimClock):
            naps = 0

            def sleep(self, seconds):
                entry.SimClock.sleep(self, seconds)
                self.naps += 1
                if self.naps == 3:
                    self.t += datetime.timedelta(minutes=17)
        clock = Dozing(ist(DAY + " 09:00"))
        calls, lines = [], []
        code, res = entry.watch_loop(live_provider(doc(), calls=calls), clock.now, clock.sleep, lines.append,
                                     dict(self.OPTS), every=30)
        self.assertEqual(code, 0)
        times = [entry.to_ist(c).strftime("%H:%M:%S") for c in calls]
        self.assertEqual(times[0], "09:20:02")
        text = "\n".join(lines)
        for start in (" 9:25", " 9:30"):
            self.assertIn(start + " bar  closed", text)
        self.assertEqual(res["trigger"]["time"], "9:35 AM")

    def test_expires_and_until(self):
        code, res, lines, fired, clock = self.loop(live_provider(no_breakout()), DAY + " 14:00", every=300)
        self.assertEqual(code, 1)
        self.assertEqual(res["status"], "expired")
        self.assertEqual(fired, [])
        self.assertEqual(entry.to_ist(clock.now()).strftime("%H:%M"), "14:30")
        until = DT(2026, 10, 30, 11, 0)
        code, res, lines, fired, clock = self.loop(live_provider(no_breakout()), DAY + " 10:30", every=300,
                                                   until=until)
        self.assertEqual(code, 1)
        self.assertIn("--until 11:00", lines[-1])

    def test_closed_day_and_repeated_errors(self):
        code, _, lines, _, _ = self.loop(live_provider(doc()), "2026-10-31 10:00")
        self.assertEqual(code, 1)
        self.assertIn("weekend", lines[0])

        def broken(now):
            raise entry.EntryError("Yahoo did not answer")
        code, _, lines, _, _ = self.loop(broken, DAY + " 10:00", every=30)
        self.assertEqual(code, 1)
        self.assertIn("Stopping after 5 failed reads", lines[-1])


class Cli(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.cwd = os.getcwd()
        os.chdir(self.d)

    def tearDown(self):
        os.chdir(self.cwd)
        shutil.rmtree(self.d)

    def test_check_write_is_the_contract_shape(self):
        code, text, _ = run(["check", "NIFTY", "--offline", NIFTY, "--now", DAY + " 09:40", "--write"])
        self.assertEqual(code, 0)
        self.assertIn("TRIGGERED 9:35 AM at ₹22990.25", text)
        self.assertIn("IST", text)
        self.assertNotIn(" ET", text)
        self.assertIn("/trader-exit", text)
        with open(os.path.join("trader", "entry.json")) as fh:
            e = json.load(fh)
        want = {"created_by": "trader-entry", "symbol": "NIFTY", "setup": "orb", "side": "buy", "date": DAY,
                "status": "triggered", "time": "9:35 AM", "bar_start": "09:30", "bar_index": 3, "price": 22990.25,
                "level": 22980.35, "interval": "5m",
                "opening_range": {"high": 22980.35, "low": 22919.85, "minutes": 15},
                "source": "yahoo", "checked_at": "2026-10-30T04:10:00Z"}
        for k, v in want.items():
            self.assertEqual(e[k], v, k)

    def test_check_waiting_json_and_exit_codes(self):
        code, text, _ = run(["check", "NIFTY", "--offline", NIFTY, "--now", DAY + " 09:32", "--json"])
        self.assertEqual(code, 1)
        r = json.loads(text)
        self.assertEqual(r["status"], "waiting")
        self.assertNotIn("_bars", r)
        code, text, _ = run(["check", "NIFTY", "--offline", NIFTY, "--now", DAY + " 09:32", "--write", "e.json"])
        with open("e.json") as fh:
            self.assertEqual(json.load(fh)["status"], "waiting")
        self.assertIn("still forming", text)

    def test_offline_gz_folder_and_mismatch(self):
        os.mkdir("charts")
        with open(NIFTY, "rb") as src, gzip.open(os.path.join("charts", "NIFTY.json.gz"), "wb") as dst:
            dst.write(src.read())
        code, text, _ = run(["check", "nifty", "--offline", "charts", "--now", DAY + " 09:40"])
        self.assertEqual(code, 0)
        code, _, err = run(["check", "NVDA", "--offline", NIFTY])
        self.assertEqual(code, 1)
        self.assertIn("holds NIFTY, not NVDA", err)

    def test_longs_only_and_flag_errors(self):
        code, _, err = run(["check", "NIFTY", "--offline", NIFTY, "--side", "short"])
        self.assertEqual(code, 1)
        self.assertIn("v2 plans longs only", err)
        code, _, err = run(["check", "NIFTY", "--offline", NIFTY, "--level", "23000"])
        self.assertIn("--level is for --setup level", err)
        code, _, err = run(["check", "NIFTY", "--offline", NIFTY, "--setup", "level"])
        self.assertIn("needs --level", err)

    def test_config_is_read(self):
        os.mkdir("trader")
        with open(os.path.join("trader", "config.json"), "w") as fh:
            json.dump({"no_entries_after": "09:30"}, fh)
        code, text, _ = run(["check", "NIFTY", "--offline", NIFTY, "--now", DAY + " 09:40"])
        self.assertEqual(code, 1)
        self.assertIn("EXPIRED", text)
        with open(os.path.join("trader", "config.json"), "w") as fh:
            fh.write("{nope")
        code, _, err = run(["check", "NIFTY", "--offline", NIFTY])
        self.assertIn("not valid JSON", err)

    def test_watch_replays_the_file_and_writes_the_entry(self):
        code, text, _ = run(["watch", "NIFTY", "--offline", NIFTY, "--now", DAY + " 09:20", "--every", "30"])
        self.assertEqual(code, 0)
        self.assertIn(" 9:30 bar  closed ₹22990.25  TRIGGERED", text)
        with open(os.path.join("trader", "entry.json")) as fh:
            self.assertEqual(json.load(fh)["bar_index"], 3)
        code, text, _ = run(["watch", "NIFTY", "--offline", NIFTY, "--now", DAY + " 09:20", "--until", "09:32",
                             "--out", "x.json"])
        self.assertEqual(code, 1)
        self.assertFalse(os.path.exists("x.json"))

    def test_watchlist(self):
        os.mkdir("charts")
        shutil.copy(NIFTY, os.path.join("charts", "NIFTY.json"))
        shutil.copy(DEMO, os.path.join("charts", "DEMO.json"))
        os.mkdir("trader")
        with open(os.path.join("trader", "watchlist.json"), "w") as fh:
            json.dump({"created_by": "trader-scanner", "hits": [
                {"symbol": "NIFTY", "setups": ["orb"]},
                {"symbol": "ZZZZ", "setups": ["orb"]}, {"symbol": "DEMO", "setups": ["orb"]}]}, fh)
        code, text, _ = run(["watchlist", "--offline", "charts", "--now", DAY + " 09:40"])
        self.assertEqual(code, 0, text)
        rows = text.splitlines()
        self.assertTrue(rows[1].startswith("NIFTY   triggered  9:35 AM"), rows[1])
        self.assertIn("₹22990.25", rows[1])
        self.assertIn("₹22980.35", rows[1])
        self.assertNotIn("$", rows[1])
        self.assertIn("ZZZZ    error: no offline file", rows[2])
        self.assertIn("DEMO    error: DEMO has 1m bars", rows[3])
        self.assertIn("1 of 3 triggered", text)
        code, text, _ = run(["watchlist", "--offline", "charts", "--now", DAY + " 09:32", "--json"])
        self.assertEqual(code, 1)
        self.assertEqual(json.loads(text)[0]["result"]["status"], "waiting")
        code, _, err = run(["watchlist", "--watchlist", "missing.json"])
        self.assertIn("run /trader-scanner first", err)


class SkillDoc(unittest.TestCase):
    def test_skill_md(self):
        with open(os.path.join(ROOT, "trader-entry", "SKILL.md"), encoding="utf-8") as fh:
            text = fh.read()
        with open(os.path.join(ROOT, "trader-risk", "SKILL.md"), encoding="utf-8") as fh:
            risk = fh.read()
        self.assertTrue(text.startswith("---\nname: trader-entry\n"))
        self.assertGreater(len(text.splitlines()), 60)
        self.assertEqual(text[text.index("## Safety"):], risk[risk.index("## Safety"):])
        low = " ".join(text.lower().split())
        for must in ("bar by bar", "can lag", "day trading loses most people money", "/trader-exit", "longs only", "in the background", "/loop", "nothing was placed", "10:15 am", "$364.18", "bar 8"):
            self.assertIn(must, low)
        for never in ("\u2014", "tick " + "by tick", "real " + "time", "pro" + "fit"):
            self.assertNotIn(never, low)


if __name__ == "__main__":
    unittest.main()
