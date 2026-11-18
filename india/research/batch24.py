"""Attempt 24. Long-term index portfolios, lump sum and monthly SIP.

The research window is 2005-04-01 through 2024-12-31. A series that starts
later is scored from its first date, and the row says so. final stays false
on this window. A portfolio that passes gets one holdout look, 2025-01-01
through the last shared date, logged once.

Nothing here places an order. The index download is not run from here.
"""

import csv
import datetime
import gzip
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from india.research import batch18
from india.research import batch22
from india.research import data
from india.research import follow
from india.research import longterm

START = datetime.date(2005, 4, 1)
END = datetime.date(2024, 12, 31)
EXPERIMENTS = batch22.EXPERIMENTS
STRATEGIES = batch22.STRATEGIES
INDEX_ROOT = os.path.join(_ROOT, "data", "nse", "indices")
LAUNCH_PATH = os.path.join(INDEX_ROOT, "launch.csv")
CAPITAL = 1000000.0
SIP = 10000.0
BENCH = "NIFTY_200_TR"
PRICE = "NIFTY_200"

# slug, label, debt, factor
SINGLES = (
    ("NIFTY_200_TR", "NIFTY 200", False, False),
    ("NIFTY200_MOMENTUM_30_TR", "Momentum 30", False, True),
    ("NIFTY100_LOW_VOLATILITY_30_TR", "LowVol 30", False, True),
    ("NIFTY200_QUALITY_30_TR", "Quality 30", False, True),
    ("NIFTY50_VALUE_20_TR", "Value 20", False, True),
    ("NIFTY_ALPHA_50_TR", "Alpha 50", False, True),
    ("NIFTY_MIDCAP_150_TR", "Midcap 150", False, False),
    ("NIFTY_SMALLCAP_250_TR", "Smallcap 250", False, False),
    ("NIFTY_MIDCAP150_MOMENTUM_50_TR", "Midcap150 Momentum 50", False, True),
    ("NIFTY_10YR_BENCHMARK_GSEC", "G-Sec 10y", True, False),
    # GOLDBEES, already net of the ETF's charges, so the expense is 0.
    ("GOLD_ETF", "Gold", True, False),
)
MIXES = (
    ("Momentum+LowVol", (
        ("NIFTY200_MOMENTUM_30_TR", 0.5),
        ("NIFTY100_LOW_VOLATILITY_30_TR", 0.5),
    )),
    ("Momentum+Quality", (
        ("NIFTY200_MOMENTUM_30_TR", 0.5),
        ("NIFTY200_QUALITY_30_TR", 0.5),
    )),
    ("Momentum+LowVol+Quality", (
        ("NIFTY200_MOMENTUM_30_TR", 1.0 / 3.0),
        ("NIFTY100_LOW_VOLATILITY_30_TR", 1.0 / 3.0),
        ("NIFTY200_QUALITY_30_TR", 1.0 / 3.0),
    )),
    ("Alpha50+LowVol", (
        ("NIFTY_ALPHA_50_TR", 0.5),
        ("NIFTY100_LOW_VOLATILITY_30_TR", 0.5),
    )),
)
ALLOCATIONS = (
    ("70/20/10", 0.70, 0.20, 0.10),
    ("60/25/15", 0.60, 0.25, 0.15),
)
DOWNLOAD = "caffeinate -i python3 india/nse_archive.py --only indices"


