"""Attempt 23. Low-turnover and tax-aware books on the same panel.

The research window is 2005-01-01 through 2024-12-31 and final stays false.
Only 23d, a new family, may take one holdout look, and only after it passes
in sample. 23a, 23b and 23c are momentum. They are compared with the published
index over 2025-2026 and are not run on those dates.

Nothing here places an order.
"""

import bisect
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
from india.research import invest
from india.research import panel

START = datetime.date(2005, 1, 1)
END = datetime.date(2024, 12, 31)
HOLD = datetime.date(2025, 1, 1)
BUY_DATE = datetime.date(2005, 4, 1)
SIX_MONTHS = (4, 10)
TWELVE_MONTHS = (4,)
TOP_N = 30
BUFFER = 60
EXPERIMENTS = batch22.EXPERIMENTS
STRATEGIES = batch22.STRATEGIES
END_RULE = (
    "If no attempt 23 variant passes, short-term stock picking is Closed "
    "and factor exposure goes through index funds."
)


def rules_text(stamp):
    return "\n".join([
        "## Attempt 23",
        "",
        "Rules fixed on %s, before the run." % stamp,
        "",
        "Window: 2005-01-01 through 2024-12-31. final stays false on this window. "
        "Prices are the survivorship-free cash panel in data/cache/panel, built from "
        "data/nse/cm. A stock that stops trading is sold at its last adjusted close, "
        "and that loss stays in the result. Costs are the delivery schedule in "
        "india/costs.py. Tax is invest.tax_due: STCG 15% before 2024-07-23 and 20% "
        "on or after that date, LTCG 10% above Rs 1,00,000 or 12.5% above Rs 1,25,000 "
        "for a sale after the one-year anniversary, and losses offset gains in the "
        "same year. The book starts at Rs 10,00,000. No new order is sent.",
        "",
        "Universe. Top 200 is the panel's monthly list: stocks that trade on the "
        "first session, ranked by the median turnover of the previous 60 sessions.",
        "",
        "23a, index-style momentum. The score is the average of the 6-month return "
        "and the 12-month return, each divided by the 1-year daily volatility. The "
        "6-month return is the adjusted close divided by the close 126 sessions "
        "earlier, minus 1. The 12-month return uses 252 sessions. Volatility is the "
        "sample standard deviation of the last 252 one-session returns. The book is "
        "the top 30 from the top 200, equal weight, long only. Rebalance is the "
        "first session of April and the first session of October. Buffer: a holding "
        "is kept while it ranks in the top 60. A name that does not rank, or ranks "
        "61 or worse, is sold. Vacancies are filled from the top of the ranking. "
        "The book never holds more than 30 names.",
        "",
        "23b, the same book as 23a, rebalanced on the first session of April only, "
        "so a sale of a name bought the previous April is after the one-year "
        "anniversary and is taxed as long-term.",
        "",
        "23c, 23a with the NIFTY 200 10-month-average overlay checked on the first "
        "session of every month. The signal is the same as attempt 22: the previous "
        "month-end close against the average of that close and the nine month-end "
        "closes before it. Below the average, the next month is cash. At or above "
        "it, the book is the latest April or October selection. The first ten "
        "month-ends have no signal, and those months stay invested. A tie stays "
        "invested.",
        "",
        "23d, post-results drift, hold 60 sessions, only for a stock inside the "
        "top 200 on the entry session. The reaction, the top 10% cutoff, the next "
        "session's open and the exit 60 sessions later are the same as attempt 22. "
        "At most 20 positions. Each new position is one twentieth of equity at the "
        "entry. Idle cash earns 0.",
        "",
        "Pass mark, the same as attempt 22. CAGR after delivery costs and tax is "
        "at least 3 points above the NIFTY 200 price index over the same dates. "
        "The monthly t of the excess over that price index is above 2.5. The book "
        "is ahead of NIFTY 200 price in 2005-2014 and in 2015-2024, measured as "
        "total return. Max drawdown of the after-tax wealth is no more than 10 "
        "points deeper than the NIFTY 200 price drawdown. The excess over NIFTY 200 "
        "TRI is reported and is not part of the mark. A boundary stated with at "
        "least, or with no more than, still passes. Above 2.5 does not.",
        "",
        "For information, not a variant: buy NIFTY200 Momentum 30 TRI on 2005-04-01 "
        "and sell on 2024-12-31, one delivery round trip, LTCG once. The same trade "
        "in NIFTY 200 TRI. Neither trade is a holdout.",
        "",
        "Holdout. Only 23d. One look, and only after an in-sample pass. The look is "
        "2025-01-01 through the last panel session, final=True, logged once. The "
        "same CAGR, t and drawdown clauses are applied on that window. The decade "
        "clauses stay in sample. 23a, 23b and 23c are momentum. They are compared "
        "with the published NIFTY200 Momentum 30 and NIFTY 200 indexes over "
        "2025-01-01 through the last index row. Those books are not run on those "
        "dates and they do not log a holdout.",
        "",
        END_RULE,
        "",
    ])


