"""Index-TRI portfolios for a long holding period. Standard library only.

A book holds one or more total-return indexes at target weights. Rebalance is
the first session of April. When bands are on, that rebalance is skipped
unless some weight is more than 5 points away from its target. Five points
exactly is not enough. The first purchase is not a band check.

The expense ratio is a drag on the index level between sessions. The default
is 0.3% a year for a broad index and 0.5% for a factor index. There is no
delivery brokerage. Gold is not an NSE index. The sleeve is GOLDBEES
(series EQ), adjusted only for its unit split, in
data/nse/indices/GOLD_ETF.csv.gz. That price is already net of the ETF's
charges, so the series is given no expense ratio. It is taxed as debt.

Tax. An equity sleeve held for more than 12 months is LTCG, 10% above
Rs 1,00,000 on a sale before 2024-07-23 and 12.5% above Rs 1,25,000 on or
after that date. An equity sleeve held for 12 months or less is STCG, 15%
before that date and 20% on or after it, the same schedule as invest.tax_due.
G-Sec and gold are taxed at 30% on the year's net gain, with no exemption.
A loss offsets gains of the same kind in that year. Nothing is carried forward.

The ending CAGR (and a SIP's XIRR) is after the sale on the last session and
the tax on that sale. Drawdown, the worst calendar year, the recovery and the
rolling CAGRs use the growth of the book before that final sale, so the exit
tax is not printed as a one-day crash. A SIP contribution is not part of that
growth.

A result that uses a sleeve on a session before that index's launch date is
marked "(back-test years included)".
"""

import datetime
import statistics

from india.research import invest

BROAD_EXPENSE = 0.003
FACTOR_EXPENSE = 0.005
BAND = 0.05
DEBT_RATE = 0.30
BACKTEST_MARK = "(back-test years included)"
_APRIL = (4,)


def expense_for(factor):
    """0.5% a year for a factor index, 0.3% for everything else."""
    if factor:
        return FACTOR_EXPENSE
    return BROAD_EXPENSE


def apply_expense(points, annual):
    """Chain the index and take the expense out of the level between sessions."""
    if not points:
        return []
    if annual <= 0:
        return list(points)
    out = [points[0]]
    for i in range(1, len(points)):
        prev_day, prev_level = out[-1]
        day, level = points[i]
        raw_prev = points[i - 1][1]
        gap = (day - prev_day).days
        if gap < 0:
            gap = 0
        drag = (1.0 - annual) ** (gap / 365.25)
        if raw_prev <= 0 or level <= 0 or prev_level <= 0:
            out.append((day, prev_level))
            continue
        out.append((day, prev_level * (level / raw_prev) * drag))
    return out


def first_sessions(days, months):
    """First date in each (year, month) whose month is in months."""
    seen = set()
    found = []
    for day in days:
        if day.month not in months:
            continue
        key = (day.year, day.month)
        if key in seen:
            continue
        seen.add(key)
        found.append(day)
    return found


def needs_rebalance(current, target, band=BAND):
    """True when any sleeve is more than `band` away from its target.

    Weights are fractions. 0.05 is five points. A gap of exactly the band
    does not rebalance.
    """
    names = set(current) | set(target)
    for name in names:
        gap = abs(current.get(name, 0.0) - target.get(name, 0.0))
        # 1e-9 of weight is a millionth of a point, so float dust on an
        # exact 5-point gap does not count as more than 5 points.
        if gap > band + 1e-9:
            return True
    return False


def before_launch(session, launch):
    """True when this session uses the index before its launch date."""
    if session is None or launch is None:
        return False
    return session < launch


def annotate(text, flagged):
    if flagged:
        return text + " " + BACKTEST_MARK
    return text


