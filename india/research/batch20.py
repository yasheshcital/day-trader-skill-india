#!/usr/bin/env python3
"""Attempt 20. Event days. Rules are written before any backtest.

Research window only until a variant passes. One logged load in that case.
Event days are a new family. Nothing is ordered.
"""

import bisect
import csv
import datetime
import os
import random
import statistics
import sys
from decimal import Decimal

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from india import costs
from india import nse_market
from india.research import batch18
from india.research import data
from india.research import events
from india.research import follow
from india.research import harness
from india.research import regime
from india.research import signal_lab as lab
from india.research import survivorship
from india.research import trend_day_study as trend

EXPERIMENTS = os.path.join("india", "EXPERIMENTS.md")
STRATEGIES = os.path.join("india", "research", "STRATEGIES.md")
START = trend.START
END = trend.END
BANK = "NIFTY BANK"
BANK_LOT = 15  # check your broker
NIFTY_LOT = harness.NIFTY_LOT
RUNS = 100
VIX_WINDOW = 250
# 250 * 0.70 = 175. Index 175 is the 176th smallest, the first of the top 75.
VIX_CUTOFF = 175
LAST75 = 13 * 60 + 55
LAST75_OFFSET = (LAST75 - trend.FIRST_END) // 5
FAMILY = "event days"

def rules_text(stamp):
    return """## Attempt 20

Rules fixed on %s, before the run.

Family: event days. This is a new family. Its holdout stays unused until a variant passes in sample.

Window: 2015-01-01 through 2024-12-31. Prices are the existing 5-minute and daily files. The research window keeps final false. No new order is sent.

Calendar. data/nse/events.csv has columns date, kind, symbol, source. Symbol is blank on a market-wide row. Kinds are results, rbi, budget, expiry-monthly, expiry-weekly, and rebalance.

Expiry days come from the continuous futures files in data/kite/futures when a file has an expiry column. Those files are daily continuous series and the column is absent, so the weekday rule supplies the dates. Weekly expiry is Thursday through 2025-08-31 and Tuesday after that date. Monthly expiry is the last Thursday through 2025-08-31 and the last Tuesday after that date. When the scheduled day is a holiday or a weekend, the expiry is the previous trading day. A date that is both is monthly only. 20a scores NIFTY and BANKNIFTY on those NIFTY expiry dates, monthly and weekly together.

Results day. The announcement time is the financial-results broadcast. From 2025, where that feed stops, an NSE announcement whose text says financial results is used, and a broadcast already mapped to that session is kept. A board-meeting intimation is archived and is not a results day. The results day is the first NIFTY session whose 09:15 is strictly after the announcement. A stamp with no clock time is treated as 15:30 on that date, so the results day is the next session. The clock time is not invented.

RBI days are the MPC resolution dates hard-coded in events.py, with the rbi.org.in source on the row. Budget days are the Union Budget speech dates, source indiabudget.gov.in. When the published date is not a NIFTY session, the event date is the next NIFTY session if that session falls within 4 calendar days, and otherwise the date is left out. Rebalance is the last NIFTY session of March and of September, the semi-annual Nifty 50 reconstitution.

20a, expiry day, index. Four variants: nifty expiry oc, nifty expiry 75m, bank expiry oc, bank expiry 75m. The book is long one lot. NIFTY lot 75. BANKNIFTY lot 15, check your broker. Costs are the attempt 16 futures schedule, same-day, so the rollover count is 0. Open to close is the open of the bar ending 09:20 (the 09:15 price) to the close of the bar ending 15:10. The usable session ends at 15:10, so the close is that bar and not the 15:30 print. The last 75 minutes are the close of the bar ending 13:55 to the close of the bar ending 15:10. 15:10 minus 75 minutes is 13:55. Both bars sit inside a usable session. The return is the after-cost futures return in percent. Excess is that return minus the mean after-cost return of the same index on same-calendar-year days that are not in the expiry set. A year with no such day leaves the excess empty. The trade still counts in the average.

20a pass. Each variant on its own. No family gate. The average of the expiry day's own after-cost return is above 0. The monthly t is the one-sample t of the monthly means of the excess, and it is above 3. The own average is above 0 in 2015-2019, in 2020-2024, and in up, down, and sideways. An empty bucket fails. The regime is the NIFTY daily regime of the session.

20b, results day, stocks. Two variants: results gap cont and results gap fade. The universe is the attempt 12 universe: the top 200 names by average close times volume over the previous 20 sessions, and the 20 sessions must sit in one segment. Large caps are the top 100 of that ranking. The gap is the open of the bar ending 09:20 divided by the previous session's daily close in the same segment, minus 1. A gap of exactly 0 is not a trade. A gap that does not clear one tick is not a trade either, because the stop would not sit beyond the slipped fill. Continuation trades in the sign of the gap. Fade trades the other way. Entry is that open. The stop is the previous close, so R is the distance from the slipped entry to that close. There is no target. Exit is the 15:10 close unless a later bar stops it out. The entry bar is not scanned. A later bar that opens through the stop fills at that open. Otherwise a touch fills at the stop. One tick of slippage, from nse_market.tick_for, on the entry and on the exit. Costs are the intraday round trip. R before charges is after the tick. R after is after the tick and the charges. Size is Rs 2,000 of risk, capped at Rs 5,00,000, in whole shares.

20b pass. The attempt 12 mark, with one change stated here: there are two variants, so the family clause is at least 1 of the 2 with t above 2. Every other clause is unchanged. Average R after costs and slippage at least +0.10. At least 300 trades on at least 100 distinct days. t above 3. Average R after costs above 0 in 2015-2019, in 2020-2024, in up, down, and sideways, and in large caps. A boundary stated with at least still passes. An empty bucket fails. The t is not a random bar, because a gap trade exists only at the open. The baseline is the same symbol on a random usable non-results day in the same calendar year: enter at that day's open, apply the same continuation or fade rule to that day's own gap, stop at that day's previous close, exit at 15:10. 100 runs. The seed is 20261106 plus the variant index times 1000, plus the run index. Excess R is R after costs minus the mean R of those random days. The monthly t is the one-sample t of the monthly means of that excess. A year with no eligible non-results day leaves that trade out of the t. It still counts in the average R.

20c, macro days. The attempt 8 trend-day opening-range breakout, both universes. Universe A is today's NIFTY 50 list and has survivorship bias. Universe B is the point-in-time top 100 by the previous 20 sessions of turnover. A trade is taken only when the session is an RBI day or a Budget day. The all-days book is printed beside it and is not a variant. It cannot pass and it is not sent to the holdout. Names: macro orb A and macro orb B. The pass mark is attempt 8's four rules. At least 100 trades. Average R after costs at least +0.10. The first half and the second half of the sessions both above 0 after costs. Those halves are the halves of the full 2015-2024 NIFTY session calendar, the same split as attempt 8, not the halves of the macro dates. After-cost average R above 0 on at least 60 percent of the stocks that traded.

20d, on/off switch. The same attempt 8 rule on both universes, taken only on a day that is on before 09:15. Names: switch orb A and switch orb B. The India VIX known before 09:15 is the previous session's close. It is in its top 30 percent of the last 250 closes when those 250 closes, ending at yesterday and including yesterday, put yesterday at or above the 176th smallest. That cutoff is index 175 of the sorted window. A tie at the cutoff is on. Fewer than 250 prior closes leaves the VIX clause off. The day is also on when events.csv has any row that day, including a stock-specific results row. Either condition is enough. The pass mark is the same four attempt 8 rules, and the halves are again the full 2015-2024 calendar.

Holdout, only for a variant that passes. One load, logged, of the NIFTY 50 daily file, from 2025-01-01 through the last NIFTY daily date. Other reads in that block do not log. If nothing passes, the holdout is not opened. Holdout pass for a 20a variant is its own average above 0 and its excess t above 2. The in-sample bar of t above 3, and the half and regime clauses, are not applied again. Holdout pass for 20b is average R after costs above 0 and the excess t above 2. The +0.10 bar and the trade-count clauses are not applied again. Holdout pass for 20c and 20d is average R after costs above 0 and the monthly t of that R above 2. The 100-trade clause and the 60 percent stock clause are not applied on the short holdout.

If no attempt 20 or 21 variant passes in-sample AND its holdout, intraday is Closed for good.
""" % stamp.isoformat()


