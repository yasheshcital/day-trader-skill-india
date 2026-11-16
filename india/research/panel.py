"""Survivorship-free daily panel from the cash bhavcopy.

Each stock is keyed by ISIN. When the symbol on that ISIN changes, the change
is kept. The stored panel adjusts in this order. For a name in the Kite day files, a day
whose raw close over the Kite close has moved more than 0.5% from the
previous overlap uses that ratio. Otherwise the NSE corporate-actions file
supplies the factor. Otherwise, on consecutive sessions, prev_close over the
previous close is used when it is more than 0.5% from 1. Across a gap, only a
factor within 1% of a standard ratio (1/2, 1/5, 1/10, 2/3, 1/3, 1/4, 4/5,
5/6, 9/10, 10/11, 1/1.5, 1/3.5) is an action. A weekday with no cash file,
and not a known NSE holiday, is an archive gap. A session where at least 30%
of the names that traded both days disagree on prev_close is treated the same
way. Every action records its source.
Volume and turnover are left as printed.

Rows that arrive with a blank ISIN are held under the symbol. An ISIN whose
last bar and another ISIN's first bar share a symbol and sit 0 to 5 sessions
apart are stitched into one series under the newer ISIN. The action check
runs across that join.

The last session of an ISIN is marked. A stock that stops trading is sold at
that last close, and the loss stays in the result. The harness in invest.py
does the sale.

The universe for a month is the top 200 and the top 500 by the median
turnover of the previous 60 sessions, taken from the stocks that trade on the
first session of that month.

The panel is cached under data/cache/panel. Ten large names are then compared
with data/kite/day.
"""

import array
import bisect
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
STITCH_SESSIONS = 5
# Within 1% of one of these, a gap is treated as a split or a bonus.
STANDARD_RATIOS = (
    1.0 / 2.0,
    1.0 / 5.0,
    1.0 / 10.0,
    2.0 / 3.0,
    1.0 / 3.0,
    1.0 / 4.0,
    4.0 / 5.0,
    5.0 / 6.0,
    9.0 / 10.0,
    10.0 / 11.0,
    1.0 / 1.5,
    1.0 / 3.5,
)
FACTOR_BUCKETS = (
    ("<0.2", lambda factor: factor < 0.2),
    ("0.2-0.5", lambda factor: 0.2 <= factor < 0.5),
    ("0.5-0.9", lambda factor: 0.5 <= factor < 0.9),
    ("0.9-0.98", lambda factor: 0.9 <= factor < 0.98),
    ("0.98-0.995", lambda factor: 0.98 <= factor <= 0.995),
    ("1.005-1.02", lambda factor: 1.005 <= factor <= 1.02),
    (">1.02", lambda factor: factor > 1.02),
)
PANEL_VERSION = 3
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


def keep_equity(isin, series):
    """EQ and BE only. A published ISIN must start with INE.

    A blank ISIN is the cash file from before June 2011. It is kept so the
    stitch can join it onto the INE series. An INF fund or any other prefix
    is dropped.
    """
    kind = (series or "").strip().upper()
    if kind not in ("EQ", "BE"):
        return False
    text = (isin or "").strip()
    if text == "":
        return True
    return text.startswith("INE")


def listed_equity(isin):
    """True for a series that survives the filter. Blank and SYM keys do not."""
    return (isin or "").startswith("INE")


def choose_factor(kite_factor, nse_factor, prev_factor, adjacent):
    """Kite, then the NSE file, then prev_close, then the gap ratio.

    A Kite value is used only when it is more than 0.5% from 1. Returns
    (factor or None, source or None).
    """
    if kite_factor is not None and abs(kite_factor - 1.0) > ACTION_GAP:
        return kite_factor, "kite"
    if nse_factor is not None:
        return nse_factor, "nse"
    if prev_factor is None:
        return None, None
    if adjacent and abs(prev_factor - 1.0) > ACTION_GAP:
        return prev_factor, "prev_close"
    if (not adjacent) and near_standard(prev_factor):
        return prev_factor, "ratio"
    return None, None


def resolve_corporate(combined, previous, prev_close, open_):
    """Price factor for a demerger or a rights issue, else the parsed factor.

    Returns (factor or None, estimated). prev_close is used when the exchange
    adjusted it. A demerger with an unadjusted prev_close uses the open.
    """
    parsed = combined.get("factor")
    if combined.get("demerger") or combined.get("rights"):
        published = None
        if previous and prev_close and previous > 0 and prev_close > 0:
            published = prev_close / float(previous)
        if published is not None and abs(published - 1.0) > ACTION_GAP:
            return published, False
        if combined.get("demerger") and previous and open_ and previous > 0 and open_ > 0:
            estimated = open_ / float(previous)
            if parsed is not None:
                estimated *= parsed
            return estimated, True
        if parsed is not None:
            return parsed, False
        return None, False
    if parsed is not None:
        return parsed, False
    return None, False


def kite_ratio(raw_now, kite_now, raw_prev, kite_prev):
    """raw/Kite against the previous overlap. None when Kite is not a real price.

    A Kite close under 1 rupee while the raw close is many times larger is a
    stub, not an adjusted series, and must not be turned into a factor.
    """
    if raw_now <= 0 or kite_now <= 0 or raw_prev <= 0 or kite_prev <= 0:
        return None
    small = kite_now if kite_now < kite_prev else kite_prev
    if small < 1.0 and max(raw_now, raw_prev) / small > 30.0:
        return None
    return (raw_now / kite_now) / (raw_prev / kite_prev)


def kite_change(raw_now, kite_now, raw_prev, kite_prev):
    """How far raw/Kite moved since the previous overlap. None inside 0.5%."""
    change = kite_ratio(raw_now, kite_now, raw_prev, kite_prev)
    if change is None or abs(change - 1.0) <= ACTION_GAP:
        return None
    return change


def near_standard(factor):
    """True when factor is within 1% of a standard split or bonus ratio."""
    for ratio in STANDARD_RATIOS:
        if abs(factor - ratio) <= 0.01 * ratio:
            return True
    return False


def is_corporate_action(factor, adjacent):
    """Adjacent sessions use the 0.5% rule. A gap uses the standard ratios only."""
    if adjacent:
        return abs(factor - 1.0) > ACTION_GAP
    return near_standard(factor)


def _relative(value, ratio):
    return abs(value - ratio) / ratio


