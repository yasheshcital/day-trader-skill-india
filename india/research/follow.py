#!/usr/bin/env python3
"""Attempt 13 big-gap continuation, and attempt 14 short swing.

Rules are written to EXPERIMENTS.md before either backtest. 2025 is not
requested. Nothing is placed.

    python3 india/research/follow.py
"""

import datetime
import os
import random
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from india.research import data
from india.research import harness as h
from india.research import regime
from india.research import signal_lab as lab
from india.research import ta

SWING_START = h.START
SWING_END = h.END
YEAR_DAYS = 365.25
NON_GAP = 0.005
VOLUME_BARS = 10
VOLUME_MULT = 2.0
NONGAP_OFFSET = 500
RSI_LIMIT = 5
SOUP_LIMIT = 3
BOOK = "BOOK"

HYPOTHESIS_13 = (
    "hypothesis found in attempt 12 data (gap GO 3 lost to random same-day entries); "
    "must clear the full pass mark"
)


def batch13():
    return [
        {"name": "gap cont 3", "kind": "big_gap", "min_gap": 0.03, "volume": False},
        {"name": "gap cont 4", "kind": "big_gap", "min_gap": 0.04, "volume": False},
        {"name": "gap cont 3 vol", "kind": "big_gap", "min_gap": 0.03, "volume": True},
    ]


def batch14():
    return [
        {"name": "rsi2 < 5", "kind": "rsi", "pool": "rsi", "rsi_max": 5.0, "down2": False},
        {"name": "rsi2 < 10", "kind": "rsi", "pool": "rsi", "rsi_max": 10.0, "down2": False},
        {"name": "rsi2 < 10 down2", "kind": "rsi", "pool": "rsi", "rsi_max": 10.0, "down2": True},
        {"name": "ibs < 0.2", "kind": "ibs", "pool": "ibs", "ibs_max": 0.2, "index": False},
        {"name": "ibs < 0.1", "kind": "ibs", "pool": "ibs", "ibs_max": 0.1, "index": False},
        {"name": "ibs < 0.2 nifty", "kind": "ibs", "pool": "ibs", "ibs_max": 0.2, "index": True},
        {"name": "soup 20", "kind": "soup", "pool": "soup", "n": 20},
        {"name": "soup 10", "kind": "soup", "pool": "soup", "n": 10},
        {"name": "soup 55", "kind": "soup", "pool": "soup", "n": 55},
        {"name": "rev K10", "kind": "reversal", "k": 10, "above": False},
        {"name": "rev K20", "kind": "reversal", "k": 20, "above": False},
        {"name": "rev K10 above200", "kind": "reversal", "k": 10, "above": True},
    ]


def vol_multiple(today, history):
    """Opening volume over the mean of the previous 10. None until 10 exist."""
    if history is None or len(history) < VOLUME_BARS:
        return None
    total = 0.0
    start = len(history) - VOLUME_BARS
    for i in range(start, len(history)):
        total += history[i]
    avg = total / float(VOLUME_BARS)
    if not avg > 0:
        return None
    return today / avg


def is_nongap(gap):
    """Strictly inside half a percent. Exactly 0.5% is not a non-gap day."""
    return gap is not None and abs(gap) < NON_GAP


def opening_volume(session):
    """Volume of bars ending 09:20 through 09:30, the 09:15-09:30 clock time."""
    total = 0.0
    ends = session["end"]
    for i in range(len(ends)):
        if ends[i] > h.M_0930:
            break
        total += session["volume"][i]
    return total


def entry_window(session):
    """Same-day random bars: ends 09:30 through 14:30, both included."""
    return h.indices_between(session, h.M_0930, h.M_1430)


def still_beyond(side, close, prev_close):
    if side == "buy":
        return close > prev_close
    return close < prev_close


def side_r(session, side, symbol):
    """09:30 close, stop at the opening-range extreme, flat at 15:10."""
    i = h.minute_index(session, h.M_0930)
    if i is None:
        return None
    high, low = h.range_bounds(session, h.M_0930)
    if high is None or low is None:
        return None
    stop = low if side == "buy" else high
    entry = session["close"][i]
    risk = abs(entry - stop)
    scored = h.bar_outcome(session, i, side, risk, None, h.M_1510, symbol, False, True)
    if scored is None:
        return None
    return scored[1]


def big_gap_trade(session, day, symbol, prev_close, regime_kind, large, spec, ratio):
    """Enter at the 09:30 close when the open gap is still open. Flat at 15:10."""
    if spec["volume"]:
        if ratio is None or not ratio >= VOLUME_MULT:
            return None
    sized = h.gap_size(session, prev_close)
    if sized is None:
        return None
    gap, _opened = sized
    if not abs(gap) >= spec["min_gap"]:
        return None
    if not gap > 0 and not gap < 0:
        return None
    side = "buy" if gap > 0 else "sell"
    i = h.minute_index(session, h.M_0930)
    if i is None:
        return None
    close = session["close"][i]
    if not still_beyond(side, close, prev_close):
        return None
    high, low = h.range_bounds(session, h.M_0930)
    if high is None or low is None:
        return None
    stop = low if side == "buy" else high
    risk = abs(close - stop)
    return h._trade(
        session, day, symbol, side, i, risk, None, h.M_1510, True,
        entry_window(session), regime_kind, large, False)


def scan_gap_symbol(symbol, sessions, book, member_days, large_days, regimes, specs):
    """Trades on universe days, and a non-gap R pool for every usable day."""
    found = {}
    for spec in specs:
        found[spec["name"]] = []
    pool = {}
    history = {}
    for day in sorted(sessions):
        session = sessions[day]
        row = book.by_date.get(day)
        if row is None:
            continue
        seg = row["seg"]
        vol = opening_volume(session)
        ratio = vol_multiple(vol, history.get(seg))
        prev = None
        if row["i"] > 0:
            earlier = book.rows[row["i"] - 1]
            if earlier["seg"] == seg and earlier["close"] > 0:
                prev = earlier["close"]
        if prev is not None:
            sized = h.gap_size(session, prev)
            gap = None if sized is None else sized[0]
            if is_nongap(gap):
                buy = side_r(session, "buy", symbol)
                sell = side_r(session, "sell", symbol)
                if buy is not None or sell is not None:
                    key = (day.year, day.month)
                    pool.setdefault(key, []).append((buy, sell))
            if day in member_days:
                kind = regimes.get(day)
                large = day in large_days
                for spec in specs:
                    trade = big_gap_trade(session, day, symbol, prev, kind, large, spec, ratio)
                    if trade is not None:
                        found[spec["name"]].append(trade)
        bucket = history.get(seg)
        if bucket is None:
            bucket = []
            history[seg] = bucket
        bucket.append(vol)
    return found, pool


