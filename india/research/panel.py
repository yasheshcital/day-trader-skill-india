"""Survivorship-free daily panel from the cash bhavcopy.

Each stock is keyed by ISIN. When the symbol on that ISIN changes, the change
is kept. The adjustment factor on a day is that day's prev_close divided by
the previous session's close. If it differs from 1 by more than 0.5%, the day
is a corporate action and every earlier open, high, low and close is
multiplied by that factor. Volume and turnover are left as printed.

The last session of an ISIN is marked. A stock that stops trading is sold at
that last close, and the loss stays in the result. The harness in invest.py
does the sale.

The universe for a month is the top 200 and the top 500 by the median
turnover of the previous 60 sessions, taken from the stocks that trade on the
first session of that month.

The panel is cached under data/cache/panel. Ten large names are then compared
with data/kite/day.
"""

import csv
import datetime
import gzip
import json
import os
import pickle
import statistics
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

ACTION_GAP = 0.005
LOOKBACK = 60
TOPS = (200, 500)
LARGE = (
    "RELIANCE", "TCS", "HDFCBANK", "INFY", "ICICIBANK",
    "SBIN", "BHARTIARTL", "ITC", "LT", "HINDUNILVR",
)
PRICE_KEYS = ("open", "high", "low", "close")


def _float(text):
    if text is None:
        return None
    text = str(text).strip()
    if text == "":
        return None
    try:
        return float(text)
    except ValueError:
        return None


def adjust_bars(bars):
    """Back-adjust one ISIN. bars are in date order.

    Returns (actions, adjusted). An action is recorded when
    prev_close / previous close differs from 1 by more than 0.5%. Earlier
    prices are multiplied by that factor. The action day's own prices are
    already on the new basis, so they are not multiplied by their own factor.
    """
    count = len(bars)
    factors = [1.0] * count
    actions = []
    for i in range(1, count):
        previous = bars[i - 1].get("close")
        prev_close = bars[i].get("prev_close")
        if previous is None or prev_close is None:
            continue
        if previous <= 0 or prev_close <= 0:
            continue
        factor = prev_close / float(previous)
        if abs(factor - 1.0) > ACTION_GAP:
            factors[i] = factor
            actions.append({
                "date": bars[i].get("date"),
                "isin": bars[i].get("isin", ""),
                "symbol": bars[i].get("symbol", ""),
                "factor": factor,
            })
    scale = [1.0] * count
    running = 1.0
    for i in range(count - 1, -1, -1):
        scale[i] = running
        running *= factors[i]
    adjusted = []
    for i, bar in enumerate(bars):
        item = dict(bar)
        item["adj_factor"] = scale[i]
        for key in PRICE_KEYS:
            value = bar.get(key)
            if value is None:
                item["adj_" + key] = None
            else:
                item["adj_" + key] = value * scale[i]
        adjusted.append(item)
    return actions, adjusted


def symbol_changes(bars_by_isin):
    """Rows of isin, date, old symbol, new symbol. The first symbol is not a change."""
    found = []
    for isin in sorted(bars_by_isin):
        previous = None
        for bar in bars_by_isin[isin]:
            symbol = bar.get("symbol") or ""
            if previous is not None and symbol and symbol != previous:
                found.append({
                    "isin": isin,
                    "date": bar.get("date"),
                    "old": previous,
                    "new": symbol,
                })
            if symbol:
                previous = symbol
    return found


