#!/usr/bin/env python3
"""Attempt 15: check the attempt 14 RSI(2) pass.

Rules are written to EXPERIMENTS.md before the run. Parts 1 to 3 stay inside
2005-2024. Part 4 is the one holdout load, with final=True. Nothing is placed.

    python3 india/research/verify.py
"""

import bisect
import datetime
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from india.research import data
from india.research import follow as f
from india.research import harness as h
from india.research import signal_lab as lab
from india.research import ta

SLIP = 0.001
STRESS_SEED = 30000
CAPITAL = 1000000.0
SLOTS = 10
SLOT = CAPITAL / float(SLOTS)
HOLDOUT = data.HOLDOUT_START


def rsi_specs():
    """The three attempt 14 RSI variants, unchanged."""
    found = []
    for spec in f.batch14():
        if spec["kind"] == "rsi":
            found.append(spec)
    return found


def stress_specs():
    """Slippage and next-close on the two thresholds, then three neighbours of rsi2 < 10."""
    return [
        {"name": "rsi2 < 5 slip", "rsi_max": 5.0, "down2": False, "rsi": "rsi2",
         "sma": "sma200", "exit": "sma5", "entry": "o", "slip": SLIP},
        {"name": "rsi2 < 10 slip", "rsi_max": 10.0, "down2": False, "rsi": "rsi2",
         "sma": "sma200", "exit": "sma5", "entry": "o", "slip": SLIP},
        {"name": "rsi2 < 5 close", "rsi_max": 5.0, "down2": False, "rsi": "rsi2",
         "sma": "sma200", "exit": "sma5", "entry": "c", "slip": 0.0},
        {"name": "rsi2 < 10 close", "rsi_max": 10.0, "down2": False, "rsi": "rsi2",
         "sma": "sma200", "exit": "sma5", "entry": "c", "slip": 0.0},
        {"name": "rsi3 < 10", "rsi_max": 10.0, "down2": False, "rsi": "rsi3",
         "sma": "sma200", "exit": "sma5", "entry": "o", "slip": 0.0},
        {"name": "exit sma10", "rsi_max": 10.0, "down2": False, "rsi": "rsi2",
         "sma": "sma200", "exit": "sma10", "entry": "o", "slip": 0.0},
        {"name": "sma100 filter", "rsi_max": 10.0, "down2": False, "rsi": "rsi2",
         "sma": "sma100", "exit": "sma5", "entry": "o", "slip": 0.0},
    ]


def index_names(root):
    """Every daily file whose symbol starts with NIFTY. Part files are skipped."""
    folder = os.path.join(root, "day")
    found = []
    if not os.path.isdir(folder):
        return found
    suffix = ".csv.gz"
    for name in os.listdir(folder):
        if not name.endswith(suffix) or name.endswith(".part.csv.gz"):
            continue
        symbol = name[:-len(suffix)]
        if symbol.startswith("NIFTY"):
            found.append(symbol)
    found.sort()
    return found


def attach_more(segments):
    """SMA5 and RSI(2) from attempt 14, plus the three neighbour series."""
    f.attach_indicators(segments)
    for seg in segments:
        seg.sma10 = ta.sma_series(seg.c, 10)
        seg.sma100 = ta.sma_series(seg.c, 100)
        seg.rsi3 = ta.rsi_series(seg.c, 3)


def hit_named(attr):
    def hit(seg, j):
        value = getattr(seg, attr)[j]
        return value is not None and seg.c[j] > value
    return hit


def exit_hit(name):
    """SMA5 uses the attempt 14 function. SMA10 is the neighbour."""
    if name == "sma5":
        return f.close_above_sma5
    return hit_named(name)


def signal_fires(seg, i, spec):
    """Base RSI(2) above SMA200 goes through attempt 14. Neighbours use the named series."""
    if spec.get("rsi", "rsi2") == "rsi2" and spec.get("sma", "sma200") == "sma200":
        return f.rsi_fires(seg, i, spec["rsi_max"], spec["down2"])
    if i < 0 or i >= len(seg.c):
        return False
    sma = getattr(seg, spec["sma"])[i]
    rsi = getattr(seg, spec["rsi"])[i]
    if sma is None or rsi is None or not seg.c[i] > sma:
        return False
    if not rsi < spec["rsi_max"]:
        return False
    if spec.get("down2"):
        if i < 2:
            return False
        if not (seg.c[i] < seg.c[i - 1] and seg.c[i - 1] < seg.c[i - 2]):
            return False
    return True


def bar_px(seg, i, field):
    if field == "o":
        return seg.o[i]
    return seg.c[i]


def slipped(entry, exit_px, slip):
    """Long fills: pay more on the buy, receive less on the sell."""
    if not slip:
        return entry, exit_px
    return entry * (1.0 + slip), exit_px * (1.0 - slip)


