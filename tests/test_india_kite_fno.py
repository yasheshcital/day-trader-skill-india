"""Kite F&O download, with recorded responses. No network."""

import datetime
import gzip
import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr

from _load import load

kh = load("india", "kite_history")
fno = load("india", "kite_fno")

NOW = datetime.datetime(2026, 11, 7, 16, 0, 0)
DAY = datetime.date(2026, 11, 7)
TO = datetime.date(2026, 11, 6)
HEADER = (
    "instrument_token,exchange_token,tradingsymbol,name,last_price,expiry,"
    "strike,tick_size,lot_size,instrument_type,segment,exchange"
)


def _body(payload):
    return json.dumps(payload).encode("utf-8")


def _candle(stamp, oi=55):
    return {
        "status": "success",
        "data": {"candles": [[stamp, 100, 110, 90, 105, 1000, oi]]},
    }


EMPTY = {"status": "success", "data": {"candles": []}}


def _nfo(lines):
    return HEADER + "\n" + "\n".join(lines) + "\n"


NFO = _nfo([
    "111,1,NIFTY25NOVFUT,NIFTY,0,2026-11-24,0,0.05,75,FUT,NFO-FUT,NFO",
    "222,2,NIFTY25DECFUT,NIFTY,0,2026-12-29,0,0.05,75,FUT,NFO-FUT,NFO",
    "333,3,NIFTY25N1024000CE,NIFTY,0,2026-11-10,100,0.05,75,CE,NFO-OPT,NFO",
    "334,4,NIFTY25N1024000PE,NIFTY,0,2026-11-10,100,0.05,75,PE,NFO-OPT,NFO",
    "335,5,NIFTY25N1010000CE,NIFTY,0,2026-11-10,50,0.05,75,CE,NFO-OPT,NFO",
    "336,6,RELIANCE25NOVFUT,RELIANCE,0,2026-11-24,0,0.05,1,FUT,NFO-FUT,NFO",
    "337,7,RELIANCE25DECFUT,RELIANCE,0,2026-12-29,0,0.05,1,FUT,NFO-FUT,NFO",
])


class OpenBucket(object):
    def take(self):
        return None


def _index_file(root, symbol, day, close):
    path = kh.bar_path(root, "day", symbol)
    kh.write_bars(path, [{
        "datetime_start_ist": datetime.datetime(day.year, day.month, day.day).strftime("%Y-%m-%d %H:%M:%S"),
        "start": datetime.datetime(day.year, day.month, day.day),
        "open": close, "high": close, "low": close, "close": close, "volume": 1,
    }])


class UrlAndCandles(unittest.TestCase):
    def test_continuous_flag_is_on_the_futures_url_only(self):
        urls = []

        def send(method, url, fields, headers):
            urls.append(url)
            self.assertEqual(headers["Authorization"], "token k:t")
            return 200, _body(EMPTY)

        client = fno.Client(send, "k", "t", OpenBucket(), lambda _s: None, lambda _line: None)
        client.continuous = True
        client.oi = True
        client.fetch_exact("999", "day", datetime.date(2026, 1, 1), datetime.date(2026, 1, 10))
        self.assertIn("continuous=1", urls[0])
        self.assertIn("oi=1", urls[0])
        self.assertIn("/instruments/historical/999/day?", urls[0])
        client.continuous = False
        client.fetch_exact("333", "5minute", datetime.date(2026, 11, 1), TO)
        self.assertNotIn("continuous=", urls[1])
        self.assertIn("oi=1", urls[1])
        self.assertIn("/instruments/historical/333/5minute?", urls[1])

    def test_oi_is_kept_and_written(self):
        rows = fno.candle_rows(_body(_candle("2026-11-06T00:00:00+0530", 55)))
        bare = fno.candle_rows(_body({
            "status": "success",
            "data": {"candles": [["2026-11-05", 1, 2, 0.5, 1.5, 3]]},
        }))
        self.assertEqual(rows[0]["oi"], 55)
        self.assertEqual(rows[0]["datetime_start_ist"], "2026-11-06 00:00:00")
        self.assertEqual(bare[0]["oi"], 0)
        self.assertEqual(bare[0]["datetime_start_ist"], "2026-11-05 00:00:00")
        path = os.path.join(tempfile.mkdtemp(), "NIFTY.csv.gz")
        fno.write_bars(path, rows)
        with gzip.open(path, "rt", encoding="utf-8") as fh:
            header = fh.readline().strip()
        self.assertEqual(header, "datetime_start_ist,open,high,low,close,volume,oi")
        back = fno.read_bars(path)
        self.assertEqual(back[0]["oi"], 55.0)
        self.assertEqual(back[0]["close"], 105.0)


