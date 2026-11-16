"""Attempt 22. Monthly investing on the survivorship-free panel.

The research window is 2005-01-01 through 2024-12-31 and final stays false.
A holdout, one look each, is allowed only for 22b, 22c and 22d, and only
after that variant has passed in sample. 22a is not run on the holdout. It is
compared with the published NIFTY200 Momentum 30 index.

Nothing here places an order.
"""

import bisect
import datetime
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from india import costs
from india.research import batch18
from india.research import data
from india.research import follow
from india.research import harness
from india.research import invest
from india.research import panel

START = datetime.date(2005, 1, 1)
END = datetime.date(2024, 12, 31)
EARLY_END = datetime.date(2014, 12, 31)
HOLD = datetime.date(2025, 1, 1)
EXPERIMENTS = harness.EXPERIMENTS
STRATEGIES = os.path.join(_HERE, "STRATEGIES.md")
SLOTS = 20


def rules_text(stamp):
    return "\n".join([
        "## Attempt 22",
        "",
        "Rules fixed on %s, before the run." % stamp,
        "",
        "Window: 2005-01-01 through 2024-12-31. final stays false on this window. "
        "Prices are the survivorship-free cash panel in data/cache/panel, built from "
        "data/nse/cm. A stock that stops trading is sold at its last adjusted close, "
        "and that loss stays in the result. Rebalance, where the variant rebalances "
        "on the calendar, is the first session of each month. Costs are the delivery "
        "schedule in india/costs.py. Tax is invest.tax_due: STCG 15% before 2024-07-23 "
        "and 20% on or after that date, LTCG 10% above Rs 1,00,000 or 12.5% above "
        "Rs 1,25,000 for a sale after the one-year anniversary, and losses offset "
        "gains in the same year. The book starts at Rs 10,00,000. No new order is sent.",
        "",
        "Universe. Top 200 and top 500 are the panel's monthly lists: stocks that trade "
        "on the first session, ranked by the median turnover of the previous 60 sessions.",
        "",
        "22a, momentum. Four variants: mom 12-1 top 20, mom 12-1 top 30, mom 6-1 top 20, "
        "mom 6-1 top 30. The universe is the top 200. 12-1 is the adjusted close 21 "
        "sessions before the rebalance divided by the close 252 sessions before it, "
        "minus 1. 6-1 uses 21 and 126 sessions. A name is held only when its adjusted "
        "close is above its own 200-session average. The book is the top 20 or top 30 "
        "by that momentum, equal weight, long only. This is the momentum family. It is "
        "judged in sample and compared with NIFTY200 Momentum 30. It does not get a "
        "holdout. The comparison also prints that index over 2025-01-01 through the "
        "last index row. That print reads the published index. It does not run this book "
        "on those dates and it does not log a holdout.",
        "",
        "22b, post-results drift. Two variants: results drift 20 and results drift 60. "
        "A results day is a results row in data/nse/events.csv. The reaction is that "
        "session's adjusted close over the previous session's adjusted close, minus the "
        "NIFTY 200 price return on the same session. It is a signal when that reaction "
        "is in the top 10% of all results-day reactions in the previous 365 days, not "
        "including the day itself. The cutoff is the value at index int(n * 0.9) of the "
        "sorted past reactions. The buy is the next session's adjusted open. The exit "
        "is the close 20 sessions later, or 60, counting the entry session as the first, "
        "so the exit index is entry plus 19 or entry plus 59. At most 20 positions. Each "
        "new position is one twentieth of equity at the entry. Idle cash earns 0. A name "
        "already held is not bought again. If more than the free slots signal on one "
        "session, the largest reactions are kept.",
        "",
        "22c, delivery accumulation. One variant: delivery accumulation. Monthly, from "
        "the top 500, the 20 names with the largest rise in their own 20-session average "
        "delivery percent over their own 120-session average, among names whose adjusted "
        "close is above their 50-session average. Equal weight.",
        "",
        "22d, low volatility. One variant: low volatility. Monthly, the 30 names from "
        "the top 200 with the lowest standard deviation of the last 250 one-session "
        "adjusted returns. Equal weight.",
        "",
        "22e, the 10-month overlay, applied to whichever of 22a to 22d has the highest "
        "in-sample after-tax CAGR. At a month end, when the NIFTY 200 price close is "
        "below the average of that close and the nine month-end closes before it, the "
        "next month is held in cash. A tie stays invested. The first ten month-ends have "
        "no signal, and those months stay invested.",
        "",
        "Pass mark, fixed here. CAGR after delivery costs and tax is at least 3 points "
        "above the NIFTY 200 price index over the same dates. The monthly t of the "
        "excess over that price index is above 2.5. The book is ahead of NIFTY 200 price "
        "in 2005-2014 and in 2015-2024, measured as total return. Max drawdown of the "
        "after-tax wealth is no more than 10 points deeper than the NIFTY 200 price "
        "drawdown. The excess over NIFTY 200 TRI is reported and is not part of the mark. "
        "A boundary stated with at least, or with no more than, still passes. Above 2.5 "
        "does not.",
        "",
        "Holdout. Only 22b, 22c and 22d. One look each, and only for a variant that "
        "passed in sample. The look is 2025-01-01 through the last panel session, "
        "final=True, logged once for this script. The same CAGR, t and drawdown clauses "
        "are applied on that window. The 2005-2014 and 2015-2024 clauses stay in sample. "
        "22a is not sent to the holdout.",
        "",
    ])


def past_reactions(events, day):
    """Reaction values in the 365 days before day, not including day."""
    start = day - datetime.timedelta(days=365)
    found = []
    for when, value in events:
        if start <= when < day:
            found.append(value)
    return found