def price_jump_ratio(previous, open_, high, low, close):
    """A standard ratio when the whole bar has already moved to the new basis.

    Coarse ratios (a half, a third, a fifth) allow the ex-day move. Fine
    ratios (a tenth off, a fifth off) have to sit tight, or a down day would
    look like a bonus. The returned value is the exact ratio.
    """
    if previous <= 0 or open_ <= 0 or high <= 0 or low <= 0 or close <= 0:
        return None
    best = None
    best_far = None
    for ratio in STANDARD_RATIOS:
        # 4/5 and 9/10 are the 20% and 10% circuit limits. A locked-down
        # day sits on them. They still count when prev_close itself carries
        # the ratio; they are not inferred from the print.
        if abs(ratio - 0.8) < 1e-12 or abs(ratio - 0.9) < 1e-12:
            continue
        coarse = ratio < 0.75
        near_lim = 0.025 if coarse else 0.005
        far_lim = 0.05 if coarse else 0.01
        band = 0.08 if coarse else 0.02
        distances = (
            _relative(open_ / previous, ratio),
            _relative(close / previous, ratio),
            _relative(high / previous, ratio),
            _relative(low / previous, ratio),
        )
        closer = distances[0] if distances[0] < distances[1] else distances[1]
        farther = distances[1] if distances[0] < distances[1] else distances[0]
        if closer > near_lim or farther > far_lim:
            continue
        if distances[2] > band or distances[3] > band:
            continue
        if best_far is None or farther < best_far:
            best = ratio
            best_far = farther
    return best


def extreme_bar_factor(previous, open_, high, low, close):
    """A split the standard list missed, when the whole bar opened on the new price.

    The bar has to stay within 25% of its open, and the open has to be at
    least 40% away from the previous close. A crash that opens near the old
    price does not qualify. Returns (factor, estimated).
    """
    if previous <= 0 or open_ <= 0 or high <= 0 or low <= 0 or close <= 0:
        return None, False
    if (high - low) / open_ > 0.25:
        return None, False
    ratio = open_ / previous
    if ratio > 0.60 and ratio < 1.0 / 0.60:
        return None, False
    for standard in STANDARD_RATIOS:
        if standard >= 0.75:
            continue
        if abs(ratio - standard) / standard <= 0.08:
            return standard, False
        inverse = 1.0 / standard
        if inverse > 1.5 and abs(ratio - inverse) / inverse <= 0.08:
            return inverse, False
    return ratio, True


def action_factor(previous, prev_close, open_, high, low, close, adjacent):
    """The factor to apply, or None when the day is an ordinary return."""
    if previous is None or prev_close is None or previous <= 0 or prev_close <= 0:
        published = None
    else:
        published = prev_close / float(previous)
    if published is not None and is_corporate_action(published, adjacent):
        return published
    if published is not None and abs(published - 1.0) > ACTION_GAP:
        return None
    return price_jump_ratio(
        previous or 0.0,
        open_ or 0.0,
        high or 0.0,
        low or 0.0,
        close or 0.0,
    )


def _adjacent(prev_day, day, calendar_index):
    """True when day is the next calendar session after prev_day.

    With no calendar, successive bars are treated as adjacent. That keeps a
    caller that does not know the session list on the 0.5% rule.
    """
    if calendar_index is None:
        return True
    prev_i = calendar_index.get(prev_day)
    cur_i = calendar_index.get(day)
    if prev_i is None or cur_i is None:
        return False
    return cur_i == prev_i + 1


def adjust_bars(bars, calendar=None):
    """Back-adjust one ISIN. bars are in date order.

    Returns (actions, adjusted). The action day's own prices stay on the new
    basis. Every earlier open, high, low and close is multiplied by the factor.
    """
    calendar_index = None
    if calendar is not None:
        calendar_index = {}
        for i, day in enumerate(calendar):
            calendar_index[day] = i
    count = len(bars)
    factors = [1.0] * count
    actions = []
    for i in range(1, count):
        previous = bars[i - 1].get("close")
        prev_close = bars[i].get("prev_close")
        adjacent = _adjacent(bars[i - 1].get("date"), bars[i].get("date"), calendar_index)
        factor = action_factor(
            previous,
            prev_close,
            bars[i].get("open"),
            bars[i].get("high"),
            bars[i].get("low"),
            bars[i].get("close"),
            adjacent,
        )
        if factor is None:
            continue
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


def factor_histogram(actions):
    """Counts and up to five examples in each factor bucket. Examples are the earliest."""
    rows = []
    ordered = sorted(actions, key=lambda item: (item["date"], item.get("symbol", ""), item.get("isin", "")))
    for label, test in FACTOR_BUCKETS:
        examples = []
        count = 0
        for action in ordered:
            if not test(action["factor"]):
                continue
            count += 1
            if len(examples) < 5:
                examples.append(action)
        rows.append({"label": label, "count": count, "examples": examples})
    return rows


def stitch_links(endpoints):
    """Pair an ISIN's last bar with a later ISIN's first bar.

    endpoints are (isin, start_idx, end_idx, start_symbol, end_symbol).
    A pair qualifies when the symbols match and the session index of the
    first bar minus the session index of the last bar is from 0 to 5.
    Each ISIN is an old series at most once and a new series at most once.
    The smaller gap wins.
    """
    starters = {}
    enders = {}
    for isin, start_idx, end_idx, start_symbol, end_symbol in endpoints:
        starters.setdefault(start_symbol, []).append((start_idx, isin))
        enders.setdefault(end_symbol, []).append((end_idx, isin))
    pairs = []
    for symbol, ends in enders.items():
        starts = starters.get(symbol) or []
        for end_idx, old in ends:
            for start_idx, new in starts:
                if new == old:
                    continue
                gap = start_idx - end_idx
                if gap < 0 or gap > STITCH_SESSIONS:
                    continue
                pairs.append((gap, old, new, symbol, start_idx))
    pairs.sort()
    used_old = set()
    used_new = set()
    links = []
    for gap, old, new, symbol, start_idx in pairs:
        if old in used_old or new in used_new:
            continue
        used_old.add(old)
        used_new.add(new)
        links.append({
            "old": old,
            "new": new,
            "sessions": gap,
            "symbol": symbol,
            "start_idx": start_idx,
        })
    return links


