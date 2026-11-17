"""Step 30. The buffer, and the April and October rebalance dates."""

import datetime
import unittest

from _load import load


class Step30Test(unittest.TestCase):
    def test_buffer_keeps_a_holding_inside_the_top_60(self):
        batch = load("india/research", "batch23")
        ranked = ["N%02d" % i for i in range(1, 71)]
        held = ["N01", "N45", "N61"]
        chosen = batch.buffered_book(ranked, held, 30, 60)
        self.assertEqual(len(chosen), 30)
        self.assertIn("N01", chosen)
        self.assertIn("N45", chosen)
        self.assertNotIn("N61", chosen)
        # N45 takes a slot, so the 30th new name is the one that does not fit.
        self.assertNotIn("N30", chosen)
        self.assertIn("N29", chosen)
        fresh = batch.buffered_book(ranked, [], 30, 60)
        self.assertEqual(fresh, ranked[:30])

    def test_rebalance_dates(self):
        batch = load("india/research", "batch23")
        calendar = [
            datetime.date(2020, 4, 2),
            datetime.date(2020, 4, 3),
            datetime.date(2020, 5, 4),
            datetime.date(2020, 10, 1),
            datetime.date(2020, 10, 5),
            datetime.date(2021, 4, 1),
            datetime.date(2021, 4, 5),
        ]
        six = batch.first_sessions(calendar, (4, 10))
        self.assertEqual(six, [
            datetime.date(2020, 4, 2),
            datetime.date(2020, 10, 1),
            datetime.date(2021, 4, 1),
        ])
        twelve = batch.first_sessions(calendar, (4,))
        self.assertEqual(twelve, [
            datetime.date(2020, 4, 2),
            datetime.date(2021, 4, 1),
        ])
        self.assertNotIn(datetime.date(2020, 10, 1), twelve)
        self.assertNotIn(datetime.date(2020, 5, 4), six)


if __name__ == "__main__":
    unittest.main()