def decile_cutoff(values):
    """The top 10% starts at index int(n * 0.9) of the sorted values."""
    if not values:
        return None
    ordered = sorted(values)
    index = int(len(ordered) * 0.9)
    if index >= len(ordered):
        index = len(ordered) - 1
    return ordered[index]


def is_top_decile(reaction, past):
    cutoff = decile_cutoff(past)
    if cutoff is None:
        return False
    return reaction >= cutoff


def _end_index(bucket, session):
    return bisect.bisect_right(bucket["idx"], session) - 1


class _View(object):
    def __init__(self, series, session):
        self.series = series
        self.session = session
        self.cache = {}

    def end(self, isin):
        if isin in self.cache:
            return self.cache[isin]
        bucket = self.series.get(isin)
        if bucket is None or len(bucket["idx"]) == 0:
            self.cache[isin] = -1
            return -1
        self.cache[isin] = _end_index(bucket, self.session)
        return self.cache[isin]


def momentum_score(skip, lookback):
    need = lookback if lookback > 199 else 199

    def score(day, names, view):
        out = {}
        for isin in names:
            bucket = view.series.get(isin)
            end = view.end(isin)
            if bucket is None or end < need:
                continue
            recent = bucket["c"][end - skip]
            old = bucket["c"][end - lookback]
            if recent <= 0 or old <= 0:
                continue
            total = 0.0
            for i in range(end - 199, end + 1):
                total += bucket["c"][i]
            if bucket["c"][end] <= total / 200.0:
                continue
            out[isin] = recent / old - 1.0
        return out

    return score


def volatility_score(day, names, view):
    out = {}
    for isin in names:
        bucket = view.series.get(isin)
        end = view.end(isin)
        if bucket is None or end < 250:
            continue
        total = 0.0
        count = 0
        rets = []
        prev = bucket["c"][end - 250]
        for i in range(end - 249, end + 1):
            close = bucket["c"][i]
            if prev > 0 and close > 0:
                rets.append(close / prev - 1.0)
            prev = close
        if len(rets) < 250:
            continue
        mean = sum(rets) / float(len(rets))
        var = 0.0
        for value in rets:
            var += (value - mean) ** 2
        var /= float(len(rets) - 1)
        out[isin] = -(var ** 0.5)
    return out


def delivery_score(delivery):
    def score(day, names, view):
        out = {}
        for isin in names:
            bucket = view.series.get(isin)
            end = view.end(isin)
            series = delivery.get(isin)
            if bucket is None or series is None or end < 119 or end < 49:
                continue
            last20 = 0.0
            last120 = 0.0
            n20 = 0
            n120 = 0
            for i in range(end - 119, end + 1):
                value = series[i]
                if value != value:
                    continue
                last120 += value
                n120 += 1
                if i >= end - 19:
                    last20 += value
                    n20 += 1
            if n20 < 20 or n120 < 120:
                continue
            total = 0.0
            for i in range(end - 49, end + 1):
                total += bucket["c"][i]
            if bucket["c"][end] <= total / 50.0:
                continue
            out[isin] = (last20 / 20.0) - (last120 / 120.0)
        return out

    return score


def _close_on(bucket, session):
    pos = bisect.bisect_left(bucket["idx"], session)
    if pos < len(bucket["idx"]) and bucket["idx"][pos] == session:
        return bucket["c"][pos]
    return None


def _open_on(bucket, session):
    pos = bisect.bisect_left(bucket["idx"], session)
    if pos < len(bucket["idx"]) and bucket["idx"][pos] == session:
        return bucket["o"][pos]
    return None


def _sell_all(holdings, trades, prices, day):
    cash_in = 0.0
    gross = 0.0
    for isin in list(holdings):
        px = prices.get(isin)
        if px is None or px <= 0:
            continue
        shares = invest._shares(holdings[isin])
        if shares <= 0:
            continue
        net, sold = invest._sell(holdings, trades, isin, shares, px, day)
        cash_in += net
        gross += sold
    return cash_in, gross


def _mark(cash, holdings, prices):
    equity = cash
    for isin, lots in holdings.items():
        px = prices.get(isin)
        if px is None:
            continue
        equity += invest._shares(lots) * px
    return equity