def _stitch_chains(links):
    succ = {}
    pred = set()
    for link in links:
        succ[link["old"]] = link
        pred.add(link["new"])
    chains = []
    for isin in sorted(succ):
        if isin in pred:
            continue
        chain = []
        cursor = isin
        while cursor in succ:
            link = succ[cursor]
            chain.append(link)
            cursor = link["new"]
        chains.append(chain)
    return chains


def stitch_isins(bars_by_isin, calendar):
    """Join ISIN changes. The kept key is the newest ISIN in the chain.

    Returns (merged bars, stitches). A stitch records the symbol, the two
    ISINs, the newer series' first date, and the session gap.
    """
    index = {}
    for i, day in enumerate(calendar):
        index[day] = i
    endpoints = []
    for isin, bars in bars_by_isin.items():
        if not bars:
            continue
        start_idx = index.get(bars[0].get("date"))
        end_idx = index.get(bars[-1].get("date"))
        if start_idx is None or end_idx is None:
            continue
        endpoints.append((
            isin, start_idx, end_idx, bars[0].get("symbol") or "", bars[-1].get("symbol") or "",
        ))
    links = stitch_links(endpoints)
    drop = set()
    merged = {}
    for isin, bars in bars_by_isin.items():
        merged[isin] = list(bars)
    stitches = []
    for chain in _stitch_chains(links):
        newer = chain[-1]["new"]
        pieces = []
        cursor = chain[0]["old"]
        for link in chain:
            older_bars = merged.get(cursor) or []
            start_idx = link["start_idx"]
            kept = []
            for bar in older_bars:
                if index.get(bar.get("date"), -1) < start_idx:
                    kept.append(bar)
            pieces.extend(kept)
            day = calendar[start_idx]
            stitches.append({
                "date": day,
                "symbol": link["symbol"],
                "old": link["old"],
                "new": link["new"],
                "sessions": link["sessions"],
            })
            drop.add(link["old"])
            cursor = link["new"]
        pieces.extend(merged.get(newer) or [])
        merged[newer] = pieces
    for isin in drop:
        merged.pop(isin, None)
    stitches.sort(key=lambda item: (item["date"], item["symbol"], item["old"]))
    return merged, stitches


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


def _blank_series():
    return {
        "idx": array.array("i"),
        "sym": array.array("I"),
        "o": array.array("d"),
        "h": array.array("d"),
        "l": array.array("d"),
        "c": array.array("d"),
        "p": array.array("d"),
        "to": array.array("d"),
    }


def _append_bar(series, session, sym, open_, high, low, close, prev, turnover):
    series["idx"].append(session)
    series["sym"].append(sym)
    series["o"].append(open_)
    series["h"].append(high)
    series["l"].append(low)
    series["c"].append(close)
    series["p"].append(prev)
    series["to"].append(turnover)


def _num_cell(text):
    try:
        return float(text)
    except ValueError:
        return 0.0


def _holiday_dates():
    from india.research.nse_holidays import HOLIDAYS
    found = set()
    for key in HOLIDAYS:
        found.add(datetime.date.fromisoformat(key))
    return found


def _with_archive_gaps(file_dates):
    """File dates plus weekdays that have no file and are not a known holiday.

    A missing file is an archive gap. The sessions on either side are then
    not adjacent, so the standard-ratio rule decides the action.
    """
    if not file_dates:
        return []
    holidays = _holiday_dates()
    have = set(file_dates)
    calendar = []
    day = file_dates[0]
    last = file_dates[-1]
    one = datetime.timedelta(days=1)
    while day <= last:
        if day in have or (day.weekday() < 5 and day not in holidays):
            calendar.append(day)
        day += one
    return calendar


def load_store(cm_root, log=None):
    """Calendar plus one raw series per ISIN. EQ wins over BE on the same day."""
    if not os.path.isdir(cm_root):
        return [], [], {}, set()
    names = []
    for name in os.listdir(cm_root):
        if len(name) >= 14 and name.endswith(".csv.gz"):
            names.append(name)
    names.sort()
    file_dates = []
    for name in names:
        file_dates.append(datetime.date(int(name[0:4]), int(name[5:7]), int(name[8:10])))
    calendar = _with_archive_gaps(file_dates)
    session_of = {}
    for i, day in enumerate(calendar):
        session_of[day] = i
    symbols = []
    sym_id = {}
    series = {}
    dropped = set()
    for nth, name in enumerate(names):
        if log and nth % 500 == 0:
            log("reading cash %d of %d" % (nth, len(names)))
        session = session_of[file_dates[nth]]
        chosen = {}
        with gzip.open(os.path.join(cm_root, name), "rt", encoding="utf-8") as fh:
            reader = csv.reader(fh)
            header = next(reader)
            col = {}
            for i, cell in enumerate(header):
                col[cell] = i
            for row in reader:
                isin = row[col["isin"]].strip()
                symbol = row[col["symbol"]].strip()
                kind = row[col["series"]].strip().upper()
                if symbol == "" or not keep_equity(isin, kind):
                    if symbol and kind in ("EQ", "BE") and isin and not isin.startswith("INE"):
                        dropped.add(symbol)
                    continue
                close = _num_cell(row[col["close"]])
                if close <= 0:
                    continue
                if isin == "":
                    isin = "SYM:" + symbol
                rank = 0 if kind == "EQ" else 1
                prev = chosen.get(isin)
                if prev is not None and prev[0] <= rank:
                    continue
                sid = sym_id.get(symbol)
                if sid is None:
                    sid = len(symbols)
                    symbols.append(sys.intern(symbol))
                    sym_id[symbol] = sid
                chosen[isin] = (
                    rank, sid,
                    _num_cell(row[col["open"]]),
                    _num_cell(row[col["high"]]),
                    _num_cell(row[col["low"]]),
                    close,
                    _num_cell(row[col["prev_close"]]),
                    _num_cell(row[col["turnover"]]),
                )
        for isin, item in chosen.items():
            bucket = series.get(isin)
            if bucket is None:
                bucket = _blank_series()
                series[isin] = bucket
            _append_bar(bucket, session, item[1], item[2], item[3], item[4], item[5], item[6], item[7])
    return calendar, symbols, series, dropped


def _slice_series(series, end_session):
    """Bars whose session index is strictly before end_session."""
    cut = 0
    idx = series["idx"]
    while cut < len(idx) and idx[cut] < end_session:
        cut += 1
    out = _blank_series()
    for key in out:
        out[key].extend(series[key][:cut])
    return out


def _extend_series(dest, src):
    for key in dest:
        dest[key].extend(src[key])