def apply_nongap(trades, pools, runs, seed):
    """Excess versus a random non-gap day of the same symbol and month.

    Each run picks a day, then a direction. Seed is the same-day seed plus
    NONGAP_OFFSET, so the two baselines do not share a stream.
    """
    trades.sort(key=lambda item: (item["date"], item["symbol"]))
    for run_i in range(runs):
        rng = random.Random(seed + run_i)
        for trade in trades:
            month = pools.get(trade["symbol"], {}).get((trade["date"].year, trade["date"].month))
            picked = trade.get("ng")
            if picked is None:
                picked = []
                trade["ng"] = picked
            if not month:
                picked.append(None)
                continue
            buy, sell = month[rng.randrange(len(month))]
            side = buy if rng.randrange(2) == 0 else sell
            picked.append(side)
    for trade in trades:
        picks = []
        for value in trade.get("ng", []):
            if value is not None:
                picks.append(value)
        random_r = h._mean(picks)
        if random_r is None:
            trade["excess_ng"] = None
        else:
            excess = trade["r_after"] - random_r
            if abs(excess) < 1e-9:
                excess = 0.0
            trade["excess_ng"] = excess
        trade.pop("ng", None)


def monthly_t(trades, key):
    by_month = {}
    for trade in trades:
        value = trade.get(key)
        if value is None:
            continue
        month = (trade["date"].year, trade["date"].month)
        by_month.setdefault(month, []).append(value)
    monthly = []
    for month in sorted(by_month):
        monthly.append(h._mean(by_month[month]))
    return h.t_stat(monthly)


def judge_gap(block, family):
    """Attempt 12's mark. The t is the non-gap t, not the same-day t."""
    reasons = []
    if block["avg_after"] is None or not block["avg_after"] >= 0.10:
        reasons.append("avg R after costs %s is below +0.10" % h._r(block["avg_after"]))
    if block["trades"] < 300:
        reasons.append("trades %d is below 300" % block["trades"])
    if block["days"] < 100:
        reasons.append("days %d is below 100" % block["days"])
    if block["t"] is None or not block["t"] > 3:
        reasons.append("t vs non-gap %s is not above 3" % h._num(block["t"]))
    checks = (
        ("early", "2015-2019"),
        ("late", "2020-2024"),
        ("up", "up"),
        ("down", "down"),
        ("sideways", "sideways"),
        ("large", "large caps"),
    )
    for key, label in checks:
        if block[key] is None or not block[key] > 0:
            reasons.append("%s %s is not above 0" % (label, h._r(block[key])))
    strong = 0
    for item in family:
        if item.get("t") is not None and item["t"] > 2:
            strong += 1
    if strong < 2:
        reasons.append("family variants with t above 2: %d of %d, need 2" % (strong, len(family)))
    return {"result": "PASS" if not reasons else "FAIL", "reasons": reasons}


def score_gap(spec, index, trades, pools, runs):
    """Same-day excess is stored. The pass t is the non-gap excess."""
    seed = h.SEED + index * 1000
    h.apply_random(trades, runs, seed)
    for trade in trades:
        trade["excess_same"] = trade.get("excess")
    apply_nongap(trades, pools, runs, seed + NONGAP_OFFSET)
    for trade in trades:
        trade["excess"] = trade.get("excess_ng")
    block = h.summarise_intraday(spec["name"], trades)
    block["kind"] = spec["kind"]
    block["t_same"] = monthly_t(trades, "excess_same")
    block["excess_same"] = h._mean([
        item["excess_same"] for item in trades if item.get("excess_same") is not None])
    block["excess_ng"] = h._mean([
        item["excess_ng"] for item in trades if item.get("excess_ng") is not None])
    block["seed"] = seed
    block["runs"] = runs
    return block


def run_gap(root, runs=h.RUNS, log=None):
    """Attempt 13. 5-minute bars, 2015-2024. final stays false."""
    emit = log or (lambda line: None)
    specs = batch13()
    names = []
    for symbol in data.symbols_in(root):
        if symbol.startswith("NIFTY"):
            continue
        names.append(symbol)
    nifty_book = h.load_daily_book(root, lab.NIFTY)
    points = [(row["date"], row["close"]) for row in nifty_book.rows]
    regimes = regime.by_date(points)
    calendar = []
    for row in nifty_book.rows:
        if h.INTRADAY_START <= row["date"] <= h.INTRADAY_END:
            calendar.append(row["date"])
    emit("loading daily books")
    books = []
    for i, symbol in enumerate(names):
        try:
            book = h.load_daily_book(root, symbol)
        except data.DataError:
            continue
        if book.rows:
            books.append((symbol, book))
        if (i + 1) % 50 == 0:
            emit("  daily %d/%d" % (i + 1, len(names)))
    emit("daily books %d, sessions %d" % (len(books), len(calendar)))
    top200, top100 = h.rank_universe(books, calendar)
    member = h._invert(top200)
    large = h._invert(top100)
    emit("universe ranked")
    collected = {}
    for spec in specs:
        collected[spec["name"]] = []
    pools = {}
    book_of = {}
    for symbol, book in books:
        book_of[symbol] = book
    symbols = sorted(member)
    emit("scanning %d symbols" % len(symbols))
    for i, symbol in enumerate(symbols):
        book = book_of.get(symbol)
        if book is None:
            continue
        try:
            sessions = h.load_usable_map(root, symbol, h.INTRADAY_START)
        except data.DataError:
            continue
        found, pool = scan_gap_symbol(
            symbol, sessions, book, member[symbol], large.get(symbol, set()), regimes, specs)
        for name, trades in found.items():
            collected[name].extend(trades)
        if pool:
            pools[symbol] = pool
        if (i + 1) % 25 == 0:
            emit("  symbol %d/%d" % (i + 1, len(symbols)))
    blocks = []
    for index, spec in enumerate(specs):
        emit("scoring %s (%d trades)" % (spec["name"], len(collected[spec["name"]])))
        blocks.append(score_gap(spec, index, collected[spec["name"]], pools, runs))
    family = list(blocks)
    for block in blocks:
        block["verdict"] = judge_gap(block, family)
    return blocks


def net_return(entry, exit_px):
    """Percent return after delivery costs. None when a whole share does not fit."""
    money = lab.delivery(entry, exit_px)
    if money is None:
        return None
    return money[0]


def ibs_value(high, low, close):
    """(close - low) / (high - low). Undefined when the bar has no range."""
    if high is None or low is None or not high > low:
        return None
    return (close - low) / (high - low)


