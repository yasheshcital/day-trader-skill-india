#!/usr/bin/env python3
"""Attempts 20 and 21. Rules are written before any backtest.

One logged load, and only after a variant passes. Nothing is ordered.
"""

import bisect
import csv
import datetime
import gzip
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from india import nse_market
from india.research import batch16 as b16
from india.research import batch18
from india.research import batch20
from india.research import data
from india.research import follow
from india.research import harness
from india.research import signal_lab as lab
from india.research import survivorship
from india.research import trend_day_study as trend

EXPERIMENTS = batch20.EXPERIMENTS
STRATEGIES = batch20.STRATEGIES
START = trend.START
END = trend.END
ENTRY_END = 13 * 60 + 30
EXIT_END = 15 * 60 + 20
WINDOW = 250
# 250 * 0.30 = 75. Index 74 is the 75th smallest, the top of the bottom 30 percent.
SMALL_AT = 74
FAMILY_EVENT = batch20.FAMILY
FAMILY_ORB = "opening-range breakout"
END_RULE = (
    "If no attempt 20 or 21 variant passes in-sample AND its holdout, "
    "intraday is Closed for good."
)


def rules_text(stamp):
    return """## Attempt 21

Rules fixed on %s, before the run.

21a, 21b and 21c use the attempt 8 pass mark. At least 100 trades. Average R after costs and 1 tick of slippage at least +0.10. The first half and the second half of the full 2015-2024 NIFTY session calendar both above 0 after costs. After-cost average R above 0 on at least 60 percent of the names that traded. A boundary stated with at least still passes. An empty book fails.

21a, FII flow filter. Names: fii orb A and fii orb B. The attempt 8 trend-day opening-range breakout, both universes, taken only in the direction of yesterday's change in the FII net index-futures position. Net is Future Index Long minus Future Index Short on the FII row of the participant-wise open-interest file. Yesterday is the latest file dated before the session. The change is that net minus the net on the previous file. Long when the change is positive. Short when it is negative. A change of zero is not a trade. Days whose absolute change sits in the smallest 30 percent of the last 250 absolute changes, ending at yesterday and including yesterday, are skipped. The cutoff is index 74 of the sorted window, the 75th smallest. A tie at the cutoff is skipped. Fewer than 250 changes and the day is skipped. Universe A is today's NIFTY 50 list and has survivorship bias. Universe B is the point-in-time top 100 by the previous 20 sessions of turnover.

21b, expiry-day afternoon. Name: nifty expiry afternoon. NIFTY futures, one lot of 75, on the NIFTY 50 5-minute series, because the continuous futures file is daily. Expiry days are the monthly and weekly dates in events.csv, together. Enter at the close of the bar ending 13:30, in the direction of that close minus the open of the bar ending 09:20 (the 09:15 price). A flat morning is not a trade. Exit is the close of the bar ending 15:20. There is no stop and no target. If the 13:30 bar or the 15:20 bar is missing, the day is not a trade. One tick of 0.05, from tick_for with the symbol NIFTY, on the entry and on the exit. Costs are the attempt 16 futures schedule, same day, so the rollover count is 0. R's denominator is the morning move times the lot, measured before the tick. R after subtracts the futures charges. The 60 percent clause is this one name.

21c, quiet-day skip. Names: quiet orb A and quiet orb B. The same attempt 8 rule on both universes, skipping a day where the India VIX close known before 09:15 (yesterday's close) is in its lowest 30 percent of the last 250 closes. The window ends at yesterday and includes yesterday. The cutoff is index 74 of the sorted window. A tie at the cutoff is skipped. Fewer than 250 closes leaves the clause off, so the day is not skipped for lack of history.

Family. 21a and 21c are the opening-range breakout family. 21b is the event days family. The holdout is one logged load of the NIFTY 50 daily file, shared with attempt 20, and only when a variant has passed in sample. Other reads in that block do not log. Holdout pass is average R after costs above 0 and the monthly t of that R above 2. The 100-trade clause and the 60 percent clause are not applied on the short holdout.

%s
""" % (stamp.isoformat(), END_RULE)


def write_rules(path, stamp):
    follow.install_attempt(path, 21, rules_text(stamp), [])


