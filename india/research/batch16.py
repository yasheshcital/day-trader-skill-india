#!/usr/bin/env python3
"""Attempt 16: pairs, Holy Grail, calendar, and mixes.

Rules are written to EXPERIMENTS.md before the run. The 2005-2024 window
stays closed to 2025 until a variant passes, and then one holdout load
uses final=True. Nothing is placed.

    python3 india/research/batch16.py
"""

import bisect
import csv
import datetime
import math
import os
import random
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from india.nse_market import tick_for
from india.research import data
from india.research import follow as f
from india.research import harness as h
from india.research import signal_lab as lab
from india.research import ta
from india.research import verify as v

# Futures schedule. Check your broker: these are not a live contract note.
BROKERAGE = 20.0
STT_SELL_PCT = 0.05
EXCHANGE_PCT = 0.00173
SEBI_PCT = 0.0001
STAMP_BUY_PCT = 0.002
GST_PCT = 18.0

LEG = 100000.0
GROSS = 200000.0
CAPITAL = 1000000.0
PAIR_SLOTS = 20
LOT = 75
FORM_MONTHS = (1, 7)
FORM_MIN = 120
Z_N = 60
Z_ENTER = 2.0
Z_STOP = 4.0
Z_MAX = 20
GRAIL_DAYS = 10
ADX_N = 14
EMA_N = 20
PAIRS_SEED = 40000
GRAIL_SEED = 50000
MIX_SEED = 60000
CAL_SEED = 70000
HOLDOUT = data.HOLDOUT_START
CATALOGUE = h.CATALOGUE
HDFC = (
    "PASS in-sample, but inflated by survivorship bias; real NIFTY200 Momentum 30 TRI: "
    "18.8% CAGR vs NIFTY 50 TRI 13.6% since Apr 2005 (HDFC MF, Jul 2026)"
)

SOURCES = "\n".join([
    "| Strategy | Source | Horizon | Status | Attempt |",
    "|---|---|---|---|---|",
    "| Turtle breakout | Richard Dennis and William Eckhardt, the 1983 rules, published by Curtis Faith, Way of the Turtle (2007) | daily | batch 1 | 11 |",
    "| Cross-sectional momentum | Jegadeesh and Titman (1993), Journal of Finance, \"Returns to Buying Winners and Selling Losers\" | monthly | batch 1 | 11 |",
    "| 52-week-high momentum | George and Hwang (2004), Journal of Finance | monthly | batch 1 | 11 |",
    "| Minervini trend template + VCP | Mark Minervini, Trade Like a Stock Market Wizard (2013), trend template and volatility contraction | daily | not started | |",
    "| Weinstein stage analysis | Stan Weinstein, Secrets for Profiting in Bull and Bear Markets (1988) | weekly and daily | not started | |",
    "| Darvas box | Nicolas Darvas, How I Made $2,000,000 in the Stock Market (1960) | daily | not started | |",
    "| Time-series momentum / Faber 10-month timing | Moskowitz, Ooi and Pedersen (2012) for time-series momentum; Meb Faber, \"A Quantitative Approach to Tactical Asset Allocation\" (2007), for the 10-month average | monthly | batch 1 (Faber timing); full TSMOM not started | 11 |",
    "| Connors RSI(2) | Larry Connors, Short Term Trading Strategies That Work (2008) | daily | not started | |",
    "| IBS | (close - low) / (high - low). Larry Connors, and the 2013 Pagonidis note \"The IBS Effect\" | daily | not started | |",
    "| Short-term reversal | Jegadeesh (1990), Journal of Finance | daily to monthly | not started | |",
    "| Pairs trading | Gatev, Goetzmann and Rouwenhorst (2006), Review of Financial Studies | daily | not started | |",
    "| Turtle Soup | Raschke and Connors, Street Smarts (1996) | daily | not started | |",
    "| Crabel NR7/NR4 | Toby Crabel, Day Trading with Short Term Price Patterns and Opening Range Breakout (1990) | daily | not started | |",
    "| Raschke Holy Grail | Linda Raschke, Street Smarts (1996), the ADX pullback | daily | not started | |",
    "| Intraday momentum (Gao et al. 2018) | Gao, Han, Li and Zhou (2018), Journal of Financial Economics, \"Market intraday momentum\" | intraday | not started | |",
    "| Gap and go vs gap fade | Practitioner opening-gap pattern. No single paper | intraday | not started | |",
    "| VWAP reversion | Berkowitz, Logue and Noser (1988) introduced VWAP. Reversion to it is a practitioner intraday strategy | intraday | not started | |",
    "| Turn of the month | Ariel (1987), Journal of Financial Economics | daily, around month-end | not started | |",
    "| F&O expiry week | NSE monthly derivatives expiry, the last Thursday. An India calendar effect | daily, expiry week | not started | |",
    "| Volatility-regime switching | Hamilton (1989); Moreira and Muir (2017), \"Volatility-Managed Portfolios\" | daily to monthly | not started | |",
])


def futures_side(value, buying):
    """Rupees charged on one futures order. GST is on brokerage, exchange and SEBI."""
    if value <= 0:
        return 0.0
    exchange = value * EXCHANGE_PCT / 100.0
    sebi = value * SEBI_PCT / 100.0
    stt = 0.0 if buying else value * STT_SELL_PCT / 100.0
    stamp = value * STAMP_BUY_PCT / 100.0 if buying else 0.0
    gst = (BROKERAGE + exchange + sebi) * GST_PCT / 100.0
    return BROKERAGE + stt + exchange + sebi + stamp + gst


def round_trip(value):
    return futures_side(value, True) + futures_side(value, False)


def rollover_count(entry, exit):
    """Month-ends strictly after the entry date and on or before the exit date."""
    if exit <= entry:
        return 0
    count = 0
    year = entry.year
    month = entry.month
    while True:
        if month == 12:
            year += 1
            month = 1
        else:
            month += 1
        first = datetime.date(year, month, 1)
        if first > exit:
            break
        if first > entry:
            count += 1
    return count


def leg_pnl(entry_px, exit_px, long_side, rolls, leg):
    """Rupee P&L of one leg. Rolls add one round trip on the opening notional."""
    if not entry_px > 0 or not exit_px > 0 or leg <= 0:
        return None
    if long_side:
        buy_val = leg
        sell_val = leg * exit_px / entry_px
        gross = sell_val - buy_val
        cost = futures_side(buy_val, True) + futures_side(sell_val, False)
    else:
        sell_val = leg
        buy_val = leg * exit_px / entry_px
        gross = sell_val - buy_val
        cost = futures_side(sell_val, False) + futures_side(buy_val, True)
    cost += rolls * round_trip(leg)
    return gross - cost


def pair_pnl(entry_a, exit_a, entry_b, exit_b, long_a, rolls, leg):
    first = leg_pnl(entry_a, exit_a, long_a, rolls, leg)
    second = leg_pnl(entry_b, exit_b, not long_a, rolls, leg)
    if first is None or second is None:
        return None
    return first + second


def pair_return(entry_a, exit_a, entry_b, exit_b, long_a, rolls, leg=LEG):
    """Percent of the two-leg gross. The default gross is Rs 2,00,000."""
    pnl = pair_pnl(entry_a, exit_a, entry_b, exit_b, long_a, rolls, leg)
    if pnl is None or not leg > 0:
        return None
    return pnl / (2.0 * leg) * 100.0


def dmi_adx(high, low, close, n=ADX_N):
    """Wilder +DI, -DI and ADX. The first ADX is the mean of the first n DX values."""
    m = len(close)
    adx = [None] * m
    plus = [None] * m
    minus = [None] * m
    if n <= 0 or m <= n:
        return adx, plus, minus
    trs = [0.0] * m
    pdm = [0.0] * m
    mdm = [0.0] * m
    for i in range(1, m):
        up = high[i] - high[i - 1]
        down = low[i - 1] - low[i]
        if up > down and up > 0:
            pdm[i] = up
        if down > up and down > 0:
            mdm[i] = down
        trs[i] = ta.true_range(high[i], low[i], close[i - 1])
    tr_s = 0.0
    p_s = 0.0
    m_s = 0.0
    for i in range(1, n + 1):
        tr_s += trs[i]
        p_s += pdm[i]
        m_s += mdm[i]
    dxs = [0.0] * m

    def store(i, tr_sum, p_sum, m_sum):
        if tr_sum <= 0:
            plus[i] = 0.0
            minus[i] = 0.0
            dxs[i] = 0.0
            return
        plus[i] = 100.0 * p_sum / tr_sum
        minus[i] = 100.0 * m_sum / tr_sum
        den = plus[i] + minus[i]
        if den == 0:
            dxs[i] = 0.0
            return
        diff = plus[i] - minus[i]
        if diff < 0:
            diff = -diff
        dxs[i] = 100.0 * diff / den

    store(n, tr_s, p_s, m_s)
    for i in range(n + 1, m):
        tr_s = tr_s - (tr_s / float(n)) + trs[i]
        p_s = p_s - (p_s / float(n)) + pdm[i]
        m_s = m_s - (m_s / float(n)) + mdm[i]
        store(i, tr_s, p_s, m_s)
    if m <= 2 * n - 1:
        return adx, plus, minus
    total = 0.0
    for i in range(n, 2 * n):
        total += dxs[i]
    prev = total / float(n)
    adx[2 * n - 1] = prev
    for i in range(2 * n, m):
        prev = (prev * float(n - 1) + dxs[i]) / float(n)
        adx[i] = prev
    return adx, plus, minus


def z_at(values, i, n=Z_N):
    """Population z-score of values[i] over the n values ending at i."""
    if i < n - 1:
        return None
    window = values[i - n + 1:i + 1]
    for value in window:
        if value is None:
            return None
    mean = 0.0
    for value in window:
        mean += value
    mean /= float(n)
    var = 0.0
    for value in window:
        var += (value - mean) ** 2
    var /= float(n)
    if var == 0.0:
        return None
    return (values[i] - mean) / (var ** 0.5)