def mkt_return(nifty, entry_day, exit_day, entry_open, exit_open):
    """NIFTY price return over the trade's own window. No cost on the benchmark."""
    entry = nifty.get(entry_day)
    exit_bar = nifty.get(exit_day)
    if entry is None or exit_bar is None:
        return None
    base = entry.get("open") if entry_open else entry.get("close")
    px = exit_bar.get("open") if exit_open else exit_bar.get("close")
    if base is None or px is None or not base > 0 or not px > 0:
        return None
    return (px / base - 1.0) * 100.0


def priced(seg, entry_i, found, nifty, field, slip):
    """Percent return after delivery costs, and the NIFTY return over that window."""
    if found is None:
        return None
    exit_i, px, on_open = found
    entry = bar_px(seg, entry_i, field)
    entry, px = slipped(entry, px, slip)
    ret = f.net_return(entry, px)
    if ret is None:
        return None
    entry_day = seg.date[entry_i]
    exit_day = seg.date[exit_i]
    return {
        "ret": ret,
        "mkt": mkt_return(nifty, entry_day, exit_day, field == "o", on_open),
        "hold": (exit_day - entry_day).days,
        "exit_day": exit_day,
        "fill": px,
        "at_open": on_open,
        "entry": entry,
        "entry_day": entry_day,
    }


def turnover_before(seg, i, n=lab.TURNOVER_N):
    """Mean close times volume of the n sessions before i, inside this segment."""
    if i < n:
        return None
    total = 0.0
    for j in range(i - n, i):
        total += seg.c[j] * float(seg.v[j])
    return total / float(n)


def order_key(order):
    """Lowest RSI first. A tie takes the higher 60-day turnover, then the name."""
    turn = order.get("turnover")
    if turn is None:
        turn = -1.0
    return (order["rsi"], -turn, order["name"])


def take_slots(orders, room, held):
    """Fill free slots. A name already held, or already chosen today, is skipped."""
    if room <= 0:
        return []
    blocked = set(held)
    chosen = []
    for order in sorted(orders, key=order_key):
        if len(chosen) >= room:
            break
        name = order["name"]
        if name in blocked:
            continue
        chosen.append(order)
        blocked.add(name)
    return chosen


def on_or_after(day, calendar):
    """The session on `day`, or the next calendar session when `day` is missing."""
    if not calendar:
        return None
    i = bisect.bisect_left(calendar, day)
    if i >= len(calendar):
        return None
    return calendar[i]


def trade_stats(trades):
    """Average return, and the t of monthly mean (return minus NIFTY)."""
    rets = []
    by_month = {}
    excesses = []
    for trade in trades:
        rets.append(trade["ret"])
        excess = trade.get("excess")
        if excess is None and trade.get("mkt") is not None:
            excess = trade["ret"] - trade["mkt"]
        if excess is None:
            continue
        excesses.append(excess)
        key = trade.get("month")
        if key is None:
            day = trade["date"]
            key = (day.year, day.month)
        by_month.setdefault(key, []).append(excess)
    monthly = []
    for key in sorted(by_month):
        monthly.append(h._mean(by_month[key]))
    return {
        "trades": len(trades),
        "avg": h._mean(rets),
        "excess": h._mean(excesses),
        "t": h.t_stat(monthly),
    }


def judge_pooled(avg, t, good, n):
    """Part 1. Exactly 2/3 of the indices passes. The t test is strict."""
    reasons = []
    if avg is None or not avg > 0:
        reasons.append("pooled avg after costs %s is not above 0" % h._pct(avg))
    if t is None or not t > 2:
        reasons.append("pooled excess t %s is not above 2" % h._num(t))
    if n <= 0 or good * 3 < 2 * n:
        reasons.append("positive on %d of %d indices, need at least 2/3" % (good, n))
    return {"result": "PASS" if not reasons else "FAIL", "reasons": reasons}


def part_verdict(blocks):
    """Part 1 passes only when every variant passes."""
    failed = []
    for block in blocks:
        if block["verdict"]["result"] != "PASS":
            failed.append("%s: %s" % (block["name"], "; ".join(block["verdict"]["reasons"])))
    return {"result": "PASS" if not failed else "FAIL", "reasons": failed}


def judge_holdout(avg, t):
    """Part 4, per trade. Strict on both marks."""
    reasons = []
    if avg is None or not avg > 0:
        reasons.append("avg return after costs %s is not above 0" % h._pct(avg))
    if t is None or not t > 2:
        reasons.append("market-adjusted excess t %s is not above 2" % h._num(t))
    return {"result": "PASS" if not reasons else "FAIL", "reasons": reasons}