def xirr(flows, guess=0.1):
    """Annual rate for dated cash flows. Investments are negative.

    The year fraction is actual days over 365, which is what a spreadsheet
    XIRR uses. Returns None when the solver does not settle.
    """
    if not flows:
        return None
    start = flows[0][0]
    for day, _amount in flows:
        if day < start:
            start = day

    def years(day):
        return (day - start).days / 365.0

    def npv(rate):
        total = 0.0
        base = 1.0 + rate
        if base <= 0:
            return None
        for day, amount in flows:
            total += amount / (base ** years(day))
        return total

    def dnpv(rate):
        total = 0.0
        base = 1.0 + rate
        if base <= 0:
            return 0.0
        for day, amount in flows:
            t = years(day)
            if t == 0:
                continue
            total += -t * amount / (base ** (t + 1.0))
        return total

    rate = guess
    for _step in range(80):
        value = npv(rate)
        slope = dnpv(rate)
        if value is None or abs(slope) < 1e-14:
            return None
        nxt = rate - value / slope
        if nxt <= -0.999999:
            nxt = (rate - 0.999999) / 2.0
        if abs(nxt - rate) < 1e-12:
            return nxt
        rate = nxt
    value = npv(rate)
    if value is not None and abs(value) < 1e-4:
        return rate
    return None


def _shift_years(day, years):
    try:
        return day.replace(year=day.year + years)
    except ValueError:
        return day.replace(year=day.year + years, day=28)


def _month_ends(points):
    ends = []
    for i, (day, value) in enumerate(points):
        last = i + 1 == len(points) or points[i + 1][0].month != day.month or points[i + 1][0].year != day.year
        if last:
            ends.append((day, value))
    return ends


def rolling_cagr(points, years):
    """Min, median and max CAGR of windows that end on a month-end."""
    ends = _month_ends(points)
    found = []
    for day, value in ends:
        target = _shift_years(day, -years)
        start = None
        for sday, sval in ends:
            if sday <= target:
                start = (sday, sval)
            else:
                break
        if start is None:
            continue
        if (day - start[0]).days < int(years * 365.25) - 45:
            continue
        cagr = invest._cagr(start[1], value, start[0], day)
        if cagr is not None:
            found.append(cagr)
    if not found:
        return None, None, None
    return min(found), statistics.median(found), max(found)


def max_drawdown(points):
    peak = None
    worst = 0.0
    for _day, value in points:
        if peak is None or value > peak:
            peak = value
        if peak and peak > 0:
            drop = (peak - value) / peak
            if drop > worst:
                worst = drop
    return worst


def recovery_years(points):
    """Years from the peak of the worst drawdown until that peak is regained.

    Returns (years, recovered). years is None when the peak is not regained.
    """
    peak_v = None
    peak_i = 0
    worst = 0.0
    trough_i = 0
    peak_at = 0
    for i, (_day, value) in enumerate(points):
        if peak_v is None or value >= peak_v:
            peak_v = value
            peak_i = i
        if peak_v and peak_v > 0:
            drop = (peak_v - value) / peak_v
            if drop > worst:
                worst = drop
                trough_i = i
                peak_at = peak_i
    if worst <= 0:
        return 0.0, True
    peak_day, peak_value = points[peak_at]
    for day, value in points[trough_i:]:
        if value >= peak_value - 1e-9:
            return (day - peak_day).days / 365.25, True
    return None, False


def worst_calendar_year(points):
    """(year, return) of the worst year-end to year-end move. None if no year ends."""
    ends = {}
    first_value = points[0][1] if points else None
    first_year = points[0][0].year if points else None
    for day, value in points:
        ends[day.year] = value
    if not ends or first_value is None:
        return None
    worst = None
    previous = first_value
    # The first year is measured from the first point, which is already that year's start.
    seen_first = False
    for year in sorted(ends):
        value = ends[year]
        if not seen_first and year == first_year:
            seen_first = True
            if previous > 0:
                ret = value / previous - 1.0
            else:
                ret = 0.0
        elif previous > 0:
            ret = value / previous - 1.0
        else:
            ret = 0.0
        if worst is None or ret < worst[1]:
            worst = (year, ret)
        previous = value
    return worst