def month_universes(bars_by_isin, tops=TOPS):
    """First session of each month -> top 200 and top 500 ISIN lists.

    A stock qualifies when it trades that day and has 60 earlier sessions.
    The rank is the median turnover of those 60 sessions, highest first.
    """
    by_date = {}
    for isin, bars in bars_by_isin.items():
        for bar in bars:
            by_date.setdefault(bar["date"], []).append((isin, bar))
    dates = sorted(by_date)
    history = {}
    out = {}
    for n in tops:
        out[n] = {}
    seen_month = {}
    for day in dates:
        month = (day.year, day.month)
        first = month not in seen_month
        if first:
            seen_month[month] = day
            ranked = []
            for isin, bar in by_date[day]:
                prior = history.get(isin) or []
                if len(prior) < LOOKBACK:
                    continue
                window = prior[-LOOKBACK:]
                ranked.append((statistics.median(window), isin))
            ranked.sort(key=lambda item: (-item[0], item[1]))
            ordered = [isin for _median, isin in ranked]
            for n in tops:
                out[n][day] = ordered[:n]
        for isin, bar in by_date[day]:
            turnover = bar.get("turnover")
            if turnover is None:
                continue
            history.setdefault(isin, []).append(turnover)
    return out


def _read_day(path):
    rows = []
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        for cell in csv.DictReader(fh):
            isin = (cell.get("isin") or "").strip()
            symbol = (cell.get("symbol") or "").strip()
            if isin == "" or symbol == "":
                continue
            close = _float(cell.get("close"))
            if close is None:
                continue
            rows.append({
                "date": datetime.date.fromisoformat(cell["date"]),
                "symbol": symbol,
                "series": (cell.get("series") or "").strip(),
                "isin": isin,
                "open": _float(cell.get("open")),
                "high": _float(cell.get("high")),
                "low": _float(cell.get("low")),
                "close": close,
                "prev_close": _float(cell.get("prev_close")),
                "volume": _float(cell.get("volume")),
                "turnover": _float(cell.get("turnover")),
            })
    return rows


def _prefer(kept, row):
    if kept is None:
        return row
    if kept.get("series") == "EQ":
        return kept
    if row.get("series") == "EQ":
        return row
    return kept


def load_raw(cm_root):
    """ISIN -> bars, one row per session. EQ wins over BE on the same day."""
    if not os.path.isdir(cm_root):
        return {}
    names = []
    for name in os.listdir(cm_root):
        if name.endswith(".csv.gz"):
            names.append(name)
    names.sort()
    grouped = {}
    for name in names:
        for row in _read_day(os.path.join(cm_root, name)):
            per_day = grouped.setdefault(row["isin"], {})
            per_day[row["date"]] = _prefer(per_day.get(row["date"]), row)
    bars = {}
    for isin, per_day in grouped.items():
        ordered = [per_day[day] for day in sorted(per_day)]
        bars[isin] = ordered
    return bars


def build_panel(bars_by_isin):
    """Adjust every ISIN, mark its last day, and build both universes."""
    actions = []
    adjusted = {}
    last = {}
    for isin, bars in bars_by_isin.items():
        found, rows = adjust_bars(bars)
        if rows:
            rows[-1]["last"] = True
            last[isin] = rows[-1]["date"]
            for row in rows[:-1]:
                row["last"] = False
        actions.extend(found)
        adjusted[isin] = rows
    actions.sort(key=lambda item: (item["date"], item["isin"]))
    return {
        "bars": adjusted,
        "actions": actions,
        "changes": symbol_changes(adjusted),
        "last": last,
        "universe": month_universes(adjusted),
    }


def cache_dir(cache_root):
    return os.path.join(cache_root, "panel")


