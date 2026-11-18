"""Step 33. Luck test, the 24c rolling comparison, and ETF tracking.

No verdict is changed. The catalogue is left as it stands.
"""

import csv
import datetime
import gzip
import math
import os
import statistics
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from india.research import batch22
from india.research import batch24
from india.research import batch25
from india.research import goldetf
from india.research import harness
from india.research import invest
from india.research import longterm

EXPERIMENTS = batch22.EXPERIMENTS
NSE = os.path.join(_ROOT, "data", "nse")
SAMPLE_END = datetime.date(2024, 12, 31)
HEADLINE_START = datetime.date(2005, 4, 1)
BOOK_START = datetime.date(2011, 1, 3)
BENCH = "NIFTY_200_TR"
# An ETF tracks an index when its daily-return correlation is at least this,
# and at least this far above its correlation with every other index here.
# A fund tracks an index when the daily-return correlation is at least this
# high and leads the next index by at least TRACK_GAP. NIFTY 50 and NIFTY 200
# move together, so that pair uses the wider minimum and the smaller lead.
TRACK_MIN = 0.90
TRACK_GAP = 0.04
BROAD_MIN = 0.95
BROAD_GAP = 0.004
MIN_RETURNS = 250
BROAD = ("NIFTY 50", "NIFTY 200")
TARGETS = (
    ("NIFTY_ALPHA_50_TR", "NIFTY Alpha 50"),
    ("NIFTY_MIDCAP_150_TR", "NIFTY Midcap 150"),
    ("NIFTY100_LOW_VOLATILITY_30_TR", "NIFTY100 Low Volatility 30"),
    ("NIFTY200_MOMENTUM_30_TR", "NIFTY200 Momentum 30"),
    ("NIFTY_200_TR", "NIFTY 200"),
    ("NIFTY_50_TR", "NIFTY 50"),
)
# The seven live-record indices other than the benchmark itself.
LUCK_COUNT = 7


def regularized_beta(a, b, x):
    """I_x(a, b), the regularized incomplete beta function."""
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    ln_bt = (
        math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b)
        + a * math.log(x) + b * math.log(1.0 - x)
    )
    bt = math.exp(ln_bt)
    if x < (a + 1.0) / (a + b + 2.0):
        return bt * _betacf(a, b, x) / a
    return 1.0 - bt * _betacf(b, a, 1.0 - x) / b


def _betacf(a, b, x):
    max_iter = 200
    eps = 3.0e-14
    fpmin = 1.0e-300
    qab = a + b
    qap = a + 1.0
    qam = a - 1.0
    c = 1.0
    d = 1.0 - qab * x / qap
    if abs(d) < fpmin:
        d = fpmin
    d = 1.0 / d
    h = d
    for m in range(1, max_iter + 1):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        if abs(d) < fpmin:
            d = fpmin
        c = 1.0 + aa / c
        if abs(c) < fpmin:
            c = fpmin
        d = 1.0 / d
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        if abs(d) < fpmin:
            d = fpmin
        c = 1.0 + aa / c
        if abs(c) < fpmin:
            c = fpmin
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < eps:
            return h
    return h


def student_t_sf(t, df):
    """One-sided P(T >= t). df is n - 1."""
    if df <= 0:
        return None
    x = float(df) / (float(df) + t * t)
    two = regularized_beta(0.5 * df, 0.5, x)
    if t >= 0:
        return 0.5 * two
    return 1.0 - 0.5 * two


def _month_ends(points, start, end):
    last = {}
    order = []
    for day, value in points:
        if day < start or day > end or value <= 0:
            continue
        key = (day.year, day.month)
        if key not in last:
            order.append(key)
        last[key] = (day, value)
    return [last[key] for key in order]


def monthly_excess(index_points, bench_points, start, end):
    """Index month return minus NIFTY 200 month return, on shared month-ends.

    The first month inside the window has no earlier month-end inside it, so
    the first return is dropped. A gap of more than one calendar month is dropped.
    """
    left = {}
    for day, value in _month_ends(index_points, start, end):
        left[(day.year, day.month)] = (day, value)
    right = {}
    for day, value in _month_ends(bench_points, start, end):
        right[(day.year, day.month)] = (day, value)
    keys = sorted(set(left) & set(right))
    excess = []
    for i in range(1, len(keys)):
        y0, m0 = keys[i - 1]
        y1, m1 = keys[i]
        if (y1 - y0) * 12 + (m1 - m0) != 1:
            continue
        e0 = left[keys[i - 1]][1]
        e1 = left[keys[i]][1]
        b0 = right[keys[i - 1]][1]
        b1 = right[keys[i]][1]
        if e0 <= 0 or b0 <= 0:
            continue
        excess.append((e1 / e0 - 1.0) - (b1 / b0 - 1.0))
    return excess