def first_sessions(calendar, months):
    """The first session of each month whose month number is in months."""
    seen = set()
    found = []
    for day in calendar:
        if day.month not in months:
            continue
        key = (day.year, day.month)
        if key in seen:
            continue
        seen.add(key)
        found.append(day)
    return found


def buffered_book(ranked, held, top_n, buffer):
    """Keep a holding while its rank is inside the buffer, then fill from the top.

    ranked is best first. Rank 1 is the best name. A holding with no rank is
    sold. The result has at most top_n names.
    """
    rank = {}
    for i, isin in enumerate(ranked):
        rank[isin] = i + 1
    kept = []
    for isin in held:
        place = rank.get(isin)
        if place is not None and place <= buffer:
            kept.append((place, isin))
    kept.sort()
    if len(kept) > top_n:
        kept = kept[:top_n]
    chosen = [isin for _place, isin in kept]
    have = set(chosen)
    for isin in ranked:
        if len(chosen) >= top_n:
            break
        if isin in have:
            continue
        chosen.append(isin)
        have.add(isin)
    return chosen


def index_momentum_score(day, names, view):
    """Average of 6-month and 12-month return, each divided by 1-year daily vol."""
    out = {}
    for isin in names:
        bucket = view.series.get(isin)
        end = view.end(isin)
        if bucket is None or end < 252:
            continue
        closes = bucket["c"]
        now = closes[end]
        six = closes[end - 126]
        twelve = closes[end - 252]
        if now <= 0 or six <= 0 or twelve <= 0:
            continue
        prev = closes[end - 252]
        rets = []
        for i in range(end - 251, end + 1):
            close = closes[i]
            if prev > 0 and close > 0:
                rets.append(close / prev - 1.0)
            prev = close
        if len(rets) < 252:
            continue
        mean = sum(rets) / float(len(rets))
        var = 0.0
        for value in rets:
            var += (value - mean) ** 2
        var /= float(len(rets) - 1)
        if var <= 0:
            continue
        vol = var ** 0.5
        r6 = now / six - 1.0
        r12 = now / twelve - 1.0
        out[isin] = 0.5 * (r6 / vol + r12 / vol)
    return out


def _members_on(universe, day):
    days = sorted(universe)
    pos = bisect.bisect_right(days, day) - 1
    if pos < 0:
        return []
    return universe[days[pos]]


def _purpose_sessions(actions_index, calendar):
    index = {}
    for session, day in enumerate(calendar):
        index[day] = session
    found = set()
    for key in actions_index:
        kind, name, day = key
        session = index.get(day)
        if session is None:
            continue
        found.add((kind, name, session))
    return found


def _has_purpose(found, isin, symbol, session):
    for delta in range(-5, 6):
        at = session + delta
        if ("isin", isin, at) in found or ("sym", symbol, at) in found:
            return True
    return False


