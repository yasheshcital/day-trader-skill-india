"""Shared NSE calendar and clock. India Standard Time is a fixed UTC+5:30
(India has no daylight saving). Naive datetimes only, in the same style as
eastern_offset / to_eastern / eastern_to_utc in trader-entry/entry.py.

Nothing here places an order, and no trader-* script imports this yet.
"""

import datetime
from decimal import Decimal

# Fixed offset. Not a zone: these helpers keep naive datetimes, like the
# New York ones, so the module stays on Python 3.8 (no zoneinfo).
IST = datetime.timedelta(hours=5, minutes=30)

OPEN = datetime.time(9, 15)
CLOSE = datetime.time(15, 30)
SESSION_MINUTES = 375  # 09:15 to 15:30

# 2026. Same dates and names as NSE_HOLIDAYS in trader-entry/entry.py.
# 2027 is not in that list yet.
NSE_HOLIDAYS = {
    "2026-01-15": "Maharashtra municipal elections",
    "2026-01-26": "Republic Day",
    "2026-03-03": "Holi",
    "2026-03-26": "Shri Ram Navami",
    "2026-03-31": "Shri Mahavir Jayanti",
    "2026-04-03": "Good Friday",
    "2026-04-14": "Dr. Baba Saheb Ambedkar Jayanti",
    "2026-05-01": "Maharashtra Day",
    "2026-05-28": "Bakri Id",
    "2026-06-26": "Muharram",
    "2026-09-14": "Ganesh Chaturthi",
    "2026-10-02": "Mahatma Gandhi Jayanti",
    "2026-10-20": "Dussehra",
    "2026-11-10": "Diwali Balipratipada",
    "2026-11-24": "Prakash Gurpurb Sri Guru Nanak Dev",
    "2026-12-25": "Christmas",
}


def to_ist(utc_dt):
    """Naive UTC -> naive IST."""
    return utc_dt.replace(tzinfo=None) + IST


def ist_to_utc(local_dt):
    """Naive IST -> naive UTC."""
    return local_dt.replace(tzinfo=None) - IST


def trading_day(d):
    """(is_trading_day, reason). Weekends and the NSE holiday list."""
    if d.weekday() >= 5:
        return False, "weekend"
    name = NSE_HOLIDAYS.get(d.isoformat())
    if name:
        return False, "NSE holiday: " + name
    return True, ""


def session(d):
    """(open_utc, close_utc) as naive UTC, or None if the NSE is closed all day."""
    ok, _ = trading_day(d)
    if not ok:
        return None
    open_utc = ist_to_utc(datetime.datetime.combine(d, OPEN))
    close_utc = ist_to_utc(datetime.datetime.combine(d, CLOSE))
    return open_utc, close_utc


def next_open(d):
    """Next session after date d, as 'YYYY-MM-DD 09:15' (IST), or None."""
    nd = d + datetime.timedelta(days=1)
    for _ in range(15):
        if session(nd):
            return "%s 09:15" % nd.isoformat()
        nd += datetime.timedelta(days=1)
    return None


# NSE cash-segment ticks since April 2025. Copied into trader-exit and
# trader-timemachine; those folders do not import this module.
INDEX_SYMBOLS = ("NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY", "SENSEX", "BANKEX")


def tick_for(price, symbol=None):
    """Cash-segment tick for this price. Indices always use 0.05.
    Below 250 -> 0.01; 250 to 1000 -> 0.05; above 1000 to 5000 -> 0.10;
    above 5000 to 10000 -> 0.50; above 10000 to 20000 -> 1.00; above 20000 -> 5.00."""
    # NSE reviews ticks monthly from the previous month-end close; we use the
    # entry price, which can differ near a band edge.
    sym = str(symbol or "").strip().upper()
    if sym in INDEX_SYMBOLS:
        return 0.05
    p = Decimal(str(price))
    if p < 250:
        return 0.01
    if p <= 1000:
        return 0.05
    if p <= 5000:
        return 0.10
    if p <= 10000:
        return 0.50
    if p <= 20000:
        return 1.00
    return 5.00


def round_to_tick(price, symbol=None, down=True, tick=None):
    """Round to the NSE tick. down floors; down=False ceils.
    A price already on the tick stays put. The tick comes from tick_for
    unless one is passed in."""
    if tick is None:
        tick = tick_for(price, symbol)
    tick_paise = int(round(float(tick) * 100))
    paise = int(round(float(price) * 100))
    rem = paise % tick_paise
    if rem:
        paise = paise - rem if down else paise + (tick_paise - rem)
    return paise / 100.0