def walk_z(zs, max_days=Z_MAX):
    """Enter at |z| > 2, stop at |z| > 4, exit on a cross of 0, else day 20.

    The entry index is day 1. The time stop is the close max_days - 1 steps
    later. The stop is checked before the zero cross.
    """
    trades = []
    pos = None
    last = len(zs) - 1
    for i, z in enumerate(zs):
        if pos is not None:
            entry_i, short_first = pos
            stop = z is not None and (z > Z_STOP or z < -Z_STOP)
            cross = z is not None and (
                z == 0.0 or (short_first and z < 0) or ((not short_first) and z > 0))
            timed = i - entry_i >= max_days - 1
            if stop or cross or timed or i == last:
                trades.append((entry_i, i, not short_first))
                pos = None
            continue
        if z is None or i >= last:
            continue
        if z > Z_ENTER or z < -Z_ENTER:
            pos = (i, z > 0)
    return trades


def spread_stats(a_closes, b_closes):
    """SSD, population std around the mean, and the two base closes."""
    if not a_closes or len(a_closes) != len(b_closes):
        return None
    a0 = a_closes[0]
    b0 = b_closes[0]
    if not a0 > 0 or not b0 > 0:
        return None
    gaps = []
    ssd = 0.0
    for i in range(len(a_closes)):
        gap = a_closes[i] / a0 - b_closes[i] / b0
        gaps.append(gap)
        ssd += gap * gap
    n = len(gaps)
    mean = sum(gaps) / float(n)
    var = 0.0
    for gap in gaps:
        var += (gap - mean) ** 2
    var /= float(n)
    return ssd, var ** 0.5, mean, a0, b0


def choose_pairs(series, industries, limit, same):
    """Smallest SSD first. `series` maps a symbol to its formation closes."""
    names = sorted(series)
    scored = []
    for i, a in enumerate(names):
        ind_a = industries.get(a) or ""
        for b in names[i + 1:]:
            ind_b = industries.get(b) or ""
            if same and (not ind_a or ind_a != ind_b):
                continue
            stats = spread_stats(series[a], series[b])
            if stats is None:
                continue
            ssd, std, mean, a0, b0 = stats
            scored.append((ssd, a, b, std, mean, a0, b0))
    scored.sort()
    return scored[:limit]


def distance_trades(rows, mean, std):
    """Open beyond 2 std from the formation mean. Close when the raw gap crosses 0.

    rows are (date, close_a, close_b) already divided by the formation bases,
    so the values ARE the normalised prices. No entry on the last row.
    """
    trades = []
    pos = None
    last = len(rows) - 1
    for i, row in enumerate(rows):
        gap = row[1] - row[2]
        if pos is None:
            if i >= last or not std > 0:
                continue
            if gap > mean + 2.0 * std:
                pos = (i, False)
            elif gap < mean - 2.0 * std:
                pos = (i, True)
            continue
        entry_i, long_a = pos
        crossed = gap == 0.0 or (long_a and gap > 0.0) or ((not long_a) and gap < 0.0)
        if crossed or i == last:
            trades.append((entry_i, i, long_a))
            pos = None
    return trades


def on_or_after(day, calendar):
    if not calendar:
        return None
    i = bisect.bisect_left(calendar, day)
    if i >= len(calendar):
        return None
    return calendar[i]


def on_or_before(day, calendar):
    if not calendar:
        return None
    i = bisect.bisect_right(calendar, day) - 1
    if i < 0:
        return None
    return calendar[i]


def last_thursday(year, month):
    if month == 12:
        nxt = datetime.date(year + 1, 1, 1)
    else:
        nxt = datetime.date(year, month + 1, 1)
    last = nxt - datetime.timedelta(days=1)
    back = (last.weekday() - 3) % 7
    return last - datetime.timedelta(days=back)


def expiry_day(year, month, calendar):
    """Last Thursday, or the previous session when that Thursday is not one."""
    return on_or_before(last_thursday(year, month), calendar)


def ols_beta(xs, ys):
    n = len(xs)
    if n < 3:
        return None
    mx = sum(xs) / float(n)
    my = sum(ys) / float(n)
    var = 0.0
    cov = 0.0
    for i in range(n):
        dx = xs[i] - mx
        var += dx * dx
        cov += dx * (ys[i] - my)
    if var == 0.0:
        return None
    return cov / var


def pearson(xs, ys):
    n = len(xs)
    if n < 3 or n != len(ys):
        return None
    mx = sum(xs) / float(n)
    my = sum(ys) / float(n)
    num = 0.0
    vx = 0.0
    vy = 0.0
    for i in range(n):
        dx = xs[i] - mx
        dy = ys[i] - my
        num += dx * dy
        vx += dx * dx
        vy += dy * dy
    if vx == 0.0 or vy == 0.0:
        return None
    return num / ((vx * vy) ** 0.5)


def month_returns(calendar, equity):
    last = {}
    for day, value in zip(calendar, equity):
        last[(day.year, day.month)] = value
    prev = None
    keys = []
    out = []
    for key in sorted(last):
        value = last[key]
        if prev is not None and prev > 0 and value > 0:
            keys.append(key)
            out.append((value / prev - 1.0) * 100.0)
        prev = value
    return keys, out


def top_fraction(scored, numer, denom):
    """Highest score first, then the name. Count is n * numer // denom."""
    ordered = sorted(scored, key=lambda item: (-item[0], item[1]))
    count = len(ordered) * numer // denom
    if count < 0:
        count = 0
    return [item[1] for item in ordered[:count]]


def momentum_12_1(seg, i):
    """Close 21 sessions ago over the close 252 sessions ago, minus 1."""
    if i < 252:
        return None
    base = seg.c[i - 252]
    prev = seg.c[i - 21]
    if not base > 0 or not prev > 0:
        return None
    return prev / base - 1.0


def grail_signal(seg, i, adx_min, need_sma):
    if i < 0 or i + 1 >= len(seg.c):
        return False
    adx = seg.adx[i]
    plus = seg.plus_di[i]
    minus = seg.minus_di[i]
    ema = seg.ema20[i]
    if adx is None or plus is None or minus is None or ema is None:
        return False
    if not adx > adx_min or not plus > minus:
        return False
    if not (seg.l[i] <= ema <= seg.h[i]):
        return False
    if need_sma:
        sma = seg.sma200[i]
        if sma is None or not seg.c[i] > sma:
            return False
    return True


def grail_fill(seg, i, symbol):
    """Buy stop one tick above the pullback high. No fill returns None.

    A next-day open at or above the stop fills at the open. A later trade
    at the stop fills at the stop.
    """
    tick = tick_for(seg.h[i], symbol)
    stop_px = seg.h[i] + tick
    nxt = i + 1
    if nxt >= len(seg.h) or not stop_px > 0:
        return None
    if seg.o[nxt] >= stop_px:
        return nxt, seg.o[nxt], True
    if seg.h[nxt] >= stop_px:
        return nxt, stop_px, False
    return None


def grail_exit(seg, entry_i, stop, target):
    """Stop before target. The entry session is day 1. Day 10 exits at the close."""
    last = entry_i + GRAIL_DAYS - 1
    if entry_i < 0 or last >= len(seg.c) or not stop > 0 or not target > stop:
        return None
    for j in range(entry_i, last + 1):
        if seg.o[j] <= stop:
            return j, seg.o[j], True
        if seg.l[j] <= stop:
            return j, stop, False
        if seg.h[j] >= target:
            return j, target, False
    return last, seg.c[last], False


def load_industries(path):
    out = {}
    if not path or not os.path.isfile(path):
        return out
    with open(path, newline="") as fh:
        for row in csv.DictReader(fh):
            symbol = (row.get("Symbol") or "").strip()
            industry = (row.get("Industry") or "").strip()
            if symbol:
                out[symbol] = industry
    return out


def closes_for(by_name, symbol, dates):
    """Closes on every date, one segment. None when any session is missing."""
    loc = by_name.get(symbol)
    if loc is None:
        return None
    seg = None
    out = []
    for day in dates:
        found = loc.get(day)
        if found is None:
            return None
        this, i = found
        if seg is None:
            seg = this
        elif this is not seg:
            return None
        px = this.c[i]
        if not px > 0:
            return None
        out.append(px)
    return out


def formation_starts(calendar):
    found = []
    if not calendar:
        return found
    first = calendar[0].year
    last = calendar[-1].year
    for year in range(first + 1, last + 1):
        for month in FORM_MONTHS:
            day = on_or_after(datetime.date(year, month, 1), calendar)
            if day is not None and day <= calendar[-1]:
                found.append(day)
    return found


def window_dates(calendar, start, end):
    out = []
    for day in calendar:
        if day < start:
            continue
        if day >= end:
            break
        out.append(day)
    return out


def attach_extra(segments):
    f.attach_indicators(segments)
    for seg in segments:
        seg.ema20 = ta.ema_series(seg.c, EMA_N)
        adx, plus, minus = dmi_adx(seg.h, seg.l, seg.c, ADX_N)
        seg.adx = adx
        seg.plus_di = plus
        seg.minus_di = minus


def _mean_of(values):
    return h._mean(values)


def trade_slices(trades):
    early = []
    late = []
    buckets = {"up": [], "down": [], "sideways": []}
    large = []
    for trade in trades:
        ret = trade["ret"]
        year = trade["date"].year
        if 2005 <= year <= 2014:
            early.append(ret)
        if 2015 <= year <= 2024:
            late.append(ret)
        kind = trade.get("regime")
        if kind in buckets:
            buckets[kind].append(ret)
        if trade.get("large"):
            large.append(ret)
    return {
        "early": _mean_of(early),
        "late": _mean_of(late),
        "up": _mean_of(buckets["up"]),
        "down": _mean_of(buckets["down"]),
        "sideways": _mean_of(buckets["sideways"]),
        "large": _mean_of(large),
    }