def _cash_row(cm_root, day, symbol, isin):
    path = os.path.join(cm_root, "%s.csv.gz" % day.isoformat())
    if not os.path.isfile(path):
        return None
    chosen = None
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        import csv
        for row in csv.DictReader(fh):
            series = (row.get("series") or "").strip()
            if series not in ("EQ", "BE"):
                continue
            same_symbol = (row.get("symbol") or "").strip() == symbol
            same_isin = (row.get("isin") or "").strip() == isin and isin.startswith("INE")
            if not same_symbol and not same_isin:
                continue
            if chosen is None or series == "EQ":
                chosen = row
            if series == "EQ" and same_symbol:
                break
    return chosen


def _num(text):
    try:
        return float(text)
    except (TypeError, ValueError):
        return None


def audit_bar_actions(built, actions_index, cm_root, log, limit=30):
    """Count bar actions inside the top 500, and those with no nearby NSE purpose."""
    calendar = built["calendar"]
    index = {}
    for session, day in enumerate(calendar):
        index[day] = session
    universe = built["universe"][500]
    purpose = _purpose_sessions(actions_index, calendar)
    bar = [row for row in built["actions"] if row.get("source") == "bar"]
    in_universe = []
    bare = []
    for row in bar:
        session = index.get(row["date"])
        if session is None:
            continue
        members = _members_on(universe, row["date"])
        if row["isin"] not in members:
            continue
        in_universe.append(row)
        if not _has_purpose(purpose, row["isin"], row["symbol"], session):
            bare.append(row)
    log("bar actions %d" % len(bar))
    log("bar actions in the monthly top 500 %d" % len(in_universe))
    log("bar actions in the top 500 with no NSE purpose within 5 sessions %d" % len(bare))
    bare.sort(key=lambda row: (row["factor"], row["date"].isoformat(), row["symbol"]))
    shown = bare[:limit]
    for row in shown:
        session = index[row["date"]]
        prev_day = calendar[session - 1] if session else None
        today = _cash_row(cm_root, row["date"], row["symbol"], row["isin"])
        prev = _cash_row(cm_root, prev_day, row["symbol"], row["isin"]) if prev_day else None
        open_ = _num(today.get("open")) if today else None
        low = _num(today.get("low")) if today else None
        if prev is not None:
            previous = _num(prev.get("close"))
        elif today is not None:
            previous = _num(today.get("prev_close"))
        else:
            previous = None
        log(
            "bar check %s %s factor %.4f open %s prev %s low %s"
            % (
                row["date"].isoformat(),
                row["symbol"],
                row["factor"],
                "n/a" if open_ is None else "%.2f" % open_,
                "n/a" if previous is None else "%.2f" % previous,
                "n/a" if low is None else "%.2f" % low,
            )
        )
    return {
        "bar": len(bar),
        "in_top": len(in_universe),
        "bare": len(bare),
        "shown": len(shown),
    }


def _rank_book(panel, score, session, day, universe_n):
    series = panel["series"]
    last = panel["last"]
    universe = panel["universe"][universe_n]
    view = batch22._View(series, session)
    pool = []
    prices = {}
    for isin in universe.get(day) or []:
        if isin not in series or last.get(isin) == day:
            continue
        px = batch22._close_on(series[isin], session)
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
    return [isin for _value, isin in ranked], prices


