#!/usr/bin/env python3
"""Robustness of the four attempt-9 candidates. Nothing is placed.

The trade is still decided at the close and entered at the next open. Costs are
the delivery schedule in signal_lab.py. Window 2005-01-01 through 2024-12-31.
Dates from 2025 on are not requested.

    python3 india/research/robustness.py
"""

import datetime
import os
import random
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from india.research import signal_lab as lab
from india.research import ta

START = lab.START
END = lab.END
WARMUP = lab.WARMUP
SEED = lab.RANDOM_SEED
CAPITAL = 1000000.0
SLOTS = 10
NOTIONAL = lab.NOTIONAL
NEIGHBOUR_NEED = 2
EXPERIMENTS = lab.EXPERIMENTS
YEAR_DAYS = 365.25


def candidates():
    """Four candidates. Neighbours change one parameter at a time."""
    return [
        {
            "name": "20d-high / sma20-close",
            "base": _spec("20d-high / sma20-close", "20d-high", "sma", 20, None, True),
            "neighbours": [
                _spec("15d-high / sma20-close", None, "sma", 20, None, False, entry="high", high_n=15),
                _spec("30d-high / sma20-close", None, "sma", 20, None, False, entry="high", high_n=30),
                _spec("20d-high / sma10-close", None, "sma", 10, None, False, entry="high", high_n=20),
                _spec("20d-high / sma30-close", None, "sma", 30, None, False, entry="high", high_n=20),
            ],
        },
        {
            "name": "engulf-low / hold-20",
            "base": _spec("engulf-low / hold-20", "engulf-low", "hold", None, 20, True),
            "neighbours": [
                _spec("engulf-10 / hold-20", None, "hold", None, 20, False, entry="engulf", low_n=10),
                _spec("engulf-30 / hold-20", None, "hold", None, 20, False, entry="engulf", low_n=30),
                _spec("engulf-20 / hold-15", None, "hold", None, 15, False, entry="engulf", low_n=20),
                _spec("engulf-20 / hold-30", None, "hold", None, 30, False, entry="engulf", low_n=20),
            ],
        },
        {
            "name": "bb-squeeze / sma20-close",
            "base": _spec("bb-squeeze / sma20-close", "bb-squeeze", "sma", 20, None, True),
            "neighbours": [
                _spec("squeeze-63 / sma20-close", None, "sma", 20, None, False, entry="squeeze", width_n=63),
                _spec("squeeze-252 / sma20-close", None, "sma", 20, None, False, entry="squeeze", width_n=252),
                _spec("squeeze-126 / sma10-close", None, "sma", 10, None, False, entry="squeeze", width_n=126),
                _spec("squeeze-126 / sma30-close", None, "sma", 30, None, False, entry="squeeze", width_n=126),
            ],
        },
        {
            "name": "sma20-touch / sma20-close",
            "base": _spec("sma20-touch / sma20-close", "sma20-touch", "sma", 20, None, True),
            "neighbours": [
                _spec("sma10-touch / sma10-close", None, "sma", 10, None, False, entry="touch", touch_n=10),
                _spec("sma50-touch / sma50-close", None, "sma", 50, None, False, entry="touch", touch_n=50),
            ],
        },
    ]


def _spec(name, base, exit_kind, exit_n, hold_n, portfolio, entry=None, high_n=None,
          low_n=None, width_n=None, touch_n=None):
    return {
        "name": name,
        "base": base,
        "entry": entry,
        "exit": exit_kind,
        "exit_n": exit_n,
        "hold_n": hold_n,
        "high_n": high_n,
        "low_n": low_n,
        "width_n": width_n,
        "touch_n": touch_n,
        "portfolio": portfolio,
    }


def prepare(seg):
    """Extra windows the neighbours need. The base series are already on the segment."""
    seg.sma10 = ta.sma_series(seg.c, 10)
    seg.sma30 = ta.sma_series(seg.c, 30)
    seg.high15 = ta.prior_high_series(seg.h, 15)
    seg.high30 = ta.prior_high_series(seg.h, 30)
    seg.low10 = ta.prior_low_series(seg.l, 10)
    seg.low30 = ta.prior_low_series(seg.l, 30)
    seg.wmin63 = ta.trailing_is_min(seg.width, 63)
    seg.wmin252 = ta.trailing_is_min(seg.width, 252)
    seg.idx = {}
    for i, day in enumerate(seg.date):
        seg.idx[day] = i


