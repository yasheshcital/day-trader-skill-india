#!/usr/bin/env python3
"""Attempt 17: sector-relative RSI(2), turn of the month with stocks, sector rotation.

Rules are written to EXPERIMENTS.md before the run. Each family gets one
holdout look. A family that has already used it is not opened again.
Nothing is placed.

    python3 india/research/batch17.py
"""

import bisect
import datetime
import os
import random
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from india.research import batch16 as b16
from india.research import data
from india.research import follow as f
from india.research import harness as h
from india.research import signal_lab as lab
from india.research import ta

HOLDOUT = data.HOLDOUT_START
CATALOGUE = h.CATALOGUE
BASKET = 20
REL_SEED = 91000
TOM_SEED = 80000
ROT_SEED = 90000
LOOKBACK = {"sector 4w": 20, "sector 8w": 40, "sector 13w": 65}

# Nearest sector index file on disk. Industries with no near file are omitted.
INDUSTRY_SECTOR = {
    "Automobile and Auto Components": "NIFTY AUTO",
    "Consumer Durables": "NIFTY CONSR DURBL",
    "Fast Moving Consumer Goods": "NIFTY FMCG",
    "Financial Services": "NIFTY FIN SERVICE",
    "Healthcare": "NIFTY HEALTHCARE",
    "Information Technology": "NIFTY IT",
    "Media Entertainment & Publication": "NIFTY MEDIA",
    "Metals & Mining": "NIFTY METAL",
    "Oil Gas & Consumable Fuels": "NIFTY OIL AND GAS",
    "Power": "NIFTY ENERGY",
    "Realty": "NIFTY REALTY",
}

ROTATION = (
    "NIFTY AUTO",
    "NIFTY BANK",
    "NIFTY CONSR DURBL",
    "NIFTY ENERGY",
    "NIFTY FIN SERVICE",
    "NIFTY FMCG",
    "NIFTY HEALTHCARE",
    "NIFTY IT",
    "NIFTY MEDIA",
    "NIFTY METAL",
    "NIFTY OIL AND GAS",
    "NIFTY PHARMA",
    "NIFTY PSU BANK",
    "NIFTY PVT BANK",
    "NIFTY REALTY",
)

REL_SPECS = (
    {"name": "rel rsi5", "rel_max": 5.0, "stock_max": None},
    {"name": "rel rsi10", "rel_max": 10.0, "stock_max": None},
    {"name": "rel rsi5 stock10", "rel_max": 5.0, "stock_max": 10.0},
)

TOM_SPECS = ("tom nifty", "tom mom20", "tom rsi20")
ROT_SPECS = ("sector 4w", "sector 8w", "sector 13w")

# momentum and the rsi2 family have already had their one look.
FAMILY_USED = {
    "opening-range breakout": "no",
    "single technical signal": "no",
    "momentum": "yes",
    "rsi2": "yes",
    "pairs": "no",
    "holy grail": "no",
    "calendar": "no",
    "sector-relative rsi": "no",
    "turn of the month": "no",
    "sector rotation": "no",
}


def sector_for(industry):
    """Sector index for one Industry cell, or None when nothing on disk is close."""
    if not industry:
        return None
    return INDUSTRY_SECTOR.get(industry)


def relative_rsi(seg, sector_close):
    """RSI(2) of stock close over the sector close. A missing sector day starts again."""
    out = [None] * len(seg.date)
    run_i = []
    run_px = []

    def flush():
        if len(run_px) > 2:
            rsi = ta.rsi_series(run_px, 2)
            for k, at in enumerate(run_i):
                out[at] = rsi[k]
        run_i[:] = []
        run_px[:] = []

    for i, day in enumerate(seg.date):
        sector_px = sector_close.get(day)
        stock = seg.c[i]
        if sector_px is None or not sector_px > 0 or not stock > 0:
            flush()
            continue
        run_i.append(i)
        run_px.append(stock / sector_px)
    flush()
    return out


def rel_fires(seg, i, maximum, stock_max):
    """Stock close strictly above SMA200, and relative RSI(2) strictly below maximum."""
    if i < 0 or i >= len(seg.c):
        return False
    sma = seg.sma200[i]
    rel = seg.rel_rsi[i]
    if sma is None or rel is None or not seg.c[i] > sma:
        return False
    if not rel < maximum:
        return False
    if stock_max is None:
        return True
    rsi = seg.rsi2[i]
    if rsi is None or not rsi < stock_max:
        return False
    return True


def pick_high(scored, k):
    """Highest value first. A tie breaks on the symbol name."""
    ordered = sorted(scored, key=lambda item: (-item[0], item[1]))
    if k < 0:
        return []
    return [item[1] for item in ordered[:k]]


def pick_low(scored, k):
    """Lowest value first. A tie breaks on the symbol name."""
    ordered = sorted(scored, key=lambda item: (item[0], item[1]))
    if k < 0:
        return []
    return [item[1] for item in ordered[:k]]


def choose_two(scored):
    """Two highest scores, then the name. Fewer than two returns nothing."""
    ordered = sorted(scored, key=lambda item: (-item[0], item[1]))
    if len(ordered) < 2:
        return []
    return ordered[:2]


def session_return(closes, end_i, n):
    """Close at end_i over the close n sessions earlier, minus 1."""
    if end_i is None or n <= 0 or end_i < n or end_i >= len(closes):
        return None
    base = closes[end_i - n]
    if not base > 0:
        return None
    return closes[end_i] / base - 1.0


