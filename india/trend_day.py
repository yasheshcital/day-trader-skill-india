#!/usr/bin/env python3
"""Paper runner for the trend-day rule. Standard library only. Nothing is placed.

The rule is attempt 7: a 30-minute opening range, NIFTY's first close beyond
its own range at or before 10:00, and a stock entry on the first close beyond
its own range in that direction at or after NIFTY's signal and by 14:30.
Stop at the range midpoint, target 2R, flat at 15:10. Costs come from india/costs.py.

    python3 india/trend_day.py signals tests/fixtures/india/nifty50 \
        --market tests/fixtures/india/NIFTY-2026-08-05_2026-11-03-5m.algotest.json --now 15:10
    python3 india/trend_day.py close tests/fixtures/india/nifty50 \
        --market tests/fixtures/india/NIFTY-2026-08-05_2026-11-03-5m.algotest.json --date 2026-10-23
    python3 india/trend_day.py report

Sizing is a day risk of Rs 6,000 split into 35 equal slices, position cap Rs 5,00,000.
"""

import argparse
import csv
import datetime
import os
import statistics
import sys
from decimal import Decimal

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from india import backtest
from india import costs

OR_MINUTES = 30
SIGNAL_BY = 10 * 60
DAY_RISK = 6000
EXPECTED_ENTRIES = 35
CAPITAL = 500000
RULE = {"or_minutes": OR_MINUTES, "stop": "or_mid", "target_r": 2.0}
LOG_FIELDS = ["date", "symbol", "side", "time", "entry", "stop", "target", "shares", "R", "net_R", "rupees"]
DEFAULT_LOG = os.path.join("trader", "paper_log.csv")
FORWARD_DAYS = 30


class TrendError(Exception):
    pass


def ist_now():
    """Naive IST. Python 3.8 has no zoneinfo, so UTC plus 5 hours 30 minutes."""
    return datetime.datetime.utcnow() + datetime.timedelta(hours=5, minutes=30)


def slice_risk():
    return backtest._d(DAY_RISK) / Decimal(EXPECTED_ENTRIES)


def _session(sessions, date):
    for day, bars in sessions:
        if day == date:
            return bars
    return None


def _closed(bars, tm, now_min):
    """Bars whose close is at or before now_min. A bar still forming is left out."""
    out = []
    for i, bar in enumerate(bars):
        if tm.OPEN_MIN + 5 * (i + 1) <= now_min:
            out.append(bar)
        else:
            break
    return out


def _pad(bars, tm):
    """history_replay reads the flat-by bar. Repeat the last close so a short morning still runs."""
    last = backtest.flat_slot(tm)
    if len(bars) > last:
        return bars
    if not bars:
        return bars
    fill = {"o": bars[-1]["c"], "h": bars[-1]["c"], "l": bars[-1]["c"], "c": bars[-1]["c"], "v": 0}
    return list(bars) + [dict(fill) for _ in range(last + 1 - len(bars))]


def trend_signal(nifty_bars, tm, now_min):
    """(side, close minute) when NIFTY has closed beyond its 30m range by 10:00, else (None, None)."""
    closed = _closed(nifty_bars, tm, now_min)
    if len(closed) <= OR_MINUTES // 5:
        return None, None
    side, minute = backtest.market_bias(closed, OR_MINUTES, tm)
    if not side or minute is None or minute > SIGNAL_BY or minute > now_min:
        return None, None
    return side, minute


def _candidates(loaded, tm, date, now_min, side, minute):
    before, after = backtest.entry_window(OR_MINUTES)
    after = min(after, now_min)
    last = backtest.flat_slot(tm)
    risk = slice_risk()
    rows = []
    need = OR_MINUTES // 5
    for item in loaded:
        raw = _session(item["sessions"], date)
        if not raw:
            continue
        closed = _closed(raw, tm, now_min)
        if len(closed) <= need:
            continue
        bars = _pad(closed, tm)
        if len(bars) <= last:
            continue
        _hist, trades = backtest._collect_trades(
            tm, [(date, bars)], item["symbol"], RULE, last, side, before, after,
            {date}, {date: minute})
        for trade in trades:
            entry_min = tm.parse_clock(trade["time"], "entry")
            if entry_min > now_min:
                continue
            shares = backtest.whole_shares(trade["entry"], trade["stop"], risk, CAPITAL)
            rows.append({
                "date": date, "symbol": item["symbol"], "side": side, "time": trade["time"],
                "entry": trade["entry"], "stop": trade["stop"], "target": trade["target"],
                "shares": shares, "entry_min": entry_min,
            })
    kept, _ran = backtest.take_until_day_risk(rows, DAY_RISK, EXPECTED_ENTRIES)
    return kept


def _score_kept(loaded, tm, date, side, minute):
    """Full-day rows, same budget, with R and rupees filled by the backtest."""
    rows = []
    risk = slice_risk()
    for item in loaded:
        bars = _session(item["sessions"], date)
        if not bars:
            continue
        _hist, part = backtest.score_symbol(
            tm, [(date, bars)], item["symbol"], RULE, risk, CAPITAL, side,
            keep={date}, not_before={date: minute})
        rows.extend(part)
    kept, _ran = backtest.take_until_day_risk(rows, DAY_RISK, EXPECTED_ENTRIES)
    return kept