def _sma(seg, n):
    if n == 10:
        return seg.sma10
    if n == 20:
        return seg.sma20
    if n == 30:
        return seg.sma30
    if n == 50:
        return seg.sma50
    if n == 200:
        return seg.sma200
    raise ValueError("sma %s" % n)


def _prior_high(seg, n):
    if n == 15:
        return seg.high15
    if n == 20:
        return seg.high20
    if n == 30:
        return seg.high30
    raise ValueError("high %s" % n)


def _prior_low(seg, n):
    if n == 10:
        return seg.low10
    if n == 20:
        return seg.low20
    if n == 30:
        return seg.low30
    raise ValueError("low %s" % n)


def _width_flags(seg, n):
    if n == 63:
        return seg.wmin63
    if n == 126:
        return seg.width_min
    if n == 252:
        return seg.wmin252
    raise ValueError("width %s" % n)


def signal_fires(seg, i, spec):
    """True when the signal is known at the close of bar i."""
    if spec.get("base"):
        return lab.entry_hit(seg, i, spec["base"])
    kind = spec["entry"]
    if kind == "high":
        level = _prior_high(seg, spec["high_n"])[i]
        return level is not None and seg.c[i] > level
    if kind == "engulf":
        if i < 1:
            return False
        level = _prior_low(seg, spec["low_n"])[i]
        if level is None:
            return False
        return (seg.l[i] <= level and
                ta.bullish_engulfing(seg.o[i - 1], seg.c[i - 1], seg.o[i], seg.c[i]))
    if kind == "squeeze":
        upper = seg.upper[i]
        if upper is None or not seg.c[i] > upper:
            return False
        flags = _width_flags(seg, spec["width_n"])
        for k in range(lab.WIDTH_RECENT):
            j = i - k
            if j < 0:
                break
            if flags[j]:
                return True
        return False
    if kind == "touch":
        sma = _sma(seg, spec["touch_n"])[i]
        slow = seg.sma200[i]
        if sma is None or slow is None:
            return False
        return seg.c[i] > slow and seg.l[i] <= sma and seg.c[i] > sma
    raise ValueError("entry %r" % kind)


def resolve_exit(seg, entry_i, last, spec):
    """(exit index, fill, at_open) inside this segment."""
    if spec["exit"] == "hold":
        return lab.exit_hold(seg, entry_i, last, spec["hold_n"])
    if spec["exit_n"] == 20:
        return lab.exit_sma20(seg, entry_i, last)
    return _exit_below(seg, entry_i, last, _sma(seg, spec["exit_n"]))


def _exit_below(seg, entry_i, last, sma):
    for j in range(entry_i, last + 1):
        level = sma[j]
        if level is None or not seg.c[j] < level:
            continue
        if j + 1 <= last:
            return j + 1, seg.o[j + 1], True
        return j, seg.c[j], False
    return last, seg.c[last], False


def turnover_before(seg, entry_i, n=lab.TURNOVER_N):
    """Average close*volume of the n sessions before the entry. Known at the open."""
    if entry_i < n:
        return None
    total = 0.0
    for j in range(entry_i - n, entry_i):
        total += seg.c[j] * seg.v[j]
    return total / float(n)


def _trade(symbol, sym_i, seg, seg_i, entry_i, found):
    exit_i, fill, at_open = found
    entry = seg.o[entry_i]
    money = lab.delivery(entry, fill)
    if money is None:
        return None
    entry_day = seg.date[entry_i]
    return {
        "name": symbol,
        "sym": sym_i,
        "seg_i": seg_i,
        "seg": seg,
        "entry_i": entry_i,
        "exit_i": exit_i,
        "entry_date": entry_day,
        "exit_date": seg.date[exit_i],
        "entry": entry,
        "fill": fill,
        "at_open": at_open,
        "pct": money[0],
        "month": (entry_day.year, entry_day.month),
        "turnover": turnover_before(seg, entry_i),
    }