def nifty_map(segments):
    out = {}
    for seg in segments:
        for i, day in enumerate(seg.date):
            out[day] = {"open": seg.o[i], "close": seg.c[i]}
    return out


def universe_of(name, segments):
    out = {}
    for seg in segments:
        for day in seg.date:
            out[day] = set([name])
    return out


def collect_index(name, segments, nifty, specs):
    """Trades from follow.scan_signals, so the rule is the attempt 14 function."""
    universe = universe_of(name, segments)
    found = f.scan_signals(name, segments, universe, {}, {}, nifty, specs)
    rows = {}
    for spec in specs:
        trades = []
        for trade in found[spec["name"]]:
            item = dict(trade)
            if item.get("mkt") is not None:
                item["excess"] = item["ret"] - item["mkt"]
            trades.append(item)
        rows[spec["name"]] = trades
    return rows


def pool_key(field, exit_name, slip):
    return "%s|%s|%s" % (field, exit_name, slip)


def walk_symbol(symbol, segments, top200, nifty, pools, orders, stress, start, end):
    """Signals and the random pools for one symbol. `start` and `end` bound the entry date."""
    for seg in segments:
        n = len(seg.date)
        for entry_i in range(n):
            day = seg.date[entry_i]
            if day < start or day > end:
                continue
            if symbol not in top200.get(day, ()):
                continue
            for exit_name, field, slip in (
                    ("sma5", "o", 0.0),
                    ("sma5", "o", SLIP),
                    ("sma5", "c", 0.0),
                    ("sma10", "o", 0.0)):
                found = f.exit_rule(seg, entry_i, f.RSI_LIMIT, exit_hit(exit_name))
                done = priced(seg, entry_i, found, nifty, field, slip)
                if done is None:
                    continue
                f._pool_add(pools, pool_key(field, exit_name, slip), symbol, day, done["ret"], done["mkt"])
        for i in range(n - 1):
            entry_i = i + 1
            entry_day = seg.date[entry_i]
            if entry_day < start or entry_day > end:
                continue
            if symbol not in top200.get(seg.date[i], ()):
                continue
            base = f.exit_rule(seg, entry_i, f.RSI_LIMIT, f.close_above_sma5)
            for spec in rsi_specs():
                if not f.rsi_fires(seg, i, spec["rsi_max"], spec["down2"]):
                    continue
                if base is None:
                    continue
                exit_i, px, on_open = base
                entry = seg.o[entry_i]
                if not entry > 0 or not px > 0:
                    continue
                orders[spec["name"]].append({
                    "name": symbol,
                    "entry_date": entry_day,
                    "exit_date": seg.date[exit_i],
                    "entry": entry,
                    "fill": px,
                    "at_open": on_open,
                    "rsi": seg.rsi2[i],
                    "turnover": turnover_before(seg, i),
                    "seg": seg,
                })
            for spec in stress_specs():
                if not signal_fires(seg, i, spec):
                    continue
                found = f.exit_rule(seg, entry_i, f.RSI_LIMIT, exit_hit(spec["exit"]))
                done = priced(seg, entry_i, found, nifty, spec["entry"], spec["slip"])
                if done is None:
                    continue
                stress[spec["name"]].append(f.make_trade(
                    entry_day, symbol, done["ret"], done["mkt"], None, False, done["hold"]))


def holdout_trades(symbol, segments, top200, nifty, start, end):
    """rsi2 < 5 only. Same fires, exit, and delivery cost. The window is the only change."""
    spec = rsi_specs()[0]
    trades = []
    orders = []
    for seg in segments:
        n = len(seg.date)
        for i in range(n - 1):
            entry_i = i + 1
            entry_day = seg.date[entry_i]
            if entry_day < start or entry_day > end:
                continue
            if symbol not in top200.get(seg.date[i], ()):
                continue
            if not f.rsi_fires(seg, i, spec["rsi_max"], spec["down2"]):
                continue
            found = f.exit_rule(seg, entry_i, f.RSI_LIMIT, f.close_above_sma5)
            done = priced(seg, entry_i, found, nifty, "o", 0.0)
            if done is None:
                continue
            trades.append(f.make_trade(
                entry_day, symbol, done["ret"], done["mkt"], None, False, done["hold"]))
            exit_i, px, on_open = found
            orders.append({
                "name": symbol,
                "entry_date": entry_day,
                "exit_date": seg.date[exit_i],
                "entry": seg.o[entry_i],
                "fill": px,
                "at_open": on_open,
                "rsi": seg.rsi2[i],
                "turnover": turnover_before(seg, i),
                "seg": seg,
            })
    return trades, orders