def rsi_fires(seg, i, maximum, down2):
    """close > SMA200 and RSI(2) strictly below maximum. down2 needs two lower closes."""
    if i < 0 or i >= len(seg.c):
        return False
    sma = seg.sma200[i]
    rsi = seg.rsi2[i]
    if sma is None or rsi is None or not seg.c[i] > sma:
        return False
    if not rsi < maximum:
        return False
    if down2:
        if i < 2:
            return False
        if not (seg.c[i] < seg.c[i - 1] and seg.c[i - 1] < seg.c[i - 2]):
            return False
    return True


def ibs_fires(seg, i, maximum):
    if i < 0 or i >= len(seg.c):
        return False
    sma = seg.sma200[i]
    if sma is None or not seg.c[i] > sma:
        return False
    value = ibs_value(seg.h[i], seg.l[i], seg.c[i])
    if value is None:
        return False
    return value < maximum


def soup_fires(low, close, prior):
    """Today's low under the prior n-day low, and today's close back above it."""
    if prior is None:
        return False
    return low < prior and close > prior


def prior_of(seg, i, n):
    if n == 10:
        return seg.low10[i]
    if n == 20:
        return seg.low20[i]
    if n == 55:
        return seg.low55[i]
    return None


def exit_rule(seg, entry_i, limit, hit):
    """Next open after hit(seg, j), else the open `limit` sessions after entry.

    Closes of the entry session through the session before the time stop are
    eligible. The time stop is the open at entry_i + limit.
    """
    last = entry_i + limit
    n = len(seg.o)
    if entry_i < 0 or last >= n:
        return None
    if not seg.o[entry_i] > 0:
        return None
    for j in range(entry_i, last):
        if hit(seg, j):
            px = seg.o[j + 1]
            if not px > 0:
                return None
            return j + 1, px, True
    px = seg.o[last]
    if not px > 0:
        return None
    return last, px, True


def close_above_sma5(seg, j):
    sma = seg.sma5[j]
    return sma is not None and seg.c[j] > sma


def close_above_prior_high(seg, j):
    if j <= 0:
        return False
    return seg.c[j] > seg.h[j - 1]


def exit_soup(seg, entry_i, stop):
    """Stop at `stop`, target at 2R, else the open three sessions later.

    A gap through the stop fills at the open. Stop is taken before target.
    An entry that is not strictly above the stop is skipped.
    """
    last = entry_i + SOUP_LIMIT
    n = len(seg.o)
    if entry_i < 0 or last >= n:
        return None
    entry = seg.o[entry_i]
    if not entry > 0 or stop is None or not stop > 0 or not entry > stop:
        return None
    risk = entry - stop
    target = entry + 2.0 * risk
    for j in range(entry_i, last):
        opened = seg.o[j]
        if opened <= stop:
            return j, opened, True
        if seg.l[j] <= stop:
            return j, stop, False
        if seg.h[j] >= target:
            return j, target, False
    px = seg.o[last]
    if not px > 0:
        return None
    return last, px, True


def market_return(nifty, entry_date, exit_date, on_open):
    """NIFTY price return from the entry open to the exit open, or that day's close."""
    entry = nifty.get(entry_date)
    exit_bar = nifty.get(exit_date)
    if entry is None or exit_bar is None or not entry.get("open", 0) > 0:
        return None
    px = exit_bar["open"] if on_open else exit_bar.get("close")
    if px is None or not px > 0:
        return None
    return (px / entry["open"] - 1.0) * 100.0


def make_trade(day, symbol, ret, mkt, regime_kind, large, hold_days, large_ret=None):
    trade = {
        "date": day,
        "symbol": symbol,
        "ret": ret,
        "mkt": mkt,
        "regime": regime_kind,
        "large": large,
        "hold_days": hold_days,
        "month": (day.year, day.month),
    }
    if large_ret is not None:
        trade["large_ret"] = large_ret
    elif large:
        trade["large_ret"] = ret
    return trade


def adjusted_excess(ret, mkt, random_pairs):
    """Strategy minus market, minus the mean of the same figure on random entries."""
    if mkt is None:
        return None
    adj = ret - mkt
    vals = []
    for rret, rmkt in random_pairs:
        if rret is None or rmkt is None:
            continue
        vals.append(adj - (rret - rmkt))
    return h._mean(vals)


def attach_indicators(segments):
    for seg in segments:
        seg.sma5 = ta.sma_series(seg.c, 5)
        seg.rsi2 = ta.rsi_series(seg.c, 2)
        seg.low10 = ta.prior_low_series(seg.l, 10)
        seg.low55 = ta.prior_low_series(seg.l, 55)


def _pool_add(pools, style, symbol, day, ret, mkt):
    if ret is None:
        return
    month = (day.year, day.month)
    by_symbol = pools.get(style)
    if by_symbol is None:
        by_symbol = {}
        pools[style] = by_symbol
    by_month = by_symbol.get(symbol)
    if by_month is None:
        by_month = {}
        by_symbol[symbol] = by_month
    bucket = by_month.get(month)
    if bucket is None:
        bucket = []
        by_month[month] = bucket
    bucket.append((ret, mkt))


def _finish(seg, entry_i, found, nifty):
    if found is None:
        return None
    exit_i, px, on_open = found
    ret = net_return(seg.o[entry_i], px)
    if ret is None:
        return None
    exit_day = seg.date[exit_i]
    mkt = market_return(nifty, seg.date[entry_i], exit_day, on_open)
    hold = (exit_day - seg.date[entry_i]).days
    return ret, mkt, hold


def fill_pools(symbol, segments, top200, nifty, pools):
    """Random entries: in the top 200 on the entry day, signal not required."""
    for seg in segments:
        n = len(seg.date)
        for entry_i in range(n):
            day = seg.date[entry_i]
            if day < SWING_START or day > SWING_END:
                continue
            if symbol not in top200.get(day, ()):
                continue
            rsi_exit = exit_rule(seg, entry_i, RSI_LIMIT, close_above_sma5)
            done = _finish(seg, entry_i, rsi_exit, nifty)
            if done is not None:
                _pool_add(pools, "rsi", symbol, day, done[0], done[1])
            ibs_exit = exit_rule(seg, entry_i, RSI_LIMIT, close_above_prior_high)
            done = _finish(seg, entry_i, ibs_exit, nifty)
            if done is not None:
                _pool_add(pools, "ibs", symbol, day, done[0], done[1])
            if entry_i < 1:
                continue
            soup_exit = exit_soup(seg, entry_i, seg.l[entry_i - 1])
            done = _finish(seg, entry_i, soup_exit, nifty)
            if done is not None:
                _pool_add(pools, "soup", symbol, day, done[0], done[1])


