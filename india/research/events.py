"""Build data/nse/events.csv. Nothing is ordered. No bhavcopy read.

Columns: date, kind, symbol, source. Symbol is blank for a market-wide row.

Kinds:
  results           first session whose 09:15 is strictly after the announcement
  rbi               MPC resolution day, mapped onto a session
  budget            Union Budget speech day, mapped onto a session
  expiry-monthly    last Thursday through 2025-08-31, last Tuesday after
  expiry-weekly     Thursday through 2025-08-31, Tuesday after, and not monthly
  rebalance         last NIFTY session of March and of September

A continuous futures file contributes a date only when it has an expiry
column. The Kite files do not, so the weekday rule supplies the dates.
A scheduled expiry on a holiday moves to the previous trading day.
Monthly wins when a date is in both sets.
"""

import bisect
import csv
import datetime
import gzip
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from india import nse_archive
from india.research import data
from india.research import nse_holidays

# Last day of each MPC meeting, when the resolution is published.
# Through March 2020: RBI "Monetary Policy Committee Voting Pattern" table,
# https://rbi.org.in/scripts/PublicationsView.aspx?id=20344
# Later years: the meeting schedule and the resolution press releases on
# rbi.org.in. 2025-26 schedule: press release 23 May 2025 (prid 60062),
# last days 9 Apr, 6 Jun, 7 Aug, 1 Oct, 5 Dec 2025 and 6 Feb 2026.
# 2026-27 schedule: press release 23 Mar 2026 (prid 62422).
# August 2025 is the 7th, the last day of the 5-7 August meeting.
RBI_DECISIONS = (
    "2016-10-04", "2016-12-07",
    "2017-02-08", "2017-04-06", "2017-06-07", "2017-08-02", "2017-10-04", "2017-12-06",
    "2018-02-07", "2018-04-05", "2018-06-06", "2018-08-01", "2018-10-05", "2018-12-05",
    "2019-02-07", "2019-04-04", "2019-06-06", "2019-08-07", "2019-10-04", "2019-12-05",
    "2020-02-06", "2020-03-27", "2020-05-22", "2020-08-06", "2020-10-09", "2020-12-04",
    "2021-02-05", "2021-04-07", "2021-06-04", "2021-08-06", "2021-10-08", "2021-12-08",
    "2022-02-10", "2022-04-08", "2022-05-04", "2022-06-08", "2022-08-05", "2022-09-30",
    "2022-12-07",
    "2023-02-08", "2023-04-06", "2023-06-08", "2023-08-10", "2023-10-06", "2023-12-08",
    "2024-02-08", "2024-04-05", "2024-06-07", "2024-08-08", "2024-10-09", "2024-12-06",
    "2025-02-07", "2025-04-09", "2025-06-06", "2025-08-07", "2025-10-01", "2025-12-05",
    "2026-02-06", "2026-04-08", "2026-06-05", "2026-08-05", "2026-10-07", "2026-12-04",
    "2027-02-05",
)
RBI_SOURCE = "RBI MPC resolution, rbi.org.in"

# Speech dates. indiabudget.gov.in. A date that is not a session is mapped
# onto the next session when that session is within four calendar days.
# 2014 and 2019 and 2024 have an interim speech and a full speech.
BUDGET_DATES = (
    "2010-02-26", "2011-02-28", "2012-03-16", "2013-02-28",
    "2014-02-17", "2014-07-10",
    "2015-02-28", "2016-02-29", "2017-02-01", "2018-02-01",
    "2019-02-01", "2019-07-05",
    "2020-02-01", "2021-02-01", "2022-02-01", "2023-02-01",
    "2024-02-01", "2024-07-23",
    "2025-02-01", "2026-02-01",
)
BUDGET_SOURCE = "Union Budget speech, indiabudget.gov.in"

# NSE Nifty 50 semi-annual reconstitution is effective the last working day
# of March and of September. https://niftyindices.com reconstitution calendar.
REBALANCE_SOURCE = "Nifty 50 semi-annual reconstitution, last session of March and September, niftyindices.com"

OPEN_TIME = datetime.time(9, 15)
# Last day the NIFTY weekly and monthly expiry is a Thursday.
# Tuesday from the next session. NSE circular, effective 1 September 2025.
CUTOFF = datetime.date(2025, 8, 31)
THURSDAY = 3
TUESDAY = 1
RULE_SOURCE = (
    "weekday rule, Thursday through 2025-08-31 then Tuesday, "
    "previous trading day on a holiday"
)
FILE_SOURCE = "continuous futures file, expiry column"
# A clock time the feed did not give. 15:30 is after the open, so the results
# day is the next session. The clock time is not invented as a real announcement.
MISSING_TIME = datetime.time(15, 30)
MAP_DAYS = 4

RESULTS_SOURCE = "NSE financial results broadcast"
ANNOUNCE_SOURCE = "NSE announcement, financial results"