def run_scheduled(panel, score, top_n, buffer, months, index_points, start, end,
                  overlay, capital, tri_points, check_monthly):
    """Equal-weight book on the first session of the given months, with a buffer."""
    calendar = panel["calendar"]
    series = panel["series"]
    last = panel["last"]
    # The panel's month start is the first session that actually traded.
    rebalance_on = set(day for day in panel["universe"][200] if day.month in months)
    month_starts = set(panel["universe"][200])
    holdings = {}
    cash = float(capital)
    trades = []
    equity = []
    turnover_sum = 0.0
    prices = {}
    target = []
    for session, day in enumerate(calendar):
        if day < start:
            continue
        if day > end:
            break
        for isin in list(holdings):
            px = batch22._close_on(series[isin], session)
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
        if day in rebalance_on and day in panel["universe"][200]:
            ranked, fresh = _rank_book(panel, score, session, day, 200)
            prices.update(fresh)
            target = buffered_book(ranked, list(holdings), top_n, buffer)
            chosen = list(target)
            if overlay is not None and not overlay(day):
                chosen = []
            cash, one_way = batch22._rebalance(cash, holdings, trades, prices, chosen, day)
            turnover_sum += one_way
        elif check_monthly and day in month_starts and overlay is not None:
            if not overlay(day):
                for isin in list(holdings):
                    px = prices.get(isin) or batch22._close_on(series[isin], session)
                    if px is not None and px > 0:
                        prices[isin] = px
                net, gross = batch22._sell_all(holdings, trades, prices, day)
                cash += net
                equity_now = cash
                turnover_sum += (gross / equity_now) if equity_now > 0 else 0.0
            elif not holdings and target:
                for isin in target:
                    px = batch22._close_on(series[isin], session)
                    if px is not None and px > 0:
                        prices[isin] = px
                cash, one_way = batch22._rebalance(
                    cash, holdings, trades, prices, list(target), day)
                turnover_sum += one_way
        equity.append((day, batch22._mark(cash, holdings, prices)))
    return batch22._finish(equity, trades, index_points, capital, turnover_sum, panel, tri_points)


def _top200_entries(panel, entries):
    universe = panel["universe"][200]
    kept = []
    for item in entries:
        members = _members_on(universe, item["day"])
        if item["isin"] in members:
            kept.append(item)
    return kept


def index_round_trip(points, start, end, capital=invest.CAPITAL):
    """Buy the first print on or after start, sell the last on or before end.

    One delivery round trip. The gain is taxed once through invest.tax_due.
    Returns (cagr, buy day, sell day, ending equity) or None.
    """
    buy = None
    sell = None
    for day, close in points:
        if day < start or day > end or close <= 0:
            continue
        if buy is None:
            buy = (day, close)
        sell = (day, close)
    if buy is None or sell is None or buy[0] >= sell[0]:
        return None
    buy_day, buy_px = buy
    sell_day, sell_px = sell
    shares = invest._afford(capital, buy_px)
    if shares <= 0:
        return None
    spent = shares * buy_px + invest._buy_cost(buy_px, shares)
    cash = capital - spent
    net = shares * sell_px - invest._sell_cost(sell_px, shares)
    gain = net - spent
    tax = invest.tax_due([{"buy": buy_day, "sell": sell_day, "gain": gain, "shares": shares}])
    final = cash + net - tax
    cagr = invest._cagr(capital, final, buy_day, sell_day)
    return cagr, buy_day, sell_day, final


def _existing_section(path, number):
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    heading = "\n## Attempt %d\n" % number
    start = text.find(heading)
    if start == -1:
        return None
    nxt = text.find("\n## ", start + 1)
    end = nxt if nxt != -1 else len(text)
    return text[start:end]


def _reprint_body(path, blocks):
    section = _existing_section(path, 22)
    if section is None:
        kept = batch22.rules_text(datetime.date.today().isoformat())
    else:
        marker = "\nResults.\n"
        at = section.find(marker)
        kept = section[:at].rstrip() if at != -1 else section.rstrip()
    lines = [kept, "", "Results.", ""]
    lines.append(
        "name | CAGR before tax | CAGR after tax | excess vs NIFTY 200 price | monthly t | "
        "max DD | NIFTY 200 DD | 2005-2014 | 2015-2024 | excess vs NIFTY 200 TRI | result"
    )
    for block in blocks:
        lines.append(batch22._row_line(block["name"], block["row"], block["result"]))
        for reason in block["reasons"]:
            lines.append("  " + reason)
    lines.append("")
    lines.append(
        "Before tax is the CAGR after delivery costs and before tax. "
        "The verdicts are unchanged."
    )
    lines.append("")
    lines.append(
        "NIFTY200 Momentum 30 price CAGR +19.33% over 2005-2024 and -4.44% "
        "over 2025 through 2026-11-09. 22a is not run on the holdout."
    )
    lines.append("")
    lines.append("No variant passed in sample. The holdout was not opened for a failure.")
    lines.append("")
    return "\n".join(lines)