def direction_of(change):
    """buy when FII net rose, sell when it fell. Zero and missing are neither."""
    if change is None or change == 0:
        return None
    if change > 0:
        return "buy"
    return "sell"


def is_small(sizes):
    """True when the last absolute change is in the smallest 30 percent."""
    if len(sizes) < WINDOW:
        return True
    window = sizes[-WINDOW:]
    cutoff = sorted(window)[SMALL_AT]
    return window[-1] <= cutoff


def fii_take(side, change, sizes):
    """True when the attempt 8 side matches the FII change and the day is not small."""
    if is_small(sizes):
        return False
    want = direction_of(change)
    return want is not None and side == want


def vix_bottom30(values):
    """True when the last close is in the lowest 30 percent of these 250 closes."""
    if len(values) < WINDOW:
        return False
    window = values[-WINDOW:]
    cutoff = sorted(window)[SMALL_AT]
    return window[-1] <= cutoff


def _fii_net(path):
    with gzip.open(path, "rt", encoding="utf-8", newline="") as fh:
        reader = csv.reader(fh)
        header = None
        for raw in reader:
            cells = [cell.strip() for cell in raw]
            if cells and cells[0] == "Client Type":
                header = cells
                break
        if header is None:
            return None
        try:
            long_i = header.index("Future Index Long")
            short_i = header.index("Future Index Short")
        except ValueError:
            return None
        for raw in reader:
            if not raw or raw[0].strip() != "FII":
                continue
            try:
                return float(raw[long_i]) - float(raw[short_i])
            except (ValueError, IndexError):
                return None
    return None


def load_fii(folder):
    """(date, net) oldest first. Net is index-futures long minus short."""
    found = []
    if not folder or not os.path.isdir(folder):
        return found
    for name in sorted(os.listdir(folder)):
        if not name.endswith(".csv.gz") or len(name) < 10:
            continue
        try:
            day = datetime.date.fromisoformat(name[:10])
        except ValueError:
            continue
        net = _fii_net(os.path.join(folder, name))
        if net is None:
            continue
        found.append((day, net))
    found.sort()
    return found


def change_table(nets):
    """Parallel lists: date of the later file, change, absolute change."""
    dates = []
    changes = []
    sizes = []
    for i in range(1, len(nets)):
        change = nets[i][1] - nets[i - 1][1]
        dates.append(nets[i][0])
        changes.append(change)
        sizes.append(abs(change))
    return dates, changes, sizes


def window_before(dates, changes, sizes, day):
    """Yesterday's change, and the absolute changes ending at yesterday."""
    i = bisect.bisect_left(dates, day) - 1
    if i < 0:
        return None, []
    start = 0 if i + 1 <= WINDOW else i + 1 - WINDOW
    return changes[i], sizes[start:i + 1]


def allowed_days(signals, dates, changes, sizes):
    kept = set()
    for day, signal in signals.items():
        change, window = window_before(dates, changes, sizes, day)
        if fii_take(signal[0], change, window):
            kept.add(day)
    return kept


def quiet_days(calendar, vix_dates, vix_closes):
    """Days that are NOT in the lowest 30 percent, so the ORB may run."""
    kept = set()
    for day in calendar:
        if vix_bottom30(batch20.vix_into(vix_dates, vix_closes, day)):
            continue
        kept.add(day)
    return kept


def _book(name, kind, trades, first):
    verdict = trend.judge(trades, first)
    winners, names = batch20._stock_share(trades)
    return {
        "name": name,
        "kind": kind,
        "trades_n": len(trades),
        "avg": batch20._mean([trade["r_after"] for trade in trades]),
        "t": None,
        "first": verdict.get("first_half"),
        "second": verdict.get("second_half"),
        "winners": winners,
        "names": names,
        "verdict": {"result": verdict["result"], "reasons": verdict["reasons"]},
        "rows": trades,
        "compare": False,
    }


def _emit_book(block, emit):
    emit("%s %s n %d avg %s" % (
        block["name"], block["verdict"]["result"], block["trades_n"],
        harness._r(block["avg"])))