def basket_return(prices):
    """Equal-weight delivery return. A missing leg is left out. None when none remain."""
    rets = []
    for item in prices:
        if item is None:
            continue
        money = lab.delivery(item[0], item[1])
        if money is None:
            continue
        rets.append(money[0])
    if not rets:
        return None
    return h._mean(rets)


def close_on(by_name, symbol, day):
    loc = by_name.get(symbol, {}).get(day)
    if loc is None:
        return None
    seg, i = loc
    px = seg.c[i]
    if not px > 0:
        return None
    return px


def priced_legs(names, by_name, entry, exit_day):
    """(entry close, exit close) for names that have both, and those names."""
    pairs = []
    kept = []
    for name in names:
        a = close_on(by_name, name, entry)
        b = close_on(by_name, name, exit_day)
        if a is None or b is None:
            continue
        if lab.delivery(a, b) is None:
            continue
        pairs.append((a, b))
        kept.append(name)
    return pairs, kept


def tom_windows(calendar, nifty):
    """Attempt 16 turn-of-month windows: (entry, exit, entry close, exit close)."""
    return b16.calendar_events(calendar, nifty)["tom"]


def mondays(calendar):
    """(monday, next monday) for NIFTY sessions that fall on a Monday."""
    days = [day for day in calendar if day.weekday() == 0]
    out = []
    for i, day in enumerate(days):
        if i + 1 < len(days):
            out.append((day, days[i + 1]))
    return out


def judge_weeks(block, family):
    """Attempt 16 trade clauses without a large-cap bucket. These are index legs."""
    reasons = []
    if block["avg"] is None or not block["avg"] > 0:
        reasons.append("avg after costs %s is not above 0" % h._pct(block["avg"]))
    if block["t"] is None or not block["t"] > 3:
        reasons.append("t vs random %s is not above 3" % h._num(block["t"]))
    checks = (
        ("early", "2005-2014"),
        ("late", "2015-2024"),
        ("up", "up"),
        ("down", "down"),
        ("sideways", "sideways"),
    )
    for key, label in checks:
        if block.get(key) is None or not block[key] > 0:
            reasons.append("%s %s is not above 0" % (label, h._pct(block.get(key))))
    strong = 0
    for item in family:
        if item.get("t") is not None and item["t"] > 2:
            strong += 1
    if strong < 2:
        reasons.append("family variants with t above 2: %d of %d, need 2" % (strong, len(family)))
    return {"result": "PASS" if not reasons else "FAIL", "reasons": reasons}


def holdout_plan(blocks, used):
    """Passers of a fresh family are looked at once. A used family waits for new months."""
    run = []
    waiting = []
    for block in blocks:
        verdict = block.get("verdict") or {}
        if verdict.get("result") != "PASS":
            continue
        family = block.get("family")
        if used.get(family) == "yes":
            waiting.append(block)
        else:
            run.append(block)
    return run, waiting


def _swing_block(name, trades, pools, style, runs, seed, family):
    block = f.summarise_swing(name, trades)
    block["nifty_t"] = b16.nifty_monthly_t(trades)
    block["family"] = family
    if runs:
        f.apply_trade_random(trades, pools, style, runs, seed)
        block["t"] = f.summarise_swing(name, trades)["t"]
    else:
        block["t"] = block["nifty_t"]
    return block


def _month_t(trades):
    """One-sample t of the monthly mean of the weekly excess."""
    by_month = {}
    for trade in trades:
        if trade.get("excess") is None:
            continue
        key = (trade["date"].year, trade["date"].month)
        by_month.setdefault(key, []).append(trade["excess"])
    monthly = []
    for key in sorted(by_month):
        monthly.append(h._mean(by_month[key]))
    return h.t_stat(monthly)


def _apply_week_random(trades, runs, seed):
    if not runs:
        return
    for run_i in range(runs):
        rng = random.Random(seed + run_i)
        for trade in trades:
            legs = trade["legs"]
            n = len(legs)
            if n < 2:
                continue
            i = rng.randrange(n)
            j = rng.randrange(n - 1)
            if j >= i:
                j += 1
            trade.setdefault("samples", []).append((legs[i] + legs[j]) / 2.0)
    for trade in trades:
        samples = trade.pop("samples", None)
        if samples:
            trade["excess"] = trade["ret"] - h._mean(samples)
        else:
            trade["excess"] = None


def load_sectors(root, end, final):
    """Sector index segments. A missing file is skipped."""
    loaded = {}
    closes = {}
    located = {}
    for name in ROTATION:
        try:
            segments = lab.load_symbol(root, name, end=end, final=final)
        except data.DataError:
            continue
        if not segments:
            continue
        loaded[name] = segments
        series = {}
        at = {}
        for seg in segments:
            for i, day in enumerate(seg.date):
                at[day] = (seg, i)
                px = seg.c[i]
                if px > 0:
                    series[day] = px
        closes[name] = series
        located[name] = at
    return loaded, closes, located


def prepare_context(root, end, log, final):
    emit = log or (lambda line: None)
    ctx = h.load_context(root, start=f.SWING_START, end=end, log=emit, final=final)
    for symbol in ctx["loaded"]:
        f.attach_indicators(symbol["segments"])
    _loaded, closes, located = load_sectors(root, end, final)
    ctx["sector_close"] = closes
    ctx["sector_at"] = located
    emit("sector indices %d" % len(closes))
    return ctx


def attach_relative(ctx, industries):
    """Map each stock to its sector and store relative RSI(2) on the segment."""
    mapped = 0
    for symbol in ctx["loaded"]:
        sector = sector_for(industries.get(symbol["name"]))
        series = None if sector is None else ctx["sector_close"].get(sector)
        if not series:
            symbol["sector"] = None
            continue
        symbol["sector"] = sector
        mapped += 1
        for seg in symbol["segments"]:
            seg.rel_rsi = relative_rsi(seg, series)
    return mapped


