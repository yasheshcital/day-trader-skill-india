"""Kite login and history, with recorded responses. No network."""

import csv
import datetime
import json
import os
import tempfile
import unittest
import hashlib
import io
from contextlib import redirect_stdout

from _load import ROOT, load

login = load("india", "kite_login")
kh = load("india", "kite_history")
bt = load("india", "backtest")

DAY = datetime.date(2026, 11, 5)
API_KEY = "kite-test-api-key"
API_SECRET = "kite-test-api-secret"
ACCESS_TOKEN = "kite-test-access-token"
SAMPLE_HISTORY = {
    "status": "success",
    "data": {"candles": [
        ["2020-04-10T09:15:00+0530", 100, 105, 99, 102, 1000],
        ["2020-04-10T09:20:00+05:30", 102, 106, 101, 104, 1100],
    ]},
}
EMPTY_HISTORY = {"status": "success", "data": {"candles": []}}
SPAN_ERROR = {
    "status": "error",
    "message": "interval exceeds max limit: 100 days",
    "error_type": "InputException",
}
INSTRUMENTS = "\n".join([
    "instrument_token,exchange_token,tradingsymbol,name,last_price,expiry,strike,tick_size,lot_size,instrument_type,segment,exchange",
    "738561,1,RELIANCE,RELIANCE INDUSTRIES,0,,,0.1,1,EQ,NSE,NSE",
    "779521,2,TCS,TATA CONSULTANCY,0,,,0.1,1,EQ,NSE,NSE",
    "256265,3,NIFTY 50,NIFTY 50,0,,,0,0,EQ,INDICES,NSE",
    "260873,4,NIFTY SMLCAP 100,NIFTY SMLCAP 100,0,,,0,0,EQ,INDICES,NSE",
]) + "\n"


class OpenBucket(object):
    def __init__(self):
        self.n = 0

    def take(self):
        self.n += 1


def _body(payload):
    return json.dumps(payload).encode("utf-8")


def _bar(day, close, hour=9, minute=15):
    stamp = datetime.datetime(day.year, day.month, day.day, hour, minute)
    return {
        "datetime_start_ist": stamp.strftime("%Y-%m-%d %H:%M:%S"),
        "start": stamp,
        "open": close, "high": close, "low": close, "close": close, "volume": 1,
    }


def _session(day, price=100.0):
    start = datetime.datetime(day.year, day.month, day.day, 9, 15)
    rows = []
    for i in range(75):
        stamp = start + datetime.timedelta(minutes=5 * i)
        px = price + i
        rows.append({
            "datetime_start_ist": stamp.strftime("%Y-%m-%d %H:%M:%S"),
            "start": stamp,
            "open": px, "high": px + 1, "low": px - 1, "close": px + 0.5, "volume": 10 + i,
        })
    return rows


class ChunksAndDepth(unittest.TestCase):
    def test_spans_are_inclusive_and_capped(self):
        one = kh.chunk_spans(datetime.date(2020, 1, 1), datetime.date(2020, 1, 1), 100)
        self.assertEqual(one, [(datetime.date(2020, 1, 1), datetime.date(2020, 1, 1))])
        # 2020-01-01 through 2020-04-09 is 100 days (2020 is a leap year).
        full = kh.chunk_spans(datetime.date(2020, 1, 1), datetime.date(2020, 4, 9), 100)
        self.assertEqual(full, [(datetime.date(2020, 1, 1), datetime.date(2020, 4, 9))])
        extra = kh.chunk_spans(datetime.date(2020, 1, 1), datetime.date(2020, 4, 10), 100)
        self.assertEqual(extra, [
            (datetime.date(2020, 1, 1), datetime.date(2020, 4, 9)),
            (datetime.date(2020, 4, 10), datetime.date(2020, 4, 10)),
        ])
        self.assertEqual(kh.MAX_DAYS, {"day": 2000, "5minute": 100, "minute": 60})

    def test_depth_probe_stops_on_the_empty_window(self):
        floor = datetime.date(2020, 1, 15)
        seen = []

        def fetch(start, end):
            seen.append((start, end))
            if end < floor:
                return []
            first = start if start >= floor else floor
            return [_bar(first, 10)]

        found = kh.probe_depth(fetch, datetime.date(2020, 6, 1), 100)
        self.assertEqual(found, floor)
        self.assertLess(seen[-1][1], floor)
        self.assertGreaterEqual(seen[-2][1], floor)

    def test_stamps_are_ist_starts(self):
        first = kh.parse_kite_stamp("2020-04-10T09:15:00+0530")
        second = kh.parse_kite_stamp("2020-04-10T09:20:00+05:30")
        self.assertEqual(first, datetime.datetime(2020, 4, 10, 9, 15))
        self.assertEqual(second, datetime.datetime(2020, 4, 10, 9, 20))
        rows = kh.candle_rows(_body(SAMPLE_HISTORY))
        self.assertEqual([row["datetime_start_ist"] for row in rows],
                         ["2020-04-10 09:15:00", "2020-04-10 09:20:00"])


