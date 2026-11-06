#!/usr/bin/env python3
"""Attempt 8. Attempt 7's trend-day rule on 2015-01-01 through 2024-12-31.

The rules below are fixed before the numbers are computed. A run writes them
to india/EXPERIMENTS.md first, then fills the results.

Nothing is placed. Prices are read only through india/research/data.py.
"""

import datetime
import os
import statistics
import sys
from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_UP

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from india import costs
from india import nse_market
from india.research import data
from india.research import regime

START = datetime.date(2015, 1, 1)
END = datetime.date(2024, 12, 31)
NIFTY = "NIFTY 50"
OR_BARS = 6
OPEN = 9 * 60 + 15
FIRST_END = OPEN + 5
FLAT_END = 15 * 60 + 10
FLAT_OFFSET = (FLAT_END - FIRST_END) // 5
ENTRY_FIRST = 9 * 60 + 45
ENTRY_LAST = 14 * 60 + 30
SIGNAL_BY = 10 * 60
TARGET_R = 2.0
RISK_RS = 2000
CAPITAL = 500000
LIQUID = 100
LOOKBACK = 20
EXPERIMENTS = os.path.join(_ROOT, "india", "EXPERIMENTS.md")

# Today's NIFTY 50. The study says so: this list is the current index, not
# the members of each past day.
NIFTY50 = (
    "ADANIENT", "ADANIPORTS", "APOLLOHOSP", "ASIANPAINT", "AXISBANK",
    "BAJAJAUTO", "BAJAJFINSV", "BAJFINANCE", "BEL", "BHARTIARTL",
    "CIPLA", "COALINDIA", "DRREDDY", "EICHERMOT", "ETERNAL",
    "GRASIM", "HCLTECH", "HDFCBANK", "HDFCLIFE", "HINDALCO",
    "HINDUNILVR", "ICICIBANK", "INDIGO", "INFY", "ITC",
    "JIOFIN", "JSWSTEEL", "KOTAKBANK", "LT", "MARUTI",
    "MAXHEALTH", "MM", "NESTLEIND", "NTPC", "ONGC",
    "POWERGRID", "RELIANCE", "SBILIFE", "SBIN", "SHRIRAMFIN",
    "SUNPHARMA", "TATACONSUM", "TATASTEEL", "TCS", "TECHM",
    "TITAN", "TMPV", "TRENT", "ULTRACEMCO", "WIPRO",
)


def _dec(value):
    if isinstance(value, float):
        return Decimal(repr(value))
    return Decimal(str(value))


def to_tick(value, tick):
    """Round half up onto this tick. The same rounding as the time machine."""
    unit = _dec(tick)
    return float((_dec(value) / unit).quantize(Decimal("1"), rounding=ROUND_HALF_UP) * unit)


def ticks_away(value, long, tick):
    """A stop, rounded away from the entry: down for a long, up for a short."""
    unit = _dec(tick)
    rounding = ROUND_FLOOR if long else ROUND_CEILING
    return float((_dec(value) / unit).quantize(Decimal("1"), rounding=rounding) * unit)