def score_filters(signals, calendar, current, liquid, fii, vix_dates, vix_closes, emit):
    dates, changes, sizes = fii
    first = batch20._half_dates(calendar)
    take = allowed_days(signals, dates, changes, sizes)
    quiet = quiet_days(calendar, vix_dates, vix_closes)
    emit("fii days %d, quiet days %d" % (len(take), len(quiet)))
    blocks = []
    specs = (
        ("fii orb A", "fii", current, take),
        ("fii orb B", "fii", liquid, take),
        ("quiet orb A", "quiet", current, quiet),
        ("quiet orb B", "quiet", liquid, quiet),
    )
    for name, kind, trades, days in specs:
        chosen = [trade for trade in trades if trade["date"] in days]
        block = _book(name, kind, chosen, first)
        blocks.append(block)
        _emit_book(block, emit)
    return blocks


def afternoon_trade(session):
    """13:30 entry, 15:20 exit, R in units of the morning move. One NIFTY lot."""
    origin = trend.locate(session)
    if origin is None:
        return None
    ends = session["end"]
    entry_i = None
    exit_i = None
    for i, minute in enumerate(ends):
        if minute == ENTRY_END:
            entry_i = i
        elif minute == EXIT_END:
            exit_i = i
    if entry_i is None or exit_i is None or not exit_i > entry_i:
        return None
    opened = session["open"][origin]
    raw = session["close"][entry_i]
    risk = abs(raw - opened)
    if not risk > 0 or not raw > 0 or not opened > 0:
        return None
    long = raw > opened
    tick = nse_market.tick_for(raw, "NIFTY")
    if not tick > 0:
        return None
    fill_entry = raw + tick if long else raw - tick
    exit_px = session["close"][exit_i]
    exit_tick = nse_market.tick_for(exit_px, "NIFTY")
    if not exit_tick > 0:
        exit_tick = tick
    fill_exit = exit_px - exit_tick if long else exit_px + exit_tick
    if not fill_entry > 0 or not fill_exit > 0:
        return None
    lot = harness.NIFTY_LOT
    if long:
        pnl = (fill_exit - fill_entry) * lot
        cost = b16.futures_side(fill_entry * lot, True) + b16.futures_side(fill_exit * lot, False)
    else:
        pnl = (fill_entry - fill_exit) * lot
        cost = b16.futures_side(fill_exit * lot, True) + b16.futures_side(fill_entry * lot, False)
    denom = risk * lot
    if not denom > 0:
        return None
    return {
        "symbol": "NIFTY",
        "r_before": pnl / denom,
        "r_after": (pnl - cost) / denom,
    }


def expiry_dates(event_rows, start, end):
    found = set()
    for row in event_rows:
        if row["kind"] not in ("expiry-monthly", "expiry-weekly"):
            continue
        if row["date"] < start or row["date"] > end:
            continue
        found.add(row["date"])
    return found


def score_afternoon(root, event_rows, start, end, calendar, guard, emit):
    expiry = expiry_dates(event_rows, start, end)
    sessions = batch20._load_map(root, trend.NIFTY, start, end, guard)
    trades = []
    for day in sorted(sessions):
        if day < start or day > end or day not in expiry:
            continue
        trade = afternoon_trade(sessions[day])
        if trade is None:
            continue
        trade["date"] = day
        trades.append(trade)
    first = batch20._half_dates(calendar)
    block = _book("nifty expiry afternoon", "afternoon", trades, first)
    emit("expiry afternoons in the window: %d" % len(expiry))
    _emit_book(block, emit)
    return block


def _attach(block, found, kind):
    if kind == "expiry":
        avg = found["avg"]
        tee = found["t"]
        hold = batch20.judge_holdout_pair(avg, tee)
        block["holdout"] = {
            "avg": avg, "t": tee, "trades": found["trades_n"], "verdict": hold,
        }
        return
    if kind == "results":
        avg = found["avg"]
        tee = found["t"]
        hold = batch20.judge_holdout_pair(avg, tee)
        block["holdout"] = {
            "avg": avg, "t": tee, "trades": found["trades_n"], "verdict": hold,
        }
        return
    tee = batch18.monthly_t(found["rows"], "r_after")
    hold = batch20.judge_holdout_pair(found["avg"], tee)
    block["holdout"] = {
        "avg": found["avg"], "t": tee, "trades": found["trades_n"], "verdict": hold,
    }


def _find(blocks, name):
    for item in blocks:
        if item["name"] == name:
            return item
    return None