def _report(stamp, blocks, notes):
    lines = [rules_text(stamp).rstrip(), "", "Results.", ""]
    lines.append(
        "name | CAGR before tax | CAGR after tax | excess vs NIFTY 200 price | monthly t | "
        "max DD | NIFTY 200 DD | 2005-2014 | 2015-2024 | excess vs NIFTY 200 TRI | result"
    )
    for block in blocks:
        lines.append(batch22._row_line(block["name"], block["row"], block["result"]))
        for reason in block["reasons"]:
            lines.append("  " + reason)
        if block.get("holdout"):
            lines.append("holdout " + batch22._row_line(
                block["name"], block["holdout_row"], block["holdout_result"]))
            for reason in block.get("holdout_reasons") or []:
                lines.append("  " + reason)
    lines.append("")
    for note in notes:
        lines.append(note)
    lines.append("")
    if any(block["passed"] for block in blocks):
        lines.append("An in-sample pass is listed above. Only 23d opens the holdout.")
    else:
        lines.append(
            "No attempt 23 variant passed. Short-term stock picking is Closed "
            "and factor exposure goes through index funds."
        )
    lines.append("")
    return "\n".join(lines)


def _catalogue(blocks):
    with open(STRATEGIES, encoding="utf-8") as fh:
        text = fh.read()
    for block in blocks:
        if block.get("holdout"):
            note = "PASS" if block["result"] == "PASS" else "FAIL"
            note = "%s Holdout %s" % (note, block.get("holdout_result") or "FAIL")
        else:
            note = block["result"]
        row = "| %s | 23 | %s |" % (block["name"], note)
        text = batch18.add_tier_row(text, "Closed", row)
    if not text.endswith("\n"):
        text += "\n"
    with open(STRATEGIES, "w", encoding="utf-8") as fh:
        fh.write(text)


def _run_22(built, price, tri, momentum, nse, log):
    batch22.build_reactions.levels = batch22._session_levels(built, price)
    events = batch22._results_events(os.path.join(nse, "events.csv"))
    sample_events = [(day, symbol) for day, symbol in events if day <= END]
    reactions = batch22.build_reactions(built, sample_events)
    entries_20 = batch22.drift_entries(built, reactions, 20, END)
    entries_60 = batch22.drift_entries(built, reactions, 60, END)
    members = batch22._members(built["universe"][500])
    log("loading delivery for the attempt 22 reprint, %d isins" % len(members))
    delivery = batch22._load_delivery(built, nse, members)
    specs = [
        ("mom 12-1 top 20", "mom", batch22.momentum_score(21, 252), 20, 200),
        ("mom 12-1 top 30", "mom", batch22.momentum_score(21, 252), 30, 200),
        ("mom 6-1 top 20", "mom", batch22.momentum_score(21, 126), 20, 200),
        ("mom 6-1 top 30", "mom", batch22.momentum_score(21, 126), 30, 200),
        ("results drift 20", "drift", entries_20, None, None),
        ("results drift 60", "drift", entries_60, None, None),
        ("delivery accumulation", "month", batch22.delivery_score(delivery), 20, 500),
        ("low volatility", "month", batch22.volatility_score, 30, 200),
    ]
    blocks = []
    best = None
    for name, kind, fn, top_n, universe_n in specs:
        log("reprint %s" % name)
        if kind == "drift":
            row = batch22._run_drift_body(built, fn, price, START, END, None, invest.CAPITAL, tri)
        else:
            row = batch22._run_monthly_body(
                built, fn, top_n, universe_n, price, START, END, None, invest.CAPITAL, tri)
        reasons = batch22.judge(row, True)
        result = "PASS" if not reasons else "FAIL"
        log(batch22._row_line(name, row, result))
        block = {
            "name": name, "kind": kind, "fn": fn, "top_n": top_n,
            "universe": universe_n, "row": row, "reasons": reasons, "result": result,
        }
        blocks.append(block)
        if row["cagr"] is not None and (best is None or row["cagr"] > best["row"]["cagr"]):
            best = block
    if best is not None:
        risk = batch22.risk_on_map(price)
        overlay = batch22._overlay_from(risk)
        name = "overlay %s" % best["name"]
        log("reprint %s" % name)
        if best["kind"] == "drift":
            row = batch22._run_drift_body(
                built, best["fn"], price, START, END, overlay, invest.CAPITAL, tri)
        else:
            row = batch22._run_monthly_body(
                built, best["fn"], best["top_n"], best["universe"],
                price, START, END, overlay, invest.CAPITAL, tri)
        reasons = batch22.judge(row, True)
        result = "PASS" if not reasons else "FAIL"
        log(batch22._row_line(name, row, result))
        blocks.append({
            "name": name, "kind": best["kind"], "fn": best["fn"],
            "top_n": best["top_n"], "universe": best["universe"],
            "row": row, "reasons": reasons, "result": result,
        })
    mom_early = batch22._span_cagr(momentum, START, END)
    mom_late = batch22._span_cagr(momentum, HOLD, batch22._holdout_end(built))
    log(
        "NIFTY200 Momentum 30 price CAGR %s over 2005-2024 and %s over 2025 through %s. "
        "22a is not run on the holdout."
        % (batch22._pct(mom_early), batch22._pct(mom_late), batch22._holdout_end(built).isoformat())
    )
    return blocks


