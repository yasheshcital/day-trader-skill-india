#!/usr/bin/env python3
"""Download Zerodha Kite F&O candles into data/kite.

    python3 india/kite_fno.py --dry-run
    python3 india/kite_fno.py
    python3 india/kite_fno.py --to 2026-11-06

Expired option contracts have no candle data. Expired futures have day candles
only, and only by passing continuous=1 on a live contract's token. The
instrument list itself only carries live contracts, so each day's NFO file is
kept: data/kite/instruments/NFO-<date>.csv.

Continuous futures (day, full depth) are written to
data/kite/futures/day/<UNDERLYING>.csv.gz for NIFTY, BANKNIFTY, FINNIFTY,
MIDCPNIFTY and every other underlying that has a future in the list. The
nearest live future is the token. Active NIFTY and BANKNIFTY options (current
and next weekly expiry, current and next monthly expiry, strikes within 10%
of the latest index close) are written, day and 5-minute, to
data/kite/options/<UNDERLYING>/<expiry>/<interval>/<tradingsymbol>.csv.gz.
Every file has an oi column.

Login, the token bucket, retries, the backward walk, part files and --to come
from kite_history.py. Resume state is data/kite/fno-progress.json so the equity
progress file is left alone. One Kite process at a time: this refuses to start
when data/kite/progress.lock exists, creates that file on start, and removes
it on the way out. --dry-run prints the request count at 3 requests/second
and does not call the API.

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

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from india import kite_history as kh
from india import kite_login

NFO_URL = kh.API + "/instruments/NFO"
INDEX_FUTURES = ("NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY")
OPTION_UNDERLYINGS = ("NIFTY", "BANKNIFTY")
# Cash index files already downloaded by kite_history.py. The close on or
# before --to is the centre of the strike band.
INDEX_BARS = {"NIFTY": "NIFTY 50", "BANKNIFTY": "NIFTY BANK"}
# Stable index tokens, used only when no NSE instrument file is on disk.
INDEX_TOKENS = {"NIFTY 50": "256265", "NIFTY BANK": "260105"}
STRIKE_BAND = 0.10
# A weekly or monthly option is listed for a few weeks to a few months.
ASSUMED_OPTION_DAYS = 90
# NSE lists about 200 stock futures. Used only when today's NFO file is absent,
# so a dry run before the first download still has a time.
ASSUMED_STOCKS = 200
ASSUMED_SPOT = {"NIFTY": 24000.0, "BANKNIFTY": 56000.0}
ASSUMED_STEP = {"NIFTY": 50.0, "BANKNIFTY": 100.0}
# NIFTY has weeklies and monthlies (current and next of each). BANKNIFTY is
# monthly after the single-weekly rule, so the estimate uses two expiries.
ASSUMED_EXPIRIES = {"NIFTY": 4, "BANKNIFTY": 2}
BAR_FIELDS = ["datetime_start_ist", "open", "high", "low", "close", "volume", "oi"]
OPTION_INTERVALS = ("5minute", "day")
DEFAULT_ROOT = os.path.join("data", "kite")
LOCK_NAME = "progress.lock"
PROGRESS_NAME = "fno-progress.json"


class LockBusy(kh.KiteError):
    pass


def history_url(token, interval, start, end, continuous=False, oi=True):
    """Same window as kite_history, plus the F&O flags."""
    url = kh.history_url(token, interval, start, end)
    extra = []
    if continuous:
        extra.append(("continuous", "1"))
    if oi:
        extra.append(("oi", "1"))
    if not extra:
        return url
    return url + "&" + urllib.parse.urlencode(extra)


def parse_stamp(text):
    """Kite stamp, or a bare YYYY-MM-DD day candle, as naive IST."""
    raw = str(text or "").strip()
    if len(raw) == 10:
        raw = raw + "T00:00:00+0530"
    return kh.parse_kite_stamp(raw)


def candle_rows(raw):
    """Historical JSON, keeping open interest. Missing oi is 0."""
    try:
        data = json_loads(raw)
    except ValueError:
        raise kh.KiteError("Kite returned something that is not JSON")
    if not isinstance(data, dict) or data.get("status") != "success":
        message = ""
        if isinstance(data, dict):
            message = str(data.get("message") or "")
        raise kh.KiteError(message or "Kite historical request failed")
    candles = ((data.get("data") or {}).get("candles")) or []
    rows = []
    for item in candles:
        if not item or len(item) < 6:
            continue
        stamp = parse_stamp(item[0])
        oi = 0
        if len(item) >= 7 and item[6] is not None and item[6] != "":
            oi = item[6]
        rows.append({
            "datetime_start_ist": stamp.strftime("%Y-%m-%d %H:%M:%S"),
            "start": stamp,
            "open": item[1],
            "high": item[2],
            "low": item[3],
            "close": item[4],
            "volume": item[5],
            "oi": oi,
        })
    return rows


def json_loads(raw):
    return json.loads(raw.decode("utf-8"))


def _parse_expiry(text):
    raw = (text or "").strip()
    if len(raw) < 10:
        return None
    try:
        day = datetime.date.fromisoformat(raw[:10])
    except ValueError:
        return None
    if day.isoformat() != raw[:10]:
        return None
    return day


def _parse_strike(text):
    raw = (text or "").strip()
    if not raw:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def parse_nfo(text):
    """NFO instrument rows. Equity columns are ignored; expiry and strike are kept."""
    rows = []
    reader = csv.DictReader(text.splitlines())
    for row in reader:
        symbol = (row.get("tradingsymbol") or "").strip()
        token = (row.get("instrument_token") or "").strip()
        kind = (row.get("instrument_type") or "").strip().upper()
        if not symbol or not token or kind not in ("FUT", "CE", "PE"):
            continue
        rows.append({
            "instrument_token": token,
            "tradingsymbol": symbol,
            "name": (row.get("name") or "").strip().upper(),
            "expiry": _parse_expiry(row.get("expiry")),
            "strike": _parse_strike(row.get("strike")),
            "instrument_type": kind,
        })
    return rows


def nfo_path(root, day):
    return os.path.join(root, "instruments", "NFO-%s.csv" % day.isoformat())


def lock_path(root):
    return os.path.join(root, LOCK_NAME)


def progress_path(root):
    return os.path.join(root, PROGRESS_NAME)


def acquire_lock(path):
    """Create the lock exclusively. Refuse when another download already did."""
    folder = os.path.dirname(path)
    if folder:
        os.makedirs(folder, exist_ok=True)
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
    except FileExistsError:
        raise LockBusy(
            "another Kite download is running (%s). Remove it if no download is running." % path)
    try:
        os.write(fd, ("%s\n" % os.getpid()).encode("ascii"))
    finally:
        os.close(fd)


def release_lock(path):
    try:
        os.remove(path)
    except OSError:
        pass


def save_text(path, text):
    def write(tmp):
        with open(tmp, "w", encoding="utf-8", newline="") as fh:
            fh.write(text if text.endswith("\n") else text + "\n")
    kh._atomic(path, write)


def load_saved_nfo(root, day):
    path = nfo_path(root, day)
    if not os.path.isfile(path) or os.path.getsize(path) == 0:
        return None
    with open(path, encoding="utf-8-sig") as fh:
        return parse_nfo(fh.read())


def futures_by_name(rows):
    found = {}
    for row in rows:
        if row["instrument_type"] != "FUT" or not row["name"] or not row["expiry"]:
            continue
        found.setdefault(row["name"], []).append(row)
    return found


def futures_underlyings(rows):
    """The four index futures first, then every other underlying, A to Z."""
    names = futures_by_name(rows)
    ordered = [name for name in INDEX_FUTURES if name in names]
    rest = sorted(name for name in names if name not in ordered)
    return ordered + rest


def nearest_future(rows, name, asof):
    """The soonest live future. The list has no expired contracts."""
    live = []
    for row in rows:
        if row["instrument_type"] != "FUT" or row["name"] != name or not row["expiry"]:
            continue
        if row["expiry"] < asof:
            continue
        live.append(row)
    if not live:
        return None
    live.sort(key=lambda row: (row["expiry"], row["tradingsymbol"]))
    return live[0]


def expiry_groups(dates):
    """(weekly, monthly). The monthly expiry is the last one in that month.

    A month with a single expiry is monthly. The same date is never both.
    """
    monthly = {}
    for day in dates:
        key = (day.year, day.month)
        if key not in monthly or day > monthly[key]:
            monthly[key] = day
    month_set = set(monthly.values())
    weekly = sorted(day for day in set(dates) if day not in month_set)
    return weekly, sorted(month_set)


def _current_and_next(dates, asof):
    live = [day for day in dates if day >= asof]
    return live[:2]


def active_expiries(dates, asof):
    """Current and next weekly, plus current and next monthly, from `asof`."""
    weekly, monthly = expiry_groups(dates)
    chosen = []
    seen = set()
    for bucket in (weekly, monthly):
        for day in _current_and_next(bucket, asof):
            if day not in seen:
                seen.add(day)
                chosen.append(day)
    return sorted(chosen)


def in_band(strike, close, band=STRIKE_BAND):
    """True when strike is within `band` of close, bounds included."""
    if strike is None or close is None or close <= 0:
        return False
    move = (float(strike) - float(close)) / float(close)
    return move >= -band and move <= band


def option_expiries(rows, underlying):
    found = []
    seen = set()
    for row in rows:
        if row["name"] != underlying or row["instrument_type"] not in ("CE", "PE"):
            continue
        if not row["expiry"] or row["expiry"] in seen:
            continue
        seen.add(row["expiry"])
        found.append(row["expiry"])
    return found


def select_options(rows, underlying, expiries, close, band=STRIKE_BAND):
    """CE and PE at the chosen expiries whose strike is inside the band."""
    want = set(expiries)
    picked = []
    for row in rows:
        if row["name"] != underlying or row["instrument_type"] not in ("CE", "PE"):
            continue
        if row["expiry"] not in want or not in_band(row["strike"], close, band):
            continue
        picked.append(row)
    picked.sort(key=lambda row: (row["expiry"], row["strike"], row["instrument_type"], row["tradingsymbol"]))
    return picked


def assumed_strike_count(name):
    spot = ASSUMED_SPOT[name]
    step = ASSUMED_STEP[name]
    width = spot * (2.0 * STRIKE_BAND)
    return int(round(width / step)) + 1


def assumed_option_count(name):
    return assumed_strike_count(name) * 2 * ASSUMED_EXPIRIES[name]


def _record(row):
    item = kh._bar_record(row)
    item["oi"] = kh._plain(row.get("oi") or 0)
    return item


def write_bars(path, rows):
    def write(tmp):
        with gzip.open(tmp, "wt", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=BAR_FIELDS, lineterminator="\n", extrasaction="ignore")
            writer.writeheader()
            for row in rows:
                writer.writerow(_record(row))
    kh._atomic(path, write)


def read_bars(path):
    """One csv.gz, oi included. Oldest first."""
    rows = []
    with gzip.open(path, "rt", encoding="utf-8-sig", newline="") as fh:
        for row in csv.DictReader(fh):
            stamp = parse_stamp(row["datetime_start_ist"])
            rows.append({
                "datetime_start_ist": stamp.strftime("%Y-%m-%d %H:%M:%S"),
                "start": stamp,
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"]),
                "volume": float(row["volume"] or 0),
                "oi": float(row.get("oi") or 0),
            })
    rows.sort(key=lambda row: row["datetime_start_ist"])
    return rows


def part_for(path):
    if not path.endswith(".csv.gz"):
        raise kh.KiteError("not a candle path: %s" % path)
    return path[:-len(".csv.gz")] + ".part.csv.gz"


def _safe(text):
    if not text or text in (".", "..") or "/" in text or "\\" in text:
        raise kh.KiteError("not a file name: %s" % text)
    return text


def futures_file(root, underlying):
    return os.path.join(root, "futures", "day", _safe(underlying) + ".csv.gz")


def option_file(root, underlying, expiry, interval, tradingsymbol):
    day = expiry.isoformat() if isinstance(expiry, datetime.date) else str(expiry)
    return os.path.join(
        root, "options", _safe(underlying), day, interval, _safe(tradingsymbol) + ".csv.gz")


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
            writer.writerow(_record(row))


def latest_close(rows, to_date):
    """(date, close) of the last bar on or before to_date."""
    best = None
    for row in rows:
        day = row["start"].date()
        if day > to_date:
            continue
        if best is None or day > best[0]:
            best = (day, float(row["close"]))
    return best


def local_index_close(root, symbol, to_date):
    path = kh.bar_path(root, "day", symbol)
    if not os.path.isfile(path):
        return None
    return latest_close(kh.read_bars(path), to_date)


def index_token(root, symbol):
    """Token from the newest NSE instrument file on disk, else the stable index token."""
    folder = os.path.join(root, "instruments")
    names = []
    if os.path.isdir(folder):
        names = sorted(name for name in os.listdir(folder) if name.startswith("NSE-") and name.endswith(".csv"))
    for name in reversed(names):
        with open(os.path.join(folder, name), encoding="utf-8-sig") as fh:
            found = kh.lookup_instrument(symbol, kh.parse_instruments(fh.read()))
        if found:
            return found[0]
    return INDEX_TOKENS.get(symbol)


class Client(kh.Client):
    """kite_history.Client, with continuous and oi on the historical URL."""

    def __init__(self, send, api_key, access_token, bucket, sleep, log):
        kh.Client.__init__(self, send, api_key, access_token, bucket, sleep, log)
        self.continuous = False
        self.oi = True

    def fetch_exact(self, token, interval, start, end):
        url = history_url(token, interval, start, end, continuous=self.continuous, oi=self.oi)
        status, body = self.call("GET", url)
        message = kh._body_message(body)
        if kh.span_rejected(status, message):
            width = (end - start).days + 1
            self.spans[interval] = max(1, width // 2)
            raise kh.SpanRejected(message or "interval exceeds max limit")
        if status != 200:
            raise kh.KiteError(message or "Kite historical request failed (%s)" % status)
        return candle_rows(body)

    def instruments_nfo(self):
        status, body = self.call("GET", NFO_URL)
        if status != 200:
            raise kh.KiteError("NFO instruments request failed (%s)" % status)
        if body and body[:2] == b"\x1f\x8b":
            body = gzip.decompress(body)
        return body.decode("utf-8")


def download_series(client, progress, path, symbol, token, interval, today, save, now=None):
    """Walk backward from `today`. Same stop, resume and part-file rules as kite_history.

    Rows are written once, when the series is done. Each new chunk is appended
    to the .part file without reading it. Returns the merged rows.
    """
    saved_at = [client.http]

    def persist(force=False):
        if force or client.http - saved_at[0] >= kh.PROGRESS_EVERY:
            save()
            saved_at[0] = client.http

    part = part_for(path)
    changed = os.path.isfile(part)
    index = {}
    if os.path.isfile(path):
        for row in read_bars(path):
            index[row["datetime_start_ist"]] = row
    if os.path.isfile(part):
        for row in read_bars(part):
            stamp = row["datetime_start_ist"]
            if stamp not in index:
                index[stamp] = row
    end = today
    empty_run = 0
    guard = 0
    while guard < 2000:
        guard += 1
        span = client.spans[interval]
        start = end - datetime.timedelta(days=span - 1)
        known = kh.covered_candles(progress, symbol, interval, start, end)
        if known is not None:
            has = known > 0
            if has:
                empty_run = 0
            else:
                empty_run += 1
                if empty_run >= kh.EMPTY_STOP:
                    break
            end = start - datetime.timedelta(days=1)
            if end.year < 1990:
                break
            continue
        rows, actual_start, actual_end = client.window(token, interval, start, end, "end")
        kept, partial = kh.finished_rows(rows, interval, today, now)
        if not partial:
            kh.mark_chunk(progress, symbol, interval, actual_start, actual_end, len(kept))
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
        persist(False)
        if kept:
            empty_run = 0
        elif not partial:
            empty_run += 1
            if empty_run >= kh.EMPTY_STOP:
                break
        end = actual_start - datetime.timedelta(days=1)
        if end.year < 1990:
            break
    rows_out = [index[stamp] for stamp in sorted(index)]
    filtered, _partial_file = kh.finished_rows(rows_out, interval, today, now)
    if [row["datetime_start_ist"] for row in filtered] != [row["datetime_start_ist"] for row in rows_out]:
        changed = True
    rows_out = filtered
    key = kh.depth_key(symbol, interval)
    if rows_out:
        earliest = min(row["start"].date() for row in rows_out)
        progress["depth"][key] = earliest.isoformat()
    elif changed or not os.path.isfile(path):
        progress["depth"][key] = ""
    persist(True)
    if changed and rows_out:
        write_bars(path, rows_out)
    elif changed and os.path.isfile(path):
        os.remove(path)
    if changed and os.path.isfile(part):
        os.remove(part)
    return rows_out


def _walk_requests(symbol, interval, to_date, span, horizon, progress):
    known, probed = kh._saved_depth(progress, symbol, interval)
    if probed and known:
        return kh.count_walk(to_date, span, known)
    if probed:
        return 0
    return kh.count_walk(to_date, span, horizon)


def _spans(progress):
    saved = progress.get("spans") or {}
    day = int(saved.get("day") or kh.MAX_DAYS["day"])
    minute = int(saved.get("5minute") or kh.MAX_DAYS["5minute"])
    return day, minute


def build_plan(rows, closes, to_date, progress, asof, need_instruments, close_fetches):
    """Request counts. `rows` is None when the NFO list is not on disk yet.

    `closes` maps an option underlying to (date, close) or None. A missing
    close falls back to the assumed contract count for that underlying.
    """
    span_day, span_5 = _spans(progress)
    fut_horizon = kh.assumed_earliest("day", to_date)
    opt_horizon = to_date - datetime.timedelta(days=ASSUMED_OPTION_DAYS)
    per_option = (
        kh.count_walk(to_date, span_5, opt_horizon) + kh.count_walk(to_date, span_day, opt_horizon))
    notes = []
    assumed = rows is None
    futures = []
    if rows is None:
        future_requests = kh.count_walk(to_date, span_day, fut_horizon) * (len(INDEX_FUTURES) + ASSUMED_STOCKS)
        notes.append(
            "NFO instrument list is not on disk; assuming %d futures (%s and %d stocks), depth from %s (20 years)" % (
                len(INDEX_FUTURES) + ASSUMED_STOCKS,
                ", ".join(INDEX_FUTURES),
                ASSUMED_STOCKS,
                fut_horizon.isoformat()))
    else:
        future_requests = 0
        for name in futures_underlyings(rows):
            fut = nearest_future(rows, name, asof)
            if not fut:
                continue
            futures.append(fut)
            future_requests += _walk_requests(name, "day", to_date, span_day, fut_horizon, progress)
    option_requests = 0
    contracts = []
    option_count = 0
    if rows is None:
        for name in OPTION_UNDERLYINGS:
            count = assumed_option_count(name)
            option_count += count
            option_requests += count * per_option
            notes.append(
                "assuming %d %s option contracts (%d expiries, %d strikes, both sides, spot %g, step %g), from a %d-day listing" % (
                    count, name, ASSUMED_EXPIRIES[name], assumed_strike_count(name),
                    ASSUMED_SPOT[name], ASSUMED_STEP[name], ASSUMED_OPTION_DAYS))
    else:
        for name in OPTION_UNDERLYINGS:
            got = closes.get(name)
            if not got:
                count = assumed_option_count(name)
                option_count += count
                option_requests += count * per_option
                assumed = True
                notes.append("no %s close on disk; assuming %d %s option contracts" % (name, count, name))
                continue
            chosen = active_expiries(option_expiries(rows, name), asof)
            picked = select_options(rows, name, chosen, got[1])
            contracts.extend(picked)
            option_count += len(picked)
            for row in picked:
                for interval, span in (("5minute", span_5), ("day", span_day)):
                    option_requests += _walk_requests(
                        row["tradingsymbol"], interval, to_date, span, opt_horizon, progress)
            if got[0] < to_date:
                notes.append(
                    "%s close %s is from %s, before %s; the run fetches a fresh close before it picks strikes" % (
                        name, kh._plain(got[1]), got[0].isoformat(), to_date.isoformat()))
    total = future_requests + option_requests + (1 if need_instruments else 0) + close_fetches
    return {
        "futures": futures,
        "future_requests": future_requests,
        "contracts": contracts,
        "option_count": option_count,
        "option_requests": option_requests,
        "instruments": 1 if need_instruments else 0,
        "closes": close_fetches,
        "total": total,
        "assumed": assumed,
        "notes": notes,
        "span_day": span_day,
        "span_5": span_5,
    }


def plan_lines(plan, to_date, label):
    lines = ["%s: through %s" % (label, to_date.isoformat())]
    lines.extend(plan["notes"])
    lines.append(
        "requests %d (%d instruments, %d index closes, %d futures, %d options across %d contracts)" % (
            plan["total"], plan["instruments"], plan["closes"],
            plan["future_requests"], plan["option_requests"], plan["option_count"]))
    lines.append("at %g requests/second, about %s" % (kh.RATE, kh.format_eta(plan["total"] / kh.RATE)))
    return lines


def _local_closes(root, to_date):
    found = {}
    fetches = 0
    for name, symbol in INDEX_BARS.items():
        got = local_index_close(root, symbol, to_date)
        found[name] = got
        if got is None or got[0] < to_date:
            fetches += 1
    return found, fetches


def fetch_index_close(client, token, to_date):
    """One short day window. Returns (date, close) or None."""
    start = to_date - datetime.timedelta(days=10)
    rows = client.fetch_exact(token, "day", start, to_date)
    now = datetime.datetime.combine(to_date, kh.SETTLED)
    kept, _partial = kh.finished_rows(rows, "day", to_date, now)
    return latest_close(kept, to_date)


def _fetch_named(client, progress, path, symbol, token, interval, today, save, now, label):
    """download_series, with the series name on a Kite error so a stop is obvious."""
    try:
        return download_series(client, progress, path, symbol, token, interval, today, save, now)
    except kh.LoginExpired:
        raise
    except kh.KiteError as exc:
        raise kh.KiteError("%s: %s" % (label, exc))


def _first_date(rows):
    if not rows:
        return None
    return min(row["start"].date() for row in rows)


def run(root, day, to_date, send, api_key, access_token, bucket, sleep, log,
        dry_run=False, now=None):
    path = progress_path(root)
    progress = kh.load_progress(path)
    need_instruments = load_saved_nfo(root, day) is None
    closes, close_fetches = _local_closes(root, to_date)
    rows = None if need_instruments else load_saved_nfo(root, day)
    # A stale local close still centres the dry-run band. The fetch is counted.
    plan = build_plan(rows, closes, to_date, progress, day, need_instruments, close_fetches)
    if dry_run:
        for line in plan_lines(plan, to_date, "dry run"):
            log(line)
        return 0

    def save():
        kh.save_progress(path, progress)

    client = Client(send, api_key, access_token, bucket, sleep, log)
    kh.apply_saved_spans(client, progress)
    client.planned = plan["total"]
    if need_instruments:
        text = client.instruments_nfo()
        save_text(nfo_path(root, day), text)
        rows = parse_nfo(text)
        log("saved %s" % nfo_path(root, day))
    client.continuous = False
    client.oi = False
    for name, symbol in INDEX_BARS.items():
        got = closes.get(name)
        if got is not None and got[0] >= to_date:
            log("%s close %s on %s" % (name, kh._plain(got[1]), got[0].isoformat()))
            continue
        token = index_token(root, symbol)
        if not token:
            log("no instrument for %s; options skipped" % symbol)
            closes[name] = None
            continue
        fresh = fetch_index_close(client, token, to_date)
        if fresh is None and got is not None:
            fresh = got
            log("%s close stayed %s on %s" % (name, kh._plain(got[1]), got[0].isoformat()))
        elif fresh is not None:
            log("%s close %s on %s" % (name, kh._plain(fresh[1]), fresh[0].isoformat()))
        else:
            log("no close for %s; options skipped" % name)
        closes[name] = fresh
    plan = build_plan(rows, closes, to_date, progress, day, False, 0)
    client.planned = client.http + plan["future_requests"] + plan["option_requests"]
    for line in plan_lines(plan, to_date, "plan"):
        log(line)
    client.continuous = True
    client.oi = True
    for fut in plan["futures"]:
        name = fut["name"]
        series = _fetch_named(
            client, progress, futures_file(root, name), name, fut["instrument_token"],
            "day", to_date, save, now, "%s future" % name)
        first = _first_date(series)
        log("%s first %s" % (name, first.isoformat() if first else "none"))
    client.continuous = False
    client.oi = True
    stats = {}
    for contract in plan["contracts"]:
        expiry = contract["expiry"]
        key = (contract["name"], expiry.isoformat())
        slot = stats.setdefault(key, {"contracts": 0, "bars": 0, "earliest": None})
        slot["contracts"] += 1
        for interval in OPTION_INTERVALS:
            series = _fetch_named(
                client, progress,
                option_file(root, contract["name"], expiry, interval, contract["tradingsymbol"]),
                contract["tradingsymbol"], contract["instrument_token"],
                interval, to_date, save, now,
                "%s %s" % (contract["tradingsymbol"], interval))
            slot["bars"] += len(series)
            first = _first_date(series)
            if first is not None and (slot["earliest"] is None or first < slot["earliest"]):
                slot["earliest"] = first
    if not stats:
        log("options: no contracts in the strike band")
    for key in sorted(stats):
        slot = stats[key]
        earliest = slot["earliest"].isoformat() if slot["earliest"] else "none"
        log("%s %s: %d contracts, %d bars, earliest %s" % (
            key[0], key[1], slot["contracts"], slot["bars"], earliest))
    return 0


def main(argv=None, send=None, today=None, bucket=None, sleep=None, log=None,
         cred_path=None, token_path=None, now=None):
    import argparse
    parser = argparse.ArgumentParser(description="Download Kite F&O candles. Nothing is placed.")
    parser.add_argument("--to", help="last session to keep, YYYY-MM-DD. Default is the last finished NSE session.")
    parser.add_argument("--data", default=DEFAULT_ROOT, help="output root (default data/kite)")
    parser.add_argument("--dry-run", action="store_true", help="print the request count and stop")
    args = parser.parse_args(argv)
    if now is None and today is not None:
        now = datetime.datetime.combine(today, kh.SETTLED)
    clock = kh.now_ist(now)
    day = clock.date()
    emit = log or (lambda line: print(line, flush=True))
    lock = lock_path(args.data)
    try:
        acquire_lock(lock)
    except LockBusy as exc:
        print("kite_fno.py: %s" % exc, file=sys.stderr)
        return 1
    try:
        try:
            to_date = kh.parse_day(args.to) if args.to else kh.default_to(clock)
            if args.dry_run:
                return run(args.data, day, to_date, send, "", "", None, None, emit,
                           dry_run=True, now=clock)
            api_key, _secret = kite_login.load_credentials(cred_path or kite_login.CRED_PATH)
            access_token = kite_login.load_token(token_path or kite_login.TOKEN_PATH, day)
            sender = send or kite_login.urlopen_send
            limiter = bucket or kh.TokenBucket(kh.RATE)
            pause = sleep or time.sleep
            return run(args.data, day, to_date, sender, api_key, access_token,
                       limiter, pause, emit, dry_run=False, now=clock)
        except kh.LoginExpired as exc:
            print("kite_fno.py: %s" % exc, file=sys.stderr)
            return 1
        except (kh.KiteError, kite_login.LoginError, OSError, urllib.error.URLError) as exc:
            print("kite_fno.py: %s" % exc, file=sys.stderr)
            return 1
    finally:
        release_lock(lock)


if __name__ == "__main__":
    sys.exit(main())
