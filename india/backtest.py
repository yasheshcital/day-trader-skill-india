#!/usr/bin/env python3
"""Batch backtest of the opening-range thesis. Standard library only.

Reads every AlgoTest 5-minute file in a folder, converts it in memory, and
replays trader-timemachine's own history_replay (loaded, not copied) on a
grid of rules. Long side only. Nothing is placed.

    python3 india/backtest.py tests/fixtures/india/stocks
    python3 india/backtest.py tests/fixtures/india/stocks --symbols RELIANCE,TCS --risk 500

Entry window: 09:30, or the end of the opening range when that is later, through
14:30. Flat by 15:10. Each trade risks --risk rupees (default 500) in whole
shares, and the position is capped at --capital (default 1,00,000). Costs come
from india/costs.py.
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
    """Shares that risk risk_rupees, then cut so the position fits in capital."""
    risk_ps = _d(entry) - _d(stop)
    if risk_ps <= 0 or _d(entry) <= 0:
        return 0
    n = int(_d(risk_rupees) // risk_ps)
    cap = int(_d(capital) // _d(entry))
    return max(0, min(n, cap))


def _sell(trade, close):
    if trade["outcome"] == "target":
        return trade["target"]
    if trade["outcome"] == "stop":
        return trade["stop"]
    return close


def score_symbol(tm, sessions, symbol, rule, risk, capital):
    """history_replay, then size and charge each trade. Halves are of the sessions."""
    before, after = entry_window(rule["or_minutes"])
    last = flat_slot(tm)
    hist = tm.history_replay(sessions, {
        "setup": "orb", "or_minutes": rule["or_minutes"], "stop_rule": rule["stop"],
        "target_r": rule["target_r"],
    }, last, "buy", before, after, symbol)
    dates = [d for d, _bars in sessions]
    mid = len(dates) // 2
    first = set(dates[:mid])
    by_date = dict(sessions)
    rows = []
    for trade in hist["trades"]:
        entry, stop = trade["entry"], trade["stop"]
        risk_ps = _d(entry) - _d(stop)
        shares = whole_shares(entry, stop, risk, capital)
        sell = _sell(trade, by_date[trade["date"]][last]["c"])
        gross = (_d(sell) - _d(entry)) * shares
        cost = costs.round_trip(entry, sell, shares)
        net = gross - cost
        denom = risk_ps * shares
        r_after = float(net / denom) if denom > 0 else trade["R"]
        rows.append({
            "date": trade["date"], "R": trade["R"], "R_after": r_after,
            "net": float(net), "half": "first" if trade["date"] in first else "second",
            "outcome": trade["outcome"], "shares": shares,
        })
    return hist, rows


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


def run_folder(folder, risk=500, capital=100000, symbols=None, before=None, tm=None):
    """Every *.algotest.json in folder -> the report dict (rules sorted by net R)."""
    if not os.path.isdir(folder):
        raise BacktestError("no folder %s" % folder)
    paths = sorted(glob.glob(os.path.join(folder, "*.algotest.json")))
    if not paths:
        raise BacktestError("no .algotest.json files in %s" % folder)
    tm = tm or load_timemachine()
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
    report_rules = []
    for rule in rules():
        per_symbol = {}
        combined_rows = []
        for item in loaded:
            hist, rows = score_symbol(tm, item["sessions"], item["symbol"], rule, risk, capital)
            per_symbol[item["symbol"]] = {
                "sessions": len(item["sessions"]),
                "short_sessions": len(item["short"]),
                "history": {"triggered": hist["triggered"], "target": hist["target"],
                            "stop": hist["stop"], "close": hist["close"], "avg_R": hist["avg_R"]},
                "summary": summarize(rows),
            }
            combined_rows.extend(rows)
        report_rules.append({
            "or_minutes": rule["or_minutes"], "stop": rule["stop"], "target_r": rule["target_r"],
            "name": rule_name(rule), "symbols": per_symbol, "combined": summarize(combined_rows),
        })
    report_rules.sort(key=lambda item: (item["combined"]["all"]["avg_R_after_costs"] is None,
                                        -(item["combined"]["all"]["avg_R_after_costs"] or 0)))
    return {
        "created_by": "india/backtest",
        "folder": os.path.abspath(folder),
        "risk": risk, "capital": capital, "before": before,
        "symbols": [item["symbol"] for item in loaded],
        "costs": dict((k, str(v)) for k, v in costs.RATES.items()),
        "rules": report_rules,
    }


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


def table(report):
    """Plain lines: combined first, then each stock, rules sorted by net R."""
    lines = [
        "Opening-range breakout, long only. Entry 09:30 (or the end of the range) to 14:30, flat by 15:10.",
        "Risk Rs %s a trade, position cap Rs %s. Win rate is trades with R > 0 before costs."
        % (format(report["risk"], ",.0f"), format(report["capital"], ",.0f")),
        "  %-16s %5s  %6s  %7s  %7s  %12s" % ("", "n", "win", "R", "net R", "rupees"),
    ]
    sections = [("ALL", None)] + [(sym, sym) for sym in report["symbols"]]
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
    p.add_argument("--write", default=os.path.join("trader", "backtest.json"),
                   help="where to write the JSON (default trader/backtest.json)")
    args = p.parse_args(argv)
    if args.risk <= 0 or args.capital <= 0:
        print("backtest.py: --risk and --capital must be above 0", file=sys.stderr)
        return 1
    symbols = args.symbols.split(",") if args.symbols else None
    try:
        report = run_folder(args.folder, args.risk, args.capital, symbols, args.before)
        write_report(args.write, report)
    except (OSError, ValueError, BacktestError, algotest_to_yahoo.ConvertError) as e:
        print("backtest.py: %s" % e, file=sys.stderr)
        return 1
    print("\n".join(table(report)))
    print("Wrote %s." % args.write)
    return 0


if __name__ == "__main__":
    sys.exit(main())
