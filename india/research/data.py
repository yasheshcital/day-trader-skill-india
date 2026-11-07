#!/usr/bin/env python3
"""The only way research code reads data/kite.

One symbol at a time, streamed from its .csv.gz. Prices are already split and
bonus adjusted, so nothing here rescales them.

Daily bars stay daily. Five-minute bars become sessions whose timestamps are
the bar end, the same five-minute shift as india/backtest.py kite_end_label.

HOLDOUT_START is 2025-01-01. A load whose result contains a bar on or after
that date raises HoldoutError, unless final=True. final=True prints a notice.
The first final=True load in a process appends one line, the date and the
script and the arguments, to HOLDOUT_LOG.md. Later symbols in that run do not
add another line.

Two exclusions apply by default. The first 20 trading sessions, counting the
symbol's first date as session 1, are the listing window and are dropped.
A daily move above +100% or below -60% is a break. The series is split there:
a holding return that would cross the break is refused.
"""

import array
import csv
import datetime
import gzip
import os
import pickle
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from india import kite_history
from india import nse_market

HOLDOUT_START = datetime.date(2025, 1, 1)
LISTING_SESSIONS = 20
# A move must be past these. Exactly +100% or exactly -60% is not a break.
BREAK_UP = 1.0
BREAK_DOWN = -0.60
BAR_MINUTES = 5
# A session is usable for an intraday test when every 5-minute bar from
# 09:15 through 15:10 is present. The flat is 15:10, so the later bars are
# not required. NSE's official close is a 30-minute weighted average, which
# is why the last 5-minute trade and the daily close often differ.
USABLE_FIRST = 9 * 60 + 15
USABLE_LAST = 15 * 60 + 10
USABLE_COUNT = (USABLE_LAST - USABLE_FIRST) // BAR_MINUTES + 1
USABLE_MASK = (1 << USABLE_COUNT) - 1
_HERE = os.path.dirname(os.path.abspath(__file__))
HOLDOUT_LOG = os.path.join(_HERE, "HOLDOUT_LOG.md")
CACHE_VERSION = 1
# Paths already given one holdout line in this process.
_HOLD_LOGGED_PATHS = set()


class DataError(Exception):
    pass


class HoldoutError(DataError):
    pass


class BreakError(DataError):
    pass


class Series(object):
    """Kept sessions, already split at breaks. `excluded` says what was dropped."""

    def __init__(self, symbol, interval, segments, excluded):
        self.symbol = symbol
        self.interval = interval
        self.segments = segments
        self.excluded = excluded

    def dates(self):
        found = []
        for segment in self.segments:
            for item in segment:
                found.append(item["date"])
        return found


def bar_path(root, interval, symbol):
    return os.path.join(root, interval, symbol + ".csv.gz")


def cache_root_for(root):
    """data/kite -> data/cache. A temp kite folder gets a sibling cache folder."""
    return os.path.join(os.path.dirname(os.path.abspath(root)), "cache")


def cache_file(root, interval, symbol, cache_root=None):
    base = cache_root or cache_root_for(root)
    folder = "5m" if interval == "5minute" else interval
    return os.path.join(base, folder, symbol + ".pkl")


def start_bit(minute):
    """Bit index of a bar start inside 09:15..15:10, or None when it is outside."""
    if minute < USABLE_FIRST or minute > USABLE_LAST:
        return None
    offset = minute - USABLE_FIRST
    if offset % BAR_MINUTES:
        return None
    return offset // BAR_MINUTES


def mask_from_starts(minutes):
    mask = 0
    for minute in minutes:
        bit = start_bit(minute)
        if bit is not None:
            mask |= 1 << bit
    return mask


def session_usable(mask):
    """True when every bar from 09:15 to 15:10 is present. Extra bars do not hurt."""
    return mask == USABLE_MASK


def stream_bars(path):
    """Yield one bar from one .csv.gz. The caller never opens the file itself."""
    with gzip.open(path, "rt", encoding="utf-8-sig", newline="") as fh:
        for row in csv.DictReader(fh):
            stamp = kite_history.parse_kite_stamp(row["datetime_start_ist"])
            yield {
                "start": stamp,
                "date": stamp.date(),
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"]),
                "volume": float(row["volume"] or 0),
            }


def _as_date(value):
    if isinstance(value, datetime.datetime):
        return value.date()
    if isinstance(value, datetime.date):
        return value
    return datetime.date.fromisoformat(value)


def _change(prev_close, close):
    if prev_close is None or prev_close == 0:
        return None
    return (close - prev_close) / prev_close


def is_break(change):
    """Above +100% or below -60%. The exact bounds are not breaks."""
    if change is None:
        return False
    return change > BREAK_UP or change < BREAK_DOWN