def simulate_book(orders, calendar, nifty, park, capital=CAPITAL, slots=SLOTS):
    """Fixed slots. Idle cash earns NIFTY when park is true, and nothing when it is false."""
    by_entry = {}
    for order in orders:
        by_entry.setdefault(order["entry_date"], []).append(order)
    book = h.Book(capital, park=park)
    if calendar and nifty.get(calendar[0], {}).get("open", 0) > 0:
        book.fund_nifty(nifty[calendar[0]]["open"])
    equity = []
    invested = []
    entries = 0
    bought = []
    slot = capital / float(slots)
    for day in calendar:
        nopen = nifty[day]["open"]
        nclose = nifty[day]["close"]
        left_today = set()
        for name in list(book.pos):
            pos = book.pos[name]
            if pos.get("exit_date") == day and pos.get("at_open"):
                book.sell(name, pos["shares"], pos["fill"], nopen)
                left_today.add(name)
        room = slots - len(book.pos)
        held = set(book.pos)
        for name in left_today:
            held.add(name)
        for order in take_slots(by_entry.get(day, []), room, held):
            shares = h.shares_for(slot, order["entry"])
            got = book.buy(order["name"], order["seg"], shares, order["entry"], nopen)
            if got < 1:
                continue
            pos = book.pos[order["name"]]
            pos["exit_date"] = order["exit_date"]
            pos["fill"] = order["fill"]
            pos["at_open"] = order["at_open"]
            entries += 1
            bought.append(order["name"])
            if order["exit_date"] == day and order["at_open"]:
                book.sell(order["name"], pos["shares"], order["fill"], nopen)
                left_today.add(order["name"])
        for name in list(book.pos):
            pos = book.pos[name]
            if pos.get("exit_date") == day and not pos.get("at_open"):
                book.sell(name, pos["shares"], pos["fill"], nclose)
        _exit_broken(book, day, nclose)
        total = book.value(day, nclose, "c")
        equity.append(total)
        stocks = book.stock_value(day, "c")
        if total > 0:
            invested.append(stocks / total)
        else:
            invested.append(0.0)
    stats = h.path_stats(calendar, equity, capital, nifty, {})
    stats["invested"] = h._mean(invested)
    stats["entries"] = entries
    stats["bought"] = bought
    if len(calendar) >= 2 and calendar[-1] > calendar[0]:
        years = (calendar[-1] - calendar[0]).days / h.YEAR_DAYS
        stats["trades_per_year"] = entries / years if years > 0 else None
    else:
        stats["trades_per_year"] = None
    return stats


def _exit_broken(book, day, nifty_px):
    """Sell a name whose segment ends today. A missing index does not raise."""
    for name in list(book.pos):
        seg = book.pos[name]["seg"]
        idx = None if seg is None else getattr(seg, "idx", None)
        if seg is None or not seg.date or seg.date[-1] != day or idx is None or day not in idx:
            continue
        book.sell(name, book.pos[name]["shares"], seg.c[idx[day]], nifty_px)


def align_orders(orders, calendar):
    """Move an exit that is not a calendar session onto the next session. Drop the rest."""
    kept = []
    for order in orders:
        entry = on_or_after(order["entry_date"], calendar)
        exit_day = on_or_after(order["exit_date"], calendar)
        if entry is None or exit_day is None or entry != order["entry_date"]:
            continue
        if exit_day < entry:
            continue
        item = dict(order)
        item["exit_date"] = exit_day
        kept.append(item)
    return kept


def run_indices(root, log):
    """Part 1. final stays false. Each index is its own series."""
    emit = log or (lambda line: None)
    names = index_names(root)
    emit("index files %d" % len(names))
    nifty_segs = lab.load_symbol(root, lab.NIFTY, end=h.END, final=False)
    attach_more(nifty_segs)
    nifty = nifty_map(nifty_segs)
    specs = rsi_specs()
    collected = {}
    per_index = {}
    for spec in specs:
        collected[spec["name"]] = []
        per_index[spec["name"]] = []
    for name in names:
        try:
            if name == lab.NIFTY:
                segs = nifty_segs
            else:
                segs = lab.load_symbol(root, name, end=h.END, final=False)
                attach_more(segs)
        except data.DataError:
            emit("skip %s" % name)
            continue
        found = collect_index(name, segs, nifty, specs)
        for spec in specs:
            trades = found[spec["name"]]
            stats = trade_stats(trades)
            stats["name"] = name
            per_index[spec["name"]].append(stats)
            collected[spec["name"]].extend(trades)
        emit("  %s" % name)
    blocks = []
    for spec in specs:
        rows = per_index[spec["name"]]
        pooled = trade_stats(collected[spec["name"]])
        good = 0
        for row in rows:
            if row["avg"] is not None and row["avg"] > 0:
                good += 1
        verdict = judge_pooled(pooled["avg"], pooled["t"], good, len(rows))
        blocks.append({
            "name": spec["name"],
            "rows": rows,
            "trades": pooled["trades"],
            "avg": pooled["avg"],
            "excess": pooled["excess"],
            "t": pooled["t"],
            "positive": good,
            "indices": len(rows),
            "verdict": verdict,
        })
    return blocks, part_verdict(blocks)


