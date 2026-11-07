#!/usr/bin/env python3
"""Strategy harness. Trade signals and portfolio rebalances, one book each.

Idle rupees sit in the NIFTY 50 price series, so a quiet book is the market
and not a zero-interest account. Faber timing is the exception: its off state
is cash at 0. Dividends are excluded everywhere. Delivery costs, from
signal_lab.py, apply to stock buys and sells and to Faber switches. They do
not apply to the idle NIFTY sleeve or to the initial funding of that sleeve.

Window 2005-01-01 through 2024-12-31. Dates from 2025 on are not requested.

    python3 india/research/harness.py
"""

import bisect
import datetime
import os
import random
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from india import costs
from india import nse_market
from india.research import data
from india.research import regime
from india.research import signal_lab as lab
from india.research import ta

START = lab.START
END = lab.END
WARMUP = lab.WARMUP
CAPITAL = 1000000.0
SLOTS = 10
SLOT = CAPITAL / float(SLOTS)
RUNS = 100
SEED = lab.RANDOM_SEED
YEAR_DAYS = 365.25
EXPERIMENTS = lab.EXPERIMENTS
CATALOGUE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "STRATEGIES.md")

# Buy-side cost as a fraction of the traded value. Matches signal_lab.delivery.
_BUY_RATE = (lab.STT_PCT + lab.EXCHANGE_PCT + lab.SEBI_PCT + lab.STAMP_PCT) / 100.0
_BUY_RATE += (lab.EXCHANGE_PCT + lab.SEBI_PCT) / 100.0 * (lab.GST_PCT / 100.0)


def trade_cost(value, buying):
    """Rupees charged on one buy or one sell. A sell pays the DP charge once."""
    if value <= 0:
        return 0.0
    stt = value * lab.STT_PCT / 100.0
    exchange = value * lab.EXCHANGE_PCT / 100.0
    sebi = value * lab.SEBI_PCT / 100.0
    stamp = value * lab.STAMP_PCT / 100.0 if buying else 0.0
    gst = (exchange + sebi) * lab.GST_PCT / 100.0
    dp = 0.0 if buying else lab.DP_CHARGE
    return lab.BROKERAGE + stt + exchange + sebi + stamp + gst + dp


