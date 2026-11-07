#!/usr/bin/env python3
"""Survivorship of the attempt-11 momentum books, then the one holdout run.

The stock files are today's survivors. A random K=30 book from that list can
beat a real index even when the rule has no skill. This script measures that
gap against the NIFTY 200 price index, and compares mom 12-1 K30 with the
NIFTY200 Momentum 30 price index.

The default window is 2005-01-01 through 2024-12-31. --holdout is the only
way to read 2025 on, and it passes final=True so the read is logged.

    python3 india/research/survivorship.py
    python3 india/research/survivorship.py --holdout
"""

import datetime
import os
import random
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from india.research import data
from india.research import harness as h
from india.research import signal_lab as lab

START = h.START
END = h.END
HOLDOUT_START = data.HOLDOUT_START
NIFTY_200 = "NIFTY 200"
MOMENTUM_INDEX = "NIFTY200MOMENTM30"
K30_NAME = "mom 12-1 K30"
PASSER_NAME = "mom 12-1 K20 above200"
RUNS = h.RUNS
EXPERIMENTS = h.EXPERIMENTS
QUOTE = (
    "PASS in-sample, but inflated by survivorship bias; real NIFTY200 Momentum 30 TRI: "
    "18.8% CAGR vs NIFTY 50 TRI 13.6% since Apr 2005 (HDFC MF, Jul 2026)"
)
NEEDLES = ("MOMENT", "ALPHA", "LOWVOL", "LOW VOL", "QUALT", "VALUE", "EQL")
EXACT = ("NIFTY 200", "NIFTY 500", "NIFTY MIDCAP 150", "NIFTY SMLCAP 250")
HEAD_CALIBRATION = "### Survivorship calibration"
HEAD_HOLDOUT = "### Holdout of mom 12-1 K20 above200"


def select_indices(names):
    """NSE index names the factor download keeps. Order is alphabetical."""
    found = []
    seen = set()
    for name in names:
        text = (name or "").strip()
        upper = text.upper()
        if not upper or upper in seen:
            continue
        if upper in EXACT or any(needle in upper for needle in NEEDLES):
            seen.add(upper)
            found.append(text)
    found.sort()
    return found