def run_books(ctx, orders, calendar, log):
    """Part 2. Two cash treatments for each RSI variant, plus NIFTY buy and hold."""
    emit = log or (lambda line: None)
    nifty = ctx["nifty"]
    books = []
    for spec in rsi_specs():
        if spec["name"] not in orders:
            continue
        aligned = align_orders(orders[spec["name"]], calendar)
        for park, label in ((False, "cash 0"), (True, "cash in NIFTY")):
            emit("portfolio %s %s (%d orders)" % (spec["name"], label, len(aligned)))
            stats = simulate_book(aligned, calendar, nifty, park)
            stats["name"] = spec["name"]
            stats["cash"] = label
            books.append(stats)
    bench = h.path_stats(calendar, h.nifty_path(calendar, nifty, CAPITAL), CAPITAL, nifty, {})
    bench["name"] = "NIFTY 50"
    bench["cash"] = "price only"
    bench["invested"] = 1.0
    bench["entries"] = 1
    bench["trades_per_year"] = None
    return books, bench


def run_stress(stress, pools, runs, log):
    """Part 3. t is the attempt 14 market-adjusted t versus same-month random entries."""
    emit = log or (lambda line: None)
    blocks = []
    for index, spec in enumerate(stress_specs()):
        trades = stress[spec["name"]]
        style = pool_key(spec["entry"], spec["exit"], spec["slip"])
        seed = h.SEED + STRESS_SEED + index * 1000
        emit("stress %s (%d trades)" % (spec["name"], len(trades)))
        f.apply_trade_random(trades, pools, style, runs, seed)
        block = f.summarise_swing(spec["name"], trades)
        block["seed"] = seed
        blocks.append(block)
    return blocks


def run_holdout(root, log):
    """Part 4. The one final=True load. rsi2 < 5, then the same book as part 2."""
    emit = log or (lambda line: None)
    path = data.bar_path(root, "day", lab.NIFTY)
    from india.research import survivorship as sv
    _first, last = sv.raw_span(path)
    emit("holdout %s to %s" % (HOLDOUT.isoformat(), last.isoformat()))
    ctx = h.load_context(root, start=f.SWING_START, end=last, log=emit, final=True)
    for symbol in ctx["loaded"]:
        attach_more(symbol["segments"])
    trades = []
    orders = []
    for symbol in ctx["loaded"]:
        found, book_orders = holdout_trades(
            symbol["name"], symbol["segments"], ctx["top200"], ctx["nifty"], HOLDOUT, last)
        trades.extend(found)
        orders.extend(book_orders)
    stats = trade_stats(trades)
    verdict = judge_holdout(stats["avg"], stats["t"])
    calendar = []
    for day in ctx["calendar"]:
        if HOLDOUT <= day <= last and ctx["nifty"].get(day, {}).get("open", 0) > 0:
            calendar.append(day)
    books, bench = run_books(ctx, {"rsi2 < 5": orders}, calendar, emit)
    return {
        "last": last,
        "trades": stats["trades"],
        "avg": stats["avg"],
        "excess": stats["excess"],
        "t": stats["t"],
        "verdict": verdict,
        "books": books,
        "bench": bench,
    }


