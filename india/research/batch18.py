#!/usr/bin/env python3
"""Attempt 18: decay of the names on Watch and Investing, overnight versus
intraday futures, and the pre-holiday session.

Rules are written to EXPERIMENTS.md before any of that runs. Track A is a
record of the AlgoTest results. Nothing is placed.

    python3 india/research/batch18.py
"""

import bisect
import csv
import datetime
import gzip
import os
import random
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from india.research import batch16 as b16
from india.research import batch17 as b17
from india.research import data
from india.research import follow as f
from india.research import harness as h
from india.research import nse_holidays
from india.research import regime
from india.research import signal_lab as lab
from india.research import survivorship

HOLDOUT_LINE = (
    "2026-11-07 AlgoTest NIFTY short straddle/strangle family (S1-S3), holdout used"
)
S2_ROW = (
    "| S2 ATM straddle 50% SL | 17-A | "
    "slippage-sensitive; BANKNIFTY weekly discontinued |"
)
S4_ROW = (
    "| S4 iron fly OTM8 | 17-A | In-sample net Rs -2.39L, t -2.90. No holdout. |"
)
FAMILY_ROWS = (
    "| options selling | yes |",
    "| overnight | no |",
    "| pre-holiday | no |",
)
DECAY_FIRST = 2015
DECAY_LAST = 2024
OPEN_END = 9 * 60 + 20
BANK_LOT = 15
HOLIDAY_SEED = 93000
HOLIDAY_RUNS = 100
LONG_EXPIRY = "2026-12-29"
LONG_BEFORE = "2026-08-01"
MOM_SPEC = {"name": "mom 12-1 K20 above200", "kind": "mom", "k": 20, "filter": True}


def rules_text():
    """The attempt 18 rules. No inner heading: a later install stops at the next one."""
    lines = [
        "## Attempt 18",
        "",
        "Research window only. Every load in this window uses final=False.",
        "A holdout is one load with final=True, logged once, and it runs only",
        "after a family passes in sample. The decay check has no pass mark and",
        "does not open 2025.",
        "",
        "18a Decay check. No pass and no fail. Does not use the holdout.",
        "Strategies: rsi2 < 5, m2 regime, rel rsi5, rel rsi5 stock10, tom rsi20,",
        "mom 12-1 K20 above200. For each one, print the average after-cost return",
        "and its t by calendar year from 2015 to 2024, then an ordinary least",
        "squares regression of that yearly average on the calendar year, with an",
        "intercept. The slope's t uses n - 2. A zero residual with a non-zero",
        "slope has t +inf or -inf. Label decaying when the slope is negative and",
        "its t is below -2. Otherwise label stable.",
        "For a trade strategy the year's average is the mean after-cost return of",
        "trades whose entry date is in that year, and the year's t is the",
        "one-sample t of those trade returns. A year with fewer than 2 trades has",
        "no t and is left out of the regression.",
        "For mom 12-1 K20 above200 the year's average is the book's calendar-year",
        "percent return (year-end equity over the prior year-end, delivery costs,",
        "idle cash in NIFTY). The year's t is the one-sample t of that year's",
        "month-end book percent returns. A year with fewer than 2 months is left",
        "out of the regression. The regression point is the calendar-year return.",
        "",
        "18b Overnight vs intraday. New family, overnight. Has not used a holdout.",
        "NIFTY 50 and NIFTY BANK 5-minute files. The files start on 2015-01-09.",
        "This test reads them directly and keeps every session. It does not apply",
        "the stock listing cut of 20 sessions. A session on or after 2025-01-01 is",
        "not read here.",
        "Bar labels are the bar end (the Kite candle start plus 5 minutes). The",
        "09:15 open is the open of the bar whose end is 09:20. A session whose",
        "first bar does not end at 09:20 is left out, and the next kept session",
        "measures overnight from the previous kept close. The first kept session",
        "has no overnight. Overnight is the previous kept close to this 09:15",
        "open. Intraday is that open to the session's last 5-minute close. The",
        "official close is a 30-minute average, so this last trade can differ from",
        "the daily close.",
        "Two trades, judged separately, four variants in all: hold the futures",
        "overnight only, and hold them intraday only, on NIFTY and on BANKNIFTY.",
        "The index level is the futures proxy. Costs are the attempt 16 futures",
        "schedule, check your broker: brokerage Rs 20 a side, STT 0.05% on the",
        "sell, exchange 0.00173% a side, SEBI 0.0001% a side, stamp 0.002% on the",
        "buy, GST 18% on brokerage plus exchange plus SEBI. NIFTY lot 75.",
        "BANKNIFTY lot 15, the lot for most of 2015-2023, check your broker. The",
        "lot matters because Rs 20 does not scale. One round trip. A rollover is",
        "one extra round trip for each month-start strictly after the entry and",
        "on or before the exit. Same-day intraday has none. Overnight can have",
        "one. Return is rupee P&L after costs divided by the buy value, in",
        "percent. Buy value is the lot times the entry price.",
        "Pass rules, the attempt 14 clauses this family uses: after-cost average",
        "above 0, monthly t above 3, and a positive average in both decades and",
        "in up, down and sideways. There is no random baseline, so the monthly t",
        "is the one-sample t of the monthly means of the daily after-cost",
        "returns. The decades are 2015-2019 and 2020-2024, because the 5-minute",
        "files begin in 2015. An empty bucket fails. No large-cap clause and no",
        "family gate. The regime is the NIFTY daily regime of the session date,",
        "including for BANKNIFTY.",
        "",
        "18c Pre-holiday effect. New family, pre-holiday. Has not used a holdout.",
        "NIFTY return from the close two sessions before an NSE holiday to the",
        "close of the session immediately before it. One close-to-close session:",
        "the last trading day before the holiday. The holiday list is",
        "nse_holidays.py, weekday full closures from 2010 to 2024, named from the",
        "NSE circulars. Muhurat sessions are not holidays here, because the NIFTY",
        "daily file has a bar. Weekend holidays are not events. A holiday after",
        "the last session in the calendar is not an event, because the session",
        "before it is not in the file. Two holidays that produce the same two",
        "sessions are one event.",
        "The session immediately before the holiday must fall in 2010-01-01",
        "through 2024-12-31. The trade date, the month, the decade and the regime",
        "are that session. The decades are 2010-2014 and 2015-2024, because the",
        "list starts in 2010.",
        "Costs are the same futures schedule, NIFTY lot 75, one round trip, plus",
        "a rollover when that one session crosses a month-start. The index close",
        "is the futures proxy.",
        "Excess is the after-cost return minus the mean of 100 other 1-session",
        "close-to-close windows in the same calendar year as the held session.",
        "Both sessions of a random window are in that year, and the window does",
        "not start on the real entry date. Seed is harness.SEED + 93000 + the",
        "event index. A year with no other window leaves the event in the average",
        "and out of the t.",
        "Pass rules are the same shape as 18b. The monthly t is the one-sample t",
        "of the monthly means of the excesses. The t bar is above 3. It is above",
        "2 only when the event count is strictly fewer than 150. Exactly 150",
        "still needs t above 3. Decades and regimes use the after-cost return,",
        "and each must be above 0. An empty bucket fails.",
        "",
        "Holdout, only for a family that passes in sample. One load, logged.",
        "Window 2025-01-01 through the last NIFTY daily date. The overnight",
        "holdout reads 5-minute bars from 2024-12-01 so the first 2025 overnight",
        "has a previous close, and drops trades before 2025-01-01. The pre-holiday",
        "holdout uses the 2025 and 2026 dates in nse_holidays.py. Holdout pass is",
        "after-cost average above 0 and t above 2, the same bar as attempts 16",
        "and 17. The in-sample event-count exception is not a second holdout bar.",
        "For overnight the holdout t is the monthly t of the after-cost returns.",
        "For pre-holiday it is the monthly t of the excesses. A family that is",
        "looked at is marked holdout used, including when the holdout fails.",
    ]
    return "\n".join(lines) + "\n"


