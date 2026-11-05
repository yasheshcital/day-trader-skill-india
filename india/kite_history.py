#!/usr/bin/env python3
"""Download Zerodha Kite historical candles into data/kite.

    python3 india/kite_history.py --universe india/universe/nifty500.csv --interval 5minute
    python3 india/kite_history.py --symbols-file symbols.txt --interval day --dry-run
    python3 india/kite_history.py --interval minute

The api_key and access token come from ~/.kite (see kite_login.py). They are
sent as the Authorization header and are never written under this repo.
data/ is gitignored.

Kite stamps the start of each candle in +05:30. Files keep that start time.
The walk backward from --to is the download: each non-empty window is kept,
and a symbol stops after two empty windows in a row. --to defaults to the
last finished NSE session (today at or after 15:45 IST, otherwise the previous
trading day). A session that is still open is not written. A stopped run
continues from data/kite/progress.json and the symbol's .part.csv.gz.
--dry-run prints the request count and the estimated time and does not call
the API.

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
from india import nse_market

# Days Kite accepts in one request. If a span is rejected, it is halved.
MAX_DAYS = {"day": 2000, "5minute": 100, "minute": 60}
INTERVALS = ("day", "5minute", "minute")
RATE = 3.0
RETRY_429 = 3
RETRY_5XX = 3
API = "https://api.kite.trade"
INSTRUMENTS_URL = API + "/instruments/NSE"
# Minute data was backfilled to about early 2015. When a symbol's depth is not
# known yet, a dry run assumes 10 years of 5-minute bars and 20 years of dailies.
HORIZON = {"minute": datetime.date(2015, 1, 1)}
ASSUMED_YEARS = {"5minute": 10, "day": 20}
# One empty window can be a suspension. Two in a row ends the walk.
EMPTY_STOP = 2
PROGRESS_EVERY = 25
MOVE_LIMIT = 0.20
SESSION_BARS_5M = 75
# The cash session ends at 15:30. A file may include today only after 15:45 IST,
# so the closing candle has had time to arrive.
SETTLED = datetime.time(15, 45)

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


def _years_before(day, years):
    try:
        return day.replace(year=day.year - years)
    except ValueError:
        return day.replace(year=day.year - years, day=28)


def now_ist(now=None):
    """Naive IST. `now` is already IST when a test passes one in."""
    if now is not None:
        return now
    return nse_market.to_ist(datetime.datetime.utcnow())


def previous_trading_day(day):
    """The NSE session before `day`. Weekends and NSE_HOLIDAYS are skipped."""
    cursor = day - datetime.timedelta(days=1)
    for _ in range(20):
        ok, _reason = nse_market.trading_day(cursor)
        if ok:
            return cursor
        cursor -= datetime.timedelta(days=1)
    raise KiteError("no NSE session before %s" % day.isoformat())


def default_to(now):
    """Last finished session. `now` is a naive IST datetime.

    Today, once the clock is at or after 15:45 on a trading day. Otherwise the
    previous trading day.
    """
    if isinstance(now, datetime.datetime):
        day = now.date()
        clock = now.time()
    else:
        day = now
        clock = SETTLED
    ok, _reason = nse_market.trading_day(day)
    if ok and clock >= SETTLED:
        return day
    return previous_trading_day(day)


def parse_day(text):
    raw = (text or "").strip()
    try:
        day = datetime.date.fromisoformat(raw)
    except ValueError:
        raise KiteError("--to must be YYYY-MM-DD, not %r" % (text,))
    if day.isoformat() != raw:
        raise KiteError("--to must be YYYY-MM-DD, not %r" % (text,))
    return day


def assumed_earliest(interval, today):
    """Depth used by --dry-run when this symbol has not been walked yet."""
    years = ASSUMED_YEARS.get(interval)
    if years:
        return _years_before(today, years)
    return HORIZON.get(interval, _years_before(today, 10))


def count_walk(today, span, earliest, empties=EMPTY_STOP):
    """Requests for one symbol: history windows plus the empty ones that stop it.

    A window whose end is before `earliest` is empty. Data windows reset that run.
    """
    end = today
    n = 0
    empty_run = 0
    while n < 2000:
        start = end - datetime.timedelta(days=span - 1)
        n += 1
        if end < earliest:
            empty_run += 1
            if empty_run >= empties:
                return n
        else:
            empty_run = 0
        end = start - datetime.timedelta(days=1)
        if end.year < 1990:
            return n + max(0, empties - empty_run)
    return n


def estimate_requests(today, earliest, span):
    """One backward walk. There is no second download pass."""
    return count_walk(today, span, earliest)


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


def gap_windows(windows):
    """Empty windows that have candles on both sides. `windows` is newest first."""
    chrono = list(reversed(windows))
    gaps = []
    for i, item in enumerate(chrono):
        start, end, has = item
        if has:
            continue
        older = any(prev[2] for prev in chrono[:i])
        newer = any(nxt[2] for nxt in chrono[i + 1:])
        if older and newer:
            gaps.append((start, end))
    return gaps


def probe_depth(fetch, today, span):
    """Walk backward and keep every row. Stops after two empty windows.

    `fetch(start, end)` returns rows or []. Returns (earliest date or None, rows, gaps).
    """
    end = today
    earliest = None
    kept = []
    windows = []
    empty_run = 0
    guard = 0
    while guard < 2000:
        guard += 1
        start = end - datetime.timedelta(days=span - 1)
        rows = fetch(start, end)
        windows.append((start, end, bool(rows)))
        if rows:
            empty_run = 0
            kept.extend(rows)
            first = min(row["start"].date() for row in rows)
            if earliest is None or first < earliest:
                earliest = first
        else:
            empty_run += 1
            if empty_run >= EMPTY_STOP:
                break
        end = start - datetime.timedelta(days=1)
        if end.year < 1990:
            break
    return earliest, kept, gap_windows(windows)


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


def _bar_record(row):
    return {
        "datetime_start_ist": row["datetime_start_ist"],
        "open": _plain(row["open"]),
        "high": _plain(row["high"]),
        "low": _plain(row["low"]),
        "close": _plain(row["close"]),
        "volume": _plain(row["volume"]),
    }


def write_bars(path, rows):
    def write(tmp):
        with gzip.open(tmp, "wt", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=BAR_FIELDS, lineterminator="\n", extrasaction="ignore")
            writer.writeheader()
            for row in rows:
                writer.writerow(_bar_record(row))
    _atomic(path, write)


def bar_path(root, interval, symbol):
    if "/" in symbol or "\\" in symbol:
        raise KiteError("symbol is not a file name: %s" % symbol)
    return os.path.join(root, interval, symbol + ".csv.gz")


def part_path(root, interval, symbol):
    final = bar_path(root, interval, symbol)
    return final[:-len(".csv.gz")] + ".part.csv.gz"


def append_part(path, rows):
    """Append one chunk. Do not read the file."""
    if not rows:
        return
    folder = os.path.dirname(path)
    if folder and not os.path.isdir(folder):
        os.makedirs(folder)
    new_file = not os.path.isfile(path)
    with gzip.open(path, "at", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=BAR_FIELDS, lineterminator="\n", extrasaction="ignore")
        if new_file:
            writer.writeheader()
        for row in rows:
            writer.writerow(_bar_record(row))


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
    return covered_candles(progress, symbol, interval, start, end) is not None


def covered_candles(progress, symbol, interval, start, end):
    """Candle count when a finished chunk covers the window, else None."""
    start_s = start.isoformat()
    end_s = end.isoformat()
    found = None
    for row in progress.get("done") or []:
        if row.get("symbol") != symbol or row.get("interval") != interval:
            continue
        if row.get("start") <= start_s and row.get("end") >= end_s:
            candles = row.get("candles") or 0
            if found is None or candles > found:
                found = candles
    return found


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


def check_rows(symbol, interval, rows, gaps=None):
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
    for start, end in gaps or []:
        out.append({
            "symbol": symbol, "check": "gap",
            "date": "%s..%s" % (start.isoformat(), end.isoformat()),
            "bars": str((end - start).days + 1),
            "prev_close": "", "close": "", "change": "",
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


def finished_rows(rows, interval, to_date, now):
    """Drop sessions after `to_date`, and an unfinished session dated today.

    Returns (kept, partial). `partial` is true when today's session was still
    open, so the chunk that held it must not be marked done. `now` is naive IST.
    """
    if not rows:
        return [], False
    by_date = {}
    for row in rows:
        by_date.setdefault(row["start"].date(), []).append(row)
    last = max(by_date)
    drop = set()
    for day in by_date:
        if day > to_date:
            drop.add(day)
    partial = False
    today = now.date() if isinstance(now, datetime.datetime) else None
    clock = now.time() if isinstance(now, datetime.datetime) else SETTLED
    if today is not None and last == today and today in by_date:
        bars = by_date[today]
        if interval == "5minute" and len(bars) < SESSION_BARS_5M:
            drop.add(today)
            partial = True
        elif interval == "day" and clock < SETTLED:
            drop.add(today)
            partial = True
    if today is not None and today in drop and today == last:
        bars = by_date.get(today) or []
        if interval == "5minute" and len(bars) < SESSION_BARS_5M:
            partial = True
        elif interval == "day" and clock < SETTLED:
            partial = True
    kept = [row for row in rows if row["start"].date() not in drop]
    return kept, partial


def download_symbol(client, progress, root, symbol, token, interval, today, save, now=None):
    """Walk backward from `today` (`--to`). The windows it fetches are the download.

    Rows stay in memory and are written once, when the symbol is done. Each new
    chunk is also appended to the .part file without reading it. `save` runs
    after every 25 requests and at the end of the symbol. An open session is
    left out of the file and its chunk is not marked done. Returns (rows, gaps).
    """
    saved_at = [client.http]

    def persist(force=False):
        if force or client.http - saved_at[0] >= PROGRESS_EVERY:
            save()
            saved_at[0] = client.http

    part = part_path(root, interval, symbol)
    final = bar_path(root, interval, symbol)
    changed = os.path.isfile(part)
    index = {}
    if os.path.isfile(final):
        for row in read_bars(final):
            index[row["datetime_start_ist"]] = row
    if os.path.isfile(part):
        for row in read_bars(part):
            stamp = row["datetime_start_ist"]
            if stamp not in index:
                index[stamp] = row
    windows = []
    end = today
    empty_run = 0
    guard = 0
    while guard < 2000:
        guard += 1
        span = client.spans[interval]
        start = end - datetime.timedelta(days=span - 1)
        known = covered_candles(progress, symbol, interval, start, end)
        if known is not None:
            has = known > 0
            windows.append((start, end, has))
            if has:
                empty_run = 0
            else:
                empty_run += 1
                if empty_run >= EMPTY_STOP:
                    break
            end = start - datetime.timedelta(days=1)
            if end.year < 1990:
                break
            continue
        rows, actual_start, actual_end = client.window(token, interval, start, end, "end")
        kept, partial = finished_rows(rows, interval, today, now)
        if not partial:
            mark_chunk(progress, symbol, interval, actual_start, actual_end, len(kept))
        progress["spans"][interval] = client.spans[interval]
        fresh = []
        for row in kept:
            key = row["datetime_start_ist"]
            if key not in index:
                index[key] = row
                fresh.append(row)
        if fresh:
            append_part(part, fresh)
            changed = True
        windows.append((actual_start, actual_end, bool(kept)))
        persist(False)
        if kept:
            empty_run = 0
        elif not partial:
            empty_run += 1
            if empty_run >= EMPTY_STOP:
                break
        end = actual_start - datetime.timedelta(days=1)
        if end.year < 1990:
            break
    gaps = gap_windows(windows)
    rows_out = [index[stamp] for stamp in sorted(index)]
    filtered, _partial_file = finished_rows(rows_out, interval, today, now)
    if [row["datetime_start_ist"] for row in filtered] != [row["datetime_start_ist"] for row in rows_out]:
        changed = True
    rows_out = filtered
    key = depth_key(symbol, interval)
    if rows_out:
        earliest = min(row["start"].date() for row in rows_out)
        progress["depth"][key] = earliest.isoformat()
    elif changed or not os.path.isfile(final):
        progress["depth"][key] = ""
    persist(True)
    if changed and rows_out:
        write_bars(final, rows_out)
    elif changed and os.path.isfile(final):
        os.remove(final)
    if changed and os.path.isfile(part):
        os.remove(part)
    return rows_out, gaps


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
    history = 0
    assumed = 0
    horizon = assumed_earliest(interval, today)
    for name in names:
        known, probed = _saved_depth_any(progress, name, interval)
        if probed and known:
            history += count_walk(today, span, known)
        elif probed:
            continue
        else:
            assumed += 1
            history += count_walk(today, span, horizon)
    total = history + (1 if need_instruments else 0)
    lines = [
        "dry run: %d symbols, interval %s, span %d days, through %s" % (
            len(names), interval, span, today.isoformat()),
    ]
    if assumed:
        years = ASSUMED_YEARS.get(interval)
        note = " (%d years)" % years if years else ""
        lines.append("%d symbols have no saved depth; estimating from %s%s" % (
            assumed, horizon.isoformat(), note))
    lines.append("requests %d (%d instruments, %d history)" % (
        total, 1 if need_instruments else 0, history))
    lines.append("at %g requests/second, about %s" % (RATE, format_eta(total / RATE)))
    return lines


def apply_saved_spans(client, progress):
    for interval, span in (progress.get("spans") or {}).items():
        if interval in client.spans and span:
            client.spans[interval] = int(span)
            if int(span) < MAX_DAYS.get(interval, int(span)):
                client.announced.add(interval)


def run(names, interval, root, today, send, api_key, access_token, bucket, sleep, log,
        dry_run=False, to_date=None, now=None):
    if interval not in MAX_DAYS:
        raise KiteError("interval must be day, 5minute or minute, not %r" % (interval,))
    if not names:
        raise KiteError("no symbols. Pass --universe, --symbols-file, or --indices")
    end = to_date or today
    progress_path = os.path.join(root, "progress.json")
    progress = load_progress(progress_path)
    if dry_run:
        for line in dry_run_lines(names, interval, end, progress, root):
            log(line)
        return 0
    def save():
        save_progress(progress_path, progress)
    log("through %s" % end.isoformat())
    client = Client(send, api_key, access_token, bucket, sleep, log)
    apply_saved_spans(client, progress)
    # The estimate only feeds the "remaining" half of the progress line.
    client.planned = count_walk(
        end, client.spans[interval], assumed_earliest(interval, end)) * max(1, len(names))
    if not os.path.isfile(instruments_path(root, today)):
        client.planned += 1
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
        rows, gaps = download_symbol(
            client, progress, root, symbol, token, interval, end, save, now)
        records.extend(check_rows(symbol, interval, rows, gaps))
    report = os.path.join(root, "reports", "%s-checks.csv" % interval)
    write_checks(report, records)
    log("wrote %s" % report)
    return 0


def main(argv=None, send=None, today=None, bucket=None, sleep=None, log=None,
         cred_path=None, token_path=None, now=None):
    import argparse
    parser = argparse.ArgumentParser(description="Download Kite historical candles. Nothing is placed.")
    parser.add_argument("--universe", help="NSE constituents CSV with a Symbol column")
    parser.add_argument("--symbols-file", help="one symbol per line")
    parser.add_argument("--indices", default=",".join(DEFAULT_INDICES),
                        help="comma separated index names. Default is the four broad indices and the NIFTY sector indices.")
    parser.add_argument("--interval", required=True, choices=INTERVALS)
    parser.add_argument("--to", help="last session to keep, YYYY-MM-DD. Default is the last finished NSE session.")
    parser.add_argument("--data", default=DEFAULT_ROOT, help="output root (default data/kite)")
    parser.add_argument("--dry-run", action="store_true", help="print the request count and stop")
    args = parser.parse_args(argv)
    if now is None and today is not None:
        now = datetime.datetime.combine(today, SETTLED)
    clock = now_ist(now)
    day = clock.date()
    emit = log or (lambda line: print(line))
    try:
        to_date = parse_day(args.to) if args.to else default_to(clock)
        names = gather_names(args.universe, args.symbols_file, args.indices)
        if args.dry_run:
            return run(names, args.interval, args.data, day, send, "", "", None, None, emit,
                       dry_run=True, to_date=to_date, now=clock)
        api_key, _secret = kite_login.load_credentials(cred_path or kite_login.CRED_PATH)
        access_token = kite_login.load_token(token_path or kite_login.TOKEN_PATH, day)
        sender = send or kite_login.urlopen_send
        limiter = bucket or TokenBucket(RATE)
        pause = sleep or time.sleep
        return run(names, args.interval, args.data, day, sender, api_key, access_token,
                   limiter, pause, emit, dry_run=False, to_date=to_date, now=clock)
    except LoginExpired as exc:
        print("kite_history.py: %s" % exc, file=sys.stderr)
        return 1
    except (KiteError, kite_login.LoginError, OSError, urllib.error.URLError) as exc:
        print("kite_history.py: %s" % exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
