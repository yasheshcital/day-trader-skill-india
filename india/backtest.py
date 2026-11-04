#!/usr/bin/env python3
"""Batch backtest of the opening-range thesis. Standard library only.

Reads every AlgoTest 5-minute file in a folder, converts it in memory, and
replays trader-timemachine's own history_replay (loaded, not copied) on a
grid of rules. Nothing is placed.

    python3 india/backtest.py tests/fixtures/india/stocks
    python3 india/backtest.py tests/fixtures/india/nifty50 --side both --filter none --summary
    python3 india/backtest.py tests/fixtures/india/nifty50 --side both --filter inplay,market \
        --market tests/fixtures/india/NIFTY-2026-08-05_2026-11-03-5m.algotest.json --summary

Entry window: 09:30, or the end of the opening range when that is later, through
14:30. Flat by 15:10. Each trade risks --risk rupees (default 500) in whole
shares, and the position is capped at --capital (default 1,00,000). Costs come
from india/costs.py. A short is history_replay with side="sell": the stop is the
range high (the or-low rule) or the midpoint, rounded up, and the target is
below the entry. On a short the buy is the exit and the sell is the entry.
The market filter waits for NIFTY's own break: a stock can enter only on a
close at or after that signal bar. --max-trades-per-day keeps the earliest
entries of the day.
"""

import argparse
import datetime
import glob
import importlib.util
import json
import os
import statistics
import sys
from decimal import Decimal

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from india import algotest_to_yahoo
from india import costs

OR_MINUTES = (15, 30)
STOPS = ("or_mid", "or_low")
TARGETS = (1.0, 1.5, 2.0)
ENTRY_AFTER = 9 * 60 + 30     # 09:30, unless the opening range ends later
ENTRY_BEFORE = 14 * 60 + 30   # 14:30
FAR_FUTURE = datetime.datetime(2099, 1, 1)
AFTER_ALL = "9999-12-31"
INPLAY_WARMUP = 10
INPLAY_GAP = Decimal("0.01")
INPLAY_VOLUME = Decimal("2")
FILTERS = ("none", "inplay", "market")
SIDES = ("buy", "sell", "both")


class BacktestError(Exception):
    pass


