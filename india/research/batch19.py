#!/usr/bin/env python3
"""Step 25. Options hygiene, the blend study, the forward record, attempt 19.

Rules are written to EXPERIMENTS.md before any of that runs. Nothing is placed.

    python3 india/research/batch19.py
"""

import bisect
import csv
import datetime
import gzip
import itertools
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from india.research import batch16 as b16
from india.research import batch17 as b17
from india.research import batch18 as b18
from india.research import data
from india.research import follow as f
from india.research import forward
from india.research import harness as h
from india.research import signal_lab as lab
from india.research import verify as v

PRIOR = 250
LOW_RANK = 50
HOLD = 5
Z_WINDOW = 60
BASKET = 10
NOTIONAL = 100000.0
BASIS_YEAR = 365.0
BASIS_START = datetime.date(2011, 1, 1)
EARLY = (2011, 2017)
LATE = (2018, 2024)
INDEX_FUTURES = ("NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY", "NIFTYNXT50", "NIFTYFPI")
LONG_EXPIRY = "2026-12-29"
LONG_BEFORE = datetime.date(2026, 8, 1)
FAMILY = "futures basis"
NAMES = ("nifty basis 5d", "stock basis z10")


def rules_text():
    """Attempt 19, fixed before the run. No inner heading."""
    today = datetime.date.today().isoformat()
    lines = [
        "## Attempt 19",
        "",
        "Rules fixed on %s, before the run." % today,
        "",
        "Family: futures basis. This is a new family. Its holdout stays unused until a variant passes in sample.",
        "",
        "Data: data/kite/futures/day, the continuous series, one file per underlying. Scored trades enter on 2011-01-01 through 2024-12-31. Bars from 2010 may warm the lookback. The file has no expiry column and open interest is not used. A futures bar is kept when its open and its close are both above 0. Volume is not a filter on these files. Spot is the day close. NIFTY futures use the NIFTY 50 day file. A future with no spot series is skipped. The stock cross-section leaves out NIFTY, BANKNIFTY, FINNIFTY, MIDCPNIFTY, NIFTYNXT50 and NIFTYFPI.",
        "",
        "Expiry, stated before the run. For a session date, the front month is this month's expiry when the session is on or before that expiry, and the next month otherwise. The monthly expiry is the last Thursday of the month for expiry months through 2025-08, and the last Tuesday of the month from 2025-09 on. When that weekday is a NIFTY session, it is the expiry. When it is not a session and it falls on or before the last date in the NIFTY calendar, the previous NIFTY session is the expiry. When the raw weekday falls after the last calendar date, the raw weekday is kept and is not pulled back into the file. Days to expiry below 1 leave the basis undefined, including the expiry day itself. Annualised basis is (future close / spot close - 1) times (365 / days). The year is 365 days, not 365.25. A price that is not above 0 is skipped.",
        "",
        "Costs, check your broker. The attempt 16 futures schedule: brokerage Rs 20 a side, STT 0.05 percent of the sell, exchange 0.00173 percent, SEBI 0.0001 percent, stamp 0.002 percent of the buy, GST 18 percent of brokerage plus exchange plus SEBI. A rollover is one extra round trip for each month-start strictly after the entry and on or before the exit. NIFTY uses lot 75. The continuous file does not carry a stock's lot, so each stock name is sized at Rs 1,00,000 of futures notional.",
        "",
        "19a, nifty basis 5d. Long NIFTY futures for 5 sessions when today's annualised basis is at or below the 50th smallest of the previous 250 defined readings of this series. That 50th value is the top of the lowest 20 percent of 250. The 250 readings do not include today. Otherwise the book is flat, and a new signal is ignored until the open position exits. The signal is known at the close. Entry is the next session's future open. Exit is the open 5 sessions later, so a signal at index i enters at i+1 and exits at i+6. A trade whose exit is past the loaded series, or whose exit date is after 2024-12-31, is not recorded. The entry must fall in 2011-01-01 through 2024-12-31. The session calendar is the dates present in both the NIFTY future file and the NIFTY 50 spot.",
        "",
        "19b, stock basis z10. Each Monday from 2011-01-01 whose next Monday session is on or before 2024-12-31. A Monday that is not a NIFTY session is already absent. The signal day is the NIFTY session immediately before that Monday. The z-score is the basis that day, minus the mean of the prior 60 defined readings of that name, divided by the sample standard deviation of those 60. The 60 do not include the signal day. A name with fewer than 60 prior readings, a standard deviation of 0, or no defined basis that day is skipped. Long the 10 lowest z-scores among names that also have a future open on both Mondays. A tie breaks on the name. Fewer than 10 qualifying names skips the week. Entry is Monday's future open and exit is the next Monday session's future open. Equal weight. Excess is the basket's after-cost return minus the equal-weight after-cost return of every stock future that has both opens that week, including names without a z-score and including the 10 that were chosen. A week with fewer than 2 priced names stays in the average and stays out of the t.",
        "",
        "Pass, the attempt 14 shape with these clauses only. The after-cost average of the strategy's own return is above 0. The monthly t is above 3. The mean own return is positive in 2011-2017, in 2018-2024, and in up, down and sideways. An empty bucket fails. There is no large-cap clause and no family gate. Each variant is judged on its own. For 19a the monthly t is the one-sample t of the monthly means of the after-cost trade returns. For 19b the monthly t is the one-sample t of the monthly means of the excess, and the average that must be above 0 is the basket's own return. The regime is the NIFTY daily regime of the entry date. The decades use the entry year.",
        "",
        "Holdout, only for a variant that passes. One load, logged, from 2025-01-01 through the last NIFTY daily date. Futures bars through that date are read directly, so the 250 and 60 lookbacks have their warmup, and a trade with an entry before 2025-01-01 is dropped. Holdout pass is an after-cost average above 0 and a t above 2. For 19a that t is the monthly t of the after-cost returns. For 19b it is the monthly t of the excesses. The in-sample bar of t above 3 is not applied again. If neither variant passes, the holdout is not opened.",
        "",
        "The research window keeps final false.",
    ]
    return "\n".join(lines)


