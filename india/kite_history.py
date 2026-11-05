#!/usr/bin/env python3
"""Download Zerodha Kite historical candles into data/kite.

    python3 india/kite_history.py --universe india/universe/nifty500.csv --interval 5minute
    python3 india/kite_history.py --symbols-file symbols.txt --interval day --dry-run
    python3 india/kite_history.py --interval minute

The api_key and access token come from ~/.kite (see kite_login.py). They are
sent as the Authorization header and are never written under this repo.
data/ is gitignored.

Kite stamps the start of each candle in +05:30. Files keep that start time.
A stopped run continues from data/kite/progress.json. --dry-run prints the
request count and the estimated time and does not call the API.

Nothing here places an order. Standard library only.
"""

import csv
import datetime
import gzip
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from india import kite_login

# Days Kite accepts in one request. If a span is rejected, it is halved.
MAX_DAYS = {"day": 2000, "5minute": 100, "minute": 60}
INTERVALS = ("day", "5minute", "minute")
RATE = 3.0
RETRY_429 = 3
RETRY_5XX = 3
API = "https://api.kite.trade"
INSTRUMENTS_URL = API + "/instruments/NSE"
# Minute data was backfilled to about early 2015. Day candles go to the late 1990s.
# A dry run with no saved depth uses these, and says so.
HORIZON = {
    "minute": datetime.date(2015, 1, 1),
    "5minute": datetime.date(2015, 1, 1),
    "day": datetime.date(1996, 1, 1),
}
MOVE_LIMIT = 0.20
SESSION_BARS_5M = 75

# The four broad indices, plus the NIFTY sector indices. The name on the left
# of INDEX_ALIASES is the one people type; the value is Kite's tradingsymbol
# when the two differ.
INDEX_ALIASES = {
    "NIFTY SMALLCAP 100": "NIFTY SMLCAP 100",
    "NIFTY FINANCIAL SERVICES": "NIFTY FIN SERVICE",
    "NIFTY PRIVATE BANK": "NIFTY PVT BANK",
    "NIFTY CONSUMER DURABLES": "NIFTY CONSR DURBL",
    "NIFTY OIL & GAS": "NIFTY OIL AND GAS",
    "NIFTY INFRASTRUCTURE": "NIFTY INFRA",
    "NIFTY SERVICES SECTOR": "NIFTY SERV SECTOR",
}
DEFAULT_INDICES = [
    "NIFTY 50",
    "NIFTY BANK",
    "NIFTY MIDCAP 100",
    "NIFTY SMALLCAP 100",
    "NIFTY AUTO",
    "NIFTY ENERGY",
    "NIFTY FINANCIAL SERVICES",
    "NIFTY FMCG",
    "NIFTY IT",
    "NIFTY MEDIA",
    "NIFTY METAL",
    "NIFTY PHARMA",
    "NIFTY PSU BANK",
    "NIFTY REALTY",
    "NIFTY PRIVATE BANK",
    "NIFTY HEALTHCARE",
    "NIFTY CONSUMER DURABLES",
    "NIFTY OIL & GAS",
]
BAR_FIELDS = ["datetime_start_ist", "open", "high", "low", "close", "volume"]
CHECK_FIELDS = ["symbol", "check", "date", "bars", "prev_close", "close", "change"]
DEFAULT_ROOT = os.path.join("data", "kite")


class KiteError(Exception):
    pass


class LoginExpired(KiteError):
    pass


class SpanRejected(KiteError):
    pass


def chunk_spans(start, end, max_days):
    """Inclusive (from, to) pairs. Each pair covers at most max_days calendar days."""
    if max_days < 1:
        raise KiteError("span must be at least 1 day")
    if end < start:
        return []
    spans = []
    cursor = start
    while cursor <= end:
        chunk_end = cursor + datetime.timedelta(days=max_days - 1)
        if chunk_end > end:
            chunk_end = end
        spans.append((cursor, chunk_end))
        cursor = chunk_end + datetime.timedelta(days=1)
    return spans


def count_probe(today, span, earliest):
    """How many windows a depth probe makes, including the empty one that stops it."""
    end = today
    n = 0
    while n < 2000:
        start = end - datetime.timedelta(days=span - 1)
        n += 1
        if end < earliest:
            return n
        end = start - datetime.timedelta(days=1)
        if end.year < 1990:
            return n
    return n