def load_timemachine():
    """trader-timemachine/timemachine.py, by path. The folder name has a hyphen."""
    path = os.path.join(_ROOT, "trader-timemachine", "timemachine.py")
    spec = importlib.util.spec_from_file_location("backtest_timemachine", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _d(x):
    if isinstance(x, float):
        return Decimal(repr(x))
    return Decimal(str(x))


def rules():
    grid = []
    for minutes in OR_MINUTES:
        for stop in STOPS:
            for target in TARGETS:
                grid.append({"or_minutes": minutes, "stop": stop, "target_r": target})
    return grid


def rule_name(rule):
    r = rule["target_r"]
    text = ("%g" % r) if r == int(r) else ("%g" % r)
    return "%dm %s %sR" % (rule["or_minutes"], rule["stop"].replace("_", "-"), text)


def sides_of(side):
    if side == "both":
        return ("buy", "sell")
    if side in ("buy", "sell"):
        return (side,)
    raise BacktestError("side must be buy, sell or both, not %r" % (side,))


def parse_filters(text):
    """none, or a comma list of inplay and market. none cannot be combined."""
    raw = [part.strip().lower() for part in (text or "none").split(",") if part.strip()]
    if not raw:
        raw = ["none"]
    bad = [part for part in raw if part not in FILTERS]
    if bad:
        raise BacktestError("unknown filter %s" % ", ".join(bad))
    chosen = []
    for part in raw:
        if part not in chosen:
            chosen.append(part)
    if "none" in chosen and len(chosen) > 1:
        raise BacktestError("none cannot be combined with another filter")
    return [part for part in chosen if part != "none"]


def symbol_of(path, payload):
    try:
        return algotest_to_yahoo._named(payload, None)
    except algotest_to_yahoo.ConvertError:
        return algotest_to_yahoo._symbol(os.path.basename(path).split("-")[0])


def load_sessions(path, tm, before=None):
    """One AlgoTest file -> (symbol, full sessions, short sessions left out)."""
    with open(path, encoding="utf-8") as fh:
        payload = json.load(fh)
    sym = symbol_of(path, payload)
    doc, _report = algotest_to_yahoo.to_yahoo(payload, sym, interval="5m")
    result = doc["chart"]["result"][0]
    _meta, bars, _dropped = tm.parse_bars(result, FAR_FUTURE)
    full, short = tm.full_sessions(tm.split_sessions(bars), before or AFTER_ALL)
    return sym, full, short


def flat_slot(tm):
    """Bar index of the 15:10 flat-by, the same --until the time machine uses."""
    return (tm.FLAT_BY_MIN - tm.OPEN_MIN) // 5 - 1


def entry_window(or_minutes):
    """Minutes after midnight. 09:30, or the end of the range when that is later, to 14:30."""
    range_end = 9 * 60 + 15 + or_minutes
    return max(ENTRY_AFTER, range_end), ENTRY_BEFORE


def whole_shares(entry, stop, risk_rupees, capital):
    """Shares that risk risk_rupees, then cut so the position fits in capital.

    The distance is |entry - stop|, so a short (stop above the entry) sizes the
    same way as a long.
    """
    risk_ps = abs(_d(entry) - _d(stop))
    if risk_ps <= 0 or _d(entry) <= 0:
        return 0
    n = int(_d(risk_rupees) // risk_ps)
    cap = int(_d(capital) // _d(entry))
    return max(0, min(n, cap))


def _exit(trade, close):
    if trade["outcome"] == "target":
        return trade["target"]
    if trade["outcome"] == "stop":
        return trade["stop"]
    return close


def round_trip_for(side, entry, exit_px, shares):
    """Cost of one trade. A short buys to cover, so the buy is the exit."""
    if side == "buy":
        return costs.round_trip(entry, exit_px, shares)
    return costs.round_trip(exit_px, entry, shares)


def _or_volume(bars, n):
    total = Decimal("0")
    for bar in bars[:n]:
        total += _d(bar.get("v") or 0)
    return total


def day_in_play(sessions, index, or_minutes):
    """Gap of at least 1% from the previous close, or opening-range volume at least
    twice the average of the previous 10 sessions. index must be >= 10."""
    prev_close = _d(sessions[index - 1][1][-1]["c"])
    if prev_close <= 0:
        return False
    opened = _d(sessions[index][1][0]["o"])
    if abs(opened - prev_close) / prev_close >= INPLAY_GAP:
        return True
    n = or_minutes // 5
    today = _or_volume(sessions[index][1], n)
    earlier = [_or_volume(sessions[j][1], n) for j in range(index - INPLAY_WARMUP, index)]
    avg = sum(earlier) / Decimal(INPLAY_WARMUP)
    if avg <= 0:
        return False
    return today >= avg * INPLAY_VOLUME


def _side_of(value):
    """A bias entry is (side, close minute), or a bare side from an older caller."""
    if isinstance(value, tuple):
        return value[0]
    return value


def dates_for(sessions, side, filters, or_minutes, bias):
    """Dates this side may trade, and how many leading sessions the in-play filter skipped."""
    skipped = 0
    dates = []
    for i, (date, _bars) in enumerate(sessions):
        if "inplay" in filters:
            if i < INPLAY_WARMUP:
                skipped += 1
                continue
            if not day_in_play(sessions, i, or_minutes):
                continue
        if "market" in filters and _side_of(bias.get(date)) != side:
            continue
        dates.append(date)
    return set(dates), skipped


def market_bias(bars, or_minutes, tm):
    """(side, close minute) of NIFTY's first close beyond this opening range.

    side is buy when that close is up and sell when it is down. (None, None)
    when no close leaves the range by 14:30. The minute is the signal bar's
    close, so a stock cannot enter before it.
    """
    n = or_minutes // 5
    if len(bars) <= n:
        return None, None
    high = max(bar["h"] for bar in bars[:n])
    low = min(bar["l"] for bar in bars[:n])
    before, after = entry_window(or_minutes)
    for i in range(n, len(bars)):
        close_min = tm.OPEN_MIN + 5 * (i + 1)
        if close_min > after:
            break
        if close_min < before:
            continue
        close = bars[i]["c"]
        if close > high:
            return "buy", close_min
        if close < low:
            return "sell", close_min
    return None, None


def bias_by_date(sessions, or_minutes, tm):
    return dict((date, market_bias(bars, or_minutes, tm)) for date, bars in sessions)


def _exit_minute(bars, entry_i, side, stop, target, last, tm):
    """Close time of the bar that ends the trade. Stop is checked before the target,
    the same order as history_replay. The flat-by bar closes the rest."""
    long = side == "buy"
    for i in range(entry_i + 1, last + 1):
        bar = bars[i]
        if (bar["l"] <= stop) if long else (bar["h"] >= stop):
            return tm.OPEN_MIN + 5 * (i + 1)
        if (bar["h"] >= target) if long else (bar["l"] <= target):
            return tm.OPEN_MIN + 5 * (i + 1)
    return tm.OPEN_MIN + 5 * (last + 1)


def _collect_trades(tm, sessions, symbol, rule, last, side, before, after, keep, not_before):
    """history_replay trades. not_before maps a date to the earliest close minute.

    Bars that close before that minute are not candidates, so the entry is the
    first later close beyond the range, not the morning break restated.
    """
    spec = {
        "setup": "orb", "or_minutes": rule["or_minutes"], "stop_rule": rule["stop"],
        "target_r": rule["target_r"],
    }
    if not_before is None:
        hist = tm.history_replay(sessions, spec, last, side, before, after, symbol)
        trades = hist["trades"]
        if keep is not None:
            trades = [trade for trade in trades if trade["date"] in keep]
        return hist, trades
    groups = {}
    for date, bars in sessions:
        if keep is not None and date not in keep:
            continue
        minute = not_before.get(date)
        if minute is None:
            continue
        earliest = minute if minute > before else before
        if earliest > after:
            continue
        groups.setdefault(earliest, []).append((date, bars))
    trades = []
    for earliest, chunk in groups.items():
        hist = tm.history_replay(chunk, spec, last, side, earliest, after, symbol)
        trades.extend(hist["trades"])
    return {"trades": trades, "triggered": len(trades)}, trades


def score_symbol(tm, sessions, symbol, rule, risk, capital, side="buy", keep=None, not_before=None):
    """history_replay for one side, then size and charge each kept trade.

    keep is a set of dates, or None for every date. not_before maps a date to the
    earliest allowed close minute (NIFTY's signal). Halves are of the sessions.
    """
    before, after = entry_window(rule["or_minutes"])
    last = flat_slot(tm)
    hist, trades = _collect_trades(tm, sessions, symbol, rule, last, side, before, after, keep, not_before)
    dates = [d for d, _bars in sessions]
    mid = len(dates) // 2
    first = set(dates[:mid])
    by_date = dict(sessions)
    rows = []
    for trade in trades:
        entry, stop = trade["entry"], trade["stop"]
        risk_ps = abs(_d(entry) - _d(stop))
        shares = whole_shares(entry, stop, risk, capital)
        bars = by_date[trade["date"]]
        exit_px = _exit(trade, bars[last]["c"])
        if side == "buy":
            gross = (_d(exit_px) - _d(entry)) * shares
        else:
            gross = (_d(entry) - _d(exit_px)) * shares
        cost = round_trip_for(side, entry, exit_px, shares)
        net = gross - cost
        denom = risk_ps * shares
        r_after = float(net / denom) if denom > 0 else trade["R"]
        entry_min = tm.parse_clock(trade["time"], "entry")
        entry_i = (entry_min - tm.OPEN_MIN) // 5 - 1
        rows.append({
            "date": trade["date"], "R": trade["R"], "R_after": r_after,
            "net": float(net), "half": "first" if trade["date"] in first else "second",
            "outcome": trade["outcome"], "shares": shares, "side": side,
            "symbol": symbol, "entry": entry, "entry_min": entry_min,
            "exit_min": _exit_minute(bars, entry_i, side, stop, trade["target"], last, tm),
        })
    return hist, rows


def cap_per_day(rows, limit):
    """The first `limit` entries of each day. Time first, then symbol. No look at the result."""
    if not limit:
        return rows
    ordered = sorted(rows, key=lambda row: (row["date"], row["entry_min"], row["symbol"], row["side"]))
    kept = []
    used = {}
    for row in ordered:
        n = used.get(row["date"], 0)
        if n >= limit:
            continue
        used[row["date"]] = n + 1
        kept.append(row)
    return kept


def position_stats(rows):
    """Average entry notional, and the most positions open at one time on any day.

    A position is open from its entry close until its exit close. When both fall
    on the same minute the exit is counted first, so the slot can be reused.
    """
    if not rows:
        return {"avg_rupees": None, "peak_open": 0}
    notionals = [float(_d(row["entry"]) * row["shares"]) for row in rows]
    by_date = {}
    for row in rows:
        by_date.setdefault(row["date"], []).append(row)
    peak = 0
    for day in by_date.values():
        events = []
        for row in day:
            events.append((row["entry_min"], 1))
            events.append((row["exit_min"], -1))
        events.sort()
        open_n = 0
        for _minute, delta in events:
            open_n += delta
            if open_n > peak:
                peak = open_n
    return {"avg_rupees": round(statistics.mean(notionals), 2), "peak_open": peak}


def _block(rows):
    n = len(rows)
    if not n:
        return {"trades": 0, "win_rate": None, "avg_R": None, "avg_R_after_costs": None, "rupees": 0.0}
    wins = sum(1 for row in rows if row["R"] > 0)
    return {
        "trades": n,
        "win_rate": round(wins / float(n), 4),
        "avg_R": round(statistics.mean(row["R"] for row in rows), 3),
        "avg_R_after_costs": round(statistics.mean(row["R_after"] for row in rows), 3),
        "rupees": round(sum(row["net"] for row in rows), 2),
    }


def summarize(rows):
    return {
        "all": _block(rows),
        "first_half": _block([row for row in rows if row["half"] == "first"]),
        "second_half": _block([row for row in rows if row["half"] == "second"]),
    }


def _signed(value):
    if value is None:
        return "n/a"
    return "%+.3f" % value


def judge(rule):
    """PASS only when every mark holds. The reasons are the marks that failed.

    trades >= 100, average R after costs >= +0.10, both halves > 0 after costs,
    and after-cost average R > 0 on at least 60% of the stocks that traded.
    """
    reasons = []
    block = rule["combined"]["all"]
    first = rule["combined"]["first_half"]["avg_R_after_costs"]
    second = rule["combined"]["second_half"]["avg_R_after_costs"]
    net = block["avg_R_after_costs"]
    if block["trades"] < 100:
        reasons.append("trades %d < 100" % block["trades"])
    if net is None or net < 0.10:
        reasons.append("average R after costs %s < +0.10" % _signed(net))
    if first is None or not first > 0:
        reasons.append("first half %s is not above 0 after costs" % _signed(first))
    if second is None or not second > 0:
        reasons.append("second half %s is not above 0 after costs" % _signed(second))
    traded = []
    for item in rule["symbols"].values():
        one = item["summary"]["all"]
        if one["trades"] > 0:
            traded.append(one["avg_R_after_costs"])
    if not traded:
        reasons.append("no stock traded")
    else:
        winners = sum(1 for value in traded if value is not None and value > 0)
        if winners * 5 < len(traded) * 3:
            reasons.append("after-cost R > 0 on %d of %d stocks (%.1f%%), need 60%%" % (
                winners, len(traded), 100.0 * winners / len(traded)))
    return {"result": "PASS" if not reasons else "FAIL", "reasons": reasons}


def history_from(rows):
    n = len(rows)
    if not n:
        return {"triggered": 0, "target": 0, "stop": 0, "close": 0, "avg_R": None}
    return {
        "triggered": n,
        "target": sum(1 for row in rows if row["outcome"] == "target"),
        "stop": sum(1 for row in rows if row["outcome"] == "stop"),
        "close": sum(1 for row in rows if row["outcome"] == "close"),
        "avg_R": round(statistics.mean(row["R"] for row in rows), 3),
    }


def load_folder(folder, tm, symbols=None, before=None):
    """Every *.algotest.json in folder, non-recursive, sorted by symbol."""
    if not os.path.isdir(folder):
        raise BacktestError("no folder %s" % folder)
    paths = sorted(glob.glob(os.path.join(folder, "*.algotest.json")))
    if not paths:
        raise BacktestError("no .algotest.json files in %s" % folder)
    wanted = None
    if symbols:
        wanted = set(s.strip().upper() for s in symbols if s.strip())
    loaded = []
    seen = set()
    for path in paths:
        sym, sessions, short = load_sessions(path, tm, before)
        if wanted is not None and sym not in wanted:
            continue
        if sym in seen:
            raise BacktestError("two files for %s" % sym)
        seen.add(sym)
        loaded.append({"symbol": sym, "path": path, "sessions": sessions, "short": short})
    if wanted is not None:
        missing = sorted(wanted - seen)
        if missing:
            raise BacktestError("no file for %s" % ", ".join(missing))
    if not loaded:
        raise BacktestError("no symbols to run")
    loaded.sort(key=lambda item: item["symbol"])
    return loaded


def run_loaded(loaded, tm, risk=500, capital=100000, side="buy", filters=None,
               market_sessions=None, ruleset=None, before=None, folder=None, market=None,
               max_trades_per_day=None):
    """Score an already loaded folder. filters is a list without 'none'."""
    filters = list(filters or [])
    if "market" in filters and not market_sessions:
        raise BacktestError("--filter market needs --market FILE")
    if max_trades_per_day is not None and max_trades_per_day < 1:
        raise BacktestError("--max-trades-per-day must be at least 1")
    sides = sides_of(side)
    skipped = 0
    if "inplay" in filters:
        skipped = sum(min(INPLAY_WARMUP, len(item["sessions"])) for item in loaded)
    report_rules = []
    for rule in (ruleset if ruleset is not None else rules()):
        bias = bias_by_date(market_sessions, rule["or_minutes"], tm) if market_sessions else {}
        pooled = []
        for item in loaded:
            for one in sides:
                keep = None
                not_before = None
                if filters:
                    keep, _skip = dates_for(item["sessions"], one, filters, rule["or_minutes"], bias)
                if "market" in filters:
                    not_before = {}
                    for date, signal in bias.items():
                        if _side_of(signal) == one and isinstance(signal, tuple) and signal[1] is not None:
                            not_before[date] = signal[1]
                _hist, part = score_symbol(
                    tm, item["sessions"], item["symbol"], rule, risk, capital, one, keep, not_before)
                pooled.extend(part)
        combined_rows = cap_per_day(pooled, max_trades_per_day)
        by_symbol = {}
        for row in combined_rows:
            by_symbol.setdefault(row["symbol"], []).append(row)
        per_symbol = {}
        for item in loaded:
            rows = by_symbol.get(item["symbol"], [])
            per_symbol[item["symbol"]] = {
                "sessions": len(item["sessions"]),
                "short_sessions": len(item["short"]),
                "history": history_from(rows),
                "summary": summarize(rows),
            }
        built = {
            "or_minutes": rule["or_minutes"], "stop": rule["stop"], "target_r": rule["target_r"],
            "name": rule_name(rule), "symbols": per_symbol, "combined": summarize(combined_rows),
            "positions": position_stats(combined_rows),
        }
        built["pass"] = judge(built)
        report_rules.append(built)
    report_rules.sort(key=lambda item: (item["combined"]["all"]["avg_R_after_costs"] is None,
                                        -(item["combined"]["all"]["avg_R_after_costs"] or 0)))
    return {
        "created_by": "india/backtest",
        "folder": os.path.abspath(folder) if folder else None,
        "risk": risk, "capital": capital, "before": before,
        "side": side, "filters": filters or ["none"],
        "market": os.path.abspath(market) if market else None,
        "max_trades_per_day": max_trades_per_day,
        "inplay_skipped": skipped,
        "symbols": [item["symbol"] for item in loaded],
        "costs": dict((k, str(v)) for k, v in costs.RATES.items()),
        "rules": report_rules,
    }


def run_folder(folder, risk=500, capital=100000, symbols=None, before=None,
               side="buy", filters=None, market=None, ruleset=None, max_trades_per_day=None, tm=None):
    """Every *.algotest.json in folder -> the report dict (rules sorted by net R)."""
    tm = tm or load_timemachine()
    filters = list(filters or [])
    loaded = load_folder(folder, tm, symbols, before)
    market_sessions = None
    if "market" in filters:
        if not market:
            raise BacktestError("--filter market needs --market FILE")
        _sym, market_sessions, _short = load_sessions(market, tm, before)
    return run_loaded(loaded, tm, risk, capital, side, filters, market_sessions,
                      ruleset, before, folder, market, max_trades_per_day)


def _pct(rate):
    if rate is None:
        return "   n/a"
    return "%5.1f%%" % (100.0 * rate)


def _num(x, width, places):
    if x is None:
        return "n/a".rjust(width)
    return ("%+.*f" % (places, x)).rjust(width)


def _rs(x, width):
    return format(x, ",.2f").rjust(width)


def _line(label, block):
    return "  %-16s %5d  %s  %s  %s  %s" % (
        label, block["trades"], _pct(block["win_rate"]), _num(block["avg_R"], 7, 3),
        _num(block["avg_R_after_costs"], 7, 3), _rs(block["rupees"], 12))


def _pass_line(check):
    if check["result"] == "PASS":
        return "  PASS"
    return "  FAIL: %s" % "; ".join(check["reasons"])


def _position_line(stats):
    stats = stats or {"avg_rupees": None, "peak_open": 0}
    if stats["avg_rupees"] is None:
        avg = "n/a"
    else:
        avg = format(stats["avg_rupees"], ",.2f")
    return "  positions: average Rs %s, peak open %d" % (avg, stats["peak_open"])


def _side_text(side):
    return {"buy": "long only", "sell": "short only", "both": "long and short"}[side]


def table(report, summary=False):
    """Plain lines. summary keeps the ALL block and its pass check."""
    filters = report.get("filters") or ["none"]
    lines = [
        "Opening-range breakout, %s. Entry 09:30 (or the end of the range) to 14:30, flat by 15:10."
        % _side_text(report.get("side") or "buy"),
        "Filters: %s. Risk Rs %s a trade, position cap Rs %s. Win rate is trades with R > 0 before costs."
        % (", ".join(filters), format(report["risk"], ",.0f"), format(report["capital"], ",.0f")),
        "  %-16s %5s  %6s  %7s  %7s  %12s" % ("", "n", "win", "R", "net R", "rupees"),
    ]
    if "inplay" in filters:
        lines.append("In play skipped the first %d sessions of each stock (%d sessions)." % (
            INPLAY_WARMUP, report.get("inplay_skipped") or 0))
    if report.get("max_trades_per_day"):
        lines.append("At most %d entries a day, the earliest first, ties broken by symbol." % (
            report["max_trades_per_day"],))
    sections = [("ALL", None)]
    if not summary:
        sections += [(sym, sym) for sym in report["symbols"]]
    for title, sym in sections:
        if sym is None:
            sessions = 0
            if report["rules"]:
                sessions = sum(item["sessions"] for item in report["rules"][0]["symbols"].values())
            lines.append("")
            lines.append("%s  (%d full sessions)" % (title, sessions))
        else:
            info = report["rules"][0]["symbols"][sym] if report["rules"] else {"sessions": 0, "short_sessions": 0}
            lines.append("")
            lines.append("%s  (%d full sessions, %d short left out)" % (
                title, info["sessions"], info["short_sessions"]))
        for rule in report["rules"]:
            block = rule["combined"] if sym is None else rule["symbols"][sym]["summary"]
            lines.append(_line(rule["name"], block["all"]))
            lines.append(_line("first half", block["first_half"]))
            lines.append(_line("second half", block["second_half"]))
            if sym is None:
                lines.append(_position_line(rule.get("positions")))
                lines.append(_pass_line(rule["pass"]))
    return lines


def write_report(path, report):
    folder = os.path.dirname(path)
    if folder:
        os.makedirs(folder, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2)
        fh.write("\n")


def main(argv=None):
    p = argparse.ArgumentParser(description="Backtest the opening-range rules on AlgoTest 5-minute files.")
    p.add_argument("folder", help="folder of *.algotest.json files")
    p.add_argument("--risk", type=float, default=500, help="rupees risked per trade (default 500)")
    p.add_argument("--capital", type=float, default=100000, help="max position in rupees (default 100000)")
    p.add_argument("--symbols", help="comma-separated tickers to keep, e.g. RELIANCE,TCS")
    p.add_argument("--before", help="use only sessions strictly before this YYYY-MM-DD")
    p.add_argument("--side", choices=SIDES, default="buy", help="buy, sell, or both (default buy)")
    p.add_argument("--filter", default="none",
                   help="none, inplay, market, or a comma list such as inplay,market")
    p.add_argument("--market", help="AlgoTest NIFTY file used when the filter includes market")
    p.add_argument("--max-trades-per-day", type=int, default=None,
                   help="take only the first N entries of each day, across all stocks")
    p.add_argument("--summary", action="store_true",
                   help="print only the ALL block and the pass check")
    p.add_argument("--write", default=os.path.join("trader", "backtest.json"),
                   help="where to write the JSON (default trader/backtest.json)")
    args = p.parse_args(argv)
    if args.risk <= 0 or args.capital <= 0:
        print("backtest.py: --risk and --capital must be above 0", file=sys.stderr)
        return 1
    symbols = args.symbols.split(",") if args.symbols else None
    try:
        filters = parse_filters(args.filter)
        report = run_folder(args.folder, args.risk, args.capital, symbols, args.before,
                            args.side, filters, args.market,
                            max_trades_per_day=args.max_trades_per_day)
        write_report(args.write, report)
    except (OSError, ValueError, BacktestError, algotest_to_yahoo.ConvertError) as e:
        print("backtest.py: %s" % e, file=sys.stderr)
        return 1
    print("\n".join(table(report, args.summary)))
    print("Wrote %s." % args.write)
    return 0


if __name__ == "__main__":
    sys.exit(main())