def track_a_text():
    lines = [
        "## Attempt 17-A (AlgoTest options selling)",
        "",
        "Record only. These results were already run on AlgoTest. This step does not rerun them.",
        "",
        "Rules: NIFTY intraday, 09:20 entry, 15:15 exit, weekly expiry, 1 lot. "
        "Costs = AlgoTest taxes and charges + Rs 20 per order. "
        "In-sample window 2019-02 to 2024.",
        "",
        "| Strategy | In-sample | Holdout |",
        "|---|---|---|",
        "| S1 ATM straddle 25% SL | net Rs 3.55L, monthly t 3.82, PASS | net Rs 27.7k, t 0.37, FAIL |",
        "| S2 ATM straddle 50% SL | net Rs 3.40L, monthly t 3.73, PASS. "
        "At 0.5% slippage t 1.82, at 1% slippage t -0.10 | net Rs 84.1k, t 1.10, FAIL |",
        "| S3 OTM4 strangle 50% SL | net Rs 1.86L, monthly t 3.54, PASS | net Rs 23.3k, t 0.53, FAIL |",
        "| S4 iron fly with OTM8 wings, no leg SL | net Rs -2.39L, monthly t -2.90, FAIL | no holdout run |",
        "",
        "BANKNIFTY S2, 2017-2024, is a replication, not a holdout. "
        "t 5.48 at 0% slippage, 3.64 at 0.5% slippage, 1.68 at 1% slippage.",
    ]
    return "\n".join(lines) + "\n"


def install_track_a(path):
    """Insert or replace the AlgoTest record. Leave Attempt 17 and Attempt 18 alone."""
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    heading = "\n## Attempt 17-A (AlgoTest options selling)\n"
    block = "\n" + track_a_text().rstrip() + "\n\n"
    start = text.find(heading)
    if start != -1:
        nxt = text.find("\n## ", start + 1)
        end = nxt if nxt != -1 else len(text)
        text = text[:start] + block + text[end:]
    else:
        at = text.find("\n## Attempt 18\n")
        if at == -1:
            at = text.find("\n## Forward test\n")
        if at == -1:
            text = text.rstrip() + "\n" + block
        else:
            text = text[:at] + block + text[at:]
    if not text.endswith("\n"):
        text += "\n"
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


def _has_row(text, name):
    return ("| %s |" % name) in text


def _insert_after(text, anchor, addition):
    at = text.find(anchor)
    if at == -1:
        raise ValueError("missing anchor %s" % anchor)
    end = text.find("\n", at)
    if end == -1:
        end = len(text)
    return text[:end] + "\n" + addition + text[end:]


def add_family_rows(text):
    missing = []
    for line in FAMILY_ROWS:
        name = line.split("|")[1].strip()
        if not _has_row(text, name):
            missing.append(line)
    if not missing:
        return text
    return _insert_after(text, "| sector rotation | no |", "\n".join(missing))


