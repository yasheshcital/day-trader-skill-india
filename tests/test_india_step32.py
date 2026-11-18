"""Step 32. The GOLDBEES unit split, and the live-record start date."""

import datetime
import unittest

from _load import load


class Step32Test(unittest.TestCase):
    def test_goldbees_split_is_one_hundred_to_one(self):
        gold = load("india/research", "goldetf")
        purpose = "Face Value Split (Sub-Division) - From Rs 100/- To Rs 1/-"
        factor = gold.unit_split_factor(purpose)
        self.assertAlmostEqual(factor, 0.01)
        per_unit = "Face Value Split (Sub-Division) - From Rs 10/- Per Unit To Rs 2/- Per Unit"
        self.assertAlmostEqual(gold.unit_split_factor(per_unit), 0.2)
        re_one = "Face Value Split (Sub-Division) - From Rs 10/- Per Unit To Re 1/- Per Unit"
        self.assertAlmostEqual(gold.unit_split_factor(re_one), 0.1)
        self.assertIsNone(gold.unit_split_factor("Dividend - Rs 1 Per Share"))
        self.assertIsNone(gold.unit_split_factor("Bonus 1:1"))
        ex = datetime.date(2019, 12, 19)
        points = [
            (datetime.date(2019, 12, 18), 1000.0),
            (ex, 10.0),
            (datetime.date(2019, 12, 20), 10.2),
        ]
        out = gold.apply_unit_splits(points, {ex: factor})
        self.assertAlmostEqual(out[0][1], 10.0)
        self.assertAlmostEqual(out[1][1], 10.0)
        self.assertAlmostEqual(out[2][1], 10.2)
        # The BL line on the same ex-date is the same split, not a second one.
        rows = [
            {"date": "2019-12-19", "symbol": "GOLDBEES", "series": "EQ", "purpose": purpose},
            {"date": "2019-12-19", "symbol": "GOLDBEES", "series": "BL", "purpose": purpose},
            {"date": "2019-12-19", "symbol": "GOLDBEES", "series": "EQ", "purpose": "Dividend - Rs 1 Per Share"},
        ]
        events = gold.split_events(rows)
        self.assertEqual(list(events), [ex])
        self.assertAlmostEqual(events[ex], 0.01)

    def test_live_record_starts_the_session_after_launch(self):
        book = load("india/research", "batch25")
        launch = datetime.date(2016, 4, 1)
        points = [
            (datetime.date(2016, 4, 1), 100.0),
            (datetime.date(2016, 4, 4), 101.0),
            (datetime.date(2016, 4, 5), 102.0),
        ]
        start = book.first_session_after(points, launch)
        self.assertEqual(start, datetime.date(2016, 4, 4))
        self.assertNotEqual(start, launch)
        # The launch day is not a session. The next session in the file is used.
        weekend = [
            (datetime.date(2016, 4, 1), 100.0),
            (datetime.date(2016, 4, 4), 101.0),
        ]
        self.assertEqual(
            book.first_session_after(weekend, datetime.date(2016, 4, 2)),
            datetime.date(2016, 4, 4),
        )


if __name__ == "__main__":
    unittest.main()