def shares_for(budget, price):
    """Whole shares whose buy value plus buy-side costs fit in the budget."""
    if budget <= 0 or price <= 0:
        return 0
    gross = budget / (1.0 + _BUY_RATE)
    return int(gross // price)


def batch1():
    """Twelve variants, three per family. Names are stable."""
    return [
        {"name": "turtle 20/10", "kind": "turtle", "entry_n": 20, "exit_n": 10, "up_only": False},
        {"name": "turtle 55/20", "kind": "turtle", "entry_n": 55, "exit_n": 20, "up_only": False},
        {"name": "turtle 55/20 up", "kind": "turtle", "entry_n": 55, "exit_n": 20, "up_only": True},
        {"name": "mom 12-1 K20", "kind": "mom", "k": 20, "filter": False},
        {"name": "mom 12-1 K30", "kind": "mom", "k": 30, "filter": False},
        {"name": "mom 12-1 K20 above200", "kind": "mom", "k": 20, "filter": True},
        {"name": "52w-high K20", "kind": "high", "k": 20, "filter": False},
        {"name": "52w-high K30", "kind": "high", "k": 30, "filter": False},
        {"name": "52w-high K20 above200", "kind": "high", "k": 20, "filter": True},
        {"name": "faber 10m", "kind": "faber", "months": 10},
        {"name": "faber 8m", "kind": "faber", "months": 8},
        {"name": "faber 12m", "kind": "faber", "months": 12},
    ]


def families(specs):
    """kind -> specs, preserving order. Each family has at most 3 variants."""
    order = []
    grouped = {}
    for spec in specs:
        kind = spec["kind"]
        if kind not in grouped:
            grouped[kind] = []
            order.append(kind)
        grouped[kind].append(spec)
    for kind in order:
        if len(grouped[kind]) > 3:
            raise ValueError("%s has %d variants" % (kind, len(grouped[kind])))
    return [(kind, grouped[kind]) for kind in order]


def prepare(seg):
    """Channels and ATR the batch needs. Base 20-day high and low already exist."""
    seg.atr20 = ta.atr_series(seg.h, seg.l, seg.c, 20)
    seg.high55 = ta.prior_high_series(seg.h, 55)
    seg.low10 = ta.prior_low_series(seg.l, 10)
    seg.high252 = ta.prior_high_series(seg.h, 252)
    seg.idx = {}
    for i, day in enumerate(seg.date):
        seg.idx[day] = i


def _highs(seg, n):
    if n == 20:
        return seg.high20
    if n == 55:
        return seg.high55
    raise ValueError("entry window %s" % n)


def _lows(seg, n):
    if n == 10:
        return seg.low10
    if n == 20:
        return seg.low20
    raise ValueError("exit window %s" % n)


def turtle_exit(seg, entry_i, last, atr, lows):
    """(exit index, fill, at_open). Stop first, then a close under the channel low.

    A gap through the stop fills at the open. The channel exit, a close below
    the prior low, leaves at the next open.
    """
    if atr is None or not atr > 0 or entry_i > last:
        return None
    entry = seg.o[entry_i]
    if not entry > 0:
        return None
    stop = entry - 2.0 * atr
    for j in range(entry_i, last + 1):
        opened = seg.o[j]
        if opened <= stop:
            return j, opened, True
        if seg.l[j] <= stop:
            return j, stop, False
        level = lows[j]
        if level is not None and seg.c[j] < level:
            if j + 1 <= last:
                return j + 1, seg.o[j + 1], True
            return j, seg.c[j], False
    return last, seg.c[last], False


def momentum_score(seg, i):
    """Close 21 sessions ago over close 252 sessions ago, minus one. Same segment."""
    if i < 252:
        return None
    base = seg.c[i - 252]
    recent = seg.c[i - 21]
    if not base > 0:
        return None
    return recent / base - 1.0


def high_score(seg, i):
    """Close divided by the prior 252-session high. Today is not inside that high."""
    level = seg.high252[i]
    if level is None or not level > 0:
        return None
    return seg.c[i] / level


def faber_on(closes, n):
    """True when the latest month-end close is above the average of the last n, itself included."""
    if closes is None or len(closes) < n or n <= 0:
        return None
    window = closes[-n:]
    avg = sum(window) / float(n)
    return closes[-1] > avg


def turnover_before(seg, entry_i, n=lab.TURNOVER_N):
    if entry_i < n:
        return None
    total = 0.0
    for j in range(entry_i - n, entry_i):
        total += seg.c[j] * seg.v[j]
    return total / float(n)


def collect_turtle(loaded, universe, regimes, entry_n, exit_n, up_only, warmup, start, end):
    """One open trade per symbol segment. The entry is the next open after the signal close."""
    trades = []
    for symbol in loaded:
        name = symbol["name"]
        for seg in symbol["segments"]:
            last = len(seg.date) - 1
            if last < 1:
                continue
            highs = _highs(seg, entry_n)
            lows = _lows(seg, exit_n)
            pending = []
            for i in range(last):
                if i < warmup:
                    continue
                level = highs[i]
                if level is None or not seg.c[i] > level:
                    continue
                entry_i = i + 1
                entry_day = seg.date[entry_i]
                if entry_day < start or entry_day > end:
                    continue
                members = universe.get(seg.date[i])
                if not members or name not in members:
                    continue
                if up_only and regimes.get(entry_day) != "up":
                    continue
                found = turtle_exit(seg, entry_i, last, seg.atr20[i], lows)
                if found is None:
                    continue
                exit_i, fill, at_open = found
                if shares_for(SLOT, seg.o[entry_i]) < 1:
                    continue
                pending.append({
                    "name": name,
                    "seg": seg,
                    "entry_i": entry_i,
                    "exit_i": exit_i,
                    "entry_date": entry_day,
                    "exit_date": seg.date[exit_i],
                    "entry": seg.o[entry_i],
                    "fill": fill,
                    "at_open": at_open,
                    "turnover": turnover_before(seg, entry_i),
                    "month": (entry_day.year, entry_day.month),
                })
            hits = [(trade["entry_i"], trade["exit_i"]) for trade in pending]
            keep = set(lab.take_one_at_a_time(hits))
            for trade in pending:
                if trade["entry_i"] in keep:
                    trades.append(trade)
    trades.sort(key=lambda trade: (trade["entry_date"], trade["name"]))
    return trades


def build_pools(loaded, universe, warmup, start, end):
    """Eligible random entries by calendar month. ATR must be positive so the stop exists."""
    pools = {}
    for sym_i, symbol in enumerate(loaded):
        name = symbol["name"]
        for seg_i, seg in enumerate(symbol["segments"]):
            last = len(seg.date) - 1
            for entry_i in range(1, last + 1):
                signal_i = entry_i - 1
                if signal_i < warmup:
                    continue
                entry_day = seg.date[entry_i]
                if entry_day < start or entry_day > end:
                    continue
                members = universe.get(seg.date[signal_i])
                if not members or name not in members:
                    continue
                atr = seg.atr20[signal_i]
                if atr is None or not atr > 0:
                    continue
                if shares_for(SLOT, seg.o[entry_i]) < 1:
                    continue
                key = (entry_day.year, entry_day.month)
                pools.setdefault(key, []).append((sym_i, seg_i, entry_i))
    for key in pools:
        pools[key].sort()
    return pools


class Book(object):
    """Stocks plus a NIFTY sleeve. park=False leaves sale proceeds in cash."""

    def __init__(self, capital, park=True):
        self.cash = float(capital)
        self.nifty_shares = 0.0
        self.pos = {}
        self.park = park

    def available(self, nifty_px):
        sleeve = self.nifty_shares * nifty_px if nifty_px > 0 else 0.0
        return self.cash + sleeve

    def fund_nifty(self, nifty_px):
        """Move cash into the sleeve at this price. No cost: it is funding, not a signal."""
        if self.park and self.cash > 0 and nifty_px > 0:
            self.nifty_shares += self.cash / nifty_px
            self.cash = 0.0

    def raise_cash(self, amount, nifty_px):
        if self.cash >= amount or amount <= 0 or not nifty_px > 0:
            return
        need = amount - self.cash
        take = min(self.nifty_shares, need / nifty_px)
        self.nifty_shares -= take
        self.cash += take * nifty_px

    def sweep(self, nifty_px):
        self.fund_nifty(nifty_px)

    def stock_value(self, day, field):
        total = 0.0
        for name in self.pos:
            pos = self.pos[name]
            seg = pos["seg"]
            i = None if seg is None else seg.idx.get(day)
            if i is None:
                px = pos["last"]
            else:
                px = seg.o[i] if field == "o" else seg.c[i]
                pos["last"] = px
            total += pos["shares"] * px
        return total

    def value(self, day, nifty_px, field):
        return self.cash + self.nifty_shares * nifty_px + self.stock_value(day, field)

    def buy(self, name, seg, shares, price, nifty_px):
        if shares < 1 or not price > 0:
            return 0
        held = self.pos.get(name)
        if held is not None and held["seg"] is not seg:
            self.sell(name, held["shares"], held["last"], nifty_px)
        affordable = shares_for(self.available(nifty_px), price)
        shares = min(shares, affordable)
        if shares < 1:
            return 0
        value = shares * price
        cost = trade_cost(value, True)
        self.raise_cash(value + cost, nifty_px)
        if self.cash + 1e-6 < value + cost:
            self.sweep(nifty_px)
            return 0
        self.cash -= value + cost
        held = self.pos.get(name)
        if held is None:
            self.pos[name] = {"shares": shares, "seg": seg, "last": price}
        else:
            held["shares"] += shares
            held["last"] = price
        self.sweep(nifty_px)
        return shares

    def sell(self, name, shares, price, nifty_px):
        pos = self.pos.get(name)
        if pos is None or shares <= 0 or not price > 0:
            return
        shares = min(shares, pos["shares"])
        if shares <= 0:
            return
        value = shares * price
        cost = trade_cost(value, False)
        self.cash += value - cost
        pos["shares"] -= shares
        pos["last"] = price
        if pos["shares"] <= 0:
            del self.pos[name]
        if self.park:
            self.sweep(nifty_px)

    def buy_index(self, nifty_px):
        """Spend cash on the index and pay buy-side costs. Used by Faber, not by the sleeve."""
        if not nifty_px > 0 or self.cash <= 0:
            return
        value = self.cash / (1.0 + _BUY_RATE)
        cost = trade_cost(value, True)
        self.nifty_shares += value / nifty_px
        self.cash -= value + cost

    def sell_index(self, nifty_px):
        if not nifty_px > 0 or self.nifty_shares <= 0:
            return
        value = self.nifty_shares * nifty_px
        cost = trade_cost(value, False)
        self.cash += value - cost
        self.nifty_shares = 0.0


def simulate_trades(trades, calendar, nifty, capital=CAPITAL, slots=SLOTS):
    """Fixed slot size. Free slots and leftover sleeve earn the NIFTY price."""
    by_entry = {}
    for trade in trades:
        by_entry.setdefault(trade["entry_date"], []).append(trade)
    for day in by_entry:
        by_entry[day].sort(key=lambda trade: (
            -(trade["turnover"] if trade["turnover"] is not None else -1.0), trade["name"]))
    book = Book(capital, park=True)
    book.fund_nifty(nifty[calendar[0]]["open"])
    slot = capital / float(slots)
    equity = []
    for day in calendar:
        nopen = nifty[day]["open"]
        nclose = nifty[day]["close"]
        # An open exit frees the name only for later days. Same-day re-entry is refused.
        left_today = set()
        for name in list(book.pos):
            pos = book.pos[name]
            if pos.get("exit_date") == day and pos.get("at_open"):
                book.sell(name, pos["shares"], pos["fill"], nopen)
                left_today.add(name)
        room = slots - len(book.pos)
        for trade in by_entry.get(day, []):
            if room <= 0:
                break
            name = trade["name"]
            if name in book.pos or name in left_today:
                continue
            shares = shares_for(slot, trade["entry"])
            got = book.buy(name, trade["seg"], shares, trade["entry"], nopen)
            if got < 1:
                continue
            pos = book.pos[name]
            pos["exit_date"] = trade["exit_date"]
            pos["fill"] = trade["fill"]
            pos["at_open"] = trade["at_open"]
            room -= 1
            if trade["exit_date"] == day and trade["at_open"]:
                book.sell(name, pos["shares"], trade["fill"], nopen)
                left_today.add(name)
        for name in list(book.pos):
            pos = book.pos[name]
            if pos.get("exit_date") == day and not pos.get("at_open"):
                book.sell(name, pos["shares"], pos["fill"], nclose)
        equity.append(book.value(day, nclose, "c"))
    return equity


def tradable(by_name, name, signal, reb):
    """Signal bar and the next session's open are consecutive bars of one segment."""
    loc = by_name.get(name)
    if loc is None:
        return False
    here = loc.get(signal)
    nxt = loc.get(reb)
    if here is None or nxt is None:
        return False
    if here[0] is not nxt[0]:
        return False
    return nxt[1] == here[1] + 1


def select_names(spec, signal, reb, universe, by_name, above, rng):
    """Top K by the spec's score, or a random K. An off filter selects nobody."""
    if spec.get("filter") and not above.get(signal):
        return []
    members = universe.get(signal)
    if not members:
        return []
    ranked = []
    pool = []
    for name in members:
        if not tradable(by_name, name, signal, reb):
            continue
        pool.append(name)
        if rng is not None:
            continue
        seg, i = by_name[name][signal]
        if spec["kind"] == "mom":
            score = momentum_score(seg, i)
        else:
            score = high_score(seg, i)
        if score is None:
            continue
        ranked.append((score, name))
    if rng is not None:
        return _sample(rng, pool, spec["k"])
    ranked.sort(key=lambda item: (-item[0], item[1]))
    return [name for _score, name in ranked[:spec["k"]]]


def _sample(rng, names, k):
    """Sample is sorted first so a seed does not depend on set order."""
    ordered = sorted(names)
    if len(ordered) <= k:
        return ordered
    return rng.sample(ordered, k)


def simulate_portfolio(pairs, picks, calendar, nifty, by_name, capital=CAPITAL, park=True):
    """Rebalance at the open. Each selected name gets an equal share of the book."""
    book = Book(capital, park=park)
    book.fund_nifty(nifty[calendar[0]]["open"])
    reb_of = {}
    for signal, reb in pairs:
        reb_of[reb] = signal
    equity = []
    for day in calendar:
        nopen = nifty[day]["open"]
        nclose = nifty[day]["close"]
        signal = reb_of.get(day)
        if signal is not None:
            _rebalance(book, picks.get(signal, []), day, nopen, by_name)
        _exit_segments(book, day, nclose)
        equity.append(book.value(day, nclose, "c"))
    return equity


def _rebalance(book, names, day, nifty_open, by_name):
    equity = book.value(day, nifty_open, "o")
    targets = {}
    count = len(names)
    if count:
        budget = equity / float(count)
        for name in names:
            seg, i = by_name[name][day]
            price = seg.o[i]
            targets[name] = shares_for(budget, price)
    for name in list(book.pos):
        want = targets.get(name, 0)
        have = book.pos[name]["shares"]
        if have > want:
            seg = book.pos[name]["seg"]
            i = seg.idx.get(day)
            price = seg.o[i] if i is not None else book.pos[name]["last"]
            book.sell(name, have - want, price, nifty_open)
    for name in names:
        want = targets.get(name, 0)
        have = book.pos[name]["shares"] if name in book.pos else 0
        if want > have:
            seg, i = by_name[name][day]
            book.buy(name, seg, want - have, seg.o[i], nifty_open)
    book.sweep(nifty_open)


def _exit_segments(book, day, nifty_px):
    """A break starts the next segment. Sell at this segment's last close."""
    for name in list(book.pos):
        seg = book.pos[name]["seg"]
        if seg is not None and seg.date[-1] == day:
            book.sell(name, book.pos[name]["shares"], seg.c[seg.idx[day]], nifty_px)


def simulate_faber(pairs, holds, calendar, nifty, capital=CAPITAL):
    """Hold the index, or cash at 0. Switching pays delivery costs. The sleeve is the position."""
    book = Book(capital, park=False)
    reb_of = {}
    for signal, reb in pairs:
        reb_of[reb] = signal
    holding = False
    equity = []
    for day in calendar:
        nopen = nifty[day]["open"]
        nclose = nifty[day]["close"]
        signal = reb_of.get(day)
        if signal is not None:
            want = bool(holds.get(signal))
            if want and not holding:
                book.buy_index(nopen)
                holding = book.nifty_shares > 0
            elif not want and holding:
                book.sell_index(nopen)
                holding = False
        equity.append(book.cash + book.nifty_shares * nclose)
    return equity


def faber_holds(pairs, month_ends, n, rng):
    """signal day -> hold?. rng set means each rebalance is a coin flip.

    month_ends is (date, close) for every month-end, including months before
    the window, so the first year already has a full average.
    """
    closes = []
    end_index = {}
    for day, close in month_ends:
        closes.append(close)
        end_index[day] = len(closes)
    out = {}
    for signal, _reb in pairs:
        if rng is not None:
            out[signal] = rng.randrange(2) == 1
            continue
        idx = end_index.get(signal)
        if idx is None:
            out[signal] = False
            continue
        flag = faber_on(closes[:idx], n)
        out[signal] = bool(flag) if flag is not None else False
    return out


def t_stat(values):
    """One-sample t. Sample standard deviation, one observation per month."""
    n = len(values)
    if n < 2:
        return None
    mean = sum(values) / float(n)
    var = 0.0
    for value in values:
        var += (value - mean) ** 2
    var /= float(n - 1)
    if var == 0.0:
        if mean > 0:
            return float("inf")
        if mean < 0:
            return float("-inf")
        return 0.0
    return mean / ((var ** 0.5) / (n ** 0.5))


def _mean(values):
    if not values:
        return None
    return sum(values) / float(len(values))


def path_stats(dates, equity, capital, nifty, regimes):
    """CAGR, drawdown, yearly returns, and monthly excess over NIFTY."""
    empty = {
        "cagr": None, "max_dd": None, "calmar": None, "worst_year": None,
        "yearly": {}, "final": capital, "excess": None, "t": None,
        "early": None, "late": None, "up": None, "down": None, "sideways": None,
        "n_months": 0,
    }
    if not dates or not capital > 0 or len(equity) != len(dates):
        return empty
    final = equity[-1]
    days = (dates[-1] - dates[0]).days
    if days <= 0 or not final > 0:
        cagr = None
    else:
        years = days / YEAR_DAYS
        cagr = ((final / float(capital)) ** (1.0 / years) - 1.0) * 100.0
    peak = float(capital)
    max_dd = 0.0
    for value in [float(capital)] + [float(item) for item in equity]:
        if value > peak:
            peak = value
        if peak > 0:
            dd = (value - peak) / peak * 100.0
            if dd < max_dd:
                max_dd = dd
    year_end = {}
    for day, value in zip(dates, equity):
        year_end[day.year] = value
    yearly = {}
    worst = None
    prev = float(capital)
    for year in range(min(year_end), max(year_end) + 1):
        if year not in year_end:
            continue
        value = year_end[year]
        if prev > 0:
            ret = (value / prev - 1.0) * 100.0
            yearly[year] = ret
            if worst is None or ret < worst:
                worst = ret
        prev = value
    calmar = None
    if cagr is not None and max_dd < 0:
        calmar = cagr / abs(max_dd)
    excess = _monthly(dates, equity, capital, nifty, regimes)
    excess.update({
        "cagr": cagr, "max_dd": max_dd, "calmar": calmar,
        "worst_year": worst, "yearly": yearly, "final": final,
    })
    return excess


def _monthly(dates, equity, capital, nifty, regimes):
    first = {}
    last_i = {}
    for i, day in enumerate(dates):
        key = (day.year, day.month)
        if key not in first:
            first[key] = day
        last_i[key] = i
    base = nifty[dates[0]]["open"]
    prev_eq = float(capital)
    prev_n = base
    rows = []
    for key in sorted(last_i):
        i = last_i[key]
        day = dates[i]
        eq = equity[i]
        nclose = nifty[day]["close"]
        if prev_eq > 0 and prev_n > 0 and eq > 0 and nclose > 0:
            sret = eq / prev_eq - 1.0
            nret = nclose / prev_n - 1.0
            rows.append((key[0], (sret - nret) * 100.0, regimes.get(first[key])))
        if eq > 0:
            prev_eq = eq
        if nclose > 0:
            prev_n = nclose
    buckets = {"up": [], "down": [], "sideways": []}
    for _year, excess, kind in rows:
        if kind in buckets:
            buckets[kind].append(excess)
    values = [row[1] for row in rows]
    return {
        "excess": _mean(values),
        "t": t_stat(values),
        "early": _mean([row[1] for row in rows if row[0] <= 2014]),
        "late": _mean([row[1] for row in rows if row[0] >= 2015]),
        "up": _mean(buckets["up"]),
        "down": _mean(buckets["down"]),
        "sideways": _mean(buckets["sideways"]),
        "n_months": len(values),
    }


def nifty_path(calendar, nifty, capital=CAPITAL):
    """Buy at the first open, mark at each close. No costs and no dividends."""
    base = nifty[calendar[0]]["open"]
    equity = []
    for day in calendar:
        equity.append(capital * nifty[day]["close"] / base)
    return equity


def cagr_of(dates, equity, capital):
    if not dates or not capital > 0 or not equity or not equity[-1] > 0:
        return None
    days = (dates[-1] - dates[0]).days
    if days <= 0:
        return None
    years = days / YEAR_DAYS
    return ((equity[-1] / float(capital)) ** (1.0 / years) - 1.0) * 100.0


def judge(block, nifty):
    """PASS when every clause holds. The two book paths are alternatives."""
    reasons = []
    if block["t"] is None or not block["t"] > 3:
        reasons.append("excess t %s is not above 3" % _num(block["t"]))
    if block["early"] is None or not block["early"] > 0:
        reasons.append("2005-2014 excess %s is not above 0" % _pct(block["early"]))
    if block["late"] is None or not block["late"] > 0:
        reasons.append("2015-2024 excess %s is not above 0" % _pct(block["late"]))
    for key in ("up", "down", "sideways"):
        if block[key] is None or not block[key] > 0:
            reasons.append("%s %s is not above 0" % (key, _pct(block[key])))
    if block["beats"] is None or block["beats"] < 95:
        got = "n/a" if block["beats"] is None else str(block["beats"])
        reasons.append("beats random %s of 100, need 95" % got)
    if block["large_excess"] is None or not block["large_excess"] > 0:
        reasons.append("large-cap excess %s is not above 0" % _pct(block["large_excess"]))
    path_dd = (
        block["cagr"] is not None and nifty.get("cagr") is not None
        and block["max_dd"] is not None and nifty.get("max_dd") is not None
        and block["cagr"] >= nifty["cagr"] + 3.0
        and block["max_dd"] >= nifty["max_dd"] - 10.0)
    path_calmar = (
        block["cagr"] is not None and nifty.get("cagr") is not None
        and block["calmar"] is not None and nifty.get("calmar") is not None
        and block["cagr"] >= nifty["cagr"]
        and block["calmar"] >= 1.5 * nifty["calmar"])
    if not path_dd and not path_calmar:
        reasons.append(
            "neither path clears: CAGR %s vs NIFTY %s, max DD %s vs %s, ratio %s vs %s" % (
                _pct(block["cagr"]), _pct(nifty.get("cagr")),
                _pct(block["max_dd"]), _pct(nifty.get("max_dd")),
                _ratio(block["calmar"]), _ratio(nifty.get("calmar"))))
    return {"result": "PASS" if not reasons else "FAIL", "reasons": reasons}


def _pct(value):
    if value is None:
        return "n/a"
    return "%+.3f%%" % value


def _num(value):
    if value is None:
        return "n/a"
    return "%+.2f" % value


def _ratio(value):
    if value is None:
        return "n/a"
    return "%.3f" % value


def _beats(real, others):
    if real is None:
        return 0
    wins = 0
    for other in others:
        if other is not None and real > other:
            wins += 1
    return wins


def _replace_turtle(trades, pools, loaded, regimes, exit_n, up_only, rng):
    """One random same-month entry per real trade, with the same channel exit and stop."""
    out = []
    lows_n = exit_n
    for trade in trades:
        pool = pools.get(trade["month"])
        if not pool:
            continue
        for _try in range(8):
            sym_i, seg_i, entry_i = pool[rng.randrange(len(pool))]
            seg = loaded[sym_i]["segments"][seg_i]
            entry_day = seg.date[entry_i]
            if up_only and regimes.get(entry_day) != "up":
                continue
            found = turtle_exit(seg, entry_i, len(seg.date) - 1, seg.atr20[entry_i - 1], _lows(seg, lows_n))
            if found is None:
                continue
            exit_i, fill, at_open = found
            out.append({
                "name": loaded[sym_i]["name"],
                "seg": seg,
                "entry_i": entry_i,
                "exit_i": exit_i,
                "entry_date": entry_day,
                "exit_date": seg.date[exit_i],
                "entry": seg.o[entry_i],
                "fill": fill,
                "at_open": at_open,
                "turnover": turnover_before(seg, entry_i),
                "month": trade["month"],
            })
            break
    return out


def _portfolio_picks(spec, pairs, universe, by_name, above, rng):
    picks = {}
    for signal, reb in pairs:
        picks[signal] = select_names(spec, signal, reb, universe, by_name, above, rng)
    return picks


def score_turtle(spec, ctx, universe, pools, runs, seed, with_random, log=None):
    trades = collect_turtle(
        ctx["loaded"], universe, ctx["regimes"], spec["entry_n"], spec["exit_n"],
        spec["up_only"], ctx["warmup"], ctx["start"], ctx["end"])
    equity = simulate_trades(trades, ctx["calendar"], ctx["nifty"])
    block = path_stats(ctx["calendar"], equity, CAPITAL, ctx["nifty"], ctx["regimes"])
    block["trades"] = len(trades)
    others = []
    if with_random:
        for run_i in range(runs):
            _progress(log, run_i, runs)
            rng = random.Random(seed + run_i)
            sample = _replace_turtle(
                trades, pools, ctx["loaded"], ctx["regimes"], spec["exit_n"], spec["up_only"], rng)
            path = simulate_trades(sample, ctx["calendar"], ctx["nifty"])
            others.append(cagr_of(ctx["calendar"], path, CAPITAL))
    block["beats"] = _beats(block["cagr"], others) if with_random else None
    return block


def score_portfolio(spec, ctx, universe, runs, seed, with_random, log=None):
    picks = _portfolio_picks(spec, ctx["pairs"], universe, ctx["by_name"], ctx["above"], None)
    equity = simulate_portfolio(ctx["pairs"], picks, ctx["calendar"], ctx["nifty"], ctx["by_name"])
    block = path_stats(ctx["calendar"], equity, CAPITAL, ctx["nifty"], ctx["regimes"])
    block["trades"] = sum(len(picks[key]) for key in picks)
    others = []
    if with_random:
        for run_i in range(runs):
            _progress(log, run_i, runs)
            rng = random.Random(seed + run_i)
            random_picks = _portfolio_picks(
                spec, ctx["pairs"], universe, ctx["by_name"], ctx["above"], rng)
            path = simulate_portfolio(
                ctx["pairs"], random_picks, ctx["calendar"], ctx["nifty"], ctx["by_name"])
            others.append(cagr_of(ctx["calendar"], path, CAPITAL))
    block["beats"] = _beats(block["cagr"], others) if with_random else None
    return block


def score_faber(spec, ctx, runs, seed, with_random, log=None):
    holds = faber_holds(ctx["pairs"], ctx["month_ends"], spec["months"], None)
    equity = simulate_faber(ctx["pairs"], holds, ctx["calendar"], ctx["nifty"])
    block = path_stats(ctx["calendar"], equity, CAPITAL, ctx["nifty"], ctx["regimes"])
    block["trades"] = sum(1 for key in holds if holds[key])
    others = []
    if with_random:
        for run_i in range(runs):
            _progress(log, run_i, runs)
            rng = random.Random(seed + run_i)
            coin = faber_holds(ctx["pairs"], ctx["month_ends"], spec["months"], rng)
            path = simulate_faber(ctx["pairs"], coin, ctx["calendar"], ctx["nifty"])
            others.append(cagr_of(ctx["calendar"], path, CAPITAL))
    block["beats"] = _beats(block["cagr"], others) if with_random else None
    return block


def large_excess(spec, ctx):
    """Mean monthly excess of the top-100 book. Faber has no stock universe, so it is unchanged."""
    if spec["kind"] == "faber":
        return None
    if spec["kind"] == "turtle":
        block = score_turtle(spec, ctx, ctx["top100"], None, 0, 0, False)
    else:
        block = score_portfolio(spec, ctx, ctx["top100"], 0, 0, False)
    return block["excess"]


def score_variant(spec, index, ctx, runs, log=None):
    seed = SEED + index * 1000
    if spec["kind"] == "turtle":
        pools = ctx["pools"] if not spec["up_only"] else ctx["pools_up"]
        block = score_turtle(spec, ctx, ctx["top200"], pools, runs, seed, True, log)
    elif spec["kind"] == "faber":
        block = score_faber(spec, ctx, runs, seed, True, log)
    else:
        block = score_portfolio(spec, ctx, ctx["top200"], runs, seed, True, log)
    if spec["kind"] == "faber":
        block["large_excess"] = block["excess"]
    else:
        block["large_excess"] = large_excess(spec, ctx)
    block["name"] = spec["name"]
    block["kind"] = spec["kind"]
    return block


def month_ends(points):
    """(date, close) of the last session of each calendar month, in order."""
    last = {}
    for day, close in points:
        last[(day.year, day.month)] = (day, close)
    return [last[key] for key in sorted(last)]


def month_pairs(all_days, calendar):
    """(month-end, next session) when that next session is inside the window.

    all_days includes sessions before the window, so a December signal can
    rebalance on the first session of January.
    """
    inside = set(calendar)
    last = {}
    nxt = {}
    for i, day in enumerate(all_days):
        last[(day.year, day.month)] = day
        if i + 1 < len(all_days):
            nxt[day] = all_days[i + 1]
    pairs = []
    for key in sorted(last):
        signal = last[key]
        reb = nxt.get(signal)
        if reb is not None and reb in inside:
            pairs.append((signal, reb))
    return pairs


def nifty_above(points, n=200):
    """date -> close above the n-day average of closes through that date."""
    closes = []
    out = {}
    total = 0.0
    for day, close in points:
        closes.append(close)
        total += close
        if len(closes) > n:
            total -= closes[-n - 1]
        if len(closes) >= n:
            out[day] = close > (total / float(n))
    return out


def load_context(root, start=START, end=END, warmup=WARMUP, log=None, final=False, log_path=None):
    emit = log or (lambda line: None)
    loaded, books = lab._books(root, end, emit, final=final, log_path=log_path)
    for symbol in loaded:
        for seg in symbol["segments"]:
            prepare(seg)
    segments = lab.load_symbol(root, lab.NIFTY, end=end, final=final, log_path=log_path)
    nifty = {}
    points = []
    for seg_i, seg in enumerate(segments):
        for i, day in enumerate(seg.date):
            nifty[day] = {"open": seg.o[i], "close": seg.c[i], "seg": seg_i}
            points.append((day, seg.c[i]))
    regimes = regime.by_date(points)
    days = []
    seen = set()
    for symbol in loaded:
        for seg in symbol["segments"]:
            for day in seg.date:
                if day not in seen and day <= end:
                    seen.add(day)
                    days.append(day)
    for day in nifty:
        if day not in seen and day <= end:
            seen.add(day)
            days.append(day)
    days.sort()
    emit("ranking turnover")
    top200 = {}
    top100 = {}
    for day in days:
        names = lab.liquid_names(day, books, lab.UNIVERSE_N)
        if names:
            top200[day] = set(names)
            top100[day] = set(names[:100])
    by_name = {}
    for symbol in loaded:
        loc = {}
        for seg in symbol["segments"]:
            for i, day in enumerate(seg.date):
                loc[day] = (seg, i)
        by_name[symbol["name"]] = loc
    all_days = sorted(day for day in nifty if nifty[day]["open"] > 0 and day <= end)
    calendar = [day for day in all_days if day >= start]
    emit("eligible symbols %d, sessions %d" % (len(loaded), len(calendar)))
    return {
        "loaded": loaded,
        "nifty": nifty,
        "regimes": regimes,
        "top200": top200,
        "top100": top100,
        "by_name": by_name,
        "calendar": calendar,
        "pairs": month_pairs(all_days, calendar),
        "above": nifty_above(points, 200),
        "month_ends": month_ends(points),
        "pools": None,
        "pools_up": None,
        "start": start,
        "end": end,
        "warmup": warmup,
    }


def _up_pools(pools, loaded, regimes):
    out = {}
    for key in pools:
        kept = []
        for sym_i, seg_i, entry_i in pools[key]:
            seg = loaded[sym_i]["segments"][seg_i]
            if regimes.get(seg.date[entry_i]) == "up":
                kept.append((sym_i, seg_i, entry_i))
        if kept:
            out[key] = kept
    return out


def _progress(log, run_i, runs):
    if log is not None and runs > 1 and run_i % 25 == 0:
        log("  random %d/%d" % (run_i + 1, runs))


def run(root=None, runs=RUNS, log=None, ctx=None, specs=None):
    """Score every variant. Pass ctx to skip the disk, as the tests do."""
    emit = log or (lambda line: None)
    if ctx is None:
        ctx = load_context(root, log=emit)
    if specs is None:
        specs = batch1()
    families(specs)
    if ctx.get("pools") is None:
        emit("building random pools")
        ctx["pools"] = build_pools(ctx["loaded"], ctx["top200"], ctx["warmup"], ctx["start"], ctx["end"])
        ctx["pools_up"] = _up_pools(ctx["pools"], ctx["loaded"], ctx["regimes"])
    bench = path_stats(ctx["calendar"], nifty_path(ctx["calendar"], ctx["nifty"]), CAPITAL, ctx["nifty"], ctx["regimes"])
    bench["name"] = "NIFTY 50"
    blocks = []
    for index, spec in enumerate(specs):
        emit("scoring %s" % spec["name"])
        block = score_variant(spec, index, ctx, runs, emit)
        block["verdict"] = judge(block, bench)
        blocks.append(block)
        emit(summary_line(block))
    return blocks, bench


def summary_line(block):
    beats = "n/a" if block.get("beats") is None else "%d/100" % block["beats"]
    verdict = block.get("verdict")
    result = verdict["result"] if verdict else ""
    return " | ".join([
        block["name"],
        _pct(block.get("cagr")),
        _pct(block.get("max_dd")),
        _ratio(block.get("calmar")),
        _pct(block.get("worst_year")),
        _pct(block.get("excess")),
        _num(block.get("t")),
        _pct(block.get("early")),
        _pct(block.get("late")),
        _pct(block.get("up")),
        _pct(block.get("down")),
        _pct(block.get("sideways")),
        _pct(block.get("large_excess")),
        beats,
        result,
    ])


def summary_table(blocks, nifty):
    """One row per variant, plus NIFTY's own price return. Dividends are excluded."""
    header = " | ".join([
        "variant", "CAGR", "max DD", "CAGR/|DD|", "worst year", "excess", "t",
        "2005-14", "2015-24", "up", "down", "sideways", "large", "beats", "result"])
    bench = {
        "name": "NIFTY 50",
        "cagr": nifty.get("cagr"),
        "max_dd": nifty.get("max_dd"),
        "calmar": nifty.get("calmar"),
        "worst_year": nifty.get("worst_year"),
    }
    lines = [header, summary_line(bench)]
    for block in blocks:
        lines.append(summary_line(block))
    return "\n".join(lines)


def format_block(block, nifty):
    lines = [summary_line(block)]
    lines.append("  2005-2014 %s, 2015-2024 %s, up %s, down %s, sideways %s, large %s, months %d" % (
        _pct(block.get("early")), _pct(block.get("late")), _pct(block.get("up")),
        _pct(block.get("down")), _pct(block.get("sideways")), _pct(block.get("large_excess")),
        block.get("n_months") or 0))
    yearly = block.get("yearly") or {}
    if yearly:
        bits = ["%d %s" % (year, _pct(yearly[year])) for year in sorted(yearly)]
        lines.append("  years: " + ", ".join(bits))
    if nifty is not None and block.get("verdict") and block["verdict"]["result"] != "PASS":
        lines.append("  FAIL: %s" % "; ".join(block["verdict"]["reasons"]))
    elif block.get("verdict"):
        lines.append("  PASS")
    return "\n".join(lines)


def rules_text(stamp):
    """Locked before the run. No result numbers belong in here."""
    return "\n".join([
        "## Attempt 11",
        "",
        "Rules fixed on %s, before the run." % stamp,
        "",
        "Hypothesis: one of twelve published variants, run through the shared harness, "
        "beats buying NIFTY 50 on the pass mark below. The catalogue is "
        "india/research/STRATEGIES.md. Attempts 1 to 10 already tested the "
        "opening-range family and the single technical-signal family.",
        "",
        "Common rules. Universe each day: the 200 symbols with the highest average "
        "close times volume over the previous 60 sessions, using only earlier bars and "
        "never a window that crosses a break. A trade or a holding that would cross a "
        "break is closed at the last close of the old segment. The last session of the "
        "window is the end of the loaded segment, so open holdings are sold at that "
        "close. The first 250 sessions "
        "of a segment produce no trade signal. Market type is india/research/regime.py, "
        "known before the open. Data is read through india/research/data.py. The window "
        "is 2005-01-01 through 2024-12-31. Dates from 2025-01-01 on are not requested. "
        "Dividends are excluded for every book and for NIFTY. The book and the NIFTY "
        "benchmark both start by buying at the first session's open, with no cost on "
        "that initial buy, and are marked at the close.",
        "",
        "Idle cash is held in the NIFTY 50 price series, not at 0, so a book that is "
        "only partly invested is still compared with the market. Delivery costs from "
        "signal_lab.py (check your broker) are charged on stock buys and stock sells. "
        "They are not charged on the idle sleeve. A trade strategy has a Rs 10,00,000 "
        "book and at most 10 positions of Rs 1,00,000. When more signals than free "
        "slots fall on one open, the highest 60-session turnover before that open is "
        "taken, ties broken by symbol name. One position per symbol. A portfolio "
        "strategy puts the whole book into the selected names in equal weight at the "
        "next session's open after the month-end close. Costs are charged only on the "
        "shares that are actually bought or sold. Rounding residual stays in NIFTY.",
        "",
        "Turtle, trade. Enter the next open after a close above the prior 20-session "
        "or 55-session high (today is not inside that high). The stop is the entry "
        "minus 2 ATR20 from the signal day: a gap through it fills at the open, and a "
        "low through it fills at the stop. A close below the prior 10-session or "
        "20-session low exits at the next open. The stop is taken first when both "
        "happen on the same day. Variants: turtle 20/10, turtle 55/20, and "
        "turtle 55/20 up. The up variant is an entry filter only: the regime of "
        "the entry day must be up, and a later change of regime does not close "
        "the trade.",
        "",
        "Cross-sectional momentum, portfolio, monthly. Rank by the close 21 sessions "
        "before the month-end divided by the close 252 sessions before it, minus one, "
        "inside one segment. Variants: K=20, K=30, and K=20 only when the NIFTY "
        "month-end close is above its 200-day average of closes through that day "
        "(otherwise the whole book is NIFTY). That average test is not the "
        "regime slope. Variant names: mom 12-1 K20, mom 12-1 K30, mom 12-1 K20 above200. "
        "When fewer than K names qualify, those names share the book equally.",
        "",
        "52-week-high momentum, portfolio, monthly. Rank by the month-end close "
        "divided by the prior 252-session high. Variant names: 52w-high K20, "
        "52w-high K30, and 52w-high K20 above200, the last with the same "
        "200-day NIFTY filter.",
        "",
        "Faber timing, portfolio on NIFTY 50 itself. Hold NIFTY when the month-end "
        "close is above the average of the last N month-end closes, including that "
        "close. Otherwise cash at 0, which is the exception to the idle-NIFTY rule. "
        "Buying or selling that index position pays delivery costs. Variant names: "
        "faber 10m, faber 8m, faber 12m. Before a full average exists the book stays "
        "in cash. Faber has no stock universe, so its large-cap excess is its own excess.",
        "",
        "Reports. CAGR over 365.25-day years, max drawdown, CAGR divided by the "
        "absolute max drawdown, worst calendar year, and each year's return. The same "
        "figures for NIFTY 50 buy-and-hold, price only. Monthly excess is the book's "
        "month-end to month-end percent return minus NIFTY's over the same dates, and "
        "the t-statistic is the one-sample t of those monthly excesses. Decades are "
        "2005-2014 and 2015-2024 by the month-end year. Market type is the regime of "
        "the first session of the month. Large caps rerun the variant on the top 100 "
        "by the same 60-session turnover; Faber has no stock book, so its large-cap "
        "excess is its own excess.",
        "",
        "Random baseline, 100 seeded runs, seed 20261106 plus an offset per variant. "
        "A portfolio run keeps the same rebalance dates, the same K, and the same "
        "NIFTY filter, and draws random members of that day's universe who can be "
        "bought on the rebalance open in the same segment. A turtle run replaces each "
        "real entry with one random eligible entry from the same calendar month and "
        "applies the same stop and channel exit; the up-only variant draws only from "
        "entry days whose regime is up. A Faber run, each month, holds NIFTY or cash "
        "with equal probability. The book beats a run when its CAGR is strictly higher.",
        "",
        "Pass mark, fixed before this run and used from attempt 11 on, separate from "
        "attempts 1 to 10: monthly excess t above 3; average excess above 0 in both "
        "decades and in up, down, and sideways months; beats at least 95 of 100 random "
        "runs; large-cap excess above 0; and either CAGR at least NIFTY plus 3 "
        "percentage points with max drawdown no more than 10 percentage points worse "
        "than NIFTY, or CAGR at least NIFTY's with CAGR / |max drawdown| at least 1.5 "
        "times NIFTY's. A value sitting on the boundary still passes.",
        "",
        "Results are filled in after the run.",
        "",
    ])


def results_text(stamp, blocks, nifty):
    body = rules_text(stamp).replace("Results are filled in after the run.", "").rstrip()
    lines = [
        body, "",
        "Dividends are excluded. The summary columns are CAGR, max drawdown, "
        "CAGR / |max drawdown|, worst year, monthly excess, t, both decades, "
        "each market type, the large-cap excess, and random beats. "
        "In the experiments table the two return columns are CAGR and the monthly t, not R. "
        "A portfolio trades cell counts selected names across rebalance dates. "
        "A Faber trades cell counts months held.",
        "",
        summary_table(blocks, nifty),
        "",
    ]
    passed = 0
    for block in blocks:
        lines.append(format_block(block, nifty))
        lines.append("")
        if block["verdict"]["result"] == "PASS":
            passed += 1
    lines.append("Variants that pass: %d of %d." % (passed, len(blocks)))
    return "\n".join(lines).rstrip() + "\n"


def table_rows(stamp, blocks):
    rows = []
    rule = "harness batch 1, delivery costs, idle cash in NIFTY except Faber"
    universe = "top 200 by prior 60-session turnover, 2005-01-01 to 2024-12-31, dividends excluded"
    for block in blocks:
        hypothesis = "%s clears the attempt 11 pass mark against NIFTY buy-and-hold." % block["name"]
        rows.append("| 11 | %s | %s | %s | %s | %s | %s | %s | %s |" % (
            stamp, hypothesis, rule, universe,
            format(block.get("trades") or 0, ",d"),
            _pct(block.get("cagr")),
            _num(block.get("t")),
            block["verdict"]["result"]))
    return rows


def install(path, section, rows):
    """Replace attempt 11 and its table rows. Leave earlier attempts in place."""
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    kept = []
    for line in text.splitlines():
        if line.startswith("| 11 |"):
            continue
        kept.append(line)
    text = "\n".join(kept)
    if not text.endswith("\n"):
        text += "\n"
    start = text.find("\n## Attempt 11\n")
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
        at = text.rfind("\n| 10 |")
        if at == -1 and text.startswith("| 10 |"):
            at = 0
        elif at != -1:
            at += 1
        if at != -1:
            line_end = text.find("\n", at)
            if line_end == -1:
                line_end = len(text)
            text = text[:line_end] + "\n" + "\n".join(rows) + text[line_end:]
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


# Attempt 12. Intraday batch. The futures rates are a working schedule:
# check your broker before treating a rupee total as final.
INTRADAY_START = datetime.date(2015, 1, 1)
INTRADAY_END = datetime.date(2024, 12, 31)
INTRADAY_RISK = 2000.0
INTRADAY_CAP = 500000.0
INTRADAY_LOOKBACK = 20
INTRADAY_TOP = 200
INTRADAY_LARGE = 100
NIFTY_LOT = 75
NIFTY_BROKERAGE = 20.0
NIFTY_STT_PCT = 0.05
NIFTY_EXCHANGE_PCT = 0.00173
NIFTY_SEBI_PCT = 0.0001
NIFTY_STAMP_PCT = 0.002
NIFTY_GST_PCT = 18.0
GAO_R = 0.0025
M_0920 = 9 * 60 + 20
M_0930 = 9 * 60 + 30
M_0935 = 9 * 60 + 35
M_0945 = 9 * 60 + 45
M_0950 = 9 * 60 + 50
M_1000 = 10 * 60
M_1400 = 14 * 60
M_1430 = 14 * 60 + 30
M_1500 = 15 * 60
M_1505 = 15 * 60 + 5
M_1510 = 15 * 60 + 10
M_1525 = 15 * 60 + 25
_EQ_BROK = float(costs.RATES["brokerage_pct"])
_EQ_CAP = float(costs.RATES["brokerage_cap"])
_EQ_STT = float(costs.RATES["stt_pct"])
_EQ_EXCH = float(costs.RATES["exchange_pct"])
_EQ_SEBI = float(costs.RATES["sebi_pct"])
_EQ_STAMP = float(costs.RATES["stamp_pct"])
_EQ_GST = float(costs.RATES["gst_pct"])


def batch2():
    """Twelve intraday variants, three per family. Names are stable."""
    return [
        {"name": "nifty mom always", "kind": "nifty_mom", "min_abs": 0.0, "same_sign": False},
        {"name": "nifty mom abs 0.25", "kind": "nifty_mom", "min_abs": 0.0025, "same_sign": False},
        {"name": "nifty mom same sign", "kind": "nifty_mom", "min_abs": 0.0, "same_sign": True},
        {"name": "NR7", "kind": "nr", "n": 7, "inside": False},
        {"name": "NR4", "kind": "nr", "n": 4, "inside": False},
        {"name": "NR7 inside", "kind": "nr", "n": 7, "inside": True},
        {"name": "gap GO 1.5", "kind": "gap", "mode": "go", "gap": 0.015},
        {"name": "gap FADE 1.5", "kind": "gap", "mode": "fade", "gap": 0.015},
        {"name": "gap GO 3", "kind": "gap", "mode": "go", "gap": 0.03},
        {"name": "vwap 1.5 sideways", "kind": "vwap", "x": 1.5},
        {"name": "vwap 2.0 sideways", "kind": "vwap", "x": 2.0},
        {"name": "vwap 2.5 sideways", "kind": "vwap", "x": 2.5},
    ]


def equity_cost(buy, sell, shares):
    """Round-trip rupees. The rates are india/costs.py, evaluated in floats."""
    if shares <= 0 or buy <= 0 or sell <= 0:
        return 0.0
    buy_value = buy * float(shares)
    sell_value = sell * float(shares)
    brokerage = min(buy_value * _EQ_BROK / 100.0, _EQ_CAP) + min(sell_value * _EQ_BROK / 100.0, _EQ_CAP)
    stt = sell_value * _EQ_STT / 100.0
    exchange = (buy_value + sell_value) * _EQ_EXCH / 100.0
    sebi = (buy_value + sell_value) * _EQ_SEBI / 100.0
    stamp = buy_value * _EQ_STAMP / 100.0
    gst = (brokerage + exchange + sebi) * _EQ_GST / 100.0
    return brokerage + stt + exchange + sebi + stamp + gst


def nifty_round_trip(buy, sell, units):
    """Futures round trip on `units`. Check the constants against your broker."""
    if units <= 0 or buy <= 0 or sell <= 0:
        return 0.0
    buy_value = buy * float(units)
    sell_value = sell * float(units)
    brokerage = NIFTY_BROKERAGE * 2.0
    stt = sell_value * NIFTY_STT_PCT / 100.0
    exchange = (buy_value + sell_value) * NIFTY_EXCHANGE_PCT / 100.0
    sebi = (buy_value + sell_value) * NIFTY_SEBI_PCT / 100.0
    stamp = buy_value * NIFTY_STAMP_PCT / 100.0
    gst = (brokerage + exchange + sebi) * NIFTY_GST_PCT / 100.0
    return brokerage + stt + exchange + sebi + stamp + gst


def intraday_shares(entry, risk):
    """Whole shares that risk INTRADAY_RISK, then cut to the position cap."""
    if entry <= 0 or risk <= 0:
        return 0
    by_risk = int(INTRADAY_RISK // risk)
    by_cap = int(INTRADAY_CAP // entry)
    return max(0, min(by_risk, by_cap))


def _session_usable(session):
    starts = []
    ends = session["end"]
    for i in range(len(ends)):
        starts.append(ends[i] - data.BAR_MINUTES)
    return data.session_usable(data.mask_from_starts(starts))


def minute_index(session, minute):
    ends = session["end"]
    for i in range(len(ends)):
        if ends[i] == minute:
            return i
        if ends[i] > minute:
            return None
    return None


def indices_between(session, first, last):
    ends = session["end"]
    found = []
    for i in range(len(ends)):
        if ends[i] < first:
            continue
        if ends[i] > last:
            break
        found.append(i)
    return found


def walk_exit(session, entry_i, side, stop, target, flat_end):
    """Later bars only. A gap through the stop fills at the open. Stop before target."""
    ends = session["end"]
    long = side == "buy"
    for i in range(entry_i + 1, len(ends)):
        end = ends[i]
        if end > flat_end:
            return None
        opened = session["open"][i]
        if stop is not None:
            if long and opened <= stop:
                return opened
            if not long and opened >= stop:
                return opened
            if long and session["low"][i] <= stop:
                return stop
            if not long and session["high"][i] >= stop:
                return stop
        if target is not None:
            if long and session["high"][i] >= target:
                return target
            if not long and session["low"][i] <= target:
                return target
        if end == flat_end:
            return session["close"][i]
    return None


def score_exit(side, entry, exit_px, risk, symbol, nifty):
    """R before charges and R after charges. Both include 1 tick of slippage."""
    if entry <= 0 or exit_px <= 0 or risk <= 0:
        return None
    if nifty:
        tick = nse_market.tick_for(entry, "NIFTY")
        shares = NIFTY_LOT
    else:
        tick = nse_market.tick_for(entry, symbol)
        shares = intraday_shares(entry, risk)
    if shares <= 0:
        return None
    if side == "buy":
        buy = entry + tick
        sell = exit_px - tick
    else:
        sell = entry - tick
        buy = exit_px + tick
    if buy <= 0 or sell <= 0:
        return None
    pnl = sell - buy
    if nifty:
        cost = nifty_round_trip(buy, sell, shares)
    else:
        cost = equity_cost(buy, sell, shares)
    return pnl / risk, (pnl * shares - cost) / (risk * shares), shares


def bar_outcome(session, i, side, risk, target_dist, flat_end, symbol, nifty, use_stop):
    entry = session["close"][i]
    if not entry > 0 or not risk > 0:
        return None
    stop = None
    if use_stop:
        stop = entry - risk if side == "buy" else entry + risk
    target = None
    if target_dist is not None and target_dist > 0:
        target = entry + target_dist if side == "buy" else entry - target_dist
    exit_px = walk_exit(session, i, side, stop, target, flat_end)
    if exit_px is None:
        return None
    return score_exit(side, entry, exit_px, risk, symbol, nifty)


def _trade(session, day, symbol, side, signal_i, risk, target_dist, flat_end, use_stop, window, regime_kind, large, nifty):
    scored = bar_outcome(session, signal_i, side, risk, target_dist, flat_end, symbol, nifty, use_stop)
    if scored is None:
        return None
    window_r = []
    for i in window:
        item = bar_outcome(session, i, side, risk, target_dist, flat_end, symbol, nifty, use_stop)
        window_r.append(None if item is None else item[1])
    return {
        "date": day,
        "symbol": symbol,
        "r_before": scored[0],
        "r_after": scored[1],
        "shares": scored[2],
        "regime": regime_kind,
        "large": large,
        "window_r": window_r,
    }


def gao_trade(session, prev_close, spec, day, regime_kind):
    """NIFTY 15:00 entry from the 09:45 return. No stop. Exit at the 15:25 close."""
    if prev_close is None or not prev_close > 0:
        return None
    i_r = minute_index(session, M_0945)
    i_1430 = minute_index(session, M_1430)
    i_1500 = minute_index(session, M_1500)
    i_1525 = minute_index(session, M_1525)
    if i_r is None or i_1430 is None or i_1500 is None or i_1525 is None:
        return None
    base = session["close"][i_1430]
    if not base > 0:
        return None
    r1 = session["close"][i_r] / prev_close - 1.0
    late = session["close"][i_1500] / base - 1.0
    if r1 > 0:
        side = "buy"
    elif r1 < 0:
        side = "sell"
    else:
        return None
    if spec["min_abs"] and not abs(r1) > spec["min_abs"]:
        return None
    if spec["same_sign"] and not ((r1 > 0 and late > 0) or (r1 < 0 and late < 0)):
        return None
    entry = session["close"][i_1500]
    return _trade(
        session, day, lab.NIFTY, side, i_1500, GAO_R * entry, None, M_1525, False,
        [i_1500], regime_kind, True, True)


def is_nr(rows, signal_i, n, inside):
    """True when rows[signal_i] is the strict narrowest range of the last n days."""
    if signal_i < 0 or signal_i + 1 >= len(rows):
        return False
    if rows[signal_i]["seg"] != rows[signal_i + 1]["seg"]:
        return False
    start = signal_i + 1 - n
    if start < 0 or rows[start]["seg"] != rows[signal_i]["seg"]:
        return False
    last = rows[signal_i]["high"] - rows[signal_i]["low"]
    if last < 0:
        return False
    for item in rows[start:signal_i]:
        if last >= item["high"] - item["low"]:
            return False
    if inside:
        if signal_i < 1 or rows[signal_i - 1]["seg"] != rows[signal_i]["seg"]:
            return False
        prior = rows[signal_i - 1]
        if not (rows[signal_i]["high"] < prior["high"] and rows[signal_i]["low"] > prior["low"]):
            return False
    return True


def range_bounds(session, last_end):
    high = None
    low = None
    ends = session["end"]
    for i in range(len(ends)):
        if ends[i] > last_end:
            break
        if high is None or session["high"][i] > high:
            high = session["high"][i]
        if low is None or session["low"][i] < low:
            low = session["low"][i]
    return high, low


def first_break(session, first_end, last_end, bound_high, bound_low, direction):
    """First close beyond the range. direction 'buy', 'sell', or None for either side."""
    for i in indices_between(session, first_end, last_end):
        close = session["close"][i]
        if close > bound_high and direction != "sell":
            return i, "buy", bound_low
        if close < bound_low and direction != "buy":
            return i, "sell", bound_high
    return None


def nr_trade(session, day, symbol, regime_kind, large):
    high, low = range_bounds(session, M_0945)
    if high is None or low is None or high < low:
        return None
    found = first_break(session, M_0950, M_1430, high, low, None)
    if found is None:
        return None
    i, side, stop = found
    entry = session["close"][i]
    risk = abs(entry - stop)
    window = indices_between(session, M_0950, M_1430)
    return _trade(session, day, symbol, side, i, risk, None, M_1510, True, window, regime_kind, large, False)


def gap_size(session, prev_close):
    i = minute_index(session, M_0920)
    if i is None or not prev_close > 0:
        return None
    opened = session["open"][i]
    if not opened > 0:
        return None
    return opened / prev_close - 1.0, opened


def go_trade(session, day, symbol, gap, regime_kind, large):
    high, low = range_bounds(session, M_0930)
    if high is None or low is None or high < low:
        return None
    direction = "buy" if gap > 0 else "sell"
    found = first_break(session, M_0935, M_1505, high, low, direction)
    if found is None:
        return None
    i, side, stop = found
    entry = session["close"][i]
    risk = abs(entry - stop)
    window = indices_between(session, M_0935, M_1505)
    return _trade(session, day, symbol, side, i, risk, None, M_1510, True, window, regime_kind, large, False)


def fade_trade(session, day, symbol, opened, y_high, y_low, y_close, regime_kind, large):
    """Fade only after a gap that opened outside yesterday's range."""
    if opened > y_high:
        side = "sell"
    elif opened < y_low:
        side = "buy"
    else:
        return None
    window = indices_between(session, M_0935, M_1505)
    signal = None
    for i in window:
        close = session["close"][i]
        if side == "sell" and close <= y_high:
            signal = i
            break
        if side == "buy" and close >= y_low:
            signal = i
            break
    if signal is None:
        return None
    entry = session["close"][signal]
    if side == "sell":
        extreme = session["high"][0]
        for j in range(signal + 1):
            if session["high"][j] > extreme:
                extreme = session["high"][j]
        if not y_close < entry:
            return None
    else:
        extreme = session["low"][0]
        for j in range(signal + 1):
            if session["low"][j] < extreme:
                extreme = session["low"][j]
        if not y_close > entry:
            return None
    risk = abs(entry - extreme)
    target_dist = abs(y_close - entry)
    return _trade(
        session, day, symbol, side, signal, risk, target_dist, M_1510, True, window,
        regime_kind, large, False)


def vwap_trade(session, day, symbol, x, regime_kind, large):
    """First close at least x percent away from the running VWAP, 10:00 to 14:00."""
    if regime_kind != "sideways":
        return None
    cum_pv = 0.0
    cum_v = 0.0
    ends = session["end"]
    signal = None
    side = None
    vwap_at = None
    for i in range(len(ends)):
        vol = session["volume"][i]
        if vol < 0:
            vol = 0.0
        typical = (session["high"][i] + session["low"][i] + session["close"][i]) / 3.0
        cum_pv += typical * vol
        cum_v += vol
        end = ends[i]
        if end < M_1000 or end > M_1400 or not cum_v > 0:
            continue
        vwap = cum_pv / cum_v
        close = session["close"][i]
        if close <= vwap * (1.0 - x / 100.0):
            signal = i
            side = "buy"
            vwap_at = vwap
            break
        if close >= vwap * (1.0 + x / 100.0):
            signal = i
            side = "sell"
            vwap_at = vwap
            break
    if signal is None:
        return None
    entry = session["close"][signal]
    dist = abs(vwap_at - entry)
    window = indices_between(session, M_1000, M_1400)
    return _trade(
        session, day, symbol, side, signal, dist, dist, M_1510, True, window,
        regime_kind, large, False)


class DailyBook(object):
    """One symbol's daily rows, in order, with a 20-session turnover lookup."""

    def __init__(self, segments):
        self.rows = []
        seg_id = 0
        for segment in segments:
            for item in segment:
                self.rows.append({
                    "date": item["date"],
                    "open": item["open"],
                    "high": item["high"],
                    "low": item["low"],
                    "close": item["close"],
                    "volume": item["volume"],
                    "seg": seg_id,
                    "i": len(self.rows),
                })
            seg_id += 1
        self.by_date = {}
        self.dates = []
        self.prefix = [0.0]
        total = 0.0
        for row in self.rows:
            self.by_date[row["date"]] = row
            self.dates.append(row["date"])
            total += row["close"] * float(row["volume"])
            self.prefix.append(total)

    def average_before(self, day):
        j = bisect.bisect_left(self.dates, day)
        if j < INTRADAY_LOOKBACK:
            return None
        if self.rows[j - 1]["seg"] != self.rows[j - INTRADAY_LOOKBACK]["seg"]:
            return None
        return (self.prefix[j] - self.prefix[j - INTRADAY_LOOKBACK]) / float(INTRADAY_LOOKBACK)


def rank_universe(books, calendar):
    """day -> (set of top 200, set of top 100) by 20-session turnover before the day."""
    top200 = {}
    top100 = {}
    for day in calendar:
        scored = []
        for symbol, book in books:
            average = book.average_before(day)
            if average is None:
                continue
            scored.append((-average, symbol))
        scored.sort()
        top200[day] = set(symbol for _average, symbol in scored[:INTRADAY_TOP])
        top100[day] = set(symbol for _average, symbol in scored[:INTRADAY_LARGE])
    return top200, top100


def _invert(membership):
    out = {}
    for day, names in membership.items():
        for symbol in names:
            bucket = out.get(symbol)
            if bucket is None:
                bucket = set()
                out[symbol] = bucket
            bucket.add(day)
    return out


def apply_random(trades, runs, seed):
    """Excess R is the trade minus the mean of `runs` random entries. Seeded."""
    trades.sort(key=lambda item: (item["date"], item["symbol"]))
    for run_i in range(runs):
        rng = random.Random(seed + run_i)
        for trade in trades:
            window = trade["window_r"]
            if not window:
                continue
            value = window[rng.randrange(len(window))]
            picked = trade.get("picks")
            if picked is None:
                picked = []
                trade["picks"] = picked
            picked.append(value)
    for trade in trades:
        picks = []
        for value in trade.get("picks", []):
            if value is not None:
                picks.append(value)
        random_r = _mean(picks)
        if random_r is None:
            trade["excess"] = None
        else:
            excess = trade["r_after"] - random_r
            # A one-bar window makes the random entry the real one. Float dust
            # is not a difference.
            if abs(excess) < 1e-9:
                excess = 0.0
            trade["excess"] = excess
        trade.pop("window_r", None)
        trade.pop("picks", None)


def summarise_intraday(name, trades):
    after = []
    before = []
    days = set()
    wins = 0
    yearly = {}
    buckets = {"up": [], "down": [], "sideways": [], "large": [], "early": [], "late": []}
    by_month = {}
    for trade in trades:
        after.append(trade["r_after"])
        before.append(trade["r_before"])
        days.add(trade["date"])
        if trade["r_after"] > 0:
            wins += 1
        year = trade["date"].year
        yearly.setdefault(year, []).append(trade["r_after"])
        kind = trade.get("regime")
        if kind in buckets:
            buckets[kind].append(trade["r_after"])
        if trade.get("large"):
            buckets["large"].append(trade["r_after"])
        if 2015 <= year <= 2019:
            buckets["early"].append(trade["r_after"])
        if 2020 <= year <= 2024:
            buckets["late"].append(trade["r_after"])
        if trade.get("excess") is not None:
            key = (year, trade["date"].month)
            by_month.setdefault(key, []).append(trade["excess"])
    monthly = []
    for key in sorted(by_month):
        monthly.append(_mean(by_month[key]))
    years = {}
    for year in sorted(yearly):
        years[year] = _mean(yearly[year])
    return {
        "name": name,
        "trades": len(trades),
        "days": len(days),
        "win": (wins / float(len(trades))) if trades else None,
        "avg_before": _mean(before),
        "avg_after": _mean(after),
        "t": t_stat(monthly),
        "early": _mean(buckets["early"]),
        "late": _mean(buckets["late"]),
        "up": _mean(buckets["up"]),
        "down": _mean(buckets["down"]),
        "sideways": _mean(buckets["sideways"]),
        "large": _mean(buckets["large"]),
        "yearly": years,
    }


def judge_intraday(block, family):
    """The attempt 12 mark. A boundary stated with 'at least' still passes."""
    reasons = []
    if block["avg_after"] is None or not block["avg_after"] >= 0.10:
        reasons.append("avg R after costs %s is below +0.10" % _r(block["avg_after"]))
    if block["trades"] < 300:
        reasons.append("trades %d is below 300" % block["trades"])
    if block["days"] < 100:
        reasons.append("days %d is below 100" % block["days"])
    if block["t"] is None or not block["t"] > 3:
        reasons.append("t vs random %s is not above 3" % _num(block["t"]))
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
            reasons.append("%s %s is not above 0" % (label, _r(block[key])))
    strong = 0
    for item in family:
        if item.get("t") is not None and item["t"] > 2:
            strong += 1
    if strong < 2:
        reasons.append("family variants with t above 2: %d of %d, need 2" % (strong, len(family)))
    return {"result": "PASS" if not reasons else "FAIL", "reasons": reasons}


def _r(value):
    if value is None:
        return "n/a"
    return "%+.3f" % value


def load_daily_book(root, symbol):
    series = data.load_daily(root, symbol, end=INTRADAY_END)
    return DailyBook(series.segments)


def load_usable_map(root, symbol, start):
    series = data.load_arrays(root, symbol, "5minute", start=start, end=INTRADAY_END)
    found = {}
    for segment in series.segments:
        for item in segment:
            session = item["session"]
            if _session_usable(session):
                found[item["date"]] = session
    return found


def scan_nifty(ordered, specs, regimes):
    """ordered is (date, session) through the window, oldest first, prior days included."""
    found = {}
    for spec in specs:
        found[spec["name"]] = []
    prev_close = None
    for day, session in ordered:
        last = session["close"][-1] if len(session["close"]) else 0.0
        if INTRADAY_START <= day <= INTRADAY_END and _session_usable(session):
            kind = regimes.get(day)
            for spec in specs:
                trade = gao_trade(session, prev_close, spec, day, kind)
                if trade is not None:
                    found[spec["name"]].append(trade)
        if last > 0:
            prev_close = last
    return found


def scan_symbol(symbol, sessions, book, member_days, large_days, regimes, specs):
    grouped = {}
    for spec in specs:
        grouped.setdefault(spec["kind"], []).append(spec)
    found = {}
    for spec in specs:
        found[spec["name"]] = []
    rows = book.rows
    for day in sorted(sessions):
        if day not in member_days:
            continue
        row = book.by_date.get(day)
        if row is None:
            continue
        session = sessions[day]
        kind = regimes.get(day)
        large = day in large_days
        prev = None
        if row["i"] > 0 and rows[row["i"] - 1]["seg"] == row["seg"]:
            prev = rows[row["i"] - 1]
        for spec in grouped.get("nr", []):
            if prev is not None and is_nr(rows, prev["i"], spec["n"], spec["inside"]):
                trade = nr_trade(session, day, symbol, kind, large)
                if trade is not None:
                    found[spec["name"]].append(trade)
        gap_specs = grouped.get("gap", [])
        if gap_specs and prev is not None:
            sized = gap_size(session, prev["close"])
            if sized is not None:
                gap, opened = sized
                for spec in gap_specs:
                    if abs(gap) < spec["gap"] or gap == 0:
                        continue
                    if spec["mode"] == "go":
                        trade = go_trade(session, day, symbol, gap, kind, large)
                    else:
                        trade = fade_trade(
                            session, day, symbol, opened, prev["high"], prev["low"], prev["close"],
                            kind, large)
                    if trade is not None:
                        found[spec["name"]].append(trade)
        if kind == "sideways":
            for spec in grouped.get("vwap", []):
                trade = vwap_trade(session, day, symbol, spec["x"], kind, large)
                if trade is not None:
                    found[spec["name"]].append(trade)
    return found


def _flatten_sessions(series):
    ordered = []
    for segment in series.segments:
        for item in segment:
            ordered.append((item["date"], item["session"]))
    return ordered


def run_intraday(root, runs=RUNS, log=None):
    """Score batch 2. 2025 is not requested. Returns one block per variant, in order."""
    emit = log or (lambda line: None)
    specs = batch2()
    names = []
    for symbol in data.symbols_in(root):
        if symbol.startswith("NIFTY"):
            continue
        names.append(symbol)
    books = []
    nifty_book = load_daily_book(root, lab.NIFTY)
    points = [(row["date"], row["close"]) for row in nifty_book.rows]
    regimes = regime.by_date(points)
    calendar = []
    for row in nifty_book.rows:
        if INTRADAY_START <= row["date"] <= INTRADAY_END:
            calendar.append(row["date"])
    emit("loading daily books")
    for i, symbol in enumerate(names):
        try:
            book = load_daily_book(root, symbol)
        except data.DataError:
            continue
        if book.rows:
            books.append((symbol, book))
        if (i + 1) % 50 == 0:
            emit("  daily %d/%d" % (i + 1, len(names)))
    emit("daily books %d, sessions %d" % (len(books), len(calendar)))
    top200, top100 = rank_universe(books, calendar)
    member = _invert(top200)
    large = _invert(top100)
    emit("universe ranked")
    collected = {}
    for spec in specs:
        collected[spec["name"]] = []
    emit("NIFTY intraday momentum")
    nifty_series = data.load_arrays(root, lab.NIFTY, "5minute", end=INTRADAY_END)
    nifty_specs = [spec for spec in specs if spec["kind"] == "nifty_mom"]
    nifty_trades = scan_nifty(_flatten_sessions(nifty_series), nifty_specs, regimes)
    for name, trades in nifty_trades.items():
        collected[name].extend(trades)
    stock_specs = [spec for spec in specs if spec["kind"] != "nifty_mom"]
    book_of = {}
    for symbol, book in books:
        book_of[symbol] = book
    symbols = sorted(member)
    emit("scanning %d symbols" % len(symbols))
    for i, symbol in enumerate(symbols):
        book = book_of.get(symbol)
        if book is None:
            continue
        try:
            sessions = load_usable_map(root, symbol, INTRADAY_START)
        except data.DataError:
            continue
        scanned = scan_symbol(
            symbol, sessions, book, member[symbol], large.get(symbol, set()), regimes, stock_specs)
        for name, trades in scanned.items():
            collected[name].extend(trades)
        if (i + 1) % 25 == 0:
            emit("  symbol %d/%d" % (i + 1, len(symbols)))
    blocks = []
    for index, spec in enumerate(specs):
        trades = collected[spec["name"]]
        apply_random(trades, runs, SEED + index * 1000)
        block = summarise_intraday(spec["name"], trades)
        block["kind"] = spec["kind"]
        block["seed"] = SEED + index * 1000
        block["runs"] = runs
        blocks.append(block)
    by_kind = {}
    for block in blocks:
        by_kind.setdefault(block["kind"], []).append(block)
    for block in blocks:
        block["verdict"] = judge_intraday(block, by_kind[block["kind"]])
    return blocks


def intraday_rules(stamp):
    """The attempt 12 rules. No measured result belongs in this text."""
    return "\n".join([
        "## Attempt 12",
        "",
        "Rules fixed on %s, before the run." % stamp,
        "",
        "Hypothesis: one of twelve intraday variants clears the pass mark below on "
        "2015-2024. Entry and exit are 5-minute bars whose labels are the bar end. "
        "Nothing is held overnight.",
        "",
        "Common rules. A session is used only when every bar from 09:15 to 15:10 is "
        "present, using the bar start. The position is flat at the 15:10 bar close "
        "unless the rule exits earlier. Gao exits at the 15:25 bar close, which is "
        "the one later exit. R is |entry - stop|. A stock trade risks Rs 2,000 and "
        "is capped at Rs 5,00,000 of entry value, in whole shares. One tick of "
        "slippage, from nse_market.tick_for, is charged against the trade on the "
        "entry and on the exit. NIFTY 50 uses tick_for with symbol NIFTY, so the "
        "index tick is 0.05. Stock costs use the india/costs.py intraday schedule. "
        "R before is after the tick and before charges. R after is after the tick "
        "and the charges. A later bar that opens through the stop fills at the open. "
        "Otherwise a touch fills at the stop. The stop is taken before the target "
        "when both can fill on the same bar. The entry bar is not scanned for the stop.",
        "",
        "NIFTY trades use the NIFTY 50 index bars as the price and one lot of 75 "
        "units, not the Rs 2,000 sizer. Futures costs, check your broker: brokerage "
        "Rs 20 per order, STT 0.05% on the sell side, exchange 0.00173% on both "
        "sides, SEBI 0.0001% on both sides, stamp 0.002% on the buy, GST 18% on "
        "brokerage + exchange + SEBI.",
        "",
        "Universe for the stock strategies: each day, the 200 symbols with the "
        "highest average close times volume over the previous 20 sessions, and the "
        "20 sessions must sit in one segment. Large caps are the top 100 by that "
        "same average. NIFTY has no stock book, so its large-cap average is its own "
        "average R. Market type is india/research/regime.py, known before the open. "
        "The window is 2015-01-01 through 2024-12-31. Dates from 2025-01-01 on are "
        "not requested.",
        "",
        "Random baseline, 100 seeded runs, seed 20261106 plus an offset per variant. "
        "Each run keeps the symbol, the day, the direction, the stop distance and "
        "the target distance, and enters at a random bar inside that rule's entry "
        "window. Gao's window is the 15:00 bar only. Excess R for a trade is its R "
        "after costs minus the mean R of those random entries. The t-statistic is "
        "the one-sample t of the mean excess in each calendar month.",
        "",
        "Pass mark, fixed before this run: average R after costs and slippage at "
        "least +0.10; at least 300 trades on at least 100 distinct days; t vs random "
        "above 3; average R after costs above 0 in 2015-2019 and in 2020-2024; above "
        "0 on up, down, and sideways days; above 0 in large caps; and at least 2 of "
        "that strategy's 3 variants have t above 2. A value on a stated boundary "
        "passes. An empty bucket does not. The attempt 11 mark is unchanged.",
        "",
        "1. NIFTY intraday momentum. r1 is the 09:45 close divided by the previous "
        "session's last close, minus 1. At the 15:00 bar close, go long if r1 > 0 "
        "and short if r1 < 0. Exit at the 15:25 close. There is no stop. R is 0.25% "
        "of the entry, for reporting only. Variants: nifty mom always; nifty mom abs "
        "0.25, which also requires |r1| > 0.25%; nifty mom same sign, which also "
        "requires r1 and the 15:00 close divided by the 14:30 close, minus 1, to be "
        "strictly the same sign.",
        "",
        "2. Crabel NR. The signal day is the strict narrowest daily high-low of the "
        "last 7 days, or 4, including that day, inside one segment. The next session "
        "trades. The opening range is the high and low of bars ending 09:20 through "
        "09:45. Enter on the first 5-minute close beyond that range, either side, "
        "on a bar ending 09:50 through 14:30. The stop is the other side of the "
        "range. Exit at the 15:10 close. Variants: NR7; NR4; NR7 inside, which also "
        "requires the signal day's high to be strictly below the prior high and its "
        "low strictly above the prior low.",
        "",
        "3. Gaps. The gap is the 09:20 bar's open divided by the previous session's "
        "daily close, minus 1. A gap of exactly the threshold counts. gap GO 1.5 "
        "and gap GO 3 enter on the first close beyond the 15-minute range (bars "
        "ending 09:20 through 09:30) in the gap's direction, on a bar ending 09:35 "
        "through 15:05. The stop is the other side of that range. gap FADE 1.5 "
        "requires the open to be outside yesterday's high-low. After the first 15 "
        "minutes, the first close back inside that range is a fade: short after a "
        "gap up, long after a gap down, toward yesterday's close. The stop is the "
        "day's extreme through the signal bar. The target is yesterday's close, and "
        "the trade is skipped when that target is not beyond the entry. Exit at "
        "15:10 at the latest. Thresholds: 1.5% for GO and FADE, 3% for the third GO.",
        "",
        "4. VWAP reversion, only on sideways days. VWAP starts at the 09:20 bar and "
        "uses bar volume times typical price (high + low + close) / 3, including "
        "the current bar. Between bars ending 10:00 and 14:00, the first close at "
        "least X percent below VWAP is a long, and the first close at least X "
        "percent above is a short. The target is that bar's VWAP. The stop is the "
        "same distance beyond the entry. Exit at 15:10. Variants: vwap 1.5 sideways, "
        "vwap 2.0 sideways, vwap 2.5 sideways. A strategy that trades only sideways "
        "days has empty up and down buckets.",
        "",
        "Reports: trades, distinct days, win rate (share of trades with R after "
        "costs above 0), average R before and after costs, t vs random, 2015-2019, "
        "2020-2024, up, down, sideways, large caps, and each year.",
    ])


def _win(value):
    if value is None:
        return "n/a"
    return "%.1f%%" % (100.0 * value)


def intraday_table(blocks):
    lines = [
        "variant | trades | days | win | R before | R after | t | 2015-19 | 2020-24 | up | down | sideways | large | result",
    ]
    for block in blocks:
        lines.append("%s | %s | %d | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s" % (
            block["name"], format(block["trades"], ",d"), block["days"], _win(block["win"]),
            _r(block["avg_before"]), _r(block["avg_after"]), _num(block["t"]),
            _r(block["early"]), _r(block["late"]), _r(block["up"]), _r(block["down"]),
            _r(block["sideways"]), _r(block["large"]), block["verdict"]["result"]))
    return lines


def intraday_report(stamp, blocks):
    lines = [intraday_rules(stamp), "", "Results."]
    lines.extend(intraday_table(blocks))
    lines.append("")
    passed = 0
    for block in blocks:
        verdict = block["verdict"]
        if verdict["result"] == "PASS":
            passed += 1
            lines.append("%s PASS." % block["name"])
        else:
            lines.append("%s FAIL: %s" % (block["name"], "; ".join(verdict["reasons"])))
        years = []
        for year in sorted(block["yearly"]):
            years.append("%d %s" % (year, _r(block["yearly"][year])))
        lines.append("  years: %s" % (", ".join(years) if years else "n/a"))
    lines.append("")
    lines.append("Variants that pass: %d of %d." % (passed, len(blocks)))
    return "\n".join(lines).rstrip() + "\n"


def intraday_rows(stamp, blocks):
    rows = []
    for block in blocks:
        if block["kind"] == "nifty_mom":
            universe = "NIFTY 50 5-minute, one lot of 75, 2015-01-01 to 2024-12-31"
        else:
            universe = "top 200 by prior 20-session turnover, 5-minute, 2015-01-01 to 2024-12-31"
        rows.append("| 12 | %s | %s | %s | %s | %s | %s | %s | %s |" % (
            stamp,
            "%s clears the attempt 12 intraday pass mark." % block["name"],
            "intraday batch 2, costs and 1 tick, Rs 2,000 risk, Rs 5,00,000 cap",
            universe,
            format(block["trades"], ",d"),
            _r(block["avg_before"]),
            _r(block["avg_after"]),
            block["verdict"]["result"]))
    return rows


def install_intraday(path, section, rows):
    """Insert or replace attempt 12. Leave attempt 11, the holdout note, and the forward test."""
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    kept = []
    for line in text.splitlines():
        if line.startswith("| 12 |"):
            continue
        kept.append(line)
    text = "\n".join(kept)
    if not text.endswith("\n"):
        text += "\n"
    heading = "\n## Attempt 12\n"
    block = "\n" + section.rstrip() + "\n\n"
    start = text.find(heading)
    if start != -1:
        nxt = text.find("\n## ", start + 1)
        end = nxt if nxt != -1 else len(text)
        text = text[:start] + block + text[end:]
    else:
        forward = text.find("\n## Forward test\n")
        if forward == -1:
            text = text.rstrip() + "\n" + block
        else:
            text = text[:forward] + block + text[forward:]
    if rows:
        at = text.rfind("\n| 11 |")
        if at == -1 and text.startswith("| 11 |"):
            at = 0
        elif at != -1:
            at += 1
        if at != -1:
            line_end = text.find("\n", at)
            if line_end == -1:
                line_end = len(text)
            text = text[:line_end] + "\n" + "\n".join(rows) + text[line_end:]
    if not text.endswith("\n"):
        text += "\n"
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


def intraday_main(args, emit):
    stamp = datetime.date.today().isoformat()
    install_intraday(args.experiments, intraday_rules(stamp), [])
    emit("rules written to %s before the run" % args.experiments)
    blocks = run_intraday(args.root, runs=args.runs, log=emit)
    install_intraday(args.experiments, intraday_report(stamp, blocks), intraday_rows(stamp, blocks))
    for line in intraday_table(blocks):
        emit(line)
    emit("")
    for block in blocks:
        verdict = block["verdict"]
        if verdict["result"] == "PASS":
            emit("%s PASS" % block["name"])
        else:
            emit("%s FAIL: %s" % (block["name"], "; ".join(verdict["reasons"])))
    return 0


def main(argv=None, log=None):
    import argparse
    parser = argparse.ArgumentParser(description="Strategy harness. Nothing is placed.")
    parser.add_argument("--root", default=os.path.join("data", "kite"))
    parser.add_argument("--experiments", default=EXPERIMENTS)
    parser.add_argument("--runs", type=int, default=RUNS)
    parser.add_argument("--intraday", action="store_true",
                        help="Attempt 12. Write the rules, then run the 12 intraday variants.")
    args = parser.parse_args(argv)
    emit = log or (lambda line: print(line, flush=True))
    if args.intraday:
        return intraday_main(args, emit)
    stamp = datetime.date.today().isoformat()
    install(args.experiments, rules_text(stamp), [])
    emit("rules written to %s before the run" % args.experiments)
    blocks, nifty = run(args.root, runs=args.runs, log=emit)
    install(args.experiments, results_text(stamp, blocks, nifty), table_rows(stamp, blocks))
    emit(summary_table(blocks, nifty))
    emit("")
    for block in [nifty] + blocks:
        emit(format_block(block, nifty if block is not nifty else None))
        emit("")
    return 0


if __name__ == "__main__":
    sys.exit(main())