def nifty_sessions(kite_root):
    """Session dates in the NIFTY 50 daily file. No holdout log."""
    found = []
    seen = set()
    for row in data.read_daily_bars(kite_root, "NIFTY 50"):
        day = row.get("date")
        if not isinstance(day, datetime.date):
            continue
        if day in seen:
            continue
        seen.add(day)
        found.append(day)
    found.sort()
    return found


def _parse_stamp(text):
    text = (text or "").strip()
    if not text:
        return None
    parts = text.split()
    iso = nse_archive.parse_nse_date(parts[0])
    if not iso:
        return None
    day = datetime.date.fromisoformat(iso)
    if len(parts) < 2 or ":" not in parts[1]:
        return datetime.datetime.combine(day, MISSING_TIME)
    clock = parts[1].split(":")
    try:
        hour = int(clock[0])
        minute = int(clock[1])
        second = int(clock[2]) if len(clock) > 2 else 0
    except ValueError:
        return datetime.datetime.combine(day, MISSING_TIME)
    return datetime.datetime(day.year, day.month, day.day, hour, minute, second)


def first_session_after(stamp, sessions):
    """First session whose 09:15 is strictly after `stamp`."""
    if stamp is None or not sessions:
        return None
    i = bisect.bisect_left(sessions, stamp.date())
    while i < len(sessions):
        open_at = datetime.datetime.combine(sessions[i], OPEN_TIME)
        if open_at > stamp:
            return sessions[i]
        i += 1
    return None


def on_session(day, sessions):
    """The day itself when it is a session, else the next session within 4 days."""
    i = bisect.bisect_left(sessions, day)
    if i >= len(sessions):
        return None
    if sessions[i] == day:
        return day
    if (sessions[i] - day).days <= MAP_DAYS:
        return sessions[i]
    return None


def _expiry_weekday(day):
    if day <= CUTOFF:
        return THURSDAY
    return TUESDAY


def _settle(day, holidays):
    """The day itself, or the previous weekday that is not a holiday."""
    cursor = day
    while cursor.weekday() >= 5 or cursor in holidays:
        cursor -= datetime.timedelta(days=1)
    return cursor


def _last_weekday(year, month, weekday):
    if month == 12:
        day = datetime.date(year, 12, 31)
    else:
        day = datetime.date(year, month + 1, 1) - datetime.timedelta(days=1)
    while day.weekday() != weekday:
        day -= datetime.timedelta(days=1)
    return day


def _monthly_scheduled(year, month):
    last_thu = _last_weekday(year, month, THURSDAY)
    if last_thu <= CUTOFF:
        return last_thu
    return _last_weekday(year, month, TUESDAY)


def rule_expiries(start, end, holidays):
    """(monthly set, weekly set) of dates. Monthly is removed from weekly."""
    closed = set(holidays)
    monthly = set()
    weekly = set()
    day = start
    while day <= end:
        if day.weekday() == _expiry_weekday(day):
            weekly.add(_settle(day, closed))
        day += datetime.timedelta(days=1)
    year = start.year
    month = start.month
    while True:
        chosen = _monthly_scheduled(year, month)
        if start <= chosen <= end:
            monthly.add(_settle(chosen, closed))
        if year == end.year and month == end.month:
            break
        if month == 12:
            year += 1
            month = 1
        else:
            month += 1
    weekly -= monthly
    return monthly, weekly


def futures_expiries(folder):
    """Dates from an expiry column. Files without that column add nothing."""
    found = set()
    if not folder or not os.path.isdir(folder):
        return found
    for name in sorted(os.listdir(folder)):
        if not name.endswith(".csv.gz"):
            continue
        path = os.path.join(folder, name)
        with gzip.open(path, "rt", encoding="utf-8", newline="") as fh:
            header = fh.readline()
        if "expiry" not in header.lower():
            continue
        with gzip.open(path, "rt", encoding="utf-8", newline="") as fh:
            for cell in csv.DictReader(fh):
                key = None
                for name_key in cell:
                    if name_key and name_key.strip().lower() == "expiry":
                        key = name_key
                        break
                if key is None:
                    continue
                iso = nse_archive.parse_nse_date((cell.get(key) or "").strip())
                if not iso:
                    text = (cell.get(key) or "").strip()
                    if len(text) >= 10 and text[4] == "-" and text[7] == "-":
                        iso = text[:10]
                if not iso:
                    continue
                try:
                    found.add(datetime.date.fromisoformat(iso))
                except ValueError:
                    continue
    return found


def _dated(text):
    iso = nse_archive.parse_nse_date(text)
    if not iso:
        return None
    return datetime.date.fromisoformat(iso)