def judge_event(block, family, t_label):
    """Avg above 0, t above 3, both decades, each market type, and 2 of 3."""
    reasons = []
    if block["avg"] is None or not block["avg"] > 0:
        reasons.append("avg after costs %s is not above 0" % h._pct(block["avg"]))
    if block["t"] is None or not block["t"] > 3:
        reasons.append("%s %s is not above 3" % (t_label, h._num(block["t"])))
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


def judge_mix(block, require_down):
    """Attempt 14 clauses for one mix. The 2-of-3 family count is not applied."""
    reasons = []
    if block["avg"] is None or not block["avg"] > 0:
        reasons.append("avg return after costs %s is not above 0" % h._pct(block["avg"]))
    if block["t"] is None or not block["t"] > 3:
        reasons.append("t vs random %s is not above 3" % h._num(block["t"]))
    checks = [
        ("early", "2005-2014"),
        ("late", "2015-2024"),
        ("up", "up"),
        ("sideways", "sideways"),
        ("large", "large caps"),
    ]
    if require_down:
        checks.append(("down", "down"))
    for key, label in checks:
        if block.get(key) is None or not block[key] > 0:
            reasons.append("%s %s is not above 0" % (label, h._pct(block.get(key))))
    return {"result": "PASS" if not reasons else "FAIL", "reasons": reasons}


def nifty_monthly_t(trades):
    """One-sample t of the monthly mean of return minus the NIFTY return."""
    by_month = {}
    for trade in trades:
        if trade.get("mkt") is None:
            continue
        key = (trade["date"].year, trade["date"].month)
        by_month.setdefault(key, []).append(trade["ret"] - trade["mkt"])
    monthly = []
    for key in sorted(by_month):
        monthly.append(h._mean(by_month[key]))
    return h.t_stat(monthly)


def judge_holdout(avg, t):
    reasons = []
    if avg is None or not avg > 0:
        reasons.append("avg after costs %s is not above 0" % h._pct(avg))
    if t is None or not t > 2:
        reasons.append("t %s is not above 2" % h._num(t))
    return {"result": "PASS" if not reasons else "FAIL", "reasons": reasons}


def tier_of(in_sample, avg, t):
    """Bucket, Watch, or Closed. Investing and Near-miss stay in the history list."""
    if in_sample != "PASS":
        return "Closed"
    if avg is not None and t is not None and avg > 0 and t > 2:
        return "Bucket"
    if avg is not None and avg > 0:
        return "Watch"
    return "Closed"


def history_entries():
    """Attempts 1 to 15, placed before attempt 16 is measured."""
    return [
        {"name": "rsi2 < 5", "tier": "Watch", "attempt": "14, 15",
         "note": "In-sample PASS. Holdout average after costs +0.327% and excess t +1.42."},
        {"name": "mom 12-1 K20 above200", "tier": "Investing", "attempt": "11",
         "note": HDFC},
        {"name": "rev K20", "tier": "Near-miss", "attempt": "14",
         "note": "Cleared every attempt 14 clause except the family gate, 1 of 3 with t above 2."},
        {"name": "Faber timing", "tier": "Near-miss", "attempt": "11",
         "note": "faber 10m, faber 8m and faber 12m. The monthly t was negative."},
        {"name": "Opening-range breakout", "tier": "Closed", "attempt": "1-8",
         "note": "The intraday opening-range family."},
        {"name": "20d-high / sma20-close and engulf-low / hold-20", "tier": "Closed", "attempt": "9",
         "note": "In-sample PASS. No 2025 holdout was run."},
        {"name": "Attempt 10 single signals", "tier": "Closed", "attempt": "10",
         "note": "The remaining entry and exit pairs."},
        {"name": "Turtle, 52-week high, mom 12-1 K20, mom 12-1 K30", "tier": "Closed", "attempt": "11",
         "note": "Failed the attempt 11 path. The above-200 momentum book is in Investing."},
        {"name": "Attempt 12 intraday batch", "tier": "Closed", "attempt": "12",
         "note": "0 of 12 passed."},
        {"name": "Big-gap continuation", "tier": "Closed", "attempt": "13",
         "note": "0 of 3 passed."},
        {"name": "rsi2 < 10 and rsi2 < 10 down2", "tier": "Closed", "attempt": "14, 15",
         "note": "In-sample PASS. The holdout was rsi2 < 5 only, and the index test failed."},
        {"name": "IBS, turtle soup, rev K10, rev K10 above200", "tier": "Closed", "attempt": "14",
         "note": "Failed the attempt 14 mark. rev K20 is the near-miss."},
        {"name": "Index RSI(2)", "tier": "Closed", "attempt": "15",
         "note": "The survivorship-free index test failed on the pooled excess t."},
    ]


