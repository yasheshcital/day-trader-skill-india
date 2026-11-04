"""Shared NSE calendar and clock. India Standard Time is a fixed UTC+5:30
(India has no daylight saving). Naive datetimes only, in the same style as
eastern_offset / to_eastern / eastern_to_utc in trader-entry/entry.py.

Nothing here places an order, and no trader-* script imports this yet.
"""

import datetime

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


def round_to_tick(price, tick=0.05, down=True):
    """Round to the NSE tick (5 paise). down floors; down=False ceils.
    A price already on the tick stays put."""
    tick_paise = int(round(tick * 100))
    paise = int(round(float(price) * 100))
    rem = paise % tick_paise
    if rem:
        paise = paise - rem if down else paise + (tick_paise - rem)
    return paise / 100.0