def scan_signals(symbol, segments, top200, top100, regimes, nifty, specs):
    """Signal on the close, buy the next open. The name must be liquid that day."""
    found = {}
    for spec in specs:
        found[spec["name"]] = []
    for seg in segments:
        n = len(seg.date)
        for i in range(n - 1):
            signal_day = seg.date[i]
            entry_i = i + 1
            entry_day = seg.date[entry_i]
            if entry_day < SWING_START or entry_day > SWING_END:
                continue
            if symbol not in top200.get(signal_day, ()):
                continue
            large = symbol in top100.get(signal_day, ())
            kind = regimes.get(entry_day)
            for spec in specs:
                if spec["kind"] == "rsi":
                    if not rsi_fires(seg, i, spec["rsi_max"], spec["down2"]):
                        continue
                    done = _finish(seg, entry_i, exit_rule(seg, entry_i, RSI_LIMIT, close_above_sma5), nifty)
                elif spec["kind"] == "ibs":
                    if not ibs_fires(seg, i, spec["ibs_max"]):
                        continue
                    done = _finish(
                        seg, entry_i, exit_rule(seg, entry_i, RSI_LIMIT, close_above_prior_high), nifty)
                elif spec["kind"] == "soup":
                    if not soup_fires(seg.l[i], seg.c[i], prior_of(seg, i, spec["n"])):
                        continue
                    done = _finish(seg, entry_i, exit_soup(seg, entry_i, seg.l[i]), nifty)
                else:
                    continue
                if done is None:
                    continue
                ret, mkt, hold = done
                found[spec["name"]].append(
                    make_trade(entry_day, symbol, ret, mkt, kind, large, hold))
    return found


def five_day_return(closes, prev_i):
    """Close at prev_i over the close five sessions earlier. Monday's close is not used."""
    if prev_i is None or prev_i < 5:
        return None
    base = closes[prev_i - 5]
    if not base > 0:
        return None
    return closes[prev_i] / base - 1.0


def week_allowed(above, require_above):
    """A filter that is off omits the week. It is not scored as zero."""
    if not require_above:
        return True
    return bool(above)


def pick_worst(eligible, k):
    """Smallest 5-day return first. A tie breaks on the symbol name."""
    ordered = sorted(eligible, key=lambda item: (item[0], item[1]))
    if k < 0:
        return []
    return ordered[:k]


def pick_random(eligible, k, rng):
    n = len(eligible)
    if n <= k:
        return list(eligible)
    chosen = []
    used = {}
    while len(chosen) < k:
        j = rng.randrange(n)
        if j in used:
            continue
        used[j] = True
        chosen.append(eligible[j])
    return chosen


def book_return(picks):
    """Equal-weight mean of delivery returns. Names that do not fit are left out."""
    rets = []
    for item in picks:
        value = net_return(item[2], item[3])
        if value is not None:
            rets.append(value)
    return h._mean(rets)


def nifty_above_prev(nifty):
    """Monday -> previous session's close is above the 200-day average through that close."""
    days = sorted(nifty)
    closes = []
    for day in days:
        closes.append(nifty[day]["close"])
    sma = ta.sma_series(closes, 200)
    out = {}
    for i, day in enumerate(days):
        if i == 0 or sma[i - 1] is None:
            out[day] = False
        else:
            out[day] = closes[i - 1] > sma[i - 1]
    return out


def eligible_monday(monday, nxt, ctx):
    """Names in Monday's top 200 with an open that day and the next Monday, same segment."""
    names = ctx["top200"].get(monday, ())
    by_name = ctx["by_name"]
    out = []
    for symbol in names:
        loc = by_name.get(symbol)
        if loc is None:
            continue
        entry = loc.get(monday)
        exit_loc = loc.get(nxt)
        if entry is None or exit_loc is None:
            continue
        seg, i_e = entry
        seg_x, i_x = exit_loc
        if seg is not seg_x or i_x <= i_e or i_e < 1:
            continue
        prev_i = i_e - 1
        ret5 = five_day_return(seg.c, prev_i)
        if ret5 is None:
            continue
        if not seg.o[i_e] > 0 or not seg_x.o[i_x] > 0:
            continue
        out.append((ret5, symbol, seg.o[i_e], seg_x.o[i_x]))
    return out


def monday_weeks(ctx, above):
    nifty = ctx["nifty"]
    days = []
    for day in nifty:
        if nifty[day].get("open", 0) > 0 and day <= SWING_END:
            days.append(day)
    days.sort()
    mondays = []
    for day in days:
        if day.weekday() == 0 and day >= SWING_START:
            mondays.append(day)
    weeks = []
    for i, monday in enumerate(mondays):
        if i + 1 >= len(mondays):
            break
        nxt = mondays[i + 1]
        if nxt > SWING_END:
            continue
        weeks.append({
            "monday": monday,
            "next": nxt,
            "eligible": eligible_monday(monday, nxt, ctx),
            "above": above.get(monday, False),
            "regime": ctx["regimes"].get(monday),
            "mkt": market_return(nifty, monday, nxt, True),
        })
    return weeks


def apply_book_random(trades, runs, seed, k):
    """Same Monday, same K, random members, same hold. The market return cancels."""
    trades.sort(key=lambda item: item["date"])
    for run_i in range(runs):
        rng = random.Random(seed + run_i)
        for trade in trades:
            eligible = trade.get("eligible") or []
            picked = trade.get("picks")
            if picked is None:
                picked = []
                trade["picks"] = picked
            if not eligible:
                picked.append(None)
                continue
            chosen = pick_random(eligible, k, rng)
            picked.append(book_return(chosen))
    for trade in trades:
        picks = []
        for value in trade.get("picks", []):
            if value is not None:
                picks.append(value)
        mean_r = h._mean(picks)
        if mean_r is None or trade.get("mkt") is None:
            trade["excess"] = None
        else:
            excess = (trade["ret"] - trade["mkt"]) - (mean_r - trade["mkt"])
            if abs(excess) < 1e-9:
                excess = 0.0
            trade["excess"] = excess
        trade.pop("picks", None)
        trade.pop("eligible", None)


def apply_trade_random(trades, pools, style, runs, seed):
    trades.sort(key=lambda item: (item["date"], item["symbol"]))
    by_symbol = pools.get(style, {})
    for run_i in range(runs):
        rng = random.Random(seed + run_i)
        for trade in trades:
            choices = by_symbol.get(trade["symbol"], {}).get(trade["month"]) or []
            picked = trade.get("picks")
            if picked is None:
                picked = []
                trade["picks"] = picked
            if not choices:
                picked.append(None)
                continue
            picked.append(choices[rng.randrange(len(choices))])
    for trade in trades:
        pairs = []
        for value in trade.get("picks", []):
            if value is not None:
                pairs.append(value)
        excess = adjusted_excess(trade["ret"], trade.get("mkt"), pairs)
        if excess is not None and abs(excess) < 1e-9:
            excess = 0.0
        trade["excess"] = excess
        trade.pop("picks", None)


