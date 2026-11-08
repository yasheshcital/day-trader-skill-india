"""Attempt 18 checks. Synthetic data, plus the Track A record text."""

import datetime
import os
import shutil
import tempfile
import unittest

from _load import load

b = load("india/research", "batch18")


class TrackARecord(unittest.TestCase):
    def test_track_a_record_text(self):
        root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, root)
        experiments = os.path.join(root, "EXPERIMENTS.md")
        with open(experiments, "w", encoding="utf-8") as fh:
            fh.write("# log\n\n## Attempt 18\n\nrules\n\n## Forward test\n\n")
        catalogue = os.path.join(root, "STRATEGIES.md")
        with open(catalogue, "w", encoding="utf-8") as fh:
            fh.write("\n".join([
                "## Families",
                "",
                "| Family | Holdout used |",
                "|---|---|",
                "| sector rotation | no |",
                "",
                "## Watch",
                "",
                "| Name | Attempt | Note |",
                "|---|---|---|",
                "| tom rsi20 | 17 | note |",
                "",
                "## Closed",
                "",
                "| Name | Attempt | Note |",
                "|---|---|---|",
                "| sector 13w | 17 | FAIL |",
                "",
                "## Sources",
                "",
            ]))
        log_path = os.path.join(root, "HOLDOUT_LOG.md")
        with open(log_path, "w", encoding="utf-8") as fh:
            fh.write("old line\n")
        b.record_track_a(experiments, catalogue, log_path)
        with open(experiments, encoding="utf-8") as fh:
            text = fh.read()
        self.assertLess(text.find("## Attempt 17-A"), text.find("## Attempt 18"))
        for piece in (
            "Attempt 17-A (AlgoTest options selling)",
            "09:20 entry, 15:15 exit, weekly expiry, 1 lot",
            "AlgoTest taxes and charges + Rs 20 per order",
            "S1 ATM straddle 25% SL",
            "net Rs 3.55L, monthly t 3.82, PASS",
            "net Rs 27.7k, t 0.37, FAIL",
            "S2 ATM straddle 50% SL",
            "net Rs 3.40L, monthly t 3.73, PASS",
            "At 0.5% slippage t 1.82, at 1% slippage t -0.10",
            "net Rs 84.1k, t 1.10, FAIL",
            "S3 OTM4 strangle 50% SL",
            "net Rs 1.86L, monthly t 3.54, PASS",
            "net Rs 23.3k, t 0.53, FAIL",
            "S4 iron fly with OTM8 wings, no leg SL",
            "net Rs -2.39L, monthly t -2.90, FAIL",
            "no holdout run",
            "replication, not a holdout",
            "t 5.48 at 0% slippage, 3.64 at 0.5% slippage, 1.68 at 1% slippage",
        ):
            self.assertIn(piece, text)
        with open(catalogue, encoding="utf-8") as fh:
            catalogue_text = fh.read()
        watch = catalogue_text.split("## Watch")[1].split("## ")[0]
        closed = catalogue_text.split("## Closed")[1].split("## ")[0]
        self.assertIn("S2 ATM straddle 50% SL", watch)
        self.assertIn("slippage-sensitive; BANKNIFTY weekly discontinued", watch)
        self.assertNotIn("S2 ATM straddle 50% SL", closed)
        self.assertIn("S4 iron fly OTM8", closed)
        self.assertIn("| options selling | yes |", catalogue_text)
        with open(log_path, encoding="utf-8") as fh:
            logged = fh.read()
        self.assertIn("old line", logged)
        self.assertIn(b.HOLDOUT_LINE, logged)


class DecayRegression(unittest.TestCase):
    def test_decay_regression_on_a_known_slope(self):
        slope, t = b.ols_slope([0.0, 1.0, 2.0], [0.0, 0.0, 3.0])
        self.assertAlmostEqual(slope, 1.5)
        self.assertAlmostEqual(t, 1.5 / (0.75 ** 0.5))
        self.assertEqual(b.decay_label(slope, t), "stable")
        perfect, perfect_t = b.ols_slope([0.0, 1.0, 2.0], [0.0, 1.0, 2.0])
        self.assertAlmostEqual(perfect, 1.0)
        self.assertEqual(perfect_t, float("inf"))
        self.assertEqual(b.decay_label(perfect, perfect_t), "stable")
        down, down_t = b.ols_slope([0.0, 1.0, 2.0], [2.0, 1.0, 0.0])
        self.assertAlmostEqual(down, -1.0)
        self.assertEqual(down_t, float("-inf"))
        self.assertEqual(b.decay_label(down, down_t), "decaying")
        self.assertEqual(b.decay_label(-0.1, -1.0), "stable")


class OvernightSplit(unittest.TestCase):
    def test_overnight_intraday_split_on_three_days(self):
        rows = b.split_series([
            (datetime.date(2024, 1, 2), 100.0, 110.0),
            (datetime.date(2024, 1, 3), 112.0, 108.0),
            (datetime.date(2024, 1, 4), 107.0, 109.0),
        ])
        self.assertEqual(len(rows), 3)
        self.assertIsNone(rows[0]["overnight"])
        self.assertAlmostEqual(rows[0]["intraday"], (110.0 / 100.0 - 1.0) * 100.0)
        self.assertAlmostEqual(rows[1]["overnight"], (112.0 / 110.0 - 1.0) * 100.0)
        self.assertAlmostEqual(rows[1]["intraday"], (108.0 / 112.0 - 1.0) * 100.0)
        self.assertAlmostEqual(rows[2]["overnight"], (107.0 / 108.0 - 1.0) * 100.0)
        self.assertAlmostEqual(rows[2]["intraday"], (109.0 / 107.0 - 1.0) * 100.0)
        self.assertEqual(rows[1]["prev"], datetime.date(2024, 1, 2))
        self.assertEqual(rows[2]["prev_close"], 108.0)