class RateLimit(unittest.TestCase):
    def test_bucket_allows_three_then_waits(self):
        clock = [0.0]

        def now():
            return clock[0]

        def sleep(seconds):
            clock[0] += seconds

        bucket = kh.TokenBucket(rate=3, capacity=3, clock=now, sleep=sleep)
        bucket.take()
        bucket.take()
        bucket.take()
        self.assertEqual(clock[0], 0.0)
        bucket.take()
        self.assertAlmostEqual(clock[0], 1.0 / 3.0, places=6)

    def test_429_waits_two_seconds_and_stops_after_three_retries(self):
        sleeps = []
        calls = {"n": 0}

        def send(method, url, fields, headers):
            calls["n"] += 1
            if calls["n"] < 3:
                return 429, b""
            return 200, _body(EMPTY_HISTORY)

        client = kh.Client(send, API_KEY, ACCESS_TOKEN, OpenBucket(), sleeps.append, lambda line: None)
        status, _ignored = client.call("GET", "https://api.kite.trade/instruments/NSE")
        self.assertEqual(status, 200)
        self.assertEqual(sleeps, [2, 2])

        calls["n"] = 0

        def always(method, url, fields, headers):
            calls["n"] += 1
            return 429, b""

        client.send = always
        with self.assertRaises(kh.KiteError) as caught:
            client.call("GET", "https://api.kite.trade/x")
        self.assertIn("429", str(caught.exception))
        self.assertEqual(calls["n"], 4)

    def test_5xx_backs_off(self):
        sleeps = []
        calls = {"n": 0}

        def send(method, url, fields, headers):
            calls["n"] += 1
            if calls["n"] < 4:
                return 500, b"down"
            return 200, _body(EMPTY_HISTORY)

        client = kh.Client(send, API_KEY, ACCESS_TOKEN, OpenBucket(), sleeps.append, lambda line: None)
        status, _ignored = client.call("GET", "https://api.kite.trade/x")
        self.assertEqual(status, 200)
        self.assertEqual(sleeps, [1, 2, 4])

    def test_403_stops_the_run(self):
        seen = []

        def send(method, url, fields, headers):
            seen.append(url)
            if "historical" in url:
                return 403, b'{"status":"error","message":"Token is invalid"}'
            return 200, INSTRUMENTS.encode("utf-8")

        root = tempfile.mkdtemp()
        lines = []
        with self.assertRaises(kh.LoginExpired) as caught:
            kh.run(
                ["RELIANCE", "TCS"], "day", root, DAY, send, API_KEY, ACCESS_TOKEN,
                OpenBucket(), lambda _s: None, lines.append)
        self.assertIn("re-login", str(caught.exception))
        joined = " ".join(seen)
        self.assertIn("738561", joined)
        self.assertNotIn("779521", joined)
        for folder, _dirs, names in os.walk(root):
            for name in names:
                with open(os.path.join(folder, name), encoding="utf-8", errors="replace") as fh:
                    self.assertNotIn(ACCESS_TOKEN, fh.read())