def forward_book_text():
    """Forward book v1, fixed before the blend. The trio is filled in after."""
    today = datetime.date.today().isoformat()
    lines = [
        "## Forward book v1",
        "",
        "Rules fixed on %s, before the blend." % today,
        "",
        "Research window 2005-01-01 to 2024-12-31. final stays false. No pass mark and no holdout.",
        "",
        "The six books are rsi2 < 5, m2 regime, rel rsi5, rel rsi5 stock10, tom rsi20, and mom 12-1 K20 above200. Capital is Rs 10,00,000. Idle cash sits in NIFTY 50 with no cost on that sleeve.",
        "",
        "rsi2 < 5, m2 regime, rel rsi5 and rel rsi5 stock10 use the 10-slot book. Each slot is Rs 1,00,000. Delivery costs. The signal is the existing rule, known at the close. Entry is the next open. Exit is the next open after a close above SMA5, otherwise the open 5 sessions after entry. A day with more signals than free slots fills the lowest RSI first, then the higher prior 60-session turnover, then the name. For the two relative books that sort value is the relative RSI. m2 keeps a trade only when the entry-day regime is up or sideways. An exit that is not a NIFTY session moves to the next session. A name already held is skipped.",
        "",
        "tom rsi20 holds the basket from the entry close to the exit close. The window is the close of the session before the last session of the month through the close of the third session of the next month. The names are the 20 lowest RSI(2) in that day's top 200 whose close is strictly above SMA200. Equal weight. Rs 10,00,000 is split across the names that have both closes. Delivery costs. The book is entirely in NIFTY outside the window. Windows do not overlap.",
        "",
        "mom 12-1 K20 above200 is the harness portfolio: 20 names, above the 200-session average, delivery costs, idle cash in NIFTY. No random books.",
        "",
        "A monthly return is the month-end equity over the prior month-end, minus 1, in percent. The first month starts from capital. Every month-end in 2005 through 2024 is a point, including a month that holds only NIFTY. The correlation is the Pearson correlation of those percent returns on the months both books have. Pearson needs at least 3 months and a non-zero variance on each side, otherwise that pair is missing.",
        "",
        "The blend month is the mean of the members' monthly returns. The equity curve starts at 1 and compounds those months. CAGR percent is (final to the power of 12 over the number of months, minus 1) times 100. Max drawdown is the deepest peak-to-equity drop of that curve, in percent. The worst calendar year is the lowest compounded calendar-year return. A year with fewer than 12 months still counts. The share of positive years counts a year only when its compounded return is strictly above 0.",
        "",
        "One blend is the equal weight of all 6. The other is the equal weight of the 3 least correlated. Among the 20 trios, the choice is the lowest average of the three pairwise correlations. A tie breaks on the alphabetical sorted name tuple, compared as (average, tuple). A trio with a missing correlation is left out.",
        "",
        "Forward record. Sessions of NIFTY 50 strictly after 2026-11-04. A date on or before that day is refused. For rsi2 < 5, m2 regime, rel rsi5, rel rsi5 stock10 and tom rsi20, a trade counts when its entry is after that day. The average is the mean of those after-cost trade returns and the t is their one-sample t. Fewer than 2 leaves t blank. For mom 12-1 K20 above200 the points are the daily book returns on sessions after that day. The first of those uses the prior session's equity as its base, and the cutoff session is not a point. Forward book v1 is the equal-weight mean of the three constituents' book daily returns. A session counts only when all three have a return. The count is the number of trades, or the number of sessions for the momentum book and for Forward book v1. The three names are frozen on the line below. They are not estimated again. Nothing in the record places an order.",
        "",
        "Constituents: pending the study.",
    ]
    return "\n".join(lines)


def install_forward_book(path, section):
    """Insert or replace Forward book v1. Stop at the next heading."""
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    heading = "\n## Forward book v1\n"
    block = "\n" + section.rstrip() + "\n\n"
    start = text.find(heading)
    if start != -1:
        nxt = text.find("\n## ", start + 1)
        end = nxt if nxt != -1 else len(text)
        text = text[:start] + block + text[end:]
    else:
        at = text.find("\n## Attempt 19\n")
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


def add_basis_family(path):
    """One family row, holdout unused, inserted before the run."""
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    if "| %s |" % FAMILY in text:
        return
    anchor = "| pre-holiday | no |"
    at = text.find(anchor)
    if at == -1:
        raise RuntimeError("missing family anchor")
    end = text.find("\n", at)
    if end == -1:
        end = len(text)
    text = text[:end] + "\n| %s | no |" % FAMILY + text[end:]
    if not text.endswith("\n"):
        text += "\n"
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


def write_rules(experiments, catalogue):
    install_forward_book(experiments, forward_book_text())
    f.install_attempt(experiments, 19, rules_text(), [])
    if catalogue:
        add_basis_family(catalogue)


def fill_forward_book(path, names, lines):
    """Replace the pending line, then store the blend results in that section."""
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    old = "Constituents: pending the study."
    if old not in text:
        raise RuntimeError("constituents line missing")
    text = text.replace(old, "Constituents: %s." % ", ".join(names), 1)
    at = text.find("\n## Attempt 19\n")
    block = "\n".join(lines).rstrip() + "\n\n"
    if at == -1:
        text = text.rstrip() + "\n\n" + block
    else:
        text = text[:at] + "\n" + block + text[at:]
    if not text.endswith("\n"):
        text += "\n"
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