def rolling_ahead(index_points, bench_points, start, end, years=3):
    """Share of shared month-end windows where the index CAGR is higher."""
    left = {}
    for day, value in _month_ends(index_points, start, end):
        left[(day.year, day.month)] = (day, value)
    right = {}
    for day, value in _month_ends(bench_points, start, end):
        right[(day.year, day.month)] = (day, value)
    keys = sorted(set(left) & set(right))
    ahead = 0
    total = 0
    for key in keys:
        day = left[key][0]
        target = longterm._shift_years(day, -years)
        start_key = None
        for candidate in keys:
            if left[candidate][0] <= target:
                start_key = candidate
            else:
                break
        if start_key is None:
            continue
        if (day - left[start_key][0]).days < int(years * 365.25) - 45:
            continue
        ic = invest._cagr(left[start_key][1], left[key][1], left[start_key][0], left[key][0])
        bc = invest._cagr(right[start_key][1], right[key][1], right[start_key][0], right[key][0])
        if ic is None or bc is None:
            continue
        total += 1
        if ic > bc:
            ahead += 1
    return ahead, total


def _pct(value):
    if value is None:
        return "n/a"
    return "%+.2f%%" % (value * 100.0)


def _num(value, digits=2):
    if value is None:
        return "n/a"
    return "%.*f" % (digits, value)


def load_index(slug):
    path = os.path.join(batch24.INDEX_ROOT, slug + ".csv.gz")
    return batch24.read_series(path)


def luck_table(loaded, launches):
    """One row per live-record index that has a verdict. NIFTY 200 is included."""
    rows = []
    bench = loaded[BENCH]
    for slug, launch in batch25.official_rows(batch24.LAUNCH_PATH):
        label = batch25.LABELS.get(slug, slug)
        series = batch25._series_slug(loaded, slug)
        if series is None:
            continue
        start = batch25.first_session_after(loaded[series], launch)
        if start is None:
            continue
        end = loaded[series][-1][0]
        if bench[-1][0] < end:
            end = bench[-1][0]
        years = batch25.live_years(start, end)
        if years is None or years < batch25.MIN_YEARS:
            continue
        excess = monthly_excess(loaded[series], bench, start, end)
        ahead, total = rolling_ahead(loaded[series], bench, start, end, 3)
        mean = statistics.mean(excess) if excess else None
        std = statistics.stdev(excess) if len(excess) >= 2 else None
        t = harness.t_stat(excess)
        share = None if total == 0 else ahead / float(total)
        rows.append({
            "label": label,
            "slug": series,
            "start": start,
            "end": end,
            "n": len(excess),
            "mean": mean,
            "std": std,
            "t": t,
            "ahead": ahead,
            "windows": total,
            "share": share,
            "years": years,
        })
    return rows


def bonferroni(rows):
    """One-sided p of Alpha 50's t, times 7."""
    alpha = None
    for row in rows:
        if row["label"] == "Alpha 50":
            alpha = row
            break
    if alpha is None or alpha["t"] is None or alpha["n"] < 2:
        return None
    p = student_t_sf(alpha["t"], alpha["n"] - 1)
    return {"t": alpha["t"], "n": alpha["n"], "p": p, "bound": p * LUCK_COUNT}


def _book(loaded, weights, kinds, expenses, launches, start, end):
    return longterm.simulate(
        dict((name, loaded[name]) for name in weights),
        weights, kinds, start, end,
        capital=batch24.CAPITAL, expenses=expenses, bands=False, launches=launches,
    )


def _nifty_weights():
    return {BENCH: 1.0}