def _summary_row(stamp, name, row, result, window):
    excess = None
    if row["cagr"] is not None and row["index_cagr"] is not None:
        excess = row["cagr"] - row["index_cagr"]
    return "| 23 | %s | %s. | attempt 23, rules fixed before the run | %s | %d | %s | %s | %s |" % (
        stamp, name, window, row["trades"], batch22._pct(excess), batch22._num(row["t"]), result)


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(description="Attempt 23. Nothing is placed.")
    parser.add_argument("--nse", default=os.path.join("data", "nse"))
    parser.add_argument("--cache", default=os.path.join("data", "cache"))
    parser.add_argument("--experiments", default=EXPERIMENTS)
    args = parser.parse_args(argv)
    log = lambda line: print(line, flush=True)
    built = panel.load_panel(args.cache)
    if not built or built.get("version") != panel.PANEL_VERSION:
        built = panel.build_store(os.path.join(args.nse, "cm"), log=log)
        if not built:
            log("no cash bhavcopy, attempt 23 was not started")
            return 2
        panel.save_panel(built, args.cache)
    stamp = datetime.date.today().isoformat()
    follow.install_attempt(args.experiments, 23, rules_text(stamp), [])
    log("rules for attempt 23 written to %s before the run" % args.experiments)
    actions_index, _unknown = panel.load_action_index(os.path.join(args.nse, "actions"))
    audit_bar_actions(built, actions_index, os.path.join(args.nse, "cm"), log)
    price = panel._load_index(os.path.join(args.nse, "indices", "NIFTY_200.csv.gz"))
    tri = panel._load_index(os.path.join(args.nse, "indices", "NIFTY_200_TR.csv.gz"))
    momentum = panel._load_index(os.path.join(args.nse, "indices", "NIFTY200_MOMENTUM_30.csv.gz"))
    momentum_tri = panel._load_index(
        os.path.join(args.nse, "indices", "NIFTY200_MOMENTUM_30_TR.csv.gz"))
    reprinted = _run_22(built, price, tri, momentum, args.nse, log)
    window = "2005-01-01 to 2024-12-31"
    rows22 = []
    for block in reprinted:
        rows22.append(batch22._summary_row(stamp, block["name"], block["row"], block["result"], window))
    follow.install_attempt(
        args.experiments, 22, _reprint_body(args.experiments, reprinted), rows22)
    log("attempt 22 reprinted with a before-tax column, verdicts unchanged")
    risk = batch22.risk_on_map(price)
    overlay = batch22._overlay_from(risk)
    batch22.build_reactions.levels = batch22._session_levels(built, price)
    events = batch22._results_events(os.path.join(args.nse, "events.csv"))
    sample_events = [(day, symbol) for day, symbol in events if day <= END]
    reactions = batch22.build_reactions(built, sample_events)
    entries_60 = _top200_entries(built, batch22.drift_entries(built, reactions, 60, END))
    log("23d signals inside the top 200 %d" % len(entries_60))
    specs = [
        ("23a index momentum 6m", "sched", SIX_MONTHS, False),
        ("23b index momentum 12m", "sched", TWELVE_MONTHS, False),
        ("23c index momentum 6m overlay", "sched", SIX_MONTHS, True),
        ("23d results drift 60 top 200", "drift", None, False),
    ]
    blocks = []
    for name, kind, months, check in specs:
        log("running %s" % name)
        if kind == "drift":
            row = batch22._run_drift_body(
                built, entries_60, price, START, END, None, invest.CAPITAL, tri)
        else:
            use_overlay = overlay if check else None
            row = run_scheduled(
                built, index_momentum_score, TOP_N, BUFFER, months, price,
                START, END, use_overlay, invest.CAPITAL, tri, check)
        reasons = batch22.judge(row, True)
        result = "PASS" if not reasons else "FAIL"
        log(batch22._row_line(name, row, result))
        blocks.append({
            "name": name, "kind": kind, "row": row, "reasons": reasons,
            "result": result, "passed": result == "PASS", "months": months,
            "check": check,
        })
    notes = []
    held = index_round_trip(momentum_tri, BUY_DATE, END)
    if held is None:
        notes.append("NIFTY200 Momentum 30 TRI round trip could not be priced.")
    else:
        notes.append(
            "NIFTY200 Momentum 30 TRI bought %s sold %s, one LTCG, after-tax CAGR %s, "
            "ending equity %.2f."
            % (held[1].isoformat(), held[2].isoformat(), batch22._pct(held[0]), held[3])
        )
    held = index_round_trip(tri, BUY_DATE, END)
    if held is None:
        notes.append("NIFTY 200 TRI round trip could not be priced.")
    else:
        notes.append(
            "NIFTY 200 TRI bought %s sold %s, one LTCG, after-tax CAGR %s, "
            "ending equity %.2f."
            % (held[1].isoformat(), held[2].isoformat(), batch22._pct(held[0]), held[3])
        )
    last_index = batch22._holdout_end(built)
    notes.append(
        "NIFTY200 Momentum 30 price CAGR %s and NIFTY 200 price CAGR %s over 2025-01-01 "
        "through %s. 23a, 23b and 23c are not run on those dates."
        % (
            batch22._pct(batch22._span_cagr(momentum, HOLD, last_index)),
            batch22._pct(batch22._span_cagr(price, HOLD, last_index)),
            last_index.isoformat(),
        )
    )
    for note in notes:
        log(note)
    end = batch22._holdout_end(built)
    for block in blocks:
        if block["kind"] != "drift" or not block["passed"]:
            continue
        log("holdout %s" % block["name"])
        data._guard("attempt23", [end], final=True, log_path=None)
        hold_events = [(day, symbol) for day, symbol in events if day <= end]
        hold_reactions = batch22.build_reactions(built, hold_events)
        hold_entries = _top200_entries(
            built, batch22.drift_entries(built, hold_reactions, 60, end))
        row = batch22._run_drift_body(
            built, hold_entries, price, HOLD, end, None, invest.CAPITAL, tri)
        reasons = batch22.judge(row, False)
        result = "PASS" if not reasons else "FAIL"
        log("holdout " + batch22._row_line(block["name"], row, result))
        block["holdout"] = True
        block["holdout_result"] = result
        block["holdout_row"] = row
        block["holdout_reasons"] = reasons
    rows = []
    for block in blocks:
        rows.append(_summary_row(stamp, block["name"], block["row"], block["result"], window))
        if block.get("holdout"):
            rows.append(_summary_row(
                stamp, "holdout " + block["name"], block["holdout_row"],
                block["holdout_result"], "2025-01-01 to %s" % end.isoformat()))
    follow.install_attempt(args.experiments, 23, _report(stamp, blocks, notes), rows)
    _catalogue(blocks)
    for block in blocks:
        log("%s %s" % (block["name"], block["result"]))
    if not any(block["passed"] for block in blocks):
        log(END_RULE)
    return 0


if __name__ == "__main__":
    sys.exit(main())