def stitch_store(series, symbols, calendar):
    """Same rule as stitch_isins, on the compact series. Kept key is the newer ISIN."""
    endpoints = []
    for isin, bucket in series.items():
        if len(bucket["idx"]) == 0:
            continue
        endpoints.append((
            isin,
            bucket["idx"][0],
            bucket["idx"][-1],
            symbols[bucket["sym"][0]],
            symbols[bucket["sym"][-1]],
        ))
    links = stitch_links(endpoints)
    stitches = []
    for chain in _stitch_chains(links):
        newer = chain[-1]["new"]
        dest = _blank_series()
        for link in chain:
            _extend_series(dest, _slice_series(series[link["old"]], link["start_idx"]))
            stitches.append({
                "date": calendar[link["start_idx"]],
                "symbol": link["symbol"],
                "old": link["old"],
                "new": link["new"],
                "sessions": link["sessions"],
            })
            del series[link["old"]]
        _extend_series(dest, series[newer])
        series[newer] = dest
    stitches.sort(key=lambda item: (item["date"], item["symbol"], item["old"]))
    return stitches


def _gap_sessions(series):
    """Sessions where a missing file moved prev_close for most of the market.

    One absent bhavcopy makes the next file look adjacent. When most names
    disagree, that day is an archive gap and only a standard ratio is an action.
    """
    eligible = {}
    suspect = {}
    for bucket in series.values():
        idx = bucket["idx"]
        close = bucket["c"]
        prev = bucket["p"]
        for i in range(1, len(idx)):
            if idx[i] != idx[i - 1] + 1:
                continue
            if close[i - 1] <= 0 or prev[i] <= 0:
                continue
            session = idx[i]
            eligible[session] = eligible.get(session, 0) + 1
            if abs(prev[i] / close[i - 1] - 1.0) > ACTION_GAP:
                suspect[session] = suspect.get(session, 0) + 1
    found = set()
    for session, count in eligible.items():
        if count >= 50 and suspect.get(session, 0) / float(count) >= 0.30:
            found.add(session)
    return found


def _series_kite(bucket, symbols, kite_by_symbol):
    """The Kite day file for this series, keyed by date. None when it has none."""
    if not kite_by_symbol:
        return None
    best = None
    best_n = 0
    counts = {}
    for sid in bucket["sym"]:
        name = symbols[sid]
        if name not in kite_by_symbol:
            continue
        counts[name] = counts.get(name, 0) + 1
    for name, count in counts.items():
        if best is None or count > best_n:
            best = name
            best_n = count
    if best is None:
        return None
    return kite_by_symbol[best]


def _kite_factor_at(bucket, calendar, kite_map, i):
    if kite_map is None:
        return None
    day = calendar[bucket["idx"][i]]
    kite_now = kite_map.get(day)
    raw_now = bucket["c"][i]
    if kite_now is None or raw_now <= 0:
        return None
    j = i - 1
    while j >= 0:
        kite_prev = kite_map.get(calendar[bucket["idx"][j]])
        raw_prev = bucket["c"][j]
        if kite_prev is not None and raw_prev > 0:
            return kite_ratio(raw_now, kite_now, raw_prev, kite_prev)
        j -= 1
    return None


def _dividend_only(combined):
    """An NSE day that is only a dividend, with no split, bonus, rights or demerger."""
    if not combined:
        return False
    if combined.get("factor") is not None:
        return False
    if combined.get("rights") or combined.get("demerger"):
        return False
    return True


def _nse_for_bar(actions_index, isin, symbol, day):
    if not actions_index:
        return None
    found = actions_index.get(("isin", isin, day))
    if found is not None:
        return found
    return actions_index.get(("sym", symbol, day))


def adjust_store(series, symbols, calendar, actions_index=None, kite_by_symbol=None):
    """Back-adjust every series. Drops the raw high, low and prev_close.

    With an actions index or a Kite map, the factor priority is Kite, then
    the NSE file, then prev_close, then the standard ratio across a gap.
    Without either, the older bar rule is kept so a caller with no archive
    still sees a split that the price itself shows.
    """
    gaps = _gap_sessions(series)
    external = actions_index is not None or kite_by_symbol is not None
    actions = []
    adjusted = {}
    for isin, bucket in series.items():
        n = len(bucket["idx"])
        factors = [1.0] * n
        idx = bucket["idx"]
        close = bucket["c"]
        prev = bucket["p"]
        opens = bucket["o"]
        highs = bucket["h"]
        lows = bucket["l"]
        kite_map = _series_kite(bucket, symbols, kite_by_symbol) if external else None
        for i in range(1, n):
            if close[i - 1] <= 0:
                continue
            adjacent = idx[i] == idx[i - 1] + 1 and idx[i] not in gaps
            estimated = False
            source = ""
            if external:
                symbol = symbols[bucket["sym"][i]]
                observed = _kite_factor_at(bucket, calendar, kite_map, i)
                combined = _nse_for_bar(actions_index, isin, symbol, calendar[idx[i]])
                nse_factor = None
                if combined is not None:
                    nse_factor, estimated = resolve_corporate(
                        combined, close[i - 1], prev[i], opens[i])
                published = None
                if prev[i] > 0:
                    published = prev[i] / close[i - 1]
                # A published prev_close that the open did not trade through is
                # a bad print, not an adjustment. Ignore it.
                published_ok = True
                if published is not None and abs(published - 1.0) > 0.05:
                    if prev[i] <= 0 or opens[i] <= 0 or abs(opens[i] / prev[i] - 1.0) > 0.40:
                        published_ok = False
                        published = None
                if nse_factor is not None and not published_ok:
                    nse_factor = None
                bar_factor = None
                bar_estimated = False
                if published is None or abs(published - 1.0) <= 0.05:
                    bar_factor = price_jump_ratio(
                        close[i - 1], opens[i], highs[i], lows[i], close[i])
                    if bar_factor is None:
                        bar_factor, bar_estimated = extreme_bar_factor(
                            close[i - 1], opens[i], highs[i], lows[i], close[i])
                raw_ret = close[i] / close[i - 1] - 1.0
                use_bar = (
                    bar_factor is not None
                    and symbol not in LARGE
                    and (raw_ret < -0.40 or raw_ret > 0.80)
                )
                if observed is not None and not use_bar:
                    factor = observed if abs(observed - 1.0) > ACTION_GAP else None
                    source = "kite"
                    if factor is not None:
                        adjusted_ret = close[i] / (close[i - 1] * factor) - 1.0
                        # Kite's own series sometimes jumps while the raw bar
                        # does not. Copying that jump invents a move.
                        if abs(raw_ret) <= 0.25 and (adjusted_ret < -0.40 or adjusted_ret > 0.80):
                            factor = None
                            observed = None
                elif use_bar:
                    factor = bar_factor
                    source = "bar"
                    estimated = bar_estimated
                    observed = "bar"
                if observed is None:
                    factor, source = choose_factor(None, nse_factor, published, adjacent)
                    if factor is None and bar_factor is not None:
                        factor = bar_factor
                        source = "bar"
                        estimated = bar_estimated
                    factor, source = choose_factor(None, nse_factor, published, adjacent)
                    if factor is None and bar_factor is not None:
                        factor = bar_factor
                        source = "bar"
                        estimated = bar_estimated
            else:
                factor = action_factor(
                    close[i - 1], prev[i], opens[i], highs[i], lows[i], close[i], adjacent)
                source = "bar"
            if factor is None:
                continue
            factors[i] = factor
            # A Kite move under 5% is rounding or an ordinary dividend. It is
            # applied so the daily return matches, and it is not a corporate action.
            if source == "kite" and abs(factor - 1.0) < 0.05:
                continue
            actions.append({
                "date": calendar[idx[i]],
                "isin": isin,
                "symbol": symbols[bucket["sym"][i]],
                "factor": factor,
                "source": source,
                "estimated": estimated,
            })
        scale_running = 1.0
        scale = [1.0] * n
        for i in range(n - 1, -1, -1):
            scale[i] = scale_running
            scale_running *= factors[i]
        opens = array.array("d")
        closes = array.array("d")
        for i in range(n):
            opens.append(bucket["o"][i] * scale[i])
            closes.append(close[i] * scale[i])
        adjusted[isin] = {
            "idx": bucket["idx"],
            "sym": bucket["sym"],
            "o": opens,
            "c": closes,
            "to": bucket["to"],
        }
    actions.sort(key=lambda item: (item["date"], item["isin"]))
    return adjusted, actions