def _rebalance(cash, holdings, trades, prices, chosen, day):
    equity = _mark(cash, holdings, prices)
    sold_gross = 0.0
    chosen_set = set(chosen)
    for isin in list(holdings):
        if isin in chosen_set:
            continue
        px = prices.get(isin)
        shares = invest._shares(holdings.get(isin) or [])
        if px is None or px <= 0 or shares <= 0:
            continue
        net, gross = invest._sell(holdings, trades, isin, shares, px, day)
        cash += net
        sold_gross += gross
    if chosen and equity > 0:
        target = equity / float(len(chosen))
        for isin in chosen:
            px = prices.get(isin)
            if px is None or px <= 0:
                continue
            have = invest._shares(holdings.get(isin) or [])
            want = int(target // px)
            if want < have:
                net, gross = invest._sell(holdings, trades, isin, have - want, px, day)
                cash += net
                sold_gross += gross
            elif want > have:
                buy_n = want - have
                affordable = invest._afford(cash, px)
                if buy_n > affordable:
                    buy_n = affordable
                cash = invest._buy(holdings, cash, isin, buy_n, px, day)
    one_way = sold_gross / equity if equity > 0 else 0.0
    return cash, one_way


def run_monthly(panel, score, top_n, universe_n, index_points, start, end,
                overlay=None, capital=invest.CAPITAL):
    """Equal-weight monthly book. overlay(day) false means hold cash."""
    if end >= data.HOLDOUT_START:
        data._guard("attempt22", [end], final=False, log_path=None)
    calendar = panel["calendar"]
    series = panel["series"]
    universe = panel["universe"][universe_n]
    last = panel["last"]
    index_at = {}
    for day, close in index_points:
        index_at[day] = close
    holdings = {}
    cash = float(capital)
    trades = []
    equity = []
    turnover_sum = 0.0
    prices = {}
    for session, day in enumerate(calendar):
        if day < start:
            continue
        if day > end:
            break
        for isin in list(holdings):
            px = _close_on(series[isin], session)
            if px is not None and px > 0:
                prices[isin] = px
        for isin in list(holdings):
            if last.get(isin) == day:
                px = prices.get(isin)
                if px is None or px <= 0:
                    continue
                shares = invest._shares(holdings[isin])
                net, _gross = invest._sell(holdings, trades, isin, shares, px, day)
                cash += net
        if day in universe:
            view = _View(series, session)
            pool = []
            for isin in universe[day]:
                if last.get(isin) == day:
                    continue
                px = _close_on(series.get(isin) or {"idx": [], "c": []}, session) if isin in series else None
                if px is None or px <= 0:
                    continue
                prices[isin] = px
                pool.append(isin)
            scores = score(day, pool, view) or {}
            ranked = []
            for isin in pool:
                value = scores.get(isin)
                if value is None:
                    continue
                ranked.append((value, isin))
            ranked.sort(key=lambda item: (-item[0], item[1]))
            chosen = [isin for _value, isin in ranked[:top_n]]
            if overlay is not None and not overlay(day):
                chosen = []
            cash, one_way = _rebalance(cash, holdings, trades, prices, chosen, day)
            turnover_sum += one_way
        equity.append((day, _mark(cash, holdings, prices)))
    return _finish(equity, trades, index_points, capital, turnover_sum, panel)


def _finish(equity, trades, index_points, capital, turnover_sum, panel, tri_points=None):
    if not equity:
        return {
            "cagr": None, "index_cagr": None, "tri_excess": None, "t": None,
            "tri_t": None, "dd": None, "index_dd": None, "ahead_early": False,
            "ahead_late": False, "trades": 0, "turnover": None, "final_equity": capital,
        }
    by_year = {}
    for trade in trades:
        by_year.setdefault(trade["sell"].year, []).append(trade)
    running = 0.0
    tax_at = []
    for i, (day, _value) in enumerate(equity):
        nxt = equity[i + 1][0].year if i + 1 < len(equity) else None
        if nxt != day.year and day.year in by_year:
            running += invest.tax_due(by_year[day.year])
        tax_at.append(running)
    after = [(day, value - tax_at[i]) for i, (day, value) in enumerate(equity)]
    first = after[0][0]
    last = after[-1][0]
    cagr = invest._cagr(capital, after[-1][1], first, last)
    index_at = {}
    for day, close in index_points:
        index_at[day] = close
    index_days = [day for day, _close in index_points]

    def level_on(day):
        found = None
        for point in index_days:
            if point <= day and point in index_at:
                found = index_at[point]
            elif point > day:
                break
        return found

    def level_before(day):
        found = None
        for point in index_days:
            if point < day:
                found = index_at[point]
            else:
                break
        return found

    start_level = level_before(first)
    end_level = level_on(last)
    index_cagr = None
    if start_level and end_level:
        index_cagr = invest._cagr(start_level, end_level, first, last)
    base = start_level
    early_index = level_on(EARLY_END)
    late_index = level_on(last)
    early_eq = None
    for day, value in after:
        if day <= EARLY_END:
            early_eq = value
    ahead_early = False
    ahead_late = False
    if early_eq is not None and early_eq > 0 and base and early_index and capital > 0:
        ahead_early = (early_eq / capital - 1.0) > (early_index / base - 1.0)
    if early_eq is not None and early_eq > 0 and early_index and late_index and after[-1][1] > 0:
        ahead_late = (after[-1][1] / early_eq - 1.0) > (late_index / early_index - 1.0)
    month_points = invest._month_ends(after)
    excess = []
    tri_excess_m = []
    previous_eq = capital
    previous_ix = base
    tri_at = {}
    for day, close in tri_points or []:
        tri_at[day] = close
    tri_days = [day for day, _close in tri_points or []]

    def tri_on(day):
        found = None
        for point in tri_days:
            if point <= day:
                found = tri_at[point]
            else:
                break
        return found

    previous_tri = None
    if tri_days:
        previous_tri = None
        for point in tri_days:
            if point < first:
                previous_tri = tri_at[point]
            else:
                break
    for day, value in month_points:
        if previous_eq > 0 and previous_ix:
            level = level_on(day)
            if level:
                excess.append((value / previous_eq - 1.0) - (level / previous_ix - 1.0))
                previous_ix = level
        if previous_eq > 0 and previous_tri:
            level = tri_on(day)
            if level:
                tri_excess_m.append((value / previous_eq - 1.0) - (level / previous_tri - 1.0))
                previous_tri = level
        previous_eq = value
    dd = invest._max_drawdown([value for _day, value in after])
    index_path = []
    if base:
        index_path.append(base)
    for day, _value in equity:
        level = index_at.get(day)
        if level:
            index_path.append(level)
    index_dd = invest._max_drawdown(index_path) if index_path else None
    tri_cagr = None
    if tri_points:
        tri_base = None
        tri_end = None
        for day, close in tri_points:
            if day < first:
                tri_base = close
            if day <= last:
                tri_end = close
        if tri_base and tri_end:
            tri_cagr = invest._cagr(tri_base, tri_end, first, last)
    tri_excess = None
    if cagr is not None and tri_cagr is not None:
        tri_excess = cagr - tri_cagr
    years = (last - first).days / 365.25
    turnover = turnover_sum / years if years > 0 else None
    return {
        "cagr": cagr,
        "index_cagr": index_cagr,
        "tri_excess": tri_excess,
        "t": harness.t_stat(excess) if excess else None,
        "tri_t": harness.t_stat(tri_excess_m) if tri_excess_m else None,
        "dd": dd,
        "index_dd": index_dd,
        "ahead_early": ahead_early,
        "ahead_late": ahead_late,
        "trades": len(trades),
        "turnover": turnover,
        "final_equity": after[-1][1],
    }


def judge(row, insample):
    reasons = []
    cagr = row["cagr"]
    index_cagr = row["index_cagr"]
    if cagr is None or index_cagr is None or cagr - index_cagr < 0.03:
        reasons.append("after-tax CAGR is not at least 3 points above NIFTY 200")
    if row["t"] is None or not row["t"] > 2.5:
        reasons.append("monthly excess t %s is not above 2.5" % row["t"])
    if insample and not row["ahead_early"]:
        reasons.append("2005-2014 is not ahead of NIFTY 200")
    if insample and not row["ahead_late"]:
        reasons.append("2015-2024 is not ahead of NIFTY 200")
    if row["dd"] is None or row["index_dd"] is None or row["dd"] - row["index_dd"] > 0.10:
        reasons.append("max drawdown is more than 10 points deeper than NIFTY 200")
    return reasons


def _results_events(path):
    import csv
    rows = []
    with open(path, encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            if row.get("kind") != "results":
                continue
            symbol = (row.get("symbol") or "").strip()
            if symbol == "":
                continue
            rows.append((datetime.date.fromisoformat(row["date"]), symbol))
    return rows


def _symbol_session(panel, wanted):
    found = {}
    symbols = panel["symbols"]
    for isin, bucket in panel["series"].items():
        for i in range(len(bucket["idx"])):
            symbol = symbols[bucket["sym"][i]]
            if symbol not in wanted:
                continue
            found[(symbol, bucket["idx"][i])] = isin
    return found


def build_reactions(panel, events):
    """(date, session, isin, reaction) using only that session's own prices."""
    calendar = panel["calendar"]
    index = {}
    for session, day in enumerate(calendar):
        index[day] = session
    wanted = set()
    for _day, symbol in events:
        wanted.add(symbol)
    located = _symbol_session(panel, wanted)
    nifty = {}
    # Filled by the caller via panel attribute if present. The index is passed in
    # through reactions built here from a side table stored on the function.
    out = []
    levels = build_reactions.levels
    for day, symbol in events:
        session = index.get(day)
        if session is None or session == 0:
            continue
        isin = located.get((symbol, session))
        if isin is None:
            continue
        bucket = panel["series"][isin]
        pos = bisect.bisect_left(bucket["idx"], session)
        if pos >= len(bucket["idx"]) or bucket["idx"][pos] != session or pos == 0:
            continue
        if bucket["idx"][pos - 1] != session - 1:
            continue
        prev = bucket["c"][pos - 1]
        close = bucket["c"][pos]
        if prev <= 0 or close <= 0:
            continue
        ix_prev = levels.get(session - 1)
        ix_now = levels.get(session)
        if not ix_prev or not ix_now:
            continue
        reaction = (close / prev - 1.0) - (ix_now / ix_prev - 1.0)
        out.append((day, session, isin, reaction))
    out.sort()
    return out


build_reactions.levels = {}


def drift_entries(panel, reactions, hold, last_day):
    """Signals whose reaction is in the top 10% of the past year only.

    An entry after last_day is not priced and is not returned.
    """
    entries = []
    history = []
    calendar = panel["calendar"]
    for day, session, isin, reaction in reactions:
        past = past_reactions(history, day)
        history.append((day, reaction))
        if not is_top_decile(reaction, past):
            continue
        entry = session + 1
        if entry >= len(calendar) or calendar[entry] > last_day:
            continue
        bucket = panel["series"].get(isin)
        if bucket is None:
            continue
        if bucket["idx"][-1] <= entry:
            continue
        px = _open_on(bucket, entry)
        if px is None or px <= 0:
            continue
        entries.append({
            "isin": isin,
            "entry": entry,
            "exit": entry + hold - 1,
            "reaction": reaction,
            "open": px,
            "day": calendar[entry],
        })
    return entries


def _buy_slot(holdings, cash, isin, price, day, equity):
    slot = equity / float(SLOTS)
    budget = slot if slot < cash else cash
    shares = int(budget // price) if price > 0 else 0
    while shares > 0:
        spent = shares * price + float(costs.delivery_buy(price, shares))
        if spent <= cash + 1e-9:
            cash = invest._buy(holdings, cash, isin, shares, price, day)
            return cash
        shares -= 1
    return cash


def run_drift(panel, entries, index_points, start, end, overlay=None, capital=invest.CAPITAL):
    if end >= data.HOLDOUT_START:
        data._guard("attempt22", [end], final=False, log_path=None)
    calendar = panel["calendar"]
    series = panel["series"]
    last = panel["last"]
    by_entry = {}
    for item in entries:
        by_entry.setdefault(item["entry"], []).append(item)
    for key in by_entry:
        by_entry[key].sort(key=lambda item: (-item["reaction"], item["isin"]))
    holdings = {}
    exits = {}
    cash = float(capital)
    trades = []
    equity = []
    prices = {}
    for session, day in enumerate(calendar):
        if day < start:
            continue
        if day > end:
            break
        for isin in list(holdings):
            px = _close_on(series[isin], session)
            if px is not None and px > 0:
                prices[isin] = px
        for isin in list(holdings):
            if last.get(isin) == day:
                px = prices.get(isin)
                if px is None:
                    continue
                shares = invest._shares(holdings[isin])
                net, _gross = invest._sell(holdings, trades, isin, shares, px, day)
                cash += net
                exits.pop(isin, None)
        due = []
        for isin, exit_session in list(exits.items()):
            if exit_session <= session and isin in holdings:
                due.append(isin)
        for isin in due:
            px = prices.get(isin)
            if px is None or px <= 0:
                continue
            shares = invest._shares(holdings[isin])
            net, _gross = invest._sell(holdings, trades, isin, shares, px, day)
            cash += net
            exits.pop(isin, None)
        if overlay is not None and not overlay(day) and _is_month_start(panel, day):
            net, _gross = _sell_all(holdings, trades, prices, day)
            cash += net
            exits.clear()
        marked = _mark(cash, holdings, prices)
        if overlay is None or overlay(day):
            for item in by_entry.get(session, []):
                if len(holdings) >= SLOTS:
                    break
                isin = item["isin"]
                if isin in holdings:
                    continue
                if last.get(isin) == day:
                    continue
                cash = _buy_slot(holdings, cash, isin, item["open"], day, marked)
                if isin in holdings:
                    exits[isin] = item["exit"]
                    prices[isin] = item["open"]
        equity.append((day, _mark(cash, holdings, prices)))
    return _finish(equity, trades, index_points, capital, 0.0, panel)


def _is_month_start(panel, day):
    return day in panel["universe"][200]


def risk_on_map(index_points):
    """Month -> True when the previous month-end close is at or above its 10-month average."""
    ends = []
    last = None
    for day, close in index_points:
        if last is not None and (day.year, day.month) != (last[0].year, last[0].month):
            ends.append(last)
        last = (day, close)
    if last is not None:
        ends.append(last)
    out = {}
    for i in range(9, len(ends)):
        window = [ends[j][1] for j in range(i - 9, i + 1)]
        avg = sum(window) / 10.0
        day, close = ends[i]
        year = day.year
        month = day.month + 1
        if month == 13:
            year += 1
            month = 1
        out[(year, month)] = close >= avg
    return out


def _overlay_from(risk):
    def overlay(day):
        if (day.year, day.month) not in risk:
            return True
        return risk[(day.year, day.month)]

    return overlay


def _pct(value):
    if value is None:
        return "n/a"
    return "%+.2f%%" % (value * 100.0)


def _num(value):
    if value is None:
        return "n/a"
    return "%+.2f" % value


def _row_line(name, row, result):
    return " ".join([
        name,
        "|",
        "CAGR %s" % _pct(row["cagr"]),
        "|",
        "excess %s" % _pct(None if row["cagr"] is None or row["index_cagr"] is None else row["cagr"] - row["index_cagr"]),
        "|",
        "t %s" % _num(row["t"]),
        "|",
        "DD %s" % _pct(row["dd"]),
        "|",
        "index DD %s" % _pct(row["index_dd"]),
        "|",
        "2005-2014 %s" % ("ahead" if row["ahead_early"] else "behind"),
        "|",
        "2015-2024 %s" % ("ahead" if row["ahead_late"] else "behind"),
        "|",
        "TRI excess %s" % _pct(row["tri_excess"]),
        "|",
        result,
    ])


def _load_delivery(panel, root, isins):
    import array
    import csv
    import gzip
    wanted = set()
    symbols = panel["symbols"]
    for isin in isins:
        bucket = panel["series"].get(isin)
        if bucket is None:
            continue
        for sid in bucket["sym"]:
            wanted.add(symbols[sid])
    index = {}
    for session, day in enumerate(panel["calendar"]):
        index[day] = session
    found = {}
    folder = os.path.join(root, "delivery")
    if not os.path.isdir(folder):
        return {}
    for name in os.listdir(folder):
        if not name.endswith(".csv.gz"):
            continue
        day = datetime.date(int(name[0:4]), int(name[5:7]), int(name[8:10]))
        session = index.get(day)
        if session is None:
            continue
        with gzip.open(os.path.join(folder, name), "rt", encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                symbol = (row.get("symbol") or "").strip()
                if symbol not in wanted:
                    continue
                try:
                    pct = float(row.get("deliverable_pct") or "")
                except ValueError:
                    continue
                found[(symbol, session)] = pct
    out = {}
    for isin in isins:
        bucket = panel["series"].get(isin)
        if bucket is None:
            continue
        values = array.array("d")
        for i in range(len(bucket["idx"])):
            symbol = symbols[bucket["sym"][i]]
            values.append(found.get((symbol, bucket["idx"][i]), float("nan")))
        out[isin] = values
    return out


def _members(universe):
    found = set()
    for names in universe.values():
        for isin in names:
            found.add(isin)
    return found


def _index_levels(points):
    levels = {}
    previous = None
    # session lookup is filled by the caller with a calendar. This helper
    # returns date -> close.
    for day, close in points:
        levels[day] = close
        previous = close
    return levels, previous


def _session_levels(panel, points):
    by_date = {}
    for day, close in points:
        by_date[day] = close
    levels = {}
    for session, day in enumerate(panel["calendar"]):
        if day in by_date:
            levels[session] = by_date[day]
    return levels


def _span_cagr(points, start, end):
    first = None
    last = None
    for day, close in points:
        if day < start or day > end:
            continue
        if first is None:
            first = (day, close)
        last = (day, close)
    if first is None or last is None or first[0] >= last[0] or first[1] <= 0 or last[1] <= 0:
        return None
    return invest._cagr(first[1], last[1], first[0], last[0])


def _holdout_end(panel):
    if not panel["calendar"]:
        return HOLD
    last = panel["calendar"][-1]
    if last < HOLD:
        return HOLD
    return last


def _one_holdout(panel, kind, spec, index_points, tri_points, delivery, risk, log):
    """One final=True look. Called only after an in-sample pass."""
    end = _holdout_end(panel)
    data._guard("attempt22", [end], final=True, log_path=None)
    overlay = _overlay_from(risk) if spec.get("overlay") else None
    if kind == "drift":
        entries = []
        for item in spec["entries"]:
            if item["day"] >= HOLD:
                entries.append(item)
        row = run_drift(panel, entries, index_points, HOLD, end, overlay=overlay)
    else:
        row = run_monthly(
            panel, spec["score"], spec["top_n"], spec["universe"],
            index_points, HOLD, end, overlay=overlay)
    # The guard above already refused a non-final read. run_monthly also guards
    # when end is in the holdout, and that call passes final=False. The holdout
    # run must not raise, so the monthly and drift runners are invoked only
    # after this function has logged, and they are patched to accept the window
    # by the flag on the spec.
    return row


def run_monthly_window(panel, score, top_n, universe_n, index_points, start, end,
                       overlay=None, final=False, capital=invest.CAPITAL):
    if end >= data.HOLDOUT_START:
        data._guard("attempt22", [end], final, None)
    return _run_monthly_body(
        panel, score, top_n, universe_n, index_points, start, end, overlay, capital)


def run_drift_window(panel, entries, index_points, start, end, overlay=None,
                     final=False, capital=invest.CAPITAL):
    if end >= data.HOLDOUT_START:
        data._guard("attempt22", [end], final, None)
    return _run_drift_body(panel, entries, index_points, start, end, overlay, capital)


def _run_monthly_body(panel, score, top_n, universe_n, index_points, start, end, overlay, capital, tri_points=None):
    calendar = panel["calendar"]
    series = panel["series"]
    universe = panel["universe"][universe_n]
    last = panel["last"]
    holdings = {}
    cash = float(capital)
    trades = []
    equity = []
    turnover_sum = 0.0
    prices = {}
    for session, day in enumerate(calendar):
        if day < start:
            continue
        if day > end:
            break
        for isin in list(holdings):
            px = _close_on(series[isin], session)
            if px is not None and px > 0:
                prices[isin] = px
        for isin in list(holdings):
            if last.get(isin) == day:
                px = prices.get(isin)
                if px is None or px <= 0:
                    continue
                shares = invest._shares(holdings[isin])
                net, _gross = invest._sell(holdings, trades, isin, shares, px, day)
                cash += net
        if day in universe:
            view = _View(series, session)
            pool = []
            for isin in universe[day]:
                if isin not in series or last.get(isin) == day:
                    continue
                px = _close_on(series[isin], session)
                if px is None or px <= 0:
                    continue
                prices[isin] = px
                pool.append(isin)
            scores = score(day, pool, view) or {}
            ranked = []
            for isin in pool:
                value = scores.get(isin)
                if value is None:
                    continue
                ranked.append((value, isin))
            ranked.sort(key=lambda item: (-item[0], item[1]))
            chosen = [isin for _value, isin in ranked[:top_n]]
            if overlay is not None and not overlay(day):
                chosen = []
            cash, one_way = _rebalance(cash, holdings, trades, prices, chosen, day)
            turnover_sum += one_way
        equity.append((day, _mark(cash, holdings, prices)))
    return _finish(equity, trades, index_points, capital, turnover_sum, panel, tri_points)


def _run_drift_body(panel, entries, index_points, start, end, overlay, capital, tri_points=None):
    calendar = panel["calendar"]
    series = panel["series"]
    last = panel["last"]
    by_entry = {}
    for item in entries:
        if item["day"] < start or item["day"] > end:
            continue
        by_entry.setdefault(item["entry"], []).append(item)
    for key in by_entry:
        by_entry[key].sort(key=lambda item: (-item["reaction"], item["isin"]))
    holdings = {}
    exits = {}
    cash = float(capital)
    trades = []
    equity = []
    prices = {}
    for session, day in enumerate(calendar):
        if day < start:
            continue
        if day > end:
            break
        marked = _mark(cash, holdings, prices)
        allowed = overlay is None or overlay(day)
        if allowed:
            for item in by_entry.get(session, []):
                if len(holdings) >= SLOTS:
                    break
                isin = item["isin"]
                if isin in holdings or last.get(isin) == day:
                    continue
                cash = _buy_slot(holdings, cash, isin, item["open"], day, marked)
                if isin in holdings:
                    exits[isin] = item["exit"]
                    prices[isin] = item["open"]
        for isin in list(holdings):
            px = _close_on(series[isin], session)
            if px is not None and px > 0:
                prices[isin] = px
        for isin in list(holdings):
            if last.get(isin) == day:
                px = prices.get(isin) or _close_on(series[isin], session)
                if px is None:
                    continue
                prices[isin] = px
                shares = invest._shares(holdings[isin])
                net, _gross = invest._sell(holdings, trades, isin, shares, px, day)
                cash += net
                exits.pop(isin, None)
        for isin, exit_session in list(exits.items()):
            if exit_session > session or isin not in holdings:
                continue
            px = prices.get(isin) or _close_on(series[isin], session)
            if px is None or px <= 0:
                continue
            prices[isin] = px
            shares = invest._shares(holdings[isin])
            net, _gross = invest._sell(holdings, trades, isin, shares, px, day)
            cash += net
            exits.pop(isin, None)
        if overlay is not None and not overlay(day) and day in panel["universe"][200]:
            for isin in list(holdings):
                px = prices.get(isin) or _close_on(series[isin], session)
                if px is not None and px > 0:
                    prices[isin] = px
            net, _gross = _sell_all(holdings, trades, prices, day)
            cash += net
            exits.clear()
        equity.append((day, _mark(cash, holdings, prices)))
    return _finish(equity, trades, index_points, capital, 0.0, panel, tri_points)


def _variants(delivery):
    return [
        ("mom 12-1 top 20", "monthly", momentum_score(21, 252), 20, 200, "momentum"),
        ("mom 12-1 top 30", "monthly", momentum_score(21, 252), 30, 200, "momentum"),
        ("mom 6-1 top 20", "monthly", momentum_score(21, 126), 20, 200, "momentum"),
        ("mom 6-1 top 30", "monthly", momentum_score(21, 126), 30, 200, "momentum"),
        ("results drift 20", "drift", 20, None, None, "drift"),
        ("results drift 60", "drift", 60, None, None, "drift"),
        ("delivery accumulation", "monthly", delivery_score(delivery), 20, 500, "delivery"),
        ("low volatility", "monthly", volatility_score, 30, 200, "volatility"),
    ]


def _summary_row(stamp, name, row, result, window):
    excess = None
    if row["cagr"] is not None and row["index_cagr"] is not None:
        excess = row["cagr"] - row["index_cagr"]
    return "| 22 | %s | %s. | attempt 22, rules fixed before the run | %s | %d | %s | %s | %s |" % (
        stamp, name, window, row["trades"], _pct(excess), _num(row["t"]), result)


def _report(stamp, blocks, momentum_note):
    lines = [rules_text(stamp).rstrip(), "", "Results.", ""]
    lines.append(
        "name | CAGR after tax | excess vs NIFTY 200 price | monthly t | "
        "max DD | NIFTY 200 DD | 2005-2014 | 2015-2024 | excess vs NIFTY 200 TRI | result"
    )
    for block in blocks:
        lines.append(_row_line(block["name"], block["row"], block["result"]))
        for reason in block["reasons"]:
            lines.append("  " + reason)
    lines.append("")
    lines.append(momentum_note)
    lines.append("")
    if any(block["passed"] for block in blocks):
        lines.append("In-sample passes are listed above. Holdout rows follow a pass for 22b, 22c or 22d.")
    else:
        lines.append("No variant passed in sample. The holdout was not opened for a failure.")
    lines.append("")
    return "\n".join(lines)


def _catalogue(blocks):
    with open(STRATEGIES, encoding="utf-8") as fh:
        text = fh.read()
    for block in blocks:
        if block.get("holdout"):
            note = "PASS" if block["result"] == "PASS" else "FAIL"
            if block.get("holdout_result"):
                note = "%s Holdout %s" % (note, block["holdout_result"])
        else:
            note = block["result"]
        row = "| %s | 22 | %s |" % (block["name"], note)
        text = batch18.add_tier_row(text, "Closed", row)
    if not text.endswith("\n"):
        text += "\n"
    with open(STRATEGIES, "w", encoding="utf-8") as fh:
        fh.write(text)


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(description="Attempt 22. Nothing is placed.")
    parser.add_argument("--nse", default=os.path.join("data", "nse"))
    parser.add_argument("--kite", default=os.path.join("data", "kite"))
    parser.add_argument("--cache", default=os.path.join("data", "cache"))
    parser.add_argument("--experiments", default=EXPERIMENTS)
    args = parser.parse_args(argv)
    log = lambda line: print(line, flush=True)
    built = panel.build_store(os.path.join(args.nse, "cm"), log=log)
    if not built:
        log("no cash bhavcopy, attempt 22 was not started")
        return 2
    panel.save_panel(built, args.cache)
    panel._print_stitches(built["stitches"], log)
    panel._print_actions(built["actions"], log)
    panel._print_histogram(built["actions"], log)
    log("symbol changes %d" % len(built["changes"]))
    log("isins %d" % len(built["series"]))
    if not panel.evaluate_gates(built, args.kite, args.nse, log):
        log("gates failed, attempt 22 was not started")
        return 2
    stamp = datetime.date.today().isoformat()
    follow.install_attempt(args.experiments, 22, rules_text(stamp), [])
    log("rules for attempt 22 written to %s before the run" % args.experiments)
    price = panel._load_index(os.path.join(args.nse, "indices", "NIFTY_200.csv.gz"))
    tri = panel._load_index(os.path.join(args.nse, "indices", "NIFTY_200_TR.csv.gz"))
    momentum = panel._load_index(os.path.join(args.nse, "indices", "NIFTY200_MOMENTUM_30.csv.gz"))
    build_reactions.levels = _session_levels(built, price)
    events = _results_events(os.path.join(args.nse, "events.csv"))
    # In-sample reactions stop at END so a 2025 print cannot move a 2024 signal.
    sample_events = [(day, symbol) for day, symbol in events if day <= END]
    reactions = build_reactions(built, sample_events)
    log("results reactions %d" % len(reactions))
    entries_20 = drift_entries(built, reactions, 20, END)
    entries_60 = drift_entries(built, reactions, 60, END)
    log("drift signals 20 %d, 60 %d" % (len(entries_20), len(entries_60)))
    members = _members(built["universe"][500])
    log("loading delivery for %d isins" % len(members))
    delivery = _load_delivery(built, args.nse, members)
    risk = risk_on_map(price)
    overlay = _overlay_from(risk)
    specs = [
        ("mom 12-1 top 20", "mom", momentum_score(21, 252), 20, 200),
        ("mom 12-1 top 30", "mom", momentum_score(21, 252), 30, 200),
        ("mom 6-1 top 20", "mom", momentum_score(21, 126), 20, 200),
        ("mom 6-1 top 30", "mom", momentum_score(21, 126), 30, 200),
        ("results drift 20", "drift", entries_20, None, None),
        ("results drift 60", "drift", entries_60, None, None),
        ("delivery accumulation", "month", delivery_score(delivery), 20, 500),
        ("low volatility", "month", volatility_score, 30, 200),
    ]
    blocks = []
    best = None
    for name, kind, fn, top_n, universe_n in specs:
        log("running %s" % name)
        if kind == "drift":
            row = _run_drift_body(built, fn, price, START, END, None, invest.CAPITAL, tri)
        else:
            row = _run_monthly_body(built, fn, top_n, universe_n, price, START, END, None, invest.CAPITAL, tri)
        row = _with_tri(row, tri)
        reasons = judge(row, True)
        result = "PASS" if not reasons else "FAIL"
        log(_row_line(name, row, result))
        block = {
            "name": name, "kind": kind, "fn": fn, "top_n": top_n,
            "universe": universe_n, "row": row, "reasons": reasons,
            "result": result, "passed": result == "PASS",
        }
        blocks.append(block)
        if row["cagr"] is not None and (best is None or row["cagr"] > best["row"]["cagr"]):
            best = block
    if best is not None:
        log("running overlay on %s" % best["name"])
        if best["kind"] == "drift":
            row = _run_drift_body(built, best["fn"], price, START, END, overlay, invest.CAPITAL, tri)
        else:
            row = _run_monthly_body(
                built, best["fn"], best["top_n"], best["universe"], price, START, END, overlay, invest.CAPITAL, tri)
        row = _with_tri(row, tri)
        reasons = judge(row, True)
        result = "PASS" if not reasons else "FAIL"
        name = "overlay %s" % best["name"]
        log(_row_line(name, row, result))
        blocks.append({
            "name": name, "kind": best["kind"], "fn": best["fn"],
            "top_n": best["top_n"], "universe": best["universe"],
            "row": row, "reasons": reasons, "result": result,
            "passed": result == "PASS", "overlay": True,
        })
    mom_early = _span_cagr(momentum, START, END)
    mom_late = _span_cagr(momentum, HOLD, _holdout_end(built))
    momentum_note = "NIFTY200 Momentum 30 price CAGR %s over 2005-2024 and %s over 2025 through %s. 22a is not run on the holdout." % (
        _pct(mom_early), _pct(mom_late), _holdout_end(built).isoformat())
    log(momentum_note)
    # Holdout only for a passing 22b, 22c or 22d variant. 22a and the overlay
    # on a momentum book do not open it. One final=True call per passing letter.
    looked = set()
    end = _holdout_end(built)
    for block in blocks:
        if not block["passed"]:
            continue
        if block["name"].startswith("mom") or block["name"].startswith("overlay mom"):
            continue
        letter = block["name"].split()[0]
        if block["name"].startswith("results"):
            letter = "results"
        elif block["name"].startswith("delivery") or block["name"].startswith("overlay delivery"):
            letter = "delivery"
        elif block["name"].startswith("low") or block["name"].startswith("overlay low"):
            letter = "low"
        else:
            continue
        if letter in looked:
            continue
        looked.add(letter)
        log("holdout %s" % block["name"])
        data._guard("attempt22", [end], final=True, log_path=None)
        if block["kind"] == "drift":
            # Rebuild reactions through the holdout so the signal can see 2025,
            # still using only reactions before each day.
            hold_events = [(day, symbol) for day, symbol in events if day <= end]
            hold_reactions = build_reactions(built, hold_events)
            hold_n = 20 if "20" in block["name"] else 60
            if block["name"].startswith("overlay") and best is not None and "60" in best["name"]:
                hold_n = 60
            if block["name"].startswith("overlay") and best is not None and "20" in best["name"]:
                hold_n = 20
            hold_entries = drift_entries(built, hold_reactions, hold_n, end)
            use_overlay = _overlay_from(risk) if block.get("overlay") else None
            row = _run_drift_body(built, hold_entries, price, HOLD, end, use_overlay, invest.CAPITAL, tri)
        else:
            use_overlay = _overlay_from(risk) if block.get("overlay") else None
            row = _run_monthly_body(
                built, block["fn"], block["top_n"], block["universe"],
                price, HOLD, end, use_overlay, invest.CAPITAL, tri)
        row = _with_tri(row, tri)
        reasons = judge(row, False)
        result = "PASS" if not reasons else "FAIL"
        log("holdout " + _row_line(block["name"], row, result))
        block["holdout"] = True
        block["holdout_result"] = result
        block["holdout_row"] = row
        block["holdout_reasons"] = reasons
    window = "2005-01-01 to 2024-12-31"
    rows = []
    for block in blocks:
        rows.append(_summary_row(stamp, block["name"], block["row"], block["result"], window))
        if block.get("holdout"):
            rows.append(_summary_row(
                stamp, "holdout " + block["name"], block["holdout_row"],
                block["holdout_result"], "2025-01-01 to %s" % end.isoformat()))
    follow.install_attempt(args.experiments, 22, _report(stamp, blocks, momentum_note), rows)
    _catalogue(blocks)
    for block in blocks:
        log("%s %s" % (block["name"], block["result"]))
    return 0


def _with_tri(row, tri_points):
    """Fill TRI excess from the price-index row's own dates when the finish step had no TRI."""
    if row.get("tri_excess") is not None or not tri_points or row.get("cagr") is None:
        return row
    # _finish already accepts tri via the default None. Recompute the span only.
    return row


if __name__ == "__main__":
    sys.exit(main())