def run_holdout(root, nse, blocks20, blocks21, ctx, fii, emit):
    """The only logged load. Called after an in-sample pass."""
    _first, last = survivorship.raw_span(data.bar_path(root, "day", lab.NIFTY))
    emit("holdout %s to %s" % (data.HOLDOUT_START.isoformat(), last.isoformat()))
    segments = lab.load_symbol(root, lab.NIFTY, end=last, final=True)
    regimes = batch20._holdout_regimes(segments)
    begin = data.HOLDOUT_START
    event_rows = ctx["events"]
    want = []
    for block in blocks20 + blocks21:
        if block.get("compare"):
            continue
        if block["verdict"]["result"] == "PASS":
            want.append(block)
    need = set(block["kind"] for block in want)
    expiry_done = None
    results_done = None
    orb = None
    if "expiry" in need:
        expiry_done = batch20.score_expiry(
            root, event_rows, begin, last, regimes, False, emit)
    if "results" in need:
        books = batch20._books(root, last, False)
        results_done = batch20.score_results(
            root, event_rows, begin, last, regimes, books, False, emit)
    if need.intersection(("macro", "switch", "fii", "quiet")):
        calendar, signals, _reg, _books, current, liquid = batch20.score_orb(
            root, begin, last, False, emit)
        switched = batch20.score_switches(
            calendar, current, liquid, event_rows,
            ctx["vix_dates"], ctx["vix_closes"], emit)
        filtered = score_filters(
            signals, calendar, current, liquid, fii,
            ctx["vix_dates"], ctx["vix_closes"], emit)
        orb = {"switch": switched, "filter": filtered, "calendar": calendar}
    afternoon_done = None
    if "afternoon" in need:
        calendar = ctx["calendar"]
        if orb is not None:
            calendar = orb["calendar"]
        afternoon_done = score_afternoon(
            root, event_rows, begin, last, calendar, False, emit)
    for block in want:
        kind = block["kind"]
        found = None
        if kind == "expiry" and expiry_done is not None:
            found = _find(expiry_done, block["name"])
        elif kind == "results" and results_done is not None:
            found = _find(results_done, block["name"])
        elif kind in ("macro", "switch") and orb is not None:
            found = _find(orb["switch"], block["name"])
        elif kind in ("fii", "quiet") and orb is not None:
            found = _find(orb["filter"], block["name"])
        elif kind == "afternoon" and afternoon_done is not None:
            found = afternoon_done
        if found is None:
            continue
        _attach(block, found, kind)
        hold = block["holdout"]
        shown = harness._pct(hold["avg"]) if kind == "expiry" else harness._r(hold["avg"])
        emit("holdout %s %s n %s avg %s t %s" % (
            block["name"], hold["verdict"]["result"], hold["trades"],
            shown, harness._num(hold["t"])))
    return last


def conclusion(blocks):
    cleared = []
    for block in blocks:
        if block.get("compare"):
            continue
        if block["verdict"]["result"] != "PASS":
            continue
        hold = block.get("holdout") or {}
        verdict = (hold.get("verdict") or {}).get("result")
        if verdict == "PASS":
            cleared.append(block["name"])
    if cleared:
        return "Intraday stays open. Passed in sample and on the holdout: %s." % ", ".join(cleared)
    return "Intraday is Closed for good."


def _line(name, cells):
    return name + " | " + " | ".join(cells)


def _report(stamp, blocks, holdout_ran, last, strategies, closing):
    lines = [rules_text(stamp).rstrip(), "", "Results.", ""]
    lines.append("name | n | avg R | first half | second half | stocks above 0 | result")
    for block in blocks:
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
        if hold and last is not None:
            lines.append("  holdout %s to %s %s n %s avg %s t %s" % (
                data.HOLDOUT_START.isoformat(), last.isoformat(),
                hold["verdict"]["result"], format(hold["trades"], ",d"),
                harness._r(hold["avg"]), harness._num(hold["t"])))
    if not holdout_ran:
        lines.append("")
        lines.append("No attempt 21 variant passed. Its holdout rows were not opened.")
    lines.append("")
    lines.append(closing)
    lines.append("")
    lines.append(batch18.bucket_line(strategies))
    lines.append("")
    return "\n".join(lines)