def read_log(path):
    if not path or not os.path.exists(path):
        return []
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def write_log(path, rows):
    folder = os.path.dirname(path)
    if folder:
        os.makedirs(folder, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=LOG_FIELDS, lineterminator="\n", extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(dict((key, row.get(key, "")) for key in LOG_FIELDS))


def _key(row):
    return (row["date"], row["symbol"], row["side"], row["time"])


def _px(value):
    return format(float(value), ".2f")


def _risk_rs(entry, stop, shares):
    return float(backtest._d(shares) * abs(backtest._d(entry) - backtest._d(stop)))


def _blank():
    return {"R": "", "net_R": "", "rupees": ""}


def signals_day(loaded, nifty_sessions, date, now_min, log_path, tm):
    """Lines for one date, and the log gains any new entries. Bars after now_min are ignored."""
    nifty = _session(nifty_sessions, date)
    if nifty is None:
        return ["%s: no NIFTY session." % date]
    side, minute = trend_signal(nifty, tm, now_min)
    if side is None:
        if now_min < SIGNAL_BY:
            return ["%s: no signal yet. Watching until 10:00." % date]
        return ["%s is not a trend day: no signal by 10:00: no trades today" % date]
    kept = _candidates(loaded, tm, date, now_min, side, minute)
    lines = ["%s is a trend day: %s, signal %s." % (date, side, tm.clock12(minute))]
    existing = read_log(log_path)
    seen = set(_key(row) for row in existing)
    added = 0
    for row in kept:
        lines.append("  %s  %s  %s  entry %s  stop %s  target %s  shares %d  risk Rs %s" % (
            row["time"], row["symbol"], row["side"], _px(row["entry"]), _px(row["stop"]),
            _px(row["target"]), row["shares"], format(_risk_rs(row["entry"], row["stop"], row["shares"]), ",.2f")))
        if _key(row) in seen:
            continue
        saved = {
            "date": date, "symbol": row["symbol"], "side": row["side"], "time": row["time"],
            "entry": _px(row["entry"]), "stop": _px(row["stop"]), "target": _px(row["target"]),
            "shares": str(row["shares"]),
        }
        saved.update(_blank())
        existing.append(saved)
        seen.add(_key(row))
        added += 1
    if kept:
        write_log(log_path, existing)
    if added:
        lines.append("Logged %d new entries." % added)
    elif kept:
        lines.append("No new entries.")
    else:
        lines.append("No stock entries yet.")
    return lines


def _settled(row):
    return row.get("R") not in (None, "")


def _exit_price(outcome, entry_stop, entry_target, bars, tm):
    if outcome == "target":
        return entry_target
    if outcome == "stop":
        return entry_stop
    return bars[backtest.flat_slot(tm)]["c"]


def _net_rupees(side, entry, exit_px, shares):
    """Gross points times shares, minus india/costs.py. A short buys to cover."""
    if side == "buy":
        gross = (backtest._d(exit_px) - backtest._d(entry)) * shares
        cost = costs.round_trip(entry, exit_px, shares)
    else:
        gross = (backtest._d(entry) - backtest._d(exit_px)) * shares
        cost = costs.round_trip(exit_px, entry, shares)
    return gross - cost


def close_day(loaded, nifty_sessions, date, log_path, tm, today=None, now=None):
    """Fill R, net R and net rupees for the logged trades. Refuses a same-day close before 15:10."""
    clock = now if now is not None else ist_now()
    today = today if today is not None else clock.date().isoformat()
    if date > today:
        raise TrendError("close cannot settle a future date")
    if date == today and (clock.hour * 60 + clock.minute) < tm.FLAT_BY_MIN:
        raise TrendError("close waits until 15:10 IST")
    rows = read_log(log_path)
    mine = [row for row in rows if row["date"] == date]
    if not mine:
        return ["%s: no trades logged." % date]
    nifty = _session(nifty_sessions, date)
    if nifty is None:
        raise TrendError("no NIFTY session on %s" % date)
    side, minute = trend_signal(nifty, tm, 15 * 60 + 30)
    if side is None:
        raise TrendError("%s was not a trend day" % date)
    scored = {}
    for row in _score_kept(loaded, tm, date, side, minute):
        scored[(row["symbol"], row["entry_min"])] = row
    by_symbol = dict((item["symbol"], item) for item in loaded)
    filled = 0
    for row in mine:
        entry_min = tm.parse_clock(row["time"], "entry")
        got = scored.get((row["symbol"], entry_min))
        bars = _session(by_symbol[row["symbol"]]["sessions"], date) if row["symbol"] in by_symbol else None
        if got is None or not bars:
            continue
        exit_px = _exit_price(got["outcome"], float(row["stop"]), float(row["target"]), bars, tm)
        net = _net_rupees(row["side"], got["entry"], exit_px, got["shares"])
        risk_ps = abs(backtest._d(got["entry"]) - backtest._d(row["stop"]))
        denom = risk_ps * got["shares"]
        r_after = float(net / denom) if denom > 0 else got["R"]
        row["R"] = format(got["R"], ".2f")
        row["net_R"] = format(r_after, ".6f")
        row["rupees"] = format(float(net), ".2f")
        filled += 1
    write_log(log_path, rows)
    return ["%s: filled %d trades." % (date, filled)]


def _f(row, key):
    try:
        return float(row[key])
    except (TypeError, ValueError):
        return None


def report_text(rows):
    """Forward-test lines. Unsettled trades are left out. Under 30 days stays IN PROGRESS."""
    settled = [row for row in rows if _settled(row)]
    by_date = {}
    by_symbol = {}
    for row in settled:
        by_date.setdefault(row["date"], []).append(row)
        by_symbol.setdefault(row["symbol"], []).append(row)
    days = sorted(by_date)
    n = len(days)
    trades = len(settled)
    lines = ["Qualifying days: %d" % n, "Trades: %d" % trades]
    if not trades:
        lines.append("IN PROGRESS: 0 of %d days" % FORWARD_DAYS)
        return lines
    avg_r = statistics.mean(_f(row, "R") for row in settled)
    avg_net = statistics.mean(_f(row, "net_R") for row in settled)
    daily = []
    wins = 0
    for date in days:
        rupees = sum(_f(row, "rupees") for row in by_date[date])
        daily.append(rupees)
        if rupees > 0:
            wins += 1
    rest = sum(daily) - sum(sorted(daily, reverse=True)[:2])
    positive = sum(1 for group in by_symbol.values() if sum(_f(row, "rupees") for row in group) > 0)
    win_share = wins / float(n)
    stock_share = positive / float(len(by_symbol))
    lines.append("Average R before costs: %+.3f" % avg_r)
    lines.append("Average R after costs: %+.3f" % avg_net)
    lines.append("Winning-day share: %.1f%%" % (100.0 * win_share))
    lines.append("Profit without the best 2 days: Rs %s" % format(rest, ",.2f"))
    lines.append("Stocks positive: %d of %d (%.1f%%)" % (positive, len(by_symbol), 100.0 * stock_share))
    if n < FORWARD_DAYS:
        lines.append("IN PROGRESS: %d of %d days" % (n, FORWARD_DAYS))
        return lines
    reasons = []
    if avg_net < 0.10:
        reasons.append("average R after costs %+.3f < +0.10" % avg_net)
    if not win_share > 0.55:
        reasons.append("winning days %.1f%%, need above 55%%" % (100.0 * win_share))
    if not rest > 0:
        reasons.append("not profitable without the best 2 days (Rs %s)" % format(rest, ",.2f"))
    if stock_share < 0.60:
        reasons.append("positive on %d of %d stocks (%.1f%%), need 60%%" % (
            positive, len(by_symbol), 100.0 * stock_share))
    lines.append("PASS" if not reasons else "FAIL: %s" % "; ".join(reasons))
    return lines


def main(argv=None):
    p = argparse.ArgumentParser(description="Paper-trade the trend-day rule. Nothing is placed.")
    sub = p.add_subparsers(dest="cmd")
    signals = sub.add_parser("signals", help="print today's entries from bars that have closed")
    signals.add_argument("folder")
    signals.add_argument("--market", required=True)
    signals.add_argument("--now", help="IST clock HH:MM. Default: the clock. Only closed bars count.")
    signals.add_argument("--date", help="session date YYYY-MM-DD. Default: today in IST.")
    signals.add_argument("--log", default=DEFAULT_LOG)
    close = sub.add_parser("close", help="fill outcomes for one logged day after 15:10")
    close.add_argument("folder")
    close.add_argument("--market", required=True)
    close.add_argument("--date", required=True)
    close.add_argument("--log", default=DEFAULT_LOG)
    report = sub.add_parser("report", help="forward test over the paper log")
    report.add_argument("--log", default=DEFAULT_LOG)
    args = p.parse_args(argv)
    if not args.cmd:
        p.print_help()
        return 2
    try:
        if args.cmd == "report":
            print("\n".join(report_text(read_log(args.log))))
            return 0
        tm = backtest.load_timemachine()
        loaded = backtest.load_folder(args.folder, tm)
        _sym, nifty, _short = backtest.load_sessions(args.market, tm)
        if args.cmd == "signals":
            clock = ist_now()
            date = args.date or clock.date().isoformat()
            now_min = backtest.parse_hhmm(args.now) if args.now else clock.hour * 60 + clock.minute
            print("\n".join(signals_day(loaded, nifty, date, now_min, args.log, tm)))
            return 0
        print("\n".join(close_day(loaded, nifty, args.date, args.log, tm)))
        return 0
    except (OSError, ValueError, backtest.BacktestError, TrendError) as exc:
        print("trend_day.py: %s" % exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
