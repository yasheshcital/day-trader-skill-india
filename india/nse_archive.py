"""Resumable NSE archive downloader. Standard library only.

Nothing here calls Kite or AlgoTest. One request per second, a browser
User-Agent, a 20-second timeout, at most 3 tries with backoff, and a 60-second
pause after 5 failures in a row. Each file is saved and recorded in the
progress file as soon as it arrives. A file that is already on disk and not
empty is skipped. A trading day the archive does not have is recorded as
missing and is not requested again.

Run one part at a time, from Terminal, not from Cursor:

  caffeinate -i python3 india/nse_archive.py --only participant
  caffeinate -i python3 india/nse_archive.py --only vix
  caffeinate -i python3 india/nse_archive.py --only results
  caffeinate -i python3 india/nse_archive.py --only bhavcopy

Output lives under data/nse/ and is gitignored:

  fo/YYYY-MM-DD.csv.gz            normalised F&O bhavcopy
  participant/YYYY-MM-DD.csv.gz   participant-wise open interest, raw
  vix/YYYY-MM-DD.csv.gz           India VIX line from that day's index file
  vix.csv                         those lines joined, date, open, high, low, close
  results/SYMBOL.csv.gz           quarterly financial-results broadcasts
  board/SYMBOL.csv.gz             board-meeting intimations
  announcements/SYMBOL.csv.gz     2025 onward, financial-results outcomes
  holidays/trading.json.gz        the holiday-master payload
  cm/YYYY-MM-DD.csv.gz            cash bhavcopy, EQ and BE, from 2005
  delivery/YYYY-MM-DD.csv.gz      deliverable quantity and percent
  indices/<slug>.csv.gz           daily closes, price or total return
  actions/YYYY.csv.gz             corporate actions, one year, equities
  progress.json                   ok or missing for the original jobs
  progress-cm.json                cash bhavcopy, its own file
  progress-delivery.json          delivery, its own file
  progress-indices.json           index history, its own file
  progress-actions.json           corporate actions, its own file

Cash, delivery and the index history each keep a separate progress file so
those three jobs can run at the same time. The original jobs stay on
progress.json.

  caffeinate -i python3 india/nse_archive.py --only cm
  caffeinate -i python3 india/nse_archive.py --only delivery
  caffeinate -i python3 india/nse_archive.py --only indices
  caffeinate -i python3 india/nse_archive.py --only actions
"""

import csv
import datetime
import decimal
import gzip
import http.client
import io
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from india.research import data
from india.research import nse_holidays

# Through 5 July 2024 the archive is the old foDDMONYYYYbhav.csv.zip file.
# From 8 July 2024 it is the UDiFF bhavcopy. 6 and 7 July 2024 are not sessions.
OLD_LAST = datetime.date(2024, 7, 5)
BHAV_START = datetime.date(2010, 1, 1)
PARTICIPANT_START = datetime.date(2012, 1, 1)
# ind_close_all returns 404 for 2010-2012. India VIX is in the file from 2013.
VIX_START = datetime.date(2013, 1, 1)
RESULTS_FROM = "01-01-2010"
ANNOUNCE_FROM = datetime.date(2025, 1, 1)
# Cash bhavcopy and delivery. The holiday list starts in 2010, so a weekday
# before that is requested, and a 404 is recorded missing.
CM_START = datetime.date(2005, 1, 1)
INDEX_START = datetime.date(2005, 1, 1)
# The historical-data page posts here. Backpage.aspx/getHistoricaldata now
# returns the site HTML. A name ending in " TR" is the total-return series,
# which is a second endpoint and the same index name without the suffix.
# An empty year is tried once more under the alternate name.
INDEX_URL = "https://www.niftyindices.com/BackPage/getHistoricaldatatabletoString"
INDEX_TR_URL = "https://www.niftyindices.com/BackPage/getTotalReturnIndexString"
INDEX_SERIES = (
    ("NIFTY_50", "NIFTY 50", "NIFTY 50 TRI"),
    ("NIFTY_50_TR", "NIFTY 50 TR", "NIFTY 50 TRI"),
    ("NIFTY_200", "NIFTY 200", "NIFTY 200 TRI"),
    ("NIFTY_200_TR", "NIFTY 200 TR", "NIFTY 200 TRI"),
    ("NIFTY_500", "NIFTY 500", "NIFTY 500 TRI"),
    ("NIFTY_500_TR", "NIFTY 500 TR", "NIFTY 500 TRI"),
    ("NIFTY200_MOMENTUM_30", "NIFTY200 MOMENTUM 30", "NIFTY200 MOMENTUM 30 TR"),
    ("NIFTY200_MOMENTUM_30_TR", "NIFTY200 MOMENTUM 30 TR", "NIFTY200 MOMENTUM 30 TRI"),
    ("NIFTY100_LOW_VOLATILITY_30", "NIFTY100 LOW VOLATILITY 30", "NIFTY100 LOW VOLATILITY 30 TR"),
    ("NIFTY100_LOW_VOLATILITY_30_TR", "NIFTY100 LOW VOLATILITY 30 TR", "NIFTY100 LOW VOLATILITY 30 TRI"),
    ("NIFTY_ALPHA_50", "NIFTY ALPHA 50", "NIFTY ALPHA 50 TR"),
    ("NIFTY_ALPHA_50_TR", "NIFTY ALPHA 50 TR", "NIFTY ALPHA 50 TRI"),
    ("NIFTY200_QUALITY_30", "NIFTY200 QUALITY 30", "NIFTY 200 QUALITY 30"),
    ("NIFTY200_QUALITY_30_TR", "NIFTY200 QUALITY 30 TR", "NIFTY200 QUALITY 30 TRI"),
    ("NIFTY50_VALUE_20", "NIFTY50 VALUE 20", "NIFTY 50 VALUE 20"),
    ("NIFTY50_VALUE_20_TR", "NIFTY50 VALUE 20 TR", "NIFTY50 VALUE 20 TRI"),
    ("NIFTY_MIDCAP_150", "NIFTY MIDCAP 150", "NIFTYMIDCAP 150"),
    ("NIFTY_MIDCAP_150_TR", "NIFTY MIDCAP 150 TR", "NIFTY MIDCAP 150 TRI"),
    ("NIFTY_SMALLCAP_250", "NIFTY SMALLCAP 250", "NIFTYSMALLCAP 250"),
    ("NIFTY_SMALLCAP_250_TR", "NIFTY SMALLCAP 250 TR", "NIFTY SMALLCAP 250 TRI"),
    ("NIFTY_MIDCAP150_MOMENTUM_50", "NIFTY MIDCAP150 MOMENTUM 50", "NIFTYMIDCAP150 MOMENTUM 50"),
    ("NIFTY_MIDCAP150_MOMENTUM_50_TR", "NIFTY MIDCAP150 MOMENTUM 50 TR", "NIFTY MIDCAP150 MOMENTUM 50 TRI"),
    # The 10-year benchmark G-Sec index is already a total return (coupons are
    # reinvested). It is published on the price endpoint, so the slug does not
    # end in _TR. The clean-price file is the price series.
    ("NIFTY_10YR_BENCHMARK_GSEC_CLEAN", "NIFTY 10 YR BENCHMARK G-SEC (CLEAN PRICE)", "NIFTY 10 YR BENCHMARK G-SEC CLEAN PRICE"),
    ("NIFTY_10YR_BENCHMARK_GSEC", "NIFTY 10 YR BENCHMARK G-SEC", "NIFTY 10 YR BENCHMARK GSEC"),
)
# Nifty Indices does not publish a bullion gold index. Nifty Commodities is an
# equity basket. Gold for the long-term books is the IBJA 999 fine-gold rate,
# INR per 10 grams, stored as indices/GOLD_INR.csv.gz with columns date, close.
# Source: https://www.ibja.co . It is not fetched by --only indices.
CM_SERIES = ("EQ", "BE")
CM_HEADER = (
    "date", "symbol", "series", "isin", "open", "high", "low", "close",
    "last", "prev_close", "volume", "turnover",
)
DELIVERY_HEADER = (
    "date", "symbol", "series", "deliverable_qty", "deliverable_pct",
)

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
HOSTS = ("https://nsearchives.nseindia.com", "https://archives.nseindia.com")
WARM_URL = "https://www.nseindia.com/reports-indices-historical-vix"
TIMEOUT = 20
RETRIES = 3
# Seconds to wait before the second try and the third try.
BACKOFF = (2, 4)
FAIL_STREAK = 5
FAIL_PAUSE = 60
GAP_SECONDS = 1.0
ONLY = ("bhavcopy", "participant", "vix", "results", "cm", "delivery", "indices", "actions")
COMMANDS = (
    "caffeinate -i python3 india/nse_archive.py --only participant",
    "caffeinate -i python3 india/nse_archive.py --only vix",
    "caffeinate -i python3 india/nse_archive.py --only results",
    "caffeinate -i python3 india/nse_archive.py --only bhavcopy",
    "caffeinate -i python3 india/nse_archive.py --only cm",
    "caffeinate -i python3 india/nse_archive.py --only delivery",
    "caffeinate -i python3 india/nse_archive.py --only indices",
    "caffeinate -i python3 india/nse_archive.py --only actions",
)
NEW_JOBS = ("cm", "delivery", "indices", "actions")
_PROGRESS_NAME = {
    "cm": "progress-cm.json",
    "delivery": "progress-delivery.json",
    "indices": "progress-indices.json",
    "actions": "progress-actions.json",
}
ACTIONS_HEADER = ("date", "symbol", "series", "isin", "purpose")
_CUR = r"r(?:s\.?|e\.?)"
_SPLIT_PAIR = re.compile(
    _CUR + r"\s*([0-9]+(?:\.[0-9]+)?)\s*(?:/-\s*)?(?:each\s+)?"
    r"(?:per\s+(?:share\s*)?)?(?:each\s+)?to\s*(?:face\s+value\s*)?"
    r"(?:" + _CUR + r"\s*)?([0-9]+(?:\.[0-9]+)?)",
    re.I)