def write_rules(path, stamp):
    follow.install_attempt(path, 20, rules_text(stamp), [])


def ensure_family(path):
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    if "| event days |" in text:
        return
    needle = "| futures basis | yes |"
    if needle not in text:
        return
    text = text.replace(needle, needle + "\n| event days | no |", 1)
    if not text.endswith("\n"):
        text += "\n"
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


def vix_top30(values):
    """True when the last close is in the top 30 percent of these 250 closes."""
    if len(values) < VIX_WINDOW:
        return False
    window = values[-VIX_WINDOW:]
    cutoff = sorted(window)[VIX_CUTOFF]
    return window[-1] >= cutoff


def switch_on(vix_values, event_today):
    """On when yesterday's VIX is in its top 30 percent, or the day is an event."""
    if event_today:
        return True
    return vix_top30(vix_values)


def filter_signals(signals, on_days):
    """Trend-day signals kept only when the session is on."""
    kept = {}
    for day, signal in signals.items():
        if day in on_days:
            kept[day] = signal
    return kept


def _mean(values):
    if not values:
        return None
    return statistics.mean(values)


def load_vix(path):
    dates = []
    closes = []
    if not os.path.isfile(path):
        return dates, closes
    with open(path, encoding="utf-8", newline="") as fh:
        for cell in csv.DictReader(fh):
            text = (cell.get("close") or "").strip()
            if text == "":
                continue
            try:
                close = float(text)
            except ValueError:
                continue
            dates.append(datetime.date.fromisoformat(cell["date"]))
            closes.append(close)
    return dates, closes