class Selection(unittest.TestCase):
    def setUp(self):
        self.rows = fno.parse_nfo(NFO)

    def test_strike_filter_includes_the_band_and_both_sides(self):
        self.assertTrue(fno.in_band(90, 100))
        self.assertTrue(fno.in_band(110, 100))
        self.assertTrue(fno.in_band(100, 100))
        self.assertFalse(fno.in_band(89, 100))
        self.assertFalse(fno.in_band(111, 100))
        picked = fno.select_options(self.rows, "NIFTY", [datetime.date(2026, 11, 10)], 100)
        symbols = [row["tradingsymbol"] for row in picked]
        self.assertEqual(symbols, ["NIFTY25N1024000CE", "NIFTY25N1024000PE"])
        self.assertNotIn("NIFTY25N1010000CE", symbols)

    def test_expiry_groups_current_and_next(self):
        dates = [
            datetime.date(2026, 11, 10),
            datetime.date(2026, 11, 17),
            datetime.date(2026, 11, 24),
            datetime.date(2026, 12, 1),
            datetime.date(2026, 12, 29),
        ]
        weekly, monthly = fno.expiry_groups(dates)
        self.assertEqual(weekly, [
            datetime.date(2026, 11, 10),
            datetime.date(2026, 11, 17),
            datetime.date(2026, 12, 1),
        ])
        self.assertEqual(monthly, [datetime.date(2026, 11, 24), datetime.date(2026, 12, 29)])
        self.assertEqual(fno.active_expiries(dates, DAY), [
            datetime.date(2026, 11, 10),
            datetime.date(2026, 11, 17),
            datetime.date(2026, 11, 24),
            datetime.date(2026, 12, 29),
        ])
        # On the monthly expiry the earlier weeklies are gone; the next weekly remains.
        self.assertEqual(fno.active_expiries(dates, datetime.date(2026, 11, 24)), [
            datetime.date(2026, 11, 24),
            datetime.date(2026, 12, 1),
            datetime.date(2026, 12, 29),
        ])
        monthlies_only = [datetime.date(2026, 11, 24), datetime.date(2026, 12, 29), datetime.date(2027, 1, 26)]
        self.assertEqual(fno.expiry_groups(monthlies_only)[0], [])
        self.assertEqual(fno.active_expiries(monthlies_only, DAY), monthlies_only[:2])

    def test_nearest_future_and_underlying_order(self):
        self.assertEqual(fno.nearest_future(self.rows, "NIFTY", DAY)["instrument_token"], "111")
        self.assertEqual(fno.nearest_future(self.rows, "RELIANCE", DAY)["tradingsymbol"], "RELIANCE25NOVFUT")
        self.assertIsNone(fno.nearest_future(self.rows, "NIFTY", datetime.date(2027, 1, 1)))
        self.assertEqual(fno.futures_underlyings(self.rows)[:2], ["NIFTY", "RELIANCE"])


class LockAndPlan(unittest.TestCase):
    def test_lock_refuses_a_second_start_and_is_removed_on_exit(self):
        root = tempfile.mkdtemp()
        path = fno.lock_path(root)
        self.assertTrue(path.endswith(os.path.join("progress.lock")))
        fno.acquire_lock(path)
        self.assertTrue(os.path.isfile(path))
        err = []
        with redirect_stderr(_List(err)):
            code = fno.main(["--dry-run", "--data", root, "--to", "2026-11-06"], now=NOW, log=lambda _line: None)
        self.assertEqual(code, 1)
        self.assertTrue(os.path.isfile(path))
        self.assertIn("progress.lock", " ".join(err))
        fno.release_lock(path)
        self.assertFalse(os.path.exists(path))
        lines = []
        code = fno.main(["--dry-run", "--data", root, "--to", "2026-11-06"], now=NOW, log=lines.append)
        self.assertEqual(code, 0)
        self.assertFalse(os.path.exists(path))
        text = "\n".join(lines)
        self.assertIn("at 3 requests/second", text)
        self.assertIn("assuming", text)
        self.assertIn("requests ", text)

    def test_lock_is_removed_when_login_fails(self):
        root = tempfile.mkdtemp()
        missing = os.path.join(root, "missing.json")
        code = fno.main(
            ["--data", root, "--to", "2026-11-06"], now=NOW,
            cred_path=missing, log=lambda _line: None)
        self.assertEqual(code, 1)
        self.assertFalse(os.path.exists(fno.lock_path(root)))

    def test_exact_plan_uses_the_saved_list_and_the_close(self):
        root = tempfile.mkdtemp()
        fno.save_text(fno.nfo_path(root, DAY), NFO)
        _index_file(root, "NIFTY 50", TO, 100)
        _index_file(root, "NIFTY BANK", TO, 100)
        progress = {"depth": {}, "spans": {}, "done": []}
        closes, fetches = fno._local_closes(root, TO)
        self.assertEqual(fetches, 0)
        plan = fno.build_plan(fno.load_saved_nfo(root, DAY), closes, TO, progress, DAY, False, fetches)
        self.assertEqual(len(plan["futures"]), 2)
        self.assertEqual(plan["option_count"], 2)
        self.assertEqual([row["instrument_token"] for row in plan["contracts"]], ["333", "334"])
        self.assertFalse(plan["assumed"])
        span_day, span_5 = fno._spans(progress)
        horizon = kh.assumed_earliest("day", TO)
        opt_horizon = TO - datetime.timedelta(days=fno.ASSUMED_OPTION_DAYS)
        per_future = kh.count_walk(TO, span_day, horizon)
        per_option = kh.count_walk(TO, span_5, opt_horizon) + kh.count_walk(TO, span_day, opt_horizon)
        self.assertEqual(plan["future_requests"], 2 * per_future)
        self.assertEqual(plan["option_requests"], 2 * per_option)
        self.assertEqual(plan["total"], plan["future_requests"] + plan["option_requests"])
        text = "\n".join(fno.plan_lines(plan, TO, "dry run"))
        self.assertIn("at 3 requests/second", text)
        self.assertNotIn("assuming", text)