_BONUS = re.compile(
    r"bon(?:us)?(?:\s+issue)?(?:\s+shares)?(?:\s+in\s+the\s+ratio\s+of)?"
    r"\s*[-:]?\s*([0-9]+(?:\.[0-9]+)?)\s*:\s*([0-9]+(?:\.[0-9]+)?)",
    re.I)
_SPLIT_LOOSE = re.compile(
    r"([0-9]+(?:\.[0-9]+)?)\s*/-\s*(?:each\s+)?to\s*(?:face\s+value\s*)?"
    r"(?:" + _CUR + r"\s*)?([0-9]+(?:\.[0-9]+)?)",
    re.I)
_SPLIT_WORD = re.compile(
    r"split|splt|\bfv\s*spl|\bspl\b|\bfv\b|face\s*val|sub-?\s*div|consolidat",
    re.I)
_DEMERGER = re.compile(r"de[\s-]*merger|scheme of arrangement|scheme of demerger|"
                       r"sch of arngment|capital reduction|composite scheme|"
                       r"return of capital|capital repayment|scheme of arangement", re.I)
_NOT_EQUITY_BONUS = re.compile(r"bonus\s+(?:debenture|ncrps|preference|dvr)", re.I)
_ADMIN = re.compile(
    r"annual general meeting|extra\s*ordinary general meeting|\bagm\b|\begm\b|"
    r"buy\s*back|buyback|book closure|interest payment",
    re.I)
_DIVIDEND = re.compile(r"dividend|intdiv|\bdiv\b", re.I)
_RIGHTS = re.compile(r"\brights?\b", re.I)

MONTHS = ("JAN", "FEB", "MAR", "APR", "MAY", "JUN",
          "JUL", "AUG", "SEP", "OCT", "NOV", "DEC")