def roll_compare(loaded, table):
    """Each 24c book's 10-year minimum against the old and the same-start benchmark."""
    gsec = "NIFTY_10YR_BENCHMARK_GSEC"
    gold = "GOLD_ETF"
    alpha = "NIFTY_ALPHA_50_TR"
    low = "NIFTY100_LOW_VOLATILITY_30_TR"
    books = []
    for alloc, eq, gs, gd in batch24.ALLOCATIONS:
        books.append((
            "24c %s NIFTY 200" % alloc,
            {BENCH: eq, gsec: gs, gold: gd},
        ))
        books.append((
            "24c %s Alpha50+LowVol" % alloc,
            {alpha: eq / 2.0, low: eq / 2.0, gsec: gs, gold: gd},
        ))
    factors = set(slug for slug, _label, _debt, is_factor in batch24.SINGLES if is_factor)
    debt = set(slug for slug, _label, is_debt, _factor in batch24.SINGLES if is_debt)
    headline = _book(
        loaded, _nifty_weights(), {BENCH: "equity"},
        {BENCH: longterm.BROAD_EXPENSE}, {BENCH: batch24.launch_of(table, BENCH)},
        HEADLINE_START, SAMPLE_END,
    )
    same = _book(
        loaded, _nifty_weights(), {BENCH: "equity"},
        {BENCH: longterm.BROAD_EXPENSE}, {BENCH: batch24.launch_of(table, BENCH)},
        BOOK_START, SAMPLE_END,
    )
    out = []
    for name, weights in books:
        kinds = {}
        expenses = {}
        launches = {}
        for sleeve in weights:
            kinds[sleeve] = "debt" if sleeve in debt else "equity"
            if sleeve == gold:
                expenses[sleeve] = 0.0
            else:
                expenses[sleeve] = longterm.expense_for(sleeve in factors)
            launches[sleeve] = batch24.launch_of(table, sleeve)
        row = _book(loaded, weights, kinds, expenses, launches, BOOK_START, SAMPLE_END)
        # The stored verdict used a NIFTY 200 book from this book's own start.
        old_bench = _book(
            loaded, _nifty_weights(), {BENCH: "equity"},
            {BENCH: longterm.BROAD_EXPENSE}, {BENCH: batch24.launch_of(table, BENCH)},
            row["start"], row["end"],
        )
        book_min = row["roll10"][0]
        old_min = old_bench["roll10"][0]
        new_min = same["roll10"][0]
        old_ok, old_why = longterm.passes(row, old_bench)
        new_bench = dict(old_bench)
        new_bench["roll10"] = same["roll10"]
        new_ok, new_why = longterm.passes(row, new_bench)
        headline_bench = dict(old_bench)
        headline_bench["roll10"] = headline["roll10"]
        head_ok, head_why = longterm.passes(row, headline_bench)
        out.append({
            "name": name,
            "start": row["start"],
            "book_min": book_min,
            "old_min": old_min,
            "new_min": new_min,
            "headline_min": headline["roll10"][0],
            "old_pass": old_ok,
            "new_pass": new_ok,
            "old_why": old_why,
            "new_why": new_why,
            "changed": old_ok != new_ok,
            "headline_pass": head_ok,
            "headline_why": head_why,
        })
    return out


def _splits(actions_root):
    """symbol -> {ex-date: factor} for EQ face-value splits. One factor per date."""
    found = {}
    if not os.path.isdir(actions_root):
        return found
    for name in sorted(os.listdir(actions_root)):
        if not name.endswith(".csv.gz"):
            continue
        path = os.path.join(actions_root, name)
        with gzip.open(path, "rt", encoding="utf-8", newline="") as fh:
            for row in csv.DictReader(fh):
                if (row.get("series") or "").strip() != "EQ":
                    continue
                factor = goldetf.unit_split_factor(row.get("purpose") or "")
                if factor is None:
                    continue
                symbol = (row.get("symbol") or "").strip()
                text = (row.get("date") or "")[:10]
                if not symbol or len(text) < 10:
                    continue
                day = datetime.date.fromisoformat(text)
                bucket = found.setdefault(symbol, {})
                previous = bucket.get(day)
                if previous is None:
                    bucket[day] = factor
                elif abs(previous - factor) > 1e-12:
                    bucket[day] = previous * factor
    return found


def _pearson(xs, ys):
    n = len(xs)
    if n < 3:
        return None
    mx = sum(xs) / float(n)
    my = sum(ys) / float(n)
    sxx = 0.0
    syy = 0.0
    sxy = 0.0
    for x, y in zip(xs, ys):
        dx = x - mx
        dy = y - my
        sxx += dx * dx
        syy += dy * dy
        sxy += dx * dy
    if sxx <= 0.0 or syy <= 0.0:
        return None
    return sxy / math.sqrt(sxx * syy)