def run_rel(ctx, start, end, runs, log, only=None):
    emit = log or (lambda line: None)
    specs = []
    for spec in REL_SPECS:
        if only is None or spec["name"] in only:
            specs.append(spec)
    if not specs:
        return []
    collected = {}
    pools = {}
    for spec in specs:
        collected[spec["name"]] = []
    nifty = ctx["nifty"]
    top200 = ctx["top200"]
    top100 = ctx["top100"]
    regimes = ctx["regimes"]
    seen = 0
    for symbol in ctx["loaded"]:
        if not symbol.get("sector"):
            continue
        seen += 1
        if seen % 100 == 0:
            emit("sector-relative scanned %d" % seen)
        name = symbol["name"]
        for seg in symbol["segments"]:
            if not hasattr(seg, "rel_rsi"):
                continue
            n = len(seg.date)
            if runs:
                for entry_i in range(n):
                    day = seg.date[entry_i]
                    if day < start or day > end:
                        continue
                    if name not in top200.get(day, ()):
                        continue
                    done = f._finish(
                        seg, entry_i,
                        f.exit_rule(seg, entry_i, f.RSI_LIMIT, f.close_above_sma5), nifty)
                    if done is not None:
                        f._pool_add(pools, "rel", name, day, done[0], done[1])
            for i in range(n - 1):
                signal = seg.date[i]
                entry_i = i + 1
                entry_day = seg.date[entry_i]
                if entry_day < start or entry_day > end:
                    continue
                if name not in top200.get(signal, ()):
                    continue
                large = name in top100.get(signal, ())
                kind = regimes.get(entry_day)
                for spec in specs:
                    if not rel_fires(seg, i, spec["rel_max"], spec["stock_max"]):
                        continue
                    done = f._finish(
                        seg, entry_i,
                        f.exit_rule(seg, entry_i, f.RSI_LIMIT, f.close_above_sma5), nifty)
                    if done is None:
                        continue
                    ret, mkt, hold = done
                    collected[spec["name"]].append(
                        f.make_trade(entry_day, name, ret, mkt, kind, large, hold))
    emit("sector-relative names %d" % seen)
    blocks = []
    for index, spec in enumerate(REL_SPECS):
        if spec["name"] not in collected:
            continue
        trades = collected[spec["name"]]
        seed = h.SEED + REL_SEED + index * 1000
        emit("scoring %s (%d)" % (spec["name"], len(trades)))
        block = _swing_block(spec["name"], trades, pools, "rel", runs, seed, "sector-relative rsi")
        blocks.append(block)
    if only is None:
        for block in blocks:
            block["verdict"] = f.judge_swing(block, blocks)
    return blocks


def _ranked(ctx, day, kind):
    scored = []
    for name in ctx["top200"].get(day, ()):
        loc = ctx["by_name"].get(name, {}).get(day)
        if loc is None:
            continue
        seg, i = loc
        if kind == "mom":
            value = b16.momentum_12_1(seg, i)
            if value is None:
                continue
            scored.append((value, name))
            continue
        sma = seg.sma200[i]
        series = getattr(seg, "rsi2", None)
        if sma is None or series is None or not seg.c[i] > sma:
            continue
        rsi = series[i]
        if rsi is None:
            continue
        scored.append((rsi, name))
    if kind == "mom":
        return pick_high(scored, BASKET)
    return pick_low(scored, BASKET)


def _tom_excess(calendar, nifty, by_name, entry, exit_day, ret, kept, runs, seed, futures):
    entry_i = bisect.bisect_left(calendar, entry)
    exit_i = bisect.bisect_left(calendar, exit_day)
    length = exit_i - entry_i
    if length < 1 or entry_i >= len(calendar) or calendar[entry_i] != entry:
        return None
    rng = random.Random(seed)
    windows = b16._random_windows(calendar, entry, exit_day, entry.year, rng, runs)
    baseline = []
    for start_i in windows:
        a = calendar[start_i]
        b = calendar[start_i + length]
        if futures:
            value = b16._futures_long(nifty[a]["close"], nifty[b]["close"], a, b)
        else:
            pairs, _names = priced_legs(kept, by_name, a, b)
            value = basket_return(pairs)
        if value is not None:
            baseline.append(value)
    if not baseline:
        return None
    return ret - h._mean(baseline)