def _file_start(path):
    with gzip.open(path, "rt", encoding="utf-8", newline="") as fh:
        row = next(csv.DictReader(fh), None)
    if row is None:
        return None
    return datetime.date.fromisoformat(row["datetime_start_ist"][:10])


def long_dated_lines(root):
    """first_traded for the 12 long-dated NIFTY 2026-12-29 contracts. Files are not trimmed."""
    folder = os.path.join(root, "options", "NIFTY", LONG_EXPIRY, "day")
    lines = ["Options hygiene. Volume 0 is dropped. first_traded is the first date with volume above 0."]
    if not os.path.isdir(folder):
        lines.append("options folder missing: %s" % folder)
        return lines
    found = []
    for name in sorted(os.listdir(folder)):
        if not name.endswith(".csv.gz"):
            continue
        path = os.path.join(folder, name)
        start = _file_start(path)
        if start is None or not start < LONG_BEFORE:
            continue
        found.append((name[:-7], start, data.first_traded(path)))
    lines.append("long-dated contracts %d (file starts before %s)" % (len(found), LONG_BEFORE.isoformat()))
    lines.append("symbol | file start | first traded")
    for symbol, start, traded in found:
        traded_text = "none" if traded is None else traded.isoformat()
        lines.append("%s | %s | %s" % (symbol, start.isoformat(), traded_text))
    return lines


def last_weekday(year, month, weekday):
    if month == 12:
        nxt = datetime.date(year + 1, 1, 1)
    else:
        nxt = datetime.date(year, month + 1, 1)
    last = nxt - datetime.timedelta(days=1)
    back = (last.weekday() - weekday) % 7
    return last - datetime.timedelta(days=back)


def raw_expiry(year, month):
    """Last Thursday through 2025-08. Last Tuesday from 2025-09."""
    if (year, month) <= (2025, 8):
        return last_weekday(year, month, 3)
    return last_weekday(year, month, 1)


def annualised(future_close, spot_close, day, expiry):
    """Decimal basis. None when a price is not above 0 or days to expiry are below 1."""
    if not future_close > 0 or not spot_close > 0:
        return None
    days = (expiry - day).days
    if days < 1:
        return None
    return (future_close / spot_close - 1.0) * (BASIS_YEAR / float(days))


def expiry_table(days):
    """Front-month expiry for each year-month the calendar can see, plus the next month."""
    if not days:
        return {}
    last = days[-1]
    have = set(days)
    year = days[0].year
    month = days[0].month
    table = {}
    limit = last + datetime.timedelta(days=70)
    while datetime.date(year, month, 1) <= limit:
        raw = raw_expiry(year, month)
        if raw in have:
            got = raw
        elif raw > last:
            got = raw
        else:
            got = b16.on_or_before(raw, days)
            if got is None:
                got = raw
        table[(year, month)] = got
        if month == 12:
            year += 1
            month = 1
        else:
            month += 1
    return table


def front_expiry(day, table):
    this = table.get((day.year, day.month))
    if this is None:
        return None
    if day <= this:
        return this
    year = day.year
    month = day.month + 1
    if month == 13:
        year += 1
        month = 1
    return table.get((year, month))


