#!/usr/bin/env python3
"""Forward record. Sessions strictly after 2026-11-04.

The rules are the six frozen books and Forward book v1. This script does not
place an order.

    python3 india/research/forward.py
"""

import datetime
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from india.research import data

CUTOFF = datetime.date(2026, 11, 4)
FORWARD_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "FORWARD.md")
STRATEGIES = (
    "rsi2 < 5",
    "m2 regime",
    "rel rsi5",
    "rel rsi5 stock10",
    "tom rsi20",
    "mom 12-1 K20 above200",
)


class ForwardRefused(Exception):
    """The forward record was asked to score a session on or before the cutoff."""


def check_date(day):
    """Refuse any session on or before 2026-11-04."""
    if day <= CUTOFF:
        raise ForwardRefused(
            "forward record refuses %s, which is on or before %s"
            % (day.isoformat(), CUTOFF.isoformat()))


def run_dates(dates):
    """Return the dates when every one is after the cutoff. Otherwise refuse."""
    kept = []
    for day in dates:
        check_date(day)
        kept.append(day)
    return kept


def constituents_of(text):
    """The frozen trio, or None while the line still says pending."""
    for line in text.splitlines():
        if not line.startswith("Constituents:"):
            continue
        rest = line.split(":", 1)[1].strip().rstrip(".")
        if not rest or rest.startswith("pending"):
            return None
        names = []
        for part in rest.split(","):
            name = part.strip()
            if name:
                names.append(name)
        return names or None
    return None


def sessions_after(root):
    """NIFTY 50 daily sessions strictly after the cutoff. No holdout log."""
    try:
        bars = data.read_daily_bars(root, "NIFTY 50")
    except data.DataError:
        return []
    found = []
    seen = set()
    for bar in bars:
        if bar["date"] <= CUTOFF or bar["date"] in seen:
            continue
        seen.add(bar["date"])
        found.append(bar["date"])
    found.sort()
    return run_dates(found)


def _zero_lines(names):
    lines = ["No NIFTY 50 session after %s." % CUTOFF.isoformat()]
    for name in STRATEGIES:
        lines.append("%s | trades 0 | avg n/a | t n/a" % name)
    if names:
        lines.append("Forward book v1 (%s) | trades 0 | avg n/a | t n/a" % ", ".join(names))
    else:
        lines.append("Forward book v1 | constituents pending | trades 0 | avg n/a | t n/a")
    return lines


def append_block(path, lines, stamp=None):
    """Append one dated block. Does not touch the holdout log."""
    day = stamp or datetime.date.today()
    block = ["## %s" % day.isoformat(), ""]
    block.extend(lines)
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        if text and not text.endswith("\n"):
            text += "\n"
    else:
        text = "# Forward record\n\nSessions after 2026-11-04. Nothing here places an order.\n\n"
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text + "\n".join(block) + "\n")


def main(argv=None, log=None):
    import argparse
    parser = argparse.ArgumentParser(description="Forward record. Nothing is placed.")
    parser.add_argument("--root", default=os.path.join("data", "kite"))
    parser.add_argument("--experiments", default=os.path.join(_ROOT, "india", "EXPERIMENTS.md"))
    parser.add_argument("--forward", default=FORWARD_PATH)
    parser.add_argument("--industries", default=os.path.join(_ROOT, "india", "universe", "nifty500.csv"))
    args = parser.parse_args(argv)
    emit = log or (lambda line: print(line, flush=True))
    with open(args.experiments, encoding="utf-8") as fh:
        names = constituents_of(fh.read())
    dates = sessions_after(args.root)
    if dates:
        from india.research import batch19
        lines = batch19.forward_lines(args.root, dates, names, args.industries, emit)
    else:
        lines = _zero_lines(names)
    append_block(args.forward, lines)
    for line in lines:
        emit(line)
    emit("forward block appended to %s" % args.forward)
    return lines


if __name__ == "__main__":
    main()