def run_tom(ctx, start, end, runs, log, only=None):
    emit = log or (lambda line: None)
    calendar = [day for day in ctx["calendar"] if ctx["nifty"].get(day, {}).get("open", 0) > 0 and day <= end]
    windows = tom_windows(calendar, ctx["nifty"])
    emit("tom windows %d" % len(windows))
    want = {}
    for name in TOM_SPECS:
        if only is None or name in only:
            want[name] = []
    if not want:
        return []
    for event_i, event in enumerate(windows):
        entry, exit_day, entry_px, exit_px = event
        if entry < start or entry > end:
            continue
        regime = ctx["regimes"].get(entry)
        if "tom nifty" in want:
            ret = b16._futures_long(entry_px, exit_px, entry, exit_day)
            if ret is not None:
                seed = h.SEED + b16.CAL_SEED + event_i
                excess = _tom_excess(
                    calendar, ctx["nifty"], ctx["by_name"], entry, exit_day,
                    ret, None, runs, seed, True)
                want["tom nifty"].append({
                    "date": entry, "ret": ret, "excess": excess, "regime": regime, "large": False,
                })
        picks = {}
        if "tom mom20" in want:
            picks["tom mom20"] = _ranked(ctx, entry, "mom")
        if "tom rsi20" in want:
            picks["tom rsi20"] = _ranked(ctx, entry, "rsi")
        for index, name in enumerate(("tom mom20", "tom rsi20")):
            if name not in want:
                continue
            names = picks.get(name) or []
            pairs, kept = priced_legs(names, ctx["by_name"], entry, exit_day)
            ret = basket_return(pairs)
            if ret is None:
                continue
            seed = h.SEED + TOM_SEED + index * 1000 + event_i
            excess = _tom_excess(
                calendar, ctx["nifty"], ctx["by_name"], entry, exit_day,
                ret, kept, runs, seed, False)
            want[name].append({
                "date": entry, "ret": ret, "excess": excess, "regime": regime, "large": False,
            })
    blocks = []
    for name in TOM_SPECS:
        if name not in want:
            continue
        trades = want[name]
        excesses = [item["excess"] for item in trades if item.get("excess") is not None]
        block = b16._event_block(name, trades, excesses)
        block["t"] = h.t_stat(excesses)
        block["family"] = "turn of the month"
        blocks.append(block)
        emit("tom %s (%d)" % (name, len(trades)))
    if only is None:
        for block in blocks:
            block["verdict"] = b16.judge_event(block, blocks, "monthly t")
    return blocks


def _week_table(ctx, start, end):
    pairs = mondays(ctx["calendar"])
    rows = []
    located = ctx["sector_at"]
    for monday, nxt in pairs:
        if monday < start or monday > end:
            continue
        sectors = []
        for name, at in located.items():
            loc = at.get(monday)
            nxt_loc = at.get(nxt)
            if loc is None or nxt_loc is None:
                continue
            seg, i = loc
            nxt_seg, j = nxt_loc
            if nxt_seg is not seg or i < 1:
                continue
            if not seg.o[i] > 0 or not seg.o[j] > 0:
                continue
            money = lab.delivery(seg.o[i], seg.o[j])
            if money is None:
                continue
            scores = {}
            for look in (20, 40, 65):
                scores[look] = session_return(seg.c, i - 1, look)
            sectors.append({"name": name, "ret": money[0], "scores": scores})
        if sectors:
            rows.append({
                "monday": monday,
                "regime": ctx["regimes"].get(monday),
                "sectors": sectors,
            })
    return rows


def run_rotation(ctx, start, end, runs, log, only=None):
    emit = log or (lambda line: None)
    weeks = _week_table(ctx, start, end)
    emit("sector weeks %d" % len(weeks))
    blocks = []
    for index, name in enumerate(ROT_SPECS):
        if only is not None and name not in only:
            continue
        look = LOOKBACK[name]
        trades = []
        for week in weeks:
            scored = []
            ret_of = {}
            for sector in week["sectors"]:
                score = sector["scores"].get(look)
                if score is None:
                    continue
                scored.append((score, sector["name"]))
                ret_of[sector["name"]] = sector["ret"]
            chosen = choose_two(scored)
            if len(chosen) < 2:
                continue
            legs = [ret_of[item[1]] for item in scored]
            rets = [ret_of[item[1]] for item in chosen]
            trades.append({
                "date": week["monday"],
                "ret": h._mean(rets),
                "regime": week["regime"],
                "legs": legs,
            })
        seed = h.SEED + ROT_SEED + index * 1000
        _apply_week_random(trades, runs, seed)
        slices = b16.trade_slices(trades)
        slices.update({
            "name": name,
            "trades": len(trades),
            "avg": h._mean([item["ret"] for item in trades]),
            "t": _month_t(trades),
            "family": "sector rotation",
        })
        blocks.append(slices)
        emit("rotation %s (%d)" % (name, len(trades)))
    if only is None:
        for block in blocks:
            block["verdict"] = judge_weeks(block, blocks)
    return blocks


def _holdout_judge(block):
    block["hold_avg"] = block.get("avg")
    block["hold_t"] = block.get("t")
    block["verdict"] = b16.judge_holdout(block.get("avg"), block.get("t"))
    block["holdout"] = True
    return block


def run_holdout(root, blocks, industries, runs, log, used=None):
    """One final=True load, and only for a family that has not used its look."""
    emit = log or (lambda line: None)
    flags = FAMILY_USED if used is None else used
    run, waiting = holdout_plan(blocks, flags)
    for block in waiting:
        block["mark"] = "needs new data"
        emit("%s needs new data" % block["name"])
    if not run:
        emit("no holdout was run")
        return []
    path = data.bar_path(root, "day", lab.NIFTY)
    from india.research import survivorship as sv
    _first, last = sv.raw_span(path)
    emit("holdout %s to %s" % (HOLDOUT.isoformat(), last.isoformat()))
    names = {}
    for block in run:
        names.setdefault(block["family"], []).append(block["name"])
    ctx = h.load_context(root, start=f.SWING_START, end=last, log=emit, final=True)
    for symbol in ctx["loaded"]:
        f.attach_indicators(symbol["segments"])
    _loaded, closes, located = load_sectors(root, last, True)
    ctx["sector_close"] = closes
    ctx["sector_at"] = located
    attach_relative(ctx, industries)
    out = []
    if names.get("sector-relative rsi"):
        for block in run_rel(ctx, HOLDOUT, last, 0, emit, names["sector-relative rsi"]):
            out.append(_holdout_judge(block))
    if names.get("turn of the month"):
        for block in run_tom(ctx, HOLDOUT, last, runs, emit, names["turn of the month"]):
            out.append(_holdout_judge(block))
    if names.get("sector rotation"):
        for block in run_rotation(ctx, HOLDOUT, last, runs, emit, names["sector rotation"]):
            out.append(_holdout_judge(block))
    for block in out:
        flags[block["family"]] = "yes"
    return out