def add_tier_row(text, tier, row):
    heading = "\n## %s\n" % tier
    start = text.find(heading)
    if start == -1:
        return text
    nxt = text.find("\n## ", start + 1)
    if nxt == -1:
        nxt = len(text)
    section = text[start:nxt]
    name = row.split("|")[1].strip()
    if ("| %s |" % name) in section:
        return text
    section = section.rstrip("\n") + "\n" + row + "\n\n"
    return text[:start] + section + text[nxt:]


def add_bucket_row(text, row):
    start = text.find("\n## Bucket\n")
    if start == -1:
        return text
    nxt = text.find("\n## ", start + 1)
    if nxt == -1:
        nxt = len(text)
    section = text[start:nxt]
    if "None yet." in section:
        table = "\n".join([
            "| Name | Attempt | Note |",
            "|---|---|---|",
            row,
            "",
        ])
        section = section.replace("None yet.\n", table, 1)
        return text[:start] + section + text[nxt:]
    return add_tier_row(text, "Bucket", row)


def set_family(text, name):
    old = "| %s | no |" % name
    new = "| %s | yes |" % name
    if old in text:
        return text.replace(old, new, 1)
    return text


def append_holdout_line(path, line):
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    if line in text:
        return
    if text and not text.endswith("\n"):
        text += "\n"
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text + line + "\n")


def record_catalogue(path):
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    text = add_family_rows(text)
    text = add_tier_row(text, "Watch", S2_ROW)
    text = add_tier_row(text, "Closed", S4_ROW)
    if not text.endswith("\n"):
        text += "\n"
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


def record_track_a(experiments, catalogue, log_path):
    install_track_a(experiments)
    record_catalogue(catalogue)
    append_holdout_line(log_path, HOLDOUT_LINE)


def ols_slope(xs, ys):
    """OLS slope of y on x, with an intercept, and the t of that slope (n - 2)."""
    n = len(xs)
    if n < 3 or n != len(ys):
        return None, None
    mx = sum(xs) / float(n)
    my = sum(ys) / float(n)
    sxx = 0.0
    sxy = 0.0
    for x, y in zip(xs, ys):
        dx = x - mx
        sxx += dx * dx
        sxy += dx * (y - my)
    if sxx == 0.0:
        return None, None
    slope = sxy / sxx
    intercept = my - slope * mx
    sse = 0.0
    for x, y in zip(xs, ys):
        err = y - (intercept + slope * x)
        sse += err * err
    if sse == 0.0:
        if slope > 0:
            return slope, float("inf")
        if slope < 0:
            return slope, float("-inf")
        return slope, 0.0
    se = ((sse / float(n - 2)) / sxx) ** 0.5
    if se == 0.0:
        return slope, None
    return slope, slope / se


def decay_label(slope, t):
    if slope is not None and t is not None and slope < 0 and t < -2:
        return "decaying"
    return "stable"


def fmt_t(value):
    if value is None:
        return "n/a"
    if value == float("inf"):
        return "+inf"
    if value == float("-inf"):
        return "-inf"
    return "%+.2f" % value


def fmt_slope(value):
    if value is None:
        return "n/a"
    return "%+.4f" % value


def trade_years(trades, first, last):
    by = {}
    for trade in trades:
        year = trade["date"].year
        if year < first or year > last:
            continue
        by.setdefault(year, []).append(trade["ret"])
    rows = []
    for year in range(first, last + 1):
        vals = by.get(year, [])
        t = h.t_stat(vals)
        rows.append({
            "year": year,
            "n": len(vals),
            "avg": h._mean(vals),
            "t": t,
            "used": t is not None,
        })
    return rows


def fit_years(rows):
    xs = []
    ys = []
    for row in rows:
        if row["used"] and row["avg"] is not None:
            xs.append(float(row["year"]))
            ys.append(row["avg"])
    slope, t = ols_slope(xs, ys)
    return {"slope": slope, "t": t, "label": decay_label(slope, t), "n": len(xs)}


def _collect_rsi(ctx, start, end):
    plain = []
    mixed = []
    nifty = ctx["nifty"]
    top200 = ctx["top200"]
    top100 = ctx["top100"]
    regimes = ctx["regimes"]
    for symbol in ctx["loaded"]:
        name = symbol["name"]
        for seg in symbol["segments"]:
            n = len(seg.date)
            for i in range(n - 1):
                signal = seg.date[i]
                entry_i = i + 1
                entry_day = seg.date[entry_i]
                if entry_day < start or entry_day > end:
                    continue
                if name not in top200.get(signal, ()):
                    continue
                if not f.rsi_fires(seg, i, 5.0, False):
                    continue
                found = f.exit_rule(seg, entry_i, f.RSI_LIMIT, f.close_above_sma5)
                done = f._finish(seg, entry_i, found, nifty)
                if done is None:
                    continue
                kind = regimes.get(entry_day)
                large = name in top100.get(signal, ())
                trade = f.make_trade(entry_day, name, done[0], done[1], kind, large, done[2])
                plain.append(trade)
                if kind in ("up", "sideways"):
                    mixed.append(trade)
    return plain, mixed