def summarise_swing(name, trades):
    after = []
    days = set()
    hold = []
    yearly = {}
    buckets = {"up": [], "down": [], "sideways": [], "large": [], "early": [], "late": []}
    by_month = {}
    for trade in trades:
        after.append(trade["ret"])
        days.add(trade["date"])
        if trade.get("hold_days") is not None:
            hold.append(trade["hold_days"])
        year = trade["date"].year
        yearly.setdefault(year, []).append(trade["ret"])
        kind = trade.get("regime")
        if kind in ("up", "down", "sideways"):
            buckets[kind].append(trade["ret"])
        large_ret = trade.get("large_ret")
        if large_ret is not None:
            buckets["large"].append(large_ret)
        if 2005 <= year <= 2014:
            buckets["early"].append(trade["ret"])
        if 2015 <= year <= 2024:
            buckets["late"].append(trade["ret"])
        if trade.get("excess") is not None:
            key = (year, trade["date"].month)
            by_month.setdefault(key, []).append(trade["excess"])
    monthly = []
    for key in sorted(by_month):
        monthly.append(h._mean(by_month[key]))
    years = {}
    for year in sorted(yearly):
        years[year] = h._mean(yearly[year])
    return {
        "name": name,
        "trades": len(trades),
        "days": len(days),
        "avg": h._mean(after),
        "t": h.t_stat(monthly),
        "excess": h._mean([item["excess"] for item in trades if item.get("excess") is not None]),
        "early": h._mean(buckets["early"]),
        "late": h._mean(buckets["late"]),
        "up": h._mean(buckets["up"]),
        "down": h._mean(buckets["down"]),
        "sideways": h._mean(buckets["sideways"]),
        "large": h._mean(buckets["large"]),
        "yearly": years,
        "hold_days": h._mean(hold),
    }


def judge_swing(block, family):
    """Raw after-cost return for the averages. The t is market-adjusted excess."""
    reasons = []
    if block["avg"] is None or not block["avg"] > 0:
        reasons.append("avg return after costs %s is not above 0" % h._pct(block["avg"]))
    if block["t"] is None or not block["t"] > 3:
        reasons.append("t vs random %s is not above 3" % h._num(block["t"]))
    checks = (
        ("early", "2005-2014"),
        ("late", "2015-2024"),
        ("up", "up"),
        ("down", "down"),
        ("sideways", "sideways"),
        ("large", "large caps"),
    )
    for key, label in checks:
        if block[key] is None or not block[key] > 0:
            reasons.append("%s %s is not above 0" % (label, h._pct(block[key])))
    strong = 0
    for item in family:
        if item.get("t") is not None and item["t"] > 2:
            strong += 1
    if strong < 2:
        reasons.append("family variants with t above 2: %d of %d, need 2" % (strong, len(family)))
    return {"result": "PASS" if not reasons else "FAIL", "reasons": reasons}


def scale_bias(annual_pct, days):
    """Annual CAGR bias, scaled to a holding length. Nothing is subtracted with it."""
    if annual_pct is None or days is None:
        return None
    grown = (1.0 + annual_pct / 100.0) ** (float(days) / YEAR_DAYS) - 1.0
    return grown * 100.0


def bias_note(annual, scaled, days):
    if days is None:
        held = "n/a"
    else:
        held = "%.2f" % days
    return "survivorship bias %s a year, %s over %s holding days (not subtracted)" % (
        h._pct(annual), h._pct(scaled), held)


def large_flag(symbol, day, top100, index_trade):
    """The index book has no stock ranking, so every index trade counts as large."""
    if index_trade:
        return True
    return symbol in top100.get(day, ())


def measured_bias(root, log):
    """In-sample annual bias. final stays false, so 2025 is not opened."""
    from india.research import survivorship as sv
    emit = log or (lambda line: None)
    report = sv.run_window(root, sv.START, sv.END, False, 100, emit)
    return report.get("bias")


def run_swing(root, runs=h.RUNS, log=None, bias=None):
    """Attempt 14. Daily bars, 2005-2024. Pass `bias` to skip a fresh measurement."""
    emit = log or (lambda line: None)
    specs = batch14()
    emit("loading daily context through %s" % SWING_END.isoformat())
    ctx = h.load_context(root, start=SWING_START, end=SWING_END, log=emit, final=False)
    for symbol in ctx["loaded"]:
        attach_indicators(symbol["segments"])
    nifty_segs = lab.load_symbol(root, lab.NIFTY, end=SWING_END, final=False)
    attach_indicators(nifty_segs)
    trade_specs = []
    index_specs = []
    book_specs = []
    for spec in specs:
        if spec["kind"] == "reversal":
            book_specs.append(spec)
        elif spec.get("index"):
            index_specs.append(spec)
        else:
            trade_specs.append(spec)
    collected = {}
    for spec in specs:
        collected[spec["name"]] = []
    pools = {}
    emit("scanning swing signals")
    loaded = ctx["loaded"]
    for i, symbol in enumerate(loaded):
        name = symbol["name"]
        attach_ok = symbol["segments"]
        fill_pools(name, attach_ok, ctx["top200"], ctx["nifty"], pools)
        found = scan_signals(
            name, attach_ok, ctx["top200"], ctx["top100"], ctx["regimes"], ctx["nifty"], trade_specs)
        for spec_name, trades in found.items():
            collected[spec_name].extend(trades)
        if (i + 1) % 50 == 0:
            emit("  symbol %d/%d" % (i + 1, len(loaded)))
    emit("NIFTY IBS")
    nifty_universe = {}
    for seg in nifty_segs:
        for day in seg.date:
            nifty_universe[day] = set([lab.NIFTY])
    fill_pools(lab.NIFTY, nifty_segs, nifty_universe, ctx["nifty"], pools)
    found = scan_signals(
        lab.NIFTY, nifty_segs, nifty_universe, {}, ctx["regimes"], ctx["nifty"], index_specs)
    for spec_name, trades in found.items():
        for trade in trades:
            trade["large"] = True
            trade["large_ret"] = trade["ret"]
        collected[spec_name].extend(trades)
    emit("Monday reversal")
    above = nifty_above_prev(ctx["nifty"])
    weeks = monday_weeks(ctx, above)
    top100 = ctx["top100"]
    for spec in book_specs:
        for week in weeks:
            if not week_allowed(week["above"], spec["above"]):
                continue
            picks = pick_worst(week["eligible"], spec["k"])
            if not picks:
                continue
            ret = book_return(picks)
            if ret is None:
                continue
            large_names = top100.get(week["monday"], ())
            large_picks = []
            for item in picks:
                if item[1] in large_names:
                    large_picks.append(item)
            large_ret = book_return(large_picks) if large_picks else None
            hold = (week["next"] - week["monday"]).days
            trade = make_trade(
                week["monday"], BOOK, ret, week["mkt"], week["regime"], False, hold, large_ret)
            trade["eligible"] = week["eligible"]
            collected[spec["name"]].append(trade)
    if bias is None:
        emit("measuring survivorship bias")
        bias = measured_bias(root, emit)
    emit("survivorship bias %s a year" % h._pct(bias))
    blocks = []
    for index, spec in enumerate(specs):
        trades = collected[spec["name"]]
        seed = h.SEED + index * 1000
        emit("scoring %s (%d trades)" % (spec["name"], len(trades)))
        if spec["kind"] == "reversal":
            apply_book_random(trades, runs, seed, spec["k"])
        else:
            apply_trade_random(trades, pools, spec["pool"], runs, seed)
        block = summarise_swing(spec["name"], trades)
        block["kind"] = spec["kind"]
        block["index"] = bool(spec.get("index"))
        block["seed"] = seed
        block["runs"] = runs
        block["bias_year"] = bias
        block["bias_hold"] = scale_bias(bias, block["hold_days"])
        blocks.append(block)
    by_kind = {}
    for block in blocks:
        by_kind.setdefault(block["kind"], []).append(block)
    for block in blocks:
        block["verdict"] = judge_swing(block, by_kind[block["kind"]])
    return blocks