def find_breaks(points):
    """points is (date, close) in date order. The break is dated on the second day."""
    found = []
    prev_close = None
    prev_date = None
    for day, close in points:
        change = _change(prev_close, close)
        if is_break(change):
            found.append({
                "date": day,
                "prev_date": prev_date,
                "prev_close": prev_close,
                "close": close,
                "change": change,
            })
        prev_close = close
        prev_date = day
    return found


def _segment(items):
    """Split kept items where the close-to-close move between neighbours is a break."""
    segments = []
    current = []
    prev_close = None
    for item in items:
        change = _change(prev_close, item["close"])
        if current and is_break(change):
            segments.append(current)
            current = []
        current.append(item)
        prev_close = item["close"]
    if current:
        segments.append(current)
    return segments


def _guard(symbol, dates, final, log_path):
    """Raise when a returned bar lands on or after the holdout. final=True logs it."""
    hit = None
    for day in dates:
        if day >= HOLDOUT_START:
            hit = day
            break
    if hit is None:
        return
    if not final:
        raise HoldoutError(
            "%s returns a bar on %s, which is on or after %s. Pass final=True to include the holdout."
            % (symbol, hit.isoformat(), HOLDOUT_START.isoformat()))
    print("HOLDOUT: %s includes bars on and after %s" % (symbol, HOLDOUT_START.isoformat()))
    _append_holdout_log(log_path or HOLDOUT_LOG)


def _append_holdout_log(path):
    """One line per process for this path. The first final=True load writes it."""
    if path in _HOLD_LOGGED_PATHS:
        return
    _HOLD_LOGGED_PATHS.add(path)
    folder = os.path.dirname(path)
    if folder and not os.path.isdir(folder):
        os.makedirs(folder)
    now = nse_market.to_ist(datetime.datetime.utcnow())
    script = sys.argv[0] if sys.argv else ""
    arguments = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else ""
    new_file = not os.path.isfile(path)
    with open(path, "a", encoding="utf-8") as fh:
        if new_file:
            fh.write("# Holdout log\n\n")
            fh.write("date\tscript\targuments\n")
        fh.write("%s\t%s\t%s\n" % (now.strftime("%Y-%m-%d %H:%M:%S"), script, arguments))


def _clip(segments, start, end):
    """Keep a single inclusive window. Trimming the ends does not join segments."""
    if start is None and end is None:
        return segments
    out = []
    for segment in segments:
        kept = []
        for item in segment:
            if start is not None and item["date"] < start:
                continue
            if end is not None and item["date"] > end:
                continue
            kept.append(item)
        if kept:
            out.append(kept)
    return out


def _prepare(symbol, items, final, log_path, start=None, end=None):
    """Drop the listing window, record breaks, split the rest, then apply the holdout.

    start and end are inclusive. They are applied after the listing cut, so a
    request for 2015-2024 does not drop the first 20 days of 2015, and it does
    not return a bar on or after the holdout.
    """
    ordered = sorted(items, key=lambda item: item["date"])
    points = [(item["date"], item["close"]) for item in ordered]
    listing = [item["date"] for item in ordered[:LISTING_SESSIONS]]
    kept = ordered[LISTING_SESSIONS:]
    excluded = {"listing": listing, "breaks": find_breaks(points)}
    segments = _clip(_segment(kept), start, end)
    dates = []
    for segment in segments:
        for item in segment:
            dates.append(item["date"])
    _guard(symbol, dates, final, log_path)
    return segments, excluded


def _choose(root, interval, symbol, cache_root=None):
    """('cache', path) when the pickle is newer than the .csv.gz, else the csv."""
    csv_path = bar_path(root, interval, symbol)
    cached = cache_file(root, interval, symbol, cache_root)
    csv_exists = os.path.isfile(csv_path)
    cache_exists = os.path.isfile(cached)
    if cache_exists and csv_exists and os.path.getmtime(cached) > os.path.getmtime(csv_path):
        return "cache", cached
    if csv_exists:
        return "csv", csv_path
    raise DataError("no %s file for %s" % (interval, symbol))


def _sessions_from_bars(bars, interval):
    """One read's bars, grouped into sessions of array columns."""
    grouped = {}
    order = []
    for bar in bars:
        day = bar["date"]
        if day not in grouped:
            grouped[day] = {"end": [], "open": [], "high": [], "low": [], "close": [], "volume": []}
            order.append(day)
        bucket = grouped[day]
        if interval == "5minute":
            end = bar["start"] + datetime.timedelta(minutes=BAR_MINUTES)
            bucket["end"].append(end.hour * 60 + end.minute)
        else:
            bucket["end"].append(bar["start"].hour * 60 + bar["start"].minute)
        bucket["open"].append(bar["open"])
        bucket["high"].append(bar["high"])
        bucket["low"].append(bar["low"])
        bucket["close"].append(bar["close"])
        bucket["volume"].append(bar["volume"])
    sessions = []
    for day in order:
        bucket = grouped[day]
        order_i = sorted(range(len(bucket["end"])), key=lambda i: bucket["end"][i])
        sessions.append(_freeze_session(day, bucket, order_i))
    return sessions


