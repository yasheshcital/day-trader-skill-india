"""Step 25 checks. Synthetic files only. The real logs are not touched."""

import csv
import datetime
import gzip
import os
import shutil
import tempfile
import unittest

from _load import ROOT, load

data = load("india/research", "data")
fwd = load("india/research", "forward")
b = load("india/research", "batch19")


class OptionHygiene(unittest.TestCase):
    def test_first_traded_skips_volume_zero(self):
        root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, root)
        path = os.path.join(root, "opt.csv.gz")
        with gzip.open(path, "wt", encoding="utf-8", newline="") as fh:
            writer = csv.writer(fh)
            writer.writerow(["datetime_start_ist", "open", "high", "low", "close", "volume"])
            writer.writerow(["2024-01-02 09:15:00", "1", "1", "1", "1", "0"])
            writer.writerow(["2024-01-03 09:15:00", "2", "2", "2", "2", "0.0"])
            writer.writerow(["2024-01-04 09:15:00", "3", "4", "2", "3.5", "10"])
            writer.writerow(["2024-01-05 09:15:00", "4", "4", "4", "4", ""])
            writer.writerow(["2024-01-08 09:15:00", "5", "5", "5", "5", "7"])
        self.assertEqual(data.first_traded(path), datetime.date(2024, 1, 4))
        bars = data.load_option_bars(path)
        self.assertEqual(
            [bar["date"] for bar in bars],
            [datetime.date(2024, 1, 4), datetime.date(2024, 1, 8)])
        self.assertEqual(bars[0]["volume"], 10.0)
        self.assertEqual(bars[0]["close"], 3.5)

    def test_all_zero_volume_returns_none(self):
        root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, root)
        path = os.path.join(root, "quiet.csv.gz")
        with gzip.open(path, "wt", encoding="utf-8", newline="") as fh:
            writer = csv.writer(fh)
            writer.writerow(["datetime_start_ist", "open", "high", "low", "close", "volume"])
            writer.writerow(["2024-02-01 09:15:00", "1", "1", "1", "1", "0"])
        self.assertIsNone(data.first_traded(path))
        self.assertEqual(data.load_option_bars(path), [])


class ForwardRefusal(unittest.TestCase):
    def test_old_dates_are_refused(self):
        cutoff = datetime.date(2026, 11, 4)
        later = datetime.date(2026, 11, 5)
        self.assertRaises(fwd.ForwardRefused, fwd.check_date, cutoff)
        self.assertRaises(fwd.ForwardRefused, fwd.check_date, datetime.date(2026, 11, 3))
        self.assertRaises(fwd.ForwardRefused, fwd.run_dates, [later, cutoff])
        self.assertIsNone(fwd.check_date(later))
        self.assertEqual(fwd.run_dates([later]), [later])
        self.assertEqual(fwd.run_dates([]), [])
        with open(os.path.join(ROOT, "india", "research", "forward.py"), encoding="utf-8") as fh:
            source = fh.read()
        self.assertNotIn("HOLDOUT_LOG", source)
        self.assertNotIn("final=True", source)
        self.assertIsNone(fwd.constituents_of("Constituents: pending the study.\n"))
        self.assertEqual(
            fwd.constituents_of("Constituents: rsi2 < 5, m2 regime, tom rsi20.\n"),
            ["rsi2 < 5", "m2 regime", "tom rsi20"])

    def test_rules_are_written_before_attempt_19(self):
        root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, root)
        experiments = os.path.join(root, "EXPERIMENTS.md")
        with open(experiments, "w", encoding="utf-8") as fh:
            fh.write("# log\n\n## Attempt 18\n\nkeep the attempt 18 text\n\n## Forward test\n\n")
        catalogue = os.path.join(root, "STRATEGIES.md")
        with open(catalogue, "w", encoding="utf-8") as fh:
            fh.write("\n".join([
                "## Families",
                "",
                "| Family | Holdout used |",
                "|---|---|",
                "| pre-holiday | no |",
                "",
                "## Closed",
                "",
                "| Name | Attempt | Note |",
                "|---|---|---|",
                "| pre-holiday | 18 | FAIL |",
                "",
            ]))
        b.write_rules(experiments, catalogue)
        with open(experiments, encoding="utf-8") as fh:
            text = fh.read()
        self.assertLess(text.find("## Attempt 18"), text.find("## Forward book v1"))
        self.assertLess(text.find("## Forward book v1"), text.find("## Attempt 19"))
        self.assertLess(text.find("## Attempt 19"), text.find("## Forward test"))
        self.assertIn("keep the attempt 18 text", text)
        self.assertIn("Constituents: pending the study.", text)
        self.assertIn("last Thursday", text)
        self.assertIn("last Tuesday", text)
        self.assertNotIn("\u2014", text)
        with open(catalogue, encoding="utf-8") as fh:
            catalogue_text = fh.read()
        self.assertIn("| futures basis | no |", catalogue_text)
        self.assertIn("| pre-holiday | 18 | FAIL |", catalogue_text)
        with open(os.path.join(ROOT, "india", "research", "batch19.py"), encoding="utf-8") as fh:
            source = fh.read()
        self.assertEqual(source.count("final=True)"), 1)
        self.assertNotIn("\u2014", source)