def universes_from_store(series, calendar):
    """Top 200 and top 500 on the first session of each month."""
    buckets = [[] for _ in calendar]
    for isin, bucket in series.items():
        idx = bucket["idx"]
        for i in range(len(idx)):
            buckets[idx[i]].append((isin, i))
    history = {}
    out = {200: {}, 500: {}}
    seen = set()
    for session, day in enumerate(calendar):
        traders = buckets[session]
        month = (day.year, day.month)
        if month not in seen and traders:
            seen.add(month)
            ranked = []
            for isin, pos in traders:
                prior = history.get(isin)
                if prior is None or len(prior) < LOOKBACK:
                    continue
                ranked.append((statistics.median(prior[-LOOKBACK:]), isin))
            ranked.sort(key=lambda item: (-item[0], item[1]))
            ordered = [isin for _median, isin in ranked]
            out[200][day] = ordered[:200]
            out[500][day] = ordered[:500]
        for isin, pos in traders:
            history.setdefault(isin, []).append(series[isin]["to"][pos])
    return out


def symbol_changes_store(series, symbols, calendar):
    found = []
    for isin in sorted(series):
        bucket = series[isin]
        previous = None
        for i in range(len(bucket["idx"])):
            symbol = symbols[bucket["sym"][i]]
            if previous is not None and symbol != previous:
                found.append({
                    "isin": isin,
                    "date": calendar[bucket["idx"][i]],
                    "old": previous,
                    "new": symbol,
                })
            previous = symbol
    return found


def _drop_unlisted(series, symbols, dropped):
    """Remove any series that is not an INE equity. Returns the symbols kept."""
    surviving = set()
    for isin in list(series):
        if listed_equity(isin):
            for sid in series[isin]["sym"]:
                surviving.add(symbols[sid])
            continue
        for sid in series[isin]["sym"]:
            dropped.add(symbols[sid])
        del series[isin]
    for name in list(dropped):
        if name in surviving:
            dropped.discard(name)
    return surviving


