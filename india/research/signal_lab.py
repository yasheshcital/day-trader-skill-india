#!/usr/bin/env python3
"""Technical-analysis signal lab on daily bars, with a random-entry baseline.

Long only. A signal is decided at the close. The entry is the next session's
open. One open trade per symbol at a time, inside one entry/exit pair.
A break splits the series, and a trade still open at the end of a segment is
closed at that segment's last close, so the break day is not inside the trade.
The same close is used at the end of the window.

Window 2005-01-01 through 2024-12-31. Dates from 2025 on stay locked.
Reads bars only through india/research/data.py.

    python3 india/research/signal_lab.py
"""

import datetime
import os
import random
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from india.research import data
from india.research import regime
from india.research import ta

# Delivery costs, Zerodha-style. Check your broker: these are not the exchange's
# full current schedule, and the DP charge is the broker's.
BROKERAGE = 0.0
STT_PCT = 0.1            # percent of buy value and of sell value
EXCHANGE_PCT = 0.00297   # percent of both sides
SEBI_PCT = 0.0001        # percent of both sides
STAMP_PCT = 0.015        # percent of buy value
GST_PCT = 18.0           # percent of exchange + SEBI
DP_CHARGE = 15.34        # rupees, once per sell
NOTIONAL = 100000.0

START = datetime.date(2005, 1, 1)
END = datetime.date(2024, 12, 31)
WARMUP = 250
TURNOVER_N = 60
UNIVERSE_N = 200
ATR_N = 14
RSI_N = 14
BB_N = 20
BB_K = 2.0
HIGH_20 = 20
HIGH_52 = 252
WIDTH_N = 126
WIDTH_RECENT = 5
RSI_RECENT = 3
HOLD_SESSIONS = 20
RANDOM_RUNS = 100
RANDOM_SEED = 20261106
NIFTY = "NIFTY 50"
EXPERIMENTS = os.path.join(_ROOT, "india", "EXPERIMENTS.md")

ENTRY_NAMES = (
    "52w-high",
    "20d-high",
    "sma50-cross",
    "sma20-touch",
    "rsi-reclaim",
    "bb-squeeze",
    "engulf-low",
)
EXIT_NAMES = ("atr-stop", "sma20-close", "hold-20")