def gap_rules(stamp):
    """Attempt 13 rules. No measured result belongs in this text."""
    return "\n".join([
        "## Attempt 13",
        "",
        "Rules fixed on %s, before the run." % stamp,
        "",
        HYPOTHESIS_13 + ".",
        "",
        "Hypothesis: one of the three big-gap continuation variants clears the attempt "
        "12 pass mark on 2015-2024. The attempt 12 gap GO 3 rule entered on the first "
        "close beyond the opening range and lost to a random bar on the same day. "
        "This attempt enters only at the 09:30 close, in the gap's direction, and it "
        "must beat a non-gap day as well as a random bar. The full pass mark applies. "
        "It is not lowered because the idea came from the earlier sample.",
        "",
        "Common rules. Bar labels are the bar end, same as attempt 12. A session is "
        "used only when every bar from 09:15 to 15:10 is present. The gap is the "
        "09:20 bar's open divided by the previous session's daily close, minus 1, "
        "and the previous close is the previous daily row in the same segment. A "
        "threshold uses >=, so a gap of exactly 3% or exactly 4% counts. Direction "
        "is long when the gap is positive and short when it is negative. A gap of "
        "zero does not trade. The entry is the 09:30 bar's close, and only when that "
        "close is still strictly beyond the previous close in the gap's direction. "
        "The stop is the opposite extreme of the bars ending 09:20, 09:25 and 09:30: "
        "the low for a long, the high for a short. The entry bar is inside that "
        "range, and it is not scanned for the stop. Exit at the 15:10 close. There "
        "is no target.",
        "",
        "R is |entry - stop|. A trade risks Rs 2,000 and is capped at Rs 5,00,000 "
        "of entry value, in whole shares. One tick of slippage, from "
        "nse_market.tick_for, is charged on the entry and on the exit. Costs are "
        "the india/costs.py intraday schedule. R before is after the tick and "
        "before charges. R after is after the tick and the charges. A later bar "
        "that opens through the stop fills at the open. Otherwise a touch fills at "
        "the stop.",
        "",
        "Universe: each day, the 200 symbols with the highest average close times "
        "volume over the previous 20 sessions, and those 20 sessions must sit in "
        "one segment. Large caps are the top 100 by that same average. Market type "
        "is india/research/regime.py, known before the open. The window is "
        "2015-01-01 through 2024-12-31. Dates from 2025-01-01 on are not requested.",
        "",
        "Volume variant. The opening volume is the sum of volume on bars ending "
        "09:20 through 09:30. It must be at least 2 times the average opening "
        "volume of the previous 10 usable sessions in the same segment. Exactly 2 "
        "times passes. Fewer than 10 prior sessions in the segment skips the day. "
        "A new segment starts the count again.",
        "",
        "Two baselines, 100 seeded runs. The same-day baseline keeps the symbol, "
        "the day, the direction and the stop distance, and enters at a random bar "
        "ending 09:30 through 14:30. Its seed is 20261106 + variant index * 1000 + "
        "the run index. The non-gap baseline uses the same symbol on a random "
        "usable day in the same calendar month whose absolute gap is strictly "
        "below 0.5%. Exactly 0.5% is not eligible. The entry is that day's 09:30 "
        "close, the direction is random, the stop is that day's own 09:15-09:30 "
        "extreme, and the exit is 15:10. Its seed is the same-day seed plus 500. "
        "A month with no non-gap day leaves that trade out of the non-gap t. The "
        "trade still counts in the average R. Excess R is R after costs minus the "
        "mean of the random Rs. The t-statistic is the one-sample t of the mean "
        "excess in each calendar month. Both excesses and both t values are "
        "reported. The pass mark uses the non-gap t.",
        "",
        "Pass mark, the same as attempt 12, fixed before this run: average R after "
        "costs and slippage at least +0.10; at least 300 trades on at least 100 "
        "distinct days; t versus the non-gap baseline above 3; average R after "
        "costs above 0 in 2015-2019 and in 2020-2024; above 0 on up, down, and "
        "sideways days; above 0 in large caps; and at least 2 of the 3 variants "
        "have non-gap t above 2. A value on a stated boundary passes. An empty "
        "bucket does not.",
        "",
        "Variants. (a) gap cont 3, absolute gap at least 3%. (b) gap cont 4, "
        "absolute gap at least 4%. (c) gap cont 3 vol, the 3% rule plus the "
        "opening-volume multiple. A day can qualify for more than one variant. "
        "Each variant is scored on its own trades.",
    ])