def vix_into(dates, closes, day):
    """Closes ending at the last date strictly before `day`."""
    i = bisect.bisect_left(dates, day) - 1
    if i < 0:
        return []
    start = 0 if i + 1 <= VIX_WINDOW else i + 1 - VIX_WINDOW
    return closes[start:i + 1]


def _futures_book(sessions, lot, start, end):
    rows = []
    for day in sorted(sessions):
        if day < start or day > end:
            continue
        session = sessions[day]
        origin = trend.locate(session)
        if origin is None:
            continue
        opened = session["open"][origin]
        last = session["close"][origin + trend.FLAT_OFFSET]
        mid = session["close"][origin + LAST75_OFFSET]
        rows.append({
            "date": day,
            "oc": batch18.futures_return(opened, last, day, day, lot),
            "m75": batch18.futures_return(mid, last, day, day, lot),
        })
    return rows


def _expiry_trades(rows, expiry, regimes, key):
    pooled = {}
    for row in rows:
        if row["date"] in expiry:
            continue
        value = row[key]
        if value is None:
            continue
        pooled.setdefault(row["date"].year, []).append(value)
    means = {}
    for year, values in pooled.items():
        means[year] = statistics.mean(values)
    trades = []
    for row in rows:
        if row["date"] not in expiry:
            continue
        own = row[key]
        if own is None:
            continue
        base = means.get(row["date"].year)
        trades.append({
            "date": row["date"],
            "own": own,
            "excess": None if base is None else own - base,
            "regime": regimes.get(row["date"]),
        })
    return trades


def _bucket(trades, pred, key):
    values = []
    for trade in trades:
        if pred(trade):
            value = trade.get(key)
            if value is not None:
                values.append(value)
    return _mean(values)


def judge_expiry(trades):
    """Own average above 0, excess t above 3, both halves, three regimes."""
    reasons = []
    avg = _bucket(trades, lambda _t: True, "own")
    if avg is None or not avg > 0:
        reasons.append("own avg %s is not above 0" % harness._pct(avg))
    tee = batch18.monthly_t(trades, "excess")
    if tee is None or not tee > 3:
        reasons.append("excess t %s is not above 3" % harness._num(tee))
    checks = (
        ("2015-2019", lambda t: 2015 <= t["date"].year <= 2019),
        ("2020-2024", lambda t: 2020 <= t["date"].year <= 2024),
        ("up", lambda t: t.get("regime") == "up"),
        ("down", lambda t: t.get("regime") == "down"),
        ("sideways", lambda t: t.get("regime") == "sideways"),
    )
    buckets = {}
    for label, pred in checks:
        value = _bucket(trades, pred, "own")
        buckets[label] = value
        if value is None or not value > 0:
            reasons.append("%s %s is not above 0" % (label, harness._pct(value)))
    return {
        "result": "PASS" if not reasons else "FAIL",
        "reasons": reasons,
        "avg": avg,
        "t": tee,
        "buckets": buckets,
        "excess": _bucket(trades, lambda t: t.get("excess") is not None, "excess"),
    }


def judge_holdout_pair(avg, tee):
    reasons = []
    if avg is None or not avg > 0:
        reasons.append("holdout avg %s is not above 0" % harness._pct(avg))
    if tee is None or not tee > 2:
        reasons.append("holdout t %s is not above 2" % harness._num(tee))
    return {"result": "PASS" if not reasons else "FAIL", "reasons": reasons}


def gap_trade(session, prev_close, side, symbol):
    """Open entry, previous-close stop, 15:10 exit. One tick each side."""
    origin = trend.locate(session)
    if origin is None or not prev_close > 0:
        return None
    raw = session["open"][origin]
    if not (raw > prev_close or raw < prev_close):
        return None
    tick = nse_market.tick_for(raw, symbol)
    if not tick > 0:
        return None
    long = side == "buy"
    fill_entry = raw + tick if long else raw - tick
    stop = prev_close
    risk = (fill_entry - stop) if long else (stop - fill_entry)
    # A gap that does not clear one tick leaves the stop on the wrong side,
    # or a dust-sized R. That day is not a trade.
    if not risk > tick or not fill_entry > 0:
        return None
    last = origin + trend.FLAT_OFFSET
    exit_px = session["close"][last]
    for i in range(origin + 1, last + 1):
        bar_open = session["open"][i]
        if long and bar_open <= stop:
            exit_px = bar_open
            break
        if (not long) and bar_open >= stop:
            exit_px = bar_open
            break
        if long and session["low"][i] <= stop:
            exit_px = stop
            break
        if (not long) and session["high"][i] >= stop:
            exit_px = stop
            break
    exit_tick = nse_market.tick_for(exit_px, symbol)
    if not exit_tick > 0:
        exit_tick = tick
    fill_exit = exit_px - exit_tick if long else exit_px + exit_tick
    if not fill_exit > 0:
        return None
    shares = trend.whole_shares(fill_entry, stop, trend.RISK_RS, trend.CAPITAL)
    if shares <= 0:
        return None
    if long:
        gross = (Decimal(repr(fill_exit)) - Decimal(repr(fill_entry))) * shares
        cost = costs.round_trip(fill_entry, fill_exit, shares)
    else:
        gross = (Decimal(repr(fill_entry)) - Decimal(repr(fill_exit))) * shares
        cost = costs.round_trip(fill_exit, fill_entry, shares)
    denom = Decimal(repr(risk)) * shares
    if denom == 0:
        return None
    return {
        "r_before": float(gross / denom),
        "r_after": float((gross - cost) / denom),
    }


