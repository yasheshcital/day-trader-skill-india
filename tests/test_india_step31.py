"""Step 31. The rebalance band, a known XIRR, and the launch-date flag."""

import datetime
import unittest

from _load import load


class Step31Test(unittest.TestCase):
    def test_band_rebalance(self):
        term = load("india/research", "longterm")
        # Exactly five points off target is kept. More than five points trades.
        calm = self._run(term, [(datetime.date(2010, 4, 1), 100.0, 100.0),
                                 (datetime.date(2011, 4, 1), 110.0, 90.0)])
        self.assertNotIn(datetime.date(2011, 4, 1), calm["rebalance_days"])
        moved = self._run(term, [(datetime.date(2010, 4, 1), 100.0, 100.0),
                                  (datetime.date(2011, 4, 1), 100.0, 100.0),
                                  (datetime.date(2012, 4, 1), 200.0, 100.0)])
        self.assertNotIn(datetime.date(2011, 4, 1), moved["rebalance_days"])
        self.assertIn(datetime.date(2012, 4, 1), moved["rebalance_days"])
        self.assertFalse(term.needs_rebalance({"A": 0.55, "B": 0.45}, {"A": 0.50, "B": 0.50}))
        self.assertTrue(term.needs_rebalance({"A": 0.56, "B": 0.44}, {"A": 0.50, "B": 0.50}))

    def test_xirr_matches_the_spreadsheet_example(self):
        term = load("india/research", "longterm")
        flows = [
            (datetime.date(2008, 1, 1), -10000.0),
            (datetime.date(2008, 3, 1), 2750.0),
            (datetime.date(2008, 10, 30), 4250.0),
            (datetime.date(2009, 2, 15), 3250.0),
            (datetime.date(2009, 3, 1), 2750.0),
        ]
        rate = term.xirr(flows)
        # Actual/365 root of these five flows. The present value is zero here
        # and is not zero at the often-quoted 37.336%.
        self.assertAlmostEqual(rate, 0.3821875943, places=6)

    def test_before_launch_flag(self):
        term = load("india/research", "longterm")
        launch = datetime.date(2016, 4, 1)
        self.assertTrue(term.before_launch(datetime.date(2005, 4, 1), launch))
        self.assertFalse(term.before_launch(datetime.date(2016, 4, 1), launch))
        self.assertFalse(term.before_launch(datetime.date(2016, 4, 2), launch))
        self.assertFalse(term.before_launch(datetime.date(2005, 4, 1), None))
        text = term.annotate("24a Midcap 150", True)
        self.assertIn("(back-test years included)", text)
        self.assertNotIn("(back-test years included)", term.annotate("24a Midcap 150", False))

    def _run(self, term, rows):
        series = {
            "A": [(day, a) for day, a, _b in rows],
            "B": [(day, b) for day, _a, b in rows],
        }
        weights = {"A": 0.5, "B": 0.5}
        kinds = {"A": "equity", "B": "equity"}
        return term.simulate(
            series, weights, kinds,
            datetime.date(2010, 4, 1), datetime.date(2012, 4, 1),
            capital=100000.0, expenses={"A": 0.0, "B": 0.0}, bands=True,
        )


if __name__ == "__main__":
    unittest.main()