def base_entries():
    """Attempts 1 to 16. Turn of the month is a near-miss, not a closed row."""
    rows = list(b16.history_entries())
    rows.extend([
        {"name": "m2 regime", "tier": "Watch", "attempt": "16",
         "note": "PASS Holdout FAIL, avg +0.079%, t +0.78."},
        {"name": "tom (turn of the month)", "tier": "Near-miss", "attempt": "16",
         "note": (
             "Average after costs +0.556% and monthly t +2.41. Positive in both "
             "decades and in up, down and sideways. t is not above 3, and the family was 1 of 3."
         )},
        {"name": "pairs same", "tier": "Closed", "attempt": "16", "note": "FAIL"},
        {"name": "pairs any", "tier": "Closed", "attempt": "16", "note": "FAIL"},
        {"name": "pairs z", "tier": "Closed", "attempt": "16", "note": "FAIL"},
        {"name": "grail adx30", "tier": "Closed", "attempt": "16", "note": "FAIL"},
        {"name": "grail adx25", "tier": "Closed", "attempt": "16", "note": "FAIL"},
        {"name": "grail adx30 sma200", "tier": "Closed", "attempt": "16", "note": "FAIL"},
        {"name": "expiry week", "tier": "Closed", "attempt": "16", "note": "FAIL"},
        {"name": "after expiry", "tier": "Closed", "attempt": "16", "note": "FAIL"},
        {"name": "m1 momentum", "tier": "Closed", "attempt": "16", "note": "FAIL"},
        {"name": "m3 book", "tier": "Closed", "attempt": "16", "note": "FAIL"},
    ])
    return rows


def tier_for(result):
    """Bucket and Watch from the holdout. A used family that passes waits on Watch."""
    if result.get("mark") == "needs new data":
        return "Watch"
    hold = result.get("holdout")
    avg = None if hold is None else hold.get("avg")
    tstat = None if hold is None else hold.get("t")
    return b16.tier_of(result.get("in_sample"), avg, tstat)


def render_catalogue(entries, flags):
    lines = [
        "# Strategy catalogue",
        "",
        "Attempts 1 to 10 tested two families. Attempts 1 to 8 are the opening-range breakout family. Attempts 9 and 10 are the single technical-signal family (one entry rule, one exit rule, scored one trade at a time and then as a 10-slot book). Attempt 11 is the first batch on the shared harness in `harness.py`. A later batch keeps the same pass mark.",
        "",
        "Dividends are excluded. Nothing here places an order.",
        "",
        "Tiers are filled from the attempt results. Bucket means an in-sample PASS "
        "and a holdout PASS. Watch means an in-sample PASS whose holdout average "
        "after costs is positive and whose holdout t is not above 2. Investing is "
        "a real edge kept for the later investing phase. Near-miss is close and "
        "closed is the rest. The source table below is the bibliography.",
        "",
        "Each family gets one holdout look. A later variant of a family that has "
        "used its look is judged on the in-sample result plus new months of data "
        "only. It is not given another look at the same holdout window.",
        "",
        "## Families",
        "",
        "| Family | Holdout used |",
        "|---|---|",
    ]
    for name in (
        "opening-range breakout",
        "single technical signal",
        "momentum",
        "rsi2",
        "pairs",
        "holy grail",
        "calendar",
        "sector-relative rsi",
        "turn of the month",
        "sector rotation",
    ):
        lines.append("| %s | %s |" % (name, flags.get(name, "no")))
    lines.append("")
    order = ("Bucket", "Watch", "Investing", "Near-miss", "Closed")
    blurbs = {
        "Bucket": "In-sample PASS and holdout PASS.",
        "Watch": (
            "In-sample PASS, holdout average after costs above 0, t not above 2. "
            "An in-sample pass whose family has already used its one holdout look waits here for new months."
        ),
        "Investing": "A real edge, for the later investing phase.",
        "Near-miss": "Close to a pass, and not in the buckets above.",
        "Closed": "Tested and not in a bucket above.",
    }
    for tier in order:
        lines.append("## %s" % tier)
        lines.append("")
        lines.append(blurbs[tier])
        lines.append("")
        rows = [item for item in entries if item["tier"] == tier]
        if not rows:
            lines.append("None yet.")
            lines.append("")
            continue
        lines.append("| Name | Attempt | Note |")
        lines.append("|---|---|---|")
        for item in rows:
            note = item["note"].replace("|", "/")
            lines.append("| %s | %s | %s |" % (item["name"], item["attempt"], note))
        lines.append("")
    lines.append("## Sources")
    lines.append("")
    lines.append(b16.SOURCES)
    lines.append("")
    return "\n".join(lines)


def update_catalogue(path, results, flags=None):
    """Rewrite tiers. A historical name keeps its tier. Tom stays a near-miss."""
    used = FAMILY_USED if flags is None else flags
    entries = base_entries()
    known = {}
    for item in entries:
        known[item["name"]] = item
    for result in results:
        name = result["name"]
        if name in known:
            continue
        entries.append({
            "name": name,
            "tier": tier_for(result),
            "attempt": str(result.get("attempt", 17)),
            "note": result.get("note") or "",
        })
    text = render_catalogue(entries, used)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
    return entries