def raw_span(path):
    """(first date, last date) in a Kite daily file, before the listing cut."""
    import csv
    import gzip
    first = None
    last = None
    with gzip.open(path, "rt", encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            day = datetime.date.fromisoformat(row["datetime_start_ist"][:10])
            if first is None or day < first:
                first = day
            if last is None or day > last:
                last = day
    return first, last


def spec_named(name):
    specs = h.batch1()
    for index, spec in enumerate(specs):
        if spec["name"] == name:
            return index, spec
    raise KeyError(name)


def close_cagr(dates, values):
    """Close-to-close CAGR in percent. Years are days / 365.25."""
    if dates is None or values is None or len(dates) < 2 or len(values) != len(dates):
        return None
    start = values[0]
    final = values[-1]
    if not start > 0 or not final > 0:
        return None
    days = (dates[-1] - dates[0]).days
    if days <= 0:
        return None
    years = days / h.YEAR_DAYS
    return ((final / start) ** (1.0 / years) - 1.0) * 100.0


def yearly_returns(dates, values):
    """Percent change by calendar year.

    The first year runs from the first mark to that year's last mark.
    Each later year runs from the previous year-end mark.
    """
    if not dates or len(dates) != len(values):
        return {}
    ends = {}
    first = None
    for day, value in zip(dates, values):
        if not value > 0:
            continue
        if first is None:
            first = value
        ends[day.year] = value
    out = {}
    prev = first
    started = False
    for year in sorted(ends):
        if prev and ends[year] > 0:
            if not started:
                out[year] = (ends[year] / first - 1.0) * 100.0
                started = True
            else:
                out[year] = (ends[year] / prev - 1.0) * 100.0
        prev = ends[year]
    return out


def mean_number(values):
    kept = [value for value in values if value is not None]
    if not kept:
        return None
    return sum(kept) / float(len(kept))


def mean_yearly(series):
    years = []
    seen = set()
    for row in series:
        for year in row:
            if year not in seen:
                seen.add(year)
                years.append(year)
    years.sort()
    out = {}
    for year in years:
        out[year] = mean_number([row.get(year) for row in series])
    return out


def year_diff(left, right):
    """left[year] - right[year] for years present in both."""
    out = {}
    for year in left:
        if year in right and left[year] is not None and right[year] is not None:
            out[year] = left[year] - right[year]
    return out


def bias_cagr(random_cagr, index_cagr):
    if random_cagr is None or index_cagr is None:
        return None
    return random_cagr - index_cagr


def adjusted_cagr(mom_cagr, bias):
    if mom_cagr is None or bias is None:
        return None
    return mom_cagr - bias


def overlap_dates(calendar, bars):
    dates = []
    for day in calendar:
        bar = bars.get(day)
        if bar is not None and bar.get("close", 0) > 0:
            dates.append(day)
    return dates


def values_on(calendar, equity, dates):
    lookup = {}
    for day, value in zip(calendar, equity):
        lookup[day] = value
    return [lookup[day] for day in dates]


def bars_from_segments(segments):
    bars = {}
    for seg in segments:
        for i, day in enumerate(seg.date):
            bars[day] = {"open": seg.o[i], "close": seg.c[i]}
    return bars


def load_index(root, symbol, end, final=False, log_path=None):
    segments = lab.load_symbol(root, symbol, end=end, final=final, log_path=log_path)
    return bars_from_segments(segments)


def portfolio_equity(ctx, spec, rng):
    picks = h._portfolio_picks(spec, ctx["pairs"], ctx["top200"], ctx["by_name"], ctx["above"], rng)
    return h.simulate_portfolio(ctx["pairs"], picks, ctx["calendar"], ctx["nifty"], ctx["by_name"])


def collect_paths(ctx, spec, runs, seed, log):
    """Official book, then `runs` random books. Equity lists match ctx['calendar']."""
    official = portfolio_equity(ctx, spec, None)
    random_paths = []
    for run_i in range(runs):
        if log is not None and runs > 1 and run_i % 25 == 0:
            log("  random %d/%d" % (run_i + 1, runs))
        rng = random.Random(seed + run_i)
        random_paths.append(portfolio_equity(ctx, spec, rng))
    return official, random_paths


def summarise_paths(calendar, paths, bars):
    """Mean CAGR and mean yearly return of the paths, plus the index, on shared dates."""
    dates = overlap_dates(calendar, bars)
    closes = [bars[day]["close"] for day in dates]
    cagrs = []
    yearly = []
    for equity in paths:
        values = values_on(calendar, equity, dates)
        cagrs.append(close_cagr(dates, values))
        yearly.append(yearly_returns(dates, values))
    return {
        "dates": dates,
        "mean_cagr": mean_number(cagrs),
        "mean_yearly": mean_yearly(yearly),
        "index_cagr": close_cagr(dates, closes),
        "index_yearly": yearly_returns(dates, closes),
        "cagrs": cagrs,
        "yearly": yearly,
    }


def build_report(calendar, mom_equity, random_paths, nifty200, momentum):
    """Parts (a), (b) and (c). Price closes only."""
    broad = summarise_paths(calendar, random_paths, nifty200)
    mom_book = summarise_paths(calendar, [mom_equity], momentum)
    bias = bias_cagr(broad["mean_cagr"], broad["index_cagr"])
    bias_years = year_diff(broad["mean_yearly"], broad["index_yearly"])
    mom_years = mom_book["mean_yearly"]
    adjusted_years = {}
    for year in mom_years:
        if year in bias_years and mom_years[year] is not None:
            adjusted_years[year] = mom_years[year] - bias_years[year]
    return {
        "broad": broad,
        "mom": mom_book,
        "bias": bias,
        "bias_years": bias_years,
        "adjusted": adjusted_cagr(mom_book["mean_cagr"], bias),
        "adjusted_years": adjusted_years,
    }


def _pct(value):
    if value is None:
        return "n/a"
    return "%+.3f%%" % value


def _span(dates):
    if not dates:
        return "no shared dates"
    return "%s to %s (%d sessions)" % (dates[0].isoformat(), dates[-1].isoformat(), len(dates))


def format_calibration(report, quote=True):
    """The attempt-11 note. No result here changes the pass mark."""
    broad = report["broad"]
    mom = report["mom"]
    lines = [HEAD_CALIBRATION, ""]
    if quote:
        lines.extend([QUOTE, ""])
    lines.extend([
        "Price indices only. Dividends are excluded. Our momentum book is monthly "
        "and equal weight, with no volatility scaling and no 5% caps. The published "
        "NIFTY200 Momentum 30 index is a different portfolio. CAGR below is "
        "close-to-close on the shared sessions, annualised with 365.25-day years. "
        "The attempt 11 pass mark is unchanged.",
        "",
        "Random K=30 books: %d runs, seed %d. These are the attempt 11 random "
        "draws for %s." % (report["runs"], report["seed"], K30_NAME),
        "NIFTY 200 overlap: %s." % _span(broad["dates"]),
        "Random K=30 mean CAGR %s. NIFTY 200 CAGR %s. Survivorship bias "
        "(random minus NIFTY 200) %s." % (
            _pct(broad["mean_cagr"]), _pct(broad["index_cagr"]), _pct(report["bias"])),
        "",
        "%s overlap with %s: %s." % (K30_NAME, MOMENTUM_INDEX, _span(mom["dates"])),
        "%s CAGR %s. %s price CAGR %s." % (
            K30_NAME, _pct(mom["mean_cagr"]), MOMENTUM_INDEX, _pct(mom["index_cagr"])),
        "%s CAGR minus the NIFTY 200 survivorship bias: %s, next to %s %s." % (
            K30_NAME, _pct(report["adjusted"]), MOMENTUM_INDEX, _pct(mom["index_cagr"])),
        "",
        "year | bias (random K=30 minus NIFTY 200) | %s | that year minus the bias | %s" % (
            K30_NAME, MOMENTUM_INDEX),
    ])
    years = set(report["bias_years"])
    years.update(mom["mean_yearly"])
    years.update(mom["index_yearly"])
    for year in sorted(years):
        lines.append("%d | %s | %s | %s | %s" % (
            year,
            _pct(report["bias_years"].get(year)),
            _pct(mom["mean_yearly"].get(year)),
            _pct(report["adjusted_years"].get(year)),
            _pct(mom["index_yearly"].get(year)),
        ))
    return "\n".join(lines).rstrip() + "\n"


def format_holdout(block, nifty_stats, mom_stats, calibration):
    """The single 2025-on record. The rule stays as attempt 11 wrote it."""
    lines = [
        HEAD_HOLDOUT,
        "",
        "One holdout run of %s, logged with final=True. Window %s. "
        "The book is the attempt 11 rule: monthly 12-1 momentum, K=20, held only "
        "when the NIFTY month-end close is above its 200-day average, otherwise "
        "the book is NIFTY 50. Idle cash is in the NIFTY 50 price. Delivery costs "
        "apply to stock buys and sells. Dividends are excluded. CAGR is annualised "
        "with 365.25-day years. The attempt 11 rule is unchanged."
        % (PASSER_NAME, _span(block["dates"])),
        "",
        "%s: CAGR %s, max drawdown %s, mean monthly excess vs NIFTY 50 %s over %d months." % (
            PASSER_NAME, _pct(block["cagr"]), _pct(block["max_dd"]),
            _pct(block["excess"]), block.get("n_months") or 0),
        "NIFTY 50 over the same dates: CAGR %s, max drawdown %s." % (
            _pct(nifty_stats["cagr"]), _pct(nifty_stats["max_dd"])),
        "%s over %s: CAGR %s, max drawdown %s, mean monthly excess of the book vs this index %s." % (
            MOMENTUM_INDEX, _span(mom_stats["dates"]),
            _pct(mom_stats["cagr"]), _pct(mom_stats["max_dd"]),
            _pct(mom_stats["excess"])),
        "",
        "The same survivorship comparison on this window:",
        "",
        format_calibration(calibration, quote=False).split("\n", 2)[-1].rstrip(),
    ]
    return "\n".join(lines).rstrip() + "\n"


def install(path, section):
    """Insert or replace one heading. Leave the attempt 11 rows and the forward test."""
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    if not text.endswith("\n"):
        text += "\n"
    heading = section.splitlines()[0].strip()
    marker = "\n%s\n" % heading
    block = "\n" + section.rstrip() + "\n\n"
    start = text.find(marker)
    if start != -1:
        nxt = text.find("\n#", start + 1)
        end = nxt if nxt != -1 else len(text)
        text = text[:start] + block + text[end:]
    else:
        forward = text.find("\n## Forward test\n")
        if forward == -1:
            text = text.rstrip() + "\n" + block
        else:
            text = text[:forward] + block + text[forward:]
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


def index_file_lines(root):
    """Names and raw first dates for the factor indices that are on disk."""
    folder = os.path.join(root, "day")
    lines = []
    if not os.path.isdir(folder):
        return lines
    names = []
    for filename in os.listdir(folder):
        if filename.endswith(".csv.gz"):
            names.append(filename[:-len(".csv.gz")])
    for name in select_indices(names):
        first, last = raw_span(os.path.join(folder, name + ".csv.gz"))
        lines.append("%s first %s last %s" % (
            name,
            first.isoformat() if first else "n/a",
            last.isoformat() if last else "n/a"))
    return lines


def _benchmark(dates, bars, capital):
    """Buy-and-hold of an open/close series. Same capital and same dates as the book."""
    nifty = {}
    for day in dates:
        bar = bars[day]
        nifty[day] = {"open": bar["open"], "close": bar["close"]}
    equity = h.nifty_path(dates, nifty, capital)
    stats = h.path_stats(dates, equity, capital, nifty, {})
    stats["dates"] = dates
    return stats


def run_window(root, start, end, final, runs, log, log_path=None):
    emit = log or (lambda line: None)
    ctx = h.load_context(root, start=start, end=end, log=emit, final=final, log_path=log_path)
    index_200 = load_index(root, NIFTY_200, end, final=final, log_path=log_path)
    momentum = load_index(root, MOMENTUM_INDEX, end, final=final, log_path=log_path)
    k30_index, k30 = spec_named(K30_NAME)
    seed = h.SEED + k30_index * 1000
    emit("scoring %s and %d random books" % (K30_NAME, runs))
    mom_equity, random_paths = collect_paths(ctx, k30, runs, seed, emit)
    report = build_report(ctx["calendar"], mom_equity, random_paths, index_200, momentum)
    report["runs"] = runs
    report["seed"] = seed
    report["ctx"] = ctx
    report["mom_equity"] = mom_equity
    return report


def run_holdout(root, runs, log, log_path=None):
    """The passer on 2025-01-01 through the last NIFTY 50 session, plus the same calibration."""
    emit = log or (lambda line: None)
    nifty_path = data.bar_path(root, "day", lab.NIFTY)
    _first, last = raw_span(nifty_path)
    emit("holdout %s to %s" % (HOLDOUT_START.isoformat(), last.isoformat()))
    report = run_window(root, HOLDOUT_START, last, True, runs, emit, log_path=log_path)
    ctx = report["ctx"]
    _index, spec = spec_named(PASSER_NAME)
    emit("scoring %s" % PASSER_NAME)
    equity = portfolio_equity(ctx, spec, None)
    block = h.path_stats(ctx["calendar"], equity, h.CAPITAL, ctx["nifty"], ctx["regimes"])
    block["dates"] = list(ctx["calendar"])
    nifty_stats = _benchmark(ctx["calendar"], ctx["nifty"], h.CAPITAL)
    momentum = load_index(root, MOMENTUM_INDEX, last, final=True, log_path=log_path)
    shared = overlap_dates(ctx["calendar"], momentum)
    shared_equity = values_on(ctx["calendar"], equity, shared)
    mom_map = {}
    for day in shared:
        mom_map[day] = momentum[day]
    # The book still starts at h.CAPITAL on the first holdout open. When the
    # index is present that day, the excess uses the same anchor.
    anchor = h.CAPITAL if shared and shared[0] == ctx["calendar"][0] else shared_equity[0]
    mom_block = h.path_stats(shared, shared_equity, anchor, mom_map, {})
    mom_index = _benchmark(shared, mom_map, anchor)
    mom_stats = {
        "dates": shared,
        "cagr": mom_index["cagr"],
        "max_dd": mom_index["max_dd"],
        "excess": mom_block["excess"],
    }
    return {
        "block": block,
        "nifty": nifty_stats,
        "momentum": mom_stats,
        "calibration": report,
        "last": last,
    }


def main(argv=None, log=None):
    import argparse
    parser = argparse.ArgumentParser(description="Survivorship calibration. Nothing is placed.")
    parser.add_argument("--root", default=os.path.join("data", "kite"))
    parser.add_argument("--experiments", default=EXPERIMENTS)
    parser.add_argument("--runs", type=int, default=RUNS)
    parser.add_argument("--holdout", action="store_true",
                        help="Read 2025 on with final=True and record the passer. Once.")
    parser.add_argument("--list-indices", action="store_true",
                        help="Print factor-index files and their first dates, then stop.")
    args = parser.parse_args(argv)
    emit = log or (lambda line: print(line, flush=True))
    for line in index_file_lines(args.root):
        emit(line)
    if args.list_indices:
        return 0
    if args.holdout:
        result = run_holdout(args.root, args.runs, emit)
        text = format_holdout(result["block"], result["nifty"], result["momentum"], result["calibration"])
        install(args.experiments, text)
        emit(text)
        return 0
    report = run_window(args.root, START, END, False, args.runs, emit)
    text = format_calibration(report)
    install(args.experiments, text)
    emit(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