def whole_shares(entry, stop, risk_rupees, capital):
    risk_ps = abs(_dec(entry) - _dec(stop))
    if risk_ps <= 0 or _dec(entry) <= 0:
        return 0
    n = int(_dec(risk_rupees) // risk_ps)
    cap = int(_dec(capital) // _dec(entry))
    return max(0, min(n, cap))


def locate(session):
    """Index of the 09:20 bar when the 15:10 bar sits 70 slots later."""
    ends = session["end"]
    origin = None
    for i in range(len(ends)):
        minute = ends[i]
        if minute == FIRST_END:
            origin = i
            break
        if minute > FIRST_END:
            return None
    if origin is None or origin + FLAT_OFFSET >= len(ends):
        return None
    if ends[origin + FLAT_OFFSET] != FLAT_END:
        return None
    return origin


def _range(session, origin):
    high = session["high"]
    low = session["low"]
    oh = high[origin]
    ol = low[origin]
    for k in range(1, OR_BARS):
        if high[origin + k] > oh:
            oh = high[origin + k]
        if low[origin + k] < ol:
            ol = low[origin + k]
    return oh, ol


def nifty_signal(session):
    """(side, close minute, range high, range low, origin) or None.

    The first close beyond the 30-minute range, at or before 10:00. A later
    first break is not a trend day.
    """
    origin = locate(session)
    if origin is None:
        return None
    oh, ol = _range(session, origin)
    close = session["close"]
    ends = session["end"]
    for k in range(OR_BARS, FLAT_OFFSET + 1):
        end = ends[origin + k]
        if end > ENTRY_LAST:
            break
        if end < ENTRY_FIRST:
            continue
        price = close[origin + k]
        if price > oh or price < ol:
            if end > SIGNAL_BY:
                return None
            side = "buy" if price > oh else "sell"
            return side, end, oh, ol, origin
    return None


def _follow(session, origin, entry_k, side, stop, target):
    """Stop is checked before the target. Otherwise the 15:10 close."""
    long = side == "buy"
    last = origin + FLAT_OFFSET
    for i in range(origin + entry_k + 1, last + 1):
        if long:
            if session["low"][i] <= stop:
                return "stop", stop
            if session["high"][i] >= target:
                return "target", target
        else:
            if session["high"][i] >= stop:
                return "stop", stop
            if session["low"][i] <= target:
                return "target", target
    return "close", session["close"][last]


def stock_trade(session, side, not_before, symbol, risk_rs, capital):
    """One stock on one trend day, or None when it never closes beyond its range."""
    origin = locate(session)
    if origin is None:
        return None
    oh, ol = _range(session, origin)
    close = session["close"]
    ends = session["end"]
    long = side == "buy"
    for k in range(OR_BARS, FLAT_OFFSET + 1):
        end = ends[origin + k]
        if end > ENTRY_LAST:
            break
        if end < not_before or end < ENTRY_FIRST:
            continue
        price = close[origin + k]
        if long and price <= oh:
            continue
        if not long and price >= ol:
            continue
        tick = nse_market.tick_for(price, symbol)
        entry = to_tick(price, tick)
        stop = ticks_away((oh + ol) / 2.0, long, tick)
        risk = (entry - stop) if long else (stop - entry)
        if risk <= 0:
            return None
        if long:
            target = to_tick(entry + TARGET_R * risk, tick)
        else:
            target = to_tick(entry - TARGET_R * risk, tick)
        outcome, exit_px = _follow(session, origin, k, side, stop, target)
        shares = whole_shares(entry, stop, risk_rs, capital)
        if shares <= 0:
            return None
        if long:
            fill_entry = entry + tick
            fill_exit = exit_px - tick
            gross = (_dec(fill_exit) - _dec(fill_entry)) * shares
            cost = costs.round_trip(fill_entry, fill_exit, shares)
        else:
            fill_entry = entry - tick
            fill_exit = exit_px + tick
            gross = (_dec(fill_entry) - _dec(fill_exit)) * shares
            cost = costs.round_trip(fill_exit, fill_entry, shares)
        if fill_entry <= 0 or fill_exit <= 0:
            return None
        denom = _dec(risk) * shares
        return {
            "time": end,
            "entry": entry,
            "stop": stop,
            "target": target,
            "outcome": outcome,
            "shares": shares,
            "r_before": float(gross / denom),
            "r_after": float((gross - cost) / denom),
            "rupees": float(gross - cost),
        }
    return None


class Turnover(object):
    """Average close*volume of the previous 20 sessions, walking forward in time."""

    def __init__(self, dates, values, segments):
        self.dates = dates
        self.segments = segments
        self.prefix = [0.0]
        total = 0.0
        for value in values:
            total += value
            self.prefix.append(total)
        self.i = 0

    def average_before(self, day):
        dates = self.dates
        while self.i < len(dates) and dates[self.i] < day:
            self.i += 1
        if self.i < LOOKBACK:
            return None
        if self.segments[self.i - 1] != self.segments[self.i - LOOKBACK]:
            return None
        total = self.prefix[self.i] - self.prefix[self.i - LOOKBACK]
        return total / float(LOOKBACK)


def book_from_series(series):
    dates = []
    values = []
    segments = []
    seg_id = 0
    for segment in series.segments:
        for item in segment:
            session = item["session"]
            dates.append(item["date"])
            values.append(item["close"] * float(session["volume"][-1]))
            segments.append(seg_id)
        seg_id += 1
    return Turnover(dates, values, segments)


def liquid_names(day, books, count):
    """The `count` symbols with the highest average turnover before `day`."""
    scored = []
    for symbol, book in books:
        average = book.average_before(day)
        if average is None:
            continue
        scored.append((average, symbol))
    scored.sort(key=lambda item: (-item[0], item[1]))
    return [symbol for _average, symbol in scored[:count]]


def usable_map(series):
    """date -> session, for sessions that have every bar from 09:15 to 15:10."""
    found = {}
    for segment in series.segments:
        for item in segment:
            session = item["session"]
            starts = [minute - data.BAR_MINUTES for minute in session["end"]]
            if data.session_usable(data.mask_from_starts(starts)):
                found[item["date"]] = session
    return found


def _mean(values):
    if not values:
        return None
    return statistics.mean(values)


def block_for(trades, trend_dates):
    by_day = {}
    for trade in trades:
        by_day[trade["date"]] = by_day.get(trade["date"], 0.0) + trade["rupees"]
    days = list(by_day.values())
    wins = sum(1 for value in days if value > 0)
    ordered = sorted(days, reverse=True)
    rest = ordered[10:]
    return {
        "trend_days": len(trend_dates),
        "trades": len(trades),
        "avg_before": _mean([trade["r_before"] for trade in trades]),
        "avg_after": _mean([trade["r_after"] for trade in trades]),
        "winning_share": (wins / float(len(days))) if days else None,
        "without_best_10": sum(rest) if rest else 0.0,
    }


def _signed(value):
    if value is None:
        return "n/a"
    return "%+.3f" % value


def judge(trades, first_dates):
    """The four rules fixed before attempt 2.

    At least 100 trades. Average R after costs at least +0.10. The first half
    and the second half of the sessions both above 0 after costs. After-cost
    average R above 0 on at least 60% of the stocks that traded.
    """
    reasons = []
    if len(trades) < 100:
        reasons.append("trades %d < 100" % len(trades))
    after = _mean([trade["r_after"] for trade in trades])
    if after is None or after < 0.10:
        reasons.append("average R after costs %s < +0.10" % _signed(after))
    first = [trade for trade in trades if trade["date"] in first_dates]
    second = [trade for trade in trades if trade["date"] not in first_dates]
    first_avg = _mean([trade["r_after"] for trade in first])
    second_avg = _mean([trade["r_after"] for trade in second])
    if first_avg is None or not first_avg > 0:
        reasons.append("first half %s is not above 0 after costs" % _signed(first_avg))
    if second_avg is None or not second_avg > 0:
        reasons.append("second half %s is not above 0 after costs" % _signed(second_avg))
    by_symbol = {}
    for trade in trades:
        by_symbol.setdefault(trade["symbol"], []).append(trade["r_after"])
    if not by_symbol:
        reasons.append("no stock traded")
    else:
        winners = 0
        for values in by_symbol.values():
            avg = _mean(values)
            if avg is not None and avg > 0:
                winners += 1
        if winners * 5 < len(by_symbol) * 3:
            reasons.append("after-cost R > 0 on %d of %d stocks (%.1f%%), need 60%%" % (
                winners, len(by_symbol), 100.0 * winners / len(by_symbol)))
    return {
        "result": "PASS" if not reasons else "FAIL",
        "reasons": reasons,
        "first_half": first_avg,
        "second_half": second_avg,
    }


def _filter_dates(dates, year=None, kind=None, regimes=None):
    kept = []
    for day in dates:
        if year is not None and day.year != year:
            continue
        if kind is not None and regimes.get(day) != kind:
            continue
        kept.append(day)
    return kept


def _filter_trades(trades, year=None, kind=None, regimes=None):
    kept = []
    for trade in trades:
        if year is not None and trade["date"].year != year:
            continue
        if kind is not None and regimes.get(trade["date"]) != kind:
            continue
        kept.append(trade)
    return kept


def report_blocks(trades, trend_dates, regimes, years):
    """Overall, each year, and each market type."""
    blocks = [("overall", block_for(trades, trend_dates))]
    for year in years:
        blocks.append((str(year), block_for(
            _filter_trades(trades, year=year),
            _filter_dates(trend_dates, year=year))))
    for kind in ("up", "down", "sideways"):
        blocks.append((kind, block_for(
            _filter_trades(trades, kind=kind, regimes=regimes),
            _filter_dates(trend_dates, kind=kind, regimes=regimes))))
    return blocks


def format_block(label, block):
    share = "n/a" if block["winning_share"] is None else "%.1f%%" % (100.0 * block["winning_share"])
    return (
        "%s: trend days %d, trades %d, avg R before %s, avg R after %s, "
        "winning-day share %s, profit without the best 10 days Rs %s" % (
            label, block["trend_days"], block["trades"],
            _signed(block["avg_before"]), _signed(block["avg_after"]),
            share, format(block["without_best_10"], ",.2f")))


def format_universe(title, note, blocks, verdict):
    lines = [title, note]
    for label, block in blocks:
        lines.append(format_block(label, block))
    if verdict["result"] == "PASS":
        lines.append("PASS")
    else:
        lines.append("FAIL: %s" % "; ".join(verdict["reasons"]))
    return lines


def rules_text(stamp):
    """The hypothesis and the four rules. Written before any result exists."""
    return "\n".join([
        "## Attempt 8",
        "",
        "Rules fixed on %s, before the run." % stamp,
        "",
        "Hypothesis: attempt 7's trend-day rule, scored on 2015-01-01 through "
        "2024-12-31, clears the pass mark after NSE costs and one tick of slippage. "
        "Two universes are scored separately.",
        "",
        "Rule: a 30-minute opening range. NIFTY 50's first close beyond that range "
        "must be a bar that closes by 10:00. A stock enters on its first close beyond "
        "its own 30-minute range, in NIFTY's direction, at or after that signal and by "
        "14:30. The stop is the range midpoint, rounded to the tick (down for a long, "
        "up for a short). The target is 2R. Flat at 15:10. Each trade risks Rs 2,000 "
        "with a Rs 5,00,000 position cap. The fill is one tick worse than the signal "
        "price on the entry and on the exit (tick_for). Costs are india/costs.py on "
        "those fill prices. R before costs uses the slipped fills and the planned risk. "
        "R after costs subtracts the round trip. A session is used only when it has "
        "every bar from 09:15 to 15:10.",
        "",
        "Pass mark, the four rules fixed before attempt 2: at least 100 trades; "
        "average R after costs at least +0.10; the first half and the second half of "
        "the sessions both above 0 after costs; after-cost average R above 0 on at "
        "least 60% of the stocks that traded.",
        "",
        "Universe A is today's NIFTY 50. It has survivorship bias: the members are "
        "the current index, not the members on each past day. Universe B, each day, "
        "is the 100 symbols with the highest average daily turnover (close times "
        "volume) over the previous 20 sessions, using only sessions before that day "
        "and never a turnover that crosses a break.",
        "",
        "Results are filled in after the run.",
        "",
    ])


def _table_row(stamp, hypothesis, rule, universe, trades, before, after, result):
    return "| 8 | %s | %s | %s | %s | %s | %s | %s | %s |" % (
        stamp, hypothesis, rule, universe, trades, before, after, result)


def _fmt_r(value):
    if value is None:
        return "n/a"
    return "%+.3f" % value


def results_text(stamp, universes):
    """universes is a list of (title, note, blocks, verdict, table_bits)."""
    lines = [rules_text(stamp).replace("Results are filled in after the run.\n", "").rstrip(), ""]
    lines.append("Winning-day share is days with net rupees above 0, divided by days that had a trade. "
                 "Profit without the best 10 days drops those days' rupees and sums the rest.")
    lines.append("")
    for title, note, blocks, verdict in universes:
        lines.extend(format_universe(title, note, blocks, verdict))
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _overall(blocks):
    for label, block in blocks:
        if label == "overall":
            return block
    return blocks[0][1]


def table_rows(stamp, universes):
    """Two rows. The hypothesis text is the one fixed before the run."""
    rule = "30m or-mid 2R, long and short, NIFTY signal by 10:00, 1 tick slippage"
    rows = []
    for title, _note, blocks, verdict in universes:
        block = _overall(blocks)
        if title.startswith("Universe A"):
            hypothesis = ("Attempt 7's trend-day rule is profitable after costs on "
                          "2015-2024 in today's NIFTY 50. This universe has survivorship bias.")
            universe = "today's NIFTY 50, 2015-01-01 to 2024-12-31, Rs 2,000 risk, Rs 5,00,000 cap"
        else:
            hypothesis = ("The same rule is profitable after costs on 2015-2024 in the "
                          "100 names with the highest prior 20-session turnover.")
            universe = "point-in-time top 100 by prior 20-session turnover, 2015-01-01 to 2024-12-31"
        rows.append(_table_row(
            stamp, hypothesis, rule, universe,
            format(block["trades"], ",d"),
            _fmt_r(block["avg_before"]), _fmt_r(block["avg_after"]),
            verdict["result"]))
    return rows


def install(path, section, rows):
    """Replace an existing attempt 8 section and its table rows."""
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    lines = text.splitlines()
    kept = []
    for line in lines:
        if line.startswith("| 8 |"):
            continue
        kept.append(line)
    text = "\n".join(kept)
    if not text.endswith("\n"):
        text += "\n"
    start = text.find("\n## Attempt 8\n")
    forward = text.find("\n## Forward test\n")
    block = "\n" + section.rstrip() + "\n\n"
    if start != -1 and (forward == -1 or start < forward):
        end = forward if forward != -1 else len(text)
        text = text[:start] + block + text[end:]
    elif forward != -1:
        text = text[:forward] + block + text[forward:]
    else:
        text = text.rstrip() + "\n" + block
    if rows:
        marker = "| 7 | 2026-11-04 | Trend-day niche"
        at = text.find(marker)
        if at != -1:
            line_end = text.find("\n", at)
            inserted = "\n" + "\n".join(rows)
            text = text[:line_end] + inserted + text[line_end:]
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


def _signals(nifty_sessions, regimes, start, end):
    """Trend days, and the session calendar used to split the halves."""
    calendar = []
    signals = {}
    for day in sorted(nifty_sessions):
        if day < start or day > end:
            continue
        calendar.append(day)
        if day not in regimes:
            continue
        signal = nifty_signal(nifty_sessions[day])
        if signal is not None:
            signals[day] = signal
    return calendar, signals


def score_symbol(symbol, sessions, signals, current, liquid_by_day, regimes, risk_rs, capital):
    """Trades for one symbol. current is a set. liquid_by_day maps a date to a set."""
    current_trades = []
    liquid_trades = []
    for day, signal in signals.items():
        session = sessions.get(day)
        if session is None:
            continue
        side, minute, _oh, _ol, _origin = signal
        in_current = symbol in current
        in_liquid = symbol in liquid_by_day.get(day, ())
        if not in_current and not in_liquid:
            continue
        trade = stock_trade(session, side, minute, symbol, risk_rs, capital)
        if trade is None:
            continue
        trade["date"] = day
        trade["symbol"] = symbol
        trade["regime"] = regimes.get(day)
        if in_current:
            current_trades.append(trade)
        if in_liquid:
            liquid_trades.append(dict(trade))
    return current_trades, liquid_trades


def assemble(calendar, signals, regimes, current_trades, liquid_trades, start=START, end=END):
    """The two universe reports. Halves are the first and second half of the calendar."""
    mid = len(calendar) // 2
    first_dates = set(calendar[:mid])
    years = list(range(start.year, end.year + 1))
    trend_dates = sorted(signals)
    universes = []
    for title, note, trades in (
        ("Universe A, today's NIFTY 50",
         "This universe has survivorship bias: members are the current index, not the members of each past day.",
         current_trades),
        ("Universe B, point-in-time liquid stocks",
         "Each day is the 100 symbols with the highest average daily turnover over the previous 20 sessions.",
         liquid_trades),
    ):
        blocks = report_blocks(trades, trend_dates, regimes, years)
        verdict = judge(trades, first_dates)
        universes.append((title, note, blocks, verdict))
    return universes


def _load_map(root, symbol, start, end):
    series = data.load_arrays(root, symbol, "5minute", start=start, end=end)
    return usable_map(series)


def run(root, start=START, end=END, members=None, liquid_count=LIQUID,
        risk_rs=RISK_RS, capital=CAPITAL, log=None):
    """Score both universes. Reads data/kite only through data.py."""
    emit = log or (lambda line: None)
    members = tuple(members) if members is not None else NIFTY50
    daily = data.load_arrays(root, NIFTY, "day", end=end)
    points = []
    for segment in daily.segments:
        for item in segment:
            points.append((item["date"], item["close"]))
    regimes = regime.by_date(points)
    nifty_sessions = _load_map(root, NIFTY, start, end)
    calendar, signals = _signals(nifty_sessions, regimes, start, end)
    emit("trend days: %d" % len(signals))

    books = []
    symbols = []
    for symbol in data.symbols_in(root):
        if symbol.startswith("NIFTY"):
            continue
        try:
            series = data.load_arrays(root, symbol, "day", end=end)
        except data.DataError:
            continue
        books.append((symbol, book_from_series(series)))
        symbols.append(symbol)
    liquid_by_day = {}
    for day in signals:
        liquid_by_day[day] = set(liquid_names(day, books, liquid_count))
    current = set(members)
    wanted = set(current)
    for names in liquid_by_day.values():
        wanted.update(names)

    current_trades = []
    liquid_trades = []
    done = 0
    ordered = [symbol for symbol in symbols if symbol in wanted]
    for symbol in ordered:
        done += 1
        if done % 25 == 0 or done == len(ordered):
            emit("scored %d / %d symbols" % (done, len(ordered)))
        try:
            sessions = _load_map(root, symbol, start, end)
        except data.DataError:
            continue
        part_current, part_liquid = score_symbol(
            symbol, sessions, signals, current, liquid_by_day, regimes, risk_rs, capital)
        current_trades.extend(part_current)
        liquid_trades.extend(part_liquid)
    return assemble(calendar, signals, regimes, current_trades, liquid_trades, start, end)


def main(argv=None, log=None):
    import argparse
    parser = argparse.ArgumentParser(description="Attempt 8 trend-day study. Nothing is placed.")
    parser.add_argument("--root", default=os.path.join("data", "kite"))
    parser.add_argument("--experiments", default=EXPERIMENTS)
    args = parser.parse_args(argv)
    emit = log or (lambda line: print(line, flush=True))
    stamp = datetime.date.today().isoformat()
    install(args.experiments, rules_text(stamp), [])
    emit("rules written to %s before the run" % args.experiments)
    universes = run(args.root, log=emit)
    section = results_text(stamp, universes)
    install(args.experiments, section, table_rows(stamp, universes))
    for title, note, blocks, verdict in universes:
        for line in format_universe(title, note, blocks, verdict):
            emit(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