def rules_text(stamp):
    """Attempt 15 rules. No measured result belongs in this text."""
    return "\n".join([
        "## Attempt 15",
        "",
        "Rules fixed on %s, before the run." % stamp,
        "",
        "This attempt checks the three RSI(2) variants that passed attempt 14. "
        "The signal, the exit, and the delivery cost are the attempt 14 functions. "
        "Nothing in the pass mark is moved to fit a result. Parts 2 and 3 have no "
        "pass mark. They are reports. Parts 1 and 4 are judged.",
        "",
        "1. Survivorship-free index test, 2005-01-01 through 2024-12-31. Every "
        "daily file in data/kite/day whose symbol starts with NIFTY is a series: "
        "NIFTY 50, NIFTY BANK, the sector indices, and the factor indices. A file "
        "that does not load is omitted. A file that loads and never trades counts "
        "as not positive. There is no stock universe. Each index is traded as its "
        "own price, with signal_lab.delivery on Rs 1,00,000, as a cash ETF. The "
        "three variants are rsi2 < 5, rsi2 < 10, and rsi2 < 10 down2, through "
        "follow.scan_signals. The market adjustment is the NIFTY 50 price return "
        "from the entry open to the exit open, minus nothing else. Excess for a "
        "trade is its percent return after costs minus that NIFTY return. A trade "
        "with no NIFTY bar on an end date stays in the average and stays out of "
        "the t. The t is the one-sample t of the mean excess in each calendar "
        "month. Pooled avg is the equal-weight mean of every trade of that "
        "variant across indices. Pooled t groups those same trades by month, "
        "averages inside the month, then takes the t across months. Positive "
        "means the index average after costs is strictly above 0. Each variant "
        "is judged on its own. A variant passes when its pooled average is above "
        "0, its pooled excess t is above 2, and the average is positive on at "
        "least 2/3 of the loaded indices. Exactly 2/3 passes. Part 1 passes only "
        "when all three variants pass. Dates from 2025-01-01 on are not requested.",
        "",
        "2. Portfolio, same window, the attempt 14 stock universe (top 200 by "
        "prior 60-session turnover on the signal day). Capital is Rs 10,00,000. "
        "At most 10 positions. Each new order is sized so the buy plus the "
        "buy-side delivery costs fit in Rs 1,00,000, using harness.shares_for. "
        "The book then pays harness.trade_cost on the buy and on the sell, which "
        "is the same delivery schedule as signal_lab.delivery (STT on both "
        "sides, stamp on the buy, the DP charge on the sell). When more new "
        "signals share an entry day than there are free slots, the lowest RSI(2) "
        "is taken first, then the highest 60-session turnover inside the signal "
        "segment, then the symbol name. A name already held is not a new slot. "
        "A name sold at the open is not bought again that day. The exit is the "
        "attempt 14 exit, so it is an open. Turnover that is missing inside the "
        "segment sorts after every name that has one. An exit that is not a "
        "NIFTY session is sold on the next NIFTY session at the same stock fill. "
        "Two books: idle cash earns 0, and idle cash is the NIFTY 50 price sleeve "
        "(funded with no cost, the harness Book). The invested share is the "
        "stock mark at the close divided by total equity, averaged over "
        "sessions. The NIFTY sleeve is not counted as invested. Trades per year "
        "are entries divided by the calendar span in 365.25-day years. NIFTY 50 "
        "buy-and-hold is the price path from the first open to each close, no "
        "costs and no dividends. Reported for each variant and each cash "
        "treatment: CAGR, max drawdown, worst year, yearly returns, average "
        "invested share, trades per year, and the NIFTY path on the same dates.",
        "",
        "3. Stress, in sample, on rsi2 < 5 and rsi2 < 10, plus three neighbours "
        "of rsi2 < 10. (a) 0.1% extra slippage: the buy fill is the entry times "
        "1.001 and the sell fill is the exit times 0.999, then delivery costs "
        "on those fills. (b) The entry is the close of the next session instead "
        "of its open. The exit walk is unchanged, so a close above SMA5 on the "
        "entry session sells at the following open, and the time stop is still "
        "the open five sessions after that entry session. The NIFTY return for "
        "a close entry starts at the NIFTY close of the entry day. (c) Each "
        "neighbour changes one piece of rsi2 < 10 and leaves the other pieces: "
        "RSI(3) below 10 with SMA200 and the SMA5 exit; RSI(2) below 10 with "
        "the exit on a close above SMA10; RSI(2) below 10 with the trend filter "
        "SMA100 instead of SMA200. The random baseline is 100 runs, seed "
        "20261106 + 30000 + variant index times 1000 + the run index. Each run "
        "picks a same-month entry of the same symbol that was in the top 200 "
        "that day, and applies that variant's own entry price, slippage, and "
        "exit. The t is the attempt 14 t: market-adjusted excess versus those "
        "random entries, one mean per month. No pass mark.",
        "",
        "4. One holdout, after parts 1 to 3. final=True, logged once. The rule "
        "is rsi2 < 5 exactly as in attempt 14: same signal, next-open entry, "
        "SMA5 exit or the open after five sessions, delivery costs, top 200 on "
        "the signal day. Entries from 2025-01-01 through the last date in the "
        "NIFTY 50 daily file. Indicator warmup before 2025 is used and is not "
        "a trade. A signal whose entry open falls on or after 2025-01-01 is a "
        "holdout trade even when the signal close was in 2024. The per-trade "
        "excess is the return after costs minus the NIFTY 50 price return over "
        "the same entry open to exit open. It is not versus a random entry. "
        "The t is the one-sample t of the monthly mean excess. The portfolio "
        "in part 2 is run on the same entries, starting from fresh cash on the "
        "first holdout session, both cash treatments. PASS, on the per-trade "
        "series only: average return after costs above 0, and that "
        "market-adjusted excess t above 2. The portfolio numbers are recorded "
        "beside it and are not part of the pass line. The rule is not changed "
        "after this run.",
    ])