def read_future(path, end):
    """Continuous bars through end. A bar needs an open and a close above 0."""
    out = {}
    with gzip.open(path, "rt", encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            day = datetime.date.fromisoformat(row["datetime_start_ist"][:10])
            if end is not None and day > end:
                continue
            opened = float(row["open"])
            closed = float(row["close"])
            if not opened > 0 or not closed > 0:
                continue
            out[day] = {"open": opened, "close": closed}
    return out


def nifty_days(ctx, end):
    days = []
    for day, bar in ctx["nifty"].items():
        if day <= end and bar.get("close", 0) > 0:
            days.append(day)
    days.sort()
    return days


def spot_close(ctx, symbol, day):
    if symbol == "NIFTY":
        bar = ctx["nifty"].get(day)
        if bar is None:
            return None
        px = bar.get("close")
        if px is None or not px > 0:
            return None
        return px
    loc = ctx["by_name"].get(symbol, {}).get(day)
    if loc is None:
        return None
    px = loc[0].c[loc[1]]
    if not px > 0:
        return None
    return px


def joint_rows(fut, ctx, symbol, table):
    rows = []
    for day in sorted(fut):
        spot = spot_close(ctx, symbol, day)
        if spot is None:
            continue
        exp = front_expiry(day, table)
        basis = None if exp is None else annualised(fut[day]["close"], spot, day, exp)
        rows.append({
            "date": day,
            "open": fut[day]["open"],
            "close": fut[day]["close"],
            "basis": basis,
        })
    return rows


def nifty_trades(rows, regimes, start, end):
    """One position. A signal is ignored until the previous one exits."""
    values = []
    pos = {}
    for i, row in enumerate(rows):
        if row["basis"] is not None:
            pos[i] = len(values)
            values.append(row["basis"])
    trades = []
    i = 0
    n = len(rows)
    while i < n:
        k = pos.get(i)
        if k is None or k < PRIOR:
            i += 1
            continue
        cutoff = sorted(values[k - PRIOR:k])[LOW_RANK - 1]
        if not values[k] <= cutoff:
            i += 1
            continue
        exit_i = i + 1 + HOLD
        if exit_i >= n:
            break
        entry = rows[i + 1]
        exit_row = rows[exit_i]
        entry_day = entry["date"]
        exit_day = exit_row["date"]
        if start <= entry_day <= end and exit_day <= end:
            ret = b18.futures_return(
                entry["open"], exit_row["open"], entry_day, exit_day, h.NIFTY_LOT)
            if ret is not None:
                trades.append({
                    "date": entry_day,
                    "ret": ret,
                    "regime": regimes.get(entry_day),
                })
        i = exit_i
    return trades


def z_at(dates, values, day):
    i = bisect.bisect_left(dates, day)
    if i >= len(dates) or dates[i] != day or i < Z_WINDOW:
        return None
    window = values[i - Z_WINDOW:i]
    mean = sum(window) / float(Z_WINDOW)
    var = 0.0
    for value in window:
        diff = value - mean
        var += diff * diff
    var /= float(Z_WINDOW - 1)
    if var == 0.0:
        return None
    return (values[i] - mean) / (var ** 0.5)


def futures_notional(entry, exit_px, entry_day, exit_day):
    if not entry > 0:
        return None
    return b18.futures_return(entry, exit_px, entry_day, exit_day, NOTIONAL / entry)


def stock_trades(series, days, regimes, start, end):
    day_index = {}
    for i, day in enumerate(days):
        day_index[day] = i
    mondays = []
    for day in days:
        if day.weekday() == 0 and day >= start:
            mondays.append(day)
    trades = []
    for i, monday in enumerate(mondays):
        if i + 1 >= len(mondays):
            break
        nxt = mondays[i + 1]
        if nxt > end or monday > end:
            continue
        k = day_index[monday]
        if k < 1:
            continue
        signal = days[k - 1]
        scored = []
        for name, pack in series.items():
            if pack["by"].get(monday) is None or pack["by"].get(nxt) is None:
                continue
            zed = z_at(pack["dates"], pack["values"], signal)
            if zed is None:
                continue
            scored.append((zed, name))
        if len(scored) < BASKET:
            continue
        scored.sort()
        chosen = {}
        for _zed, name in scored[:BASKET]:
            chosen[name] = True
        all_rets = []
        chosen_rets = []
        for name, pack in series.items():
            left = pack["by"].get(monday)
            right = pack["by"].get(nxt)
            if left is None or right is None:
                continue
            ret = futures_notional(left["open"], right["open"], monday, nxt)
            if ret is None:
                continue
            all_rets.append(ret)
            if name in chosen:
                chosen_rets.append(ret)
        if len(chosen_rets) < BASKET:
            continue
        basket = sum(chosen_rets) / float(len(chosen_rets))
        excess = None
        if len(all_rets) >= 2:
            excess = basket - (sum(all_rets) / float(len(all_rets)))
        trades.append({
            "date": monday,
            "ret": basket,
            "excess": excess,
            "regime": regimes.get(monday),
        })
    return trades


def load_futures(root, end, want, emit):
    folder = os.path.join(root, "futures", "day")
    out = {}
    names = sorted(os.listdir(folder))
    for filename in names:
        if not filename.endswith(".csv.gz"):
            continue
        name = filename[:-7]
        if want is not None and name not in want:
            continue
        out[name] = read_future(os.path.join(folder, filename), end)
        if len(out) % 40 == 0:
            emit("futures loaded %d" % len(out))
    emit("futures files %d" % len(out))
    return out


def stock_series(futs, ctx, table):
    series = {}
    for name, bars in futs.items():
        if name in INDEX_FUTURES:
            continue
        if name not in ctx["by_name"]:
            continue
        by = {}
        dates = []
        values = []
        for day in sorted(bars):
            spot = spot_close(ctx, name, day)
            exp = front_expiry(day, table)
            basis = None
            if spot is not None and exp is not None:
                basis = annualised(bars[day]["close"], spot, day, exp)
            by[day] = bars[day]
            if basis is not None:
                dates.append(day)
                values.append(basis)
        series[name] = {"by": by, "dates": dates, "values": values}
    return series


def judge_basis(block):
    reasons = []
    if block["avg"] is None or not block["avg"] > 0:
        reasons.append("avg after costs %s is not above 0" % h._pct(block["avg"]))
    if block["t"] is None or not block["t"] > 3:
        reasons.append("monthly t %s is not above 3" % h._num(block["t"]))
    checks = (
        ("early", "2011-2017"),
        ("late", "2018-2024"),
        ("up", "up"),
        ("down", "down"),
        ("sideways", "sideways"),
    )
    for key, label in checks:
        if block.get(key) is None or not block[key] > 0:
            reasons.append("%s %s is not above 0" % (label, h._pct(block.get(key))))
    return {"result": "PASS" if not reasons else "FAIL", "reasons": reasons}


def finish_block(name, trades, t_key):
    rets = []
    for trade in trades:
        if trade.get("ret") is not None:
            rets.append(trade["ret"])
    block = {
        "name": name,
        "trades": len(rets),
        "avg": h._mean(rets),
        "t": b18.monthly_t(trades, t_key),
    }
    block.update(b18.slice_means(trades, EARLY, LATE))
    block["verdict"] = judge_basis(block)
    return block


def run_variants(ctx, root, start, end, emit, only=None):
    """19a and 19b on one context. Futures are read through end and no further."""
    want = {"NIFTY": True}
    for name in ctx["by_name"]:
        if name not in INDEX_FUTURES:
            want[name] = True
    futs = load_futures(root, end, want, emit)
    days = nifty_days(ctx, end)
    table = expiry_table(days)
    blocks = []
    if only is None or "nifty basis 5d" in only:
        rows = joint_rows(futs.get("NIFTY", {}), ctx, "NIFTY", table)
        emit("nifty basis sessions %d" % len(rows))
        trades = nifty_trades(rows, ctx["regimes"], start, end)
        blocks.append(finish_block("nifty basis 5d", trades, "ret"))
    if only is None or "stock basis z10" in only:
        emit("stock basis series")
        series = stock_series(futs, ctx, table)
        emit("stock futures with a spot %d" % len(series))
        trades = stock_trades(series, days, ctx["regimes"], start, end)
        blocks.append(finish_block("stock basis z10", trades, "excess"))
    return blocks


def run_holdout(root, blocks, emit):
    """One logged load. Only the variants that passed are scored again."""
    from india.research import survivorship
    path = data.bar_path(root, "day", lab.NIFTY)
    _first, last = survivorship.raw_span(path)
    emit("holdout %s to %s" % (data.HOLDOUT_START.isoformat(), last.isoformat()))
    lab.load_symbol(root, lab.NIFTY, end=last, final=True)
    ctx = h.load_context(
        root, start=f.SWING_START, end=last, log=emit, final=False, guard=False)
    names = []
    for block in blocks:
        names.append(block["name"])
    fresh = run_variants(ctx, root, data.HOLDOUT_START, last, emit, names)
    by_name = {}
    for item in fresh:
        by_name[item["name"]] = item
    for block in blocks:
        found = by_name.get(block["name"])
        if found is None:
            continue
        hold = {"trades": found["trades"], "avg": found["avg"], "t": found["t"]}
        hold["verdict"] = b18.judge_holdout(hold)
        block["holdout"] = hold
        emit("holdout %s %s avg %s t %s" % (
            block["name"], hold["verdict"]["result"], h._pct(hold["avg"]), h._num(hold["t"])))
    return last


def finish_catalogue(path, blocks, looked):
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    for block in blocks:
        tier = b18.tier_of(block)
        row = "| %s | 19 | %s |" % (block["name"], b18.note_of(block))
        if tier == "Bucket":
            text = b18.add_bucket_row(text, row)
        else:
            text = b18.add_tier_row(text, tier, row)
    for name in looked:
        text = b18.set_family(text, name)
    if not text.endswith("\n"):
        text += "\n"
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


def _order_and_trade(name, seg, signal_i, entry_i, found, rsi):
    exit_i, px, on_open = found
    entry_px = seg.o[entry_i]
    ret = f.net_return(entry_px, px)
    if ret is None:
        return None, None
    order = {
        "name": name,
        "entry_date": seg.date[entry_i],
        "exit_date": seg.date[exit_i],
        "entry": entry_px,
        "fill": px,
        "at_open": on_open,
        "rsi": rsi,
        "turnover": v.turnover_before(seg, signal_i),
        "seg": seg,
    }
    trade = {"date": seg.date[entry_i], "ret": ret}
    return order, trade


def collect_signals(ctx, start, end, emit):
    orders = {
        "rsi2 < 5": [],
        "m2 regime": [],
        "rel rsi5": [],
        "rel rsi5 stock10": [],
    }
    trades = {
        "rsi2 < 5": [],
        "m2 regime": [],
        "rel rsi5": [],
        "rel rsi5 stock10": [],
    }
    top200 = ctx["top200"]
    regimes = ctx["regimes"]
    specs = []
    for spec in b17.REL_SPECS:
        if spec["name"] in ("rel rsi5", "rel rsi5 stock10"):
            specs.append(spec)
    seen = 0
    for symbol in ctx["loaded"]:
        seen += 1
        if seen % 100 == 0:
            emit("signals scanned %d" % seen)
        name = symbol["name"]
        for seg in symbol["segments"]:
            n = len(seg.date)
            for i in range(n - 1):
                entry_i = i + 1
                entry_day = seg.date[entry_i]
                if entry_day < start or entry_day > end:
                    continue
                if name not in top200.get(seg.date[i], ()):
                    continue
                if f.rsi_fires(seg, i, 5.0, False):
                    found = f.exit_rule(seg, entry_i, f.RSI_LIMIT, f.close_above_sma5)
                    if found is not None:
                        order, trade = _order_and_trade(
                            name, seg, i, entry_i, found, seg.rsi2[i])
                        if order is not None:
                            orders["rsi2 < 5"].append(order)
                            trades["rsi2 < 5"].append(trade)
                            if regimes.get(entry_day) in ("up", "sideways"):
                                orders["m2 regime"].append(order)
                                trades["m2 regime"].append(trade)
                if not symbol.get("sector") or not hasattr(seg, "rel_rsi"):
                    continue
                fired = []
                for spec in specs:
                    if b17.rel_fires(seg, i, spec["rel_max"], spec["stock_max"]):
                        fired.append(spec)
                if not fired:
                    continue
                found = f.exit_rule(seg, entry_i, f.RSI_LIMIT, f.close_above_sma5)
                if found is None:
                    continue
                for spec in fired:
                    order, trade = _order_and_trade(
                        name, seg, i, entry_i, found, seg.rel_rsi[i])
                    if order is None:
                        continue
                    orders[spec["name"]].append(order)
                    trades[spec["name"]].append(trade)
    for name in orders:
        emit("signals %s %d" % (name, len(orders[name])))
    return orders, trades


def slot_equity(orders, calendar, nifty):
    """The 10-slot book. Returns the calendar and the equity, idle cash in NIFTY."""
    orders = v.align_orders(orders, calendar)
    by_entry = {}
    for order in orders:
        by_entry.setdefault(order["entry_date"], []).append(order)
    book = h.Book(h.CAPITAL, park=True)
    if calendar and nifty.get(calendar[0], {}).get("open", 0) > 0:
        book.fund_nifty(nifty[calendar[0]]["open"])
    equity = []
    slot = h.CAPITAL / float(h.SLOTS)
    for day in calendar:
        nopen = nifty[day]["open"]
        nclose = nifty[day]["close"]
        left_today = set()
        for pos_name in list(book.pos):
            pos = book.pos[pos_name]
            if pos.get("exit_date") == day and pos.get("at_open"):
                book.sell(pos_name, pos["shares"], pos["fill"], nopen)
                left_today.add(pos_name)
        room = h.SLOTS - len(book.pos)
        held = set(book.pos)
        for pos_name in left_today:
            held.add(pos_name)
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
        for pos_name in list(book.pos):
            pos = book.pos[pos_name]
            if pos.get("exit_date") == day and not pos.get("at_open"):
                book.sell(pos_name, pos["shares"], pos["fill"], nclose)
        v._exit_broken(book, day, nclose)
        equity.append(book.value(day, nclose, "c"))
    return calendar, equity


def tom_book(ctx, start, end):
    calendar = []
    for day in ctx["calendar"]:
        if day <= end:
            calendar.append(day)
    windows = b17.tom_windows(calendar, ctx["nifty"])
    events = {}
    trades = []
    for entry, exit_day, _entry_px, _exit_px in windows:
        if entry < start or entry > end:
            continue
        names = b17._ranked(ctx, entry, "rsi")
        pairs, kept = b17.priced_legs(names, ctx["by_name"], entry, exit_day)
        ret = b17.basket_return(pairs)
        if ret is None or not kept:
            continue
        events[entry] = (exit_day, kept)
        trades.append({"date": entry, "ret": ret, "regime": ctx["regimes"].get(entry)})
    book = h.Book(h.CAPITAL, park=True)
    if calendar and ctx["nifty"].get(calendar[0], {}).get("open", 0) > 0:
        book.fund_nifty(ctx["nifty"][calendar[0]]["open"])
    equity = []
    holding_until = None
    for day in calendar:
        nclose = ctx["nifty"][day]["close"]
        if holding_until == day:
            for pos_name in list(book.pos):
                pos = book.pos[pos_name]
                loc = ctx["by_name"].get(pos_name, {}).get(day)
                px = pos["last"]
                if loc is not None:
                    px = loc[0].c[loc[1]]
                book.sell(pos_name, pos["shares"], px, nclose)
            holding_until = None
        event = events.get(day)
        if event is not None and holding_until is None:
            exit_day, kept = event
            slot = h.CAPITAL / float(len(kept))
            for pos_name in kept:
                seg, i = ctx["by_name"][pos_name][day]
                px = seg.c[i]
                shares = h.shares_for(slot, px)
                book.buy(pos_name, seg, shares, px, nclose)
            if exit_day == day:
                for pos_name in list(book.pos):
                    pos = book.pos[pos_name]
                    book.sell(pos_name, pos["shares"], pos["last"], nclose)
            else:
                holding_until = exit_day
        equity.append(book.value(day, nclose, "c"))
    return calendar, equity, trades


def mom_book(ctx, end):
    spec = {"name": "mom 12-1 K20 above200", "kind": "mom", "k": 20, "filter": True}
    picks = h._portfolio_picks(
        spec, ctx["pairs"], ctx["top200"], ctx["by_name"], ctx["above"], None)
    calendar = []
    for day in ctx["calendar"]:
        if day <= end:
            calendar.append(day)
    equity = h.simulate_portfolio(
        ctx["pairs"], picks, calendar, ctx["nifty"], ctx["by_name"])
    return calendar, equity


def build_books(ctx, start, end, emit):
    orders, trades = collect_signals(ctx, start, end, emit)
    books = {}
    calendar = []
    for day in ctx["calendar"]:
        if day <= end:
            calendar.append(day)
    for name in ("rsi2 < 5", "m2 regime", "rel rsi5", "rel rsi5 stock10"):
        emit("book %s" % name)
        books[name] = slot_equity(orders[name], calendar, ctx["nifty"])
    emit("book tom rsi20")
    cal, equity, tom_trades = tom_book(ctx, start, end)
    books["tom rsi20"] = (cal, equity)
    trades["tom rsi20"] = tom_trades
    emit("book mom 12-1 K20 above200")
    books["mom 12-1 K20 above200"] = mom_book(ctx, end)
    return books, trades


def month_returns(dates, equity, first=2005, last=2024):
    last_i = {}
    for i, day in enumerate(dates):
        last_i[(day.year, day.month)] = i
    prev = float(h.CAPITAL)
    out = []
    for key in sorted(last_i):
        if key[0] < first or key[0] > last:
            val = float(equity[last_i[key]])
            if val > 0:
                prev = val
            continue
        val = float(equity[last_i[key]])
        if prev > 0 and val > 0:
            out.append((key[0], key[1], (val / prev - 1.0) * 100.0))
        if val > 0:
            prev = val
    return out


def month_map(rows):
    out = {}
    for year, month, ret in rows:
        out[(year, month)] = ret
    return out


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


def correlation_matrix(named):
    out = {}
    for i, (left, lmap) in enumerate(named):
        for right, rmap in named[i + 1:]:
            keys = sorted(set(lmap) & set(rmap))
            xs = []
            ys = []
            for key in keys:
                xs.append(lmap[key])
                ys.append(rmap[key])
            value = pearson(xs, ys)
            out[(left, right)] = value
            out[(right, left)] = value
    return out


def least_correlated(names, matrix):
    """Lowest average pairwise correlation. A tie breaks on the sorted names."""
    best = None
    best_avg = None
    for trio in itertools.combinations(names, 3):
        pairs = ((trio[0], trio[1]), (trio[0], trio[2]), (trio[1], trio[2]))
        vals = []
        missing = False
        for left, right in pairs:
            value = matrix.get((left, right))
            if value is None:
                missing = True
                break
            vals.append(value)
        if missing:
            continue
        avg = sum(vals) / 3.0
        key = (avg, tuple(sorted(trio)))
        if best is None or key < best:
            best = key
            best_avg = avg
    if best is None:
        return None, None
    return best[1], best_avg


def blend_rows(maps):
    keys = None
    for item in maps:
        if keys is None:
            keys = set(item)
        else:
            keys = keys & set(item)
    if not keys:
        return []
    rows = []
    for key in sorted(keys):
        total = 0.0
        for item in maps:
            total += item[key]
        rows.append((key[0], key[1], total / float(len(maps))))
    return rows


def curve_stats(rows):
    if not rows:
        return None
    equity = 1.0
    peak = 1.0
    worst_dd = 0.0
    by_year = {}
    for year, _month, ret in rows:
        equity *= (1.0 + ret / 100.0)
        if equity > peak:
            peak = equity
        if peak > 0:
            dd = (equity / peak - 1.0) * 100.0
            if dd < worst_dd:
                worst_dd = dd
        by_year.setdefault(year, []).append(ret)
    n = len(rows)
    if equity <= 0:
        cagr = None
    else:
        cagr = (equity ** (12.0 / float(n)) - 1.0) * 100.0
    worst_year = None
    worst_ret = None
    positive = 0
    years = 0
    for year in sorted(by_year):
        year_eq = 1.0
        for ret in by_year[year]:
            year_eq *= (1.0 + ret / 100.0)
        yr = (year_eq - 1.0) * 100.0
        years += 1
        if yr > 0:
            positive += 1
        if worst_ret is None or yr < worst_ret:
            worst_ret = yr
            worst_year = year
    return {
        "cagr": cagr,
        "dd": worst_dd,
        "worst_year": worst_year,
        "worst": worst_ret,
        "positive": positive,
        "years": years,
        "n": n,
    }


def matrix_lines(names, matrix):
    head = ["correlation"]
    head.extend(names)
    lines = [" | ".join(head)]
    for left in names:
        cells = [left]
        for right in names:
            if left == right:
                cells.append("1.00")
                continue
            value = matrix.get((left, right))
            if value is None:
                cells.append("n/a")
            else:
                cells.append("%+.2f" % value)
        lines.append(" | ".join(cells))
    return lines


def stats_line(name, stats):
    if stats is None:
        return "%s | n/a | n/a | n/a | n/a" % name
    return "%s | %s | %s | %s %s | %d/%d" % (
        name,
        h._pct(stats["cagr"]),
        h._pct(stats["dd"]),
        stats["worst_year"],
        h._pct(stats["worst"]),
        stats["positive"],
        stats["years"],
    )


def run_blend(ctx, emit):
    books, _trades = build_books(ctx, f.SWING_START, h.END, emit)
    named = []
    stats = []
    for name in forward.STRATEGIES:
        dates, equity = books[name]
        rows = month_returns(dates, equity)
        named.append((name, month_map(rows)))
        item = curve_stats(rows)
        stats.append((name, item))
        emit("months %s %d" % (name, 0 if item is None else item["n"]))
    matrix = correlation_matrix(named)
    trio, avg = least_correlated(forward.STRATEGIES, matrix)
    maps = {}
    for name, mapped in named:
        maps[name] = mapped
    all_rows = blend_rows([maps[name] for name in forward.STRATEGIES])
    all_stats = curve_stats(all_rows)
    trio_stats = None
    if trio:
        trio_rows = blend_rows([maps[name] for name in trio])
        trio_stats = curve_stats(trio_rows)
    lines = []
    lines.extend(matrix_lines(list(forward.STRATEGIES), matrix))
    lines.append("")
    lines.append("book | CAGR | max DD | worst year | positive years")
    for name, item in stats:
        lines.append(stats_line(name, item))
    lines.append(stats_line("equal weight of 6", all_stats))
    if trio:
        label = "equal weight of 3 (%s)" % ", ".join(trio)
        lines.append(stats_line(label, trio_stats))
        lines.append("least-3 average correlation %s" % ("%+.3f" % avg))
    else:
        lines.append("equal weight of 3 | n/a | no trio had three correlations")
    return lines, trio


def daily_after(dates, equity, cutoff):
    out = []
    for i in range(1, len(dates)):
        if dates[i] <= cutoff:
            continue
        prev = equity[i - 1]
        if prev > 0 and equity[i] > 0:
            out.append((dates[i], (equity[i] / prev - 1.0) * 100.0))
    return out


def _count_line(name, values):
    return "%s | trades %s | avg %s | t %s" % (
        name, format(len(values), ",d"), h._pct(h._mean(values)), h._num(h.t_stat(values)))


def forward_lines(root, dates, names, industries, emit):
    """Score the frozen rules on the sessions after the cutoff. No logged load."""
    end = max(dates)
    emit("forward load through %s" % end.isoformat())
    ctx = b17.prepare_context(root, end, emit, False, guard=False)
    mapped = b17.attach_relative(ctx, b16.load_industries(industries))
    emit("forward sector map %d" % mapped)
    books, trades = build_books(ctx, f.SWING_START, end, emit)
    lines = []
    daily = {}
    for name in forward.STRATEGIES:
        cal, equity = books[name]
        points = daily_after(cal, equity, forward.CUTOFF)
        mapped_day = {}
        for day, ret in points:
            mapped_day[day] = ret
        daily[name] = mapped_day
        if name == "mom 12-1 K20 above200":
            values = []
            for _day, ret in points:
                values.append(ret)
        else:
            values = []
            for trade in trades.get(name, []):
                if trade["date"] > forward.CUTOFF and trade.get("ret") is not None:
                    values.append(trade["ret"])
        lines.append(_count_line(name, values))
    if names:
        blend = []
        for day in dates:
            vals = []
            ready = True
            for name in names:
                if name not in daily or day not in daily[name]:
                    ready = False
                    break
                vals.append(daily[name][day])
            if ready:
                blend.append(sum(vals) / float(len(vals)))
        lines.append(_count_line("Forward book v1 (%s)" % ", ".join(names), blend))
    else:
        lines.append("Forward book v1 | constituents pending | trades 0 | avg n/a | t n/a")
    return lines


def leg_line(block):
    return "%s | %s | %s | %s | %s | %s | %s | %s | %s | %s" % (
        block["name"],
        format(block["trades"], ",d"),
        h._pct(block["avg"]),
        h._num(block["t"]),
        h._pct(block.get("early")),
        h._pct(block.get("late")),
        h._pct(block.get("up")),
        h._pct(block.get("down")),
        h._pct(block.get("sideways")),
        block["verdict"]["result"],
    )


def result_rows(blocks, last):
    today = datetime.date.today().isoformat()
    rows = []
    for block in blocks:
        rows.append("| 19 | %s | %s. | attempt 19, rules fixed before the run | 2011-01-01 to 2024-12-31 | %s | %s | %s | %s |" % (
            today,
            block["name"],
            format(block["trades"], ",d"),
            h._pct(block["avg"]),
            h._num(block["t"]),
            block["verdict"]["result"],
        ))
        hold = block.get("holdout")
        if not hold:
            continue
        window = "2025-01-01 to %s" % (last.isoformat() if last is not None else "the last NIFTY date")
        rows.append("| 19 | %s | holdout %s. | same rule, one logged load | %s | %s | %s | %s | %s |" % (
            today,
            block["name"],
            window,
            format(hold["trades"], ",d"),
            h._pct(hold["avg"]),
            h._num(hold["t"]),
            hold["verdict"]["result"],
        ))
    return rows


def main(argv=None, log=None):
    import argparse
    parser = argparse.ArgumentParser(description="Step 25. Nothing is placed.")
    parser.add_argument("--root", default=os.path.join("data", "kite"))
    parser.add_argument("--experiments", default=h.EXPERIMENTS)
    parser.add_argument("--catalogue", default=h.CATALOGUE)
    parser.add_argument("--industries", default=os.path.join(_ROOT, "india", "universe", "nifty500.csv"))
    parser.add_argument("--forward", default=forward.FORWARD_PATH)
    args = parser.parse_args(argv)
    emit = log or (lambda line: print(line, flush=True))

    write_rules(args.experiments, args.catalogue)
    emit("rules for attempt 19 written to %s before the run" % args.experiments)
    emit("Forward book v1 written before the blend. Constituents stay pending until the study.")
    emit("expiry rule: last Thursday through 2025-08, last Tuesday from 2025-09, stated before the run")

    option_lines = long_dated_lines(args.root)
    for line in option_lines:
        emit(line)

    emit("loading stocks through %s" % h.END.isoformat())
    ctx = b17.prepare_context(args.root, h.END, emit, False)
    mapped = b17.attach_relative(ctx, b16.load_industries(args.industries))
    emit("sector map %d" % mapped)

    blend_lines, trio = run_blend(ctx, emit)
    if trio:
        fill_forward_book(args.experiments, list(trio), ["Blend results.", ""] + blend_lines)
        emit("constituents frozen: %s" % ", ".join(trio))
    else:
        emit("no trio could be frozen")
    for line in blend_lines:
        emit(line)

    emit("forward record")
    forward.main([
        "--root", args.root,
        "--experiments", args.experiments,
        "--forward", args.forward,
        "--industries", args.industries,
    ], log=emit)

    emit("attempt 19, research window, final false")
    blocks = run_variants(ctx, args.root, BASIS_START, h.END, emit)
    passed = []
    for block in blocks:
        if block["verdict"]["result"] == "PASS":
            passed.append(block)
    last = None
    looked = []
    if passed:
        last = run_holdout(args.root, passed, emit)
        looked = [FAMILY]
    else:
        emit("no holdout was run")

    finish_catalogue(args.catalogue, blocks, looked)

    lines = ["Results.", ""]
    lines.extend(option_lines)
    lines.append("")
    lines.append("19 futures basis.")
    lines.append("name | n | avg | monthly t | 2011-2017 | 2018-2024 | up | down | sideways | result")
    for block in blocks:
        lines.append(leg_line(block))
        for reason in block["verdict"]["reasons"]:
            lines.append("  %s" % reason)
        hold = block.get("holdout")
        if hold:
            lines.append("  holdout %s to %s %s avg %s t %s" % (
                data.HOLDOUT_START.isoformat(),
                last.isoformat() if last is not None else "n/a",
                hold["verdict"]["result"],
                h._pct(hold["avg"]),
                h._num(hold["t"]),
            ))
    if not looked:
        lines.append("")
        lines.append("No variant passed in sample, so no holdout was run.")
    lines.append("")
    lines.append(b18.bucket_line(args.catalogue))
    section = rules_text().rstrip() + "\n\n" + "\n".join(lines)
    f.install_attempt(args.experiments, 19, section, result_rows(blocks, last))

    emit("")
    emit("19 futures basis")
    emit("name | n | avg | monthly t | 2011-2017 | 2018-2024 | up | down | sideways | result")
    for block in blocks:
        emit(leg_line(block))
        for reason in block["verdict"]["reasons"]:
            emit("  %s" % reason)
        hold = block.get("holdout")
        if hold:
            emit("  holdout %s avg %s t %s" % (
                hold["verdict"]["result"], h._pct(hold["avg"]), h._num(hold["t"])))
    emit("")
    if not looked:
        emit("no variant passed in sample, so no holdout was run")
    emit(b18.bucket_line(args.catalogue))


if __name__ == "__main__":
    main()