def _prev_closes(series):
    found = {}
    for segment in series.segments:
        last = None
        for item in segment:
            if last is not None:
                found[item["date"]] = last
            last = item["close"]
    return found


def _apply_excess(trades, pools, seed):
    trades.sort(key=lambda item: (item["date"], item["symbol"]))
    picks = []
    for _trade in trades:
        picks.append([])
    for run_i in range(RUNS):
        rng = random.Random(seed + run_i)
        for i, trade in enumerate(trades):
            window = pools.get((trade["symbol"], trade["date"].year))
            if not window:
                continue
            picks[i].append(window[rng.randrange(len(window))])
    for trade, chosen in zip(trades, picks):
        base = _mean(chosen)
        trade["excess"] = None if base is None else trade["r_after"] - base


def _pack_results(trades):
    return {
        "trades": len(trades),
        "days": len(set(trade["date"] for trade in trades)),
        "avg_after": _mean([trade["r_after"] for trade in trades]),
        "t": batch18.monthly_t(trades, "excess"),
        "early": _bucket(trades, lambda t: 2015 <= t["date"].year <= 2019, "r_after"),
        "late": _bucket(trades, lambda t: 2020 <= t["date"].year <= 2024, "r_after"),
        "up": _bucket(trades, lambda t: t.get("regime") == "up", "r_after"),
        "down": _bucket(trades, lambda t: t.get("regime") == "down", "r_after"),
        "sideways": _bucket(trades, lambda t: t.get("regime") == "sideways", "r_after"),
        "large": _bucket(trades, lambda t: t.get("large"), "r_after"),
    }


def judge_results(block, family):
    """Attempt 12's clauses. The family bar is 1 of 2, not 2 of 3."""
    reasons = []
    if block["avg_after"] is None or not block["avg_after"] >= 0.10:
        reasons.append("avg R after costs %s is below +0.10" % harness._r(block["avg_after"]))
    if block["trades"] < 300:
        reasons.append("trades %d is below 300" % block["trades"])
    if block["days"] < 100:
        reasons.append("days %d is below 100" % block["days"])
    if block["t"] is None or not block["t"] > 3:
        reasons.append("t vs non-results days %s is not above 3" % harness._num(block["t"]))
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
            reasons.append("%s %s is not above 0" % (label, harness._r(block[key])))
    strong = 0
    for item in family:
        if item.get("t") is not None and item["t"] > 2:
            strong += 1
    if strong < 1:
        reasons.append("family variants with t above 2: %d of %d, need 1" % (strong, len(family)))
    return {"result": "PASS" if not reasons else "FAIL", "reasons": reasons}


def _load_map(root, symbol, start, end, guard):
    series = data.load_arrays(
        root, symbol, "5minute", start=start, end=end, guard=guard)
    return trend.usable_map(series)


def _regimes(root, end, guard):
    series = data.load_arrays(root, trend.NIFTY, "day", end=end, guard=guard)
    points = []
    for segment in series.segments:
        for item in segment:
            points.append((item["date"], item["close"]))
    return regime.by_date(points)


def score_expiry(root, event_rows, start, end, regimes, guard, emit):
    expiry = set()
    for row in event_rows:
        if row["kind"] in ("expiry-monthly", "expiry-weekly"):
            if start <= row["date"] <= end:
                expiry.add(row["date"])
    emit("expiry days in the window: %d" % len(expiry))
    blocks = []
    specs = (
        ("nifty expiry oc", trend.NIFTY, NIFTY_LOT, "oc"),
        ("nifty expiry 75m", trend.NIFTY, NIFTY_LOT, "m75"),
        ("bank expiry oc", BANK, BANK_LOT, "oc"),
        ("bank expiry 75m", BANK, BANK_LOT, "m75"),
    )
    cached = {}
    for name, symbol, lot, key in specs:
        if symbol not in cached:
            try:
                cached[symbol] = _load_map(root, symbol, start, end, guard)
            except data.DataError:
                cached[symbol] = None
        sessions = cached[symbol]
        if not sessions:
            trades = []
        else:
            rows = _futures_book(sessions, lot, start, end)
            trades = _expiry_trades(rows, expiry, regimes, key)
        verdict = judge_expiry(trades)
        blocks.append({
            "name": name,
            "kind": "expiry",
            "trades_n": len(trades),
            "avg": verdict["avg"],
            "t": verdict["t"],
            "excess": verdict["excess"],
            "buckets": verdict["buckets"],
            "verdict": {"result": verdict["result"], "reasons": verdict["reasons"]},
            "rows": trades,
        })
        emit("%s %s n %d own %s t %s" % (
            name, verdict["result"], len(trades),
            harness._pct(verdict["avg"]), harness._num(verdict["t"])))
    return blocks


