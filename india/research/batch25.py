"""Attempt 25. Live record of each index from the session after its launch.

The book starts on the first session after the official launch date. The
launch day itself is not included. final stays false. This history was not
used to design the rule, so there is no holdout look.

Nothing here places an order.
"""

import csv
import datetime
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from india.research import batch18
from india.research import batch22
from india.research import batch24
from india.research import longterm

END = datetime.date(2024, 12, 31)
CAPITAL = 1000000.0
EXPERIMENTS = batch22.EXPERIMENTS
STRATEGIES = batch22.STRATEGIES
MIN_YEARS = 5
# Above 1 point is strict. No more than 5 points deeper includes 5 points.
EXCESS_BAR = 0.01
DEEPER_BAR = 0.05

LABELS = {
    "NIFTY_50": "NIFTY 50",
    "NIFTY_200": "NIFTY 200",
    "NIFTY200_MOMENTUM_30": "Momentum 30",
    "NIFTY100_LOW_VOLATILITY_30": "LowVol 30",
    "NIFTY_ALPHA_50": "Alpha 50",
    "NIFTY200_QUALITY_30": "Quality 30",
    "NIFTY_MIDCAP_150": "Midcap 150",
    "NIFTY_SMALLCAP_250": "Smallcap 250",
    "NIFTY_MIDCAP150_MOMENTUM_50": "Midcap150 Momentum 50",
}
FACTORS = (
    "NIFTY200_MOMENTUM_30",
    "NIFTY100_LOW_VOLATILITY_30",
    "NIFTY_ALPHA_50",
    "NIFTY200_QUALITY_30",
    "NIFTY50_VALUE_20",
    "NIFTY_MIDCAP150_MOMENTUM_50",
)


def rules_text(stamp):
    return "\n".join([
        "## Attempt 25",
        "",
        "Rules fixed on %s, before the run." % stamp,
        "",
        "Each index with an official launch date in data/nse/indices/launch.csv "
        "is bought on the first session after that date and held to the end of "
        "the window. The launch day itself is not in the book. A blank launch "
        "date is skipped. The G-Sec row records a base date, not a launch date, "
        "and it is skipped. The series is the total-return file when that file "
        "is on disk, otherwise the price file. The book is a Rs 10,00,000 buy "
        "and hold, after the attempt 24 expense (0.3% a year for a broad index, "
        "0.5% for a factor index) and the same equity tax. It is compared with "
        "NIFTY 200 TRI over the same dates, with the same expense and the same tax.",
        "",
        "Two windows. (i) through 2024-12-31. (ii) through the last date in the "
        "file. Each window reports the excess CAGR, the max drawdown, the worst "
        "calendar year, and the number of live years from the book's first session "
        "to that window's end.",
        "",
        "Pass rule, on window (ii) only. Excess CAGR above 1 point, and max "
        "drawdown no more than 5 points deeper than NIFTY 200 over those same "
        "dates. Above is strict: 1 point exactly does not pass. No more than "
        "includes 5 points exactly. An index with under 5 live years, measured "
        "to the last date, is reported as too short and gets no verdict. Under "
        "is strict: 5 years exactly is scored.",
        "",
        "This uses NSE's live index history. The rule was not designed on that "
        "history, so there is no holdout look. A file that starts years after "
        "the launch date is scored from its first session, and the row says so. "
        "Drawdown and the worst calendar year use the growth of the book before "
        "the final sale, the same path as attempt 24. The CAGR is after that sale "
        "and its tax.",
    ])


def first_session_after(points, launch):
    """First session strictly after the launch date. The launch day is excluded."""
    if launch is None:
        return None
    for item in points:
        day = item[0] if isinstance(item, tuple) else item
        if day > launch:
            return day
    return None


def live_years(start, end):
    if start is None or end is None or end < start:
        return None
    return (end - start).days / 365.25