def _results(nse_root, sessions):
    """One row per symbol per results session. Broadcasts win over announcements."""
    found = {}

    def add(symbol, stamp, source):
        day = first_session_after(stamp, sessions)
        if day is None or not symbol:
            return
        key = (day, symbol)
        if key in found:
            return
        found[key] = source

    results_dir = os.path.join(nse_root, "results")
    if os.path.isdir(results_dir):
        for name in sorted(os.listdir(results_dir)):
            if not name.endswith(".csv.gz"):
                continue
            symbol = name[:-len(".csv.gz")]
            with gzip.open(os.path.join(results_dir, name), "rt", encoding="utf-8", newline="") as fh:
                for cell in csv.DictReader(fh):
                    add(symbol, _parse_stamp(cell.get("broadcast") or ""), RESULTS_SOURCE)
    announce_dir = os.path.join(nse_root, "announcements")
    if os.path.isdir(announce_dir):
        for name in sorted(os.listdir(announce_dir)):
            if not name.endswith(".csv.gz"):
                continue
            symbol = name[:-len(".csv.gz")]
            with gzip.open(os.path.join(announce_dir, name), "rt", encoding="utf-8", newline="") as fh:
                for cell in csv.DictReader(fh):
                    add(symbol, _parse_stamp(cell.get("announced") or ""), ANNOUNCE_SOURCE)
    rows = []
    for (day, symbol), source in sorted(found.items()):
        rows.append((day, "results", symbol, source))
    return rows


def rebalance_dates(sessions):
    """Last session of March and of September, from 2010 on."""
    last = {}
    for day in sessions:
        if day.year < 2010 or day.month not in (3, 9):
            continue
        key = (day.year, day.month)
        if key not in last or day > last[key]:
            last[key] = day
    return sorted(last.values())


def build(nse_root, sessions, out_path, futures_dir=None):
    """Write events.csv. `sessions` is the NIFTY session calendar, oldest first."""
    sessions = sorted(sessions)
    rows = []
    if sessions:
        start, end = sessions[0], sessions[-1]
    else:
        start, end = datetime.date(2010, 1, 1), datetime.date.today()
    holidays = []
    for key in nse_holidays.HOLIDAYS:
        holidays.append(datetime.date.fromisoformat(key))
    monthly, weekly = rule_expiries(start, end, holidays)
    from_file = futures_expiries(futures_dir)
    file_only = []
    for day in sorted(from_file):
        if day in monthly or day in weekly:
            continue
        file_only.append(day)
        weekly.add(day)
    for day in sorted(monthly):
        rows.append((day, "expiry-monthly", "", RULE_SOURCE))
    for day in sorted(weekly):
        if day in file_only:
            source = FILE_SOURCE
        else:
            source = RULE_SOURCE
        rows.append((day, "expiry-weekly", "", source))
    for iso in RBI_DECISIONS:
        day = on_session(datetime.date.fromisoformat(iso), sessions)
        if day is None:
            continue
        rows.append((day, "rbi", "", RBI_SOURCE))
    for iso in BUDGET_DATES:
        day = on_session(datetime.date.fromisoformat(iso), sessions)
        if day is None:
            continue
        rows.append((day, "budget", "", BUDGET_SOURCE))
    for day in rebalance_dates(sessions):
        rows.append((day, "rebalance", "", REBALANCE_SOURCE))
    rows.extend(_results(nse_root, sessions))
    rows.sort(key=lambda item: (item[0], item[1], item[2]))
    folder = os.path.dirname(out_path)
    if folder:
        os.makedirs(folder, exist_ok=True)
    tmp = out_path + ".part"
    with open(tmp, "w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh, lineterminator="\n")
        writer.writerow(("date", "kind", "symbol", "source"))
        for day, kind, symbol, source in rows:
            writer.writerow((day.isoformat(), kind, symbol, source))
    os.replace(tmp, out_path)
    return rows


def read_events(path):
    out = []
    with open(path, encoding="utf-8", newline="") as fh:
        for cell in csv.DictReader(fh):
            out.append({
                "date": datetime.date.fromisoformat(cell["date"]),
                "kind": cell.get("kind") or "",
                "symbol": cell.get("symbol") or "",
                "source": cell.get("source") or "",
            })
    return out


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(description="Build data/nse/events.csv. Nothing is ordered.")
    parser.add_argument("--nse", default=os.path.join("data", "nse"))
    parser.add_argument("--kite", default=os.path.join("data", "kite"))
    parser.add_argument("--futures", default=os.path.join("data", "kite", "futures", "day"))
    parser.add_argument("--out", default="")
    args = parser.parse_args(argv)
    out = args.out or os.path.join(args.nse, "events.csv")
    sessions = nifty_sessions(args.kite)
    rows = build(args.nse, sessions, out, args.futures)
    counts = {}
    for _day, kind, _symbol, _source in rows:
        counts[kind] = counts.get(kind, 0) + 1
    print("events %d written to %s" % (len(rows), out), flush=True)
    for kind in sorted(counts):
        print("%s %d" % (kind, counts[kind]), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
