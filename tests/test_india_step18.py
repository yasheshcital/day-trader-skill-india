"""Survivorship calibration. Synthetic bars only. No kite cache is read."""

import datetime
import os
import shutil
import tempfile
import unittest

from _load import load

sv = load("india/research", "survivorship")
h = load("india/research", "harness")
data = load("india/research", "data")


def _write_daily(path, rows):
    import csv
    import gzip
    folder = os.path.dirname(path)
    if folder and not os.path.isdir(folder):
        os.makedirs(folder)
    fields = ["datetime_start_ist", "open", "high", "low", "close", "volume"]
    with gzip.open(path, "wt", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({
                "datetime_start_ist": "%s 00:00:00" % row["date"].isoformat(),
                "open": row["open"], "high": row["high"], "low": row["low"],
                "close": row["close"], "volume": row["volume"],
            })


def _bar(day, close, open_=None):
    price = close if open_ is None else open_
    return {"date": day, "open": price, "high": close, "low": close, "close": close, "volume": 1}


class IndexList(unittest.TestCase):
    def test_the_factor_names_and_a_raw_first_date(self):
        names = sv.select_indices([
            "NIFTY 50",
            "NIFTY 200",
            "nifty200momentm30",
            "NIFTY100 QUALTY30",
            "NIFTY LOW VOL 50",
            "NIFTY100 EQL WGT",
            "NIFTY 200",
            "RELIANCE",
        ])
        self.assertEqual(names, [
            "NIFTY 200",
            "NIFTY LOW VOL 50",
            "NIFTY100 EQL WGT",
            "NIFTY100 QUALTY30",
            "nifty200momentm30",
        ])
        folder = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, folder)
        path = os.path.join(folder, "NIFTY 200.csv.gz")
        _write_daily(path, [
            _bar(datetime.date(2005, 4, 1), 100),
            _bar(datetime.date(2005, 4, 4), 101),
        ])
        first, last = sv.raw_span(path)
        self.assertEqual(first, datetime.date(2005, 4, 1))
        self.assertEqual(last, datetime.date(2005, 4, 4))


class BiasMath(unittest.TestCase):
    def test_close_to_close_cagr_and_years(self):
        start = datetime.date(2005, 1, 1)
        end = datetime.date(2015, 1, 1)
        cagr = sv.close_cagr([start, end], [100.0, 200.0])
        years = (end - start).days / 365.25
        expected = (2.0 ** (1.0 / years) - 1.0) * 100.0
        self.assertAlmostEqual(cagr, expected, places=6)
        yearly = sv.yearly_returns(
            [datetime.date(2010, 1, 4), datetime.date(2010, 12, 31), datetime.date(2011, 12, 30)],
            [100.0, 110.0, 121.0])
        self.assertAlmostEqual(yearly[2010], 10.0)
        self.assertAlmostEqual(yearly[2011], 10.0)

    def test_bias_is_random_minus_the_index_and_comes_off_momentum(self):
        self.assertAlmostEqual(sv.bias_cagr(12.0, 10.0), 2.0)
        self.assertAlmostEqual(sv.adjusted_cagr(15.0, 2.0), 13.0)
        bias_years = sv.year_diff({2010: 12.0, 2011: 8.0}, {2010: 10.0, 2011: 9.0})
        self.assertAlmostEqual(bias_years[2010], 2.0)
        self.assertAlmostEqual(bias_years[2011], -1.0)
        self.assertNotIn(2012, bias_years)

    def test_shared_dates_drive_the_report(self):
        d1 = datetime.date(2010, 1, 4)
        d2 = datetime.date(2011, 1, 4)
        calendar = [d1, d2]
        nifty200 = {d1: {"close": 100.0}, d2: {"close": 100.0}}
        momentum = {d1: {"close": 100.0}, d2: {"close": 110.0}}
        random_paths = [[100.0, 120.0], [100.0, 140.0]]
        mom = [100.0, 150.0]
        report = sv.build_report(calendar, mom, random_paths, nifty200, momentum)
        self.assertGreater(report["bias"], 0.0)
        self.assertAlmostEqual(
            report["adjusted"], report["mom"]["mean_cagr"] - report["bias"], places=6)
        self.assertAlmostEqual(report["mom"]["index_cagr"], sv.close_cagr([d1, d2], [100.0, 110.0]))
        self.assertIn(2010, report["bias_years"])

    def test_the_k30_seed_is_the_attempt_11_draw(self):
        index, spec = sv.spec_named(sv.K30_NAME)
        self.assertEqual(spec["k"], 30)
        self.assertFalse(spec["filter"])
        self.assertEqual(h.SEED + index * 1000, h.SEED + 4000)
        passer = sv.spec_named(sv.PASSER_NAME)[1]
        self.assertEqual(passer["k"], 20)
        self.assertTrue(passer["filter"])