def live_passes(row, bench, years):
    """PASS, FAIL, or too short. too short has no verdict and no reasons."""
    if years is None or years < MIN_YEARS:
        return "too short", []
    reasons = []
    if row is None or bench is None or row["cagr"] is None or bench["cagr"] is None:
        reasons.append("CAGR is missing")
    else:
        gap = row["cagr"] - bench["cagr"]
        # 1e-12 keeps float dust on an exact 1-point gap from counting as above.
        if not gap > EXCESS_BAR + 1e-12:
            reasons.append("excess CAGR is not above 1 point")
    if row is None or bench is None or row["dd"] is None or bench["dd"] is None:
        reasons.append("drawdown is missing")
    elif row["dd"] > bench["dd"] + DEEPER_BAR + 1e-9:
        reasons.append("max drawdown is more than 5 points deeper")
    if reasons:
        return "FAIL", reasons
    return "PASS", []


def official_rows(path):
    """Slugs whose launch cell is an official launch, not a blank or a base date."""
    found = []
    with open(path, encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            text = (row.get("launch") or "").strip()
            note = row.get("note") or ""
            if not text:
                continue
            if "Launch Date" not in note:
                continue
            found.append((row["slug"].strip(), datetime.date.fromisoformat(text)))
    return found


def _series_slug(loaded, slug):
    tri = slug + "_TR"
    if tri in loaded:
        return tri
    if slug in loaded:
        return slug
    return None


def _pct(value):
    if value is None:
        return "n/a"
    return "%+.2f%%" % (value * 100.0)


def _worst(item):
    if not item:
        return "n/a"
    year, ret = item
    return "%d %s" % (year, _pct(ret))


def _run(loaded, slug, factor, table, start, end):
    weights = {slug: 1.0}
    kinds = {slug: "equity"}
    expenses = {slug: longterm.expense_for(factor)}
    launches = {slug: batch24.launch_of(table, slug)}
    return longterm.simulate(
        {slug: loaded[slug]}, weights, kinds, start, end,
        capital=CAPITAL, expenses=expenses, bands=False, launches=launches,
    )


def _window_line(label, tag, row, bench, years):
    excess = None
    if row is not None and bench is not None and row["cagr"] is not None and bench["cagr"] is not None:
        excess = row["cagr"] - bench["cagr"]
    if row is None:
        return "%s %s | not scored" % (label, tag)
    lived = "n/a" if years is None else "%.2f" % years
    return "%s %s | %s to %s | CAGR %s | excess %s | DD %s | bench DD %s | worst %s | live years %s" % (
        label, tag,
        row["start"].isoformat(), row["end"].isoformat(),
        _pct(row["cagr"]), _pct(excess), _pct(row["dd"]),
        _pct(None if bench is None else bench["dd"]),
        _worst(row["worst_year"]),
        lived,
    )


def _summary_row(stamp, block):
    row = block["full"]
    start = row["start"].isoformat() if row is not None else ""
    end = row["end"].isoformat() if row is not None else ""
    return "| 25 | %s | %s. | attempt 25, rules fixed before the run | %s to %s | 1 | %s | %s | %s |" % (
        stamp, block["name"], start, end, _pct(block["excess"]), _pct(block["dd"]), block["result"])


def _catalogue(blocks):
    text = open(STRATEGIES, encoding="utf-8").read()
    for block in blocks:
        if block["result"] == "too short":
            continue
        if block["result"] == "PASS":
            tier = "Investing"
            note = "live record PASS. No holdout, by the attempt 25 rule."
        else:
            tier = "Closed"
            note = "FAIL"
        row = "| %s | 25 | %s |" % (block["name"], note)
        text = batch18.add_tier_row(text, tier, row)
    with open(STRATEGIES, "w", encoding="utf-8") as fh:
        fh.write(text)


def _report(stamp, blocks, notes):
    lines = [rules_text(stamp).rstrip(), "", "Results.", ""]
    lines.append(
        "name | window | dates | CAGR after tax | excess vs NIFTY 200 TRI | "
        "max DD | NIFTY 200 DD | worst year | live years | result"
    )
    for block in blocks:
        lines.append(block["line_i"])
        lines.append(block["line_ii"])
        if block["gap_note"]:
            lines.append("  " + block["gap_note"])
        for reason in block["reasons"]:
            lines.append("  " + reason)
        lines.append("  %s" % block["result"])
    lines.append("")
    for note in notes:
        lines.append(note)
    lines.append("")
    return "\n".join(lines)


def main(argv=None):
    del argv
    stamp = datetime.date.today().isoformat()
    log = lambda line: print(line, flush=True)
    from india.research import follow
    follow.install_attempt(EXPERIMENTS, 25, rules_text(stamp), [])
    log("rules for attempt 25 written to %s before the run" % EXPERIMENTS)
    table = batch24.load_launches(batch24.LAUNCH_PATH)
    loaded = {}
    root = batch24.INDEX_ROOT
    for name in os.listdir(root):
        if not name.endswith(".csv.gz"):
            continue
        slug = name[:-7]
        loaded[slug] = batch24.read_series(os.path.join(root, name))
    bench_slug = "NIFTY_200_TR"
    launches = official_rows(batch24.LAUNCH_PATH)
    blocks = []
    notes = []
    skipped = []
    for slug, launch in launches:
        label = LABELS.get(slug, slug)
        series = _series_slug(loaded, slug)
        name = "25 %s" % label
        if series is None or bench_slug not in loaded:
            skipped.append(label)
            log("%s series not on disk" % name)
            continue
        start = first_session_after(loaded[series], launch)
        if start is None:
            skipped.append(label)
            log("%s has no session after %s" % (name, launch.isoformat()))
            continue
        last = loaded[series][-1][0]
        bench_last = loaded[bench_slug][-1][0]
        end_full = last if last <= bench_last else bench_last
        end_sample = END if END < end_full else end_full
        factor = slug in FACTORS
        row_i = None
        bench_i = None
        years_i = None
        if start <= end_sample:
            row_i = _run(loaded, series, factor, table, start, end_sample)
            if row_i is not None:
                bench_i = _run(loaded, bench_slug, False, table, row_i["start"], row_i["end"])
                years_i = live_years(row_i["start"], row_i["end"])
        row_ii = _run(loaded, series, factor, table, start, end_full)
        bench_ii = None
        years_ii = None
        if row_ii is not None:
            bench_ii = _run(loaded, bench_slug, False, table, row_ii["start"], row_ii["end"])
            years_ii = live_years(row_ii["start"], row_ii["end"])
        result, reasons = live_passes(row_ii, bench_ii, years_ii)
        excess = None
        dd = None
        if row_ii is not None and bench_ii is not None and row_ii["cagr"] is not None and bench_ii["cagr"] is not None:
            excess = row_ii["cagr"] - bench_ii["cagr"]
        if row_ii is not None:
            dd = row_ii["dd"]
        gap_note = ""
        first_on_disk = loaded[series][0][0]
        if first_on_disk > launch and (first_on_disk - launch).days > 7:
            gap_note = "on-disk history starts %s, after the %s launch" % (
                first_on_disk.isoformat(), launch.isoformat())
        bench_launch = batch24.launch_of(table, bench_slug)
        if bench_launch is not None and start < bench_launch:
            extra = "NIFTY 200 comparison includes sessions before its %s launch" % bench_launch.isoformat()
            gap_note = extra if not gap_note else gap_note + ". " + extra
        block = {
            "name": name,
            "line_i": _window_line(name, "(i)", row_i, bench_i, years_i),
            "line_ii": _window_line(name, "(ii)", row_ii, bench_ii, years_ii),
            "gap_note": gap_note,
            "reasons": reasons,
            "result": result,
            "excess": excess,
            "dd": dd,
            "full": row_ii,
        }
        blocks.append(block)
        log(block["line_i"])
        log(block["line_ii"])
        if gap_note:
            log("  " + gap_note)
        log("  %s" % result)
    if skipped:
        notes.append("Not scored: %s." % ", ".join(skipped))
    notes.append("No holdout. The live record was not used to design the rule.")
    notes.append(
        "Window (ii) ends on the last date in the index file. A calendar year "
        "that is still in progress is the return from its first session through that date."
    )
    from india.research import follow
    rows = [_summary_row(stamp, block) for block in blocks if block["full"] is not None]
    follow.install_attempt(EXPERIMENTS, 25, _report(stamp, blocks, notes), rows)
    _catalogue(blocks)
    log("attempt 25 written")
    return 0


if __name__ == "__main__":
    sys.exit(main())