def _freeze_session(day, bucket, order_i):
    return {
        "date": day.toordinal() if isinstance(day, datetime.date) else day,
        "end": array.array("H", (bucket["end"][i] for i in order_i)),
        "open": array.array("d", (bucket["open"][i] for i in order_i)),
        "high": array.array("d", (bucket["high"][i] for i in order_i)),
        "low": array.array("d", (bucket["low"][i] for i in order_i)),
        "close": array.array("d", (bucket["close"][i] for i in order_i)),
        "volume": array.array("d", (bucket["volume"][i] for i in order_i)),
    }


def pack_bars(bars, interval):
    """The pickle payload for one symbol. `bars` is the stream of one file."""
    return {"version": CACHE_VERSION, "interval": interval, "sessions": _sessions_from_bars(bars, interval)}


def read_cache(path):
    with open(path, "rb") as fh:
        payload = pickle.load(fh)
    if payload.get("version") != CACHE_VERSION:
        raise DataError("cache %s has version %s" % (path, payload.get("version")))
    return payload


def _thaw(session):
    """Ordinal date -> date. The arrays stay arrays."""
    thawed = dict(session)
    thawed["date"] = datetime.date.fromordinal(session["date"])
    return thawed


def _raw_sessions(root, interval, symbol, cache_root=None):
    kind, path = _choose(root, interval, symbol, cache_root)
    if kind == "cache":
        payload = read_cache(path)
        return [_thaw(session) for session in payload["sessions"]]
    return [_thaw(session) for session in _sessions_from_bars(stream_bars(path), interval)]