def load_etfs(cm_root):
    """INF series EQ closes, volume and turnover. Session date is the file name."""
    found = {}
    calendar = []
    if not os.path.isdir(cm_root):
        return found, calendar
    for name in sorted(os.listdir(cm_root)):
        if not name.endswith(".csv.gz"):
            continue
        text = name[:10]
        try:
            day = datetime.date.fromisoformat(text)
        except ValueError:
            continue
        if day.year < 1990:
            continue
        calendar.append(day)
        path = os.path.join(cm_root, name)
        with gzip.open(path, "rt", encoding="utf-8", newline="") as fh:
            for row in csv.DictReader(fh):
                isin = (row.get("isin") or "").strip()
                if not isin.startswith("INF"):
                    continue
                if (row.get("series") or "").strip() != "EQ":
                    continue
                symbol = (row.get("symbol") or "").strip()
                if not symbol:
                    continue
                try:
                    close = float(row.get("close") or "")
                    volume = float(row.get("volume") or "0")
                    turnover = float(row.get("turnover") or "0")
                except ValueError:
                    continue
                if close <= 0:
                    continue
                bucket = found.get(symbol)
                if bucket is None:
                    bucket = {"isin": isin, "rows": []}
                    found[symbol] = bucket
                bucket["rows"].append((day, close, volume, turnover))
    return found, calendar


def _price_breaks(points):
    breaks = []
    prev = None
    for day, close in points:
        if prev is not None and prev[1] > 0:
            ratio = close / prev[1]
            if ratio < 0.2 or ratio > 5.0:
                breaks.append((prev[0], day, ratio))
        prev = (day, close)
    return breaks


def _daily_corr(etf_points, index_points):
    index = {}
    for day, value in index_points:
        index[day] = value
    common = []
    for day, close in etf_points:
        if day in index:
            common.append((day, close, index[day]))
    xs = []
    ys = []
    for i in range(1, len(common)):
        gap = (common[i][0] - common[i - 1][0]).days
        if gap <= 0 or gap > 7:
            continue
        e0 = common[i - 1][1]
        i0 = common[i - 1][2]
        if e0 <= 0 or i0 <= 0:
            continue
        xs.append(common[i][1] / e0 - 1.0)
        ys.append(common[i][2] / i0 - 1.0)
    return _pearson(xs, ys), len(xs)


def _named_index(symbol):
    """The index a symbol's letters name, when the letters are specific."""
    name = symbol.upper()
    if any(word in name for word in ("SENSEX", "BANK", "GOLD", "SILVER", "NEXT", "INFRA")):
        return None
    if "LOWVOL" in name:
        return "NIFTY100 Low Volatility 30"
    if "MOM30" in name or "MOMENTUM" in name or "MOMENT" in name:
        return "NIFTY200 Momentum 30"
    if "ALPHA" in name and "ALPL" not in name:
        return "NIFTY Alpha 50"
    if "MID150" in name or "MIDCAP" in name:
        return "NIFTY Midcap 150"
    if "N200" in name:
        return "NIFTY 200"
    if "NIFTY" in name and "500" not in name and "100" not in name:
        return "NIFTY 50"
    return None