class Download(unittest.TestCase):
    def _client(self, send, lines, planned=0):
        client = kh.Client(send, API_KEY, ACCESS_TOKEN, OpenBucket(), lambda _s: None, lines.append)
        client.planned = planned
        return client

    def test_rejected_span_is_halved_and_the_accepted_limit_is_printed(self):
        widths = []

        def send(method, url, fields, headers):
            query = kh.urllib.parse.urlparse(url).query
            got = kh.urllib.parse.parse_qs(query)
            start = datetime.date.fromisoformat(got["from"][0][:10])
            end = datetime.date.fromisoformat(got["to"][0][:10])
            widths.append((end - start).days + 1)
            if widths[-1] > 50:
                return 400, _body(SPAN_ERROR)
            return 200, _body(SAMPLE_HISTORY)

        lines = []
        client = self._client(send, lines)
        rows, start, end = client.window(
            "738561", "5minute", datetime.date(2020, 1, 1), datetime.date(2020, 4, 9), "start")
        self.assertEqual(widths[0], 100)
        self.assertEqual(widths[1], 50)
        self.assertEqual((end - start).days + 1, 50)
        self.assertEqual(len(rows), 2)
        self.assertIn("5minute span accepted: 50 days", lines)

    def test_resume_skips_a_finished_chunk_and_does_not_duplicate(self):
        root = tempfile.mkdtemp()
        progress = {"depth": {"RELIANCE|5minute": "2020-01-01"}, "spans": {}, "done": [{
            "symbol": "RELIANCE", "interval": "5minute",
            "start": "2020-01-01", "end": "2020-04-09", "candles": 1,
        }]}
        kh.save_progress(os.path.join(root, "progress.json"), progress)
        kh.write_bars(kh.bar_path(root, "5minute", "RELIANCE"), [_bar(datetime.date(2020, 1, 2), 10)])
        seen = []

        def send(method, url, fields, headers):
            seen.append(url)
            return 200, _body(SAMPLE_HISTORY)

        lines = []
        client = self._client(send, lines)
        loaded = kh.load_progress(os.path.join(root, "progress.json"))

        def save():
            kh.save_progress(os.path.join(root, "progress.json"), loaded)

        rows = kh.download_symbol(
            client, loaded, root, "RELIANCE", "738561", "5minute",
            datetime.date(2020, 4, 10), save)
        self.assertEqual(len(seen), 1)
        self.assertIn("2020-04-10", seen[0])
        self.assertNotIn("from=2020-01-01", seen[0])
        stamps = [row["datetime_start_ist"] for row in rows]
        self.assertEqual(stamps, [
            "2020-01-02 09:15:00", "2020-04-10 09:15:00", "2020-04-10 09:20:00"])
        self.assertEqual(len(stamps), len(set(stamps)))
        with open(os.path.join(root, "progress.json"), encoding="utf-8") as fh:
            text = fh.read()
        self.assertNotIn(ACCESS_TOKEN, text)
        self.assertNotIn(API_SECRET, text)

    def test_overlap_keeps_the_first_row(self):
        root = tempfile.mkdtemp()
        path = kh.bar_path(root, "day", "RELIANCE")
        kh.append_bars(path, [_bar(datetime.date(2020, 1, 2), 10)])
        kh.append_bars(path, [_bar(datetime.date(2020, 1, 2), 99), _bar(datetime.date(2020, 1, 3), 11)])
        rows = kh.read_bars(path)
        self.assertEqual([row["close"] for row in rows], [10.0, 11.0])

    def test_progress_line_every_50_requests(self):
        lines = []

        def send(method, url, fields, headers):
            return 200, _body(EMPTY_HISTORY)

        client = self._client(send, lines, planned=50)
        for _i in range(50):
            client.call("GET", "https://api.kite.trade/x")
        self.assertEqual(lines, ["50 done, 0 remaining, about 0s left"])

    def test_dry_run_does_not_call_the_api(self):
        def send(method, url, fields, headers):
            raise AssertionError("dry run called the API")

        root = tempfile.mkdtemp()
        lines = []
        today = datetime.date(2026, 11, 5)
        rc = kh.run(["AAA", "BBB"], "minute", root, today, send, "", "", None, None,
                    lines.append, dry_run=True)
        self.assertEqual(rc, 0)
        one = kh.estimate_requests(today, kh.HORIZON["minute"], 60, True, False)
        total = one["probe"] * 2 + one["download"] * 2 + 1
        self.assertIn("dry run: 2 symbols, interval minute, span 60 days", lines[0])
        self.assertIn("requests %d (1 instruments, %d probe, %d download)" % (
            total, one["probe"] * 2, one["download"] * 2), lines)
        self.assertIn("2015-01-01", " ".join(lines))

    def test_alias_and_checks(self):
        rows = kh.parse_instruments(INSTRUMENTS)
        self.assertEqual(kh.lookup_instrument("NIFTY SMALLCAP 100", rows), ("260873", "NIFTY SMLCAP 100"))
        self.assertEqual(kh.lookup_instrument("RELIANCE", rows)[0], "738561")
        quiet = [
            _bar(datetime.date(2020, 1, 2), 100),
            _bar(datetime.date(2020, 1, 3), 120),
            _bar(datetime.date(2020, 1, 6), 150),
        ]
        _short, moves = kh.session_checks(quiet, "day")
        self.assertEqual([move[0] for move in moves], [datetime.date(2020, 1, 6)])
        partial = _session(datetime.date(2026, 10, 30))[:74]
        short, _moves = kh.session_checks(partial, "5minute")
        self.assertEqual(short, [(datetime.date(2026, 10, 30), 74)])