def _collect_rel(ctx, start, end):
    specs = []
    for spec in b17.REL_SPECS:
        if spec["name"] in ("rel rsi5", "rel rsi5 stock10"):
            specs.append(spec)
    collected = {}
    for spec in specs:
        collected[spec["name"]] = []
    nifty = ctx["nifty"]
    top200 = ctx["top200"]
    top100 = ctx["top100"]
    regimes = ctx["regimes"]
    for symbol in ctx["loaded"]:
        if not symbol.get("sector"):
            continue
        name = symbol["name"]
        for seg in symbol["segments"]:
            if not hasattr(seg, "rel_rsi"):
                continue
            n = len(seg.date)
            for i in range(n - 1):
                signal = seg.date[i]
                entry_i = i + 1
                entry_day = seg.date[entry_i]
                if entry_day < start or entry_day > end:
                    continue
                if name not in top200.get(signal, ()):
                    continue
                kind = regimes.get(entry_day)
                large = name in top100.get(signal, ())
                for spec in specs:
                    if not b17.rel_fires(seg, i, spec["rel_max"], spec["stock_max"]):
                        continue
                    found = f.exit_rule(seg, entry_i, f.RSI_LIMIT, f.close_above_sma5)
                    done = f._finish(seg, entry_i, found, nifty)
                    if done is None:
                        continue
                    collected[spec["name"]].append(
                        f.make_trade(entry_day, name, done[0], done[1], kind, large, done[2]))
    return collected


def month_book_returns(dates, equity, capital):
    last_i = {}
    for i, day in enumerate(dates):
        last_i[(day.year, day.month)] = i
    prev = float(capital)
    out = []
    for key in sorted(last_i):
        val = float(equity[last_i[key]])
        if prev > 0 and val > 0:
            out.append((key[0], (val / prev - 1.0) * 100.0))
        if val > 0:
            prev = val
    return out


def book_years(dates, equity, yearly, first, last):
    by = {}
    for year, ret in month_book_returns(dates, equity, h.CAPITAL):
        if first <= year <= last:
            by.setdefault(year, []).append(ret)
    rows = []
    for year in range(first, last + 1):
        vals = by.get(year, [])
        t = h.t_stat(vals)
        avg = yearly.get(year)
        rows.append({
            "year": year,
            "n": len(vals),
            "avg": avg,
            "t": t,
            "used": t is not None and avg is not None,
        })
    return rows


def run_decay(ctx, emit):
    emit("decay: rsi2 < 5 and m2")
    plain, mixed = _collect_rsi(ctx, f.SWING_START, h.END)
    emit("decay: sector-relative")
    rel = _collect_rel(ctx, f.SWING_START, h.END)
    emit("decay: tom rsi20")
    tom_blocks = b17.run_tom(ctx, f.SWING_START, h.END, 0, emit, only=["tom rsi20"])
    tom_rows = tom_blocks[0]["rows"] if tom_blocks else []
    emit("decay: momentum book")
    picks = h._portfolio_picks(
        MOM_SPEC, ctx["pairs"], ctx["top200"], ctx["by_name"], ctx["above"], None)
    equity = h.simulate_portfolio(
        ctx["pairs"], picks, ctx["calendar"], ctx["nifty"], ctx["by_name"])
    path = h.path_stats(ctx["calendar"], equity, h.CAPITAL, ctx["nifty"], ctx["regimes"])
    named = (
        ("rsi2 < 5", trade_years(plain, DECAY_FIRST, DECAY_LAST)),
        ("m2 regime", trade_years(mixed, DECAY_FIRST, DECAY_LAST)),
        ("rel rsi5", trade_years(rel.get("rel rsi5", []), DECAY_FIRST, DECAY_LAST)),
        ("rel rsi5 stock10", trade_years(rel.get("rel rsi5 stock10", []), DECAY_FIRST, DECAY_LAST)),
        ("tom rsi20", trade_years(tom_rows, DECAY_FIRST, DECAY_LAST)),
        ("mom 12-1 K20 above200", book_years(
            ctx["calendar"], equity, path["yearly"], DECAY_FIRST, DECAY_LAST)),
    )
    out = []
    for name, rows in named:
        fit = fit_years(rows)
        fit["name"] = name
        fit["rows"] = rows
        out.append(fit)
        emit("decay %s %s slope %s t %s" % (
            name, fit["label"], fmt_slope(fit["slope"]), fmt_t(fit["t"])))
    return out