def rules_text(stamp):
    return "\n".join([
        "## Attempt 24",
        "",
        "Rules fixed on %s, before the run." % stamp,
        "",
        "Window: 2005-04-01 through 2024-12-31. final stays false on this window. "
        "A portfolio whose series starts after 2005-04-01 is scored from that first "
        "date, and the row says so. Prices are the total-return files in "
        "data/nse/indices. The NIFTY 10 yr Benchmark G-Sec file is the total-return "
        "index (the index itself reinvests coupons). Gold is not an NSE index. "
        "Nifty Indices does not publish a bullion series, so gold is the IBJA 999 "
        "fine-gold rate, INR per 10 grams, in GOLD_INR.csv.gz. That file is not "
        "part of the index download. A sleeve used on a session before its launch "
        "date in data/nse/indices/launch.csv is marked (back-test years included). "
        "A blank launch date is not treated as a back-test.",
        "",
        "Costs. Each sleeve pays an expense ratio, taken out of the index level "
        "between sessions. Broad indexes, the G-Sec index and gold pay 0.3% a year. "
        "Factor indexes (momentum, low volatility, quality, value, alpha, and "
        "Midcap150 Momentum 50) pay 0.5% a year. There is no delivery brokerage.",
        "",
        "Tax. Equity held for more than 12 months is LTCG: 10% above Rs 1,00,000 "
        "on a sale before 2024-07-23, and 12.5% above Rs 1,25,000 on or after that "
        "date. Equity held for 12 months or less is STCG, 15% before that date and "
        "20% on or after it. G-Sec and gold are taxed at 30% on the year's net gain, "
        "with no exemption. A loss offsets gains of the same kind in that year. "
        "The book is sold on the last session so the CAGR is after that tax. "
        "Drawdown, the worst calendar year, the recovery and the rolling CAGRs use "
        "the growth of the book before that final sale.",
        "",
        "Rebalance is the first session of April, back to the target weights. "
        "The engine can skip that rebalance unless a weight is more than 5 points "
        "away from its target. Five points exactly does not trade. Attempt 24 leaves "
        "the bands off, so every April is a full rebalance. The first purchase is "
        "not a band check.",
        "",
        "24a, each single index, buy and hold. The lump sum is Rs 10,00,000.",
        "",
        "24b, equal mixes: Momentum+LowVol, Momentum+Quality, Momentum+LowVol+Quality, "
        "Alpha50+LowVol. Same lump sum, April rebalance.",
        "",
        "24c, 70/20/10 and 60/25/15 equity, G-Sec and gold. Equity is (i) NIFTY 200 "
        "and (ii) the 24b mix with the highest after-tax CAGR. Same lump sum, April "
        "rebalance. When the signal in 24e is off, the equity weight is cash and the "
        "G-Sec and gold weights stay put.",
        "",
        "24d, every 24a, 24b and 24c portfolio as a Rs 10,000 contribution on the "
        "first session of each month. The growth rate is the XIRR of those "
        "contributions and the after-tax ending value. There is no lump sum.",
        "",
        "24e, the 10-month NIFTY 200 price rule on the equity part of the best 24c "
        "portfolio, after tax. The signal is the same as attempt 22: the previous "
        "month-end close against the average of that close and the nine before it. "
        "Below the average, equity is cash until the signal turns back on. At or "
        "above it, equity is invested. The first ten month-ends have no signal, and "
        "those months stay invested. A tie stays invested. G-Sec and gold are not "
        "sold by the signal.",
        "",
        "Pass mark, versus NIFTY 200 TRI run the same way (buy and hold against buy "
        "and hold, SIP against SIP), after the 0.3% expense and the same tax, over "
        "the portfolio's own dates. CAGR (XIRR for a SIP) at least 2 points higher, "
        "OR the same CAGR within 1 point with max drawdown at least 15 points "
        "smaller. It must also have a higher minimum rolling 10-year CAGR. A "
        "boundary stated with at least, or with within, still passes. Higher does not. "
        "A portfolio with no complete 10-year window fails the rolling clause.",
        "",
        "Holdout. Each portfolio that passes in sample gets one look, 2025-01-01 "
        "through the last shared date, final=True, logged once. The CAGR and "
        "drawdown clauses are applied on that window. The rolling 10-year clause "
        "stays in sample, because the holdout window is shorter than 10 years.",
        "",
        "A sleeve whose file is not on disk is not scored. That row is not a FAIL "
        "and it is not catalogued.",
    ])