class Sessions(unittest.TestCase):
    def test_start_shifts_to_the_end_label_and_loads_like_algotest(self):
        day = datetime.date(2026, 10, 30)
        start = datetime.datetime(2026, 10, 30, 9, 15)
        self.assertEqual(bt.kite_end_label(start), datetime.datetime(2026, 10, 30, 9, 20))
        rows = _session(day)
        root = tempfile.mkdtemp()
        path = os.path.join(root, "RELIANCE.csv.gz")
        kh.write_bars(path, rows)
        tm = bt.load_timemachine()
        symbol, full, short = bt.load_kite_sessions(path, tm)
        self.assertEqual(symbol, "RELIANCE")
        self.assertEqual(short, [])
        self.assertEqual(len(full), 1)
        self.assertEqual(full[0][0], "2026-10-30")
        self.assertEqual(full[0][1][0]["slot"], 0)
        self.assertEqual(full[0][1][0]["start"], "09:15")
        self.assertEqual(full[0][1][-1]["start"], "15:25")
        candles = []
        for row in rows:
            candles.append({
                "datetime": bt.kite_end_label(row["start"]).strftime("%Y-%m-%dT%H:%M:%S"),
                "open": row["open"], "high": row["high"], "low": row["low"],
                "close": row["close"], "volume": row["volume"],
            })
        algo = os.path.join(tempfile.mkdtemp(), "RELIANCE-day.algotest.json")
        with open(algo, "w", encoding="utf-8") as fh:
            json.dump({"underlying": "NSE_RELIANCE", "candles": candles}, fh)
        _sym, algo_full, algo_short = bt.load_sessions(algo, tm)
        self.assertEqual(algo_short, [])
        for got, want in zip(full[0][1], algo_full[0][1]):
            self.assertEqual(got["slot"], want["slot"])
            self.assertEqual(got["start"], want["start"])
            self.assertEqual(got["o"], want["o"])
            self.assertEqual(got["h"], want["h"])
            self.assertEqual(got["l"], want["l"])
            self.assertEqual(got["c"], want["c"])
            self.assertEqual(got["v"], want["v"])
        loaded = bt.load_folder(root, tm, symbols=["RELIANCE"])
        self.assertEqual([item["symbol"] for item in loaded], ["RELIANCE"])