def etf_table(etfs, calendar, splits, indices):
    """ETFs whose daily returns track one of the target indices.

    Returns the assigned funds and the named funds that did not clear the bar.
    """
    calendar_set = set(calendar)
    rows = []
    missed = []
    for symbol in sorted(etfs):
        bucket = etfs[symbol]
        raw = [(day, close) for day, close, _volume, _turnover in bucket["rows"]]
        adjusted = goldetf.apply_unit_splits(raw, splits.get(symbol) or {})
        scores = []
        for slug, label in TARGETS:
            corr, n = _daily_corr(adjusted, indices[slug])
            scores.append((corr, n, slug, label))
        scores.sort(key=lambda item: -1.0 if item[0] is None else -item[0])
        best = scores[0]
        second = scores[1]
        named = _named_index(symbol)
        assigned = True
        if best[0] is None or best[1] < MIN_RETURNS:
            assigned = False
        else:
            lead = None if second[0] is None else best[0] - second[0]
            broad = best[3] in BROAD and second[3] in BROAD
            if broad:
                if best[0] < BROAD_MIN or lead is None or lead < BROAD_GAP:
                    assigned = False
            elif best[0] < TRACK_MIN or lead is None or lead < TRACK_GAP:
                assigned = False
        if not assigned:
            if named is not None and best[0] is not None and best[1] >= MIN_RETURNS and best[0] >= 0.45:
                named_corr = None
                for corr, _n, _slug, label in scores:
                    if label == named:
                        named_corr = corr
                missed.append({
                    "symbol": symbol,
                    "named": named,
                    "best": best[3],
                    "corr": best[0],
                    "named_corr": named_corr,
                    "second": second[3],
                    "lead": None if second[0] is None else best[0] - second[0],
                    "n": best[1],
                    "splits": len(splits.get(symbol) or {}),
                    "breaks": _price_breaks(adjusted),
                })
            continue
        by_day = {}
        for day, close in adjusted:
            by_day[day] = close
        index = indices[best[2]]
        index_by = {}
        for day, value in index:
            index_by[day] = value
        shared = sorted(set(by_day) & set(index_by))
        if len(shared) < 2:
            continue
        etf_cagr = invest._cagr(by_day[shared[0]], by_day[shared[-1]], shared[0], shared[-1])
        tri_cagr = invest._cagr(index_by[shared[0]], index_by[shared[-1]], shared[0], shared[-1])
        gap = None
        if etf_cagr is not None and tri_cagr is not None:
            gap = etf_cagr - tri_cagr
        turnovers = []
        traded = set()
        first = bucket["rows"][0][0]
        last = bucket["rows"][-1][0]
        for day, _close, volume, turnover in bucket["rows"]:
            if volume > 0:
                traded.add(day)
                turnovers.append(turnover)
        silent = 0
        for day in calendar_set:
            if first <= day <= last and day not in traded:
                silent += 1
        rows.append({
            "symbol": symbol,
            "isin": bucket["isin"],
            "index": best[3],
            "slug": best[2],
            "corr": best[0],
            "start": shared[0],
            "end": shared[-1],
            "etf_cagr": etf_cagr,
            "tri_cagr": tri_cagr,
            "gap": gap,
            "median": statistics.median(turnovers) if turnovers else None,
            "silent": silent,
            "splits": len(splits.get(symbol) or {}),
            "breaks": _price_breaks(adjusted),
        })
    rows.sort(key=lambda item: (item["index"], item["start"], item["symbol"]))
    missed.sort(key=lambda item: (item["named"], -item["corr"], item["symbol"]))
    return rows, missed


def _line_luck(row):
    share = "n/a" if row["share"] is None else "%.1f%%" % (row["share"] * 100.0)
    return "%s | %s to %s | n %d | mean %s | std %s | t %s | 3y ahead %s (%d/%d)" % (
        row["label"], row["start"].isoformat(), row["end"].isoformat(), row["n"],
        _pct(row["mean"]), _pct(row["std"]), _num(row["t"]),
        share, row["ahead"], row["windows"],
    )


def _line_roll(row):
    flag = "VERDICT WOULD CHANGE" if row["changed"] else "verdict unchanged"
    return (
        "%s | start %s | book min %s | old bench min %s | new bench min %s | "
        "headline 2005-04-01 min %s | old %s | new %s | %s"
        % (
            row["name"], row["start"].isoformat(),
            _pct(row["book_min"]), _pct(row["old_min"]), _pct(row["new_min"]),
            _pct(row["headline_min"]),
            "PASS" if row["old_pass"] else "FAIL",
            "PASS" if row["new_pass"] else "FAIL",
            flag,
        )
    )


def _rupees(value):
    if value is None:
        return "n/a"
    return format(value, ",.0f")


def _line_etf(row):
    breaks = ""
    if row["breaks"] and row["splits"] == 0:
        breaks = " | no split row; price not adjusted"
    elif row["breaks"]:
        breaks = " | price break remains after the actions-file splits"
    return (
        "%s | %s | %s to %s | ETF %s | index TRI %s | difference %s | "
        "median turnover Rs %s | days with no trade %d | splits %d%s"
        % (
            row["symbol"], row["index"], row["start"].isoformat(), row["end"].isoformat(),
            _pct(row["etf_cagr"]), _pct(row["tri_cagr"]), _pct(row["gap"]),
            _rupees(row["median"]), row["silent"], row["splits"], breaks,
        )
    )