def rules_text(stamp):
    """Attempt 17 rules. No measured result belongs in this text."""
    return "\n".join([
        "## Attempt 17",
        "",
        "Rules fixed on %s, before the run." % stamp,
        "",
        "Three families on daily bars, 2005-01-01 through 2024-12-31. No 5-minute "
        "bars are used. Each family gets one holdout look. Momentum has used its "
        "look (attempt 11) and the rsi2 family has used its look (attempt 15). "
        "Every other family, including the three below, has not. A PASS from a "
        "family that has not used its look is scored once, in one load, from "
        "2025-01-01 through the last NIFTY 50 daily date. A PASS from a family "
        "that has already used its look is marked needs new data and is not "
        "opened. Dates from 2025-01-01 on are not requested until that one look. "
        "Dividends are excluded. Nothing is placed.",
        "",
        "1. Sector-relative RSI(2). New family. Hypothesis: the edge is "
        "stock-specific, so the dip is measured against the stock's own sector. "
        "Industry is the Industry column of india/universe/nifty500.csv. The "
        "nearest sector index file in data/kite/day is used, and a stock with no "
        "near file is skipped. The map is Automobile and Auto Components to "
        "NIFTY AUTO, Consumer Durables to NIFTY CONSR DURBL, Fast Moving Consumer "
        "Goods to NIFTY FMCG, Financial Services to NIFTY FIN SERVICE, Healthcare "
        "to NIFTY HEALTHCARE, Information Technology to NIFTY IT, Media "
        "Entertainment & Publication to NIFTY MEDIA, Metals & Mining to NIFTY "
        "METAL, Oil Gas & Consumable Fuels to NIFTY OIL AND GAS, Power to NIFTY "
        "ENERGY, Realty to NIFTY REALTY. Capital Goods, Chemicals, Construction, "
        "Construction Materials, Consumer Services, Diversified, Services, "
        "Telecommunication and Textiles are skipped. Relative price is the stock "
        "close divided by that sector index close on the same session. A session "
        "with no sector close breaks the series and RSI(2) starts again. The "
        "signal is the stock close strictly above its own SMA200 and the RSI(2) "
        "of the relative price strictly below the threshold. The entry is the "
        "next session's open. The exit is the attempt 14 exit: the next open "
        "after a close above SMA5, or the open five sessions after entry. "
        "Delivery costs, Rs 1,00,000 a trade. The name is in the top 200 by prior "
        "60-session turnover on the signal day. Variants: relative RSI(2) below "
        "5; below 10; below 5 and the stock's own RSI(2) below 10. Exactly 5 and "
        "exactly 10 do not fire. The random entries are 100 runs, seed 20261106 "
        "+ 91000 + variant index times 1000 + the run index, same-month top-200 "
        "days of the same symbol. The signal is not required. The t is the "
        "attempt 14 market-adjusted t versus those entries. The family is judged "
        "with the attempt 14 clauses, including large caps and at least 2 of the "
        "3 variants with t above 2.",
        "",
        "2. Turn of the month with stocks. This family is the turn of the month, "
        "which has not used a holdout. The window is the attempt 16 window: the "
        "close of the session before the last session of the month, to the close "
        "of the third session of the next month. That span is five sessions. (a) "
        "NIFTY 50, the attempt 16 rule, for reference: futures costs, one lot of "
        "75, and the attempt 16 tom seed 20261106 + 70000 + the event index. (b) "
        "The 20 stocks in that day's top 200 with the highest 12-1 momentum. "
        "12-1 is the close 21 sessions before the entry divided by the close 252 "
        "sessions before it, minus 1, inside one segment. (c) The 20 stocks in "
        "that day's top 200 with the lowest RSI(2), among names whose close is "
        "strictly above SMA200. Ties break on the symbol name. A basket shorter "
        "than 20 is held when fewer names qualify. An empty basket skips the "
        "month. (b) and (c) use delivery costs, Rs 1,00,000 a name, equal weight "
        "of the names that have both the entry close and the exit close. The "
        "baseline is the same holdings over 100 other 5-session windows in the "
        "same calendar year, not starting on the real entry date. Seeds for (b) "
        "and (c) are 20261106 + 80000 + the stock index times 1000 + the event "
        "index, with (b) at index 0 and (c) at index 1. A name with no close on a "
        "random window is left out of that window, and a window with no priced "
        "name is left out of the baseline. The average that must be above 0 is the window's own return "
        "after costs. The monthly t is the one-sample t of (that return minus "
        "the mean of the same-year random windows), one observation per month. "
        "A year with no other window leaves the month in the average and out of "
        "the t. Decades and market types use the window's own return and the "
        "entry date's regime. Large caps are not a pass clause. At least 2 of "
        "the 3 variants need t above 2.",
        "",
        "3. Weekly sector rotation. New family, a trading timeframe. Each NIFTY "
        "Monday, hold the 2 sector indices with the best trailing return, and "
        "sell them at the next NIFTY Monday's open. A Monday that is not a "
        "session is skipped, so the hold reaches the next session that is a "
        "Monday. The lookback ends on the session before that Monday, inside "
        "one segment of the sector: 20 sessions for 4 weeks, 40 for 8 weeks, "
        "65 for 13 weeks. Variants are those three lookbacks. The rotation "
        "universe is the sector indices on disk: NIFTY AUTO, NIFTY BANK, NIFTY "
        "CONSR DURBL, NIFTY ENERGY, NIFTY FIN SERVICE, NIFTY FMCG, NIFTY "
        "HEALTHCARE, NIFTY IT, NIFTY MEDIA, NIFTY METAL, NIFTY OIL AND GAS, "
        "NIFTY PHARMA, NIFTY PSU BANK, NIFTY PVT BANK, NIFTY REALTY. A sector "
        "joins a week only when it has the lookback and both Monday opens, in "
        "one segment. The two are treated as index ETFs with delivery costs, "
        "Rs 1,00,000 a leg, equal weight. A leg whose price does not buy one "
        "share is skipped, and a week with fewer than two eligible sectors is "
        "skipped. Ties break on the symbol name. The baseline is 2 random "
        "eligible sectors on the same week, 100 runs, seed 20261106 + 90000 + "
        "variant index times 1000 + the run index. The t is the one-sample t "
        "of the monthly mean of (the week's return minus the mean of those "
        "random pairs). Decades and market types use the week's own return and "
        "the Monday's regime. There is no large-cap clause. At least 2 of the "
        "3 variants need t above 2.",
        "",
        "Pass marks, fixed before this run, are the attempt 16 marks. Sector-relative "
        "RSI uses the attempt 14 judge: average after costs above 0, t versus "
        "random above 3, both decades, up, down, sideways, large caps, and at "
        "least 2 of the 3 variants with t above 2. Turn of the month uses the "
        "calendar judge: average after costs above 0, monthly t above 3, above "
        "0 in both decades and in each market type, and at least 2 of the 3 "
        "with t above 2. Sector rotation uses the same trade clauses without "
        "the large-cap bucket. A boundary stated as above is strict. At least "
        "2 of 3 passes when the count is exactly 2. An empty required bucket "
        "fails. Holdout PASS, for a family that has not used its look, is "
        "average after costs above 0 and t above 2. For sector-relative RSI the "
        "holdout t is the one-sample t of the monthly mean of (return after "
        "costs minus the NIFTY price return over the trade), not versus a "
        "random entry. For the turn of the month the holdout t is the same "
        "excess versus same-year 5-session windows. For sector rotation it is "
        "the same monthly t versus random sectors. The rule is not changed "
        "after the holdout. STRATEGIES.md is updated from these results at the end.",
        "",
    ])