def _eligible(seg, symbol, entry_i, universe, warmup, start, end):
    signal_i = entry_i - 1
    if signal_i < warmup:
        return False
    entry_day = seg.date[entry_i]
    if entry_day < start or entry_day > end:
        return False
    members = universe.get(seg.date[signal_i])
    if not members or symbol not in members:
        return False
    opened = seg.o[entry_i]
    if not opened > 0 or int(NOTIONAL // opened) < 1:
        return False
    return True


def scan(loaded, universe, specs, warmup, start, end):
    """Eligible random pools, thinned trades, and raw signals for portfolio specs."""
    pools = {}
    grouped = [dict() for _spec in specs]
    raw = [[] for _spec in specs]
    for sym_i, symbol in enumerate(loaded):
        for seg_i, seg in enumerate(symbol["segments"]):
            last = len(seg.date) - 1
            if last < 1:
                continue
            buckets = [[] for _spec in specs]
            for entry_i in range(1, last + 1):
                if not _eligible(seg, symbol["name"], entry_i, universe, warmup, start, end):
                    continue
                entry_day = seg.date[entry_i]
                pools.setdefault((entry_day.year, entry_day.month), []).append((sym_i, seg_i, entry_i))
                signal_i = entry_i - 1
                for s_i, spec in enumerate(specs):
                    if not signal_fires(seg, signal_i, spec):
                        continue
                    found = resolve_exit(seg, entry_i, last, spec)
                    if found is None:
                        continue
                    trade = _trade(symbol["name"], sym_i, seg, seg_i, entry_i, found)
                    if trade is None:
                        continue
                    buckets[s_i].append(trade)
                    if spec["portfolio"]:
                        raw[s_i].append(trade)
            for s_i, bucket in enumerate(buckets):
                if bucket:
                    grouped[s_i][(sym_i, seg_i)] = bucket
    thinned = [_thin(group) for group in grouped]
    return pools, thinned, raw


def _thin(grouped):
    out = []
    for key in grouped:
        bucket = grouped[key]
        hits = [(trade["entry_i"], trade["exit_i"]) for trade in bucket]
        keep = set(lab.take_one_at_a_time(hits))
        for trade in bucket:
            if trade["entry_i"] in keep:
                out.append(trade)
    out.sort(key=lambda trade: (trade["entry_date"], trade["name"]))
    return out


def load_nifty(root, end):
    """date -> open, close, segment id. A return that would cross a break is refused."""
    segments = lab.load_symbol(root, lab.NIFTY, end=end)
    by_date = {}
    for seg_i, seg in enumerate(segments):
        for i, day in enumerate(seg.date):
            by_date[day] = {"open": seg.o[i], "close": seg.c[i], "seg": seg_i}
    return by_date


def nifty_return(nifty, entry_date, exit_date, at_open, cache):
    key = (entry_date.toordinal(), exit_date.toordinal(), at_open)
    if key in cache:
        return cache[key]
    start = nifty.get(entry_date)
    stop = nifty.get(exit_date)
    value = None
    if start is not None and stop is not None and start["seg"] == stop["seg"] and start["open"] > 0:
        end_px = stop["open"] if at_open else stop["close"]
        if end_px > 0:
            value = (end_px - start["open"]) / start["open"] * 100.0
    cache[key] = value
    return value


def _random_leg(pool, loaded, spec, nifty, cache, rng, tries=8):
    n = len(pool)
    if n < 1:
        return None
    for _try in range(tries):
        sym_i, seg_i, entry_i = pool[rng.randrange(n)]
        seg = loaded[sym_i]["segments"][seg_i]
        found = resolve_exit(seg, entry_i, len(seg.date) - 1, spec)
        if found is None:
            continue
        exit_i, fill, at_open = found
        money = lab.delivery(seg.o[entry_i], fill)
        if money is None:
            continue
        nret = nifty_return(nifty, seg.date[entry_i], seg.date[exit_i], at_open, cache)
        if nret is None:
            continue
        return money[0], nret
    return None


def build_pairs(trades, pools, loaded, spec, nifty, cache, rng):
    """(month, signal excess minus random excess) for each trade that can be matched."""
    pairs = []
    for trade in trades:
        pool = pools.get(trade["month"])
        if not pool:
            continue
        n_s = nifty_return(nifty, trade["entry_date"], trade["exit_date"], trade["at_open"], cache)
        if n_s is None:
            continue
        sampled = _random_leg(pool, loaded, spec, nifty, cache, rng)
        if sampled is None:
            continue
        random_pct, n_r = sampled
        diff = (trade["pct"] - n_s) - (random_pct - n_r)
        pairs.append((trade["month"], diff))
    return pairs


def t_stat(values):
    """One-sample t of a list of monthly averages. Sample standard deviation."""
    n = len(values)
    if n < 2:
        return None
    mean = sum(values) / float(n)
    var = 0.0
    for value in values:
        var += (value - mean) ** 2
    var /= float(n - 1)
    if var == 0.0:
        if mean > 0:
            return float("inf")
        if mean < 0:
            return float("-inf")
        return 0.0
    return mean / ((var ** 0.5) / (n ** 0.5))


def cluster_stats(pairs):
    """Trade-level mean, and a t-statistic of the per-month means."""
    if not pairs:
        return {"excess": None, "t": None, "pairs": 0, "months": 0}
    total = 0.0
    buckets = {}
    for month, diff in pairs:
        total += diff
        buckets.setdefault(month, []).append(diff)
    monthly = []
    for month in buckets:
        vals = buckets[month]
        monthly.append(sum(vals) / float(len(vals)))
    return {
        "excess": total / float(len(pairs)),
        "t": t_stat(monthly),
        "pairs": len(pairs),
        "months": len(monthly),
    }


def split_decades(pairs):
    early = [pair for pair in pairs if pair[0][0] <= 2014]
    late = [pair for pair in pairs if pair[0][0] >= 2015]
    return cluster_stats(early), cluster_stats(late)


def neighbour_ok(stats):
    return (stats["excess"] is not None and stats["excess"] > 0 and
            stats["t"] is not None and stats["t"] > 2)


def legs(entry, exit_px):
    """(shares, buy-side costs, net rupees) for a position sized at NOTIONAL."""
    if entry <= 0 or exit_px <= 0:
        return None
    shares = int(NOTIONAL // entry)
    if shares < 1:
        return None
    buy = entry * shares
    sell = exit_px * shares

    def side(value, buying):
        stt = value * lab.STT_PCT / 100.0
        exchange = value * lab.EXCHANGE_PCT / 100.0
        sebi = value * lab.SEBI_PCT / 100.0
        stamp = value * lab.STAMP_PCT / 100.0 if buying else 0.0
        gst = (exchange + sebi) * lab.GST_PCT / 100.0
        dp = 0.0 if buying else lab.DP_CHARGE
        return stt + exchange + sebi + stamp + gst + dp

    buy_cost = side(buy, True)
    net = sell - buy - buy_cost - side(sell, False)
    return shares, buy_cost, net


def curve_stats(dates, equity, capital):
    """CAGR in percent, max drawdown in percent (negative), and the worst calendar year."""
    if not dates or not capital > 0:
        return {"cagr": None, "max_dd": None, "worst_year": None, "final": capital}
    final = equity[-1]
    days = (dates[-1] - dates[0]).days
    if days <= 0 or not final > 0:
        cagr = None
    else:
        years = days / YEAR_DAYS
        cagr = ((final / float(capital)) ** (1.0 / years) - 1.0) * 100.0
    peak = float(capital)
    max_dd = 0.0
    for value in [float(capital)] + [float(item) for item in equity]:
        if value > peak:
            peak = value
        if peak > 0:
            dd = (value - peak) / peak * 100.0
            if dd < max_dd:
                max_dd = dd
    year_end = {}
    for day, value in zip(dates, equity):
        year_end[day.year] = value
    worst = None
    prev = float(capital)
    for year in range(min(year_end), max(year_end) + 1):
        if year not in year_end:
            continue
        value = year_end[year]
        if prev > 0:
            ret = (value / prev - 1.0) * 100.0
            if worst is None or ret < worst:
                worst = ret
        prev = value
    return {"cagr": cagr, "max_dd": max_dd, "worst_year": worst, "final": final}


def nifty_buy_hold(calendar, nifty, capital):
    """Price path of NIFTY 50. The first close is the buy. Dividends are not in the file."""
    base = None
    last = None
    equity = []
    for day in calendar:
        bar = nifty.get(day)
        if bar is not None and bar["close"] > 0:
            last = bar["close"]
            if base is None:
                base = last
        if base is None or last is None:
            equity.append(capital)
        else:
            equity.append(capital * last / base)
    return curve_stats(calendar, equity, capital)


def simulate(signals, calendar, capital=CAPITAL, slots=SLOTS, notional=NOTIONAL):
    """Ten slots, highest prior turnover first. Cash earns 0. One position per symbol."""
    by_day = {}
    for trade in signals:
        by_day.setdefault(trade["entry_date"], []).append(trade)
    for day in by_day:
        by_day[day].sort(key=lambda trade: (-(trade["turnover"] if trade["turnover"] is not None else -1.0),
                                            trade["name"]))
    open_pos = {}
    cash = float(capital)
    equity = []
    taken = []
    for day in calendar:
        exited = set()
        for name in list(open_pos):
            pos = open_pos[name]
            if pos["exit_date"] == day and pos["at_open"]:
                cash += notional + pos["net"]
                del open_pos[name]
                exited.add(name)
        free = slots - len(open_pos)
        for trade in by_day.get(day, []):
            if free <= 0 or cash < notional:
                break
            if trade["name"] in open_pos or trade["name"] in exited:
                continue
            parts = legs(trade["entry"], trade["fill"])
            if parts is None:
                continue
            shares, buy_cost, net = parts
            cash -= notional
            open_pos[trade["name"]] = {
                "seg": trade["seg"],
                "entry": trade["entry"],
                "exit_date": trade["exit_date"],
                "at_open": trade["at_open"],
                "shares": shares,
                "buy_cost": buy_cost,
                "net": net,
                "last": trade["entry"],
            }
            taken.append(trade["name"])
            free -= 1
        for name in list(open_pos):
            pos = open_pos[name]
            if pos["exit_date"] == day and not pos["at_open"]:
                cash += notional + pos["net"]
                del open_pos[name]
        marked = cash
        for name in open_pos:
            pos = open_pos[name]
            i = pos["seg"].idx.get(day) if pos["seg"] is not None else None
            if i is not None:
                pos["last"] = pos["seg"].c[i]
            marked += notional + (pos["last"] - pos["entry"]) * pos["shares"] - pos["buy_cost"]
        equity.append(marked)
    stats = curve_stats(calendar, equity, capital) if calendar else {
        "cagr": None, "max_dd": None, "worst_year": None, "final": capital}
    stats["taken"] = taken
    return stats


def judge(block, nifty, need=NEIGHBOUR_NEED):
    """PASS only when every mark holds. Reasons name the marks that missed."""
    reasons = []
    if block["t"] is None or not block["t"] > 2:
        reasons.append("excess t %s is not above 2" % _num(block["t"]))
    if block["early"] is None or not block["early"] > 0:
        reasons.append("2005-2014 excess %s is not above 0" % _pct(block["early"]))
    if block["late"] is None or not block["late"] > 0:
        reasons.append("2015-2024 excess %s is not above 0" % _pct(block["late"]))
    if block["neighbours_pass"] < need:
        reasons.append("neighbours %d of %d, need %d" % (
            block["neighbours_pass"], block["neighbours_n"], need))
    if block["large_excess"] is None or not block["large_excess"] > 0:
        reasons.append("large-cap excess %s is not above 0" % _pct(block["large_excess"]))
    cagr = block["cagr"]
    ncagr = None if nifty is None else nifty.get("cagr")
    if cagr is None or ncagr is None or not cagr >= ncagr + 3.0:
        reasons.append("CAGR %s is below NIFTY %s plus 3" % (_pct(cagr), _pct(ncagr)))
    dd = block["max_dd"]
    ndd = None if nifty is None else nifty.get("max_dd")
    if dd is None or ndd is None or not dd >= ndd - 10.0:
        reasons.append("max drawdown %s is more than 10 points worse than NIFTY %s" % (
            _pct(dd), _pct(ndd)))
    return {"result": "PASS" if not reasons else "FAIL", "reasons": reasons}


def _pct(value):
    if value is None:
        return "n/a"
    return "%+.3f%%" % value


def _num(value):
    if value is None:
        return "n/a"
    return "%+.2f" % value


def _score_spec(spec, trades, pools, loaded, nifty, cache, seed):
    rng = random.Random(seed)
    pairs = build_pairs(trades, pools, loaded, spec, nifty, cache, rng)
    overall = cluster_stats(pairs)
    early, late = split_decades(pairs)
    return overall, early, late


def score_candidate(cand, index, loaded, pools, trades_for, raw_for, pools100, trades100,
                    nifty, calendar, nifty_stats):
    cache = {}
    base = cand["base"]
    overall, early, late = _score_spec(
        base, trades_for[id(base)], pools, loaded, nifty, cache, SEED + index)
    neighbours = []
    passed = 0
    for j, spec in enumerate(cand["neighbours"]):
        stats, _e, _l = _score_spec(
            spec, trades_for[id(spec)], pools, loaded, nifty, cache, SEED + 100 + index * 10 + j)
        ok = neighbour_ok(stats)
        if ok:
            passed += 1
        neighbours.append({
            "name": spec["name"],
            "excess": stats["excess"],
            "t": stats["t"],
            "pairs": stats["pairs"],
            "pass": ok,
        })
    large, _e, _l = _score_spec(
        base, trades100[id(base)], pools100, loaded, nifty, cache, SEED + 500 + index)
    port = simulate(raw_for[id(base)], calendar)
    block = {
        "name": cand["name"],
        "trades": len(trades_for[id(base)]),
        "pairs": overall["pairs"],
        "months": overall["months"],
        "excess": overall["excess"],
        "t": overall["t"],
        "early": early["excess"],
        "early_t": early["t"],
        "early_pairs": early["pairs"],
        "late": late["excess"],
        "late_t": late["t"],
        "late_pairs": late["pairs"],
        "neighbours": neighbours,
        "neighbours_n": len(neighbours),
        "neighbours_pass": passed,
        "large_excess": large["excess"],
        "large_t": large["t"],
        "large_trades": len(trades100[id(base)]),
        "large_pairs": large["pairs"],
        "cagr": port["cagr"],
        "max_dd": port["max_dd"],
        "worst_year": port["worst_year"],
    }
    block["verdict"] = judge(block, nifty_stats)
    return block


def load_market(root, end, log=None):
    emit = log or (lambda line: None)
    loaded, books = lab._books(root, end, emit)
    for symbol in loaded:
        for seg in symbol["segments"]:
            prepare(seg)
    nifty = load_nifty(root, end)
    return loaded, books, nifty


def _universe(calendar, books):
    top200 = {}
    top100 = {}
    for day in calendar:
        names = lab.liquid_names(day, books, lab.UNIVERSE_N)
        if not names:
            continue
        top200[day] = set(names)
        top100[day] = set(names[:100])
    return top200, top100


def _flat_specs(cands):
    specs = []
    for cand in cands:
        specs.append(cand["base"])
        for spec in cand["neighbours"]:
            specs.append(spec)
    return specs


def run(root, start=START, end=END, warmup=WARMUP, log=None, loaded=None, books=None,
        nifty=None, calendar=None):
    """Score the four candidates. Pass loaded symbols to skip the disk."""
    emit = log or (lambda line: None)
    if loaded is None:
        loaded, books, nifty = load_market(root, end, emit)
    days = []
    seen = set()
    for symbol in loaded:
        for seg in symbol["segments"]:
            for day in seg.date:
                # Days before the window stay in the rank. A signal on the session
                # before the first entry is decided from that earlier book.
                if day not in seen and day <= end:
                    seen.add(day)
                    days.append(day)
    for day in nifty:
        if day not in seen and day <= end:
            seen.add(day)
            days.append(day)
    days.sort()
    if calendar is None:
        calendar = [day for day in sorted(nifty) if start <= day <= end]
    emit("ranking turnover")
    top200, top100 = _universe(days, books)
    cands = candidates()
    emit("scanning top 200")
    pools, thinned, raw = scan(loaded, top200, _flat_specs(cands), warmup, start, end)
    trades_for = {}
    raw_for = {}
    for spec, trades, raw_trades in zip(_flat_specs(cands), thinned, raw):
        trades_for[id(spec)] = trades
        raw_for[id(spec)] = raw_trades
    emit("scanning top 100")
    bases = [cand["base"] for cand in cands]
    pools100, thinned100, _raw100 = scan(loaded, top100, bases, warmup, start, end)
    trades100 = {}
    for spec, trades in zip(bases, thinned100):
        trades100[id(spec)] = trades
    emit("nifty buy and hold")
    nifty_stats = nifty_buy_hold(calendar, nifty, CAPITAL)
    blocks = []
    for index, cand in enumerate(cands):
        block = score_candidate(
            cand, index, loaded, pools, trades_for, raw_for, pools100, trades100,
            nifty, calendar, nifty_stats)
        blocks.append(block)
        emit(format_block(block, nifty_stats))
    return blocks, nifty_stats


def format_block(block, nifty):
    lines = [block["name"]]
    lines.append("  trades %d, pairs %d, months %d, excess %s, t %s" % (
        block["trades"], block["pairs"], block["months"], _pct(block["excess"]), _num(block["t"])))
    lines.append("  2005-2014 excess %s, t %s, pairs %d" % (
        _pct(block["early"]), _num(block["early_t"]), block["early_pairs"]))
    lines.append("  2015-2024 excess %s, t %s, pairs %d" % (
        _pct(block["late"]), _num(block["late_t"]), block["late_pairs"]))
    bits = []
    for item in block["neighbours"]:
        bits.append("%s excess %s t %s %s" % (
            item["name"], _pct(item["excess"]), _num(item["t"]),
            "PASS" if item["pass"] else "FAIL"))
    lines.append("  neighbours %d of %d: %s" % (
        block["neighbours_pass"], block["neighbours_n"], "; ".join(bits)))
    lines.append("  large caps: trades %d, pairs %d, excess %s, t %s" % (
        block["large_trades"], block["large_pairs"], _pct(block["large_excess"]), _num(block["large_t"])))
    lines.append("  portfolio CAGR %s, max DD %s, worst year %s" % (
        _pct(block["cagr"]), _pct(block["max_dd"]), _pct(block["worst_year"])))
    if nifty is not None:
        lines.append("  NIFTY CAGR %s, max DD %s, worst year %s" % (
            _pct(nifty.get("cagr")), _pct(nifty.get("max_dd")), _pct(nifty.get("worst_year"))))
    lines.append("  dividends excluded")
    if block["verdict"]["result"] == "PASS":
        lines.append("  PASS")
    else:
        lines.append("  FAIL: %s" % "; ".join(block["verdict"]["reasons"]))
    return "\n".join(lines)


def rules_text(stamp):
    """Locked before the run. No result numbers belong in here."""
    return "\n".join([
        "## Attempt 10",
        "",
        "Rules fixed on %s, before the run." % stamp,
        "",
        "Hypothesis: the attempt-9 signals that beat a random entry still do so after "
        "a market adjustment, and the edge is not an artifact of one decade, one "
        "parameter, the smaller names, or of ignoring how many positions fit in a book.",
        "",
        "Candidates, long only, same entry and exit as attempt 9: (a) 20d-high / "
        "sma20-close, (b) engulf-low / hold-20, (c) bb-squeeze / sma20-close, "
        "(d) sma20-touch / sma20-close. A signal is decided at the close and the entry "
        "is the next session's open. One open trade per symbol inside a segment for the "
        "excess study. A break closes the trade at the segment's last close. The first "
        "250 sessions of a segment are skipped, and a break starts that count again. "
        "Costs are the delivery schedule in signal_lab.py (check your broker), sized at "
        "Rs 1,00,000. Data is read through india/research/data.py. The window is "
        "2005-01-01 through 2024-12-31. Dates from 2025-01-01 on are not requested.",
        "",
        "1. Market-adjusted excess. For each signal trade, excess is its percent return "
        "after costs minus NIFTY 50's percent price change over the same dates: from "
        "NIFTY's open on the entry date to NIFTY's open on the exit date when the trade "
        "exits at the open, otherwise to NIFTY's close on the exit date. A pair whose "
        "dates sit in different NIFTY segments is skipped, because that return would "
        "cross a break. Each signal trade is matched to one seeded random eligible "
        "entry from the same calendar month, with the same exit, and that random trade "
        "is measured the same way. The paired difference is the signal excess minus the "
        "random excess. The average excess per trade is the mean of those differences. "
        "The t-statistic averages the differences inside each entry month, then takes "
        "the mean of those monthly averages divided by their sample standard error. "
        "The seed is 20261106 plus a fixed offset per candidate, per neighbour and for "
        "the large-cap rerun.",
        "",
        "2. Decades. The same average excess, split by the entry date, for 2005-2014 "
        "and for 2015-2024.",
        "",
        "3. Neighbours change one parameter at a time. A neighbour passes when its "
        "average excess is above 0 and its t-statistic is above 2. (a) prior 15-session "
        "high with the SMA20 exit; prior 30-session high with the SMA20 exit; prior "
        "20-session high with the SMA10 exit; prior 20-session high with the SMA30 exit. "
        "(b) bullish engulfing at the prior 10-session low, held 20 sessions; at the "
        "prior 30-session low, held 20 sessions; at the prior 20-session low, held 15 "
        "sessions; at the prior 20-session low, held 30 sessions. (c) Bollinger width "
        "lookback 63 with the SMA20 exit; lookback 252 with the SMA20 exit; lookback "
        "126 with the SMA10 exit; lookback 126 with the SMA30 exit. The close must "
        "still finish above the upper band, and the width low must still fall within "
        "the last 5 sessions. (d) a touch of SMA10 with the exit on a close below SMA10; "
        "a touch of SMA50 with the exit on a close below SMA50. The close must still be "
        "above SMA200. At least 2 neighbours must pass. (a), (b) and (c) have four "
        "neighbours. (d) has two, so both must pass.",
        "",
        "4. Large caps. The same excess as (1), with the daily universe cut to the 100 "
        "names with the highest average turnover over the previous 60 sessions.",
        "",
        "5. Portfolio. Capital Rs 10,00,000. At most 10 positions, each reserved at "
        "Rs 1,00,000. When more signals are due on an entry date than there are free "
        "slots, take the highest average turnover over the 60 sessions before that "
        "entry, and break ties by symbol name. A symbol already open is skipped, and a "
        "symbol that exits at the open is not re-entered the same day. Cash earns 0. "
        "Report CAGR, max drawdown and the worst calendar year. CAGR uses 365.25-day "
        "years from the first NIFTY session in the window to the last. Drawdown is the "
        "worst peak-to-trough on the daily equity, in percent. The same three numbers "
        "are reported for buying NIFTY 50 at the first close and holding to the last "
        "close. Dividends are excluded for the portfolio and for NIFTY. The portfolio "
        "still pays the delivery costs. NIFTY is the price change only, with no costs.",
        "",
        "Pass mark, fixed before this run and separate from attempts 1 to 9: excess t "
        "above 2 on the whole window; average excess above 0 in both decades; at least "
        "2 neighbours passing; average excess above 0 in the top 100; portfolio CAGR at "
        "least NIFTY's CAGR plus 3 percentage points; and max drawdown no more than 10 "
        "percentage points worse than NIFTY's. A drawdown exactly 10 points worse still "
        "passes. A CAGR exactly 3 points above NIFTY still passes.",
        "",
        "Results are filled in after the run.",
        "",
    ])


def results_text(stamp, blocks, nifty):
    body = rules_text(stamp).replace("Results are filled in after the run.", "").rstrip()
    lines = [body, "", "Dividends are excluded. The table columns are average excess and the monthly t, not R.", ""]
    lines.append("NIFTY 50 buy and hold, price only: CAGR %s, max DD %s, worst year %s." % (
        _pct(nifty.get("cagr")), _pct(nifty.get("max_dd")), _pct(nifty.get("worst_year"))))
    lines.append("")
    passed = 0
    for block in blocks:
        lines.append(format_block(block, nifty))
        lines.append("")
        if block["verdict"]["result"] == "PASS":
            passed += 1
    lines.append("Candidates that pass: %d of %d." % (passed, len(blocks)))
    return "\n".join(lines).rstrip() + "\n"


def table_rows(stamp, blocks):
    rows = []
    rule = "excess vs same-month random, monthly t, top 100, 10-slot portfolio"
    universe = "point-in-time turnover, 2005-01-01 to 2024-12-31, dividends excluded"
    for block in blocks:
        hypothesis = "%s keeps a market-adjusted excess over a same-month random entry." % block["name"]
        rows.append("| 10 | %s | %s | %s | %s | %s | %s | %s | %s |" % (
            stamp, hypothesis, rule, universe,
            format(block["trades"], ",d"),
            _pct(block["excess"]),
            _num(block["t"]),
            block["verdict"]["result"]))
    return rows


def install(path, section, rows):
    """Replace an existing attempt 10 section and its table rows. Leave attempt 9 in place."""
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    kept = []
    for line in text.splitlines():
        if line.startswith("| 10 |"):
            continue
        kept.append(line)
    text = "\n".join(kept)
    if not text.endswith("\n"):
        text += "\n"
    start = text.find("\n## Attempt 10\n")
    forward = text.find("\n## Forward test\n")
    later = text.find("\n## Attempt 11\n")
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
        if text.startswith("| 9 |"):
            line_start = 0
        else:
            at = text.find("\n| 9 |")
            line_start = at + 1 if at != -1 else -1
        if line_start != -1:
            line_end = text.find("\n", line_start)
            if line_end == -1:
                line_end = len(text)
            text = text[:line_end] + "\n" + "\n".join(rows) + text[line_end:]
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


def main(argv=None, log=None):
    import argparse
    parser = argparse.ArgumentParser(description="Robustness of the attempt 9 signals.")
    parser.add_argument("--root", default=os.path.join("data", "kite"))
    parser.add_argument("--experiments", default=EXPERIMENTS)
    args = parser.parse_args(argv)
    emit = log or (lambda line: print(line, flush=True))
    stamp = datetime.date.today().isoformat()
    install(args.experiments, rules_text(stamp), [])
    emit("rules written to %s before the run" % args.experiments)
    blocks, nifty = run(args.root, log=emit)
    install(args.experiments, results_text(stamp, blocks, nifty), table_rows(stamp, blocks))
    emit("nifty buy and hold: CAGR %s, max DD %s, worst year %s" % (
        _pct(nifty.get("cagr")), _pct(nifty.get("max_dd")), _pct(nifty.get("worst_year"))))
    for block in blocks:
        emit(format_block(block, nifty))
        emit("")
    return 0


if __name__ == "__main__":
    sys.exit(main())