def _line_miss(row):
    breaks = ""
    if row["breaks"] and row["splits"] == 0:
        breaks = " | no split row; price not adjusted"
    elif row["breaks"]:
        breaks = " | price break remains after the actions-file splits"
    return "%s | letters say %s (corr %s) | closest %s (corr %s, lead %s) | days %d | splits %d%s" % (
        row["symbol"], row["named"], _num(row["named_corr"], 3),
        row["best"], _num(row["corr"], 3), _num(row["lead"], 4),
        row["n"], row["splits"], breaks,
    )


def conclusions_text(luck, bound, rolls, etfs, missed):
    changed = [row["name"] for row in rolls if row["changed"]]
    headline_changed = [row["name"] for row in rolls if row["headline_pass"] != row["old_pass"]]
    if changed:
        change_line = "A same-start minimum would change the verdict of: %s. The catalogue was not changed." % ", ".join(changed)
    else:
        change_line = "No 24c verdict would change. The catalogue was not changed."
    if headline_changed:
        headline_line = "Against the 2005-04-01 minimum the verdict would change for: %s. That is not the comparison the stored verdict used." % ", ".join(headline_changed)
    else:
        headline_line = "Against the 2005-04-01 minimum the verdict would not change either. The two NIFTY 200 mixes already fail the CAGR clause, and the two Alpha mixes already beat the higher same-start minimum."
    lines = [
        "## Conclusions (research phase 1)",
        "",
        "Step 33, 2026-11-18. No verdict was changed.",
        "",
        "Trading verdict. No rule is in the Bucket: nothing has an in-sample pass and a holdout pass. Attempt 23 closed short-term stock picking, and factor exposure from here goes through index funds. The Watch list is still open and is not a pass: rsi2 < 5, m2 regime, rel rsi5, rel rsi5 stock10, tom rsi20, the S2 ATM straddle, and nifty basis 5d. Each of those was positive after costs on the holdout and none had a holdout t above 2.",
        "",
        "Investing verdict. On the live record, only NIFTY Alpha 50 clears the attempt 25 bar. Its monthly excess over NIFTY 200 TRI is in the luck table below. The other live indices do not clear the bar. Midcap150 Momentum 50 is under 5 live years and has no verdict. The back-tested factor books that passed attempt 24 in sample failed the 2025 holdout. Two of the four 24c mixes passed in sample on a window that includes back-test years, and both failed that same holdout. The 10-month rule on the best 24c book failed in sample. Value 20 and gold are marked (back-test years included) because a blank launch date is unknown, and unknown is not live.",
        "",
        "Luck test, attempt 25 live window through the last index date, monthly excess versus NIFTY 200 TRI. The t is the one-sample t of those monthly excesses, sample standard deviation. A rolling 3-year window counts as ahead only when the index CAGR is higher. NIFTY 50's file starts on 2005-01-03, after its 1996-04-22 launch, and that comparison uses NIFTY 200 TRI before the NIFTY 200 launch on 2011-07-19.",
        "",
    ]
    for row in luck:
        lines.append(_line_luck(row))
    if bound is not None:
        lines.append("")
        lines.append(
            "Alpha 50 t %s on %d months. One-sided p %s. Bonferroni, p times 7: %s. This is the chance bound that the best of the 7 indices other than NIFTY 200 reaches a t this large when every monthly excess has mean zero."
            % (_num(bound["t"]), bound["n"], "%.4g" % bound["p"], "%.4g" % bound["bound"])
        )
    lines.append("")
    lines.append(
        "24c rolling 10-year comparison. Old bench min is the NIFTY 200 book the stored verdict used, run from that book's own start through 2024-12-31, after the same expense and tax. New bench min is the NIFTY 200 book from 2011-01-03 through 2024-12-31. The headline minimum is the NIFTY 200 book from 2005-04-01, the figure on the 24a row. Higher, in the rolling clause, is strict."
    )
    lines.append("")
    for row in rolls:
        lines.append(_line_roll(row))
        if row["old_why"] or row["new_why"]:
            lines.append("  same-start: " + "; ".join(row["new_why"]))
    lines.append(change_line)
    lines.append(headline_line)
    lines.append("")
    lines.append(
        "Tracking differences. An exchange-traded fund is an INF symbol in series EQ. The cash file has no fund name. A fund is assigned when it has at least %d overlapping daily returns and its correlation with one index TRI is the highest of the six. The lead over the next index must be at least %.2f, and the correlation at least %.2f. NIFTY 50 and NIFTY 200 move together, so when those two are the top pair the correlation must be at least %.2f and the lead at least %.3f. Prices are adjusted only for face-value splits in the actions files. Where the mutual-fund feed had a split the equities file did not, that EQ row was copied into the actions file and then read back. The difference is the ETF price CAGR minus the index TRI CAGR from the first shared date to the last. Median turnover is rupees, on days with volume above zero. Days with no trade are market sessions from the fund's first print to its last print with no EQ volume."
        % (MIN_RETURNS, TRACK_GAP, TRACK_MIN, BROAD_MIN, BROAD_GAP)
    )
    lines.append("")
    if not etfs:
        lines.append("No ETF cleared the tracking rule.")
    for row in etfs:
        lines.append(_line_etf(row))
    if not any(row["index"] == "NIFTY 200" for row in etfs):
        lines.append("No fund cleared the bar as a NIFTY 200 tracker. The NIFTY 50 funds above are closer to NIFTY 50 than to NIFTY 200, and GROWWN200's daily correlation with NIFTY 200 TRI is about 0.59.")
    lines.append("")
    lines.append("Named funds that did not clear that bar. MOMENTUM50, MOMMIDCAP and a momentum-50 symbol are not treated as NIFTY200 Momentum 30 from the letters alone, and ALPL30 is not treated as NIFTY Alpha 50.")
    if not missed:
        lines.append("None.")
    for row in missed:
        lines.append(_line_miss(row))
    lines.append("")
    lines.append(
        "Open items. The Watch list above is unconfirmed. The forward record in the section above this one started 2026-11-04, has no filled numbers, and stays IN PROGRESS until 30 qualifying days. nse_holidays.py covers 2010 through 2026 and has no 2027 holiday list."
    )
    lines.append("")
    return "\n".join(lines)