def _result_cell(block):
    if block.get("mark") == "needs new data":
        return "needs new data"
    return (block.get("verdict") or {}).get("result", "")


def family_table(blocks, columns):
    lines = [" | ".join(columns)]
    for block in blocks:
        values = []
        for column in columns:
            values.append(b16._cell(block, column) if column != "result" else _result_cell(block))
        lines.append(" | ".join(values))
    return lines


def _reasons(block):
    if block.get("mark") == "needs new data":
        return "%s needs new data." % block["name"]
    return b16._reasons(block)


def table_rows(stamp, groups, holdouts, waiting):
    rows = []
    for blocks in groups:
        for block in blocks:
            trades = block.get("trades")
            trade_cell = "see section" if trades is None else format(trades, ",d")
            rows.append("| 17 | %s | %s | %s | %s | %s | %s | %s | %s |" % (
                stamp,
                "%s." % block["name"],
                "attempt 17, rules fixed before the run",
                "2005-01-01 to 2024-12-31",
                trade_cell,
                h._pct(block.get("avg")),
                h._num(block.get("t")),
                _result_cell(block)))
    if not holdouts and not waiting:
        rows.append("| 17 | %s | %s | %s | %s | %s | %s | %s | %s |" % (
            stamp,
            "no in-sample pass, so no holdout was run.",
            "final=True was not called",
            "2025-01-01 onward, not opened",
            "0", "n/a", "n/a", "n/a"))
    for block in holdouts:
        rows.append("| 17 | %s | %s | %s | %s | %s | %s | %s | %s |" % (
            stamp,
            "holdout %s." % block["name"],
            "same rule, final=True once",
            "2025-01-01 to the last NIFTY date",
            format(block["trades"], ",d") if block.get("trades") is not None else "see section",
            h._pct(block.get("hold_avg", block.get("avg"))),
            h._num(block.get("hold_t", block.get("t"))),
            (block.get("verdict") or {}).get("result", "")))
    return rows


def _catalogue_results(groups, holdouts):
    by_name = {}
    for block in holdouts:
        by_name[block["name"]] = block
    results = []
    for blocks in groups:
        for block in blocks:
            hold = by_name.get(block["name"])
            mark = block.get("mark")
            if mark == "needs new data":
                note = "In-sample PASS. The family has used its one holdout look. Needs new data."
                results.append({
                    "name": block["name"],
                    "attempt": 17,
                    "in_sample": "PASS",
                    "mark": "needs new data",
                    "holdout": None,
                    "note": note,
                })
                continue
            verdict = (block.get("verdict") or {}).get("result", "")
            note = verdict
            hold_rec = None
            if hold is not None:
                note = "%s Holdout %s, avg %s, t %s." % (
                    verdict,
                    (hold.get("verdict") or {}).get("result", ""),
                    h._pct(hold.get("hold_avg", hold.get("avg"))),
                    h._num(hold.get("hold_t", hold.get("t"))))
                hold_rec = {
                    "avg": hold.get("hold_avg", hold.get("avg")),
                    "t": hold.get("hold_t", hold.get("t")),
                }
            results.append({
                "name": block["name"],
                "attempt": 17,
                "in_sample": verdict,
                "holdout": hold_rec,
                "note": note,
            })
    return results


