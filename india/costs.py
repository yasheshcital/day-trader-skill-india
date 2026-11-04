"""Round-trip cost of one NSE intraday equity trade. Standard library only.

Check RATES against your broker's calculator before you trust a rupee total.
A percentage is "percent of that side's value" (0.03 means 0.03%, not 3%).
Nothing here places an order.
"""

from decimal import Decimal

# Usual cash-segment intraday schedule. Check it against your broker's calculator:
# the exchange and SEBI rates move, and the brokerage cap is your broker's, not the exchange's.
RATES = {
    "brokerage_pct": Decimal("0.03"),    # per executed order (buy and sell are each an order)
    "brokerage_cap": Decimal("20"),      # rupees, per executed order
    "stt_pct": Decimal("0.025"),         # on the sell value
    "exchange_pct": Decimal("0.00297"),  # on both sides
    "sebi_pct": Decimal("0.0001"),       # on both sides
    "stamp_pct": Decimal("0.003"),       # on the buy value
    "gst_pct": Decimal("18"),            # on brokerage + exchange + SEBI
}


def _d(x, what):
    try:
        if isinstance(x, float):
            return Decimal(repr(x))
        return Decimal(str(x))
    except Exception:
        raise ValueError("%s is not a number: %r" % (what, x))


def _pct(value, key):
    return value * RATES[key] / Decimal("100")


def breakdown(buy, sell, shares):
    """Each charge, and the total, as exact Decimals in rupees.

    Brokerage is 0.03% of each order, capped at Rs 20 a side. STT is on the
    sell value, stamp duty on the buy value, exchange and SEBI on both.
    GST is 18% of brokerage + exchange + SEBI.
    """
    buy_px = _d(buy, "buy price")
    sell_px = _d(sell, "sell price")
    n = _d(shares, "shares")
    if buy_px <= 0 or sell_px <= 0:
        raise ValueError("buy and sell prices must be above 0")
    if n != n.to_integral_value() or n < 0:
        raise ValueError("shares must be a whole number, not %r" % (shares,))
    if n == 0:
        zero = Decimal("0")
        return {"brokerage": zero, "stt": zero, "exchange": zero, "sebi": zero,
                "stamp": zero, "gst": zero, "total": zero}
    buy_value = buy_px * n
    sell_value = sell_px * n
    cap = RATES["brokerage_cap"]
    brokerage = min(_pct(buy_value, "brokerage_pct"), cap) + min(_pct(sell_value, "brokerage_pct"), cap)
    stt = _pct(sell_value, "stt_pct")
    exchange = _pct(buy_value + sell_value, "exchange_pct")
    sebi = _pct(buy_value + sell_value, "sebi_pct")
    stamp = _pct(buy_value, "stamp_pct")
    gst = _pct(brokerage + exchange + sebi, "gst_pct")
    total = brokerage + stt + exchange + sebi + stamp + gst
    return {"brokerage": brokerage, "stt": stt, "exchange": exchange, "sebi": sebi,
            "stamp": stamp, "gst": gst, "total": total}


def round_trip(buy, sell, shares):
    """Total round-trip cost in rupees."""
    return breakdown(buy, sell, shares)["total"]
