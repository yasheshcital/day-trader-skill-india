"""GOLDBEES as the gold sleeve. Standard library only.

Raw EQ closes from data/nse/cm, from the first day. The only adjustment is
the unit split in the NSE actions file. Dividends and bonuses are left in
the price. The ETF price is already net of its charges, so this series has
no expense ratio.

The equities corporate-actions files do not list this ETF. NSE's mutual-fund
feed does: ex-date 2019-12-19, face value Rs 100 to Rs 1, series EQ and BL.
https://www.nseindia.com/api/corporates-corporateActions?index=mf&symbol=GOLDBEES
That EQ row is copied into data/nse/actions/2019.csv.gz when it is missing,
and the series is then read back from the actions file.
"""

import csv
import datetime
import gzip
import io
import os
import re
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from india.nse_archive import _SPLIT_LOOSE
from india.nse_archive import _SPLIT_PAIR
from india.nse_archive import _SPLIT_WORD
from india.research import invest

# The share-wording patterns miss "Per Unit" and "Re 1". NSE writes both.
_PER_UNIT = re.compile(
    r"r(?:s\.?|e\.?)\s*([0-9]+(?:\.[0-9]+)?)\s*/-\s*per\s+unit\s+to\s*"
    r"(?:r(?:s\.?|e\.?)\s*)?([0-9]+(?:\.[0-9]+)?)",
    re.I)

SYMBOL = "GOLDBEES"
SERIES = "EQ"
# Official mutual-fund corporate action. One row, one ex-date.
SPLIT_ROW = {
    "date": "2019-12-19",
    "symbol": "GOLDBEES",
    "series": "EQ",
    "isin": "INF732E01102",
    "purpose": "Face Value Split (Sub-Division) - From Rs 100/- To Rs 1/-",
}


def unit_split_factor(purpose):
    """New face over old face. None when the line is not a face-value split.

    A bonus and a dividend do not change the factor. Two splits in one line
    multiply.
    """
    raw = (purpose or "").strip()
    if raw == "" or _SPLIT_WORD.search(raw) is None:
        return None
    pairs = _SPLIT_PAIR.findall(raw) or _SPLIT_LOOSE.findall(raw) or _PER_UNIT.findall(raw)
    factor = 1.0
    have = False
    for old_face, new_face in pairs:
        old_value = float(old_face)
        if old_value <= 0:
            continue
        factor *= float(new_face) / old_value
        have = True
    if not have:
        return None
    return factor


def split_events(rows):
    """Ex-date to factor for GOLDBEES series EQ. One factor per date.

    A second line on the same ex-date with the same factor (the BL row) is
    not applied again.
    """
    found = {}
    for row in rows:
        if (row.get("symbol") or "").strip() != SYMBOL:
            continue
        if (row.get("series") or "").strip() != SERIES:
            continue
        factor = unit_split_factor(row.get("purpose") or "")
        if factor is None:
            continue
        text = (row.get("date") or "")[:10]
        if len(text) < 10:
            continue
        day = datetime.date.fromisoformat(text)
        previous = found.get(day)
        if previous is None:
            found[day] = factor
        elif abs(previous - factor) > 1e-12:
            found[day] = previous * factor
    return found


def apply_unit_splits(points, events):
    """Scale closes from before each ex-date into the new units.

    The ex-date itself keeps the raw close. Prices after it are already on
    the new face value.
    """
    if not events:
        return list(points)
    out = []
    for day, close in points:
        scale = 1.0
        for ex_date, factor in events.items():
            if day < ex_date:
                scale *= factor
        out.append((day, close * scale))
    return out


def _read_action_rows(actions_root):
    rows = []
    if not actions_root or not os.path.isdir(actions_root):
        return rows
    for name in sorted(os.listdir(actions_root)):
        if not name.endswith(".csv.gz"):
            continue
        path = os.path.join(actions_root, name)
        with gzip.open(path, "rt", encoding="utf-8", newline="") as fh:
            for row in csv.DictReader(fh):
                rows.append(row)
    return rows


def read_split_events(actions_root):
    return split_events(_read_action_rows(actions_root))