class BasisRule(unittest.TestCase):
    def test_expiry_and_annualised_basis(self):
        august = b.raw_expiry(2025, 8)
        september = b.raw_expiry(2025, 9)
        self.assertEqual(august, datetime.date(2025, 8, 28))
        self.assertEqual(august.weekday(), 3)
        self.assertEqual(september, datetime.date(2025, 9, 30))
        self.assertEqual(september.weekday(), 1)
        self.assertEqual(b.raw_expiry(2012, 1), b.b16.last_thursday(2012, 1))
        day = datetime.date(2020, 1, 2)
        expiry = datetime.date(2021, 1, 1)
        self.assertEqual((expiry - day).days, 365)
        self.assertAlmostEqual(b.annualised(110.0, 100.0, day, expiry), 0.10)
        self.assertIsNone(b.annualised(110.0, 100.0, expiry, expiry))
        self.assertEqual(b.PRIOR, 250)
        self.assertEqual(b.LOW_RANK, 50)
        self.assertEqual(b.HOLD, 5)

    def test_least_correlated_trio_breaks_ties_on_the_name(self):
        names = ["a", "b", "c", "d"]
        matrix = {}
        pairs = {
            ("a", "b"): 0.9, ("a", "c"): 0.9, ("a", "d"): 0.0,
            ("b", "c"): 0.9, ("b", "d"): 0.0, ("c", "d"): 0.0,
        }
        for (left, right), value in pairs.items():
            matrix[(left, right)] = value
            matrix[(right, left)] = value
        trio, avg = b.least_correlated(names, matrix)
        self.assertEqual(trio, ("a", "b", "d"))
        self.assertAlmostEqual(avg, 0.3)
        self.assertAlmostEqual(b.pearson([1.0, 2.0, 3.0, 4.0], [1.0, 2.0, 3.0, 4.0]), 1.0)
        self.assertAlmostEqual(b.pearson([1.0, 2.0, 3.0, 4.0], [4.0, 3.0, 2.0, 1.0]), -1.0)
        self.assertIsNone(b.pearson([1.0, 1.0, 1.0, 1.0], [1.0, 2.0, 3.0, 4.0]))
        self.assertIsNone(b.pearson([1.0, 2.0], [3.0, 4.0]))
        flat = []
        for month in range(1, 13):
            flat.append((2005, month, 0.0))
        stats = b.curve_stats(flat)
        self.assertAlmostEqual(stats["cagr"], 0.0)
        self.assertAlmostEqual(stats["dd"], 0.0)
        self.assertEqual(stats["positive"], 0)
        self.assertEqual(stats["years"], 1)
        self.assertEqual(b.stats_line("flat", stats).split("|")[-1].strip(), "0/1")


if __name__ == "__main__":
    unittest.main()
