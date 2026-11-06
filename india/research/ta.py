"""Daily technical indicators. Standard library only.

Bollinger bands use the population standard deviation (the mean of the squared
deviations, divisor n). RSI and ATR use Wilder's smoothing. A 20-day or
52-week extreme is the prior window only: today's bar is not inside it.
"""

import collections


def sma(values, n):
    """Mean of the last n values, or None when fewer than n are present."""
    if n <= 0 or values is None or len(values) < n:
        return None
    total = 0.0
    start = len(values) - n
    for i in range(start, len(values)):
        total += values[i]
    return total / float(n)


def sma_series(values, n):
    """SMA aligned to values. Leading slots are None until n values exist."""
    out = [None] * len(values)
    if n <= 0:
        return out
    total = 0.0
    for i in range(len(values)):
        total += values[i]
        if i >= n:
            total -= values[i - n]
        if i >= n - 1:
            out[i] = total / float(n)
    return out


def ema_series(values, n):
    """EMA seeded with the SMA of the first n values. Multiplier is 2/(n+1)."""
    out = [None] * len(values)
    if n <= 0 or len(values) < n:
        return out
    total = 0.0
    for i in range(n):
        total += values[i]
    prev = total / float(n)
    out[n - 1] = prev
    k = 2.0 / float(n + 1)
    keep = 1.0 - k
    for i in range(n, len(values)):
        prev = values[i] * k + prev * keep
        out[i] = prev
    return out


def true_range(high, low, prev_close):
    """One bar's true range, using the previous close for the gaps."""
    span = high - low
    up = high - prev_close
    if up < 0:
        up = -up
    down = low - prev_close
    if down < 0:
        down = -down
    if span >= up and span >= down:
        return span
    if up >= down:
        return up
    return down


def atr_series(high, low, close, n=14):
    """Wilder ATR. The first value is the mean of the first n true ranges."""
    out = [None] * len(close)
    if n <= 0 or len(close) <= n:
        return out
    total = 0.0
    for i in range(1, n + 1):
        total += true_range(high[i], low[i], close[i - 1])
    prev = total / float(n)
    out[n] = prev
    for i in range(n + 1, len(close)):
        tr = true_range(high[i], low[i], close[i - 1])
        prev = (prev * float(n - 1) + tr) / float(n)
        out[i] = prev
    return out


def _rsi(avg_gain, avg_loss):
    if avg_loss == 0:
        if avg_gain == 0:
            return 50.0
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


def rsi_series(close, n=14):
    """Wilder RSI. The first average is the mean of the first n changes."""
    out = [None] * len(close)
    if n <= 0 or len(close) <= n:
        return out
    gain_sum = 0.0
    loss_sum = 0.0
    for i in range(1, n + 1):
        change = close[i] - close[i - 1]
        if change >= 0:
            gain_sum += change
        else:
            loss_sum += -change
    avg_gain = gain_sum / float(n)
    avg_loss = loss_sum / float(n)
    out[n] = _rsi(avg_gain, avg_loss)
    for i in range(n + 1, len(close)):
        change = close[i] - close[i - 1]
        gain = change if change > 0 else 0.0
        loss = -change if change < 0 else 0.0
        avg_gain = (avg_gain * float(n - 1) + gain) / float(n)
        avg_loss = (avg_loss * float(n - 1) + loss) / float(n)
        out[i] = _rsi(avg_gain, avg_loss)
    return out


def bollinger_series(close, n=20, k=2.0):
    """(middle, upper, lower, width). Width is (upper - lower) / middle.

    The deviation is the population figure: sum of squared deviations over n.
    """
    mid = sma_series(close, n)
    upper = [None] * len(close)
    lower = [None] * len(close)
    width = [None] * len(close)
    if n <= 0:
        return mid, upper, lower, width
    for i in range(n - 1, len(close)):
        center = mid[i]
        if not center:
            continue
        var = 0.0
        start = i - n + 1
        for j in range(start, i + 1):
            diff = close[j] - center
            var += diff * diff
        std = (var / float(n)) ** 0.5
        up = center + k * std
        lo = center - k * std
        upper[i] = up
        lower[i] = lo
        width[i] = (up - lo) / center
    return mid, upper, lower, width


def _prior_series(values, n, high):
    """Prior n-bar extreme, excluding the current bar. None until n bars exist."""
    out = [None] * len(values)
    if n <= 0:
        return out
    dq = collections.deque()
    for i in range(len(values)):
        left = i - n
        while dq and dq[0] < left:
            dq.popleft()
        if i >= n and dq:
            out[i] = values[dq[0]]
        value = values[i]
        if high:
            while dq and values[dq[-1]] <= value:
                dq.pop()
        else:
            while dq and values[dq[-1]] >= value:
                dq.pop()
        dq.append(i)
    return out


def prior_high_series(values, n):
    """Highest value of the previous n bars."""
    return _prior_series(values, n, True)


def prior_low_series(values, n):
    """Lowest value of the previous n bars."""
    return _prior_series(values, n, False)


def trailing_is_min(values, n):
    """True when values[i] equals the minimum of the n bars ending at i."""
    out = [False] * len(values)
    if n <= 0:
        return out
    dq = collections.deque()
    run = 0
    for i in range(len(values)):
        value = values[i]
        if value is None:
            dq.clear()
            run = 0
            continue
        run += 1
        while dq and dq[0] <= i - n:
            dq.popleft()
        if run >= n and dq and value <= values[dq[0]]:
            out[i] = True
        elif run >= n and not dq:
            out[i] = True
        while dq and values[dq[-1]] > value:
            dq.pop()
        dq.append(i)
    return out


def bullish_engulfing(prev_open, prev_close, today_open, today_close):
    """A bullish body that covers the previous bearish body, wicks ignored."""
    if not prev_close < prev_open:
        return False
    if not today_close > today_open:
        return False
    if today_open > prev_close:
        return False
    if today_close < prev_open:
        return False
    return True