def _equity_tax(trades):
    if not trades:
        return 0.0
    return invest.tax_due(trades)


def _debt_tax(trades):
    gain = 0.0
    for trade in trades:
        gain += trade["gain"]
    if gain <= 0:
        return 0.0
    return gain * DEBT_RATE


def _tax_of(trades):
    equity = []
    debt = []
    for trade in trades:
        if trade["kind"] == "debt":
            debt.append(trade)
        else:
            equity.append(trade)
    return _equity_tax(equity) + _debt_tax(debt)


class _Book(object):
    def __init__(self, names):
        self.cash = 0.0
        self.lots = {}
        for name in names:
            self.lots[name] = []
        self.trades = []

    def units(self, name):
        total = 0.0
        for lot in self.lots[name]:
            total += lot["units"]
        return total

    def mark(self, price):
        total = self.cash
        for name, lots in self.lots.items():
            px = price.get(name)
            if px is None:
                continue
            for lot in lots:
                total += lot["units"] * px
        return total

    def weight(self, price):
        equity = self.mark(price)
        out = {}
        if equity <= 0:
            return out
        for name in self.lots:
            px = price.get(name) or 0.0
            out[name] = self.units(name) * px / equity
        return out

    def buy(self, name, money, day, px):
        if money <= 1e-8 or px <= 0 or self.cash <= 1e-8:
            return 0.0
        if money > self.cash:
            money = self.cash
        qty = money / px
        self.cash -= money
        self.lots[name].append({"units": qty, "basis": money, "buy": day})
        return money

    def sell(self, name, qty, day, px, kind):
        if qty <= 1e-12 or px <= 0:
            return 0.0
        have = self.units(name)
        if qty > have:
            qty = have
        left = qty
        while left > 1e-12 and self.lots[name]:
            lot = self.lots[name][0]
            take = lot["units"] if lot["units"] < left else left
            frac = take / lot["units"] if lot["units"] else 0.0
            basis = lot["basis"] * frac
            proceeds = take * px
            self.trades.append({
                "name": name,
                "kind": kind,
                "buy": lot["buy"],
                "sell": day,
                "gain": proceeds - basis,
            })
            lot["units"] -= take
            lot["basis"] -= basis
            left -= take
            if lot["units"] <= 1e-10:
                self.lots[name].pop(0)
        sold = qty - left
        self.cash += sold * px
        return sold * px

    def sell_all(self, day, price, kinds):
        for name in list(self.lots):
            qty = self.units(name)
            px = price.get(name)
            if qty > 1e-12 and px:
                self.sell(name, qty, day, px, kinds.get(name, "equity"))


def _rebalance(book, day, price, targets, kinds, allow_sell):
    """Move the book to targets. Returns True when something was traded."""
    equity = book.mark(price)
    if equity <= 0:
        return False
    traded = False
    if allow_sell:
        for name, target in targets.items():
            px = price.get(name)
            if not px:
                continue
            have = book.units(name) * px
            want = target * equity
            if have > want + 0.01:
                book.sell(name, (have - want) / px, day, px, kinds.get(name, "equity"))
                traded = True
    for name, target in targets.items():
        px = price.get(name)
        if not px:
            continue
        have = book.units(name) * px
        want = target * equity
        gap = want - have
        if gap > 0.01 and book.cash > 0.01:
            spent = book.buy(name, gap, day, px)
            if spent > 0.01:
                traded = True
    return traded


def _pay(book, day, price, kinds, unpaid):
    """Charge tax for unpaid trades. Sell to raise cash if the book is invested.

    A sale made to pay the tax is added to `unpaid` and taxed in the same charge.
    """
    if not unpaid:
        return 0.0
    tax = _tax_of(unpaid)
    for _turn in range(3):
        if book.cash + 1e-6 >= tax:
            break
        short = tax - book.cash
        held = []
        for name in book.lots:
            px = price.get(name)
            value = book.units(name) * px if px else 0.0
            if value > 0.01:
                held.append((name, value, px))
        if not held:
            break
        total = 0.0
        for _name, value, _px in held:
            total += value
        before = len(book.trades)
        for name, value, px in held:
            portion = short * (value / total)
            book.sell(name, portion / px, day, px, kinds.get(name, "equity"))
        unpaid.extend(book.trades[before:])
        tax = _tax_of(unpaid)
    if tax > book.cash:
        tax = book.cash
    if tax > 0:
        book.cash -= tax
    return tax