def score_results(root, event_rows, start, end, regimes, books, guard, emit):
    by_symbol = {}
    for row in event_rows:
        if row["kind"] != "results":
            continue
        if row["date"] < start or row["date"] > end or not row["symbol"]:
            continue
        by_symbol.setdefault(row["symbol"], set()).add(row["date"])
    days = []
    seen = set()
    for dates in by_symbol.values():
        for day in dates:
            if day not in seen:
                seen.add(day)
                days.append(day)
    days.sort()
    top200, top100 = harness.rank_universe(books, days)
    emit("results symbols %d, results days %d" % (len(by_symbol), len(days)))
    grouped = [[], []]
    pools = [{}, {}]
    done = 0
    symbols = sorted(by_symbol)
    for symbol in symbols:
        done += 1
        if done % 25 == 0 or done == len(symbols):
            emit("results scored %d / %d" % (done, len(symbols)))
        result_days = by_symbol[symbol]
        try:
            daily = data.load_arrays(root, symbol, "day", end=end, guard=guard)
            sessions = _load_map(root, symbol, start, end, guard)
        except data.DataError:
            continue
        prev = _prev_closes(daily)
        for day in sorted(sessions):
            if day < start or day > end or day not in prev:
                continue
            raw = sessions[day]["open"]
            origin = trend.locate(sessions[day])
            if origin is None:
                continue
            opened = raw[origin]
            previous = prev[day]
            if not (opened > previous or opened < previous):
                continue
            cont_side = "buy" if opened > previous else "sell"
            fade_side = "sell" if cont_side == "buy" else "buy"
            made = (
                gap_trade(sessions[day], previous, cont_side, symbol),
                gap_trade(sessions[day], previous, fade_side, symbol),
            )
            is_result = day in result_days
            for index, trade in enumerate(made):
                if trade is None:
                    continue
                if is_result:
                    if symbol not in top200.get(day, ()):
                        continue
                    trade["date"] = day
                    trade["symbol"] = symbol
                    trade["regime"] = regimes.get(day)
                    trade["large"] = symbol in top100.get(day, ())
                    grouped[index].append(trade)
                else:
                    pools[index].setdefault((symbol, day.year), []).append(trade["r_after"])
    packed = []
    for index, name in enumerate(("results gap cont", "results gap fade")):
        _apply_excess(grouped[index], pools[index], harness.SEED + index * 1000)
        packed.append(_pack_results(grouped[index]))
        packed[-1]["name"] = name
        packed[-1]["rows"] = grouped[index]
    family = packed
    blocks = []
    for item in packed:
        verdict = judge_results(item, family)
        blocks.append({
            "name": item["name"],
            "kind": "results",
            "trades_n": item["trades"],
            "days": item["days"],
            "avg": item["avg_after"],
            "t": item["t"],
            "buckets": {
                "2015-2019": item["early"],
                "2020-2024": item["late"],
                "up": item["up"],
                "down": item["down"],
                "sideways": item["sideways"],
                "large": item["large"],
            },
            "verdict": verdict,
            "rows": item["rows"],
        })
        emit("%s %s n %d days %d avg %s t %s" % (
            item["name"], verdict["result"], item["trades"], item["days"],
            harness._r(item["avg_after"]), harness._num(item["t"])))
    return blocks


def _stock_share(trades):
    by_symbol = {}
    for trade in trades:
        by_symbol.setdefault(trade["symbol"], []).append(trade["r_after"])
    if not by_symbol:
        return 0, 0
    winners = 0
    for values in by_symbol.values():
        avg = _mean(values)
        if avg is not None and avg > 0:
            winners += 1
    return winners, len(by_symbol)


def _books(root, end, guard):
    books = []
    for symbol in data.symbols_in(root):
        if symbol.startswith("NIFTY"):
            continue
        try:
            series = data.load_arrays(root, symbol, "day", end=end, guard=guard)
        except data.DataError:
            continue
        books.append((symbol, trend.book_from_series(series)))
    return books


def score_orb(root, start, end, guard, emit, books=None):
    """One pass of the attempt 8 rule. Returns calendar, signals, both trade lists."""
    regimes = _regimes(root, end, guard)
    nifty_sessions = _load_map(root, trend.NIFTY, start, end, guard)
    calendar, signals = trend._signals(nifty_sessions, regimes, start, end)
    emit("trend days: %d" % len(signals))
    if books is None:
        books = _books(root, end, guard)
    liquid_by_day = {}
    for day in signals:
        liquid_by_day[day] = set(trend.liquid_names(day, books, trend.LIQUID))
    current = set(trend.NIFTY50)
    wanted = set(current)
    for names in liquid_by_day.values():
        wanted.update(names)
    symbols = []
    for symbol, _book in books:
        if symbol in wanted:
            symbols.append(symbol)
    current_trades = []
    liquid_trades = []
    done = 0
    for symbol in symbols:
        done += 1
        if done % 25 == 0 or done == len(symbols):
            emit("orb scored %d / %d" % (done, len(symbols)))
        try:
            sessions = _load_map(root, symbol, start, end, guard)
        except data.DataError:
            continue
        part_current, part_liquid = trend.score_symbol(
            symbol, sessions, signals, current, liquid_by_day, regimes,
            trend.RISK_RS, trend.CAPITAL)
        current_trades.extend(part_current)
        liquid_trades.extend(part_liquid)
    return calendar, signals, regimes, books, current_trades, liquid_trades