def estimate_requests(today, earliest, span, probe, instruments):
    """Download chunks, plus a probe when the depth is not known yet."""
    downloads = len(chunk_spans(earliest, today, span))
    probes = count_probe(today, span, earliest) if probe else 0
    return {
        "probe": probes,
        "download": downloads,
        "instruments": 1 if instruments else 0,
        "total": probes + downloads + (1 if instruments else 0),
    }


def format_eta(seconds):
    seconds = int(round(max(0, seconds)))
    if seconds < 60:
        return "%ds" % seconds
    minutes, sec = divmod(seconds, 60)
    if minutes < 60:
        return "%dm %02ds" % (minutes, sec)
    hours, minutes = divmod(minutes, 60)
    return "%dh %02dm" % (hours, minutes)


def format_progress(done, remaining, rate=RATE):
    left = (remaining / rate) if rate else 0
    return "%d done, %d remaining, about %s left" % (done, remaining, format_eta(left))


class TokenBucket(object):
    """A bucket of `capacity` tokens, refilled at `rate` per second.

    The bucket starts full, so the first `capacity` calls do not wait.
    The next call waits until one token has been refilled.
    """

    def __init__(self, rate=RATE, capacity=None, clock=None, sleep=None):
        self.rate = float(rate)
        self.capacity = float(rate if capacity is None else capacity)
        self.clock = clock or time.monotonic
        self.sleep = sleep or time.sleep
        self.tokens = self.capacity
        self.updated = self.clock()

    def take(self):
        while True:
            now = self.clock()
            elapsed = now - self.updated
            if elapsed < 0:
                elapsed = 0.0
            self.updated = now
            self.tokens = min(self.capacity, self.tokens + elapsed * self.rate)
            if self.tokens >= 1.0:
                self.tokens -= 1.0
                return
            self.sleep((1.0 - self.tokens) / self.rate)