def report_text(stamp, rel, tom, rotation, holdouts, entries, flags):
    lines = [rules_text(stamp).rstrip(), "", "Results.", ""]
    lines.append("Sector-relative RSI. Delivery costs, Rs 1,00,000. t versus same-month random entries.")
    lines.extend(family_table(rel, [
        "variant", "trades", "avg", "t", "2005-2014", "2015-2024",
        "up", "down", "sideways", "large", "result",
    ]))
    for block in rel:
        lines.append(_reasons(block))
    lines.append("")
    lines.append("Turn of the month. (a) is the attempt 16 futures rule. (b) and (c) are delivery baskets.")
    lines.extend(family_table(tom, [
        "variant", "trades", "avg", "t", "2005-2014", "2015-2024",
        "up", "down", "sideways", "result",
    ]))
    for block in tom:
        lines.append(_reasons(block))
    lines.append("")
    lines.append("Sector rotation. Index ETFs, delivery costs, two sectors, Monday to Monday.")
    lines.extend(family_table(rotation, [
        "variant", "trades", "avg", "t", "2005-2014", "2015-2024",
        "up", "down", "sideways", "result",
    ]))
    for block in rotation:
        lines.append(_reasons(block))
    lines.append("")
    lines.append("Holdout.")
    if not holdouts:
        lines.append("No fresh family passed in sample, so no holdout was run.")
    for block in holdouts:
        lines.append("%s | avg %s | t %s | %s" % (
            block["name"],
            h._pct(block.get("hold_avg", block.get("avg"))),
            h._num(block.get("hold_t", block.get("t"))),
            (block.get("verdict") or {}).get("result", "")))
        lines.append(_reasons(block))
    lines.append("")
    lines.append("Families.")
    for name in (
        "opening-range breakout", "single technical signal", "momentum", "rsi2",
        "pairs", "holy grail", "calendar", "sector-relative rsi",
        "turn of the month", "sector rotation",
    ):
        lines.append("%s: %s" % (name, flags.get(name, "no")))
    lines.append("")
    lines.append("Bucket list.")
    for tier in ("Bucket", "Watch", "Investing", "Near-miss", "Closed"):
        rows = [item["name"] for item in entries if item["tier"] == tier]
        lines.append("%s: %s" % (tier, ", ".join(rows) if rows else "none"))
    return "\n".join(lines).rstrip() + "\n"


def main(argv=None, log=None):
    import argparse
    parser = argparse.ArgumentParser(description="Attempt 17. Nothing is placed.")
    parser.add_argument("--root", default=os.path.join("data", "kite"))
    parser.add_argument("--experiments", default=h.EXPERIMENTS)
    parser.add_argument("--catalogue", default=CATALOGUE)
    parser.add_argument("--industries", default=os.path.join(_ROOT, "india", "universe", "nifty500.csv"))
    parser.add_argument("--runs", type=int, default=h.RUNS)
    args = parser.parse_args(argv)
    emit = log or (lambda line: print(line, flush=True))
    stamp = datetime.date.today().isoformat()
    f.install_attempt(args.experiments, 17, rules_text(stamp), [])
    emit("rules for attempt 17 written to %s before the run" % args.experiments)
    update_catalogue(args.catalogue, [])
    emit("tom near-miss and the holdout column written before the run")
    industries = b16.load_industries(args.industries)
    emit("loading stocks through %s" % h.END.isoformat())
    ctx = prepare_context(args.root, h.END, emit, False)
    mapped = attach_relative(ctx, industries)
    emit("mapped stocks %d" % mapped)
    rel = run_rel(ctx, f.SWING_START, h.END, args.runs, emit)
    tom = run_tom(ctx, f.SWING_START, h.END, args.runs, emit)
    rotation = run_rotation(ctx, f.SWING_START, h.END, args.runs, emit)
    groups = (rel, tom, rotation)
    flat = []
    for blocks in groups:
        flat.extend(blocks)
    holdouts = run_holdout(args.root, flat, industries, args.runs, emit)
    waiting = [block for block in flat if block.get("mark") == "needs new data"]
    results = _catalogue_results(groups, holdouts)
    entries = update_catalogue(args.catalogue, results)
    text = report_text(stamp, rel, tom, rotation, holdouts, entries, FAMILY_USED)
    f.install_attempt(
        args.experiments, 17, text,
        table_rows(stamp, groups, holdouts, waiting))
    columns = {
        "rel": ["variant", "trades", "avg", "t", "2005-2014", "2015-2024", "up", "down", "sideways", "large", "result"],
        "tom": ["variant", "trades", "avg", "t", "2005-2014", "2015-2024", "up", "down", "sideways", "result"],
        "rot": ["variant", "trades", "avg", "t", "2005-2014", "2015-2024", "up", "down", "sideways", "result"],
    }
    emit("Sector-relative RSI")
    for line in family_table(rel, columns["rel"]):
        emit(line)
    for block in rel:
        emit(_reasons(block))
    emit("Turn of the month")
    for line in family_table(tom, columns["tom"]):
        emit(line)
    for block in tom:
        emit(_reasons(block))
    emit("Sector rotation")
    for line in family_table(rotation, columns["rot"]):
        emit(line)
    for block in rotation:
        emit(_reasons(block))
    emit("Holdout")
    if not holdouts and not waiting:
        emit("No fresh family passed in sample, so no holdout was run.")
    for block in waiting:
        emit(_reasons(block))
    for block in holdouts:
        emit("%s | avg %s | t %s | %s" % (
            block["name"],
            h._pct(block.get("hold_avg", block.get("avg"))),
            h._num(block.get("hold_t", block.get("t"))),
            (block.get("verdict") or {}).get("result", "")))
        emit(_reasons(block))
    emit("Bucket list")
    for tier in ("Bucket", "Watch", "Investing", "Near-miss", "Closed"):
        rows = [item["name"] for item in entries if item["tier"] == tier]
        emit("%s: %s" % (tier, ", ".join(rows) if rows else "none"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