class Login(unittest.TestCase):
    def test_checksum_and_the_token_is_not_printed(self):
        digest = hashlib.sha256(b"kite-test-api-keyREQ1kite-test-api-secret").hexdigest()
        self.assertEqual(login.checksum(API_KEY, "REQ1", API_SECRET), digest)
        self.assertEqual(
            login.login_url(API_KEY),
            "https://kite.zerodha.com/connect/login?v=3&api_key=" + API_KEY)
        pasted = "https://example.test/redirect?action=login&status=success&request_token=REQ1"
        self.assertEqual(login.request_token_from(pasted), "REQ1")
        captured = {}

        def send(method, url, fields, headers):
            captured["url"] = url
            captured["fields"] = dict(fields)
            return 200, _body({"status": "success", "data": {"access_token": ACCESS_TOKEN}})

        folder = tempfile.mkdtemp()
        cred = os.path.join(folder, "credentials.json")
        token = os.path.join(folder, "token.json")
        with open(cred, "w", encoding="utf-8") as fh:
            json.dump({"api_key": API_KEY, "api_secret": API_SECRET}, fh)
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = login.main([], input_fn=lambda _prompt: pasted, send=send, today=DAY,
                            cred_path=cred, token_path=token)
        self.assertEqual(rc, 0)
        out = buf.getvalue()
        self.assertIn("api_key=" + API_KEY, out)
        self.assertNotIn(API_SECRET, out)
        self.assertNotIn(ACCESS_TOKEN, out)
        self.assertEqual(captured["url"], login.SESSION_URL)
        self.assertEqual(captured["fields"]["checksum"], digest)
        self.assertNotIn("api_secret", captured["fields"])
        with open(token, encoding="utf-8") as fh:
            saved = json.load(fh)
        self.assertEqual(saved["access_token"], ACCESS_TOKEN)
        self.assertEqual(saved["date"], "2026-11-05")
        self.assertEqual(os.stat(token).st_mode & 0o777, 0o600)


class Secrets(unittest.TestCase):
    def test_scanner_flags_a_planted_secret(self):
        folder = tempfile.mkdtemp()
        os.makedirs(os.path.join(folder, "india"))
        with open(os.path.join(folder, "india", "note.txt"), "w", encoding="utf-8") as fh:
            fh.write("access = PLANTED-KITE-TOKEN\n")
        self.assertIn(
            os.path.join(folder, "india", "note.txt"),
            list(files_containing(folder, ["PLANTED-KITE-TOKEN"])))

    def test_repo_does_not_contain_kite_secrets(self):
        for folder, names in _walk(ROOT):
            for name in names:
                self.assertNotIn(name, ("credentials.json", "token.json", "kite_credentials.json"))
        hits = list(files_containing(ROOT, _home_needles()))
        if hits:
            self.fail("a Kite credential or token value appears in %s" % ", ".join(
                os.path.relpath(path, ROOT) for path in hits))


def _walk(root):
    for folder, dirnames, names in os.walk(root):
        dirnames[:] = [name for name in dirnames if name not in (".git", "__pycache__", "data")]
        yield folder, names


def files_containing(root, needles):
    if not needles:
        return
    for folder, names in _walk(root):
        for name in names:
            path = os.path.join(folder, name)
            try:
                with open(path, encoding="utf-8", errors="replace") as fh:
                    text = fh.read()
            except OSError:
                continue
            for needle in needles:
                if needle and needle in text:
                    yield path
                    break


def _home_needles():
    found = []
    pairs = (
        (login.CRED_PATH, ("api_key", "api_secret")),
        (login.TOKEN_PATH, ("access_token",)),
    )
    for path, keys in pairs:
        try:
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, ValueError):
            continue
        if not isinstance(data, dict):
            continue
        for key in keys:
            value = str(data.get(key) or "")
            if len(value) >= 8:
                found.append(value)
    return found


if __name__ == "__main__":
    unittest.main()