class RecordedDownload(unittest.TestCase):
    def test_download_writes_oi_and_resumes_without_another_request(self):
        root = tempfile.mkdtemp()
        _index_file(root, "NIFTY 50", TO, 100)
        _index_file(root, "NIFTY BANK", TO, 100)
        calls = []

        def send(method, url, fields, headers):
            calls.append(url)
            self.assertNotIn("api_secret", url)
            if url.endswith("/instruments/NFO"):
                return 200, NFO.encode("utf-8")
            token = url.split("/historical/")[1].split("/")[0]
            interval = url.split("/historical/")[1].split("/")[1].split("?")[0]
            key = token + "|" + interval
            nth = sum(1 for seen in calls if ("/historical/%s/%s" % (token, interval)) in seen)
            if token in ("111", "336"):
                self.assertIn("continuous=1", url)
                self.assertEqual(interval, "day")
            else:
                self.assertNotIn("continuous=", url)
                self.assertIn(token, ("333", "334"))
            self.assertIn("oi=1", url)
            if nth == 1:
                stamp = "2026-11-06T00:00:00+0530" if interval == "day" else "2026-11-06T09:15:00+0530"
                return 200, _body(_candle(stamp, 55 if token == "111" else 7))
            self.assertLessEqual(nth, 3, key)
            return 200, _body(EMPTY)

        lines = []
        code = fno.main(
            ["--data", root, "--to", "2026-11-06"], now=NOW, send=send,
            log=lines.append, cred_path=_cred(root), token_path=_token(root))
        self.assertEqual(code, 0, "\n".join(lines))
        self.assertFalse(os.path.exists(fno.lock_path(root)))
        text = "\n".join(lines)
        self.assertIn("NIFTY first 2026-11-06", text)
        self.assertIn("RELIANCE first 2026-11-06", text)
        self.assertIn("NIFTY 2026-11-10: 2 contracts, 4 bars, earliest 2026-11-06", text)
        future = fno.read_bars(fno.futures_file(root, "NIFTY"))
        self.assertEqual(future[0]["oi"], 55.0)
        option = fno.option_file(root, "NIFTY", datetime.date(2026, 11, 10), "5minute", "NIFTY25N1024000CE")
        day = fno.option_file(root, "NIFTY", datetime.date(2026, 11, 10), "day", "NIFTY25N1024000PE")
        self.assertTrue(os.path.isfile(option))
        self.assertEqual(fno.read_bars(option)[0]["oi"], 7.0)
        self.assertTrue(os.path.isfile(day))
        self.assertFalse(os.path.isfile(
            fno.option_file(root, "NIFTY", datetime.date(2026, 11, 10), "5minute", "NIFTY25N1010000CE")))
        self.assertFalse(any("/historical/222/" in url for url in calls))
        self.assertTrue(os.path.isfile(fno.nfo_path(root, DAY)))
        self.assertFalse(os.path.isfile(os.path.join(root, "progress.json")))
        with open(fno.nfo_path(root, DAY), encoding="utf-8") as fh:
            saved = fh.read()
        self.assertIn("NIFTY25NOVFUT", saved)
        used = len(calls)
        again = []

        def send_again(method, url, fields, headers):
            again.append(url)
            raise AssertionError("resume must not call the API: %s" % url)

        code = fno.main(
            ["--data", root, "--to", "2026-11-06"], now=NOW, send=send_again,
            log=lines.append, cred_path=_cred(root), token_path=_token(root))
        self.assertEqual(code, 0)
        self.assertEqual(again, [])
        self.assertGreater(used, 0)


class _List(object):
    """A file-like sink for redirect_stderr."""

    def __init__(self, lines):
        self.lines = lines

    def write(self, text):
        if text.strip():
            self.lines.append(text.strip())
        return len(text)

    def flush(self):
        return None


def _cred(root):
    path = os.path.join(root, "credentials.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({"api_key": "kite-test-api-key", "api_secret": "kite-test-api-secret"}, fh)
    return path


def _token(root):
    path = os.path.join(root, "token.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({"access_token": "kite-test-access-token", "date": DAY.isoformat()}, fh)
    return path


if __name__ == "__main__":
    unittest.main()