def first_bars(path, n):
    rows = []
    with gzip.open(path, "rt", encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            rows.append(row)
            if len(rows) >= n:
                break
    return rows


def strike_of(filename):
    stem = filename.replace(".csv.gz", "")
    side = stem[-2:]
    digits = []
    i = len(stem) - 3
    while i >= 0 and stem[i].isdigit():
        digits.append(stem[i])
        i -= 1
    digits.reverse()
    return int("".join(digits)), side


def nifty_close_map(path, needed):
    found = {}
    with gzip.open(path, "rt", encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            day = row["datetime_start_ist"][:10]
            if day in needed:
                found[day] = row["close"]
            if len(found) == len(needed):
                break
    return found


def long_dated_report(root, emit):
    """Read the raw option files. Nothing under data/ is written."""
    folder = os.path.join(root, "options", "NIFTY", LONG_EXPIRY, "day")
    chosen = []
    for name in sorted(os.listdir(folder)):
        if not name.endswith(".csv.gz"):
            continue
        path = os.path.join(folder, name)
        bars = first_bars(path, 3)
        if not bars:
            continue
        start = bars[0]["datetime_start_ist"][:10]
        if start >= LONG_BEFORE:
            continue
        strike, side = strike_of(name)
        chosen.append((strike, side, name, bars))
    chosen.sort()
    needed = set()
    for _strike, _side, _name, bars in chosen:
        for bar in bars:
            needed.add(bar["datetime_start_ist"][:10])
    closes = nifty_close_map(data.bar_path(root, "day", lab.NIFTY), needed)
    strikes = [item[0] for item in chosen]
    every = bool(strikes) and all(strike % 500 == 0 for strike in strikes)
    emit("long-dated NIFTY %s contracts with a first bar before %s: %d" % (
        LONG_EXPIRY, LONG_BEFORE, len(chosen)))
    emit("every strike is a multiple of 500: %s" % ("yes" if every else "no"))
    lines = []
    lines.append("Long-dated check. Raw files, first 3 day bars, nothing trimmed.")
    lines.append("Contracts before %s: %d. Every strike a multiple of 500: %s." % (
        LONG_BEFORE, len(chosen), "yes" if every else "no"))
    for strike, side, name, bars in chosen:
        multiple = "yes" if strike % 500 == 0 else "no"
        emit("%s strike %d %s multiple of 500: %s" % (name, strike, side, multiple))
        lines.append("%s strike %d %s multiple of 500: %s" % (name, strike, side, multiple))
        for bar in bars:
            day = bar["datetime_start_ist"][:10]
            text = "  %s open %s high %s low %s close %s NIFTY close %s" % (
                bar["datetime_start_ist"], bar["open"], bar["high"], bar["low"],
                bar["close"], closes.get(day, "missing"))
            emit(text)
            lines.append(text)
    return lines


def session_prices(session):
    ends = session["end"]
    n = len(ends)
    if n == 0 or ends[0] != OPEN_END:
        return None
    opened = session["open"][0]
    closed = session["close"][n - 1]
    if not opened > 0 or not closed > 0:
        return None
    return opened, closed


def split_series(days):
    """days is (date, open, close) in order. Price returns, before costs."""
    out = []
    prev_close = None
    prev_date = None
    for day, opened, closed in days:
        overnight = None
        if prev_close is not None and prev_close > 0 and opened > 0:
            overnight = (opened / prev_close - 1.0) * 100.0
        intraday = None
        if opened > 0 and closed > 0:
            intraday = (closed / opened - 1.0) * 100.0
        out.append({
            "date": day,
            "prev": prev_date,
            "prev_close": prev_close,
            "open": opened,
            "close": closed,
            "overnight": overnight,
            "intraday": intraday,
        })
        if closed > 0:
            prev_close = closed
            prev_date = day
    return out


def read_sessions(path, start, end):
    """One Kite 5-minute file, grouped by session. Dates outside the window are skipped."""
    grouped = {}
    order = []
    start_s = start.isoformat()
    end_s = end.isoformat()
    with gzip.open(path, "rt", encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            stamp = row["datetime_start_ist"]
            day_s = stamp[:10]
            if day_s < start_s or day_s > end_s:
                continue
            day = datetime.date.fromisoformat(day_s)
            if day not in grouped:
                grouped[day] = []
                order.append(day)
            start_dt = datetime.datetime.strptime(stamp, "%Y-%m-%d %H:%M:%S")
            end_dt = start_dt + datetime.timedelta(minutes=5)
            grouped[day].append((
                end_dt.hour * 60 + end_dt.minute,
                float(row["open"]),
                float(row["close"]),
            ))
    sessions = []
    for day in order:
        bars = sorted(grouped[day], key=lambda item: item[0])
        sessions.append({
            "date": day,
            "end": [item[0] for item in bars],
            "open": [item[1] for item in bars],
            "close": [item[2] for item in bars],
        })
    sessions.sort(key=lambda item: item["date"])
    return sessions


def sessions_from_series(series):
    out = []
    for segment in series.segments:
        for item in segment:
            out.append(item["session"])
    out.sort(key=lambda item: item["date"])
    return out


def legs_of(sessions):
    days = []
    for session in sessions:
        prices = session_prices(session)
        if prices is None:
            continue
        days.append((session["date"], prices[0], prices[1]))
    return split_series(days)


def futures_return(entry, exit_px, entry_day, exit_day, lot):
    if not entry > 0 or not exit_px > 0 or not lot > 0:
        return None
    buy = lot * entry
    sell = lot * exit_px
    rolls = b16.rollover_count(entry_day, exit_day)
    cost = b16.futures_side(buy, True) + b16.futures_side(sell, False)
    cost += rolls * b16.round_trip(buy)
    return (sell - buy - cost) / buy * 100.0


def monthly_t(trades, key):
    by = {}
    for trade in trades:
        value = trade.get(key)
        if value is None:
            continue
        month = (trade["date"].year, trade["date"].month)
        by.setdefault(month, []).append(value)
    means = []
    for month in sorted(by):
        means.append(h._mean(by[month]))
    return h.t_stat(means)


def slice_means(trades, early, late):
    buckets = {"early": [], "late": [], "up": [], "down": [], "sideways": []}
    for trade in trades:
        year = trade["date"].year
        if early[0] <= year <= early[1]:
            buckets["early"].append(trade["ret"])
        if late[0] <= year <= late[1]:
            buckets["late"].append(trade["ret"])
        kind = trade.get("regime")
        if kind in buckets:
            buckets[kind].append(trade["ret"])
    out = {}
    for key in buckets:
        out[key] = h._mean(buckets[key])
    return out


def judge_leg(block):
    need = block["t_need"]
    reasons = []
    if block["avg"] is None or not block["avg"] > 0:
        reasons.append("avg after costs %s is not above 0" % h._pct(block["avg"]))
    if block["t"] is None or not block["t"] > need:
        reasons.append("monthly t %s is not above %d" % (h._num(block["t"]), need))
    labels = (
        ("early", block["early_label"]),
        ("late", block["late_label"]),
        ("up", "up"),
        ("down", "down"),
        ("sideways", "sideways"),
    )
    for key, label in labels:
        if block.get(key) is None or not block[key] > 0:
            reasons.append("%s %s is not above 0" % (label, h._pct(block.get(key))))
    return {"result": "PASS" if not reasons else "FAIL", "reasons": reasons}


def finish_block(name, family, trades, early, late, early_label, late_label, t_need, t_key):
    block = {
        "name": name,
        "family": family,
        "trades": len(trades),
        "avg": h._mean([item["ret"] for item in trades]),
        "t": monthly_t(trades, t_key),
        "rows": trades,
        "t_need": t_need,
        "early_label": early_label,
        "late_label": late_label,
    }
    block.update(slice_means(trades, early, late))
    block["verdict"] = judge_leg(block)
    return block


def score_index(rows, label, lot, regimes, start):
    blocks = []
    for kind, entry_of in (
        ("overnight", "overnight"),
        ("intraday", "intraday"),
    ):
        trades = []
        for row in rows:
            if row["date"] < start:
                continue
            if kind == "overnight":
                if row["prev"] is None or row["prev_close"] is None:
                    continue
                ret = futures_return(
                    row["prev_close"], row["open"], row["prev"], row["date"], lot)
            else:
                ret = futures_return(row["open"], row["close"], row["date"], row["date"], lot)
            if ret is None:
                continue
            trades.append({
                "date": row["date"],
                "ret": ret,
                "regime": regimes.get(row["date"]),
            })
        name = "%s %s" % (label, kind)
        blocks.append(finish_block(
            name, "overnight", trades,
            (2015, 2019), (2020, 2024), "2015-2019", "2020-2024", 3, "ret"))
    return blocks


def run_overnight(root, regimes, emit, start, end):
    blocks = []
    for label, symbol, lot in (
        ("nifty", lab.NIFTY, h.NIFTY_LOT),
        ("bank", "NIFTY BANK", BANK_LOT),
    ):
        path = data.bar_path(root, "5minute", symbol)
        emit("reading %s" % symbol)
        sessions = read_sessions(path, start, end)
        rows = legs_of(sessions)
        blocks.extend(score_index(rows, label, lot, regimes, start))
    return blocks


def holiday_windows(calendar, holidays, start, end):
    """Unique (entry, held). held is the last session strictly before the holiday."""
    seen = set()
    out = []
    last = calendar[-1] if calendar else None
    for holiday in sorted(holidays):
        if last is None or holiday > last:
            continue
        i = bisect.bisect_left(calendar, holiday)
        if i < 2:
            continue
        held = calendar[i - 1]
        entry = calendar[i - 2]
        if held < start or held > end or not held < holiday:
            continue
        key = (entry, held)
        if key in seen:
            continue
        seen.add(key)
        out.append(key)
    return out


def preholiday_trades(calendar, nifty, regimes, holidays, start, end, runs):
    days = []
    for day in calendar:
        bar = nifty.get(day)
        if bar is None or not bar.get("close", 0) > 0:
            continue
        days.append(day)
    windows = holiday_windows(days, holidays, start, end)
    trades = []
    for event_i, (entry, held) in enumerate(windows):
        ret = futures_return(
            nifty[entry]["close"], nifty[held]["close"], entry, held, h.NIFTY_LOT)
        if ret is None:
            continue
        rng = random.Random(h.SEED + HOLIDAY_SEED + event_i)
        picked = b16._random_windows(days, entry, held, held.year, rng, runs)
        baseline = []
        for start_i in picked:
            a = days[start_i]
            b = days[start_i + 1]
            value = futures_return(nifty[a]["close"], nifty[b]["close"], a, b, h.NIFTY_LOT)
            if value is not None:
                baseline.append(value)
        excess = None
        if baseline:
            excess = ret - h._mean(baseline)
        trades.append({
            "date": held,
            "entry": entry,
            "ret": ret,
            "excess": excess,
            "regime": regimes.get(held),
        })
    return trades


def run_preholiday(ctx, emit, start, end, runs):
    holidays = nse_holidays.between(start, end)
    calendar = sorted(ctx["nifty"])
    trades = preholiday_trades(
        calendar, ctx["nifty"], ctx["regimes"], holidays, start, end, runs)
    need = 2 if len(trades) < 150 else 3
    block = finish_block(
        "pre-holiday", "pre-holiday", trades,
        (2010, 2014), (2015, 2024), "2010-2014", "2015-2024", need, "excess")
    emit("pre-holiday events %d, t bar above %d" % (block["trades"], need))
    return block


def judge_holdout(block):
    reasons = []
    if block["avg"] is None or not block["avg"] > 0:
        reasons.append("holdout avg after costs %s is not above 0" % h._pct(block["avg"]))
    if block["t"] is None or not block["t"] > 2:
        reasons.append("holdout t %s is not above 2" % h._num(block["t"]))
    return {"result": "PASS" if not reasons else "FAIL", "reasons": reasons}


def _nifty_from_segments(segments):
    nifty = {}
    points = []
    for seg in segments:
        for i, day in enumerate(seg.date):
            nifty[day] = {"open": seg.o[i], "close": seg.c[i]}
            points.append((day, seg.c[i]))
    points.sort()
    return nifty, regime.by_date(points)


def run_holdout(root, overnight_blocks, holiday_block, emit):
    """The only final=True load. Called after an in-sample pass."""
    _first, last = survivorship.raw_span(data.bar_path(root, "day", lab.NIFTY))
    emit("holdout %s to %s" % (data.HOLDOUT_START.isoformat(), last.isoformat()))
    segments = lab.load_symbol(root, lab.NIFTY, end=last, final=True)
    nifty, regimes = _nifty_from_segments(segments)
    ctx = {"nifty": nifty, "regimes": regimes, "calendar": sorted(nifty)}
    looked = []
    if overnight_blocks:
        looked.append("overnight")
        flag = True
        begin = datetime.date(2024, 12, 1)
        cached = {}
        for block in overnight_blocks:
            label = block["name"].split()[0]
            symbol = lab.NIFTY if label == "nifty" else "NIFTY BANK"
            lot = h.NIFTY_LOT if label == "nifty" else BANK_LOT
            if symbol not in cached:
                series = data.load_arrays(
                    root, symbol, "5minute", start=begin, end=last, final=flag)
                cached[symbol] = legs_of(sessions_from_series(series))
            rows = cached[symbol]
            kind = block["name"].split()[1]
            scored = score_index(rows, label, lot, regimes, data.HOLDOUT_START)
            found = None
            for item in scored:
                if item["name"].endswith(kind):
                    found = item
            if found is None:
                continue
            hold = {
                "trades": found["trades"],
                "avg": found["avg"],
                "t": found["t"],
            }
            hold["verdict"] = judge_holdout(hold)
            block["holdout"] = hold
            emit("holdout %s %s avg %s t %s" % (
                block["name"], hold["verdict"]["result"], h._pct(hold["avg"]), h._num(hold["t"])))
    if holiday_block is not None:
        looked.append("pre-holiday")
        trades = preholiday_trades(
            ctx["calendar"], nifty, regimes,
            nse_holidays.between(data.HOLDOUT_START, last),
            data.HOLDOUT_START, last, HOLIDAY_RUNS)
        block = finish_block(
            "pre-holiday", "pre-holiday", trades,
            (2025, 2026), (2025, 2026), "2025-2026", "2025-2026", 3, "excess")
        hold = {"trades": block["trades"], "avg": block["avg"], "t": block["t"]}
        hold["verdict"] = judge_holdout(hold)
        holiday_block["holdout"] = hold
        emit("holdout pre-holiday %s events %d avg %s t %s" % (
            hold["verdict"]["result"], hold["trades"], h._pct(hold["avg"]), h._num(hold["t"])))
    return looked


def tier_of(block):
    if block["verdict"]["result"] != "PASS":
        return "Closed"
    hold = block.get("holdout") or {}
    verdict = hold.get("verdict") or {}
    if verdict.get("result") == "PASS":
        return "Bucket"
    if hold.get("avg") is not None and hold["avg"] > 0:
        return "Watch"
    return "Closed"


def note_of(block):
    if block["verdict"]["result"] != "PASS":
        return "FAIL"
    hold = block.get("holdout") or {}
    verdict = hold.get("verdict") or {}
    return "PASS Holdout %s, avg %s, t %s." % (
        verdict.get("result", "n/a"), h._pct(hold.get("avg")), h._num(hold.get("t")))


def finish_catalogue(path, blocks, looked):
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    for block in blocks:
        tier = tier_of(block)
        row = "| %s | 18 | %s |" % (block["name"], note_of(block))
        if tier == "Bucket":
            text = add_bucket_row(text, row)
        else:
            text = add_tier_row(text, tier, row)
    for name in looked:
        text = set_family(text, name)
    if not text.endswith("\n"):
        text += "\n"
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


def bucket_line(path):
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    start = text.find("\n## Bucket\n")
    nxt = text.find("\n## ", start + 1)
    section = text[start:nxt]
    if "None yet." in section:
        return "Bucket: empty"
    names = []
    for line in section.splitlines():
        if not line.startswith("| "):
            continue
        cell = line.split("|")[1].strip()
        if cell in ("Name", "") or set(cell) <= set("-:"):
            continue
        names.append(cell)
    if not names:
        return "Bucket: empty"
    return "Bucket: %s" % ", ".join(names)


def _year_lines(fit):
    lines = ["%s %s slope %s t %s (%d years in the regression)" % (
        fit["name"], fit["label"], fmt_slope(fit["slope"]), fmt_t(fit["t"]), fit["n"])]
    lines.append("year | n | avg | t | in regression")
    for row in fit["rows"]:
        lines.append("%d | %d | %s | %s | %s" % (
            row["year"], row["n"], h._pct(row["avg"]), fmt_t(row["t"]),
            "yes" if row["used"] else "no"))
    return lines


def _leg_line(block):
    return "%s | %d | %s | %s | %s %s | %s %s | %s | %s | %s | %s" % (
        block["name"], block["trades"], h._pct(block["avg"]), h._num(block["t"]),
        block["early_label"], h._pct(block["early"]),
        block["late_label"], h._pct(block["late"]),
        h._pct(block["up"]), h._pct(block["down"]), h._pct(block["sideways"]),
        block["verdict"]["result"])


def emit_block(emit, block):
    emit(_leg_line(block))
    for reason in block["verdict"]["reasons"]:
        emit("  %s" % reason)
    hold = block.get("holdout")
    if hold:
        emit("  holdout %s events %s avg %s t %s" % (
            hold["verdict"]["result"], hold["trades"], h._pct(hold["avg"]), h._num(hold["t"])))
        for reason in hold["verdict"]["reasons"]:
            emit("  %s" % reason)


def result_rows(fits, overnight, holiday):
    rows = []
    for fit in fits:
        rows.append("| 18 | %s | decay %s, slope %s, t %s |" % (
            fit["name"], fit["label"], fmt_slope(fit["slope"]), fmt_t(fit["t"])))
    for block in overnight:
        rows.append("| 18 | %s | %s | avg %s, monthly t %s |" % (
            block["name"], block["verdict"]["result"], h._pct(block["avg"]), h._num(block["t"])))
    rows.append("| 18 | %s | %s | avg %s, monthly t %s, events %d |" % (
        holiday["name"], holiday["verdict"]["result"],
        h._pct(holiday["avg"]), h._num(holiday["t"]), holiday["trades"]))
    return rows


def main(argv=None, log=None):
    import argparse
    parser = argparse.ArgumentParser(description="Attempt 18. Nothing is placed.")
    parser.add_argument("--root", default=os.path.join("data", "kite"))
    parser.add_argument("--experiments", default=h.EXPERIMENTS)
    parser.add_argument("--catalogue", default=h.CATALOGUE)
    parser.add_argument("--log", default=data.HOLDOUT_LOG)
    parser.add_argument("--industries", default=os.path.join(_ROOT, "india", "universe", "nifty500.csv"))
    args = parser.parse_args(argv)
    emit = log or (lambda line: print(line, flush=True))

    f.install_attempt(args.experiments, 18, rules_text(), [])
    emit("rules for attempt 18 written to %s before the run" % args.experiments)
    record_track_a(args.experiments, args.catalogue, args.log)
    emit("Track A recorded. AlgoTest was not rerun.")

    option_lines = long_dated_report(args.root, emit)

    research = False
    emit("loading stocks through %s" % h.END.isoformat())
    ctx = b17.prepare_context(args.root, h.END, emit, research)
    industries = b16.load_industries(args.industries)
    mapped = b17.attach_relative(ctx, industries)
    emit("sector map %d" % mapped)

    fits = run_decay(ctx, emit)
    overnight = run_overnight(
        args.root, ctx["regimes"], emit, h.INTRADAY_START, h.END)
    holiday = run_preholiday(
        ctx, emit, nse_holidays.RESEARCH_START, nse_holidays.RESEARCH_END, HOLIDAY_RUNS)

    passed_night = []
    for block in overnight:
        if block["verdict"]["result"] == "PASS":
            passed_night.append(block)
    passed_holiday = holiday if holiday["verdict"]["result"] == "PASS" else None
    looked = []
    if passed_night or passed_holiday is not None:
        looked = run_holdout(args.root, passed_night, passed_holiday, emit)
    else:
        emit("no holdout was run")

    finish_catalogue(args.catalogue, overnight + [holiday], looked)

    lines = ["Results.", ""]
    lines.extend(option_lines)
    lines.append("")
    lines.append("18a Decay. No pass mark.")
    for fit in fits:
        lines.extend(_year_lines(fit))
        lines.append("")
    lines.append("18b Overnight vs intraday.")
    lines.append("name | n | avg | monthly t | early | late | up | down | sideways | result")
    for block in overnight:
        lines.append(_leg_line(block))
        for reason in block["verdict"]["reasons"]:
            lines.append("  %s" % reason)
        hold = block.get("holdout")
        if hold:
            lines.append("  holdout %s avg %s t %s" % (
                hold["verdict"]["result"], h._pct(hold["avg"]), h._num(hold["t"])))
    lines.append("")
    lines.append("18c Pre-holiday. t bar above %d because events are %d." % (
        holiday["t_need"], holiday["trades"]))
    lines.append(_leg_line(holiday))
    for reason in holiday["verdict"]["reasons"]:
        lines.append("  %s" % reason)
    hold = holiday.get("holdout")
    if hold:
        lines.append("  holdout %s events %s avg %s t %s" % (
            hold["verdict"]["result"], hold["trades"], h._pct(hold["avg"]), h._num(hold["t"])))
    if not looked:
        lines.append("")
        lines.append("No family passed in sample, so no holdout was run.")
    lines.append("")
    lines.append(bucket_line(args.catalogue))
    section = rules_text().rstrip() + "\n\n" + "\n".join(lines)
    f.install_attempt(
        args.experiments, 18, section, result_rows(fits, overnight, holiday))

    emit("")
    emit("18a Decay")
    for fit in fits:
        for line in _year_lines(fit):
            emit(line)
        emit("")
    emit("18b Overnight vs intraday")
    emit("name | n | avg | monthly t | early | late | up | down | sideways | result")
    for block in overnight:
        emit_block(emit, block)
    emit("")
    emit("18c Pre-holiday")
    emit_block(emit, holiday)
    emit("")
    if not looked:
        emit("no family passed in sample, so no holdout was run")
    emit(bucket_line(args.catalogue))


if __name__ == "__main__":
    main()