def parse_kite_stamp(text):
    """Kite candle time -> naive IST. +05:30 stamps are already IST wall time."""
    raw = str(text or "").strip()
    if len(raw) < 19:
        raise KiteError("not a Kite timestamp: %r" % (text,))
    day = raw[:10]
    clock = raw[11:19]
    try:
        local = datetime.datetime.strptime(day + " " + clock, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        raise KiteError("not a Kite timestamp: %r" % (text,))
    rest = raw[19:]
    if rest.startswith("."):
        rest = rest[1:]
        while rest and rest[0].isdigit():
            rest = rest[1:]
    if rest in ("",):
        return local
    if rest == "Z" or rest in ("+00:00", "+0000"):
        return local + datetime.timedelta(hours=5, minutes=30)
    sign = rest[0]
    if sign not in ("+", "-") or len(rest) < 5:
        raise KiteError("not a Kite timestamp: %r" % (text,))
    digits = rest[1:].replace(":", "")
    if len(digits) < 4 or not digits[:4].isdigit():
        raise KiteError("not a Kite timestamp: %r" % (text,))
    off = int(digits[:2]) * 60 + int(digits[2:4])
    if sign == "+":
        # +05:30 is the exchange zone: the clock in the string is IST.
        if off == 5 * 60 + 30:
            return local
        return local - datetime.timedelta(minutes=off) + datetime.timedelta(hours=5, minutes=30)
    return local + datetime.timedelta(minutes=off) + datetime.timedelta(hours=5, minutes=30)


def _plain(value):
    number = float(value)
    if number == int(number) and abs(number) < 1e15:
        return str(int(number))
    text = ("%.8f" % number).rstrip("0").rstrip(".")
    return text or "0"


def candle_rows(raw):
    """Historical JSON body -> row dicts. An empty candle list is a real empty window."""
    try:
        data = json.loads(raw.decode("utf-8"))
    except (ValueError, AttributeError):
        raise KiteError("Kite returned something that is not JSON")
    if not isinstance(data, dict) or data.get("status") != "success":
        message = ""
        if isinstance(data, dict):
            message = str(data.get("message") or "")
        raise KiteError(message or "Kite historical request failed")
    candles = ((data.get("data") or {}).get("candles")) or []
    rows = []
    for item in candles:
        if not item or len(item) < 6:
            continue
        stamp = parse_kite_stamp(item[0])
        rows.append({
            "datetime_start_ist": stamp.strftime("%Y-%m-%d %H:%M:%S"),
            "start": stamp,
            "open": item[1],
            "high": item[2],
            "low": item[3],
            "close": item[4],
            "volume": item[5],
        })
    return rows


def _body_message(raw):
    try:
        data = json.loads(raw.decode("utf-8"))
    except (ValueError, AttributeError):
        return ""
    if isinstance(data, dict):
        return str(data.get("message") or data.get("error_type") or "")
    return ""


def span_rejected(status, message):
    if status != 400:
        return False
    text = (message or "").lower()
    return "max limit" in text or "interval exceeds" in text


def history_url(token, interval, start, end):
    if interval == "day":
        frm = "%s 00:00:00" % start.isoformat()
        to = "%s 23:59:59" % end.isoformat()
    else:
        frm = "%s 09:15:00" % start.isoformat()
        to = "%s 15:30:00" % end.isoformat()
    query = urllib.parse.urlencode([("from", frm), ("to", to)])
    return "%s/instruments/historical/%s/%s?%s" % (API, token, interval, query)


class Client(object):
    """Rate-limited Kite calls. 429 waits 2s, 5xx backs off, 403 stops the run."""

    def __init__(self, send, api_key, access_token, bucket, sleep, log):
        self.send = send
        self.api_key = api_key
        self.access_token = access_token
        self.bucket = bucket
        self.sleep = sleep
        self.log = log
        self.spans = dict(MAX_DAYS)
        self.announced = set()
        self.http = 0
        self.planned = 0

    def note(self):
        self.http += 1
        if self.http % 50 == 0:
            remaining = self.planned - self.http
            if remaining < 0:
                remaining = 0
            self.log(format_progress(self.http, remaining))

    def _headers(self):
        return {
            "Authorization": "token %s:%s" % (self.api_key, self.access_token),
            "X-Kite-Version": "3",
        }

    def call(self, method, url):
        """One logical call, with retries. Each attempt takes a rate-limit token."""
        retries_429 = 0
        retries_5xx = 0
        backoff = 1
        while True:
            self.bucket.take()
            self.note()
            status, body = self.send(method, url, None, self._headers())
            if status == 403:
                raise LoginExpired(
                    "Kite refused the token (403). Please re-login: python3 india/kite_login.py")
            if status == 429:
                retries_429 += 1
                if retries_429 > RETRY_429:
                    raise KiteError("Kite rate limit (429) after %d retries" % RETRY_429)
                self.sleep(2)
                continue
            if status >= 500:
                retries_5xx += 1
                if retries_5xx > RETRY_5XX:
                    raise KiteError("Kite server error %s after %d retries" % (status, RETRY_5XX))
                self.sleep(backoff)
                backoff *= 2
                continue
            return status, body

    def instruments_csv(self):
        status, body = self.call("GET", INSTRUMENTS_URL)
        if status != 200:
            raise KiteError("instruments request failed (%s)" % status)
        if body[:2] == b"\x1f\x8b":
            body = gzip.decompress(body)
        return body.decode("utf-8")

    def fetch_exact(self, token, interval, start, end):
        status, body = self.call("GET", history_url(token, interval, start, end))
        message = _body_message(body)
        if span_rejected(status, message):
            width = (end - start).days + 1
            self.spans[interval] = max(1, width // 2)
            raise SpanRejected(message or "interval exceeds max limit")
        if status != 200:
            raise KiteError(message or "Kite historical request failed (%s)" % status)
        return candle_rows(body)

    def window(self, token, interval, start, end, anchor):
        """Fetch [start, end]. A rejected span is halved and the window is rebuilt.

        anchor 'start' keeps the start (a download walking forward).
        anchor 'end' keeps the end (a probe walking backward).
        """
        shrunk = False
        guard = 0
        while guard < 20:
            guard += 1
            try:
                rows = self.fetch_exact(token, interval, start, end)
            except SpanRejected:
                shrunk = True
                span = self.spans[interval]
                width = (end - start).days + 1
                if width <= 1 or span >= width:
                    raise KiteError("Kite rejected a %d-day span" % width)
                if anchor == "start":
                    end = start + datetime.timedelta(days=span - 1)
                else:
                    start = end - datetime.timedelta(days=span - 1)
                continue
            if shrunk and interval not in self.announced:
                self.announced.add(interval)
                self.log("%s span accepted: %d days" % (interval, self.spans[interval]))
            return rows, start, end
        raise KiteError("gave up shrinking the %s span" % interval)


def probe_depth(fetch, today, span):
    """Earliest candle date. `fetch(start, end)` returns rows or [].

    Steps back one span at a time. The window that comes back empty stops it.
    """
    end = today
    earliest = None
    guard = 0
    while guard < 2000:
        guard += 1
        start = end - datetime.timedelta(days=span - 1)
        rows = fetch(start, end)
        if not rows:
            return earliest
        first = min(row["start"].date() for row in rows)
        if earliest is None or first < earliest:
            earliest = first
        end = start - datetime.timedelta(days=1)
        if end.year < 1990:
            return earliest
    return earliest


def parse_instruments(text):
    rows = []
    reader = csv.DictReader(text.splitlines())
    for row in reader:
        symbol = (row.get("tradingsymbol") or "").strip()
        token = (row.get("instrument_token") or "").strip()
        if not symbol or not token:
            continue
        rows.append({
            "instrument_token": token,
            "tradingsymbol": symbol,
            "instrument_type": (row.get("instrument_type") or "").strip(),
            "segment": (row.get("segment") or "").strip(),
            "exchange": (row.get("exchange") or "").strip(),
        })
    return rows


def index_candidates(name):
    found = [name]
    alias = INDEX_ALIASES.get(name)
    if alias and alias not in found:
        found.append(alias)
    return found


def lookup_instrument(name, rows):
    """(token, tradingsymbol) for an equity or an index. None when it is absent."""
    by_name = {}
    for row in rows:
        by_name.setdefault(row["tradingsymbol"].upper(), []).append(row)
    for candidate in index_candidates(name):
        matches = by_name.get(candidate.upper(), [])
        indices = [row for row in matches if row["segment"] == "INDICES"]
        equities = [row for row in matches if row["segment"] == "NSE" and row["instrument_type"] == "EQ"]
        pick = None
        if indices:
            pick = indices[0]
        elif equities:
            pick = equities[0]
        elif matches:
            pick = matches[0]
        if pick:
            return pick["instrument_token"], pick["tradingsymbol"]
    return None


def read_symbol_lines(path):
    names = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            text = line.strip()
            if not text or text.startswith("#"):
                continue
            names.append(text.upper())
    return names


def read_universe(path):
    """NSE constituents CSV. The Symbol column, after any title line."""
    with open(path, encoding="utf-8-sig", newline="") as fh:
        lines = fh.read().splitlines()
    start = 0
    for i, line in enumerate(lines):
        cells = [cell.strip() for cell in line.split(",")]
        if "Symbol" in cells or "symbol" in cells:
            start = i
            break
    reader = csv.DictReader(lines[start:])
    names = []
    for row in reader:
        if not row:
            continue
        symbol = (row.get("Symbol") or row.get("symbol") or "").strip()
        if symbol:
            names.append(symbol.upper())
    return names


def dedupe(names):
    out = []
    seen = set()
    for name in names:
        key = (name or "").strip().upper()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(key)
    return out


def symbol_from_path(path):
    name = os.path.basename(path)
    if name.endswith(".csv.gz"):
        return name[:-len(".csv.gz")]
    raise KiteError("not a Kite candle file: %s" % name)


def read_bars(path):
    """One SYMBOL.csv.gz -> rows with a naive IST start."""
    rows = []
    with gzip.open(path, "rt", encoding="utf-8-sig", newline="") as fh:
        for row in csv.DictReader(fh):
            stamp = parse_kite_stamp(row["datetime_start_ist"])
            rows.append({
                "datetime_start_ist": stamp.strftime("%Y-%m-%d %H:%M:%S"),
                "start": stamp,
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"]),
                "volume": float(row["volume"] or 0),
            })
    rows.sort(key=lambda row: row["datetime_start_ist"])
    return rows


def merge_rows(existing, extra):
    """existing wins on a duplicate timestamp. Result is oldest first."""
    by_stamp = {}
    for row in existing:
        by_stamp[row["datetime_start_ist"]] = row
    for row in extra:
        if row["datetime_start_ist"] not in by_stamp:
            by_stamp[row["datetime_start_ist"]] = row
    return [by_stamp[key] for key in sorted(by_stamp)]


def _atomic(path, write_fn):
    folder = os.path.dirname(path)
    if folder:
        os.makedirs(folder, exist_ok=True)
    tmp = path + ".tmp"
    write_fn(tmp)
    os.replace(tmp, path)


def write_bars(path, rows):
    def write(tmp):
        with gzip.open(tmp, "wt", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=BAR_FIELDS, lineterminator="\n", extrasaction="ignore")
            writer.writeheader()
            for row in rows:
                writer.writerow({
                    "datetime_start_ist": row["datetime_start_ist"],
                    "open": _plain(row["open"]),
                    "high": _plain(row["high"]),
                    "low": _plain(row["low"]),
                    "close": _plain(row["close"]),
                    "volume": _plain(row["volume"]),
                })
    _atomic(path, write)


def bar_path(root, interval, symbol):
    if "/" in symbol or "\\" in symbol:
        raise KiteError("symbol is not a file name: %s" % symbol)
    return os.path.join(root, interval, symbol + ".csv.gz")


def append_bars(path, rows):
    existing = read_bars(path) if os.path.isfile(path) else []
    merged = merge_rows(existing, rows)
    write_bars(path, merged)
    return merged


def load_progress(path):
    if not os.path.isfile(path):
        return {"depth": {}, "spans": {}, "done": []}
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    data.setdefault("depth", {})
    data.setdefault("spans", {})
    data.setdefault("done", [])
    return data


def save_progress(path, data):
    def write(tmp):
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, sort_keys=True)
            fh.write("\n")
    _atomic(path, write)


def depth_key(symbol, interval):
    return "%s|%s" % (symbol, interval)


def chunk_covered(progress, symbol, interval, start, end):
    start_s = start.isoformat()
    end_s = end.isoformat()
    for row in progress.get("done") or []:
        if row.get("symbol") != symbol or row.get("interval") != interval:
            continue
        if row.get("start") <= start_s and row.get("end") >= end_s:
            return True
    return False


def mark_chunk(progress, symbol, interval, start, end, candles):
    progress["done"].append({
        "symbol": symbol,
        "interval": interval,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "candles": candles,
    })


def session_checks(rows, interval):
    """Short 5-minute sessions (not 75 bars), and day-to-day closes over 20%."""
    by_date = {}
    for row in rows:
        by_date.setdefault(row["start"].date(), []).append(row)
    short = []
    closes = []
    for day in sorted(by_date):
        bars = by_date[day]
        if interval == "5minute" and len(bars) != SESSION_BARS_5M:
            short.append((day, len(bars)))
        last = max(bars, key=lambda item: item["datetime_start_ist"])
        closes.append((day, float(last["close"])))
    moves = []
    for i in range(1, len(closes)):
        prev_day, prev_close = closes[i - 1]
        day, close = closes[i]
        if prev_close <= 0:
            continue
        change = (close - prev_close) / prev_close
        if change > MOVE_LIMIT or change < -MOVE_LIMIT:
            moves.append((day, prev_close, close, change))
    return short, moves


def check_rows(symbol, interval, rows):
    short, moves = session_checks(rows, interval)
    out = []
    if interval == "5minute":
        out.append({
            "symbol": symbol, "check": "short_sessions", "date": "",
            "bars": str(len(short)), "prev_close": "", "close": "", "change": "",
        })
        for day, count in short:
            out.append({
                "symbol": symbol, "check": "short_session", "date": day.isoformat(),
                "bars": str(count), "prev_close": "", "close": "", "change": "",
            })
    for day, prev_close, close, change in moves:
        out.append({
            "symbol": symbol, "check": "day_move", "date": day.isoformat(),
            "bars": "", "prev_close": _plain(prev_close), "close": _plain(close),
            "change": "%.4f" % change,
        })
    return out


def write_checks(path, records):
    def write(tmp):
        with open(tmp, "w", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=CHECK_FIELDS, lineterminator="\n")
            writer.writeheader()
            for row in records:
                writer.writerow(row)
    _atomic(path, write)


def instruments_path(root, day):
    return os.path.join(root, "instruments", "NSE-%s.csv" % day.isoformat())


def load_instruments(root, day, client):
    path = instruments_path(root, day)
    if os.path.isfile(path) and os.path.getsize(path) > 0:
        with open(path, encoding="utf-8") as fh:
            return parse_instruments(fh.read())
    text = client.instruments_csv()
    def write(tmp):
        with open(tmp, "w", encoding="utf-8", newline="") as fh:
            fh.write(text if text.endswith("\n") else text + "\n")
    _atomic(path, write)
    return parse_instruments(text)


def _saved_depth(progress, symbol, interval):
    key = depth_key(symbol, interval)
    if key not in progress["depth"]:
        return None, False
    raw = progress["depth"][key]
    if not raw:
        return None, True
    return datetime.date.fromisoformat(raw), True


def _saved_depth_any(progress, name, interval):
    """Depth is stored under the tradingsymbol, which may be the alias."""
    for candidate in index_candidates(name):
        known, probed = _saved_depth(progress, candidate, interval)
        if probed:
            return known, True
    return None, False


def download_symbol(client, progress, root, symbol, token, interval, today, save):
    """Probe, then download every unfinished chunk. Returns the merged rows."""
    known, probed = _saved_depth(progress, symbol, interval)
    if probed:
        earliest = known
    else:
        earliest = client_probe(client, token, interval, today)
        progress["depth"][depth_key(symbol, interval)] = earliest.isoformat() if earliest else ""
        progress["spans"][interval] = client.spans[interval]
        save()
    if earliest is None or earliest > today:
        return []
    span = client.spans[interval]
    cursor = earliest
    path = bar_path(root, interval, symbol)
    while cursor <= today:
        span = client.spans[interval]
        chunk_end = cursor + datetime.timedelta(days=span - 1)
        if chunk_end > today:
            chunk_end = today
        if chunk_covered(progress, symbol, interval, cursor, chunk_end):
            cursor = chunk_end + datetime.timedelta(days=1)
            continue
        rows, actual_start, actual_end = client.window(token, interval, cursor, chunk_end, "start")
        if rows:
            append_bars(path, rows)
        mark_chunk(progress, symbol, interval, actual_start, actual_end, len(rows))
        progress["spans"][interval] = client.spans[interval]
        save()
        cursor = actual_end + datetime.timedelta(days=1)
    if not os.path.isfile(path):
        return []
    return read_bars(path)


def client_probe(client, token, interval, today):
    """Depth probe through the client, so a rejected span is halved and retried."""
    end = today
    earliest = None
    guard = 0
    while guard < 2000:
        guard += 1
        span = client.spans[interval]
        start = end - datetime.timedelta(days=span - 1)
        rows, actual_start, actual_end = client.window(token, interval, start, end, "end")
        if not rows:
            return earliest
        first = min(row["start"].date() for row in rows)
        if earliest is None or first < earliest:
            earliest = first
        end = actual_start - datetime.timedelta(days=1)
        if end.year < 1990:
            return earliest
    return earliest


def gather_names(universe, symbols_file, indices):
    names = []
    if universe:
        names.extend(read_universe(universe))
    if symbols_file:
        names.extend(read_symbol_lines(symbols_file))
    if indices:
        names.extend(part.strip().upper() for part in indices.split(",") if part.strip())
    return dedupe(names)


def dry_run_lines(names, interval, today, progress, root):
    span = int((progress.get("spans") or {}).get(interval) or MAX_DAYS[interval])
    need_instruments = not os.path.isfile(instruments_path(root, today))
    probe = 0
    download = 0
    assumed = 0
    for name in names:
        known, probed = _saved_depth_any(progress, name, interval)
        if probed and known:
            download += len(chunk_spans(known, today, span))
        elif probed:
            continue
        else:
            assumed += 1
            horizon = HORIZON[interval]
            probe += count_probe(today, span, horizon)
            download += len(chunk_spans(horizon, today, span))
    total = probe + download + (1 if need_instruments else 0)
    lines = [
        "dry run: %d symbols, interval %s, span %d days" % (len(names), interval, span),
    ]
    if assumed:
        lines.append("%d symbols have no saved depth; estimating from %s" % (
            assumed, HORIZON[interval].isoformat()))
    lines.append("requests %d (%d instruments, %d probe, %d download)" % (
        total, 1 if need_instruments else 0, probe, download))
    lines.append("at %g requests/second, about %s" % (RATE, format_eta(total / RATE)))
    return lines


def apply_saved_spans(client, progress):
    for interval, span in (progress.get("spans") or {}).items():
        if interval in client.spans and span:
            client.spans[interval] = int(span)
            if int(span) < MAX_DAYS.get(interval, int(span)):
                client.announced.add(interval)


def run(names, interval, root, today, send, api_key, access_token, bucket, sleep, log, dry_run=False):
    if interval not in MAX_DAYS:
        raise KiteError("interval must be day, 5minute or minute, not %r" % (interval,))
    if not names:
        raise KiteError("no symbols. Pass --universe, --symbols-file, or --indices")
    progress_path = os.path.join(root, "progress.json")
    progress = load_progress(progress_path)
    if dry_run:
        for line in dry_run_lines(names, interval, today, progress, root):
            log(line)
        return 0
    def save():
        save_progress(progress_path, progress)
    client = Client(send, api_key, access_token, bucket, sleep, log)
    apply_saved_spans(client, progress)
    # The estimate is replaced as each symbol's real depth is known. It only
    # feeds the "remaining" half of the progress line.
    client.planned = estimate_requests(
        today, HORIZON[interval], client.spans[interval], True, True)["total"] * max(1, len(names))
    instruments = load_instruments(root, today, client)
    resolved = []
    seen_tokens = set()
    for name in names:
        found = lookup_instrument(name, instruments)
        if not found:
            log("no instrument for %s" % name)
            continue
        token, tradingsymbol = found
        if token in seen_tokens:
            continue
        seen_tokens.add(token)
        resolved.append((tradingsymbol, token))
    records = []
    for symbol, token in resolved:
        rows = download_symbol(client, progress, root, symbol, token, interval, today, save)
        records.extend(check_rows(symbol, interval, rows))
    report = os.path.join(root, "reports", "%s-checks.csv" % interval)
    write_checks(report, records)
    log("wrote %s" % report)
    return 0


def main(argv=None, send=None, today=None, bucket=None, sleep=None, log=None,
         cred_path=None, token_path=None):
    import argparse
    parser = argparse.ArgumentParser(description="Download Kite historical candles. Nothing is placed.")
    parser.add_argument("--universe", help="NSE constituents CSV with a Symbol column")
    parser.add_argument("--symbols-file", help="one symbol per line")
    parser.add_argument("--indices", default=",".join(DEFAULT_INDICES),
                        help="comma separated index names. Default is the four broad indices and the NIFTY sector indices.")
    parser.add_argument("--interval", required=True, choices=INTERVALS)
    parser.add_argument("--data", default=DEFAULT_ROOT, help="output root (default data/kite)")
    parser.add_argument("--dry-run", action="store_true", help="print the request count and stop")
    args = parser.parse_args(argv)
    day = today or datetime.date.today()
    emit = log or (lambda line: print(line))
    try:
        names = gather_names(args.universe, args.symbols_file, args.indices)
        if args.dry_run:
            return run(names, args.interval, args.data, day, send, "", "", None, None, emit, dry_run=True)
        api_key, _secret = kite_login.load_credentials(cred_path or kite_login.CRED_PATH)
        access_token = kite_login.load_token(token_path or kite_login.TOKEN_PATH, day)
        sender = send or kite_login.urlopen_send
        limiter = bucket or TokenBucket(RATE)
        pause = sleep or time.sleep
        return run(names, args.interval, args.data, day, sender, api_key, access_token,
                   limiter, pause, emit, dry_run=False)
    except LoginExpired as exc:
        print("kite_history.py: %s" % exc, file=sys.stderr)
        return 1
    except (KiteError, kite_login.LoginError, OSError, urllib.error.URLError) as exc:
        print("kite_history.py: %s" % exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