class NotesAndHoldoutGuard(unittest.TestCase):
    def _report(self):
        d1 = datetime.date(2010, 1, 4)
        d2 = datetime.date(2011, 12, 30)
        return {
            "runs": 100,
            "seed": h.SEED + 4000,
            "bias": 2.0,
            "adjusted": 8.0,
            "bias_years": {2010: 1.5},
            "adjusted_years": {2010: 3.5},
            "broad": {
                "dates": [d1, d2],
                "mean_cagr": 12.0,
                "index_cagr": 10.0,
            },
            "mom": {
                "dates": [d1, d2],
                "mean_cagr": 10.0,
                "index_cagr": 9.0,
                "mean_yearly": {2010: 5.0},
                "index_yearly": {2010: 4.0},
            },
        }

    def test_the_note_names_the_quote_and_the_method(self):
        text = sv.format_calibration(self._report())
        self.assertIn(sv.QUOTE, text)
        self.assertIn("18.8% CAGR", text)
        self.assertIn("13.6%", text)
        self.assertIn("HDFC MF, Jul 2026", text)
        self.assertIn("no volatility scaling", text)
        self.assertIn("no 5% caps", text)
        self.assertIn("equal weight", text)
        self.assertIn("pass mark is unchanged", text)
        self.assertIn("2010 | +1.500% | +5.000% | +3.500% | +4.000%", text)
        self.assertNotIn("\u2014", text)

    def test_install_keeps_attempt_11_and_the_forward_test(self):
        folder = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, folder)
        path = os.path.join(folder, "EXPERIMENTS.md")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("\n".join([
                "| 11 | 2026-11-06 | mom 12-1 K20 above200 | r | d | 1 | +35% | +4.82 | PASS |",
                "",
                "## Attempt 11",
                "",
                "Rules fixed on 2026-11-06, before the run.",
                "",
                "Variants that pass: 1 of 12.",
                "",
                "## Forward test",
                "",
                "Started.",
                "",
            ]))
        sv.install(path, sv.format_calibration(self._report()))
        with open(path, encoding="utf-8") as fh:
            early = fh.read()
        self.assertIn("| 11 |", early)
        self.assertIn("Rules fixed on 2026-11-06, before the run.", early)
        self.assertIn(sv.QUOTE, early)
        self.assertLess(early.find("### Survivorship calibration"), early.find("## Forward test"))
        self.assertIn("Started.", early)
        block = {
            "dates": [datetime.date(2025, 1, 2), datetime.date(2025, 6, 30)],
            "cagr": 1.0, "max_dd": -2.0, "excess": 0.5, "n_months": 6,
        }
        nifty = {"cagr": 0.4, "max_dd": -3.0}
        mom = {
            "dates": block["dates"],
            "cagr": 0.2, "max_dd": -1.0, "excess": 0.1,
        }
        sv.install(path, sv.format_holdout(block, nifty, mom, self._report()))
        with open(path, encoding="utf-8") as fh:
            later = fh.read()
        self.assertLess(later.find("### Survivorship calibration"), later.find("### Holdout"))
        self.assertLess(later.find("### Holdout"), later.find("## Forward test"))
        self.assertIn("final=True", later)
        self.assertIn("The attempt 11 rule is unchanged.", later)
        self.assertIn("| 11 |", later)
        self.assertEqual(later.count("### Survivorship calibration"), 1)
        sv.install(path, sv.format_calibration(self._report()))
        with open(path, encoding="utf-8") as fh:
            again = fh.read()
        self.assertEqual(again.count("### Survivorship calibration"), 1)
        self.assertIn("### Holdout", again)
        self.assertNotIn("\u2014", again)

    def test_the_holdout_stays_locked_until_final(self):
        root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, root)
        kite = os.path.join(root, "kite")
        rows = []
        day = datetime.date(2024, 12, 1)
        for i in range(30):
            rows.append(_bar(day + datetime.timedelta(days=i), 10))
        rows.append(_bar(datetime.date(2025, 1, 2), 11))
        _write_daily(data.bar_path(kite, "day", "AAA"), rows)
        log_path = os.path.join(root, "holdout-log.md")
        real = data.HOLDOUT_LOG
        before = os.path.getsize(real) if os.path.isfile(real) else None
        with self.assertRaises(data.HoldoutError):
            data.load_arrays(kite, "AAA", "day", end=datetime.date(2025, 1, 2))
        quiet = data.load_arrays(kite, "AAA", "day", end=datetime.date(2024, 12, 31))
        dates = [item["date"] for segment in quiet.segments for item in segment]
        self.assertTrue(dates)
        self.assertTrue(all(day < data.HOLDOUT_START for day in dates))
        opened = data.load_arrays(
            kite, "AAA", "day", final=True, log_path=log_path, end=datetime.date(2025, 1, 2))
        opened_dates = [item["date"] for segment in opened.segments for item in segment]
        self.assertIn(datetime.date(2025, 1, 2), opened_dates)
        with open(log_path, encoding="utf-8") as fh:
            logged = fh.read()
        self.assertIn("Holdout log", logged)
        self.assertIn("\t", logged)
        after = os.path.getsize(real) if os.path.isfile(real) else None
        self.assertEqual(before, after)