def _years(yearly, fmt):
    parts = []
    for year in sorted(yearly):
        parts.append("%d %s" % (year, fmt(yearly[year])))
    if not parts:
        return "n/a"
    return ", ".join(parts)


def index_table(block):
    lines = ["index | trades | avg after costs | excess vs NIFTY | t"]
    for row in block["rows"]:
        lines.append("%s | %s | %s | %s | %s" % (
            row["name"], format(row["trades"], ",d"), h._pct(row["avg"]),
            h._pct(row["excess"]), h._num(row["t"])))
    lines.append("POOLED %s | %s | %s | %s | %s | positive %d of %d | %s" % (
        block["name"], format(block["trades"], ",d"), h._pct(block["avg"]),
        h._pct(block["excess"]), h._num(block["t"]),
        block["positive"], block["indices"], block["verdict"]["result"]))
    return lines


def _share(value):
    if value is None:
        return "n/a"
    return h._pct(value * 100.0)


def book_table(books, bench):
    lines = ["variant | cash | CAGR | max DD | worst year | invested | trades/year"]
    for block in books:
        lines.append("%s | %s | %s | %s | %s | %s | %s" % (
            block["name"], block["cash"], h._pct(block.get("cagr")),
            h._pct(block.get("max_dd")), h._pct(block.get("worst_year")),
            _share(block.get("invested")),
            h._num(block.get("trades_per_year"))))
    lines.append("%s | %s | %s | %s | %s | %s | %s" % (
        bench["name"], bench["cash"], h._pct(bench.get("cagr")),
        h._pct(bench.get("max_dd")), h._pct(bench.get("worst_year")),
        h._pct(100.0), "n/a"))
    return lines


def stress_table(blocks):
    lines = ["variant | trades | avg after costs | t vs random"]
    for block in blocks:
        lines.append("%s | %s | %s | %s" % (
            block["name"], format(block["trades"], ",d"),
            h._pct(block["avg"]), h._num(block["t"])))
    return lines


def report_text(stamp, indices, part1, books, bench, stress, holdout):
    lines = [rules_text(stamp), "", "Results."]
    lines.append("")
    lines.append("Part 1. Index files, one table per variant.")
    for block in indices:
        lines.append("")
        lines.extend(index_table(block))
    lines.append("")
    if part1["result"] == "PASS":
        lines.append("Part 1 PASS.")
    else:
        lines.append("Part 1 FAIL: %s" % "; ".join(part1["reasons"]))
    lines.append("")
    lines.append("Part 2. Portfolio. No pass mark.")
    lines.extend(book_table(books, bench))
    for block in books:
        lines.append("%s, %s years: %s" % (
            block["name"], block["cash"], _years(block.get("yearly") or {}, h._pct)))
    lines.append("NIFTY 50 years: %s" % _years(bench.get("yearly") or {}, h._pct))
    lines.append("Part 2 report. No pass mark was set.")
    lines.append("")
    lines.append("Part 3. Stress. No pass mark.")
    lines.extend(stress_table(stress))
    lines.append("Part 3 report. No pass mark was set.")
    lines.append("")
    lines.append("Part 4. Holdout rsi2 < 5, %s to %s." % (
        HOLDOUT.isoformat(), holdout["last"].isoformat()))
    lines.append("per trade | %s | %s | %s | %s" % (
        format(holdout["trades"], ",d"), h._pct(holdout["avg"]),
        h._pct(holdout["excess"]), h._num(holdout["t"])))
    lines.extend(book_table(holdout["books"], holdout["bench"]))
    for block in holdout["books"]:
        lines.append("%s, %s years: %s" % (
            block["name"], block["cash"], _years(block.get("yearly") or {}, h._pct)))
    lines.append("NIFTY 50 years: %s" % _years(holdout["bench"].get("yearly") or {}, h._pct))
    verdict = holdout["verdict"]
    if verdict["result"] == "PASS":
        lines.append("Part 4 PASS.")
    else:
        lines.append("Part 4 FAIL: %s" % "; ".join(verdict["reasons"]))
    lines.append("The holdout rule was not changed after the run.")
    return "\n".join(lines).rstrip() + "\n"