def _bars_of(session, interval):
    """Expand one array session into the bar dicts load_daily and load_sessions use."""
    day = session["date"]
    bars = []
    ends = session["end"]
    for i in range(len(session["close"])):
        minute = ends[i]
        end = datetime.datetime(day.year, day.month, day.day, minute // 60, minute % 60)
        if interval == "5minute":
            start = end - datetime.timedelta(minutes=BAR_MINUTES)
        else:
            start = end
        bars.append({
            "start": start,
            "date": day,
            "open": session["open"][i],
            "high": session["high"][i],
            "low": session["low"][i],
            "close": session["close"][i],
            "volume": session["volume"][i],
        })
    return bars


def _read_symbol(root, interval, symbol, cache_root=None):
    bars = []
    for session in _raw_sessions(root, interval, symbol, cache_root):
        bars.extend(_bars_of(session, interval))
    return bars


def load_daily(root, symbol, final=False, log_path=None, start=None, end=None, cache_root=None):
    """One symbol's daily bars. Listing days are gone and breaks split the rest."""
    by_date = {}
    for bar in _read_symbol(root, "day", symbol, cache_root):
        by_date[bar["date"]] = {
            "date": bar["date"],
            "open": bar["open"],
            "high": bar["high"],
            "low": bar["low"],
            "close": bar["close"],
            "volume": bar["volume"],
        }
    segments, excluded = _prepare(symbol, list(by_date.values()), final, log_path, start, end)
    return Series(symbol, "day", segments, excluded)


def _sessions(bars):
    by_date = {}
    for bar in bars:
        day = bar["date"]
        end = bar["start"] + datetime.timedelta(minutes=BAR_MINUTES)
        by_date.setdefault(day, []).append({
            "end": end,
            "open": bar["open"],
            "high": bar["high"],
            "low": bar["low"],
            "close": bar["close"],
            "volume": bar["volume"],
        })
    sessions = []
    for day in sorted(by_date):
        items = sorted(by_date[day], key=lambda item: item["end"])
        sessions.append({
            "date": day,
            "bars": items,
            "close": items[-1]["close"],
        })
    return sessions


def load_sessions(root, symbol, final=False, log_path=None, start=None, end=None, cache_root=None):
    """One symbol's 5-minute sessions. Bar timestamps are the bar end."""
    sessions = _sessions(_read_symbol(root, "5minute", symbol, cache_root))
    segments, excluded = _prepare(symbol, sessions, final, log_path, start, end)
    return Series(symbol, "5minute", segments, excluded)


def load_arrays(root, symbol, interval, final=False, log_path=None, start=None, end=None, cache_root=None):
    """One symbol as per-session arrays. Same listing cut, breaks, and holdout.

    This is the bulk reader. Expanding every bar into a dict is what load_sessions
    does for one symbol; a folder of 513 symbols stays in the arrays.
    """
    items = []
    for session in _raw_sessions(root, interval, symbol, cache_root):
        if len(session["close"]) == 0:
            continue
        items.append({
            "date": session["date"],
            "close": session["close"][-1],
            "session": session,
        })
    segments, excluded = _prepare(symbol, items, final, log_path, start, end)
    return Series(symbol, interval, segments, excluded)


def holding_return(series, start, end):
    """Close-to-close from start to end, inside a single segment.

    A date in the listing window, or a pair with a break between them, is refused.
    """
    start = _as_date(start)
    end = _as_date(end)
    if end < start:
        raise BreakError("holding period ends before it starts")
    start_at = None
    end_at = None
    for index, segment in enumerate(series.segments):
        for item in segment:
            if item["date"] == start:
                start_at = index
            if item["date"] == end:
                end_at = index
    if start_at is None or end_at is None:
        raise BreakError(
            "%s to %s is not inside the kept series" % (start.isoformat(), end.isoformat()))
    if start_at != end_at:
        raise BreakError("%s to %s crosses a break" % (start.isoformat(), end.isoformat()))
    closes = {}
    for item in series.segments[start_at]:
        closes[item["date"]] = item["close"]
    first = closes[start]
    if first == 0:
        raise BreakError("close on %s is 0" % start.isoformat())
    return (closes[end] - first) / first


def _points_from_sessions(sessions):
    closes = {}
    for session in sessions:
        if len(session["close"]) == 0:
            continue
        closes[session["date"]] = session["close"][-1]
    if not closes:
        return None, None, 0, []
    dates = sorted(closes)
    return dates[0], dates[-1], len(dates), [(day, closes[day]) for day in dates]


def scan_daily(path):
    """Stream one daily file. Returns first, last, session count, (date, close) pairs."""
    closes = {}
    for bar in stream_bars(path):
        closes[bar["date"]] = bar["close"]
    if not closes:
        return None, None, 0, []
    dates = sorted(closes)
    points = [(day, closes[day]) for day in dates]
    return dates[0], dates[-1], len(dates), points


def scan_daily_symbol(root, symbol, cache_root=None):
    """Daily scan through the cache when the pickle is newer than the csv."""
    kind, path = _choose(root, "day", symbol, cache_root)
    if kind == "csv":
        return scan_daily(path)
    return _points_from_sessions(_raw_sessions(root, "day", symbol, cache_root))


def _minute_from_sessions(sessions):
    counts = {}
    last_close = {}
    masks = {}
    for session in sessions:
        day = session["date"]
        if len(session["close"]) == 0:
            continue
        counts[day] = len(session["close"])
        last_close[day] = session["close"][-1]
        starts = []
        for minute in session["end"]:
            starts.append(minute - BAR_MINUTES)
        masks[day] = mask_from_starts(starts)
    if not counts:
        return None, None, {}, {}, {}
    return min(counts), max(counts), counts, last_close, masks


def scan_minute(path):
    """Stream one 5-minute file. Last close, bar count, and the 09:15-15:10 mask."""
    counts = {}
    last_stamp = {}
    last_close = {}
    masks = {}
    for bar in stream_bars(path):
        day = bar["date"]
        counts[day] = counts.get(day, 0) + 1
        minute = bar["start"].hour * 60 + bar["start"].minute
        if day not in last_stamp or bar["start"] >= last_stamp[day]:
            last_stamp[day] = bar["start"]
            last_close[day] = bar["close"]
        bit = start_bit(minute)
        if bit is not None:
            masks[day] = masks.get(day, 0) | (1 << bit)
    if not counts:
        return None, None, {}, {}, {}
    return min(counts), max(counts), counts, last_close, masks


def scan_minute_symbol(root, symbol, cache_root=None):
    """5-minute scan through the cache when the pickle is newer than the csv."""
    kind, path = _choose(root, "5minute", symbol, cache_root)
    if kind == "csv":
        return scan_minute(path)
    return _minute_from_sessions(_raw_sessions(root, "5minute", symbol, cache_root))


def symbols_in(root):
    """Symbol names that have a day file or a 5-minute file. Part files are skipped."""
    found = set()
    for interval in ("day", "5minute"):
        folder = os.path.join(root, interval)
        if not os.path.isdir(folder):
            continue
        for name in os.listdir(folder):
            if not name.endswith(".csv.gz") or name.endswith(".part.csv.gz"):
                continue
            found.add(name[:-len(".csv.gz")])
    return sorted(found)


def off_by_more_than_half_percent(day_close, minute_close):
    """True when the two closes differ by more than 0.5%. Exactly 0.5% is not off."""
    if day_close == 0:
        return minute_close != 0
    return abs(minute_close - day_close) / abs(day_close) > 0.005