def delivery(entry, exit_px):
    """(percent return, net rupees) for a long sized at NOTIONAL, or None.

    Whole shares. A price above the notional buys nothing and is skipped.
    """
    if entry <= 0 or exit_px <= 0:
        return None
    shares = int(NOTIONAL // entry)
    if shares < 1:
        return None
    buy = entry * shares
    sell = exit_px * shares
    stt = (buy + sell) * STT_PCT / 100.0
    exchange = (buy + sell) * EXCHANGE_PCT / 100.0
    sebi = (buy + sell) * SEBI_PCT / 100.0
    stamp = buy * STAMP_PCT / 100.0
    gst = (exchange + sebi) * GST_PCT / 100.0
    cost = BROKERAGE + stt + exchange + sebi + stamp + gst + DP_CHARGE
    net = sell - buy - cost
    return (net / buy) * 100.0, net


def _ohlcv(session):
    n = len(session["close"])
    if n == 1:
        return (session["open"][0], session["high"][0], session["low"][0],
                session["close"][0], session["volume"][0])
    volume = 0.0
    high = session["high"][0]
    low = session["low"][0]
    for i in range(n):
        if session["high"][i] > high:
            high = session["high"][i]
        if session["low"][i] < low:
            low = session["low"][i]
        volume += session["volume"][i]
    return session["open"][0], high, low, session["close"][-1], volume


class Segment(object):
    """One break-free stretch of daily bars, with the indicators on it."""

    def __init__(self, dates, opens, highs, lows, closes, volumes):
        self.date = dates
        self.o = opens
        self.h = highs
        self.l = lows
        self.c = closes
        self.v = volumes
        self.sma20 = ta.sma_series(closes, 20)
        self.sma50 = ta.sma_series(closes, 50)
        self.sma200 = ta.sma_series(closes, 200)
        self.atr = ta.atr_series(highs, lows, closes, ATR_N)
        self.rsi = ta.rsi_series(closes, RSI_N)
        _mid, upper, _lower, width = ta.bollinger_series(closes, BB_N, BB_K)
        self.upper = upper
        self.width = width
        self.width_min = ta.trailing_is_min(width, WIDTH_N)
        self.high20 = ta.prior_high_series(highs, HIGH_20)
        self.high252 = ta.prior_high_series(highs, HIGH_52)
        self.low20 = ta.prior_low_series(lows, HIGH_20)


def segment_from_items(items):
    dates = []
    opens = []
    highs = []
    lows = []
    closes = []
    volumes = []
    for item in items:
        op, high, low, close, volume = _ohlcv(item["session"])
        dates.append(item["date"])
        opens.append(op)
        highs.append(high)
        lows.append(low)
        closes.append(close)
        volumes.append(volume)
    return Segment(dates, opens, highs, lows, closes, volumes)


def segment_from_rows(rows):
    """rows are dicts with date, open, high, low, close, volume. For tests."""
    items = []
    for row in rows:
        items.append({
            "date": row["date"],
            "session": {
                "open": [row["open"]],
                "high": [row["high"]],
                "low": [row["low"]],
                "close": [row["close"]],
                "volume": [row["volume"]],
            },
        })
    return segment_from_items(items)


def entry_hit(seg, i, kind):
    """True when entry rule `kind` fires on bar i. Indicators that are not ready are false."""
    if i < 0 or i >= len(seg.c):
        return False
    close = seg.c[i]
    if kind == "52w-high":
        level = seg.high252[i]
        return level is not None and close > level
    if kind == "20d-high":
        level = seg.high20[i]
        return level is not None and close > level
    if kind == "sma50-cross":
        if i < 1:
            return False
        prev_fast, prev_slow = seg.sma50[i - 1], seg.sma200[i - 1]
        fast, slow = seg.sma50[i], seg.sma200[i]
        if prev_fast is None or prev_slow is None or fast is None or slow is None:
            return False
        return prev_fast <= prev_slow and fast > slow
    if kind == "sma20-touch":
        sma20, sma200 = seg.sma20[i], seg.sma200[i]
        if sma20 is None or sma200 is None:
            return False
        return close > sma200 and seg.l[i] <= sma20 and close > sma20
    if kind == "rsi-reclaim":
        sma200 = seg.sma200[i]
        if sma200 is None or not close > sma200 or i < 1:
            return False
        if not close > seg.h[i - 1]:
            return False
        for k in range(RSI_RECENT):
            j = i - k
            if j < 0:
                break
            rsi = seg.rsi[j]
            if rsi is not None and rsi < 30.0:
                return True
        return False
    if kind == "bb-squeeze":
        upper = seg.upper[i]
        if upper is None or not close > upper:
            return False
        for k in range(WIDTH_RECENT):
            j = i - k
            if j < 0:
                break
            if seg.width_min[j]:
                return True
        return False
    if kind == "engulf-low":
        if i < 1 or seg.low20[i] is None:
            return False
        return (seg.l[i] <= seg.low20[i] and
                ta.bullish_engulfing(seg.o[i - 1], seg.c[i - 1], seg.o[i], seg.c[i]))
    raise ValueError("unknown entry %r" % (kind,))


def _hold(entry_i, exit_i, at_open):
    """Sessions the position is on. An open exit does not include the exit session."""
    if at_open:
        return exit_i - entry_i
    return exit_i - entry_i + 1


def exit_atr(seg, entry_i, last_i, atr):
    """(exit index, fill, at_open). Stop is entry - 2 ATR, target is entry + 3 ATR.

    A gap through either level fills at the open. On a day that trades through
    both, the stop is taken.
    """
    if atr is None or atr <= 0 or entry_i > last_i:
        return None
    entry = seg.o[entry_i]
    stop = entry - 2.0 * atr
    target = entry + 3.0 * atr
    for j in range(entry_i, last_i + 1):
        opened = seg.o[j]
        if opened <= stop or opened >= target:
            return j, opened, True
        if seg.l[j] <= stop:
            return j, stop, False
        if seg.h[j] >= target:
            return j, target, False
    return last_i, seg.c[last_i], False


def exit_sma20(seg, entry_i, last_i):
    """Close below SMA20 exits at the next open. The segment end closes at the close."""
    for j in range(entry_i, last_i + 1):
        sma = seg.sma20[j]
        if sma is None or not seg.c[j] < sma:
            continue
        if j + 1 <= last_i:
            return j + 1, seg.o[j + 1], True
        return j, seg.c[j], False
    return last_i, seg.c[last_i], False


def exit_hold(seg, entry_i, last_i, sessions=HOLD_SESSIONS):
    """Exit at the open `sessions` bars after the entry. Otherwise the segment's last close."""
    j = entry_i + sessions
    if j <= last_i:
        return j, seg.o[j], True
    return last_i, seg.c[last_i], False


def settle(seg, entry_i, last_i, kind, atr):
    """One round trip, or None when it cannot be sized."""
    if kind == "atr-stop":
        found = exit_atr(seg, entry_i, last_i, atr)
    elif kind == "sma20-close":
        found = exit_sma20(seg, entry_i, last_i)
    elif kind == "hold-20":
        found = exit_hold(seg, entry_i, last_i)
    else:
        raise ValueError("unknown exit %r" % (kind,))
    if found is None:
        return None
    exit_i, fill, at_open = found
    money = delivery(seg.o[entry_i], fill)
    if money is None:
        return None
    pct, rupees = money
    return {
        "pct": pct,
        "rupees": rupees,
        "hold": _hold(entry_i, exit_i, at_open),
        "exit_i": exit_i,
        "exit_date": seg.date[exit_i],
        "fill": fill,
        "entry": seg.o[entry_i],
    }


def take_one_at_a_time(hits):
    """hits are (entry_i, exit_i) in entry order. The next entry waits until after the exit."""
    taken = []
    busy = -1
    for entry_i, exit_i in hits:
        if entry_i <= busy:
            continue
        taken.append(entry_i)
        if exit_i > busy:
            busy = exit_i
    return taken


class Turnover(object):
    """Average close*volume of the previous n sessions, walking forward."""

    def __init__(self, dates, values, segments, n):
        self.dates = dates
        self.segments = segments
        self.n = n
        self.prefix = [0.0]
        total = 0.0
        for value in values:
            total += value
            self.prefix.append(total)
        self.i = 0

    def average_before(self, day):
        dates = self.dates
        while self.i < len(dates) and dates[self.i] < day:
            self.i += 1
        if self.i < self.n:
            return None
        if self.segments[self.i - 1] != self.segments[self.i - self.n]:
            return None
        total = self.prefix[self.i] - self.prefix[self.i - self.n]
        return total / float(self.n)


def liquid_names(day, books, count):
    scored = []
    for symbol, book in books:
        average = book.average_before(day)
        if average is None:
            continue
        scored.append((average, symbol))
    scored.sort(key=lambda item: (-item[0], item[1]))
    return [symbol for _average, symbol in scored[:count]]


def _percentile(values, p):
    ordered = sorted(values)
    if not ordered:
        return None
    if len(ordered) == 1:
        return ordered[0]
    rank = (len(ordered) - 1) * p
    lo = int(rank)
    hi = lo + 1
    if hi >= len(ordered):
        return ordered[-1]
    frac = rank - lo
    return ordered[lo] * (1.0 - frac) + ordered[hi] * frac


def _mean(values):
    if not values:
        return None
    return sum(values) / float(len(values))


def judge(row):
    """PASS only when every mark holds. The reasons are the marks that missed.

    Beats random in at least 95 of 100 runs, average after costs above 0,
    profitable in at least 14 of 20 years, average return above 0 in each
    market type, and at least 300 trades.
    """
    reasons = []
    if row["trades"] < 300:
        reasons.append("trades %d < 300" % row["trades"])
    avg = row["avg"]
    if avg is None or not avg > 0:
        reasons.append("average after costs %s is not above 0" % _signed(avg))
    if row["beats"] < 95:
        reasons.append("beats random %d of 100, need 95" % row["beats"])
    if row["years"] < 14:
        reasons.append("profitable years %d of 20, need 14" % row["years"])
    for key, label in (("up", "up"), ("down", "down"), ("sideways", "sideways")):
        value = row[key]
        if value is None or not value > 0:
            reasons.append("%s %s is not above 0" % (label, _signed(value)))
    return {"result": "PASS" if not reasons else "FAIL", "reasons": reasons}


def _signed(value):
    if value is None:
        return "n/a"
    return "%+.3f%%" % value


def _year_count(trades, start, end):
    totals = {}
    for trade in trades:
        year = trade["exit_date"].year
        totals[year] = totals.get(year, 0.0) + trade["rupees"]
    good = 0
    for year in range(start.year, end.year + 1):
        if totals.get(year, 0.0) > 0:
            good += 1
    return good


def _regime_avg(trades):
    buckets = {"up": [], "down": [], "sideways": []}
    for trade in trades:
        kind = trade.get("regime")
        if kind in buckets:
            buckets[kind].append(trade["pct"])
    return dict((key, _mean(buckets[key])) for key in buckets)


def summarize(name, entry, exit_name, trades, random_avgs, start=START, end=END):
    pcts = [trade["pct"] for trade in trades]
    avg = _mean(pcts)
    beats = 0
    for other in random_avgs:
        if avg is not None and other is not None and avg > other:
            beats += 1
    regimes = _regime_avg(trades)
    wins = sum(1 for trade in trades if trade["pct"] > 0)
    row = {
        "name": name,
        "entry": entry,
        "exit": exit_name,
        "trades": len(trades),
        "win_rate": (wins / float(len(trades))) if trades else None,
        "avg": avg,
        "hold": _mean([trade["hold"] for trade in trades]),
        "beats": beats,
        "random_median": _percentile(random_avgs, 0.5),
        "random_p95": _percentile(random_avgs, 0.95),
        "years": _year_count(trades, start, end),
        "up": regimes["up"],
        "down": regimes["down"],
        "sideways": regimes["sideways"],
    }
    row["verdict"] = judge(row)
    return row


def format_row(row):
    win = "n/a" if row["win_rate"] is None else "%.1f%%" % (100.0 * row["win_rate"])
    hold = "n/a" if row["hold"] is None else "%.1f" % row["hold"]
    return (
        "%s / %s: trades %d, win %s, avg %s, hold %sd, beats random %d/100 "
        "(random median %s, p95 %s), years %d/20, up %s, down %s, sideways %s, %s" % (
            row["entry"], row["exit"], row["trades"], win, _signed(row["avg"]), hold,
            row["beats"], _signed(row["random_median"]), _signed(row["random_p95"]),
            row["years"], _signed(row["up"]), _signed(row["down"]), _signed(row["sideways"]),
            row["verdict"]["result"]))


def _last_index(seg, end):
    last = -1
    for i, day in enumerate(seg.date):
        if day <= end:
            last = i
        else:
            break
    return last


def _flags(seg, i):
    bits = 0
    for bit, name in enumerate(ENTRY_NAMES):
        if entry_hit(seg, i, name):
            bits |= 1 << bit
    return bits


def _build_slots(symbols, universe, regimes, warmup, start, end):
    """Eligible entries: in the universe on the signal day, warmup done, entry in the window."""
    slots = []
    by_month = {}
    for sym_i, symbol in enumerate(symbols):
        for seg_i, seg in enumerate(symbol["segments"]):
            last = _last_index(seg, end)
            if last < 1:
                continue
            for entry_i in range(1, last + 1):
                signal_i = entry_i - 1
                if signal_i < warmup:
                    continue
                signal_day = seg.date[signal_i]
                entry_day = seg.date[entry_i]
                if entry_day < start or entry_day > end:
                    continue
                members = universe.get(signal_day)
                if not members or symbol["name"] not in members:
                    continue
                money_ok = int(NOTIONAL // seg.o[entry_i]) >= 1 if seg.o[entry_i] > 0 else False
                if not money_ok:
                    continue
                slot = {
                    "sym": sym_i,
                    "seg": seg_i,
                    "signal_i": signal_i,
                    "entry_i": entry_i,
                    "entry_date": entry_day,
                    "regime": regimes.get(entry_day),
                    "flags": _flags(seg, signal_i),
                    "atr": seg.atr[signal_i],
                    "outcomes": None,
                }
                slot["outcomes"] = _three(seg, entry_i, last, slot["atr"])
                slots.append(slot)
                key = (entry_day.year, entry_day.month)
                by_month.setdefault(key, []).append(len(slots) - 1)
    return slots, by_month


def _three(seg, entry_i, last, atr):
    found = []
    for name in EXIT_NAMES:
        found.append(settle(seg, entry_i, last, name, atr))
    return found


def _trade_from(slot, exit_id):
    outcome = slot["outcomes"][exit_id]
    if outcome is None:
        return None
    return {
        "pct": outcome["pct"],
        "rupees": outcome["rupees"],
        "hold": outcome["hold"],
        "exit_i": outcome["exit_i"],
        "exit_date": outcome["exit_date"],
        "entry_i": slot["entry_i"],
        "entry_date": slot["entry_date"],
        "regime": slot["regime"],
        "sym": slot["sym"],
        "seg": slot["seg"],
        "entry": outcome["entry"],
        "fill": outcome["fill"],
    }


def real_trades(slots, entry_bit, exit_id):
    """One open trade per symbol segment. Signals that fire while it is open are skipped."""
    grouped = {}
    for slot in slots:
        if slot["flags"] & (1 << entry_bit):
            grouped.setdefault((slot["sym"], slot["seg"]), []).append(slot)
    trades = []
    for key in grouped:
        hits = []
        chosen = []
        for slot in grouped[key]:
            outcome = slot["outcomes"][exit_id]
            if outcome is None:
                continue
            hits.append((slot["entry_i"], outcome["exit_i"]))
            chosen.append(slot)
        keep = set(take_one_at_a_time(hits))
        for slot in chosen:
            if slot["entry_i"] in keep:
                trade = _trade_from(slot, exit_id)
                if trade is not None:
                    trades.append(trade)
    return trades


def random_average(trades, by_month, slots, exit_id, rng):
    """Replace each real entry with a random eligible entry from the same month."""
    pcts = []
    for trade in trades:
        key = (trade["entry_date"].year, trade["entry_date"].month)
        pool = by_month.get(key)
        if not pool:
            continue
        slot = slots[pool[rng.randrange(len(pool))]]
        sampled = _trade_from(slot, exit_id)
        if sampled is None:
            continue
        pcts.append(sampled["pct"])
    return _mean(pcts)


def score_slots(slots, by_month, runs, seed, start=START, end=END, log=None):
    emit = log or (lambda line: None)
    rows = []
    for entry_bit, entry in enumerate(ENTRY_NAMES):
        for exit_id, exit_name in enumerate(EXIT_NAMES):
            trades = real_trades(slots, entry_bit, exit_id)
            rng = random.Random(seed + entry_bit * 10 + exit_id)
            random_avgs = []
            for _run in range(runs):
                random_avgs.append(random_average(trades, by_month, slots, exit_id, rng))
            row = summarize("%s / %s" % (entry, exit_name), entry, exit_name, trades, random_avgs, start, end)
            rows.append(row)
            emit(format_row(row))
    rows.sort(key=lambda row: (-row["beats"], -(row["avg"] or -1e9), row["name"]))
    return rows


def load_symbol(root, symbol, end=END, final=False, log_path=None):
    """Daily segments through `end`. The holdout stays out unless final=True."""
    series = data.load_arrays(root, symbol, "day", final=final, log_path=log_path, end=end)
    segments = []
    for segment in series.segments:
        if segment:
            segments.append(segment_from_items(segment))
    return segments


def _books(root, end, log, final=False, log_path=None):
    emit = log or (lambda line: None)
    names = []
    loaded = []
    books = []
    for symbol in data.symbols_in(root):
        if symbol.startswith("NIFTY"):
            continue
        try:
            series = data.load_arrays(root, symbol, "day", final=final, log_path=log_path, end=end)
        except data.DataError:
            continue
        dates = []
        values = []
        seg_ids = []
        segments = []
        seg_id = 0
        for segment in series.segments:
            if not segment:
                continue
            built = segment_from_items(segment)
            segments.append(built)
            for i, day in enumerate(built.date):
                dates.append(day)
                values.append(built.c[i] * built.v[i])
                seg_ids.append(seg_id)
            seg_id += 1
        if not dates:
            continue
        names.append(symbol)
        loaded.append({"name": symbol, "segments": segments})
        books.append((symbol, Turnover(dates, values, seg_ids, TURNOVER_N)))
        if len(names) % 25 == 0:
            emit("loaded %d symbols" % len(names))
    if names:
        emit("loaded %d symbols" % len(names))
    return loaded, books


def run(root, start=START, end=END, warmup=WARMUP, universe_n=UNIVERSE_N,
        runs=RANDOM_RUNS, seed=RANDOM_SEED, log=None, symbols=None, regimes=None):
    """Score the 21 combinations. `symbols` and `regimes` bypass the disk for tests."""
    emit = log or (lambda line: None)
    if symbols is None:
        loaded, books = _books(root, end, emit)
        calendar = []
        seen = set()
        for symbol in loaded:
            for seg in symbol["segments"]:
                for day in seg.date:
                    if day not in seen and day <= end:
                        seen.add(day)
                        calendar.append(day)
        calendar.sort()
        emit("ranking turnover")
        universe = {}
        for day in calendar:
            names = liquid_names(day, books, universe_n)
            if names:
                universe[day] = set(names)
        nifty = data.load_arrays(root, NIFTY, "day", end=end)
        points = []
        for segment in nifty.segments:
            for item in segment:
                points.append((item["date"], item["close"]))
        regimes = regime.by_date(points)
    else:
        loaded = symbols
        universe = {}
        # Tests pass symbols that are already the whole universe every day.
        for symbol in loaded:
            for seg in symbol["segments"]:
                for day in seg.date:
                    universe.setdefault(day, set()).add(symbol["name"])
        if regimes is None:
            regimes = {}
    emit("building entries")
    slots, by_month = _build_slots(loaded, universe, regimes, warmup, start, end)
    emit("eligible entries: %d" % len(slots))
    rows = score_slots(slots, by_month, runs, seed, start, end, emit)
    rows.sort(key=lambda row: (-row["beats"], -(row["avg"] or -1e9), row["name"]))
    return rows


def rules_text(stamp):
    """The hypothesis and the pass mark. Written before any result exists."""
    return "\n".join([
        "## Attempt 9",
        "",
        "Rules fixed on %s, before the run." % stamp,
        "",
        "Hypothesis: one of seven long daily signals, with one of three exits, "
        "beats a same-month random entry often enough to clear the pass mark on "
        "2005-01-01 through 2024-12-31.",
        "",
        "Universe, point in time: each day, the 200 symbols with the highest average "
        "daily turnover (close times volume) over the previous 60 sessions, using only "
        "sessions before that day and never a turnover that crosses a break. A symbol's "
        "first 250 sessions in a segment are skipped, because the indicators need that "
        "history. A break starts the count again. Data is read through india/research/data.py. "
        "Dates from 2025-01-01 on are not requested.",
        "",
        "A signal is decided at the close. The entry is the next session's open. Long only. "
        "One open trade per symbol at a time. A trade still open at the end of a segment "
        "exits at that segment's last close, so it is not open across a break, and the same "
        "close is used at the end of the window.",
        "",
        "Entries: (1) close above the prior 252-session high, (2) close above the prior "
        "20-session high, (3) SMA50 crosses above SMA200, (4) close above SMA200, the low "
        "touches SMA20 and the close finishes above SMA20, (5) close above SMA200, RSI14 "
        "below 30 within the last 3 sessions and the close above yesterday's high, "
        "(6) Bollinger width (20, 2, population deviation) at its 126-session low within "
        "the last 5 sessions and the close above the upper band, (7) bullish engulfing with "
        "the low at or through the prior 20-session low.",
        "",
        "Exits: (A) stop at entry minus 2 ATR14 and target at entry plus 3 ATR14, ATR from "
        "the signal day, stop first when both are hit the same day, gaps filled at the open, "
        "(B) a close below SMA20 exits at the next open, (C) exit at the open 20 sessions "
        "after the entry.",
        "",
        "Costs, delivery, check your broker: brokerage 0, STT 0.1% of buy value and of sell "
        "value, exchange 0.00297% of both sides, SEBI 0.0001% of both sides, stamp duty "
        "0.015% of buy value, GST 18% of exchange plus SEBI, DP charge Rs 15.34 per sell. "
        "Each trade is sized at Rs 1,00,000 in whole shares.",
        "",
        "Random baseline: for each of the 21 pairs, 100 seeded runs. Each real entry is "
        "replaced by an entry on a random eligible symbol and day from the same calendar "
        "month, with the same exit. The seed is 20261106.",
        "",
        "Market type is the type known before the entry day's open, from NIFTY 50's 200-day "
        "average (up, down, or sideways).",
        "",
        "Pass mark, fixed before this run and separate from the mark used for attempts 1 to 8: "
        "beats the random entry in at least 95 of 100 runs, average percent return after costs "
        "above 0, profitable in at least 14 of the 20 years, average return above 0 in up, down "
        "and sideways markets, and at least 300 trades. A year is profitable when the sum of "
        "net rupees of trades that exit in that year is above 0.",
        "",
        "Results are filled in after the run.",
        "",
    ])


def results_text(stamp, rows):
    body = rules_text(stamp).replace("Results are filled in after the run.", "").rstrip()
    lines = [body, "", "Sorted by how many of the 100 random runs the signal beat.", ""]
    passed = 0
    for row in rows:
        lines.append(format_row(row))
        if row["verdict"]["result"] == "PASS":
            passed += 1
        else:
            lines.append("  " + "; ".join(row["verdict"]["reasons"]))
    lines.append("")
    lines.append("Combinations that pass: %d of %d." % (passed, len(rows)))
    return "\n".join(lines).rstrip() + "\n"


def table_rows(stamp, rows):
    """One row. The numbers are the combinations that pass, each with its own average."""
    passing = [row for row in rows if row["verdict"]["result"] == "PASS"]
    result = "PASS" if passing else "FAIL"
    rule = "7 entries x 3 exits, delivery costs, Rs 1,00,000"
    universe = "point-in-time top 200 by prior 60-session turnover, 2005-01-01 to 2024-12-31"
    if not passing:
        hypothesis = ("A daily long technical signal beats a same-month random entry on "
                      "2005-2024. None of the combinations pass.")
        trades, avg = "0", "n/a"
    else:
        bits = []
        for row in passing:
            bits.append("%s (%s trades, %s after costs, beats random %d/100)" % (
                row["name"], format(row["trades"], ",d"), _signed(row["avg"]), row["beats"]))
        hypothesis = "Passing combinations on 2005-2024: %s." % "; ".join(bits)
        trades = "; ".join(format(row["trades"], ",d") for row in passing)
        avg = "; ".join(_signed(row["avg"]) for row in passing)
    return ["| 9 | %s | %s | %s | %s | %s | %s | %s | %s |" % (
        stamp, hypothesis, rule, universe, trades, avg, avg, result)]


def install(path, section, rows):
    """Replace an existing attempt 9 section and its table rows."""
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    kept = []
    for line in text.splitlines():
        if line.startswith("| 9 |"):
            continue
        kept.append(line)
    text = "\n".join(kept)
    if not text.endswith("\n"):
        text += "\n"
    start = text.find("\n## Attempt 9\n")
    forward = text.find("\n## Forward test\n")
    later = text.find("\n## Attempt 10\n")
    block = "\n" + section.rstrip() + "\n\n"
    if start != -1 and (forward == -1 or start < forward):
        end = forward if forward != -1 else len(text)
        if later != -1 and later > start and later < end:
            end = later
        text = text[:start] + block + text[end:]
    elif forward != -1:
        text = text[:forward] + block + text[forward:]
    else:
        text = text.rstrip() + "\n" + block
    if rows:
        marker = "| 8 | 2026-11-06 | The same rule is profitable after costs on 2015-2024"
        at = text.find(marker)
        if at == -1:
            at = text.rfind("\n| 8 |")
            if at != -1:
                at += 1
        if at != -1:
            line_end = text.find("\n", at)
            text = text[:line_end] + "\n" + "\n".join(rows) + text[line_end:]
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


def main(argv=None, log=None):
    import argparse
    parser = argparse.ArgumentParser(description="Daily signal lab. Nothing is placed.")
    parser.add_argument("--root", default=os.path.join("data", "kite"))
    parser.add_argument("--experiments", default=EXPERIMENTS)
    parser.add_argument("--runs", type=int, default=RANDOM_RUNS)
    args = parser.parse_args(argv)
    emit = log or (lambda line: print(line, flush=True))
    stamp = datetime.date.today().isoformat()
    install(args.experiments, rules_text(stamp), [])
    emit("rules written to %s before the run" % args.experiments)
    rows = run(args.root, runs=args.runs, log=emit)
    install(args.experiments, results_text(stamp, rows), table_rows(stamp, rows))
    emit("sorted by beats-random")
    for row in rows:
        emit(format_row(row))
    return 0


if __name__ == "__main__":
    sys.exit(main())