def table_rows(stamp, indices, holdout):
    rows = []
    for block in indices:
        share = "%d of %d" % (block["positive"], block["indices"])
        rows.append("| 15 | %s | %s | %s | %s | %s | %s | %s | %s |" % (
            stamp,
            "index %s pooled, positive on %s." % (block["name"], share),
            "delivery costs on the index price, Rs 1,00,000",
            "every NIFTY daily file, 2005-01-01 to 2024-12-31",
            format(block["trades"], ",d"),
            h._pct(block["avg"]),
            h._num(block["t"]),
            block["verdict"]["result"]))
    rows.append("| 15 | %s | %s | %s | %s | %s | %s | %s | %s |" % (
        stamp,
        "RSI portfolio, Rs 10,00,000, 10 slots. No pass mark.",
        "harness delivery costs, cash at 0 and cash in NIFTY",
        "top 200 by prior 60-session turnover, 2005-01-01 to 2024-12-31",
        "see section",
        "see section",
        "see section",
        "REPORT"))
    rows.append("| 15 | %s | %s | %s | %s | %s | %s | %s | %s |" % (
        stamp,
        "RSI stress: slippage, next close, RSI3, SMA10, SMA100. No pass mark.",
        "delivery costs, t versus same-month random",
        "top 200 by prior 60-session turnover, 2005-01-01 to 2024-12-31",
        "see section",
        "see section",
        "see section",
        "REPORT"))
    rows.append("| 15 | %s | %s | %s | %s | %s | %s | %s | %s |" % (
        stamp,
        "holdout rsi2 < 5, per trade, through %s." % holdout["last"].isoformat(),
        "attempt 14 rule, delivery costs, final=True once",
        "top 200, %s to %s" % (HOLDOUT.isoformat(), holdout["last"].isoformat()),
        format(holdout["trades"], ",d"),
        h._pct(holdout["avg"]),
        h._num(holdout["t"]),
        holdout["verdict"]["result"]))
    return rows


def emit_part(label, verdict, emit):
    if verdict["result"] == "PASS":
        emit("%s PASS" % label)
    elif verdict["result"] == "REPORT":
        emit("%s report. No pass mark was set." % label)
    else:
        emit("%s FAIL: %s" % (label, "; ".join(verdict["reasons"])))


def main(argv=None, log=None):
    import argparse
    parser = argparse.ArgumentParser(description="Attempt 15. Nothing is placed.")
    parser.add_argument("--root", default=os.path.join("data", "kite"))
    parser.add_argument("--experiments", default=h.EXPERIMENTS)
    parser.add_argument("--runs", type=int, default=h.RUNS)
    args = parser.parse_args(argv)
    emit = log or (lambda line: print(line, flush=True))
    stamp = datetime.date.today().isoformat()
    f.install_attempt(args.experiments, 15, rules_text(stamp), [])
    emit("rules for attempt 15 written to %s before the run" % args.experiments)
    indices, part1 = run_indices(args.root, emit)
    emit("loading stocks for the portfolio and the stress")
    ctx = h.load_context(args.root, start=f.SWING_START, end=h.END, log=emit, final=False)
    orders = {}
    stress = {}
    for spec in rsi_specs():
        orders[spec["name"]] = []
    for spec in stress_specs():
        stress[spec["name"]] = []
    pools = {}
    loaded = ctx["loaded"]
    emit("scanning %d symbols" % len(loaded))
    for i, symbol in enumerate(loaded):
        attach_more(symbol["segments"])
        walk_symbol(
            symbol["name"], symbol["segments"], ctx["top200"], ctx["nifty"],
            pools, orders, stress, f.SWING_START, h.END)
        if (i + 1) % 50 == 0:
            emit("  symbol %d/%d" % (i + 1, len(loaded)))
    books, bench = run_books(ctx, orders, ctx["calendar"], emit)
    stressed = run_stress(stress, pools, args.runs, emit)
    holdout = run_holdout(args.root, emit)
    text = report_text(stamp, indices, part1, books, bench, stressed, holdout)
    f.install_attempt(args.experiments, 15, text, table_rows(stamp, indices, holdout))
    emit("Part 1")
    for block in indices:
        emit("")
        for line in index_table(block):
            emit(line)
    emit("")
    emit_part("Part 1", part1, emit)
    emit("Part 2")
    for line in book_table(books, bench):
        emit(line)
    for block in books:
        emit("%s, %s years: %s" % (
            block["name"], block["cash"], _years(block.get("yearly") or {}, h._pct)))
    emit("NIFTY 50 years: %s" % _years(bench.get("yearly") or {}, h._pct))
    emit_part("Part 2", {"result": "REPORT", "reasons": []}, emit)
    emit("Part 3")
    for line in stress_table(stressed):
        emit(line)
    emit_part("Part 3", {"result": "REPORT", "reasons": []}, emit)
    emit("Part 4")
    emit("per trade | %s | avg %s | excess %s | t %s" % (
        format(holdout["trades"], ",d"), h._pct(holdout["avg"]),
        h._pct(holdout["excess"]), h._num(holdout["t"])))
    for line in book_table(holdout["books"], holdout["bench"]):
        emit(line)
    emit_part("Part 4", holdout["verdict"], emit)
    return 0


if __name__ == "__main__":
    sys.exit(main())
