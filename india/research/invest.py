"""Monthly rebalance harness for a long-only book. This is not attempt 22.

Inputs are a score function, the number of names, how often to rebalance,
and an optional overlay. The score is score(day, names, history). history.closes
returns that ISIN's bars up to and including the rebalance day, so a later
session is not visible. Higher scores are kept. The book holds the top N at
equal weight. frequency is "monthly" or "quarterly". overlay(day, chosen)
may replace the list, including with an empty list, which is cash.

Costs are the delivery schedule in india.costs. Tax is charged at each year
end on trades closed that year. A loss offsets gains in that year, highest
rate first. STCG is 15% on a sale before 2024-07-23 and 20% on a sale on or
after that date. A holding sold after its one-year anniversary is LTCG: 10%
above Rs 1,00,000 for a sale before that date, and 12.5% above Rs 1,25,000
on or after it. The two exemptions are separate. An open lot is not taxed.

A name whose last session falls inside the window is sold at that close.
The loss stays in the result.

final=False is the default. An end date on or after 2025-01-01 raises the
same holdout error as data.py. final=True logs that one look the same way.
The default end is 2024-12-31, so a normal call does not open the holdout.
"""

import datetime
import os
import sys
from decimal import Decimal, ROUND_HALF_UP

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from india import costs
from india.research import data
from india.research import harness
from india.research import regime

# Rs 10,00,000. The LTCG exemption is a fixed rupee amount, so the after-tax
# CAGR depends on the size of the book. This is the default.
CAPITAL = 1000000.0
START = datetime.date(2005, 1, 1)
END = datetime.date(2024, 12, 31)
# A sale on this date uses the later rates. The budget change is 23 July 2024.
STCG_CUTOFF = datetime.date(2024, 7, 23)
QUARTER_MONTHS = (1, 4, 7, 10)
_PAISE = Decimal("0.01")


def _anniversary(day):
    try:
        return day.replace(year=day.year + 1)
    except ValueError:
        return day.replace(year=day.year + 1, day=28)


def holding_long(buy, sell):
    """True when the sale is after the one-year anniversary. That is over 12 months."""
    return sell > _anniversary(buy)


def tax_due(trades):
    """Rupees of tax for one year's closed trades. Rounded to the paisa.

    Each trade has buy, sell, and gain. A negative gain is a loss. Losses
    reduce the year's gains before the exemption, in this order: STCG at 20%,
    STCG at 15%, LTCG at 12.5%, LTCG at 10%. LTCG left in each regime is taxed
    only above its own exemption.
    """
    buckets = {
        "stcg_new": Decimal("0"),
        "stcg_old": Decimal("0"),
        "ltcg_new": Decimal("0"),
        "ltcg_old": Decimal("0"),
    }
    for trade in trades:
        gain = Decimal(str(trade["gain"]))
        new = trade["sell"] >= STCG_CUTOFF
        long = holding_long(trade["buy"], trade["sell"])
        if long and new:
            key = "ltcg_new"
        elif long:
            key = "ltcg_old"
        elif new:
            key = "stcg_new"
        else:
            key = "stcg_old"
        buckets[key] += gain
    order = ("stcg_new", "stcg_old", "ltcg_new", "ltcg_old")
    loss = Decimal("0")
    for key in order:
        if buckets[key] < 0:
            loss += -buckets[key]
            buckets[key] = Decimal("0")
    for key in order:
        if loss <= 0:
            break
        use = buckets[key] if buckets[key] < loss else loss
        buckets[key] -= use
        loss -= use
    ltcg_old = buckets["ltcg_old"] - Decimal("100000")
    ltcg_new = buckets["ltcg_new"] - Decimal("125000")
    if ltcg_old < 0:
        ltcg_old = Decimal("0")
    if ltcg_new < 0:
        ltcg_new = Decimal("0")
    tax = (
        buckets["stcg_old"] * Decimal("0.15")
        + buckets["stcg_new"] * Decimal("0.20")
        + ltcg_old * Decimal("0.10")
        + ltcg_new * Decimal("0.125")
    )
    if tax < 0:
        tax = Decimal("0")
    return float(tax.quantize(_PAISE, rounding=ROUND_HALF_UP))


def _buy_cost(price, shares):
    return float(costs.delivery_buy(price, shares))