def load_launches(path):
    table = {}
    with open(path, encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            text = (row.get("launch") or "").strip()
            launch = datetime.date.fromisoformat(text) if text else None
            table[row["slug"].strip()] = launch
    return table


def launch_of(table, slug):
    if slug in table:
        return table[slug]
    if slug.endswith("_TR"):
        return table.get(slug[:-3])
    return None


def read_series(path):
    rows = []
    with gzip.open(path, "rt", encoding="utf-8", newline="") as fh:
        for cell in csv.DictReader(fh):
            close = float(cell["close"])
            if close <= 0:
                continue
            rows.append((datetime.date.fromisoformat(cell["date"]), close))
    rows.sort()
    return rows


def _kind_map(weights, debt):
    kinds = {}
    for name in weights:
        kinds[name] = "debt" if name in debt else "equity"
    return kinds


def _expenses(weights, factors):
    out = {}
    for name in weights:
        # The ETF price is already net of its charges.
        if name == "GOLD_ETF":
            out[name] = 0.0
        else:
            out[name] = longterm.expense_for(name in factors)
    return out


def _launches(weights, table):
    out = {}
    for name in weights:
        out[name] = launch_of(table, name)
    return out


def _pct(value):
    if value is None:
        return "n/a"
    return "%+.2f%%" % (value * 100.0)


def _num(value):
    if value is None:
        return "n/a"
    return "%.2f" % value


def _roll(triple):
    if triple is None or triple[0] is None:
        return "n/a"
    return "%s / %s / %s" % (_pct(triple[0]), _pct(triple[1]), _pct(triple[2]))


def _worst(item):
    if not item:
        return "n/a"
    year, ret = item
    return "%d %s" % (year, _pct(ret))


def _recovery(row):
    if row["recovered"] and row["recovery_years"] == 0:
        return "none"
    if not row["recovered"] or row["recovery_years"] is None:
        return "not recovered"
    return "%.2f years" % row["recovery_years"]


def _line(block):
    row = block["row"]
    if row is None:
        return "%s | NOT SCORED | %s" % (block["name"], "; ".join(block["reasons"]))
    name = longterm.annotate(block["name"], row["backtest"])
    if row["start"] != START:
        name = "%s | starts %s" % (name, row["start"].isoformat())
    rate = "XIRR" if block["sip"] else "CAGR"
    return " ".join([
        name,
        "|",
        "%s %s" % (rate, _pct(row["cagr"])),
        "|",
        "excess %s" % _pct(block["excess"]),
        "|",
        "DD %s" % _pct(row["dd"]),
        "|",
        "bench DD %s" % _pct(block["bench_dd"]),
        "|",
        "worst %s" % _worst(row["worst_year"]),
        "|",
        "recover %s" % _recovery(row),
        "|",
        "5y %s" % _roll(row["roll5"]),
        "|",
        "10y %s" % _roll(row["roll10"]),
        "|",
        block["result"],
    ])


def _summary_row(stamp, block):
    row = block["row"]
    trades = 0 if row is None else row["trades"]
    excess = block["excess"]
    roll = None if row is None or row["roll10"][0] is None else row["roll10"][0]
    window = "%s to %s" % (START.isoformat(), END.isoformat())
    if row is not None:
        window = "%s to %s" % (row["start"].isoformat(), row["end"].isoformat())
    result = block["result"]
    if block.get("holdout_result"):
        result = "%s Holdout %s" % (block["result"], block["holdout_result"])
    return "| 24 | %s | %s. | attempt 24, rules fixed before the run | %s | %d | %s | %s | %s |" % (
        stamp, block["name"], window, trades, _pct(excess), _pct(roll), result)


def _overlay_fn(price_points):
    risk = batch22.risk_on_map(price_points)
    return batch22._overlay_from(risk)


def _run_one(loaded, weights, debt, factors, table, start, end, sip, overlay):
    missing = [name for name in weights if name not in loaded]
    if missing:
        return None, ["series not on disk: %s" % ", ".join(missing)]
    series = {}
    for name in weights:
        series[name] = loaded[name]
    row = longterm.simulate(
        series, weights, _kind_map(weights, debt), start, end,
        capital=CAPITAL, expenses=_expenses(weights, factors),
        bands=False, sip=sip, overlay=overlay, launches=_launches(weights, table),
    )
    if row is None:
        return None, ["no shared dates"]
    return row, []


def _judge(row, bench, insample):
    if not insample:
        reasons = []
        if row["cagr"] is None or bench["cagr"] is None:
            reasons.append("CAGR is missing")
        else:
            gap = row["cagr"] - bench["cagr"]
            dd_gap = bench["dd"] - row["dd"]
            cagr_ok = gap >= 0.02 - 1e-12
            same = abs(gap) <= 0.01 + 1e-12 and dd_gap >= 0.15 - 1e-12
            if not cagr_ok and not same:
                reasons.append("holdout CAGR is not 2 points higher, and the drawdown clause is not met")
        return not reasons, reasons
    return longterm.passes(row, bench)


def _block(name, group, sip, row, reasons, bench):
    if row is None:
        return {
            "name": name,
            "group": group,
            "sip": sip,
            "row": None,
            "reasons": reasons,
            "excess": None,
            "bench_dd": None,
            "result": "NOT SCORED",
            "passed": False,
            "weights": None,
        }
    excess = None
    if row["cagr"] is not None and bench is not None and bench["cagr"] is not None:
        excess = row["cagr"] - bench["cagr"]
    passed, why = _judge(row, bench, True)
    return {
        "name": name,
        "group": group,
        "sip": sip,
        "row": row,
        "reasons": why,
        "excess": excess,
        "bench_dd": None if bench is None else bench["dd"],
        "result": "PASS" if passed else "FAIL",
        "passed": passed,
        "weights": None,
    }


def _best(blocks):
    found = None
    for block in blocks:
        if block["row"] is None or block["row"]["cagr"] is None:
            continue
        if found is None or block["row"]["cagr"] > found["row"]["cagr"]:
            found = block
    return found


def _scale(weights, share):
    out = {}
    for name, weight in weights.items():
        out[name] = weight * share
    return out


def _report(stamp, blocks, notes):
    lines = [rules_text(stamp).rstrip(), "", "Results.", ""]
    lines.append(
        "name | CAGR or XIRR after tax | excess vs NIFTY 200 TRI | max DD | "
        "NIFTY 200 DD | worst year | years to recover | rolling 5-year min/med/max | "
        "rolling 10-year min/med/max | result"
    )
    for block in blocks:
        lines.append(_line(block))
        for reason in block["reasons"]:
            lines.append("  " + reason)
    held = [block for block in blocks if block.get("holdout_line")]
    if held:
        lines.append("")
        lines.append("Holdout, 2025-01-01 through the last shared date. The rolling 10-year clause stays in sample.")
        for block in held:
            lines.append(block["holdout_line"])
            for reason in block.get("holdout_reasons") or []:
                lines.append("  " + reason)
    lines.append("")
    for note in notes:
        lines.append(note)
    lines.append("")
    return "\n".join(lines)


def _catalogue(blocks):
    text = open(STRATEGIES, encoding="utf-8").read()
    for block in blocks:
        if block["result"] == "NOT SCORED":
            continue
        if block["result"] == "PASS" and block.get("holdout_result") == "PASS":
            tier = "Bucket"
            note = "PASS Holdout PASS"
        elif block["result"] == "PASS":
            tier = "Closed"
            hold = block.get("holdout_result") or "not run"
            note = "PASS in-sample, Holdout %s" % hold
        else:
            tier = "Closed"
            note = "FAIL"
        row = "| %s | 24 | %s |" % (block["name"], note)
        text = batch18.add_tier_row(text, tier, row)
    with open(STRATEGIES, "w", encoding="utf-8") as fh:
        fh.write(text)


def _saved_holdouts(text):
    """Holdout lines already written, keyed by the portfolio name."""
    found = {}
    lines = text.splitlines()
    index = 0
    while index < len(lines):
        line = lines[index]
        if line.startswith("holdout "):
            head = line.split("|", 1)[0]
            name = head[len("holdout "):].strip()
            tail = line.strip().split("|")[-1].strip()
            result = tail if tail in ("PASS", "FAIL", "NOT SCORED") else "FAIL"
            reasons = []
            nxt = index + 1
            while nxt < len(lines) and lines[nxt].startswith("  "):
                reasons.append(lines[nxt].strip())
                nxt += 1
            found[name] = {"line": line, "reasons": reasons, "result": result}
            index = nxt
            continue
        index += 1
    return found


def _summary_name(line):
    parts = line.split("|")
    if len(parts) < 4:
        return ""
    return parts[3].strip().rstrip(".")


def main(argv=None, rules_stamp=None, reuse_holdouts=False):
    del argv
    stamp = datetime.date.today().isoformat()
    rules_day = rules_stamp or stamp
    log = lambda line: print(line, flush=True)
    saved = {}
    old_summary = []
    if reuse_holdouts:
        existing = open(EXPERIMENTS, encoding="utf-8").read()
        start = existing.find("\n## Attempt 24\n")
        end = existing.find("\n## ", start + 1) if start != -1 else -1
        section = existing[start:end] if start != -1 else ""
        saved = _saved_holdouts(section)
        old_summary = [line for line in existing.splitlines() if line.startswith("| 24 |")]
        log("attempt 24 rules already in the file, not rewritten")
        log("holdouts already logged %d" % len(saved))
    else:
        follow.install_attempt(EXPERIMENTS, 24, rules_text(rules_day), [])
        log("rules for attempt 24 written to %s before the run" % EXPERIMENTS)
    table = load_launches(LAUNCH_PATH)
    loaded = {}
    for name in os.listdir(INDEX_ROOT):
        if not name.endswith(".csv.gz"):
            continue
        slug = name[:-7]
        loaded[slug] = read_series(os.path.join(INDEX_ROOT, name))
        log("loaded %s %d rows %s .. %s" % (
            slug, len(loaded[slug]),
            loaded[slug][0][0].isoformat(), loaded[slug][-1][0].isoformat()))
    debt = set(slug for slug, _label, is_debt, _factor in SINGLES if is_debt)
    factors = set(slug for slug, _label, _debt, is_factor in SINGLES if is_factor)
    notes = []
    missing = []
    for slug, _label, _debt, _factor in SINGLES:
        if slug not in loaded:
            missing.append(slug)
    if missing:
        notes.append("Not on disk: %s." % ", ".join(missing))
        index_missing = [slug for slug in missing if slug != "GOLD_ETF"]
        if index_missing:
            notes.append("Index download, run from Terminal, not from Cursor: %s" % DOWNLOAD)
            log(notes[-1])
        if "GOLD_ETF" in missing:
            notes.append(
                "Gold is GOLDBEES series EQ from data/nse/cm, adjusted only for its "
                "unit split, written to data/nse/indices/GOLD_ETF.csv.gz. No expense "
                "ratio. python3 india/research/goldetf.py"
            )
            log(notes[-1])
    if "GOLD_ETF" in loaded and loaded["GOLD_ETF"]:
        from india.research import invest
        g0 = loaded["GOLD_ETF"][0]
        g1 = loaded["GOLD_ETF"][-1]
        gcagr = invest._cagr(g0[1], g1[1], g0[0], g1[0])
        notes.append(
            "Gold is GOLD_ETF, GOLDBEES series EQ, adjusted only for the unit split, "
            "with no expense ratio because the ETF price is already net of its charges. "
            "The rules above still name the IBJA rate at 0.3 percent. This scoring uses "
            "GOLD_ETF instead. First date %s, close CAGR %s through %s. "
            "The 24c books start later, on the first date every sleeve shares. "
            "That date is the first G-Sec session, which is printed on the row. "
            "Gold itself is held from its own first date inside that window."
            % (g0[0].isoformat(), _pct(gcagr), g1[0].isoformat())
        )
        log(notes[-1])
    if launch_of(table, "NIFTY50_VALUE_20_TR") is None and "NIFTY50_VALUE_20_TR" in loaded:
        notes.append(
            "NIFTY50 Value 20 has a blank launch date. A blank launch is unknown, "
            "and unknown is not live, so the row is marked (back-test years included)."
        )

    blocks = []
    # 24a
    for slug, label, _debt, _factor in SINGLES:
        weights = {slug: 1.0}
        row, why = _run_one(loaded, weights, debt, factors, table, START, END, None, None)
        bench = None
        if row is not None and slug != BENCH:
            bench, _bw = _run_one(
                loaded, {BENCH: 1.0}, debt, factors, table, row["start"], row["end"], None, None)
        elif row is not None:
            bench = row
        block = _block("24a %s" % label, "a", False, row, why, bench)
        block["weights"] = weights
        blocks.append(block)
        log(_line(block))

    # 24b
    mix_blocks = []
    for label, pairs in MIXES:
        weights = {}
        for slug, weight in pairs:
            weights[slug] = weight
        row, why = _run_one(loaded, weights, debt, factors, table, START, END, None, None)
        bench = None
        if row is not None:
            bench, _bw = _run_one(
                loaded, {BENCH: 1.0}, debt, factors, table, row["start"], row["end"], None, None)
        block = _block("24b %s" % label, "b", False, row, why, bench)
        block["weights"] = weights
        blocks.append(block)
        mix_blocks.append(block)
        log(_line(block))

    best_mix = _best(mix_blocks)
    if best_mix is None:
        notes.append("No 24b mix could be scored, so 24c uses only NIFTY 200 as equity.")
    else:
        notes.append("Best 24b mix by after-tax CAGR: %s at %s." % (
            best_mix["name"], _pct(best_mix["row"]["cagr"])))
        log(notes[-1])

    # 24c
    equity_books = [(("NIFTY_200_TR",), {BENCH: 1.0}, "NIFTY 200")]
    if best_mix is not None and best_mix["weights"]:
        equity_books.append((tuple(best_mix["weights"]), best_mix["weights"], best_mix["name"]))
    c_blocks = []
    for _keys, equity_weights, equity_label in equity_books:
        for alloc, eq, gs, gd in ALLOCATIONS:
            weights = _scale(equity_weights, eq)
            weights["NIFTY_10YR_BENCHMARK_GSEC"] = gs
            weights["GOLD_ETF"] = gd
            row, why = _run_one(loaded, weights, debt, factors, table, START, END, None, None)
            bench = None
            if row is not None:
                bench, _bw = _run_one(
                    loaded, {BENCH: 1.0}, debt, factors, table, row["start"], row["end"], None, None)
            name = "24c %s %s" % (alloc, equity_label)
            block = _block(name, "c", False, row, why, bench)
            block["weights"] = weights
            blocks.append(block)
            c_blocks.append(block)
            log(_line(block))

    # 24d SIP of every scored 24a-24c specification, including the ones that were missing
    sip_sources = [block for block in blocks if block["group"] in ("a", "b", "c")]
    for source in sip_sources:
        if not source["weights"]:
            continue
        row, why = _run_one(
            loaded, source["weights"], debt, factors, table, START, END, SIP, None)
        bench = None
        if row is not None:
            bench, _bw = _run_one(
                loaded, {BENCH: 1.0}, debt, factors, table, row["start"], row["end"], SIP, None)
        name = source["name"].replace("24a ", "24d ").replace("24b ", "24d ").replace("24c ", "24d ")
        # 24a/b/c names already carry the prefix. A SIP of 24a is "24d ...".
        if name.startswith("24d "):
            pass
        block = _block("24d " + source["name"].split(" ", 1)[1], "d", True, row, why, bench)
        block["weights"] = source["weights"]
        blocks.append(block)
        log(_line(block))

    best_c = _best(c_blocks)
    if best_c is None:
        notes.append("No 24c portfolio could be scored, so 24e was not run.")
        log(notes[-1])
    elif PRICE not in loaded:
        notes.append("NIFTY 200 price is not on disk, so 24e was not run.")
        log(notes[-1])
    else:
        notes.append("Best 24c portfolio by after-tax CAGR: %s at %s." % (
            best_c["name"], _pct(best_c["row"]["cagr"])))
        overlay = _overlay_fn(loaded[PRICE])
        row, why = _run_one(
            loaded, best_c["weights"], debt, factors, table, START, END, None, overlay)
        bench = None
        if row is not None:
            bench, _bw = _run_one(
                loaded, {BENCH: 1.0}, debt, factors, table, row["start"], row["end"], None, None)
        block = _block("24e " + best_c["name"].split(" ", 1)[1], "e", False, row, why, bench)
        block["weights"] = best_c["weights"]
        blocks.append(block)
        log(_line(block))

    if reuse_holdouts:
        guard = [block for block in blocks if block["name"] == "24a NIFTY 200"]
        if guard and "+13.69%" not in _line(guard[0]):
            log("NIFTY 200 in-sample CAGR moved, attempt 24 was not rewritten")
            return 1

    # Holdout, one look each, only after an in-sample pass.
    # A portfolio that already has a logged look is not opened again.
    passing = [block for block in blocks if block["passed"]]
    fresh = []
    for block in passing:
        prior = saved.get(block["name"]) if reuse_holdouts else None
        if prior:
            block["holdout_result"] = prior["result"]
            block["holdout_line"] = prior["line"]
            block["holdout_reasons"] = prior["reasons"]
            log("holdout reused %s" % block["name"])
        else:
            fresh.append(block)
    if not passing:
        notes.append("No attempt 24 portfolio passed in sample. The holdout was not opened.")
        log(notes[-1])
    elif not fresh:
        notes.append("No new attempt 24 portfolio passed. The earlier holdout looks were kept.")
        log(notes[-1])
    else:
        hold_end = data.HOLDOUT_START
        for slug in loaded:
            if loaded[slug] and loaded[slug][-1][0] > hold_end:
                hold_end = loaded[slug][-1][0]
        data._guard("attempt24", [hold_end], True, None)
        log("new holdout looks %d" % len(fresh))
        for block in fresh:
            book_end = hold_end
            for name in block["weights"]:
                if loaded.get(name):
                    book_end = min(book_end, loaded[name][-1][0])
            if loaded.get(BENCH):
                book_end = min(book_end, loaded[BENCH][-1][0])
            overlay = None
            if block["group"] == "e":
                overlay = _overlay_fn(loaded[PRICE])
            sip = SIP if block["sip"] else None
            row, why = _run_one(
                loaded, block["weights"], debt, factors, table,
                data.HOLDOUT_START, book_end, sip, overlay)
            bench = None
            if row is not None:
                bench, _bw = _run_one(
                    loaded, {BENCH: 1.0}, debt, factors, table,
                    row["start"], row["end"], sip, None)
            if row is None or bench is None:
                block["holdout_result"] = "NOT SCORED"
                block["holdout_line"] = "holdout %s | NOT SCORED" % block["name"]
            else:
                ok, reasons = _judge(row, bench, False)
                block["holdout_result"] = "PASS" if ok else "FAIL"
                excess = None
                if row["cagr"] is not None and bench["cagr"] is not None:
                    excess = row["cagr"] - bench["cagr"]
                rate = "XIRR" if block["sip"] else "CAGR"
                block["holdout_line"] = "holdout %s | %s to %s | %s %s | excess %s | DD %s | bench DD %s | %s" % (
                    block["name"], row["start"].isoformat(), row["end"].isoformat(),
                    rate, _pct(row["cagr"]), _pct(excess), _pct(row["dd"]), _pct(bench["dd"]),
                    block["holdout_result"])
                block["holdout_reasons"] = reasons
            log(block["holdout_line"])

    if reuse_holdouts:
        known = set(_summary_name(line) for line in old_summary)
        rows = list(old_summary)
        for block in blocks:
            if block["result"] == "NOT SCORED" or block["name"] in known:
                continue
            rows.append(_summary_row(stamp, block))
    else:
        rows = [_summary_row(stamp, block) for block in blocks if block["result"] != "NOT SCORED"]
    follow.install_attempt(EXPERIMENTS, 24, _report(rules_day, blocks, notes), rows)
    _catalogue(blocks)
    log("attempt 24 written")
    return 0


def finish():
    """Score the rows that were waiting on the index files. Do not rewrite the rules date.

    Portfolios that already have a holdout line keep that line. A new in-sample
    pass gets one look, logged once for the whole batch.
    """
    return main(rules_stamp="2026-11-17", reuse_holdouts=True)


if __name__ == "__main__":
    sys.exit(main())