def save_panel(panel, cache_root):
    folder = cache_dir(cache_root)
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, "panel.pkl")
    tmp = path + ".part"
    with open(tmp, "wb") as fh:
        pickle.dump(panel, fh, protocol=3)
    os.replace(tmp, path)
    changes = os.path.join(folder, "symbol_changes.csv")
    with open(changes, "w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh, lineterminator="\n")
        writer.writerow(("isin", "date", "old", "new"))
        for row in panel["changes"]:
            writer.writerow((
                row["isin"], row["date"].isoformat(), row["old"], row["new"]))
    for n, mapping in panel["universe"].items():
        payload = {}
        for day, names in mapping.items():
            payload[day.isoformat()] = names
        dest = os.path.join(folder, "universe-%d.json" % n)
        with open(dest, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, sort_keys=True)
            fh.write("\n")
    return path


def load_panel(cache_root):
    path = os.path.join(cache_dir(cache_root), "panel.pkl")
    if not os.path.isfile(path):
        return None
    with open(path, "rb") as fh:
        return pickle.load(fh)


def _kite_closes(path):
    found = {}
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            stamp = row.get("datetime_start_ist") or row.get("date") or ""
            day = stamp[:10]
            close = _float(row.get("close"))
            if len(day) == 10 and close is not None and close > 0:
                found[day] = close
    return found


def _isin_for_symbol(panel, symbol):
    best = None
    best_n = -1
    for isin, bars in panel["bars"].items():
        count = 0
        for bar in bars:
            if bar.get("symbol") == symbol:
                count += 1
        if count > best_n:
            best = isin
            best_n = count
    if best_n <= 0:
        return None
    return best


def cross_check(panel, kite_root, names=LARGE):
    """Largest absolute percent gap between adjusted closes and Kite day closes.

    Each row is symbol, overlapping sessions, and the largest gap in percent.
    A missing file or a symbol that never appears is reported with no overlap.
    """
    rows = []
    largest = None
    for symbol in names:
        path = os.path.join(kite_root, "day", symbol + ".csv.gz")
        isin = _isin_for_symbol(panel, symbol) if panel else None
        if not panel or isin is None or not os.path.isfile(path):
            rows.append({"symbol": symbol, "n": 0, "gap": None, "date": None})
            continue
        kite = _kite_closes(path)
        gap = None
        when = None
        n = 0
        for bar in panel["bars"][isin]:
            adj = bar.get("adj_close")
            other = kite.get(bar["date"].isoformat())
            if adj is None or other is None or other == 0:
                continue
            n += 1
            pct = abs(adj / other - 1.0) * 100.0
            if gap is None or pct > gap:
                gap = pct
                when = bar["date"]
        rows.append({"symbol": symbol, "n": n, "gap": gap, "date": when})
        if gap is not None and (largest is None or gap > largest["gap"]):
            largest = {"symbol": symbol, "gap": gap, "date": when, "n": n}
    return {"rows": rows, "largest": largest}


def _print_actions(actions, log):
    for action in actions:
        day = action["date"]
        text = day.isoformat() if hasattr(day, "isoformat") else str(day)
        log("%s %s %s factor %.4f" % (
            text, action.get("symbol", ""), action.get("isin", ""), action["factor"]))
    log("corporate actions %d" % len(actions))


def _print_check(check, log):
    log("kite cross-check")
    for row in check["rows"]:
        if row["gap"] is None:
            log("%s no overlap" % row["symbol"])
        else:
            when = row["date"].isoformat() if row["date"] is not None else ""
            log("%s sessions %d max gap %.3f%% on %s" % (
                row["symbol"], row["n"], row["gap"], when))
    largest = check["largest"]
    if largest is None:
        log("largest gap: no overlap")
    else:
        log("largest gap %s %.3f%% on %s" % (
            largest["symbol"], largest["gap"], largest["date"].isoformat()))


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(description="Build the survivorship-free panel. Nothing is ordered.")
    parser.add_argument("--nse", default=os.path.join("data", "nse"))
    parser.add_argument("--kite", default=os.path.join("data", "kite"))
    parser.add_argument("--cache", default=os.path.join("data", "cache"))
    args = parser.parse_args(argv)
    log = lambda line: print(line, flush=True)
    raw = load_raw(os.path.join(args.nse, "cm"))
    if not raw:
        log("corporate actions 0")
        log("no cash bhavcopy on disk")
        log("kite cross-check: no cash bhavcopy on disk")
        log("largest gap: no overlap")
        return 0
    panel = build_panel(raw)
    save_panel(panel, args.cache)
    _print_actions(panel["actions"], log)
    log("symbol changes %d" % len(panel["changes"]))
    log("isins %d" % len(panel["bars"]))
    _print_check(cross_check(panel, args.kite), log)
    return 0


if __name__ == "__main__":
    sys.exit(main())