def _half_dates(calendar):
    mid = len(calendar) // 2
    return set(calendar[:mid])


def _orb_block(name, kind, trades, first_dates, compare):
    verdict = trend.judge(trades, first_dates)
    winners, names = _stock_share(trades)
    if compare:
        verdict = {"result": "comparison", "reasons": []}
    return {
        "name": name,
        "kind": kind,
        "trades_n": len(trades),
        "avg": _mean([trade["r_after"] for trade in trades]),
        "t": None,
        "first": verdict.get("first_half") if not compare else _half_avg(trades, first_dates, True),
        "second": verdict.get("second_half") if not compare else _half_avg(trades, first_dates, False),
        "winners": winners,
        "names": names,
        "verdict": verdict if not compare else {"result": "comparison", "reasons": []},
        "rows": trades,
        "compare": compare,
    }


def _half_avg(trades, first_dates, first):
    values = []
    for trade in trades:
        inside = trade["date"] in first_dates
        if inside == first:
            values.append(trade["r_after"])
    return _mean(values)


def score_switches(calendar, current_trades, liquid_trades, event_rows, vix_dates, vix_closes, emit):
    event_dates = set(row["date"] for row in event_rows)
    macro = set()
    for row in event_rows:
        if row["kind"] in ("rbi", "budget"):
            macro.add(row["date"])
    switched = set()
    for day in calendar:
        if switch_on(vix_into(vix_dates, vix_closes, day), day in event_dates):
            switched.add(day)
    emit("macro days %d, switch days %d" % (len(macro), len(switched)))
    first = _half_dates(calendar)
    blocks = []
    specs = (
        ("all days A", "compare", current_trades, None, True),
        ("all days B", "compare", liquid_trades, None, True),
        ("macro orb A", "macro", current_trades, macro, False),
        ("macro orb B", "macro", liquid_trades, macro, False),
        ("switch orb A", "switch", current_trades, switched, False),
        ("switch orb B", "switch", liquid_trades, switched, False),
    )
    for name, kind, trades, days, compare in specs:
        chosen = trades if days is None else [trade for trade in trades if trade["date"] in days]
        block = _orb_block(name, kind, chosen, first, compare)
        # judge() already filled first and second. A comparison still needs them.
        if compare:
            block["first"] = _half_avg(chosen, first, True)
            block["second"] = _half_avg(chosen, first, False)
        else:
            judged = trend.judge(chosen, first)
            block["first"] = judged["first_half"]
            block["second"] = judged["second_half"]
            block["verdict"] = {"result": judged["result"], "reasons": judged["reasons"]}
        blocks.append(block)
        emit("%s %s n %d avg %s" % (
            name, block["verdict"]["result"], block["trades_n"], harness._r(block["avg"])))
    return blocks


def _holdout_regimes(segments):
    points = []
    for seg in segments:
        for i, day in enumerate(seg.date):
            points.append((day, seg.c[i]))
    points.sort()
    return regime.by_date(points)


def run_holdout(root, blocks, event_rows, vix_dates, vix_closes, emit):
    """The only logged load. Called after an in-sample pass."""
    _first, last = survivorship.raw_span(data.bar_path(root, "day", lab.NIFTY))
    emit("holdout %s to %s" % (data.HOLDOUT_START.isoformat(), last.isoformat()))
    segments = lab.load_symbol(root, lab.NIFTY, end=last, final=True)
    regimes = _holdout_regimes(segments)
    begin = data.HOLDOUT_START
    expiry_done = None
    results_done = None
    orb_done = None
    for block in blocks:
        if block["verdict"]["result"] != "PASS":
            continue
        kind = block["kind"]
        if kind == "expiry":
            if expiry_done is None:
                expiry_done = score_expiry(
                    root, event_rows, begin, last, regimes, False, emit)
            found = None
            for item in expiry_done:
                if item["name"] == block["name"]:
                    found = item
            if found is None:
                continue
            hold = judge_holdout_pair(found["avg"], found["t"])
            block["holdout"] = {"avg": found["avg"], "t": found["t"], "trades": found["trades_n"], "verdict": hold}
        elif kind == "results":
            if results_done is None:
                books = _books(root, last, False)
                results_done = score_results(
                    root, event_rows, begin, last, regimes, books, False, emit)
            found = None
            for item in results_done:
                if item["name"] == block["name"]:
                    found = item
            if found is None:
                continue
            hold = judge_holdout_pair(found["avg"], found["t"])
            block["holdout"] = {"avg": found["avg"], "t": found["t"], "trades": found["trades_n"], "verdict": hold}
        else:
            if orb_done is None:
                calendar, _signals, _regimes_h, _books_h, current_trades, liquid_trades = score_orb(
                    root, begin, last, False, emit)
                orb_done = score_switches(
                    calendar, current_trades, liquid_trades, event_rows, vix_dates, vix_closes, emit)
            found = None
            for item in orb_done:
                if item["name"] == block["name"]:
                    found = item
            if found is None:
                continue
            tee = batch18.monthly_t(found["rows"], "r_after")
            hold = judge_holdout_pair(found["avg"], tee)
            block["holdout"] = {"avg": found["avg"], "t": tee, "trades": found["trades_n"], "verdict": hold}
        hold = block["holdout"]
        emit("holdout %s %s n %s avg %s t %s" % (
            block["name"], hold["verdict"]["result"], hold["trades"],
            harness._pct(hold["avg"]) if kind == "expiry" else harness._r(hold["avg"]),
            harness._num(hold["t"])))
    return last