def write_conclusions(section):
    with open(EXPERIMENTS, encoding="utf-8") as fh:
        text = fh.read()
    heading = "\n## Conclusions (research phase 1)\n"
    start = text.find(heading)
    block = "\n" + section.rstrip() + "\n"
    if start != -1:
        text = text[:start] + block
    else:
        if not text.endswith("\n"):
            text += "\n"
        text = text + block
    if not text.endswith("\n"):
        text += "\n"
    with open(EXPERIMENTS, "w", encoding="utf-8") as fh:
        fh.write(text)


def main(argv=None):
    del argv
    log = lambda line: print(line, flush=True)
    loaded = {}
    for name in os.listdir(batch24.INDEX_ROOT):
        if not name.endswith(".csv.gz"):
            continue
        slug = name[:-7]
        loaded[slug] = batch24.read_series(os.path.join(batch24.INDEX_ROOT, name))
    table = batch24.load_launches(batch24.LAUNCH_PATH)
    luck = luck_table(loaded, table)
    bound = bonferroni(luck)
    log("Luck test")
    for row in luck:
        log(_line_luck(row))
    if bound is not None:
        log("Alpha 50 t %s p %s bonferroni %s" % (
            _num(bound["t"]), "%.6g" % bound["p"], "%.6g" % bound["bound"]))
    rolls = roll_compare(loaded, table)
    log("24c rolling")
    for row in rolls:
        log(_line_roll(row))
    log("reading ETFs")
    etfs, calendar = load_etfs(os.path.join(NSE, "cm"))
    log("INF symbols %d" % len(etfs))
    splits = _splits(os.path.join(NSE, "actions"))
    indices = {}
    for slug, _label in TARGETS:
        indices[slug] = loaded[slug]
    funds, missed = etf_table(etfs, calendar, splits, indices)
    log("trackers %d missed %d" % (len(funds), len(missed)))
    for row in funds:
        log(_line_etf(row))
    for row in missed:
        log(_line_miss(row))
    section = conclusions_text(luck, bound, rolls, funds, missed)
    write_conclusions(section)
    log("conclusions written")
    return 0


if __name__ == "__main__":
    sys.exit(main())
