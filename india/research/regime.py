"""The market type known before the open.

It is read from NIFTY 50 daily closes up to the previous session. "up" when
that close is above the 200-day average and the average is higher than it was
20 sessions earlier. "down" when the close is below the average and the
average is lower than it was 20 sessions earlier. A tie, or a flat average,
is "sideways". Fewer than 220 prior closes has no type.
"""

SMA = 200
SLOPE = 20


def classify(closes):
    """closes are daily closes through yesterday, oldest first. None until 220 exist."""
    if closes is None or len(closes) < SMA + SLOPE:
        return None
    window = closes[-SMA:]
    earlier = closes[-(SMA + SLOPE):-SLOPE]
    sma = sum(window) / float(SMA)
    prev = sum(earlier) / float(SMA)
    close = closes[-1]
    if close > sma and sma > prev:
        return "up"
    if close < sma and sma < prev:
        return "down"
    return "sideways"


def by_date(points):
    """(date, close) in date order. The type for a date uses only earlier closes."""
    closes = []
    out = {}
    for day, close in points:
        kind = classify(closes)
        if kind is not None:
            out[day] = kind
        closes.append(close)
    return out