def swing_rules(stamp):
    """Attempt 14 rules. No measured result belongs in this text."""
    return "\n".join([
        "## Attempt 14",
        "",
        "Rules fixed on %s, before the run." % stamp,
        "",
        "Hypothesis: one short-swing family clears the pass mark below on "
        "2005-2024. Signals use the close. The buy is the next session's open, "
        "in the same segment. Every signal is its own round trip, including one "
        "that overlaps another open trade. Long only. Delivery costs are "
        "signal_lab.delivery on a Rs 1,00,000 notional, in whole shares. A price "
        "that does not fit one share is skipped. Dividends are excluded.",
        "",
        "Universe for the stock rules: the 200 names with the highest average "
        "close times volume over the 60 sessions before the signal day, one "
        "segment only. Large caps are the top 100 by that average on the signal "
        "day. A random entry instead requires the name to be in the top 200 on "
        "the entry day, because that is what is known at the open, and the "
        "signal condition is not required. Market type is india/research/regime.py "
        "on the entry date, from earlier NIFTY closes only. The window is "
        "2005-01-01 through 2024-12-31. An exit that would need a session after "
        "2024-12-31 is skipped. Dates from 2025-01-01 on are not requested.",
        "",
        "RSI(2). Wilder RSI from ta.rsi_series, period 2. SMA200 and SMA5 are "
        "ta.sma_series on the same segment. Buy when the close is strictly above "
        "SMA200 and RSI(2) is strictly below the threshold. Exit at the next "
        "open after a close strictly above that session's SMA5. The entry "
        "session's close can be the trigger, which sells at the following open. "
        "If no close does that, sell at the open five sessions after the entry "
        "session. Variants: rsi2 < 5; rsi2 < 10; rsi2 < 10 down2, which also "
        "requires the signal close and the close before it to each be strictly "
        "below the close before them.",
        "",
        "IBS. IBS is (close - low) / (high - low). A bar with high equal to low "
        "has no IBS and no signal. Buy when the close is strictly above SMA200 "
        "and IBS is strictly below the threshold. Exit at the next open after a "
        "close strictly above the prior session's high, or at the open five "
        "sessions after the entry. Variants: ibs < 0.2; ibs < 0.1; ibs < 0.2 "
        "nifty. The third trades the NIFTY 50 index itself, price only, no "
        "futures and no futures charges. The same delivery cost and Rs 1,00,000 "
        "notional are applied to the index points, as a NIFTYBEES-like cash "
        "book. Its large-cap average is its own average return. Its random "
        "entries are other NIFTY sessions in the same month.",
        "",
        "Turtle soup. The prior low is the lowest low of the N sessions before "
        "the signal day, today not included. Buy when today's low is strictly "
        "below that prior low and today's close is strictly back above it. The "
        "stop is the signal day's low. The next open must be strictly above that "
        "low, otherwise the trade is skipped. The target is the entry plus 2 "
        "times (entry - stop). On the entry day and the two following sessions, "
        "a gap through the stop fills at the open, a low through the stop fills "
        "at the stop, and a high through the target fills at the target. The "
        "stop is taken before the target on the same day. If neither is hit, "
        "sell at the open three sessions after the entry. Variants: soup 20, "
        "soup 10, soup 55.",
        "",
        "Short-term reversal, a portfolio. Every Monday, rank the top 200 by the "
        "5-session return ending at the previous session: that close divided by "
        "the close five sessions before it, minus 1. Monday's own close is not "
        "in the rank. Buy the K worst at Monday's open, equal weight, each name "
        "sized by delivery() at Rs 1,00,000. Sell at the next Monday's open. "
        "The next Monday is the next session that falls on a Monday. A name "
        "must have both opens in the same segment. When fewer than K names "
        "qualify, those names are the book. A week with no name is skipped. "
        "Each week is its own round trip: the book is sold and, if it qualifies "
        "again, bought again, so costs apply both times. Variants: rev K10; "
        "rev K20; rev K10 above200, which is taken only when the previous "
        "session's NIFTY close is strictly above the 200-day average of NIFTY "
        "closes through that previous session. This is a level test, not the "
        "regime slope. When the filter fails, the week is omitted, not scored "
        "as zero. The average return is the mean of the weekly book returns. "
        "The large-cap figure is the mean of those weekly returns computed from "
        "only the picked names that were in the top 100 that Monday. A week "
        "with no large-cap name stays out of that bucket.",
        "",
        "Random baseline, 100 seeded runs, seed 20261106 + variant index * 1000 "
        "+ the run index. For a stock or index trade, each run picks a random "
        "eligible entry in the same calendar month and applies that variant's "
        "own exit. A turtle draw whose previous-day low is not below the open "
        "is dropped from the mean. For the Monday book, each run picks K random "
        "eligible names that Monday and holds them to the same next Monday. "
        "The market adjustment is the NIFTY price return over the same window: "
        "entry open to the exit open when the exit is an open, and entry open "
        "to the NIFTY close of the exit day when the exit is a stop or a target. "
        "Excess is (trade return - NIFTY return) minus the mean of that figure "
        "on the random entries. On the Monday book the window matches, so NIFTY "
        "cancels and the excess is the book minus the random book. The "
        "t-statistic is the one-sample t of the mean excess in each calendar "
        "month of the entry date.",
        "",
        "Pass mark, fixed before this run: average raw return after costs above "
        "0; t versus random above 3, on the market-adjusted excess; raw return "
        "above 0 in 2005-2014 and in 2015-2024; above 0 on up, down, and "
        "sideways entries; above 0 in large caps; and at least 2 of the 3 "
        "variants in the family have t above 2. A value on a stated boundary "
        "passes where the word is 'at least'. The averages here are strict. An "
        "empty bucket does not. The survivorship bias is not subtracted. Next "
        "to each result, the measured annual survivorship bias (random K=30 "
        "CAGR minus the NIFTY 200 price CAGR, from survivorship.py on this same "
        "2005-2024 window) is scaled to the variant's average holding length "
        "in calendar days: (1 + annual) ** (days / 365.25) - 1. The scaled "
        "figure is printed and is not used in the pass test.",
        "",
        "In the experiments table, the two return columns are the average "
        "percent return after costs and the market-adjusted t. The printed "
        "summary is the long table.",
    ])


def _years(block, fmt):
    parts = []
    for year in sorted(block["yearly"]):
        parts.append("%d %s" % (year, fmt(block["yearly"][year])))
    if not parts:
        return "n/a"
    return ", ".join(parts)


def gap_table(blocks):
    lines = [
        "variant | trades | days | win | R before | R after | excess same | t same | "
        "excess non-gap | t non-gap | 2015-19 | 2020-24 | up | down | sideways | large | result",
    ]
    for block in blocks:
        lines.append(
            "%s | %s | %d | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s" % (
                block["name"], format(block["trades"], ",d"), block["days"],
                _win(block["win"]),
                h._r(block["avg_before"]), h._r(block["avg_after"]),
                h._r(block.get("excess_same")), h._num(block.get("t_same")),
                h._r(block.get("excess_ng")), h._num(block["t"]),
                h._r(block["early"]), h._r(block["late"]),
                h._r(block["up"]), h._r(block["down"]), h._r(block["sideways"]),
                h._r(block["large"]), block["verdict"]["result"]))
    return lines


def _win(value):
    if value is None:
        return "n/a"
    return "%.1f%%" % (100.0 * value)