def _line(name, cells):
    return name + " | " + " | ".join(cells)


def _report(stamp, event_rows, blocks, holdout_ran, last, strategies):
    lines = [rules_text(stamp).rstrip(), "", "Results.", ""]
    counts = {}
    for row in event_rows:
        counts[row["kind"]] = counts.get(row["kind"], 0) + 1
    lines.append("events.csv rows %d" % len(event_rows))
    for kind in sorted(counts):
        lines.append("%s %d" % (kind, counts[kind]))
    lines.append("")
    lines.append("20a expiry day, index. Long one lot. Own return after futures costs.")
    lines.append("name | n | own avg | excess avg | monthly t | 2015-2019 | 2020-2024 | up | down | sideways | result")
    for block in blocks:
        if block["kind"] != "expiry":
            continue
        buckets = block["buckets"]
        lines.append(_line(block["name"], [
            format(block["trades_n"], ",d"),
            harness._pct(block["avg"]),
            harness._pct(block["excess"]),
            harness._num(block["t"]),
            harness._pct(buckets.get("2015-2019")),
            harness._pct(buckets.get("2020-2024")),
            harness._pct(buckets.get("up")),
            harness._pct(buckets.get("down")),
            harness._pct(buckets.get("sideways")),
            block["verdict"]["result"],
        ]))
        for reason in block["verdict"]["reasons"]:
            lines.append("  " + reason)
        hold = block.get("holdout")
        if hold:
            lines.append("  holdout %s to %s %s n %s avg %s t %s" % (
                data.HOLDOUT_START.isoformat(), last.isoformat(),
                hold["verdict"]["result"], format(hold["trades"], ",d"),
                harness._pct(hold["avg"]), harness._num(hold["t"])))
    lines.append("")
    lines.append("20b results day, stocks. R after the tick and the intraday charges.")
    lines.append("name | n | days | avg R | monthly t | 2015-2019 | 2020-2024 | up | down | sideways | large | result")
    for block in blocks:
        if block["kind"] != "results":
            continue
        buckets = block["buckets"]
        lines.append(_line(block["name"], [
            format(block["trades_n"], ",d"),
            format(block["days"], ",d"),
            harness._r(block["avg"]),
            harness._num(block["t"]),
            harness._r(buckets.get("2015-2019")),
            harness._r(buckets.get("2020-2024")),
            harness._r(buckets.get("up")),
            harness._r(buckets.get("down")),
            harness._r(buckets.get("sideways")),
            harness._r(buckets.get("large")),
            block["verdict"]["result"],
        ]))
        for reason in block["verdict"]["reasons"]:
            lines.append("  " + reason)
        hold = block.get("holdout")
        if hold:
            lines.append("  holdout %s to %s %s n %s avg %s t %s" % (
                data.HOLDOUT_START.isoformat(), last.isoformat(),
                hold["verdict"]["result"], format(hold["trades"], ",d"),
                harness._r(hold["avg"]), harness._num(hold["t"])))
    lines.append("")
    lines.append("20c macro days and 20d switch. Attempt 8 rule. all days is a comparison.")
    lines.append("name | n | avg R | first half | second half | stocks above 0 | result")
    for block in blocks:
        if block["kind"] not in ("macro", "switch", "compare"):
            continue
        if block["names"]:
            share = "%d of %d" % (block["winners"], block["names"])
        else:
            share = "n/a"
        lines.append(_line(block["name"], [
            format(block["trades_n"], ",d"),
            harness._r(block["avg"]),
            harness._r(block.get("first")),
            harness._r(block.get("second")),
            share,
            block["verdict"]["result"],
        ]))
        for reason in block["verdict"]["reasons"]:
            lines.append("  " + reason)
        hold = block.get("holdout")
        if hold:
            lines.append("  holdout %s to %s %s n %s avg %s t %s" % (
                data.HOLDOUT_START.isoformat(), last.isoformat(),
                hold["verdict"]["result"], format(hold["trades"], ",d"),
                harness._r(hold["avg"]), harness._num(hold["t"])))
    if not holdout_ran:
        lines.append("")
        lines.append("No variant passed. The holdout was not opened.")
    lines.append("")
    lines.append(batch18.bucket_line(strategies))
    lines.append("")
    return "\n".join(lines)