def _sell_cost(price, shares):
    return float(costs.delivery_sell(price, shares))


class _History(object):
    """Bars up to the current session. A later bar is not returned."""

    def __init__(self, series):
        self.series = series
        self.end_at = {}

    def closes(self, isin):
        rows = self.series.get(isin) or []
        end = self.end_at.get(isin, -1)
        if end < 0:
            return []
        return rows[:end + 1]


def _shares(lots):
    total = 0
    for lot in lots:
        total += lot["shares"]
    return total


def _sell(holdings, trades, isin, shares, price, day):
    """Close shares FIFO. Returns (cash in, gross notional)."""
    lots = holdings.get(isin) or []
    if shares <= 0:
        return 0.0, 0.0
    cost = _sell_cost(price, shares)
    net = shares * price - cost
    left = shares
    slices = []
    while left > 0 and lots:
        lot = lots[0]
        take = lot["shares"] if lot["shares"] < left else left
        slices.append((lot["buy"], take, lot["basis"] * take))
        lot["shares"] -= take
        left -= take
        if lot["shares"] == 0:
            lots.pop(0)
    if left != 0:
        raise ValueError("sell of %s is larger than the holding" % isin)
    if not lots:
        holdings.pop(isin, None)
    for buy, take, basis in slices:
        gain = net * (float(take) / float(shares)) - basis
        trades.append({
            "isin": isin,
            "buy": buy,
            "sell": day,
            "shares": take,
            "price": price,
            "gain": gain,
        })
    return net, shares * price