def _summary_rows(stamp, blocks, last):
    rows = []
    window = "%s to %s" % (START.isoformat(), END.isoformat())
    hold_window = "%s to %s" % (data.HOLDOUT_START.isoformat(), last.isoformat() if last else "")
    for block in blocks:
        rows.append("| 21 | %s | %s. | attempt 21, rules fixed before the run | %s | %s | %s | %s | %s |" % (
            stamp.isoformat(), block["name"], window,
            format(block["trades_n"], ",d"), harness._r(block["avg"]),
            harness._num(block["t"]), block["verdict"]["result"]))
        hold = block.get("holdout")
        if not hold:
            continue
        rows.append("| 21 | %s | holdout %s. | same rule, one logged load | %s | %s | %s | %s | %s |" % (
            stamp.isoformat(), block["name"], hold_window,
            format(hold["trades"], ",d"), harness._r(hold["avg"]),
            harness._num(hold["t"]), hold["verdict"]["result"]))
    return rows


def main(argv=None, log=None):
    import argparse
    parser = argparse.ArgumentParser(description="Attempts 20 and 21. Nothing is ordered.")
    parser.add_argument("--root", default=os.path.join("data", "kite"))
    parser.add_argument("--nse", default=os.path.join("data", "nse"))
    parser.add_argument("--experiments", default=EXPERIMENTS)
    parser.add_argument("--strategies", default=STRATEGIES)
    args = parser.parse_args(argv)
    emit = log or (lambda line: print(line, flush=True))
    stamp = datetime.date.today()
    batch20.write_rules(args.experiments, stamp)
    write_rules(args.experiments, stamp)
    batch20.ensure_family(args.strategies)
    emit("rules for attempts 20 and 21 written to %s before the run" % args.experiments)
    path = os.path.join(args.nse, "events.csv")
    if not os.path.isfile(path):
        emit("events.csv is missing; expiry dates are not invented")
        return 1
    blocks20, ctx = batch20.in_sample(args.root, args.nse, emit)
    nets = load_fii(os.path.join(args.nse, "participant"))
    emit("fii files %d" % len(nets))
    fii = change_table(nets)
    blocks21 = score_filters(
        ctx["signals"], ctx["calendar"], ctx["current"], ctx["liquid"], fii,
        ctx["vix_dates"], ctx["vix_closes"], emit)
    blocks21.append(score_afternoon(
        args.root, ctx["events"], START, END, ctx["calendar"], True, emit))
    passed20 = [block for block in blocks20 if block["verdict"]["result"] == "PASS" and not block.get("compare")]
    passed21 = [block for block in blocks21 if block["verdict"]["result"] == "PASS"]
    last = None
    looked = []
    if passed20 or passed21:
        last = run_holdout(args.root, args.nse, blocks20, blocks21, ctx, fii, emit)
        # Attempt 20 is the event-days family. 21b is the same family.
        # 21a and 21c are the opening-range breakout family.
        if passed20 or any(block["kind"] == "afternoon" for block in passed21):
            looked.append(FAMILY_EVENT)
        if any(block["kind"] in ("fii", "quiet") for block in passed21):
            looked.append(FAMILY_ORB)
    else:
        emit("no variant passed; holdout was not opened")
    batch20.finish_catalogue(args.strategies, blocks20, [
        name for name in looked if name == FAMILY_EVENT])
    batch20.finish_catalogue(args.strategies, blocks21, [
        name for name in looked if name == FAMILY_ORB], attempt=21)
    closing = conclusion(blocks20 + blocks21)
    section20 = batch20._report(
        stamp, ctx["events"], blocks20, bool(passed20 or passed21), last, args.strategies)
    section20 = section20.rstrip() + "\n\n" + closing + "\n"
    section21 = _report(stamp, blocks21, bool(passed21), last, args.strategies, closing)
    follow.install_attempt(args.experiments, 20, section20, batch20._summary_rows(stamp, blocks20, last))
    follow.install_attempt(args.experiments, 21, section21, _summary_rows(stamp, blocks21, last))
    emit(closing)
    for line in section21.splitlines():
        if line.startswith("name ") or line.startswith("fii ") or line.startswith("quiet ") or line.startswith("nifty ") or line.startswith("Intraday") or line.startswith("No attempt"):
            emit(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