_INDEX_MON = ("Jan", "Feb", "Mar", "Apr", "May", "Jun",
              "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
MONTH_NUMBER = {}
for _i, _name in enumerate(MONTHS):
    MONTH_NUMBER[_name] = _i + 1

SCHEMA = (
    "date", "symbol", "instrument", "expiry", "strike", "option_type",
    "open", "high", "low", "close", "settle", "contracts",
    "open_interest", "change_in_oi",
)
# The header cell keeps the space. "change in OI" is the column the rest of the step reads.
HEADER = (
    "date", "symbol", "instrument", "expiry", "strike", "option type",
    "open", "high", "low", "close", "settle", "contracts",
    "open interest", "change in OI",
)

FUTURES_OPTION = ("XX", "FF")


def trading_days(start, end):
    """Weekdays in the inclusive range that are not in nse_holidays.HOLIDAYS."""
    closed = set(nse_holidays.between(start, end))
    out = []
    day = start
    one = datetime.timedelta(days=1)
    while day <= end:
        if day.weekday() < 5 and day not in closed:
            out.append(day)
        day += one
    return out


def stock_symbols(kite_root):
    """Day-file names that are not an index. This is the 495-name universe."""
    found = []
    for symbol in data.symbols_in(kite_root):
        if symbol.startswith("NIFTY"):
            continue
        found.append(symbol)
    return found


def _num(text):
    text = (text or "").strip()
    if text == "":
        return ""
    try:
        value = decimal.Decimal(text)
    except Exception:
        return text
    return format(value.normalize(), "f")


def parse_nse_date(text):
    """ISO date from 25-Jan-2024, 25-JAN-2024, or 2024-01-25. Blank if unknown."""
    text = (text or "").strip()
    if not text or text in ("-", "0"):
        return ""
    if len(text) >= 10 and text[4] == "-" and text[7] == "-":
        return text[:10]
    parts = text.split("-")
    if len(parts) != 3:
        return ""
    month = MONTH_NUMBER.get(parts[1].upper())
    if month is None:
        return ""
    try:
        return "%04d-%02d-%02d" % (int(parts[2]), month, int(parts[0]))
    except ValueError:
        return ""


def action_years(today):
    """Calendar years from 2005 through the run's year."""
    return list(range(CM_START.year, today.year + 1))


def actions_path(root, year):
    return os.path.join(root, "actions", "%d.csv.gz" % year)


def actions_url(year, today):
    """One calendar year of the equities corporate-actions feed."""
    end_month = 12
    end_day = 31
    if year == today.year:
        end_month = today.month
        end_day = today.day
    return (
        "https://www.nseindia.com/api/corporates-corporateActions?index=equities"
        "&from_date=01-01-%d&to_date=%02d-%02d-%d" % (year, end_day, end_month, year)
    )


def parse_purpose(text):
    """Turn one NSE purpose line into a factor, or a flag for a later price ratio.

    A face-value split from Rs A to Rs B has factor B/A. Bonus X:Y (X new
    shares for every Y held) has factor Y/(X+Y). Both in one line multiply.
    A rights issue, a demerger, a scheme of arrangement, or a capital
    reduction carries no price of its own. An ordinary dividend does not adjust.
    """
    raw = (text or "").strip()
    low = raw.lower()
    out = {
        "purpose": raw,
        "factor": None,
        "rights": False,
        "demerger": False,
        "dividend": False,
        "readable": False,
    }
    if raw == "":
        return out
    demerger = _DEMERGER.search(raw) is not None
    split_words = _SPLIT_WORD.search(raw) is not None
    factor = 1.0
    have = False
    if _NOT_EQUITY_BONUS.search(raw) is None:
        for new_shares, old_shares in _BONUS.findall(raw):
            added = float(new_shares) + float(old_shares)
            if added <= 0:
                continue
            factor *= float(old_shares) / added
            have = True
    if split_words:
        pairs = _SPLIT_PAIR.findall(raw) or _SPLIT_LOOSE.findall(raw)
        for old_face, new_face in pairs:
            old_value = float(old_face)
            if old_value <= 0:
                continue
            factor *= float(new_face) / old_value
            have = True
    dividend = _DIVIDEND.search(raw) is not None or "interest payment" in low
    if "distribution" in low and not demerger:
        dividend = True
    rights = _RIGHTS.search(raw) is not None
    known = have or demerger or rights or dividend or _ADMIN.search(raw) is not None
    equity_bonus = re.search(r"\bbon(?:us)?\b", low) is not None and _NOT_EQUITY_BONUS.search(raw) is None
    if equity_bonus and not _BONUS.search(raw):
        known = False
    if split_words and not _SPLIT_PAIR.search(raw) and not _SPLIT_LOOSE.search(raw):
        known = False
    out["factor"] = factor if have else None
    out["rights"] = rights
    out["demerger"] = demerger
    out["dividend"] = dividend
    out["readable"] = known
    return out


def combine_purpose(parts):
    """Multiply split and bonus factors that share an ex-date."""
    factor = 1.0
    have = False
    rights = False
    demerger = False
    for part in parts:
        if part.get("factor") is not None:
            factor *= part["factor"]
            have = True
        if part.get("rights"):
            rights = True
        if part.get("demerger"):
            demerger = True
    return {
        "factor": factor if have else None,
        "rights": rights,
        "demerger": demerger,
    }


def parse_actions(payload):
    """JSON from the corporate-actions feed, as date, symbol, series, isin, purpose."""
    if isinstance(payload, bytes):
        payload = payload.decode("utf-8", "replace")
    if payload.startswith("\ufeff"):
        payload = payload[1:]
    data = json.loads(payload)
    if isinstance(data, dict):
        data = data.get("data") or []
    rows = []
    for item in data:
        symbol = (item.get("symbol") or "").strip()
        ex = parse_nse_date(item.get("exDate") or "")
        if symbol == "" or ex == "":
            continue
        rows.append({
            "date": ex,
            "symbol": symbol,
            "series": (item.get("series") or "").strip(),
            "isin": (item.get("isin") or "").strip(),
            "purpose": (item.get("subject") or "").strip(),
        })
    return rows


def _option_type(text):
    text = (text or "").strip().upper()
    if text in FUTURES_OPTION or text in ("", "-"):
        return ""
    return text


def _row(date, symbol, instrument, expiry, strike, option_type,
         open_, high, low, close, settle, contracts, oi, change):
    return {
        "date": date,
        "symbol": symbol,
        "instrument": instrument,
        "expiry": expiry,
        "strike": _num(strike),
        "option_type": _option_type(option_type),
        "open": _num(open_),
        "high": _num(high),
        "low": _num(low),
        "close": _num(close),
        "settle": _num(settle),
        "contracts": _num(contracts),
        "open_interest": _num(oi),
        "change_in_oi": _num(change),
    }


def _cells(reader):
    for raw in reader:
        out = {}
        for key, value in raw.items():
            if key is None:
                continue
            out[key.strip()] = (value or "").strip()
        yield out


def parse_bhav(text):
    """One bhavcopy CSV, old format or UDiFF, as normalised rows.

    Old rows use INSTRUMENT, SYMBOL, EXPIRY_DT, TIMESTAMP.
    New rows use FinInstrmTp, TckrSymb, XpryDt, TradDt.
    A futures option type of XX or FF is stored blank. The instrument code
    is kept as published (FUTIDX, OPTIDX, IDF, IDO, STF, STO).
    """
    if text.startswith("\ufeff"):
        text = text[1:]
    reader = csv.DictReader(io.StringIO(text))
    fields = []
    for name in reader.fieldnames or []:
        if name is None:
            continue
        fields.append(name.strip())
    rows = []
    if "INSTRUMENT" in fields:
        for cell in _cells(reader):
            symbol = cell.get("SYMBOL", "")
            if symbol == "":
                continue
            rows.append(_row(
                parse_nse_date(cell.get("TIMESTAMP", "")),
                symbol,
                cell.get("INSTRUMENT", ""),
                parse_nse_date(cell.get("EXPIRY_DT", "")),
                cell.get("STRIKE_PR", ""),
                cell.get("OPTION_TYP", ""),
                cell.get("OPEN", ""),
                cell.get("HIGH", ""),
                cell.get("LOW", ""),
                cell.get("CLOSE", ""),
                cell.get("SETTLE_PR", ""),
                cell.get("CONTRACTS", ""),
                cell.get("OPEN_INT", ""),
                cell.get("CHG_IN_OI", ""),
            ))
        return rows
    if "TckrSymb" in fields or "FinInstrmTp" in fields:
        for cell in _cells(reader):
            symbol = cell.get("TckrSymb", "")
            if symbol == "":
                continue
            rows.append(_row(
                parse_nse_date(cell.get("TradDt", "")),
                symbol,
                cell.get("FinInstrmTp", ""),
                parse_nse_date(cell.get("XpryDt", "")),
                cell.get("StrkPric", ""),
                cell.get("OptnTp", ""),
                cell.get("OpnPric", ""),
                cell.get("HghPric", ""),
                cell.get("LwPric", ""),
                cell.get("ClsPric", ""),
                cell.get("SttlmPric", ""),
                cell.get("TtlTradgVol", ""),
                cell.get("OpnIntrst", ""),
                cell.get("ChngInOpnIntrst", ""),
            ))
        return rows
    raise ValueError("unrecognised bhavcopy header")


def _cm_row(date, symbol, series, isin, open_, high, low, close, last, prev, volume, turnover):
    series = (series or "").strip().upper()
    symbol = (symbol or "").strip()
    if symbol == "" or series not in CM_SERIES:
        return None
    return {
        "date": date,
        "symbol": symbol,
        "series": series,
        "isin": (isin or "").strip(),
        "open": _num(open_),
        "high": _num(high),
        "low": _num(low),
        "close": _num(close),
        "last": _num(last),
        "prev_close": _num(prev),
        "volume": _num(volume),
        "turnover": _num(turnover),
    }


def parse_cm(text, day=None):
    """Cash bhavcopy, old EQUITIES file or UDiFF, EQ and BE only.

    Old columns are SYMBOL, SERIES, OPEN, HIGH, LOW, CLOSE, LAST, PREVCLOSE,
    TOTTRDQTY, TOTTRDVAL, TIMESTAMP, ISIN. New columns are TradDt, TckrSymb,
    SctySrs, ISIN, OpnPric, HghPric, LwPric, ClsPric, LastPric, PrvsClsgPric,
    TtlTradgVol, TtlTrfVal. Any other series is dropped.
    """
    if text.startswith("\ufeff"):
        text = text[1:]
    reader = csv.DictReader(io.StringIO(text))
    fields = []
    for name in reader.fieldnames or []:
        if name is None:
            continue
        fields.append(name.strip())
    fallback = day.isoformat() if day is not None else ""
    rows = []
    if "SYMBOL" in fields and "SERIES" in fields:
        for cell in _cells(reader):
            stamped = parse_nse_date(cell.get("TIMESTAMP", "")) or fallback
            row = _cm_row(
                stamped,
                cell.get("SYMBOL", ""),
                cell.get("SERIES", ""),
                cell.get("ISIN", ""),
                cell.get("OPEN", ""),
                cell.get("HIGH", ""),
                cell.get("LOW", ""),
                cell.get("CLOSE", ""),
                cell.get("LAST", ""),
                cell.get("PREVCLOSE", ""),
                cell.get("TOTTRDQTY", ""),
                cell.get("TOTTRDVAL", ""),
            )
            if row is not None:
                rows.append(row)
        return rows
    if "TckrSymb" in fields or "SctySrs" in fields:
        for cell in _cells(reader):
            stamped = (cell.get("TradDt", "") or "")[:10] or fallback
            row = _cm_row(
                stamped,
                cell.get("TckrSymb", ""),
                cell.get("SctySrs", ""),
                cell.get("ISIN", ""),
                cell.get("OpnPric", ""),
                cell.get("HghPric", ""),
                cell.get("LwPric", ""),
                cell.get("ClsPric", ""),
                cell.get("LastPric", ""),
                cell.get("PrvsClsgPric", ""),
                cell.get("TtlTradgVol", ""),
                cell.get("TtlTrfVal", ""),
            )
            if row is not None:
                rows.append(row)
        return rows
    raise ValueError("unrecognised cash bhavcopy header")


def parse_delivery(text, day):
    """Security-wise delivery. sec_bhavdata_full or the older MTO file.

    Header cells are stripped, so a spaced ' DELIV_QTY ' still matches.
    EQ and BE only. The date is the session we asked for.
    """
    if text.startswith("\ufeff"):
        text = text[1:]
    lines = text.splitlines()
    start = 0
    for i, line in enumerate(lines):
        upper = line.upper()
        if "DELIV" in upper or "DELIVERABLE" in upper:
            start = i
            break
    # The MTO file's header has no series cell, but each data row does:
    # 20,sr,symbol,EQ,traded,deliverable,percent.
    if any("NAME OF SECURITY" in line.upper() for line in lines):
        rows = []
        for line in lines:
            if not line.startswith("20,"):
                continue
            parts = [part.strip() for part in next(csv.reader([line]))]
            if len(parts) < 7:
                continue
            row = _delivery_row(day, parts[2], parts[3], parts[5], parts[6])
            if row is not None:
                rows.append(row)
        return rows
    reader = csv.DictReader(io.StringIO("\n".join(lines[start:])))
    rows = []
    for cell in _cells(reader):
        symbol = (
            cell.get("SYMBOL")
            or cell.get("Security Name")
            or cell.get("Name of Security")
            or ""
        )
        series = (cell.get("SERIES") or cell.get("Series") or "EQ").strip().upper()
        if series not in CM_SERIES:
            continue
        qty = (
            cell.get("DELIV_QTY")
            or cell.get("Deliverable Quantity")
            or cell.get("Deliverable Qty")
            or ""
        )
        pct = (
            cell.get("DELIV_PER")
            or cell.get("% of Deliverable Quantity to Traded Quantity")
            or cell.get("% of Deliverable Qty to Traded Qty")
            or ""
        )
        row = _delivery_row(day, symbol, series, qty, pct)
        if row is not None:
            rows.append(row)
    return rows


def _delivery_row(day, symbol, series, qty, pct):
    series = (series or "").strip().upper()
    symbol = (symbol or "").strip()
    qty = (qty or "").strip()
    if series not in CM_SERIES or symbol == "" or qty == "" or qty == "-":
        return None
    return {
        "date": day.isoformat(),
        "symbol": symbol,
        "series": series,
        "deliverable_qty": _num(qty),
        "deliverable_pct": _num(pct),
    }


def _index_stamp(day):
    return "%02d-%s-%d" % (day.day, _INDEX_MON[day.month - 1], day.year)


def _index_date(text):
    text = (text or "").strip()
    iso = parse_nse_date(text)
    if iso:
        return iso
    parts = text.replace(",", " ").split()
    if len(parts) != 3:
        return ""
    try:
        month = _INDEX_MON.index(parts[1][:3].title()) + 1
        return "%04d-%02d-%02d" % (int(parts[2]), month, int(parts[0]))
    except ValueError:
        return ""


def parse_index_history(payload):
    """Rows of (date, close) from a getHistoricaldata response.

    The body is JSON. Field d is itself a JSON string of rows. An empty list
    means that name has no rows in the span. None means the body was not that
    shape.
    """
    if isinstance(payload, bytes):
        text = payload.decode("utf-8", "replace")
    else:
        text = payload
    if text.startswith("\ufeff"):
        text = text[1:]
    try:
        obj = json.loads(text)
    except ValueError:
        return None
    if isinstance(obj, list):
        raw = obj
    else:
        raw = obj.get("d") if isinstance(obj, dict) else None
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except ValueError:
            return None
        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except ValueError:
                return None
    if not isinstance(raw, list):
        return None
    rows = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        cell = {}
        for key, value in item.items():
            cell[str(key).strip()] = "" if value is None else str(value).strip()
        stamped = (
            _index_date(cell.get("HistoricalDate", ""))
            or _index_date(cell.get("CH_TIMESTAMP", ""))
            or _index_date(cell.get("Date", ""))
            or _index_date(cell.get("DATE", ""))
        )
        close = (
            cell.get("CLOSE")
            or cell.get("Close")
            or cell.get("close")
            or cell.get("CH_CLOSING_VALUE")
            or cell.get("Closing Index Value")
            or cell.get("TotalReturnsIndex")
            or ""
        )
        if not stamped or close == "" or close == "-":
            continue
        rows.append((stamped, _num(close)))
    return rows


def _index_query_name(name):
    """Drop a trailing TR or TRI. The total-return endpoint wants the price name."""
    text = (name or "").strip()
    upper = text.upper()
    for suffix in (" TRI", " TR"):
        if upper.endswith(suffix):
            return text[: -len(suffix)].strip()
    return text


def index_body(name, start, end):
    """The cinfo string niftyindices expects, wrapped as JSON."""
    cinfo = (
        "{'name':'%s','startDate':'%s','endDate':'%s','indexName':'%s'}"
        % (name, _index_stamp(start), _index_stamp(end), name)
    )
    return json.dumps({"cinfo": cinfo})


def index_years(today):
    return list(range(INDEX_START.year, today.year + 1))


def index_span(year, today):
    start = datetime.date(year, 1, 1)
    end = datetime.date(year, 12, 31)
    if start < INDEX_START:
        start = INDEX_START
    if end > today:
        end = today
    return start, end


def write_rows(path, rows):
    """Gzipped CSV in HEADER order. Atomic replace."""
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(HEADER)
    for row in rows:
        writer.writerow((
            row["date"], row["symbol"], row["instrument"], row["expiry"],
            row["strike"], row["option_type"], row["open"], row["high"],
            row["low"], row["close"], row["settle"], row["contracts"],
            row["open_interest"], row["change_in_oi"],
        ))
    _write_gzip(path, buf.getvalue().encode("utf-8"))


def iter_rows(path):
    """Stream one normalised bhavcopy. The caller filters."""
    with gzip.open(path, "rt", encoding="utf-8", newline="") as fh:
        for cell in csv.DictReader(fh):
            yield {
                "date": cell.get("date", ""),
                "symbol": cell.get("symbol", ""),
                "instrument": cell.get("instrument", ""),
                "expiry": cell.get("expiry", ""),
                "strike": cell.get("strike", ""),
                "option_type": cell.get("option type", ""),
                "open": cell.get("open", ""),
                "high": cell.get("high", ""),
                "low": cell.get("low", ""),
                "close": cell.get("close", ""),
                "settle": cell.get("settle", ""),
                "contracts": cell.get("contracts", ""),
                "open_interest": cell.get("open interest", ""),
                "change_in_oi": cell.get("change in OI", ""),
            }


def read_rows(path):
    return list(iter_rows(path))


def _write_gzip(path, payload):
    folder = os.path.dirname(path)
    if folder:
        os.makedirs(folder, exist_ok=True)
    tmp = path + ".part"
    with gzip.open(tmp, "wb") as fh:
        fh.write(payload)
    os.replace(tmp, path)


def _write_bytes(path, payload):
    folder = os.path.dirname(path)
    if folder:
        os.makedirs(folder, exist_ok=True)
    tmp = path + ".part"
    with open(tmp, "wb") as fh:
        fh.write(payload)
    os.replace(tmp, path)


def _ddmmyyyy(day):
    return "%02d%02d%d" % (day.day, day.month, day.year)


def _dmy(day):
    return "%02d-%02d-%d" % (day.day, day.month, day.year)


def cm_urls(day):
    """Old cash bhavcopy through 5 July 2024, UDiFF from 8 July 2024."""
    if day <= OLD_LAST:
        name = "cm%02d%s%dbhav.csv.zip" % (day.day, MONTHS[day.month - 1], day.year)
        path = "/content/historical/EQUITIES/%d/%s/%s" % (
            day.year, MONTHS[day.month - 1], name)
    else:
        path = "/content/cm/BhavCopy_NSE_CM_0_0_0_%s_F_0000.csv.zip" % day.strftime("%Y%m%d")
    return [host + path for host in HOSTS]


def delivery_urls(day):
    """sec_bhavdata_full first, then the older MTO file. Both hosts."""
    stamp = _ddmmyyyy(day)
    paths = (
        "/products/content/sec_bhavdata_full_%s.csv" % stamp,
        "/archives/equities/mto/MTO_%s.DAT" % stamp,
    )
    urls = []
    for path in paths:
        for host in HOSTS:
            urls.append(host + path)
    return urls


def bhav_urls(day):
    urls = []
    if day <= OLD_LAST:
        name = "fo%02d%s%dbhav.csv.zip" % (day.day, MONTHS[day.month - 1], day.year)
        path = "/content/historical/DERIVATIVES/%d/%s/%s" % (
            day.year, MONTHS[day.month - 1], name)
    else:
        path = "/content/fo/BhavCopy_NSE_FO_0_0_0_%s_F_0000.csv.zip" % day.strftime("%Y%m%d")
    for host in HOSTS:
        urls.append(host + path)
    return urls


def participant_urls(day):
    path = "/content/nsccl/fao_participant_oi_%s.csv" % _ddmmyyyy(day)
    return [host + path for host in HOSTS]


def vix_urls(day):
    path = "/content/indices/ind_close_all_%s.csv" % _ddmmyyyy(day)
    return [host + path for host in HOSTS]


def bhav_path(root, day):
    return os.path.join(root, "fo", day.isoformat() + ".csv.gz")


def participant_path(root, day):
    return os.path.join(root, "participant", day.isoformat() + ".csv.gz")


def vix_day_path(root, day):
    return os.path.join(root, "vix", day.isoformat() + ".csv.gz")


def vix_path(root):
    return os.path.join(root, "vix.csv")


def results_path(root, symbol):
    return os.path.join(root, "results", symbol + ".csv.gz")


def board_path(root, symbol):
    return os.path.join(root, "board", symbol + ".csv.gz")


def announce_path(root, symbol):
    return os.path.join(root, "announcements", symbol + ".csv.gz")


def holiday_path(root):
    return os.path.join(root, "holidays", "trading.json.gz")


def cm_path(root, day):
    return os.path.join(root, "cm", day.isoformat() + ".csv.gz")


def delivery_path(root, day):
    return os.path.join(root, "delivery", day.isoformat() + ".csv.gz")


def index_part_path(root, slug, year):
    return os.path.join(root, "indices", "parts", slug, "%d.csv.gz" % year)


def index_path(root, slug):
    return os.path.join(root, "indices", slug + ".csv.gz")


def progress_path(root, only=None):
    """Original jobs share progress.json. cm, delivery and indices do not."""
    return os.path.join(root, _PROGRESS_NAME.get(only, "progress.json"))


def _present(path):
    return os.path.isfile(path) and os.path.getsize(path) > 0


class Client(object):
    """One request a second. 20-second timeout. Three tries, then a pause.

    `fetch`, when set, replaces the HTTP call. It is (url, accept, timeout)
    and returns (status, body) or raises. `sleep` replaces time.sleep so a
    test can fail twice and succeed without waiting.
    """

    def __init__(self, fetch=None, sleep=None):
        self.fetch = fetch
        self.sleep = sleep or time.sleep
        self.opener = None if fetch else urllib.request.build_opener()
        self.last = 0.0
        self.warmed = False
        self.streak = 0

    def _wait(self):
        now = time.monotonic()
        delay = GAP_SECONDS - (now - self.last)
        if delay > 0:
            self.sleep(delay)
        self.last = time.monotonic()

    def _once(self, url, accept, data=None, content_type=None):
        self._wait()
        if self.fetch is not None:
            return self.fetch(url, accept, TIMEOUT)
        headers = {
            "User-Agent": USER_AGENT,
            "Accept": accept,
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://www.nseindia.com/",
        }
        payload = None
        if data is not None:
            payload = data if isinstance(data, bytes) else data.encode("utf-8")
            headers["Content-Type"] = content_type or "application/json; charset=utf-8"
        if "niftyindices.com" in url:
            headers["Referer"] = "https://www.niftyindices.com/reports/historical-data"
            headers["Origin"] = "https://www.niftyindices.com"
            headers["X-Requested-With"] = "XMLHttpRequest"
        req = urllib.request.Request(url, data=payload, headers=headers)
        try:
            resp = self.opener.open(req, timeout=TIMEOUT)
            try:
                return resp.status, resp.read()
            except (OSError, http.client.HTTPException):
                return 0, b""
        except urllib.error.HTTPError as exc:
            try:
                body = exc.read() if exc.fp is not None else b""
            except (OSError, http.client.HTTPException):
                body = b""
            return exc.code, body
        except (OSError, http.client.HTTPException):
            return 0, b""

    def warm(self):
        if self.warmed or self.fetch is not None:
            self.warmed = True
            return
        self._once(WARM_URL, "text/html")
        self.warmed = True

    def _note(self, ok):
        if ok:
            self.streak = 0
            return
        self.streak += 1
        if self.streak >= FAIL_STREAK:
            self.sleep(FAIL_PAUSE)
            self.streak = 0

    def get(self, urls, accept="*/*", data=None, content_type=None):
        """Try each URL, then retry the list. (status, body) or (404, b'').

        data, when set, is posted as the body. The retry and pause rules are
        the same as a GET.
        """
        self.warm()
        last = (0, b"")
        for attempt in range(RETRIES):
            if attempt:
                self.sleep(BACKOFF[attempt - 1])
            saw_other = False
            for url in urls:
                try:
                    status, body = self._once(url, accept, data, content_type)
                except (OSError, http.client.HTTPException):
                    status, body = 0, b""
                last = (status, body)
                if status == 200 and body and not _looks_html(body):
                    self._note(True)
                    return status, body
                if status != 404:
                    self._note(False)
                    saw_other = True
            if not saw_other and last[0] == 404:
                return 404, b""
        return last


def _zip_text(payload):
    """CSV text, a zipped CSV, or an Excel file NSE sometimes names .csv."""
    if payload[:2] != b"PK":
        return payload.decode("utf-8", "replace")
    import zipfile
    zf = zipfile.ZipFile(io.BytesIO(payload))
    names = zf.namelist()
    if "xl/worksheets/sheet1.xml" in names:
        return _xlsx_csv(zf)
    return zf.read(names[0]).decode("utf-8", "replace")


def _xlsx_csv(zf):
    """First worksheet of an xlsx archive, as CSV text. Standard library only."""
    import xml.etree.ElementTree as ET
    ns = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
    strings = []
    if "xl/sharedStrings.xml" in zf.namelist():
        root = ET.fromstring(zf.read("xl/sharedStrings.xml"))
        for item in root.findall(ns + "si"):
            strings.append("".join(node.text or "" for node in item.iter(ns + "t")))
    sheet = ET.fromstring(zf.read("xl/worksheets/sheet1.xml"))
    lines = []
    for row in sheet.findall(ns + "sheetData/" + ns + "row"):
        cells = {}
        width = 0
        for cell in row.findall(ns + "c"):
            ref = cell.get("r") or "A"
            letters = "".join(ch for ch in ref if ch.isalpha())
            index = 0
            for ch in letters:
                index = index * 26 + (ord(ch) - 64)
            value = cell.find(ns + "v")
            text = "" if value is None or value.text is None else value.text
            kind = cell.get("t")
            if kind == "s" and text.isdigit():
                text = strings[int(text)]
            elif kind == "inlineStr":
                inline = cell.find(ns + "is")
                text = ""
                if inline is not None:
                    text = "".join(node.text or "" for node in inline.iter(ns + "t"))
            cells[index] = text.strip()
            if index > width:
                width = index
        if width == 0:
            continue
        buffer = io.StringIO()
        csv.writer(buffer).writerow([cells.get(i, "") for i in range(1, width + 1)])
        lines.append(buffer.getvalue().rstrip("\r\n"))
    return "\n".join(lines)


def _looks_html(payload):
    head = payload[:200].lstrip().lower()
    return head.startswith(b"<!doctype") or head.startswith(b"<html")


def india_vix_line(text, day):
    """The India VIX row, or None when this index file has no such line."""
    if text.startswith("\ufeff"):
        text = text[1:]
    reader = csv.DictReader(io.StringIO(text))
    for cell in _cells(reader):
        if cell.get("Index Name", "") != "India VIX":
            continue
        return {
            "date": day.isoformat(),
            "open": cell.get("Open Index Value", ""),
            "high": cell.get("High Index Value", ""),
            "low": cell.get("Low Index Value", ""),
            "close": cell.get("Closing Index Value", ""),
        }
    return None


def _load_progress(root, only=None):
    path = progress_path(root, only)
    if not os.path.isfile(path):
        return {}
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _save_progress(root, progress, only=None):
    path = progress_path(root, only)
    os.makedirs(root, exist_ok=True)
    tmp = path + ".part"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(progress, fh, sort_keys=True)
        fh.write("\n")
    os.replace(tmp, path)


def _mark(root, progress, kind, key, status, only=None):
    bucket = progress.get(kind)
    if bucket is None:
        bucket = {}
        progress[kind] = bucket
    bucket[key] = status
    _save_progress(root, progress, only)


def _status(progress, kind, key):
    return (progress.get(kind) or {}).get(key, "")


def _tally_actions(root, today):
    own = _load_progress(root, "actions")
    years = action_years(today)
    present = 0
    missing = 0
    fetch = 0
    for year in years:
        key = str(year)
        if _present(actions_path(root, year)):
            present += 1
        elif _status(own, "actions", key) == "missing":
            missing += 1
        else:
            fetch += 1
    return {
        "expected": len(years),
        "present": present,
        "missing": missing,
        "fetch": fetch,
    }


def _fetch_actions(client, root, progress, year, today, log):
    path = actions_path(root, year)
    key = str(year)
    if _present(path) or _status(progress, "actions", key) == "missing":
        return "skip"
    status, body = client.get(
        [actions_url(year, today)],
        accept="application/json,text/plain,*/*",
    )
    if status != 200 or not body or _looks_html(body):
        log("actions %s failed status %s" % (key, status))
        return "fail"
    try:
        rows = parse_actions(body)
    except (ValueError, OSError, KeyError) as exc:
        log("actions %s parse failed: %s" % (key, exc))
        return "fail"
    if not rows:
        log("actions %s had no rows" % key)
        return "fail"
    _record_rows(path, ACTIONS_HEADER, rows)
    _mark(root, progress, "actions", key, "ok", "actions")
    log("actions %s rows %d" % (key, len(rows)))
    return "ok"


def plan(root, symbols, today):
    """Counts only. No request is made."""
    bhav_days = trading_days(BHAV_START, today)
    part_days = trading_days(PARTICIPANT_START, today)
    vix_days = trading_days(VIX_START, today)
    progress = _load_progress(root)

    def tally(kind, days, path_of):
        present = 0
        missing = 0
        fetch = 0
        for day in days:
            key = day.isoformat()
            if _present(path_of(root, day)):
                present += 1
            elif _status(progress, kind, key) == "missing":
                missing += 1
            else:
                fetch += 1
        return {
            "expected": len(days),
            "present": present,
            "missing": missing,
            "fetch": fetch,
        }

    def tally_names(kind, path_of):
        present = 0
        missing = 0
        fetch = 0
        for symbol in symbols:
            if _present(path_of(root, symbol)):
                present += 1
            elif _status(progress, kind, symbol) == "missing":
                missing += 1
            else:
                fetch += 1
        return {
            "expected": len(symbols),
            "present": present,
            "missing": missing,
            "fetch": fetch,
        }

    def tally_own(only, kind, days, path_of):
        own = _load_progress(root, only)
        present = 0
        missing = 0
        fetch = 0
        for day in days:
            key = day.isoformat()
            if _present(path_of(root, day)):
                present += 1
            elif _status(own, kind, key) == "missing":
                missing += 1
            else:
                fetch += 1
        return {
            "expected": len(days),
            "present": present,
            "missing": missing,
            "fetch": fetch,
        }

    def tally_indices():
        own = _load_progress(root, "indices")
        years = index_years(today)
        present = 0
        missing = 0
        fetch = 0
        for slug, _name, _alt in INDEX_SERIES:
            for year in years:
                key = "%s|%d" % (slug, year)
                if _present(index_part_path(root, slug, year)):
                    present += 1
                elif _status(own, "indices", key) == "missing":
                    missing += 1
                else:
                    fetch += 1
        expected = len(INDEX_SERIES) * len(years)
        return {
            "expected": expected,
            "present": present,
            "missing": missing,
            "fetch": fetch,
        }

    holiday_present = 1 if _present(holiday_path(root)) else 0
    cm_days = trading_days(CM_START, today)
    return {
        "today": today.isoformat(),
        "bhav": tally("bhav", bhav_days, bhav_path),
        "participant": tally("participant", part_days, participant_path),
        "vix": tally("vix", vix_days, vix_day_path),
        "results": tally_names("results", results_path),
        "board": tally_names("board", board_path),
        "announcements": tally_names("announcements", announce_path),
        "holidays": {
            "expected": 1,
            "present": holiday_present,
            "missing": 0,
            "fetch": 0 if holiday_present else 1,
        },
        "cm": tally_own("cm", "cm", cm_days, cm_path),
        "delivery": tally_own("delivery", "delivery", cm_days, delivery_path),
        "indices": tally_indices(),
        "actions": _tally_actions(root, today),
    }


def format_plan(counts):
    lines = ["dry run, today %s" % counts["today"]]
    order = (
        ("bhav", "bhavcopy"),
        ("participant", "participant oi"),
        ("vix", "india vix"),
        ("results", "financial results"),
        ("board", "board meetings"),
        ("announcements", "results announcements from 2025"),
        ("holidays", "holiday lists"),
        ("cm", "cash bhavcopy"),
        ("delivery", "delivery"),
        ("indices", "index history"),
        ("actions", "corporate actions"),
    )
    for key, label in order:
        item = counts[key]
        lines.append(
            "%s expected %d, on disk %d, recorded missing %d, to fetch %d" % (
                label, item["expected"], item["present"], item["missing"], item["fetch"]))
    return "\n".join(lines)


def _csv_gzip(path, header, records):
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(header)
    for record in records:
        writer.writerow(record)
    _write_gzip(path, buf.getvalue().encode("utf-8"))


def _safe_symbol(symbol):
    if not symbol or "/" in symbol or "\\" in symbol:
        return False
    return True


def _results_rows(payload):
    try:
        data_rows = json.loads(payload.decode("utf-8"))
    except ValueError:
        return None
    if not isinstance(data_rows, list):
        return None
    out = []
    for row in data_rows:
        if not isinstance(row, dict):
            continue
        out.append((
            row.get("broadCastDate") or "",
            row.get("filingDate") or "",
            row.get("fromDate") or "",
            row.get("toDate") or "",
            row.get("consolidated") or "",
            row.get("period") or "",
        ))
    return out


def _board_rows(payload):
    try:
        data_rows = json.loads(payload.decode("utf-8"))
    except ValueError:
        return None
    if not isinstance(data_rows, list):
        return None
    out = []
    for row in data_rows:
        if not isinstance(row, dict):
            continue
        desc = (row.get("bm_desc") or "").replace("\r", " ").replace("\n", " ")
        out.append((
            row.get("bm_date") or "",
            row.get("bm_timestamp") or "",
            row.get("bm_purpose") or "",
            desc,
        ))
    return out


def _announce_rows(payload):
    try:
        data_rows = json.loads(payload.decode("utf-8"))
    except ValueError:
        return None
    if not isinstance(data_rows, list):
        return None
    out = []
    for row in data_rows:
        if not isinstance(row, dict):
            continue
        desc = row.get("desc") or ""
        text = (row.get("attchmntText") or "").replace("\r", " ").replace("\n", " ")
        blob = (desc + " " + text).lower()
        if "financial result" not in blob:
            continue
        if desc not in ("Financial Result Updates", "Outcome of Board Meeting"):
            continue
        out.append((row.get("an_dt") or "", desc, text))
    return out


def rebuild_vix(root):
    """Join the per-day India VIX files into data/nse/vix.csv."""
    folder = os.path.join(root, "vix")
    lines = ["date,open,high,low,close"]
    if os.path.isdir(folder):
        names = sorted(name for name in os.listdir(folder) if name.endswith(".csv.gz"))
        for name in names:
            rows = []
            with gzip.open(os.path.join(folder, name), "rt", encoding="utf-8", newline="") as fh:
                for cell in csv.DictReader(fh):
                    rows.append(cell)
            if not rows:
                continue
            cell = rows[0]
            lines.append(",".join((
                cell.get("date", ""), cell.get("open", ""), cell.get("high", ""),
                cell.get("low", ""), cell.get("close", ""),
            )))
    path = vix_path(root)
    tmp = path + ".part"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    os.replace(tmp, path)
    return len(lines) - 1


def _fetch_day(client, root, progress, kind, day, urls, log):
    key = day.isoformat()
    path = {
        "bhav": bhav_path,
        "participant": participant_path,
        "vix": vix_day_path,
    }[kind](root, day)
    if _present(path) or _status(progress, kind, key) == "missing":
        return "skip"
    status, body = client.get(urls)
    if status == 404 or not body or _looks_html(body):
        if status == 404:
            _mark(root, progress, kind, key, "missing")
            return "missing"
        log("%s %s failed status %s" % (kind, key, status))
        return "fail"
    try:
        if kind == "bhav":
            rows = parse_bhav(_zip_text(body))
            write_rows(path, rows)
        elif kind == "participant":
            _write_gzip(path, body)
        else:
            line = india_vix_line(_zip_text(body), day)
            if line is None:
                _mark(root, progress, kind, key, "missing")
                return "missing"
            _csv_gzip(path, ("date", "open", "high", "low", "close"), [(
                line["date"], line["open"], line["high"], line["low"], line["close"])])
    except (ValueError, OSError, KeyError) as exc:
        log("%s %s parse failed: %s" % (kind, key, exc))
        return "fail"
    _mark(root, progress, kind, key, "ok")
    return "ok"


def _fetch_symbol(client, root, progress, kind, symbol, url, parse, header, log):
    path = {
        "results": results_path,
        "board": board_path,
        "announcements": announce_path,
    }[kind](root, symbol)
    if _present(path) or _status(progress, kind, symbol) == "missing":
        return "skip"
    status, body = client.get([url], accept="application/json,text/plain,*/*")
    if status != 200 or not body or _looks_html(body):
        log("%s %s failed status %s" % (kind, symbol, status))
        return "fail"
    rows = parse(body)
    if rows is None:
        log("%s %s was not a list" % (kind, symbol))
        return "fail"
    _csv_gzip(path, header, rows)
    _mark(root, progress, kind, symbol, "ok")
    return "ok"


def _clock(seconds):
    seconds = int(seconds)
    if seconds < 0:
        seconds = 0
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60
    if hours:
        return "%dh %dm %ds" % (hours, minutes, secs)
    return "%dm %ds" % (minutes, secs)


def _record_rows(path, header, rows):
    _csv_gzip(path, header, [tuple(row[name] for name in header) for row in rows])


def _fetch_cm(client, root, progress, day, log):
    path = cm_path(root, day)
    key = day.isoformat()
    if _present(path) or _status(progress, "cm", key) == "missing":
        return "skip"
    status, body = client.get(cm_urls(day))
    if status == 404 or not body or _looks_html(body):
        if status == 404:
            _mark(root, progress, "cm", key, "missing", "cm")
            return "missing"
        log("cm %s failed status %s" % (key, status))
        return "fail"
    try:
        rows = parse_cm(_zip_text(body), day)
    except (ValueError, OSError, KeyError) as exc:
        log("cm %s parse failed: %s" % (key, exc))
        return "fail"
    if not rows:
        log("cm %s had no EQ or BE rows" % key)
        return "fail"
    _record_rows(path, CM_HEADER, rows)
    _mark(root, progress, "cm", key, "ok", "cm")
    return "ok"


def _fetch_delivery(client, root, progress, day, log):
    path = delivery_path(root, day)
    key = day.isoformat()
    if _present(path) or _status(progress, "delivery", key) == "missing":
        return "skip"
    status, body = client.get(delivery_urls(day), accept="text/csv,text/plain,*/*")
    if status == 404 or not body or _looks_html(body):
        if status == 404:
            _mark(root, progress, "delivery", key, "missing", "delivery")
            return "missing"
        log("delivery %s failed status %s" % (key, status))
        return "fail"
    try:
        rows = parse_delivery(_zip_text(body), day)
    except (ValueError, OSError, KeyError) as exc:
        log("delivery %s parse failed: %s" % (key, exc))
        return "fail"
    if not rows:
        log("delivery %s had no EQ or BE rows" % key)
        return "fail"
    _record_rows(path, DELIVERY_HEADER, rows)
    _mark(root, progress, "delivery", key, "ok", "delivery")
    return "ok"


def _fetch_index(client, root, progress, slug, names, year, today, log):
    key = "%s|%d" % (slug, year)
    path = index_part_path(root, slug, year)
    if _present(path) or _status(progress, "indices", key) == "missing":
        return "skip"
    start, end = index_span(year, today)
    if start > end:
        _mark(root, progress, "indices", key, "missing", "indices")
        return "missing"
    found = None
    last_status = 0
    endpoint = INDEX_TR_URL if slug.endswith("_TR") else INDEX_URL
    for name in names:
        if not name:
            continue
        status, body = client.get(
            [endpoint],
            accept="application/json,text/plain,*/*",
            data=index_body(_index_query_name(name), start, end),
        )
        last_status = status
        if status != 200 or not body or _looks_html(body):
            if status == 404:
                continue
            log("indices %s failed status %s" % (key, status))
            return "fail"
        try:
            rows = parse_index_history(body)
        except (ValueError, OSError, KeyError) as exc:
            log("indices %s parse failed: %s" % (key, exc))
            return "fail"
        if rows is None:
            log("indices %s was not index history" % key)
            return "fail"
        if rows:
            found = rows
            break
    if not found:
        if last_status in (200, 404):
            _mark(root, progress, "indices", key, "missing", "indices")
            return "missing"
        log("indices %s failed status %s" % (key, last_status))
        return "fail"
    found.sort()
    _csv_gzip(path, ("date", "close"), found)
    _mark(root, progress, "indices", key, "ok", "indices")
    return "ok"


def _join_indices(root, log):
    for slug, _name, _alt in INDEX_SERIES:
        folder = os.path.join(root, "indices", "parts", slug)
        if not os.path.isdir(folder):
            continue
        seen = {}
        for name in sorted(os.listdir(folder)):
            if not name.endswith(".csv.gz"):
                continue
            with gzip.open(os.path.join(folder, name), "rt", encoding="utf-8") as fh:
                for row in csv.DictReader(fh):
                    seen[row["date"]] = row["close"]
        if not seen:
            continue
        _csv_gzip(index_path(root, slug), ("date", "close"), sorted(seen.items()))
        log("indices %s joined %d rows" % (slug, len(seen)))


def _download_job(root, today, only, counts, client, emit):
    """cm, delivery, or indices. Its own progress file. Same pause and ETA."""
    progress = _load_progress(root, only)
    planned = counts[only]["fetch"]
    emit("%s to fetch %d" % (only, planned))
    done = {"ok": 0, "missing": 0, "fail": 0, "skip": 0}
    started = time.monotonic()

    def note(result):
        done[result] = done.get(result, 0) + 1
        total = done["ok"] + done["missing"] + done["fail"]
        if total and total % 100 == 0:
            left = planned - total
            if left < 0:
                left = 0
            elapsed = time.monotonic() - started
            eta = (elapsed / float(total)) * left
            emit("remaining %d, eta %s" % (left, _clock(eta)))

    if only == "cm":
        for day in trading_days(CM_START, today):
            note(_fetch_cm(client, root, progress, day, emit))
    elif only == "delivery":
        for day in trading_days(CM_START, today):
            note(_fetch_delivery(client, root, progress, day, emit))
    elif only == "actions":
        for year in action_years(today):
            note(_fetch_actions(client, root, progress, year, today, emit))
    else:
        for slug, name, alt in INDEX_SERIES:
            for year in index_years(today):
                note(_fetch_index(
                    client, root, progress, slug, (name, alt), year, today, emit))
        _join_indices(root, emit)
    left = planned - (done["ok"] + done["missing"] + done["fail"])
    if left < 0:
        left = 0
    emit("remaining %d, eta %s" % (left, _clock(0)))
    emit("done ok %d missing %d failed %d skipped %d" % (
        done["ok"], done["missing"], done["fail"], done["skip"]))
    return done


def download(root, symbols, today, only, log=None, client=None):
    """Fetch one part. Prints the dry-run count first. Saves each file at once."""
    if only not in ONLY:
        raise ValueError("only must be one of %s" % ", ".join(ONLY))
    emit = log or (lambda line: print(line, flush=True))
    counts = plan(root, symbols, today)
    emit(format_plan(counts))
    client = client or Client()
    if only in NEW_JOBS:
        return _download_job(root, today, only, counts, client, emit)
    progress = _load_progress(root)
    today_text = _dmy(today)
    done = {"ok": 0, "missing": 0, "fail": 0, "skip": 0}
    vix_writes = [0]
    started = time.monotonic()
    if only == "bhavcopy":
        planned = counts["bhav"]["fetch"]
    elif only == "participant":
        planned = counts["participant"]["fetch"]
    elif only == "vix":
        planned = counts["vix"]["fetch"]
    else:
        planned = (
            counts["results"]["fetch"] + counts["board"]["fetch"]
            + counts["announcements"]["fetch"] + counts["holidays"]["fetch"])
    emit("%s to fetch %d" % (only, planned))

    def note(result):
        done[result] = done.get(result, 0) + 1
        total = done["ok"] + done["missing"] + done["fail"]
        if total and total % 100 == 0:
            left = planned - total
            if left < 0:
                left = 0
            elapsed = time.monotonic() - started
            eta = (elapsed / float(total)) * left
            emit("remaining %d, eta %s" % (left, _clock(eta)))

    def run_days(kind, days, urls_of):
        emit("phase %s, %d days" % (kind, len(days)))
        for day in days:
            result = _fetch_day(client, root, progress, kind, day, urls_of(day), emit)
            note(result)
            if kind == "vix" and result == "ok":
                vix_writes[0] += 1
                if vix_writes[0] % 200 == 0:
                    rebuild_vix(root)

    if only == "bhavcopy":
        run_days("bhav", trading_days(BHAV_START, today), bhav_urls)
    elif only == "vix":
        run_days("vix", trading_days(VIX_START, today), vix_urls)
        n = rebuild_vix(root)
        emit("vix.csv rows %d" % n)
    elif only == "participant":
        run_days("participant", trading_days(PARTICIPANT_START, today), participant_urls)
    else:
        emit("phase results, board, announcements, %d symbols" % len(symbols))
        for index, symbol in enumerate(symbols):
            if not _safe_symbol(symbol):
                emit("skip unsafe symbol %s" % symbol)
                continue
            if index % 25 == 0:
                emit("symbols %d / %d" % (index, len(symbols)))
            quoted = urllib.parse.quote(symbol)
            result = _fetch_symbol(
                client, root, progress, "results", symbol,
                "https://www.nseindia.com/api/corporates-financial-results?index=equities"
                "&from_date=%s&to_date=%s&symbol=%s&period=Quarterly" % (
                    RESULTS_FROM, today_text, quoted),
                _results_rows,
                ("broadcast", "filing", "period_from", "period_to", "consolidated", "period"),
                emit)
            note(result)
            result = _fetch_symbol(
                client, root, progress, "board", symbol,
                "https://www.nseindia.com/api/corporate-board-meetings?index=equities"
                "&symbol=%s&from_date=%s&to_date=%s" % (quoted, RESULTS_FROM, today_text),
                _board_rows,
                ("date", "intimated", "purpose", "description"),
                emit)
            note(result)
            result = _fetch_symbol(
                client, root, progress, "announcements", symbol,
                "https://www.nseindia.com/api/corporate-announcements?index=equities"
                "&symbol=%s&from_date=%s&to_date=%s" % (
                    quoted, _dmy(ANNOUNCE_FROM), today_text),
                _announce_rows,
                ("announced", "desc", "text"),
                emit)
            note(result)
        if not _present(holiday_path(root)) and _status(progress, "holidays", "trading") != "missing":
            status, body = client.get(
                ["https://www.nseindia.com/api/holiday-master?type=trading"],
                accept="application/json,text/plain,*/*")
            if status == 200 and body and not _looks_html(body):
                _write_gzip(holiday_path(root), body)
                _mark(root, progress, "holidays", "trading", "ok")
                emit("holiday list saved")
                note("ok")
            else:
                emit("holiday list failed status %s" % status)
                note("fail")
    left = planned - (done["ok"] + done["missing"] + done["fail"])
    if left < 0:
        left = 0
    emit("remaining %d, eta %s" % (left, _clock(0)))
    emit("done ok %d missing %d failed %d skipped %d" % (
        done["ok"], done["missing"], done["fail"], done["skip"]))
    return done


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(description="Download one NSE archive part. Nothing is ordered.")
    parser.add_argument("--root", default=os.path.join("data", "nse"))
    parser.add_argument("--kite", default=os.path.join("data", "kite"))
    parser.add_argument("--count-only", action="store_true")
    parser.add_argument("--only", choices=ONLY, default="")
    parser.add_argument("--today", default="")
    args = parser.parse_args(argv)
    if args.today:
        today = datetime.date.fromisoformat(args.today)
    else:
        today = datetime.date.today()
    symbols = stock_symbols(args.kite)
    if args.count_only or not args.only:
        print(format_plan(plan(args.root, symbols, today)), flush=True)
        if args.count_only:
            return 0
        print("pass --only. Run these in Terminal, not from Cursor:", flush=True)
        for line in COMMANDS:
            print(line, flush=True)
        return 2
    download(args.root, symbols, today, args.only)
    return 0


if __name__ == "__main__":
    sys.exit(main())
