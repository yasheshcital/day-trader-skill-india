"""Step 29. Purpose parser, the INE filter, and factor priority."""

import unittest

from _load import load


class Step29Test(unittest.TestCase):
    def test_purpose_parser(self):
        archive = load("india", "nse_archive")
        split = archive.parse_purpose(
            "Face Value Split (Sub-Division) - From Rs 10/- Per Share To Rs 2/- Per Share")
        self.assertAlmostEqual(split["factor"], 0.2)
        self.assertFalse(split["demerger"])
        self.assertTrue(split["readable"])
        bonus = archive.parse_purpose("Bonus 1:1")
        self.assertAlmostEqual(bonus["factor"], 0.5)
        both = archive.parse_purpose(
            "Bonus 1:1/Face Value Split (Sub-Division) - From Rs 10/- Per Share To Rs 5/- Per Share")
        self.assertAlmostEqual(both["factor"], 0.25)
        spaced = archive.parse_purpose(
            "Bonus 1 : 1 / Face Value Split From Rs 10/- Each To Rs 2/- Each")
        self.assertTrue(spaced["readable"])
        self.assertAlmostEqual(spaced["factor"], 0.1)
        short = archive.parse_purpose("Fv Splt Frm Rs 10 To Rs 2")
        self.assertTrue(short["readable"])
        self.assertAlmostEqual(short["factor"], 0.2)
        self.assertTrue(archive.parse_purpose("De-Merger")["demerger"])
        short_face = archive.parse_purpose("Agm/Div-Rs.2/Fv Rs10tors5")
        self.assertTrue(short_face["readable"])
        self.assertAlmostEqual(short_face["factor"], 0.5)
        self.assertTrue(short_face["dividend"])
        bare = archive.parse_purpose(
            "Bonus 1:1 / Face Value Split From 10/- To Face Value 2/-")
        self.assertTrue(bare["readable"])
        self.assertAlmostEqual(bare["factor"], 0.1)
        panel = load("india/research", "panel")
        factor, estimated = panel.extreme_bar_factor(100.0, 20.0, 22.0, 19.5, 20.5)
        self.assertAlmostEqual(factor, 0.2)
        self.assertFalse(estimated)
        self.assertEqual(panel.extreme_bar_factor(100.0, 90.0, 91.0, 80.0, 85.0), (None, False))
        joined = archive.combine_purpose([
            archive.parse_purpose("Bonus 1:1"),
            archive.parse_purpose(
                "Face Value Split (Sub-Division) - From Rs 10/- Per Share To Rs 5/- Per Share"),
        ])
        self.assertAlmostEqual(joined["factor"], 0.25)
        demerger = archive.parse_purpose("Demerger")
        self.assertTrue(demerger["demerger"])
        self.assertIsNone(demerger["factor"])
        self.assertTrue(demerger["readable"])
        dividend = archive.parse_purpose("Interim Dividend - Rs 6.50 Per Share")
        self.assertTrue(dividend["dividend"])
        self.assertIsNone(dividend["factor"])
        self.assertTrue(dividend["readable"])
        panel = load("india/research", "panel")
        factor, estimated = panel.resolve_corporate(
            {"factor": None, "rights": False, "demerger": True},
            200.0, 200.0, 80.0)
        self.assertAlmostEqual(factor, 0.4)
        self.assertTrue(estimated)
        factor, estimated = panel.resolve_corporate(
            {"factor": None, "rights": False, "demerger": True},
            200.0, 100.0, 110.0)
        self.assertAlmostEqual(factor, 0.5)
        self.assertFalse(estimated)
        rights, estimated = panel.resolve_corporate(
            {"factor": None, "rights": True, "demerger": False},
            100.0, 100.0, 90.0)
        self.assertIsNone(rights)
        self.assertFalse(estimated)

    def test_ine_only_filter(self):
        panel = load("india/research", "panel")
        self.assertTrue(panel.keep_equity("INE002A01018", "EQ"))
        self.assertTrue(panel.keep_equity("INE002A01018", "BE"))
        self.assertTrue(panel.keep_equity("", "EQ"))
        self.assertFalse(panel.keep_equity("INF204KB17I5", "EQ"))
        self.assertFalse(panel.keep_equity("INF732E01045", "EQ"))
        self.assertFalse(panel.keep_equity("INE002A01018", "GS"))
        self.assertFalse(panel.keep_equity("INE002A01018", "N1"))
        self.assertTrue(panel.listed_equity("INE002A01018"))
        self.assertFalse(panel.listed_equity("SYM:GOLDBEES"))
        self.assertFalse(panel.listed_equity("INF204KB17I5"))

    def test_factor_priority(self):
        panel = load("india/research", "panel")
        self.assertEqual(panel.choose_factor(0.5, 0.2, 0.9, True), (0.5, "kite"))
        self.assertEqual(panel.choose_factor(None, 0.2, 0.9, True), (0.2, "nse"))
        self.assertEqual(panel.choose_factor(None, None, 0.5, True), (0.5, "prev_close"))
        self.assertEqual(panel.choose_factor(None, None, 1.02, False), (None, None))
        factor, source = panel.choose_factor(None, None, 0.5, False)
        self.assertEqual(source, "ratio")
        self.assertAlmostEqual(factor, 0.5)
        self.assertEqual(panel.choose_factor(1.001, 0.2, 0.9, True), (0.2, "nse"))
        self.assertAlmostEqual(panel.kite_change(50.0, 100.0, 100.0, 100.0), 0.5)
        self.assertIsNone(panel.kite_change(100.2, 100.0, 100.0, 100.0))


if __name__ == "__main__":
    unittest.main()