def ensure_split(actions_root, log=None):
    """Copy the mutual-fund split into the 2019 actions file when it is absent."""
    log = log or (lambda line: None)
    rows = _read_action_rows(actions_root)
    if split_events(rows):
        log("GOLDBEES unit split already in the actions file")
        return False
    path = os.path.join(actions_root, "2019.csv.gz")
    existing = []
    header = ("date", "symbol", "series", "isin", "purpose")
    if os.path.isfile(path):
        with gzip.open(path, "rt", encoding="utf-8", newline="") as fh:
            reader = csv.DictReader(fh)
            if reader.fieldnames:
                header = tuple(reader.fieldnames)
            for row in reader:
                existing.append(row)
    existing.append(dict(SPLIT_ROW))
    buf_rows = []
    for row in existing:
        buf_rows.append(tuple((row.get(name) or "") for name in header))
    handle = io.StringIO()
    writer = csv.writer(handle, lineterminator="\n")
    writer.writerow(header)
    for record in buf_rows:
        writer.writerow(record)
    folder = os.path.dirname(path)
    if folder and not os.path.isdir(folder):
        os.makedirs(folder)
    with gzip.open(path, "wt", encoding="utf-8", newline="") as fh:
        fh.write(handle.getvalue())
    log("GOLDBEES unit split copied into %s from the mutual-fund feed" % path)
    return True


def read_goldbees(cm_root):
    """Raw GOLDBEES EQ closes, first day through the last file."""
    found = {}
    if not cm_root or not os.path.isdir(cm_root):
        return []
    for name in sorted(os.listdir(cm_root)):
        if not name.endswith(".csv.gz"):
            continue
        file_day = name[:10]
        try:
            day = datetime.date.fromisoformat(file_day)
        except ValueError:
            continue
        if day.year < 1990:
            continue
        # One file is one session. The 2020-07-13 file dates its row 0020-07-13,
        # so a year before 1990 is ignored and the file name is the session.
        path = os.path.join(cm_root, name)
        with gzip.open(path, "rt", encoding="utf-8", newline="") as fh:
            for row in csv.DictReader(fh):
                if (row.get("symbol") or "").strip() != SYMBOL:
                    continue
                if (row.get("series") or "").strip() != SERIES:
                    continue
                text = (row.get("date") or "")[:10]
                if len(text) >= 10:
                    try:
                        row_day = datetime.date.fromisoformat(text)
                    except ValueError:
                        row_day = None
                    if row_day is not None and row_day.year >= 1990 and row_day != day:
                        continue
                try:
                    close = float(row.get("close") or "")
                except ValueError:
                    continue
                if close <= 0:
                    continue
                found[day] = close
    return sorted(found.items())


def write_series(path, points):
    folder = os.path.dirname(path)
    if folder and not os.path.isdir(folder):
        os.makedirs(folder)
    lines = ["date,close\n"]
    for day, close in points:
        text = ("%.6f" % close).rstrip("0").rstrip(".")
        lines.append("%s,%s\n" % (day.isoformat(), text))
    with gzip.open(path, "wt", encoding="utf-8", newline="") as fh:
        fh.write("".join(lines))


def series_cagr(points):
    if len(points) < 2:
        return None
    return invest._cagr(points[0][1], points[-1][1], points[0][0], points[-1][0])


def build(nse_root, log=None):
    """Write indices/GOLD_ETF.csv.gz and return the split-adjusted points."""
    log = log or (lambda line: print(line, flush=True))
    ensure_split(os.path.join(nse_root, "actions"), log)
    events = read_split_events(os.path.join(nse_root, "actions"))
    raw = read_goldbees(os.path.join(nse_root, "cm"))
    points = apply_unit_splits(raw, events)
    path = os.path.join(nse_root, "indices", "GOLD_ETF.csv.gz")
    write_series(path, points)
    if points:
        log("GOLD_ETF first %s close %s" % (points[0][0].isoformat(), ("%.4f" % points[0][1])))
        log("GOLD_ETF last %s close %s" % (points[-1][0].isoformat(), ("%.4f" % points[-1][1])))
        log("GOLD_ETF CAGR %s" % _pct(series_cagr(points)))
        log("GOLD_ETF splits %s" % ", ".join(
            "%s x%s" % (day.isoformat(), ("%.4f" % factor).rstrip("0").rstrip("."))
            for day, factor in sorted(events.items())
        ))
    else:
        log("GOLD_ETF has no rows")
    return points


def _pct(value):
    if value is None:
        return "n/a"
    return "%+.2f%%" % (value * 100.0)


def main(argv=None):
    root = os.path.join(_ROOT, "data", "nse")
    if argv:
        root = argv[0]
    build(root)
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main(sys.argv[1:]))