def swing_table(blocks):
    lines = [
        "variant | trades | days | avg return | excess | t | 2005-14 | 2015-24 | "
        "up | down | sideways | large | hold days | bias over hold | result",
    ]
    for block in blocks:
        held = block.get("hold_days")
        if held is None:
            held_txt = "n/a"
        else:
            held_txt = "%.2f" % held
        lines.append(
            "%s | %s | %d | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s" % (
                block["name"], format(block["trades"], ",d"), block["days"],
                h._pct(block["avg"]), h._pct(block.get("excess")), h._num(block["t"]),
                h._pct(block["early"]), h._pct(block["late"]),
                h._pct(block["up"]), h._pct(block["down"]), h._pct(block["sideways"]),
                h._pct(block["large"]), held_txt, h._pct(block.get("bias_hold")),
                block["verdict"]["result"]))
    return lines


def gap_report(stamp, blocks):
    lines = [gap_rules(stamp), "", "Results."]
    lines.extend(gap_table(blocks))
    lines.append("")
    passed = 0
    for block in blocks:
        verdict = block["verdict"]
        if verdict["result"] == "PASS":
            passed += 1
            lines.append("%s PASS." % block["name"])
        else:
            lines.append("%s FAIL: %s" % (block["name"], "; ".join(verdict["reasons"])))
        lines.append("  years: %s" % _years(block, h._r))
    lines.append("")
    lines.append("Variants that pass: %d of %d." % (passed, len(blocks)))
    return "\n".join(lines).rstrip() + "\n"


def swing_report(stamp, blocks):
    lines = [swing_rules(stamp), "", "Results."]
    lines.extend(swing_table(blocks))
    lines.append("")
    passed = 0
    for block in blocks:
        verdict = block["verdict"]
        note = bias_note(block.get("bias_year"), block.get("bias_hold"), block.get("hold_days"))
        if verdict["result"] == "PASS":
            passed += 1
            lines.append("%s PASS. %s." % (block["name"], note))
        else:
            lines.append("%s FAIL: %s. %s." % (
                block["name"], "; ".join(verdict["reasons"]), note))
        lines.append("  years: %s" % _years(block, h._pct))
    lines.append("")
    lines.append("The survivorship figure is printed beside each result and is not subtracted.")
    lines.append("Variants that pass: %d of %d." % (passed, len(blocks)))
    return "\n".join(lines).rstrip() + "\n"


def gap_rows(stamp, blocks):
    rows = []
    for block in blocks:
        rows.append("| 13 | %s | %s | %s | %s | %s | %s | %s | %s |" % (
            stamp,
            "%s clears the attempt 13 intraday pass mark." % block["name"],
            "big-gap continuation, costs and 1 tick, Rs 2,000 risk, Rs 5,00,000 cap",
            "top 200 by prior 20-session turnover, 5-minute, 2015-01-01 to 2024-12-31",
            format(block["trades"], ",d"),
            h._r(block["avg_before"]),
            h._r(block["avg_after"]),
            block["verdict"]["result"]))
    return rows


def swing_rows(stamp, blocks):
    rows = []
    for block in blocks:
        if block["kind"] == "reversal":
            universe = "top 200 by prior 60-session turnover, Monday book, 2005-01-01 to 2024-12-31"
        elif block.get("index"):
            universe = "NIFTY 50 daily price, delivery costs, Rs 1,00,000, 2005-01-01 to 2024-12-31"
        else:
            universe = "top 200 by prior 60-session turnover, daily, 2005-01-01 to 2024-12-31"
        rows.append("| 14 | %s | %s | %s | %s | %s | %s | %s | %s |" % (
            stamp,
            "%s clears the attempt 14 swing pass mark." % block["name"],
            "short swing, delivery costs, Rs 1,00,000, next open",
            universe,
            format(block["trades"], ",d"),
            h._pct(block["avg"]),
            h._num(block["t"]),
            block["verdict"]["result"]))
    return rows


def install_attempt(path, number, section, rows):
    """Insert or replace one attempt. Stop at the next heading so later sections stay."""
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    prefix = "| %d |" % number
    kept = []
    for line in text.splitlines():
        if line.startswith(prefix):
            continue
        kept.append(line)
    text = "\n".join(kept)
    if not text.endswith("\n"):
        text += "\n"
    heading = "\n## Attempt %d\n" % number
    block = "\n" + section.rstrip() + "\n\n"
    start = text.find(heading)
    if start != -1:
        nxt = text.find("\n## ", start + 1)
        end = nxt if nxt != -1 else len(text)
        text = text[:start] + block + text[end:]
    else:
        forward = text.find("\n## Forward test\n")
        if forward == -1:
            text = text.rstrip() + "\n" + block
        else:
            text = text[:forward] + block + text[forward:]
    if rows:
        anchor = "| %d |" % (number - 1)
        at = text.rfind("\n" + anchor)
        if at == -1 and text.startswith(anchor):
            at = 0
        elif at != -1:
            at += 1
        if at != -1:
            line_end = text.find("\n", at)
            if line_end == -1:
                line_end = len(text)
            text = text[:line_end] + "\n" + "\n".join(rows) + text[line_end:]
    if not text.endswith("\n"):
        text += "\n"
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


def _emit_verdicts(blocks, emit, bias=False):
    for block in blocks:
        verdict = block["verdict"]
        if verdict["result"] == "PASS":
            text = "%s PASS" % block["name"]
        else:
            text = "%s FAIL: %s" % (block["name"], "; ".join(verdict["reasons"]))
        if bias:
            text = "%s. %s" % (text, bias_note(
                block.get("bias_year"), block.get("bias_hold"), block.get("hold_days")))
        emit(text)


def main(argv=None, log=None):
    import argparse
    parser = argparse.ArgumentParser(description="Attempts 13 and 14. Nothing is placed.")
    parser.add_argument("--root", default=os.path.join("data", "kite"))
    parser.add_argument("--experiments", default=h.EXPERIMENTS)
    parser.add_argument("--runs", type=int, default=h.RUNS)
    args = parser.parse_args(argv)
    emit = log or (lambda line: print(line, flush=True))
    stamp = datetime.date.today().isoformat()
    install_attempt(args.experiments, 13, gap_rules(stamp), [])
    install_attempt(args.experiments, 14, swing_rules(stamp), [])
    emit("rules for attempts 13 and 14 written to %s before the run" % args.experiments)
    blocks13 = run_gap(args.root, runs=args.runs, log=emit)
    install_attempt(args.experiments, 13, gap_report(stamp, blocks13), gap_rows(stamp, blocks13))
    emit("Attempt 13")
    for line in gap_table(blocks13):
        emit(line)
    emit("")
    _emit_verdicts(blocks13, emit)
    blocks14 = run_swing(args.root, runs=args.runs, log=emit)
    install_attempt(
        args.experiments, 14, swing_report(stamp, blocks14), swing_rows(stamp, blocks14))
    emit("Attempt 14")
    for line in swing_table(blocks14):
        emit(line)
    emit("")
    _emit_verdicts(blocks14, emit, bias=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
