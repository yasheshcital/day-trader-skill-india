#!/usr/bin/env python3
"""Build data/cache from data/kite.

One symbol at a time, one read of each .csv.gz, written as a pickle of
per-session array columns. A pool of processes walks the symbols. A progress
line prints every 25 symbols, and again on the last symbol.

    python3 india/research/cache.py
    python3 india/research/cache.py --root data/kite

After the build, every 5-minute pickle is loaded and the load time is printed.
The target is under one minute.
"""

import os
import pickle
import sys
import time
from multiprocessing import Pool

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from india.research import data


def should_report(done, total):
    return total > 0 and (done % 25 == 0 or done == total)


def build_symbol(job):
    """Read one symbol once per interval and write its pickles. Returns the name."""
    root, symbol, cache_root = job
    for interval in ("day", "5minute"):
        src = data.bar_path(root, interval, symbol)
        if not os.path.isfile(src):
            continue
        payload = data.pack_bars(data.stream_bars(src), interval)
        dest = data.cache_file(root, interval, symbol, cache_root)
        folder = os.path.dirname(dest)
        if folder:
            os.makedirs(folder, exist_ok=True)
        with open(dest, "wb") as fh:
            pickle.dump(payload, fh, protocol=4)
    return symbol


def build_all(root, cache_root=None, workers=None, log=None):
    """Build every symbol. workers=0 stays in this process. Returns seconds, count."""
    symbols = data.symbols_in(root)
    jobs = [(os.path.abspath(root), symbol, cache_root) for symbol in symbols]
    total = len(jobs)
    emit = log or (lambda line: print(line, flush=True))
    started = time.time()
    done = 0
    if workers == 0 or total == 0:
        for job in jobs:
            build_symbol(job)
            done += 1
            if should_report(done, total):
                emit("%d / %d symbols" % (done, total))
    else:
        import india.research.cache as cache_mod
        pool_size = workers or os.cpu_count() or 1
        with Pool(pool_size) as pool:
            for _symbol in pool.imap_unordered(cache_mod.build_symbol, jobs):
                done += 1
                if should_report(done, total):
                    emit("%d / %d symbols" % (done, total))
    elapsed = time.time() - started
    emit("build time: %.1f s" % elapsed)
    return elapsed, total


def load_all(root, interval="5minute", cache_root=None):
    """Unpickle every cached symbol. The list stays resident for the timing."""
    symbols = data.symbols_in(root)
    started = time.time()
    payloads = []
    for symbol in symbols:
        path = data.cache_file(root, interval, symbol, cache_root)
        if not os.path.isfile(path):
            continue
        payloads.append(data.read_cache(path))
    return time.time() - started, payloads


def main(argv=None, log=None):
    import argparse
    parser = argparse.ArgumentParser(description="Build the research cache. Nothing is placed.")
    parser.add_argument("--root", default=os.path.join("data", "kite"))
    parser.add_argument("--workers", type=int, default=None)
    parser.add_argument("--skip-build", action="store_true")
    args = parser.parse_args(argv)
    emit = log or (lambda line: print(line, flush=True))
    if not args.skip_build:
        build_all(args.root, workers=args.workers, log=emit)
    _elapsed, payloads = load_all(args.root, "5minute")
    sessions = 0
    for payload in payloads:
        sessions += len(payload["sessions"])
    emit("load time: %.1f s for %d symbols (%d sessions)" % (_elapsed, len(payloads), sessions))
    return 0


if __name__ == "__main__":
    sys.exit(main())