def _afford(cash, price):
    if price <= 0 or cash <= 0:
        return 0
    shares = int(cash // price)
    while shares > 0:
        spent = shares * price + _buy_cost(price, shares)
        if spent <= cash + 1e-6:
            return shares
        shares -= 1
    return 0


def _buy(holdings, cash, isin, shares, price, day):
    if shares <= 0:
        return cash
    extra = _buy_cost(price, shares)
    spent = shares * price + extra
    if spent > cash + 1e-6:
        return cash
    cash -= spent
    per = spent / float(shares)
    holdings.setdefault(isin, []).append({
        "shares": shares,
        "basis": per,
        "buy": day,
    })
    return cash


def _is_rebalance(day, previous, frequency):
    if previous is None:
        return True
    if frequency == "quarterly":
        return day.month != previous.month and day.month in QUARTER_MONTHS
    return (day.year, day.month) != (previous.year, previous.month)


def _cagr(start_value, end_value, start_day, end_day):
    if start_value <= 0 or end_value <= 0:
        return None
    years = (end_day - start_day).days / 365.25
    if years <= 0:
        return None
    return (end_value / start_value) ** (1.0 / years) - 1.0


def _max_drawdown(equity):
    peak = None
    worst = 0.0
    for value in equity:
        if peak is None or value > peak:
            peak = value
        if peak > 0:
            drop = (peak - value) / peak
            if drop > worst:
                worst = drop
    return worst


def _compound(returns):
    if not returns:
        return None
    growth = 1.0
    for value in returns:
        growth *= 1.0 + value
    return growth - 1.0


def _month_ends(points):
    """Last point of each calendar month. points are (date, value) in order."""
    ends = []
    for i, (day, value) in enumerate(points):
        last = i + 1 == len(points) or points[i + 1][0].month != day.month or points[i + 1][0].year != day.year
        if last:
            ends.append((day, value))
    return ends


def simulate(bars, score, top_n, frequency="monthly", overlay=None,
             index_closes=None, regime_points=None, start=None, end=None,
             final=False, capital=CAPITAL, universe=None, log_path=None):
    """Run one book. bars is ISIN -> list of dicts with date and adj_close.

    universe, when given, maps a rebalance date to the ISINs allowed that day.
    A missing date uses every name that trades that day. A name on its last
    session is sold at that close and is not bought again.
    """
    if frequency not in ("monthly", "quarterly"):
        raise ValueError("frequency must be monthly or quarterly")
    if top_n < 1:
        raise ValueError("top_n must be at least 1")
    start = start or START
    end = end or END
    if end >= data.HOLDOUT_START:
        data._guard("invest", [end], final, log_path)
    series = {}
    last_dates = {}
    price = {}
    calendar = set()
    for isin, rows in bars.items():
        kept = []
        for row in rows:
            day = row["date"]
            if day < start or day > end:
                continue
            close = row.get("adj_close")
            if close is None:
                close = row.get("close")
            if close is None or close <= 0:
                continue
            item = {
                "date": day,
                "adj_close": close,
                "turnover": row.get("turnover"),
                "symbol": row.get("symbol", ""),
            }
            kept.append(item)
            price.setdefault(isin, {})[day] = close
            calendar.add(day)
        if kept and rows[-1].get("last") and start <= rows[-1]["date"] <= end:
            last_dates[isin] = rows[-1]["date"]
            series[isin] = kept
        elif kept:
            series[isin] = kept
    days = sorted(calendar)
    history = _History(series)
    index_at = {}
    for point in index_closes or []:
        index_at[point[0]] = point[1]
    index_days = sorted(index_at)
    if isinstance(regime_points, dict):
        regimes = regime_points
    elif regime_points:
        regimes = regime.by_date(regime_points)
    else:
        regimes = {}

    def level_on(day):
        level = None
        for point_day in index_days:
            if point_day <= day:
                level = index_at[point_day]
            else:
                break
        return level

    holdings = {}
    cash = float(capital)
    trades = []
    equity = []
    turnover_sum = 0.0
    previous = None
    cursor = {}
    last_px = {}
    first_session = {}
    for day in days:
        key = (day.year, day.month)
        if key not in first_session:
            first_session[key] = day
        for isin, rows in series.items():
            pos = cursor.get(isin, 0)
            while pos < len(rows) and rows[pos]["date"] <= day:
                pos += 1
            cursor[isin] = pos
            if pos > 0:
                history.end_at[isin] = pos - 1
            if day in price.get(isin, {}):
                last_px[isin] = price[isin][day]
        for isin, last in list(last_dates.items()):
            if last == day and _shares(holdings.get(isin) or []):
                net, _gross = _sell(
                    holdings, trades, isin, _shares(holdings[isin]), price[isin][day], day)
                cash += net
        if _is_rebalance(day, previous, frequency):
            marked = cash
            for isin, lots in list(holdings.items()):
                px = last_px.get(isin)
                if px is None:
                    continue
                marked += _shares(lots) * px
            if universe is not None and day in universe:
                allowed = universe[day]
            else:
                allowed = list(series)
            pool = []
            for isin in allowed:
                if day in price.get(isin, {}) and last_dates.get(isin) != day:
                    pool.append(isin)
            scores = score(day, pool, history) or {}
            ranked = []
            for isin in pool:
                value = scores.get(isin)
                if value is None:
                    continue
                ranked.append((value, isin))
            ranked.sort(key=lambda item: (-item[0], item[1]))
            chosen = [isin for _score, isin in ranked[:top_n]]
            if overlay is not None:
                chosen = list(overlay(day, chosen))
            sold = 0.0
            chosen_set = set(chosen)
            for isin in list(holdings):
                if isin not in chosen_set:
                    have = _shares(holdings[isin])
                    px = last_px.get(isin)
                    if px is None or have <= 0:
                        continue
                    net, gross = _sell(holdings, trades, isin, have, px, day)
                    cash += net
                    sold += gross
            if chosen and marked > 0:
                target = marked / float(len(chosen))
                for isin in chosen:
                    if day not in price.get(isin, {}):
                        continue
                    px = price[isin][day]
                    have = _shares(holdings.get(isin) or [])
                    want = int(target // px)
                    if want < have:
                        net, gross = _sell(holdings, trades, isin, have - want, px, day)
                        cash += net
                        sold += gross
                    elif want > have:
                        buy_n = want - have
                        affordable = _afford(cash, px)
                        if buy_n > affordable:
                            buy_n = affordable
                        cash = _buy(holdings, cash, isin, buy_n, px, day)
            if marked > 0:
                turnover_sum += sold / marked
        marked = cash
        for isin, lots in holdings.items():
            px = last_px.get(isin)
            if px is None:
                continue
            marked += _shares(lots) * px
        equity.append((day, marked))
        previous = day
    if not equity:
        return {
            "cagr_before_tax": None,
            "cagr_after_tax": None,
            "excess_cagr": None,
            "monthly_excess_t": None,
            "max_drawdown": None,
            "worst_year": None,
            "turnover": None,
            "decades": {},
            "regimes": {},
            "trades": trades,
            "final_equity": capital,
            "final_equity_after_tax": capital,
            "tax_paid": 0.0,
            "open_shares": {},
            "monthly_excess": [],
        }
    by_year = {}
    for trade in trades:
        by_year.setdefault(trade["sell"].year, []).append(trade)
    tax_paid = 0.0
    for year in sorted(by_year):
        tax_paid += tax_due(by_year[year])
    # Tax leaves the book on the last session of the year it was earned.
    tax_at = {}
    running_tax = 0.0
    for i, (day, _value) in enumerate(equity):
        nxt_year = equity[i + 1][0].year if i + 1 < len(equity) else None
        if nxt_year != day.year and day.year in by_year:
            running_tax += tax_due(by_year[day.year])
        tax_at[i] = running_tax
    after = [(day, value - tax_at[i]) for i, (day, value) in enumerate(equity)]
    first_day = equity[0][0]
    last_day = equity[-1][0]
    before_end = equity[-1][1]
    after_end = after[-1][1]
    month_points = _month_ends(equity)
    month_rows = []
    previous_value = capital
    for day, value in month_points:
        if previous_value > 0:
            ret = value / previous_value - 1.0
        else:
            ret = 0.0
        month_rows.append((day, ret))
        previous_value = value
    excess = []
    previous_index = level_on(first_day)
    previous_strategy = capital
    for day, value in month_points:
        level = level_on(day)
        if previous_index is not None and previous_index > 0 and level is not None and previous_strategy > 0:
            strat = value / previous_strategy - 1.0
            idx = level / previous_index - 1.0
            excess.append(strat - idx)
        if level is not None:
            previous_index = level
        previous_strategy = value
    cagr_before = _cagr(capital, before_end, first_day, last_day)
    cagr_after = _cagr(capital, after_end, first_day, last_day)
    excess_cagr = None
    start_level = level_on(first_day)
    end_level = level_on(last_day)
    if start_level and end_level and cagr_before is not None:
        index_cagr = _cagr(start_level, end_level, first_day, last_day)
        if index_cagr is not None:
            excess_cagr = cagr_before - index_cagr
    years = (last_day - first_day).days / 365.25
    turnover = None
    if years > 0:
        turnover = turnover_sum / years
    year_ends = {}
    for day, value in equity:
        year_ends[day.year] = value
    worst = None
    previous_value = capital
    for year in sorted(year_ends):
        value = year_ends[year]
        if previous_value > 0:
            ret = value / previous_value - 1.0
        else:
            ret = 0.0
        if worst is None or ret < worst[1]:
            worst = (year, ret)
        previous_value = value
    decades = {}
    for decade in (2000, 2010, 2020):
        chunk = [ret for day, ret in month_rows if decade <= day.year < decade + 10]
        decades[decade] = _compound(chunk)
    regime_returns = {"up": [], "down": [], "sideways": []}
    for day, ret in month_rows:
        opened = first_session.get((day.year, day.month))
        kind = regimes.get(opened) if opened is not None else None
        if kind in regime_returns:
            regime_returns[kind].append(ret)
    regimes_out = {}
    for key, values in regime_returns.items():
        regimes_out[key] = _compound(values)
    open_shares = {}
    for isin, lots in holdings.items():
        count = _shares(lots)
        if count:
            open_shares[isin] = count
    return {
        "cagr_before_tax": cagr_before,
        "cagr_after_tax": cagr_after,
        "excess_cagr": excess_cagr,
        "monthly_excess_t": harness.t_stat(excess) if excess else None,
        "max_drawdown": _max_drawdown([value for _day, value in equity]),
        "worst_year": worst,
        "turnover": turnover,
        "decades": decades,
        "regimes": regimes_out,
        "trades": trades,
        "final_equity": before_end,
        "final_equity_after_tax": after_end,
        "tax_paid": tax_paid,
        "open_shares": open_shares,
        "monthly_excess": excess,
    }


def main(argv=None):
    """The harness is a library. Attempt 22 is not run from here."""
    print("invest harness ready. No attempt is run in this step.", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