def load_action_index(actions_root):
    """Parsed NSE actions keyed by ('isin', isin, date) and ('sym', symbol, date)."""
    from india.nse_archive import combine_purpose
    from india.nse_archive import parse_purpose
    groups = {}
    unknown = {}
    if not actions_root or not os.path.isdir(actions_root):
        return {}, unknown
    for name in sorted(os.listdir(actions_root)):
        if not name.endswith(".csv.gz"):
            continue
        path = os.path.join(actions_root, name)
        with gzip.open(path, "rt", encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                parsed = parse_purpose(row.get("purpose") or "")
                if not parsed["readable"]:
                    text = parsed["purpose"]
                    unknown[text] = unknown.get(text, 0) + 1
                day_text = row.get("date") or ""
                if len(day_text) < 10:
                    continue
                day = datetime.date.fromisoformat(day_text[:10])
                isin = (row.get("isin") or "").strip()
                symbol = (row.get("symbol") or "").strip()
                if isin.startswith("INE"):
                    groups.setdefault(("isin", isin, day), []).append(parsed)
                if symbol:
                    groups.setdefault(("sym", symbol, day), []).append(parsed)
    combined = {}
    for key, parts in groups.items():
        combined[key] = combine_purpose(parts)
    return combined, unknown


def load_kite_day(kite_root):
    """Adjusted closes for the Kite day-file names, excluding index files."""
    from india.nse_archive import stock_symbols
    found = {}
    if not kite_root or not os.path.isdir(os.path.join(kite_root, "day")):
        return found
    for symbol in stock_symbols(kite_root):
        path = os.path.join(kite_root, "day", symbol + ".csv.gz")
        if not os.path.isfile(path):
            continue
        closes = {}
        for text, close in _kite_closes(path).items():
            closes[datetime.date.fromisoformat(text)] = close
        found[symbol] = closes
    return found


def build_store(cm_root, log=None, actions_root=None, kite_root=None):
    """The cached panel. Equity ISINs only, adjusted from Kite and NSE actions."""
    calendar, symbols, raw, dropped = load_store(cm_root, log=log)
    if not calendar:
        return None
    if log:
        log("raw isins %d" % len(raw))
    stitches = stitch_store(raw, symbols, calendar)
    surviving = _drop_unlisted(raw, symbols, dropped)
    if log:
        log("stitches %d" % len(stitches))
        log("equity filter removed %d symbols" % len(dropped))
        log("GOLDBEES %s" % ("gone" if "GOLDBEES" not in surviving else "still present"))
        log("NIFTYBEES %s" % ("gone" if "NIFTYBEES" not in surviving else "still present"))
    parent = os.path.dirname(cm_root)
    if actions_root is None:
        actions_root = os.path.join(parent, "actions")
    if kite_root is None:
        kite_root = os.path.join(os.path.dirname(parent), "kite")
    actions_index, unknown = load_action_index(actions_root)
    if log:
        log("nse action keys %d" % len(actions_index))
        for text, count in sorted(unknown.items(), key=lambda item: (-item[1], item[0])):
            log("unreadable purpose %d %s" % (count, text))
    kite_by_symbol = load_kite_day(kite_root)
    if log:
        log("kite names %d" % len(kite_by_symbol))
    series, actions = adjust_store(raw, symbols, calendar, actions_index, kite_by_symbol)
    if log:
        log("adjusting done, actions %d" % len(actions))
    universe = universes_from_store(series, calendar)
    last = {}
    for isin, bucket in series.items():
        if len(bucket["idx"]):
            last[isin] = calendar[bucket["idx"][-1]]
    return {
        "version": PANEL_VERSION,
        "calendar": calendar,
        "symbols": symbols,
        "series": series,
        "actions": actions,
        "stitches": stitches,
        "changes": symbol_changes_store(series, symbols, calendar),
        "last": last,
        "universe": universe,
    }


def _isin_for_symbol(panel, symbol):
    if "series" in panel and "symbols" in panel:
        best = None
        best_n = -1
        symbols = panel["symbols"]
        for isin, bucket in panel["series"].items():
            count = 0
            for sid in bucket["sym"]:
                if symbols[sid] == symbol:
                    count += 1
            if count > best_n:
                best = isin
                best_n = count
        if best_n <= 0:
            return None
        return best
    best = None
    best_n = -1
    for isin, bars in panel.get("bars", {}).items():
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


def _panel_closes(panel, isin):
    """(date, adjusted close) for one ISIN."""
    if "series" in panel and isin in panel["series"]:
        bucket = panel["series"][isin]
        calendar = panel["calendar"]
        out = []
        for i in range(len(bucket["idx"])):
            out.append((calendar[bucket["idx"][i]], bucket["c"][i]))
        return out
    out = []
    for bar in panel.get("bars", {}).get(isin, []):
        out.append((bar["date"], bar.get("adj_close")))
    return out


def _year_back(day):
    try:
        return day.replace(year=day.year - 1)
    except ValueError:
        return day.replace(year=day.year - 1, day=28)


def _close_on_or_before(points, target, slack_days):
    """Last (date, close) on or before target, if it is within slack_days."""
    found = None
    for day, close in points:
        if day <= target:
            found = (day, close)
        else:
            break
    if found is None:
        return None
    if (target - found[0]).days > slack_days:
        return None
    return found


def cross_check(panel, kite_root, names=LARGE):
    """Largest level gap and largest 1-year-return gap versus Kite day closes.

    The level gap is abs(adjusted / kite - 1) in percent. The return gap is
    the absolute difference, in percentage points, between the panel's return
    over the previous calendar year and Kite's return over that same year.
    """
    rows = []
    largest = None
    largest_year = None
    for symbol in names:
        path = os.path.join(kite_root, "day", symbol + ".csv.gz")
        isin = _isin_for_symbol(panel, symbol) if panel else None
        if not panel or isin is None or not os.path.isfile(path):
            rows.append({
                "symbol": symbol, "n": 0, "gap": None, "date": None,
                "year_n": 0, "year_gap": None, "year_date": None,
            })
            continue
        kite_map = _kite_closes(path)
        kite_points = []
        for text in sorted(kite_map):
            kite_points.append((datetime.date.fromisoformat(text), kite_map[text]))
        panel_points = _panel_closes(panel, isin)
        gap = None
        when = None
        n = 0
        year_gap = None
        year_when = None
        year_n = 0
        for day, adj in panel_points:
            other = kite_map.get(day.isoformat())
            if adj is None or other is None or other == 0 or adj <= 0:
                continue
            n += 1
            pct = abs(adj / other - 1.0) * 100.0
            if gap is None or pct > gap:
                gap = pct
                when = day
            target = _year_back(day)
            panel_then = _close_on_or_before(panel_points, target, 10)
            kite_then = _close_on_or_before(kite_points, target, 10)
            if panel_then is None or kite_then is None:
                continue
            if panel_then[1] <= 0 or kite_then[1] <= 0:
                continue
            panel_ret = adj / panel_then[1] - 1.0
            kite_ret = other / kite_then[1] - 1.0
            points = abs(panel_ret - kite_ret) * 100.0
            year_n += 1
            if year_gap is None or points > year_gap:
                year_gap = points
                year_when = day
        rows.append({
            "symbol": symbol, "n": n, "gap": gap, "date": when,
            "year_n": year_n, "year_gap": year_gap, "year_date": year_when,
        })
        if gap is not None and (largest is None or gap > largest["gap"]):
            largest = {"symbol": symbol, "gap": gap, "date": when, "n": n}
        if year_gap is not None and (largest_year is None or year_gap > largest_year["gap"]):
            largest_year = {"symbol": symbol, "gap": year_gap, "date": year_when, "n": year_n}
    return {"rows": rows, "largest": largest, "largest_year": largest_year}


def actions_per_year(actions):
    counts = {}
    for action in actions:
        year = action["date"].year
        counts[year] = counts.get(year, 0) + 1
    return counts


def largest_falls(panel, count=20):
    """The most negative one-session adjusted returns. A missed split shows up here."""
    import heapq
    worst = []
    calendar = panel["calendar"]
    symbols = panel["symbols"]
    for isin, bucket in panel["series"].items():
        idx = bucket["idx"]
        close = bucket["c"]
        for i in range(1, len(idx)):
            if idx[i] != idx[i - 1] + 1:
                continue
            if close[i - 1] <= 0 or close[i] <= 0:
                continue
            ret = close[i] / close[i - 1] - 1.0
            symbol = symbols[bucket["sym"][i]]
            day = calendar[idx[i]]
            if len(worst) < count:
                heapq.heappush(worst, (-ret, day, symbol, isin))
            elif -ret > worst[0][0]:
                heapq.heapreplace(worst, (-ret, day, symbol, isin))
    rows = [(-item[0], item[1], item[2], item[3]) for item in worst]
    rows.sort()
    return rows


def _load_index(path):
    points = []
    if not os.path.isfile(path):
        return points
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            close = _float(row.get("close"))
            if close is None or close <= 0:
                continue
            points.append((datetime.date.fromisoformat(row["date"]), close))
    points.sort()
    return points


def top200_mean(panel, index_points, start, end):
    """Equal-weight mean daily return of the monthly top 200, and the index mean.

    A name contributes only when it traded the previous calendar session, so a
    gap is not treated as a one-day return. Both means are decimal returns.
    """
    import bisect
    universe = panel["universe"][200]
    members = {}
    for day, names in universe.items():
        for isin in names:
            members[isin] = True
    locate = {}
    for isin in members:
        bucket = panel["series"].get(isin)
        if bucket is None:
            continue
        locate[isin] = bucket
    rebalance_days = sorted(universe)
    book = []
    index_rets = []
    index_at = {}
    for day, close in index_points:
        index_at[day] = close
    previous_index = None
    cursor = 0
    current = []
    calendar = panel["calendar"]
    for session, day in enumerate(calendar):
        while cursor < len(rebalance_days) and rebalance_days[cursor] <= day:
            current = universe[rebalance_days[cursor]]
            cursor += 1
        if day < start or day > end:
            if day in index_at:
                previous_index = index_at[day]
            continue
        rets = []
        for isin in current:
            bucket = locate.get(isin)
            if bucket is None:
                continue
            pos = bisect.bisect_left(bucket["idx"], session)
            if pos >= len(bucket["idx"]) or bucket["idx"][pos] != session or pos == 0:
                continue
            if bucket["idx"][pos - 1] != session - 1:
                continue
            prev = bucket["c"][pos - 1]
            close = bucket["c"][pos]
            if prev <= 0 or close <= 0:
                continue
            rets.append(close / prev - 1.0)
        level = index_at.get(day)
        if rets and previous_index is not None and level is not None and previous_index > 0:
            book.append(sum(rets) / float(len(rets)))
            index_rets.append(level / previous_index - 1.0)
        if level is not None:
            previous_index = level
    if not book or not index_rets:
        return None, None, 0
    return (
        sum(book) / float(len(book)),
        sum(index_rets) / float(len(index_rets)),
        len(book),
    )


def _percentile(values, pct):
    """Nearest-rank percentile. pct is a fraction, so 0.99 is the 99th."""
    ordered = sorted(values)
    if not ordered:
        return None
    rank = int(pct * len(ordered) + 0.999999) - 1
    if rank < 0:
        rank = 0
    if rank >= len(ordered):
        rank = len(ordered) - 1
    return ordered[rank]


def _on_or_before(dates, closes, target, slack_days):
    """Close on or before target, within slack_days. dates are sorted."""
    pos = bisect.bisect_right(dates, target) - 1
    if pos < 0:
        return None
    if (target - dates[pos]).days > slack_days:
        return None
    return closes[pos]


def return_gates(panel, kite_root, names=LARGE):
    """Daily and 1-year return gaps versus Kite for the large names.

    A daily gap is our one-session return minus Kite's, in percentage points.
    The 1-year gap is the absolute difference over the previous calendar year.
    """
    daily = []
    year_gaps = []
    for symbol in names:
        path = os.path.join(kite_root, "day", symbol + ".csv.gz")
        isin = _isin_for_symbol(panel, symbol) if panel else None
        if not panel or isin is None or not os.path.isfile(path):
            continue
        kite_map = _kite_closes(path)
        bucket = panel["series"][isin]
        idx = bucket["idx"]
        dates = []
        closes = []
        for day, close in _panel_closes(panel, isin):
            dates.append(day)
            closes.append(close)
        kite_dates = []
        kite_closes = []
        for text in sorted(kite_map):
            kite_dates.append(datetime.date.fromisoformat(text))
            kite_closes.append(kite_map[text])
        for i in range(1, len(dates)):
            if idx[i] != idx[i - 1] + 1:
                continue
            prev_close = closes[i - 1]
            close = closes[i]
            kite_now = kite_map.get(dates[i].isoformat())
            kite_prev = kite_map.get(dates[i - 1].isoformat())
            if (prev_close <= 0 or close <= 0 or kite_now is None or kite_prev is None
                    or kite_prev <= 0 or kite_now <= 0):
                continue
            ours = close / prev_close - 1.0
            theirs = kite_now / kite_prev - 1.0
            daily.append({
                "symbol": symbol,
                "date": dates[i],
                "gap": (ours - theirs) * 100.0,
            })
            target = _year_back(dates[i])
            panel_then = _on_or_before(dates, closes, target, 10)
            kite_then = _on_or_before(kite_dates, kite_closes, target, 10)
            if panel_then is None or kite_then is None or panel_then <= 0 or kite_then <= 0:
                continue
            panel_ret = close / panel_then - 1.0
            kite_ret = kite_now / kite_then - 1.0
            year_gaps.append(abs(panel_ret - kite_ret) * 100.0)
    return daily, year_gaps


def unexplained_moves(panel, start, end):
    """One-session adjusted moves beyond -40% or +80% inside the monthly top 500."""
    universe = panel["universe"][500]
    rebalance = sorted(universe)
    calendar = panel["calendar"]
    symbols = panel["symbols"]
    cursor = 0
    current = []
    found = []
    for session, day in enumerate(calendar):
        while cursor < len(rebalance) and rebalance[cursor] <= day:
            current = universe[rebalance[cursor]]
            cursor += 1
        if day < start or day > end:
            continue
        for isin in current:
            bucket = panel["series"].get(isin)
            if bucket is None:
                continue
            pos = bisect.bisect_left(bucket["idx"], session)
            if pos <= 0 or pos >= len(bucket["idx"]) or bucket["idx"][pos] != session:
                continue
            if bucket["idx"][pos - 1] != session - 1:
                continue
            prev = bucket["c"][pos - 1]
            close = bucket["c"][pos]
            if prev <= 0 or close <= 0:
                continue
            ret = close / prev - 1.0
            if ret < -0.40 - 1e-4 or ret > 0.80 + 1e-4:
                found.append((day, symbols[bucket["sym"][pos]], isin, ret))
    found.sort()
    return found


def evaluate_gates(panel, kite_root, nse_root, log):
    """Print PASS or FAIL. Returns True only when every numeric gate passes."""
    ok = True
    daily, year_gaps = return_gates(panel, kite_root)
    wide = []
    worst = None
    for row in daily:
        gap = abs(row["gap"])
        if worst is None or gap > worst:
            worst = gap
        if gap > 1.0:
            wide.append(row)
    n_daily = len(daily)
    share = (len(wide) / float(n_daily)) if n_daily else 1.0
    for row in wide:
        log("daily return gap %s %s %+.2f points" % (
            row["date"].isoformat(), row["symbol"], row["gap"]))
    if n_daily and share < 0.002 and (worst is None or worst <= 5.0):
        log("gate kite daily return: PASS %d of %d days over 1 point (%.3f%%), worst %.2f points" % (
            len(wide), n_daily, share * 100.0, worst or 0.0))
    else:
        ok = False
        log("gate kite daily return: FAIL %d of %d days over 1 point (%.3f%%), worst %.2f points" % (
            len(wide), n_daily, share * 100.0, worst or 0.0))
    p99 = _percentile(year_gaps, 0.99)
    if p99 is not None and p99 < 2.0:
        log("gate kite 1-year return: PASS 99th percentile %.3f points on %d overlaps" % (
            p99, len(year_gaps)))
    else:
        ok = False
        shown = "no overlap" if p99 is None else "%.3f points on %d overlaps" % (p99, len(year_gaps))
        log("gate kite 1-year return: FAIL 99th percentile %s" % shown)
    counts = actions_per_year(panel["actions"])
    too_many = []
    busiest = None
    for year_n in sorted(counts):
        count = counts[year_n]
        log("actions %d %d" % (year_n, count))
        if busiest is None or count > busiest[1]:
            busiest = (year_n, count)
        if count >= 400:
            too_many.append(year_n)
    if too_many or busiest is None:
        ok = False
        log("gate actions per year: FAIL %s" % ", ".join(str(item) for item in too_many))
    else:
        log("gate actions per year: PASS max %d in %d" % (busiest[1], busiest[0]))
    index_path = os.path.join(nse_root, "indices", "NIFTY_200.csv.gz")
    index_points = _load_index(index_path)
    book, index_mean, n_days = top200_mean(
        panel, index_points, datetime.date(2006, 1, 1), datetime.date(2024, 12, 31))
    if book is None or index_mean is None:
        ok = False
        log("gate top 200 mean daily: FAIL no overlap")
    else:
        diff = (book - index_mean) * 100.0
        if abs(diff) <= 0.02:
            log("gate top 200 mean daily: PASS book %.4f%% index %.4f%% diff %+.4f points on %d days" % (
                book * 100.0, index_mean * 100.0, diff, n_days))
        else:
            ok = False
            log("gate top 200 mean daily: FAIL book %.4f%% index %.4f%% diff %+.4f points on %d days" % (
                book * 100.0, index_mean * 100.0, diff, n_days))
    moves = unexplained_moves(panel, datetime.date(2005, 1, 1), datetime.date(2024, 12, 31))
    log("unexplained moves %d" % len(moves))
    for day, symbol, isin, ret in moves:
        log("unexplained %s %s %s %+.2f%%" % (day.isoformat(), symbol, isin, ret * 100.0))
    if len(moves) < 20:
        log("gate unexplained moves: PASS %d" % len(moves))
    else:
        ok = False
        log("gate unexplained moves: FAIL %d" % len(moves))
    return ok


def _print_actions(actions, log):
    log("corporate actions %d" % len(actions))
    counts = {}
    for action in actions:
        source = action.get("source") or "bar"
        counts[source] = counts.get(source, 0) + 1
    for source in sorted(counts):
        log("action source %s %d" % (source, counts[source]))


def _print_histogram(actions, log):
    for row in factor_histogram(actions):
        log("factor %s count %d" % (row["label"], row["count"]))
        for action in row["examples"]:
            log("  %s %s %s %.4f" % (
                action["date"].isoformat(), action.get("symbol", ""),
                action.get("isin", ""), action["factor"]))


def _print_stitches(stitches, log):
    for row in stitches:
        log("stitch %s %s %s -> %s sessions %d" % (
            row["date"].isoformat(), row["symbol"], row["old"], row["new"], row["sessions"]))
    log("stitches %d" % len(stitches))


def _print_check(check, log):
    log("kite cross-check")
    for row in check["rows"]:
        if row["gap"] is None:
            log("%s no overlap" % row["symbol"])
        else:
            when = row["date"].isoformat() if row["date"] is not None else ""
            year = "n/a" if row["year_gap"] is None else "%.3f points" % row["year_gap"]
            log("%s sessions %d max gap %.3f%% on %s, 1-year %s" % (
                row["symbol"], row["n"], row["gap"], when, year))
    largest = check["largest"]
    if largest is None:
        log("largest gap: no overlap")
    else:
        log("largest gap %s %.3f%% on %s" % (
            largest["symbol"], largest["gap"], largest["date"].isoformat()))
    year = check.get("largest_year")
    if year is None:
        log("largest 1-year gap: no overlap")
    else:
        log("largest 1-year gap %s %.3f points on %s" % (
            year["symbol"], year["gap"], year["date"].isoformat()))


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(description="Build the survivorship-free panel. Nothing is ordered.")
    parser.add_argument("--nse", default=os.path.join("data", "nse"))
    parser.add_argument("--kite", default=os.path.join("data", "kite"))
    parser.add_argument("--cache", default=os.path.join("data", "cache"))
    args = parser.parse_args(argv)
    log = lambda line: print(line, flush=True)
    panel = build_store(os.path.join(args.nse, "cm"), log=log)
    if not panel:
        log("corporate actions 0")
        log("no cash bhavcopy on disk")
        log("kite cross-check: no cash bhavcopy on disk")
        log("largest gap: no overlap")
        log("gate kite daily gap: FAIL no cash bhavcopy")
        return 2
    save_panel(panel, args.cache)
    _print_stitches(panel["stitches"], log)
    _print_actions(panel["actions"], log)
    _print_histogram(panel["actions"], log)
    log("symbol changes %d" % len(panel["changes"]))
    log("isins %d" % len(panel["series"]))
    passed = evaluate_gates(panel, args.kite, args.nse, log)
    return 0 if passed else 2


if __name__ == "__main__":
    sys.exit(main())