def _align(series, start, end):
    """Common window. Forward-fill a sleeve that has no print that session."""
    trimmed = {}
    firsts = []
    for name, points in series.items():
        kept = [(day, value) for day, value in points if day <= end and value > 0]
        if not kept:
            return None
        first = None
        for day, _value in kept:
            if day >= start:
                first = day
                break
        if first is None:
            return None
        firsts.append(first)
        trimmed[name] = kept
    begin = max(firsts)
    days = sorted(set(
        day for points in trimmed.values() for day, _value in points if begin <= day <= end
    ))
    if not days:
        return None
    prices = []
    for day_i, day in enumerate(days):
        prices.append({})
    for name, points in trimmed.items():
        level = None
        cursor = 0
        for day, value in points:
            if day <= begin:
                level = value
                cursor += 1
            else:
                break
        cursor = 0
        by_day = {}
        for day, value in points:
            by_day[day] = value
        running = None
        for day, value in points:
            if day <= days[0]:
                running = value
        if running is None:
            return None
        for i, day in enumerate(days):
            if day in by_day:
                running = by_day[day]
            prices[i][name] = running
    return begin, days, prices


def simulate(series, weights, kinds, start, end, capital=invest.CAPITAL,
             expenses=None, bands=False, band=BAND, sip=None, overlay=None,
             launches=None):
    """Run one portfolio.

    series maps a name to (date, level) total-return points before expenses.
    weights are the invested fractions. The rest is cash. kinds is "equity"
    or "debt". sip, when set, is the rupee contribution on the first session
    of each month and the book does not start with `capital`. overlay(day)
    is True when equity sleeves stay at their targets and False when they
    are moved to cash. launches maps a name to a date or None.
    """
    expenses = expenses or {}
    launches = launches or {}
    adjusted = {}
    for name, points in series.items():
        adjusted[name] = apply_expense(points, expenses.get(name, 0.0))
    aligned = _align(adjusted, start, end)
    if aligned is None:
        return None
    begin, days, prices = aligned
    names = list(weights)
    book = _Book(names)
    flows = []
    growth = []
    level = 1.0
    rebalance_days = []
    unpaid = []
    traded_n = 0
    overlay_on = True

    def price_of(i):
        return prices[i]

    def targets_for(on):
        out = {}
        for name, weight in weights.items():
            if (not on) and kinds.get(name) == "equity":
                out[name] = 0.0
            else:
                out[name] = weight
        return out

    month_starts = set(first_sessions(days, (1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12)))
    april = set(first_sessions(days, _APRIL))

    for i, day in enumerate(days):
        pre = book.mark(price_of(i))
        if i == 0:
            if sip:
                book.cash += sip
                flows.append((day, -float(sip)))
            else:
                book.cash += capital
                flows.append((day, -float(capital)))
            on = True if overlay is None else bool(overlay(day))
            overlay_on = on
            if _rebalance(book, day, price_of(i), targets_for(on), kinds, True):
                rebalance_days.append(day)
            level = 1.0
            growth.append((day, level))
            yesterday = book.mark(price_of(i))
        else:
            if yesterday > 0 and pre > 0:
                level *= pre / yesterday
            elif yesterday > 0 and pre <= 0:
                level *= 0.0
            on = True if overlay is None else bool(overlay(day))
            flipped = overlay is not None and on != overlay_on
            is_april = day in april
            is_month = day in month_starts
            # The band looks at the mix before today's contribution arrives.
            before_band = book.weight(price_of(i))
            if sip and is_month:
                book.cash += sip
                flows.append((day, -float(sip)))
            do_full = is_april or flipped or i == 0
            if do_full:
                skip = False
                if bands and is_april and not flipped and i != 0:
                    if not needs_rebalance(before_band, targets_for(on), band):
                        skip = True
                if skip:
                    if sip and is_month:
                        _rebalance(book, day, price_of(i), targets_for(on), kinds, False)
                else:
                    if _rebalance(book, day, price_of(i), targets_for(on), kinds, True):
                        rebalance_days.append(day)
                overlay_on = on
            elif sip and is_month:
                _rebalance(book, day, price_of(i), targets_for(on), kinds, False)
            before_tax = book.mark(price_of(i))
            year_ends = i + 1 == len(days) or days[i + 1].year != day.year
            if year_ends:
                fresh = book.trades[len(unpaid):]
                if fresh:
                    _pay(book, day, price_of(i), kinds, fresh)
                unpaid[:] = book.trades[:]
            post = book.mark(price_of(i))
            if before_tax > 0:
                level *= post / before_tax
            growth.append((day, level))
            yesterday = post
        traded_n = len(book.trades)

    path = list(growth)
    last_day = days[-1]
    last_price = prices[-1]
    book.sell_all(last_day, last_price, kinds)
    final_trades = book.trades[traded_n:]
    # Tax on the final sale, plus any earlier sale in that year not yet charged.
    # Year-end charging already ran on the last day before this sale, so only
    # the liquidation trades are still unpaid.
    exit_tax = _tax_of(final_trades)
    final_wealth = book.cash - exit_tax
    if final_wealth < 0:
        final_wealth = 0.0
    flows.append((last_day, final_wealth))
    flagged = False
    for name in names:
        if before_launch(begin, launches.get(name)):
            flagged = True
            break
    worst = worst_calendar_year(path)
    recovered_years, recovered = recovery_years(path)
    roll5 = rolling_cagr(path, 5)
    roll10 = rolling_cagr(path, 10)
    if sip:
        rate = xirr(flows)
        cagr = rate
    else:
        rate = None
        cagr = invest._cagr(capital, final_wealth, begin, last_day)
    return {
        "cagr": cagr,
        "xirr": rate if sip else cagr,
        "dd": max_drawdown(path),
        "worst_year": worst,
        "recovery_years": recovered_years,
        "recovered": recovered,
        "roll5": roll5,
        "roll10": roll10,
        "final": final_wealth,
        "start": begin,
        "end": last_day,
        "backtest": flagged,
        "rebalance_days": rebalance_days,
        "trades": len(book.trades),
        "flows": flows,
        "growth": path,
    }


def passes(row, bench):
    """The attempt 24 mark against a same-mode NIFTY 200 TRI result.

    CAGR at least 2 points higher, or within 1 point with max drawdown at
    least 15 points smaller. The minimum rolling 10-year CAGR must be higher.
    A missing 10-year window fails the rolling clause.
    """
    reasons = []
    if row["cagr"] is None or bench["cagr"] is None:
        reasons.append("CAGR is missing")
    else:
        gap = row["cagr"] - bench["cagr"]
        dd_gap = None
        if row["dd"] is not None and bench["dd"] is not None:
            dd_gap = bench["dd"] - row["dd"]
        cagr_ok = gap >= 0.02 - 1e-12
        same = abs(gap) <= 0.01 + 1e-12 and dd_gap is not None and dd_gap >= 0.15 - 1e-12
        if not cagr_ok and not same:
            reasons.append("CAGR is not 2 points higher, and the drawdown clause is not met")
    row_min = row["roll10"][0]
    bench_min = bench["roll10"][0]
    if row_min is None or bench_min is None:
        reasons.append("a rolling 10-year window is missing")
    elif not row_min > bench_min:
        reasons.append("minimum rolling 10-year CAGR is not higher")
    return not reasons, reasons