def _summary_rows(stamp, blocks, last):
    rows = []
    window = "%s to %s" % (START.isoformat(), END.isoformat())
    hold_window = "%s to %s" % (data.HOLDOUT_START.isoformat(), last.isoformat() if last else "")
    for block in blocks:
        if block.get("compare"):
            continue
        if block["kind"] == "expiry":
            avg = harness._pct(block["avg"])
        else:
            avg = harness._r(block["avg"])
        rows.append("| 20 | %s | %s. | attempt 20, rules fixed before the run | %s | %s | %s | %s | %s |" % (
            stamp.isoformat(), block["name"], window,
            format(block["trades_n"], ",d"), avg, harness._num(block["t"]),
            block["verdict"]["result"]))
        hold = block.get("holdout")
        if not hold:
            continue
        if block["kind"] == "expiry":
            havg = harness._pct(hold["avg"])
        else:
            havg = harness._r(hold["avg"])
        rows.append("| 20 | %s | holdout %s. | same rule, one logged load | %s | %s | %s | %s | %s |" % (
            stamp.isoformat(), block["name"], hold_window,
            format(hold["trades"], ",d"), havg, harness._num(hold["t"]),
            hold["verdict"]["result"]))
    return rows


def finish_catalogue(path, blocks, looked, attempt=20):
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    for block in blocks:
        if block.get("compare"):
            continue
        tier = batch18.tier_of(block)
        row = "| %s | %d | %s |" % (block["name"], attempt, batch18.note_of(block))
        if tier == "Bucket":
            text = batch18.add_bucket_row(text, row)
        else:
            text = batch18.add_tier_row(text, tier, row)
    for name in looked:
        text = batch18.set_family(text, name)
    if not text.endswith("\n"):
        text += "\n"
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


def in_sample(root, nse, emit):
    """Attempt 20 on the research window. No holdout load."""
    path = os.path.join(nse, "events.csv")
    event_rows = events.read_events(path)
    vix_dates, vix_closes = load_vix(os.path.join(nse, "vix.csv"))
    emit("vix closes %d" % len(vix_closes))
    regimes = _regimes(root, END, True)
    blocks = []
    blocks.extend(score_expiry(root, event_rows, START, END, regimes, True, emit))
    books = _books(root, END, True)
    blocks.extend(score_results(
        root, event_rows, START, END, regimes, books, True, emit))
    # Fresh turnover books. score_results walks each book's cursor forward,
    # and that cursor does not rewind.
    calendar, signals, _reg, _loaded, current_trades, liquid_trades = score_orb(
        root, START, END, True, emit)
    blocks.extend(score_switches(
        calendar, current_trades, liquid_trades, event_rows, vix_dates, vix_closes, emit))
    return blocks, {
        "events": event_rows,
        "vix_dates": vix_dates,
        "vix_closes": vix_closes,
        "calendar": calendar,
        "signals": signals,
        "current": current_trades,
        "liquid": liquid_trades,
    }


def main(argv=None, log=None):
    import argparse
    parser = argparse.ArgumentParser(description="Attempt 20. Nothing is ordered.")
    parser.add_argument("--root", default=os.path.join("data", "kite"))
    parser.add_argument("--nse", default=os.path.join("data", "nse"))
    parser.add_argument("--experiments", default=EXPERIMENTS)
    parser.add_argument("--strategies", default=STRATEGIES)
    args = parser.parse_args(argv)
    emit = log or (lambda line: print(line, flush=True))
    stamp = datetime.date.today()
    write_rules(args.experiments, stamp)
    ensure_family(args.strategies)
    emit("rules for attempt 20 written to %s before the run" % args.experiments)
    path = os.path.join(args.nse, "events.csv")
    if not os.path.isfile(path):
        emit("events.csv is missing; expiry dates are not invented")
        return 1
    blocks, ctx = in_sample(args.root, args.nse, emit)
    event_rows = ctx["events"]
    passed = [block for block in blocks if block["verdict"]["result"] == "PASS"]
    last = None
    looked = []
    if passed:
        last = run_holdout(
            args.root, blocks, event_rows, ctx["vix_dates"], ctx["vix_closes"], emit)
        looked.append(FAMILY)
    else:
        emit("no variant passed; holdout was not opened")
    finish_catalogue(args.strategies, blocks, looked)
    section = _report(stamp, event_rows, blocks, bool(passed), last, args.strategies)
    follow.install_attempt(args.experiments, 20, section, _summary_rows(stamp, blocks, last))
    for line in section.splitlines():
        if line.startswith("20") or line.startswith("name ") or line.startswith("nifty ") or line.startswith("bank ") or line.startswith("results ") or line.startswith("macro ") or line.startswith("switch ") or line.startswith("all days") or line.startswith("No variant") or line.startswith("events") or line.startswith("Bucket"):
            emit(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