def render_catalogue(entries):
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
    ]
    order = ("Bucket", "Watch", "Investing", "Near-miss", "Closed")
    blurbs = {
        "Bucket": "In-sample PASS and holdout PASS.",
        "Watch": "In-sample PASS, holdout average after costs above 0, t not above 2.",
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
    lines.append(SOURCES)
    lines.append("")
    return "\n".join(lines)


def update_tiers(path, results):
    """Rewrite the tier sections from attempts 1-15 plus this attempt's results.

    A historical name keeps its tier. A new name is Bucket, Watch, or Closed
    from `tier_of`. Investing and Near-miss are not assigned automatically.
    """
    entries = history_entries()
    known = {}
    for item in entries:
        known[item["name"]] = item
    for result in results:
        name = result["name"]
        if name in known:
            continue
        hold = result.get("holdout")
        avg = None if hold is None else hold.get("avg")
        tstat = None if hold is None else hold.get("t")
        tier = tier_of(result.get("in_sample"), avg, tstat)
        entries.append({
            "name": name,
            "tier": tier,
            "attempt": str(result.get("attempt", 16)),
            "note": result.get("note") or tier,
        })
    text = render_catalogue(entries)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
    return entries


def rules_text(stamp):
    """Attempt 16 rules. No measured result belongs in this text."""
    return "\n".join([
        "## Attempt 16",
        "",
        "Rules fixed on %s, before the run." % stamp,
        "",
        "Four families on 2005-01-01 through 2024-12-31. No 5-minute bars are "
        "used. Dates from 2025-01-01 on are not requested until a variant passes, "
        "and then only in the one holdout load. Dividends are excluded. Nothing "
        "is placed. Spot prices are the futures proxy for every futures rule, "
        "and the report says so.",
        "",
        "Futures costs, check your broker. Brokerage Rs 20 an order. STT 0.05% "
        "of sell value. Exchange 0.00173% of both sides. SEBI 0.0001% of both "
        "sides. Stamp 0.002% of buy value. GST 18% of brokerage plus exchange "
        "plus SEBI. STT and stamp are outside the GST base. One extra round "
        "trip per leg is charged for each month-end strictly after the entry "
        "date and on or before the exit date. A pair that opens and closes in "
        "the same month pays no rollover.",
        "",
        "1. Pairs. Market-neutral, both legs treated as stock futures. Universe "
        "on the formation date: the top 200 by prior 60-session turnover. "
        "Industry is the Industry column of india/universe/nifty500.csv. A "
        "blank industry is not a match. Rs 1,00,000 notional per leg, so the "
        "per-trade average is on Rs 2,00,000 gross. Every 6 months, on the "
        "first NIFTY session of January and of July, form on the sessions from "
        "the same month a year earlier up to the session before the formation "
        "date. A name must have a close on every one of those sessions, inside "
        "one segment, and there must be at least 120 of them. Both prices are "
        "divided by their first formation close. The score is the sum of "
        "squared differences. The formation mean and the population standard "
        "deviation of that normalised gap are saved. The next window runs until "
        "the day before the next formation date. Marks use sessions where both "
        "names have a close. (a) The 20 same-industry pairs with the smallest "
        "score. Open when the live gap is strictly more than 2 standard "
        "deviations from the formation mean. Long the cheaper normalised "
        "price, short the dearer, at that close. Close when the raw normalised "
        "gap crosses zero, or at the last common close of the window. A "
        "standard deviation of 0 opens nothing. Exactly 2 standard deviations "
        "does not open. (b) The same rule with any industry allowed. (c) The "
        "same 20 same-industry pairs as (a). The z-score is the population "
        "z-score of the log price ratio over the 60 closes ending that day. "
        "Enter at the close when the absolute z is strictly above 2, short the "
        "richer name. Exit at the close when the absolute z is strictly above "
        "4 (checked first), or when z crosses 0, or at the close of day 20 "
        "counting the entry session as day 1. One position per pair. The "
        "portfolio funds 20 slots from Rs 10,00,000, so each leg of each slot "
        "is Rs 25,000, including a slot that is flat. Idle cash earns 0. The "
        "market beta is the OLS slope, with an intercept, of the book's daily "
        "percent change on NIFTY's close-to-close percent change, using only "
        "days when a pair is open. The monthly t is the one-sample t of the "
        "book's month-end percent returns. Decades and market types are the "
        "mean per-trade return by the entry date. Large caps, both legs in "
        "the top 100 that day, are reported and are not a pass clause.",
        "",
        "2. Holy Grail, stocks, daily, delivery costs, Rs 1,00,000 a trade, "
        "top 200 on the pullback day. ADX(14) and +DI and -DI are Wilder. "
        "EMA20 is ta.ema_series. The pullback day has ADX strictly above the "
        "threshold, +DI strictly above -DI, and a low at or below EMA20 with "
        "a high at or above it. The next session buys on a stop one tick, from "
        "nse_market.tick_for, above that day's high. An open at or above the "
        "stop fills at the open. Otherwise a high at or above the stop fills "
        "at the stop. No fill, no trade. The protective stop is the pullback "
        "day's low. The target is the fill plus 2 times (fill minus that low). "
        "A gap through the stop fills at the open, a low through the stop "
        "fills at the stop, and the stop is taken before the target. If "
        "neither is hit, sell at the close of the 10th session, counting the "
        "entry session as day 1. A trade that would need a later session is "
        "skipped. Variants: ADX above 30; ADX above 25; ADX above 30 and the "
        "pullback close strictly above SMA200. Exactly 30 fails the first and "
        "the third. Random entries, 100 runs, seed 20261106 + 50000 + variant "
        "index times 1000 + the run index, are same-month top-200 days of the "
        "same symbol. The signal is not required. The same stop, target and "
        "10-day exit are applied from that day. The t is the attempt 14 "
        "market-adjusted t versus those entries.",
        "",
        "3. Calendar on NIFTY 50, futures costs, one lot of 75. The return is "
        "the rupee P&L divided by 75 times the entry price. (a) Turn of the "
        "month: long from the close of the session before the last session of "
        "the month to the close of the third session of the next month. (b) "
        "Expiry week: long from the Monday open of the expiry week to the "
        "expiry close. Expiry is the last Thursday, or the previous NIFTY "
        "session when that Thursday is not a session. The Monday, when it is "
        "not a session, moves to the next session that is still on or before "
        "the expiry. Expiry-day changes after 2024 are outside this window, "
        "and a holdout of this rule keeps the last-Thursday definition. (c) "
        "The week after expiry: long from that next Monday's open to that "
        "Friday's close, moving either end onto a NIFTY session inside the "
        "week. The baseline is 100 other windows in the same calendar year "
        "with the same session count, not starting on the real entry date. "
        "Seed 20261106 + 70000 + variant index times 1000, then the event "
        "index. The average that must be above 0 is the trade's own return "
        "after costs. The monthly t is the one-sample t of (that return minus "
        "the mean of the same-year random windows). A year with no other "
        "window leaves the trade in the average and out of the t. Decades and "
        "market types use the trade's own return and the entry date's regime.",
        "",
        "4. Mixes. (m1) rsi2 < 5, the attempt 14 rule, and the signal-day name "
        "is in the top 30% of that day's top 200 by 12-1 momentum. 12-1 is the "
        "close 21 sessions before the signal divided by the close 252 sessions "
        "before it, minus 1, inside one segment. The count is n times 30 "
        "divided by 100, truncating. Ties break on the symbol name. (m2) rsi2 "
        "< 5 only when the entry date's market type is up or sideways. "
        "Hypothesis from attempt 14's weak down bucket: the down average was "
        "the weak one, so this mix does not trade a down entry. An empty down "
        "bucket is reported and is not a failure. (m3) One Rs 10,00,000 book "
        "in two halves of Rs 5,00,000. The first half is rsi2 < 5 with 5 slots "
        "of Rs 1,00,000, lowest RSI then highest turnover, and a name sold at "
        "the open is not bought again that day. The second half is rev K20: "
        "every Monday, the 20 worst 5-session returns in the top 200, sold and "
        "bought again the next Monday so both costs apply. Each half parks "
        "idle cash in the NIFTY price with no funding cost. The same name may "
        "sit in both halves. The correlation is the Pearson correlation of "
        "the two halves' month-end percent returns.",
        "",
        "Pass marks, fixed before this run. Holy Grail uses the attempt 14 "
        "judge: average after costs above 0, t versus random above 3, both "
        "decades, up, down, sideways, large caps, and at least 2 of the 3 "
        "variants with t above 2. Pairs and calendar: average after costs "
        "above 0, monthly t above 3, above 0 in both decades and in each "
        "market type, and at least 2 of the 3 variants with t above 2. Large "
        "caps and the pairs beta are not pass clauses. m1 and m2 use the "
        "attempt 14 trade clauses and are not a three-variant family, so the "
        "2-of-3 count is not applied. m2 does not require a down average. m3 "
        "uses the attempt 11 path against NIFTY 50 buy-and-hold: excess t "
        "above 3, both decades, each market type, large-cap excess above 0, "
        "beats 95 of 100 random books, and either the drawdown path or the "
        "calmar path. The m3 random book keeps the same dates and replaces "
        "the names. A boundary stated as above is strict. At least 2 of 3 "
        "passes when the count is exactly 2. An empty required bucket fails.",
        "",
        "5. Every variant that PASSES gets one automatic holdout, after the "
        "in-sample run. One load_context with final=True, logged once, from "
        "2025-01-01 through the last NIFTY 50 daily date. Warmup before 2025 "
        "is used and is not a trade. An entry on or after 2025-01-01 counts. "
        "The signal rules are unchanged. Holdout PASS is average after costs "
        "above 0 and t above 2, and nothing else. For Holy Grail, m1 and m2 "
        "the holdout t is the one-sample t of the monthly mean of (return "
        "after costs minus the NIFTY price return over the trade), not versus "
        "a random entry. For pairs the holdout t is the same monthly book t. "
        "For calendar it is the same excess t versus same-year random windows. "
        "For m3 the average is the mean monthly book return and the t is the "
        "t of monthly excess versus NIFTY. The rule is not changed after the "
        "holdout. STRATEGIES.md is updated from these results at the end.",
    ])


def _event_block(name, trades, monthly):
    slices = trade_slices(trades)
    slices.update({
        "name": name,
        "trades": len(trades),
        "avg": _mean_of([item["ret"] for item in trades]),
        "t": h.t_stat(monthly),
        "rows": trades,
    })
    return slices


def _price_book(trades, calendar, nifty, closes):
    """Equity of 20 fixed slots. Daily P&L is marked from the previous close."""
    leg = CAPITAL / float(PAIR_SLOTS) / 2.0
    by_entry = {}
    for trade in trades:
        by_entry.setdefault(trade["entry"], []).append(trade)
    active = []
    cash = float(CAPITAL)
    equity = []
    open_flag = []
    for day in calendar:
        pnl = 0.0
        kept = []
        working = False
        for pos in active:
            ca = closes.get(pos["a"], {}).get(day)
            cb = closes.get(pos["b"], {}).get(day)
            if ca is None or cb is None:
                if day == pos["exit"]:
                    pnl -= pos["exit_cost"]
                else:
                    kept.append(pos)
                continue
            working = True
            if pos["long_a"]:
                pnl += leg * (ca - pos["prev_a"]) / pos["ea"]
                pnl += leg * (pos["prev_b"] - cb) / pos["eb"]
            else:
                pnl += leg * (cb - pos["prev_b"]) / pos["eb"]
                pnl += leg * (pos["prev_a"] - ca) / pos["ea"]
            pos["prev_a"] = ca
            pos["prev_b"] = cb
            month = (day.year, day.month)
            if month != (pos["entry"].year, pos["entry"].month) and pos.get("rolled") != month:
                pnl -= round_trip(leg) * 2.0
                pos["rolled"] = month
            if day == pos["exit"]:
                pnl -= pos["exit_cost"]
            else:
                kept.append(pos)
        for trade in by_entry.get(day, []):
            working = True
            entry_cost = futures_side(leg, True) + futures_side(leg, False)
            pnl -= entry_cost
            exit_cost = 0.0
            if trade["long_a"]:
                exit_cost += futures_side(leg * trade["xa"] / trade["ea"], False)
                exit_cost += futures_side(leg * trade["xb"] / trade["eb"], True)
            else:
                exit_cost += futures_side(leg * trade["xa"] / trade["ea"], True)
                exit_cost += futures_side(leg * trade["xb"] / trade["eb"], False)
            active_pos = {
                "a": trade["a"], "b": trade["b"], "exit": trade["exit"],
                "entry": trade["entry"], "long_a": trade["long_a"],
                "ea": trade["ea"], "eb": trade["eb"],
                "prev_a": trade["ea"], "prev_b": trade["eb"],
                "exit_cost": exit_cost, "rolled": None,
            }
            if day == trade["exit"]:
                pnl -= exit_cost
            else:
                kept.append(active_pos)
        active = kept
        cash += pnl
        equity.append(cash)
        open_flag.append(working)
    return equity, open_flag


def _beta(calendar, equity, flags, nifty):
    xs = []
    ys = []
    for i in range(1, len(calendar)):
        if not flags[i]:
            continue
        prev_e = equity[i - 1]
        prev_n = nifty.get(calendar[i - 1], {}).get("close")
        now_n = nifty.get(calendar[i], {}).get("close")
        if not prev_e > 0 or not prev_n or not now_n or not prev_n > 0 or not now_n > 0:
            continue
        ys.append(equity[i] / prev_e - 1.0)
        xs.append(now_n / prev_n - 1.0)
    return ols_beta(xs, ys)


def run_pairs(ctx, industries, start, end, log):
    emit = log or (lambda line: None)
    calendar = [day for day in ctx["calendar"] if day <= end]
    nifty = ctx["nifty"]
    by_name = ctx["by_name"]
    top100 = ctx["top100"]
    starts = formation_starts(calendar)
    names = ("pairs same", "pairs any", "pairs z")
    collected = {}
    for name in names:
        collected[name] = []
    closes = {}
    for symbol in by_name:
        closes[symbol] = {}
        for day, found in by_name[symbol].items():
            seg, i = found
            closes[symbol][day] = seg.c[i]
    emit("pair formations %d" % len(starts))
    for index, form_day in enumerate(starts):
        if index + 1 < len(starts):
            trade_end = starts[index + 1]
        else:
            trade_end = end + datetime.timedelta(days=1)
        if trade_end <= start:
            continue
        anchor = datetime.date(form_day.year - 1, form_day.month, 1)
        form_begin = on_or_after(anchor, calendar)
        if form_begin is None:
            continue
        form_dates = window_dates(calendar, form_begin, form_day)
        trade_dates = window_dates(calendar, form_day, trade_end)
        if len(form_dates) < FORM_MIN or len(trade_dates) < 2:
            continue
        universe = ctx["top200"].get(form_day, ())
        series = {}
        for symbol in universe:
            got = closes_for(by_name, symbol, form_dates)
            if got is not None:
                series[symbol] = got
        if len(series) < 2:
            continue
        same = choose_pairs(series, industries, PAIR_SLOTS, True)
        any_ind = choose_pairs(series, industries, PAIR_SLOTS, False)
        _consume_distance(collected["pairs same"], same, form_dates, trade_dates, by_name, top100, ctx, start, end)
        _consume_distance(collected["pairs any"], any_ind, form_dates, trade_dates, by_name, top100, ctx, start, end)
        _consume_z(collected["pairs z"], same, form_dates, trade_dates, by_name, top100, ctx, start, end)
        if (index + 1) % 4 == 0:
            emit("  formation %d/%d" % (index + 1, len(starts)))
    blocks = []
    for name in names:
        trades = collected[name]
        equity, flags = _price_book(trades, calendar, nifty, closes)
        keys, monthly = month_returns(calendar, equity)
        block = _event_block(name, trades, monthly)
        stats = h.path_stats(calendar, equity, CAPITAL, nifty, {})
        block["cagr"] = stats.get("cagr")
        block["max_dd"] = stats.get("max_dd")
        block["beta"] = _beta(calendar, equity, flags, nifty)
        block["equity"] = equity
        blocks.append(block)
    for block in blocks:
        block["verdict"] = judge_event(block, blocks, "monthly t")
    return blocks


def _rows_for(by_name, a, b, dates):
    rows = []
    for day in dates:
        left = closes_for(by_name, a, [day])
        right = closes_for(by_name, b, [day])
        if left is None or right is None:
            continue
        rows.append((day, left[0], right[0]))
    return rows


def _stamp_trade(bucket, a, b, rows, entry_i, exit_i, long_a, top100, ctx, start, end):
    entry = rows[entry_i][0]
    exit_day = rows[exit_i][0]
    if entry < start or entry > end or exit_day < entry:
        return
    ea, eb = rows[entry_i][1], rows[entry_i][2]
    xa, xb = rows[exit_i][1], rows[exit_i][2]
    rolls = rollover_count(entry, exit_day)
    ret = pair_return(ea, xa, eb, xb, long_a, rolls, LEG)
    if ret is None:
        return
    large = a in top100.get(entry, ()) and b in top100.get(entry, ())
    bucket.append({
        "date": entry, "exit": exit_day, "ret": ret, "regime": ctx["regimes"].get(entry),
        "large": large, "a": a, "b": b, "long_a": long_a,
        "ea": ea, "eb": eb, "xa": xa, "xb": xb, "entry": entry,
    })


def _consume_distance(bucket, picked, form_dates, trade_dates, by_name, top100, ctx, start, end):
    for item in picked:
        _ssd, a, b, std, mean, a0, b0 = item
        rows = []
        for day in trade_dates:
            raw = _rows_for(by_name, a, b, [day])
            if not raw:
                continue
            _day, ca, cb = raw[0]
            rows.append((day, ca / a0, cb / b0, ca, cb))
        if len(rows) < 2:
            continue
        norm = [(row[0], row[1], row[2]) for row in rows]
        for entry_i, exit_i, long_a in distance_trades(norm, mean, std):
            raw_rows = [(row[0], row[3], row[4]) for row in rows]
            _stamp_trade(bucket, a, b, raw_rows, entry_i, exit_i, long_a, top100, ctx, start, end)


def _consume_z(bucket, picked, form_dates, trade_dates, by_name, top100, ctx, start, end):
    both = list(form_dates) + list(trade_dates)
    for item in picked:
        _ssd, a, b, _std, _mean, _a0, _b0 = item
        rows = []
        for day in both:
            raw = _rows_for(by_name, a, b, [day])
            if raw:
                rows.append(raw[0])
        if len(rows) < Z_N + 2:
            continue
        logs = []
        for row in rows:
            if row[1] <= 0 or row[2] <= 0:
                logs.append(None)
            else:
                logs.append(math.log(row[1] / row[2]))
        zs = [z_at(logs, i, Z_N) for i in range(len(logs))]
        first = None
        for i, row in enumerate(rows):
            if row[0] >= trade_dates[0]:
                first = i
                break
        if first is None:
            continue
        clipped = [None] * first
        clipped.extend(zs[first:])
        for entry_i, exit_i, long_a in walk_z(clipped, Z_MAX):
            _stamp_trade(bucket, a, b, rows, entry_i, exit_i, long_a, top100, ctx, start, end)


def _grail_one(seg, i, symbol, nifty, adx_min, need_sma):
    if not grail_signal(seg, i, adx_min, need_sma):
        return None
    return _grail_from_day(seg, i, symbol, nifty)


def _grail_from_day(seg, i, symbol, nifty):
    filled = grail_fill(seg, i, symbol)
    if filled is None:
        return None
    entry_i, fill, at_open = filled
    stop = seg.l[i]
    if not fill > stop:
        return None
    target = fill + 2.0 * (fill - stop)
    found = grail_exit(seg, entry_i, stop, target)
    if found is None:
        return None
    exit_i, px, exit_open = found
    ret = f.net_return(fill, px)
    if ret is None:
        return None
    entry_day = seg.date[entry_i]
    exit_day = seg.date[exit_i]
    mkt = v.mkt_return(nifty, entry_day, exit_day, at_open, exit_open)
    return {
        "date": entry_day,
        "exit": exit_day,
        "ret": ret,
        "mkt": mkt,
        "hold": (exit_day - entry_day).days,
        "at_open": at_open,
    }


def run_grail(ctx, start, end, runs, log):
    emit = log or (lambda line: None)
    specs = (
        {"name": "grail adx30", "adx": 30.0, "sma": False},
        {"name": "grail adx25", "adx": 25.0, "sma": False},
        {"name": "grail adx30 sma200", "adx": 30.0, "sma": True},
    )
    collected = {}
    pools = {}
    for spec in specs:
        collected[spec["name"]] = []
    loaded = ctx["loaded"]
    emit("holy grail on %d symbols" % len(loaded))
    for symbol in loaded:
        name = symbol["name"]
        for seg in symbol["segments"]:
            n = len(seg.date)
            for i in range(n - 1):
                entry_day = seg.date[i + 1]
                if entry_day < start or entry_day > end:
                    continue
                if name not in ctx["top200"].get(seg.date[i], ()):
                    continue
                probe = _grail_from_day(seg, i, name, ctx["nifty"])
                if probe is not None and name in ctx["top200"].get(probe["date"], ()):
                    f._pool_add(pools, "grail", name, probe["date"], probe["ret"], probe["mkt"])
                for spec in specs:
                    if not grail_signal(seg, i, spec["adx"], spec["sma"]):
                        continue
                    done = probe if probe is not None else None
                    if spec["sma"] or spec["adx"] != 30.0:
                        done = _grail_one(seg, i, name, ctx["nifty"], spec["adx"], spec["sma"])
                    if done is None:
                        continue
                    if done["date"] < start or done["date"] > end:
                        continue
                    large = name in ctx["top100"].get(seg.date[i], ())
                    trade = f.make_trade(
                        done["date"], name, done["ret"], done["mkt"],
                        ctx["regimes"].get(done["date"]), large, done["hold"])
                    collected[spec["name"]].append(trade)
    blocks = []
    for index, spec in enumerate(specs):
        trades = collected[spec["name"]]
        seed = h.SEED + GRAIL_SEED + index * 1000
        emit("scoring %s (%d)" % (spec["name"], len(trades)))
        block = f.summarise_swing(spec["name"], trades)
        block["nifty_t"] = nifty_monthly_t(trades)
        block["seed"] = seed
        f.apply_trade_random(trades, pools, "grail", runs, seed)
        block["t"] = f.summarise_swing(spec["name"], trades)["t"]
        blocks.append(block)
    for block in blocks:
        block["verdict"] = f.judge_swing(block, blocks)
    return blocks


def _futures_long(entry_px, exit_px, entry, exit_day):
    if not entry_px > 0 or not exit_px > 0:
        return None
    buy_val = LOT * entry_px
    sell_val = LOT * exit_px
    pnl = sell_val - buy_val
    rolls = rollover_count(entry, exit_day)
    cost = futures_side(buy_val, True) + futures_side(sell_val, False)
    cost += rolls * round_trip(buy_val)
    return (pnl - cost) / buy_val * 100.0


def calendar_events(calendar, nifty):
    """Three lists of (entry, exit, entry_px, exit_px, at_open_entry)."""
    index = {}
    for i, day in enumerate(calendar):
        index[day] = i
    by_month = {}
    for day in calendar:
        by_month.setdefault((day.year, day.month), []).append(day)
    tom = []
    keys = sorted(by_month)
    for pos, key in enumerate(keys):
        if pos + 1 >= len(keys):
            break
        month = by_month[key]
        nxt = by_month[keys[pos + 1]]
        if len(month) < 2 or len(nxt) < 3:
            continue
        entry = month[-2]
        exit_day = nxt[2]
        tom.append((entry, exit_day, nifty[entry]["close"], nifty[exit_day]["close"]))
    expiry = []
    after = []
    seen = {}
    for day in calendar:
        key = (day.year, day.month)
        if key in seen:
            continue
        seen[key] = True
        exp = expiry_day(day.year, day.month, calendar)
        if exp is None or exp not in index:
            continue
        monday = exp - datetime.timedelta(days=exp.weekday())
        entry = on_or_after(monday, calendar)
        if entry is None or entry > exp or entry not in index:
            continue
        expiry.append((entry, exp, nifty[entry]["open"], nifty[exp]["close"]))
        nxt_monday = exp + datetime.timedelta(days=(7 - exp.weekday()) % 7)
        if nxt_monday <= exp:
            nxt_monday = exp + datetime.timedelta(days=7)
        friday = nxt_monday + datetime.timedelta(days=4)
        start = on_or_after(nxt_monday, calendar)
        finish = on_or_before(friday, calendar)
        if start is None or finish is None or finish < start or finish > friday:
            continue
        if start < nxt_monday or (finish - nxt_monday).days > 4:
            continue
        after.append((start, finish, nifty[start]["open"], nifty[finish]["close"]))
    return {"tom": tom, "expiry week": expiry, "after expiry": after}


def _random_windows(calendar, entry, exit_day, year, rng, runs):
    index = {}
    for i, day in enumerate(calendar):
        index[day] = i
    if entry not in index or exit_day not in index:
        return []
    length = index[exit_day] - index[entry]
    if length < 1:
        return []
    starts = []
    for i, day in enumerate(calendar):
        j = i + length
        if j >= len(calendar) or day == entry:
            continue
        if day.year != year or calendar[j].year != year:
            continue
        starts.append(i)
    if not starts:
        return []
    picked = []
    for _k in range(runs):
        picked.append(starts[rng.randrange(len(starts))])
    return picked


def run_calendar(ctx, start, end, runs, log):
    emit = log or (lambda line: None)
    calendar = [day for day in ctx["calendar"] if ctx["nifty"].get(day, {}).get("open", 0) > 0 and day <= end]
    events = calendar_events(calendar, ctx["nifty"])
    order = ("tom", "expiry week", "after expiry")
    blocks = []
    for index, name in enumerate(order):
        trades = []
        excesses = []
        for event_i, event in enumerate(events[name]):
            entry, exit_day, entry_px, exit_px = event
            if entry < start or entry > end:
                continue
            ret = _futures_long(entry_px, exit_px, entry, exit_day)
            if ret is None:
                continue
            rng = random.Random(h.SEED + CAL_SEED + index * 1000 + event_i)
            windows = _random_windows(calendar, entry, exit_day, entry.year, rng, runs)
            baseline = []
            entry_i = bisect.bisect_left(calendar, entry)
            exit_i = bisect.bisect_left(calendar, exit_day)
            length = exit_i - entry_i
            for start_i in windows:
                a = calendar[start_i]
                b = calendar[start_i + length]
                # Match the real window's open/close mix: tom is close to close.
                if name == "tom":
                    px_a = ctx["nifty"][a]["close"]
                    px_b = ctx["nifty"][b]["close"]
                else:
                    px_a = ctx["nifty"][a]["open"]
                    px_b = ctx["nifty"][b]["close"]
                value = _futures_long(px_a, px_b, a, b)
                if value is not None:
                    baseline.append(value)
            excess = None
            if baseline:
                excess = ret - h._mean(baseline)
            trade = {
                "date": entry,
                "ret": ret,
                "excess": excess,
                "regime": ctx["regimes"].get(entry),
                "large": False,
            }
            trades.append(trade)
            if excess is not None:
                excesses.append(excess)
        block = _event_block(name, trades, excesses)
        block["t"] = h.t_stat(excesses)
        blocks.append(block)
        emit("calendar %s (%d)" % (name, len(trades)))
    for block in blocks:
        block["verdict"] = judge_event(block, blocks, "monthly t")
    return blocks


def _momentum_map(ctx, start, end):
    scored = {}
    for symbol in ctx["loaded"]:
        name = symbol["name"]
        for seg in symbol["segments"]:
            for i, day in enumerate(seg.date):
                if day < start or day > end:
                    continue
                if name not in ctx["top200"].get(day, ()):
                    continue
                value = momentum_12_1(seg, i)
                if value is None:
                    continue
                scored.setdefault(day, []).append((value, name))
    out = {}
    for day, rows in scored.items():
        out[day] = set(top_fraction(rows, 30, 100))
    return out


def _rsi_scan(ctx, start, end, momentum, require_up):
    """Attempt 14 rsi2 < 5, plus one mix filter. Returns trades and book orders."""
    trades = []
    orders = []
    pools = {}
    for symbol in ctx["loaded"]:
        name = symbol["name"]
        for seg in symbol["segments"]:
            n = len(seg.date)
            for entry_i in range(n):
                day = seg.date[entry_i]
                if day < start or day > end:
                    continue
                if name not in ctx["top200"].get(day, ()):
                    continue
                if require_up:
                    kind = ctx["regimes"].get(day)
                    if kind not in ("up", "sideways"):
                        continue
                if momentum is not None and entry_i > 0:
                    prev = seg.date[entry_i - 1]
                    if name not in momentum.get(prev, ()):
                        continue
                if momentum is not None and entry_i == 0:
                    continue
                found = f.exit_rule(seg, entry_i, f.RSI_LIMIT, f.close_above_sma5)
                done = f._finish(seg, entry_i, found, ctx["nifty"])
                if done is None:
                    continue
                f._pool_add(pools, "mix", name, day, done[0], done[1])
            for i in range(n - 1):
                entry_i = i + 1
                entry_day = seg.date[entry_i]
                signal = seg.date[i]
                if entry_day < start or entry_day > end:
                    continue
                if name not in ctx["top200"].get(signal, ()):
                    continue
                if not f.rsi_fires(seg, i, 5.0, False):
                    continue
                if momentum is not None and name not in momentum.get(signal, ()):
                    continue
                if require_up and ctx["regimes"].get(entry_day) not in ("up", "sideways"):
                    continue
                found = f.exit_rule(seg, entry_i, f.RSI_LIMIT, f.close_above_sma5)
                done = f._finish(seg, entry_i, found, ctx["nifty"])
                if done is None:
                    continue
                exit_i, px, on_open = found
                large = name in ctx["top100"].get(signal, ())
                trade = f.make_trade(
                    entry_day, name, done[0], done[1],
                    ctx["regimes"].get(entry_day), large, done[2])
                trades.append(trade)
                orders.append({
                    "name": name,
                    "entry_date": entry_day,
                    "exit_date": seg.date[exit_i],
                    "entry": seg.o[entry_i],
                    "fill": px,
                    "at_open": on_open,
                    "rsi": seg.rsi2[i],
                    "turnover": v.turnover_before(seg, i),
                    "seg": seg,
                })
    return trades, orders, pools


def weeks_until(ctx, end):
    """Mondays through `end`. follow.monday_weeks stops at 2024-12-31."""
    nifty = ctx["nifty"]
    days = []
    for day in nifty:
        if nifty[day].get("open", 0) > 0 and day <= end:
            days.append(day)
    days.sort()
    mondays = []
    for day in days:
        if day.weekday() == 0 and day >= f.SWING_START:
            mondays.append(day)
    weeks = []
    for i, monday in enumerate(mondays):
        if i + 1 >= len(mondays):
            break
        nxt = mondays[i + 1]
        if nxt > end:
            continue
        weeks.append({
            "monday": monday,
            "next": nxt,
            "eligible": f.eligible_monday(monday, nxt, ctx),
        })
    return weeks


def _weekly_orders(ctx, start, end, random_fn=None):
    weeks = weeks_until(ctx, end)
    orders = []
    for week in weeks:
        if week["monday"] < start or week["monday"] > end:
            continue
        if random_fn is None:
            picks = f.pick_worst(week["eligible"], 20)
        else:
            picks = random_fn(week["eligible"])
        for item in picks:
            _ret5, symbol, entry_px, exit_px = item
            loc = ctx["by_name"].get(symbol, {}).get(week["monday"])
            if loc is None:
                continue
            seg, _i = loc
            orders.append({
                "name": symbol,
                "entry_date": week["monday"],
                "exit_date": week["next"],
                "entry": entry_px,
                "fill": exit_px,
                "seg": seg,
            })
    return orders


def simulate_weekly(orders, calendar, nifty, capital, slots):
    """Sell the old week at the open, then buy the new week the same day."""
    by_entry = {}
    for order in orders:
        by_entry.setdefault(order["entry_date"], []).append(order)
    book = h.Book(capital, park=True)
    if calendar and nifty.get(calendar[0], {}).get("open", 0) > 0:
        book.fund_nifty(nifty[calendar[0]]["open"])
    equity = []
    slot = capital / float(slots)
    for day in calendar:
        bar = nifty.get(day)
        if bar is None or not bar.get("open", 0) > 0:
            equity.append(book.cash + book.nifty_shares * 0.0)
            continue
        nopen = bar["open"]
        nclose = bar["close"]
        for name in list(book.pos):
            pos = book.pos[name]
            if pos.get("exit_date") == day:
                book.sell(name, pos["shares"], pos["fill"], nopen)
        for order in by_entry.get(day, []):
            shares = h.shares_for(slot, order["entry"])
            got = book.buy(order["name"], order["seg"], shares, order["entry"], nopen)
            if got < 1:
                continue
            pos = book.pos[order["name"]]
            pos["exit_date"] = order["exit_date"]
            pos["fill"] = order["fill"]
        equity.append(book.value(day, nclose, "c"))
    return equity


def _combine(calendar, left, right):
    out = []
    for i in range(len(calendar)):
        out.append(left[i] + right[i])
    return out


def _book_block(name, calendar, equity, nifty, regimes, beats, large_excess, corr):
    stats = h.path_stats(calendar, equity, CAPITAL, nifty, regimes)
    stats["name"] = name
    stats["trades"] = None
    stats["beats"] = beats
    stats["large_excess"] = large_excess
    stats["corr"] = corr
    stats["verdict"] = h.judge(stats, {
        "cagr": None, "max_dd": None, "calmar": None,
    })
    return stats


def _finish_book(name, calendar, equity, nifty, regimes, random_cagrs, large_equity):
    real = h.cagr_of(calendar, equity, CAPITAL)
    beats = 0
    for other in random_cagrs:
        if real is not None and other is not None and real > other:
            beats += 1
    large_stats = h.path_stats(calendar, large_equity, CAPITAL, nifty, regimes)
    return _book_block(name, calendar, equity, nifty, regimes, beats, large_stats.get("excess"), None)


def run_mixes(ctx, start, end, runs, log):
    emit = log or (lambda line: None)
    emit("mix momentum map")
    momentum = _momentum_map(ctx, f.SWING_START, end)
    emit("mix m1")
    t1, o1, p1 = _rsi_scan(ctx, start, end, momentum, False)
    emit("mix m2")
    t2, o2, p2 = _rsi_scan(ctx, start, end, None, True)
    n1 = nifty_monthly_t(t1)
    n2 = nifty_monthly_t(t2)
    f.apply_trade_random(t1, p1, "mix", runs, h.SEED + MIX_SEED)
    f.apply_trade_random(t2, p2, "mix", runs, h.SEED + MIX_SEED + 1000)
    b1 = f.summarise_swing("m1 momentum", t1)
    b2 = f.summarise_swing("m2 regime", t2)
    b1["nifty_t"] = n1
    b2["nifty_t"] = n2
    b1["verdict"] = judge_mix(b1, True)
    b2["verdict"] = judge_mix(b2, False)
    emit("mix m3")
    calendar = [day for day in ctx["calendar"] if start <= day <= end and ctx["nifty"].get(day, {}).get("open", 0) > 0]
    half = CAPITAL / 2.0
    rev_orders = _weekly_orders(ctx, start, end)
    rev_eq = simulate_weekly(rev_orders, calendar, ctx["nifty"], half, 20)
    rsi_equity = _rsi_equity(v.align_orders(o1, calendar), calendar, ctx["nifty"], half, 5)
    combined = _combine(calendar, rsi_equity, rev_eq)
    _k1, r_left = month_returns(calendar, rsi_equity)
    _k2, r_right = month_returns(calendar, rev_eq)
    corr = pearson(r_left, r_right)
    random_cagrs = []
    emit("mix m3 random %d" % runs)
    for run_i in range(runs):
        rng = random.Random(h.SEED + MIX_SEED + 2000 + run_i)
        rand_orders = _weekly_orders(ctx, start, end, lambda eligible, rng=rng: f.pick_random(eligible, 20, rng))
        rand_rev = simulate_weekly(rand_orders, calendar, ctx["nifty"], half, 20)
        rand_rsi = _random_rsi_orders(o1, ctx, rng)
        rand_left = _rsi_equity(v.align_orders(rand_rsi, calendar), calendar, ctx["nifty"], half, 5)
        both = _combine(calendar, rand_left, rand_rev)
        random_cagrs.append(h.cagr_of(calendar, both, CAPITAL))
    large_orders = []
    for order in o1:
        if order["name"] in ctx["top100"].get(order["entry_date"], ()):
            large_orders.append(order)
    large_rev = _weekly_orders_large(ctx, start, end)
    large_left = _rsi_equity(v.align_orders(large_orders, calendar), calendar, ctx["nifty"], half, 5)
    large_right = simulate_weekly(large_rev, calendar, ctx["nifty"], half, 20)
    large_eq = _combine(calendar, large_left, large_right)
    bench = h.path_stats(calendar, h.nifty_path(calendar, ctx["nifty"], CAPITAL), CAPITAL, ctx["nifty"], {})
    block = _finish_book("m3 book", calendar, combined, ctx["nifty"], ctx["regimes"], random_cagrs, large_eq)
    block["verdict"] = h.judge(block, bench)
    block["corr"] = corr
    block["bench"] = bench
    _keys, combined_monthly = month_returns(calendar, combined)
    block["book_avg"] = h._mean(combined_monthly)
    block["yearly"] = h.path_stats(calendar, combined, CAPITAL, ctx["nifty"], ctx["regimes"]).get("yearly")
    return [b1, b2, block], None


def _rsi_equity(orders, calendar, nifty, capital, slots):
    """Same book as verify.simulate_book, returning the equity curve."""
    by_entry = {}
    for order in orders:
        by_entry.setdefault(order["entry_date"], []).append(order)
    book = h.Book(capital, park=True)
    if calendar and nifty.get(calendar[0], {}).get("open", 0) > 0:
        book.fund_nifty(nifty[calendar[0]]["open"])
    equity = []
    slot = capital / float(slots)
    for day in calendar:
        bar = nifty.get(day)
        if bar is None or not bar.get("open", 0) > 0:
            equity.append(book.cash)
            continue
        nopen = bar["open"]
        nclose = bar["close"]
        left = set()
        for name in list(book.pos):
            pos = book.pos[name]
            if pos.get("exit_date") == day and pos.get("at_open"):
                book.sell(name, pos["shares"], pos["fill"], nopen)
                left.add(name)
        room = slots - len(book.pos)
        held = set(book.pos)
        for name in left:
            held.add(name)
        for order in v.take_slots(by_entry.get(day, []), room, held):
            shares = h.shares_for(slot, order["entry"])
            got = book.buy(order["name"], order["seg"], shares, order["entry"], nopen)
            if got < 1:
                continue
            pos = book.pos[order["name"]]
            pos["exit_date"] = order["exit_date"]
            pos["fill"] = order["fill"]
            pos["at_open"] = order["at_open"]
            if order["exit_date"] == day and order["at_open"]:
                book.sell(order["name"], pos["shares"], order["fill"], nopen)
        for name in list(book.pos):
            pos = book.pos[name]
            if pos.get("exit_date") == day and not pos.get("at_open"):
                book.sell(name, pos["shares"], pos["fill"], nclose)
        v._exit_broken(book, day, nclose)
        equity.append(book.value(day, nclose, "c"))
    return equity


def _random_rsi_orders(orders, ctx, rng):
    out = []
    for order in orders:
        day = order["entry_date"]
        names = list(ctx["top200"].get(day, ()))
        if not names:
            continue
        symbol = names[rng.randrange(len(names))]
        loc = ctx["by_name"].get(symbol, {}).get(day)
        exit_loc = ctx["by_name"].get(symbol, {}).get(order["exit_date"])
        if loc is None or exit_loc is None:
            continue
        seg, i = loc
        seg_x, j = exit_loc
        if seg is not seg_x or not seg.o[i] > 0:
            continue
        fill = seg.o[j] if order.get("at_open") else seg.c[j]
        if not fill > 0:
            continue
        item = dict(order)
        item["name"] = symbol
        item["seg"] = seg
        item["entry"] = seg.o[i]
        item["fill"] = fill
        item["rsi"] = 50.0
        item["turnover"] = 0.0
        out.append(item)
    return out


def _weekly_orders_large(ctx, start, end):
    weeks = weeks_until(ctx, end)
    orders = []
    for week in weeks:
        if week["monday"] < start or week["monday"] > end:
            continue
        large = ctx["top100"].get(week["monday"], ())
        eligible = []
        for item in week["eligible"]:
            if item[1] in large:
                eligible.append(item)
        for item in f.pick_worst(eligible, 20):
            _ret5, symbol, entry_px, exit_px = item
            loc = ctx["by_name"].get(symbol, {}).get(week["monday"])
            if loc is None:
                continue
            seg, _i = loc
            orders.append({
                "name": symbol, "entry_date": week["monday"], "exit_date": week["next"],
                "entry": entry_px, "fill": exit_px, "seg": seg,
            })
    return orders


def _passers(groups):
    found = []
    for blocks in groups:
        for block in blocks:
            verdict = block.get("verdict") or {}
            if verdict.get("result") == "PASS":
                found.append(block["name"])
    return found


def run_holdout(root, names, industries, runs, log):
    """One final=True load. Only names that passed in sample are scored."""
    emit = log or (lambda line: None)
    if not names:
        emit("no in-sample pass, so no holdout was run")
        return []
    path = data.bar_path(root, "day", lab.NIFTY)
    from india.research import survivorship as sv
    _first, last = sv.raw_span(path)
    emit("holdout %s to %s" % (HOLDOUT.isoformat(), last.isoformat()))
    ctx = h.load_context(root, start=f.SWING_START, end=last, log=emit, final=True)
    for symbol in ctx["loaded"]:
        attach_extra(symbol["segments"])
    want = set(names)
    blocks = []
    if want.intersection(("pairs same", "pairs any", "pairs z")):
        for block in run_pairs(ctx, industries, HOLDOUT, last, emit):
            if block["name"] in want:
                verdict = judge_holdout(block["avg"], block["t"])
                block["verdict"] = verdict
                block["holdout"] = True
                blocks.append(block)
    grail_names = set(("grail adx30", "grail adx25", "grail adx30 sma200"))
    if want.intersection(grail_names):
        for block in run_grail(ctx, HOLDOUT, last, 0, emit):
            if block["name"] not in want:
                continue
            block["hold_avg"] = block["avg"]
            block["hold_t"] = block.get("nifty_t")
            block["verdict"] = judge_holdout(block["hold_avg"], block["hold_t"])
            block["holdout"] = True
            blocks.append(block)
    if want.intersection(("tom", "expiry week", "after expiry")):
        for block in run_calendar(ctx, HOLDOUT, last, runs, emit):
            if block["name"] in want:
                block["verdict"] = judge_holdout(block["avg"], block["t"])
                block["holdout"] = True
                blocks.append(block)
    if want.intersection(("m1 momentum", "m2 regime", "m3 book")):
        mixes, _unused = run_mixes(ctx, HOLDOUT, last, 0, emit)
        for block in mixes:
            if block["name"] not in want:
                continue
            if block["name"] == "m3 book":
                avg = block.get("book_avg")
                tstat = block.get("t")
            else:
                avg = block.get("avg")
                tstat = block.get("nifty_t")
            block["hold_avg"] = avg
            block["hold_t"] = tstat
            block["verdict"] = judge_holdout(avg, tstat)
            block["holdout"] = True
            blocks.append(block)
    return blocks


def prepare_context(root, end, log, final):
    emit = log or (lambda line: None)
    ctx = h.load_context(root, start=f.SWING_START, end=end, log=emit, final=final)
    for symbol in ctx["loaded"]:
        attach_extra(symbol["segments"])
    return ctx


def family_table(blocks, columns):
    lines = [" | ".join(columns)]
    for block in blocks:
        lines.append(_format_block(block, columns))
    return lines


def _format_block(block, columns):
    values = []
    for column in columns:
        values.append(_cell(block, column))
    return " | ".join(values)


def _cell(block, column):
    if column == "variant":
        return block["name"]
    if column == "result":
        return (block.get("verdict") or {}).get("result", "")
    if column == "trades":
        if block.get("trades") is None:
            return "n/a"
        return format(block["trades"], ",d")
    key = {
        "avg": "avg", "t": "t", "beta": "beta", "CAGR": "cagr", "max DD": "max_dd",
        "2005-2014": "early", "2015-2024": "late", "up": "up", "down": "down",
        "sideways": "sideways", "large": "large", "corr": "corr",
        "beats": "beats", "excess": "excess",
    }.get(column, column)
    if column == "beats":
        value = block.get("beats")
        return "n/a" if value is None else str(value)
    if column in ("t", "beta", "corr"):
        return h._num(block.get(key))
    if key == "large" and "large_excess" in block and block.get("large") is None:
        return h._pct(block.get("large_excess"))
    return h._pct(block.get(key))


def _reasons(block):
    verdict = block.get("verdict") or {}
    if verdict.get("result") == "PASS":
        return "%s PASS." % block["name"]
    return "%s FAIL: %s" % (block["name"], "; ".join(verdict.get("reasons") or []))


def table_rows(stamp, groups, holdouts):
    rows = []
    for blocks in groups:
        for block in blocks:
            avg = block.get("avg")
            if avg is None and block.get("cagr") is not None:
                avg = block.get("cagr")
            tstat = block.get("t")
            trades = block.get("trades")
            trade_cell = "see section" if trades is None else format(trades, ",d")
            rows.append("| 16 | %s | %s | %s | %s | %s | %s | %s | %s |" % (
                stamp,
                "%s." % block["name"],
                "attempt 16, rules fixed before the run",
                "2005-01-01 to 2024-12-31",
                trade_cell,
                h._pct(avg),
                h._num(tstat),
                (block.get("verdict") or {}).get("result", "")))
    if not holdouts:
        rows.append("| 16 | %s | %s | %s | %s | %s | %s | %s | %s |" % (
            stamp,
            "no in-sample pass, so no holdout was run.",
            "final=True was not called",
            "2025-01-01 onward, not opened",
            "0", "n/a", "n/a", "n/a"))
    for block in holdouts:
        avg = block.get("hold_avg", block.get("avg"))
        tstat = block.get("hold_t", block.get("t"))
        rows.append("| 16 | %s | %s | %s | %s | %s | %s | %s | %s |" % (
            stamp,
            "holdout %s." % block["name"],
            "same rule, final=True once",
            "2025-01-01 to the last NIFTY date",
            format(block["trades"], ",d") if block.get("trades") is not None else "see section",
            h._pct(avg),
            h._num(tstat),
            (block.get("verdict") or {}).get("result", "")))
    return rows


def report_text(stamp, pairs, grail, calendar, mixes, holdouts, entries):
    lines = [rules_text(stamp), "", "Results.", "", "Spot prices are the futures proxy.", ""]
    lines.append("Pairs. Per-trade average on Rs 2,00,000. Beta is not a pass clause.")
    lines.extend(family_table(pairs, [
        "variant", "trades", "avg", "beta", "t", "2005-2014", "2015-2024",
        "up", "down", "sideways", "large", "CAGR", "max DD", "result",
    ]))
    for block in pairs:
        lines.append(_reasons(block))
    lines.append("")
    lines.append("Holy Grail.")
    lines.extend(family_table(grail, [
        "variant", "trades", "avg", "t", "2005-2014", "2015-2024",
        "up", "down", "sideways", "large", "result",
    ]))
    for block in grail:
        lines.append(_reasons(block))
    lines.append("")
    lines.append("Calendar. The t is versus same-year random windows.")
    lines.extend(family_table(calendar, [
        "variant", "trades", "avg", "t", "2005-2014", "2015-2024",
        "up", "down", "sideways", "result",
    ]))
    for block in calendar:
        lines.append(_reasons(block))
    lines.append("")
    lines.append("Mixes.")
    trade_mixes = mixes[:2]
    lines.extend(family_table(trade_mixes, [
        "variant", "trades", "avg", "t", "2005-2014", "2015-2024",
        "up", "down", "sideways", "large", "result",
    ]))
    book = mixes[2]
    lines.append("m3 book | CAGR %s | max DD %s | excess %s | t %s | beats %s | corr %s | %s" % (
        h._pct(book.get("cagr")), h._pct(book.get("max_dd")), h._pct(book.get("excess")),
        h._num(book.get("t")), _cell(book, "beats"), h._num(book.get("corr")),
        (book.get("verdict") or {}).get("result", "")))
    for block in mixes:
        lines.append(_reasons(block))
    lines.append("")
    lines.append("Holdout.")
    if not holdouts:
        lines.append("No variant passed in sample, so no holdout was run.")
    for block in holdouts:
        lines.append("%s | avg %s | t %s | %s" % (
            block["name"], h._pct(block.get("hold_avg", block.get("avg"))),
            h._num(block.get("hold_t", block.get("t"))),
            (block.get("verdict") or {}).get("result", "")))
        lines.append(_reasons(block))
    lines.append("")
    lines.append("Bucket list.")
    lines.append(render_catalogue(entries))
    return "\n".join(lines).rstrip() + "\n"


def _catalogue_entries(pairs, grail, calendar, mixes, holdouts):
    by_name = {}
    for block in holdouts:
        by_name[block["name"]] = block
    results = []
    for block in list(pairs) + list(grail) + list(calendar) + list(mixes):
        hold = by_name.get(block["name"])
        note = (block.get("verdict") or {}).get("result", "")
        if hold is not None:
            note = "%s Holdout %s, avg %s, t %s." % (
                note, (hold.get("verdict") or {}).get("result", ""),
                h._pct(hold.get("hold_avg", hold.get("avg"))),
                h._num(hold.get("hold_t", hold.get("t"))))
        avg = None if hold is None else hold.get("hold_avg", hold.get("avg"))
        tstat = None if hold is None else hold.get("hold_t", hold.get("t"))
        results.append({
            "name": block["name"],
            "attempt": 16,
            "in_sample": (block.get("verdict") or {}).get("result"),
            "holdout": None if hold is None else {"avg": avg, "t": tstat},
            "note": note,
        })
    return results


def main(argv=None, log=None):
    import argparse
    parser = argparse.ArgumentParser(description="Attempt 16. Nothing is placed.")
    parser.add_argument("--root", default=os.path.join("data", "kite"))
    parser.add_argument("--experiments", default=h.EXPERIMENTS)
    parser.add_argument("--catalogue", default=CATALOGUE)
    parser.add_argument("--industries", default=os.path.join(_ROOT, "india", "universe", "nifty500.csv"))
    parser.add_argument("--runs", type=int, default=h.RUNS)
    args = parser.parse_args(argv)
    emit = log or (lambda line: print(line, flush=True))
    stamp = datetime.date.today().isoformat()
    f.install_attempt(args.experiments, 16, rules_text(stamp), [])
    emit("rules for attempt 16 written to %s before the run" % args.experiments)
    update_tiers(args.catalogue, [])
    emit("bucket list for attempts 1 to 15 written before the run")
    industries = load_industries(args.industries)
    emit("loading stocks through %s" % h.END.isoformat())
    ctx = prepare_context(args.root, h.END, emit, False)
    pairs = run_pairs(ctx, industries, f.SWING_START, h.END, emit)
    grail = run_grail(ctx, f.SWING_START, h.END, args.runs, emit)
    calendar = run_calendar(ctx, f.SWING_START, h.END, args.runs, emit)
    mixes, _unused = run_mixes(ctx, f.SWING_START, h.END, args.runs, emit)
    names = _passers((pairs, grail, calendar, mixes))
    holdouts = run_holdout(args.root, names, industries, args.runs, emit)
    results = _catalogue_entries(pairs, grail, calendar, mixes, holdouts)
    entries = update_tiers(args.catalogue, results)
    text = report_text(stamp, pairs, grail, calendar, mixes, holdouts, entries)
    f.install_attempt(args.experiments, 16, text, table_rows(stamp, (pairs, grail, calendar, mixes), holdouts))
    for title, blocks, columns in (
        ("Pairs", pairs, ["variant", "trades", "avg", "beta", "t", "2005-2014", "2015-2024", "up", "down", "sideways", "large", "CAGR", "max DD", "result"]),
        ("Holy Grail", grail, ["variant", "trades", "avg", "t", "2005-2014", "2015-2024", "up", "down", "sideways", "large", "result"]),
        ("Calendar", calendar, ["variant", "trades", "avg", "t", "2005-2014", "2015-2024", "up", "down", "sideways", "result"]),
    ):
        emit(title)
        for line in family_table(blocks, columns):
            emit(line)
        for block in blocks:
            emit(_reasons(block))
    emit("Mixes")
    for line in family_table(mixes[:2], ["variant", "trades", "avg", "t", "2005-2014", "2015-2024", "up", "down", "sideways", "large", "result"]):
        emit(line)
    book = mixes[2]
    emit("m3 book | CAGR %s | max DD %s | t %s | beats %s | corr %s | %s" % (
        h._pct(book.get("cagr")), h._pct(book.get("max_dd")), h._num(book.get("t")),
        _cell(book, "beats"), h._num(book.get("corr")),
        (book.get("verdict") or {}).get("result", "")))
    for block in mixes:
        emit(_reasons(block))
    emit("Holdout")
    if not holdouts:
        emit("No variant passed in sample, so no holdout was run.")
    for block in holdouts:
        emit("%s | avg %s | t %s | %s" % (
            block["name"], h._pct(block.get("hold_avg", block.get("avg"))),
            h._num(block.get("hold_t", block.get("t"))),
            (block.get("verdict") or {}).get("result", "")))
    emit("Bucket list")
    for tier in ("Bucket", "Watch", "Investing", "Near-miss", "Closed"):
        rows = [item["name"] for item in entries if item["tier"] == tier]
        emit("%s: %s" % (tier, ", ".join(rows) if rows else "none"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
