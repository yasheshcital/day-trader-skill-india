"""Step 28. Gap rule, ISIN stitch, and the results-drift threshold."""

import datetime
import unittest

from _load import load


def _bar(day, close, prev_close, symbol="ABC", isin="INE000TEST01"):
    return {
        "date": day,
        "symbol": symbol,
        "isin": isin,
        "series": "EQ",
        "open": close,
        "high": close,
        "low": close,
        "close": close,
        "prev_close": prev_close,
        "volume": 100.0,
        "turnover": close * 100.0,
    }


class Step28Test(unittest.TestCase):
    def test_gap_rule(self):
        panel = load("india/research", "panel")
        first = datetime.date(2024, 1, 2)
        second = datetime.date(2024, 1, 3)
        third = datetime.date(2024, 1, 4)
        calendar = [first, second, third]
        # A 2% move across a missed session is a return, not an action.
        actions, adjusted = panel.adjust_bars([
            _bar(first, 100.0, 100.0),
            _bar(third, 102.0, 102.0),
        ], calendar)
        self.assertEqual(actions, [])
        self.assertAlmostEqual(adjusted[0]["adj_close"], 100.0)
        # A 1:2 split across that same gap is an action, and earlier prices are cut in half.
        actions, adjusted = panel.adjust_bars([
            _bar(first, 200.0, 200.0),
            _bar(third, 100.0, 100.0),
        ], calendar)
        self.assertEqual(len(actions), 1)
        self.assertAlmostEqual(actions[0]["factor"], 0.5)
        self.assertAlmostEqual(adjusted[0]["adj_close"], 100.0)
        self.assertAlmostEqual(adjusted[1]["adj_close"], 100.0)
        # The same 2% move on the next session is still an action.
        actions, _adjusted = panel.adjust_bars([
            _bar(first, 100.0, 100.0),
            _bar(second, 102.0, 102.0),
        ], calendar)
        self.assertEqual(len(actions), 1)
        self.assertAlmostEqual(actions[0]["factor"], 1.02)
        # A 1:2 split whose prev_close was left unchanged is still an action.
        actions, adjusted = panel.adjust_bars([
            _bar(first, 200.0, 200.0),
            _bar(second, 100.0, 200.0),
        ], calendar)
        self.assertEqual(len(actions), 1)
        self.assertAlmostEqual(actions[0]["factor"], 0.5)
        self.assertAlmostEqual(adjusted[0]["adj_close"], 100.0)
        self.assertAlmostEqual(adjusted[1]["adj_close"], 100.0)
        # A 10% lock is the circuit, not a bonus.
        actions, adjusted = panel.adjust_bars([
            _bar(first, 100.0, 100.0),
            _bar(second, 90.0, 100.0),
        ], calendar)
        self.assertEqual(actions, [])
        self.assertAlmostEqual(adjusted[0]["adj_close"], 100.0)
        # A 1-for-10 bonus leaves the price at 10/11 when prev_close is unchanged.
        bonus = 100.0 * 10.0 / 11.0
        actions, adjusted = panel.adjust_bars([
            _bar(first, 100.0, 100.0),
            _bar(second, bonus, 100.0),
        ], calendar)
        self.assertEqual(len(actions), 1)
        self.assertAlmostEqual(actions[0]["factor"], 10.0 / 11.0)
        self.assertAlmostEqual(adjusted[0]["adj_close"], bonus)

    def test_isin_stitch(self):
        panel = load("india/research", "panel")
        first = datetime.date(2024, 1, 2)
        second = datetime.date(2024, 1, 3)
        third = datetime.date(2024, 1, 4)
        fourth = datetime.date(2024, 1, 5)
        calendar = [first, second, third, fourth]
        old = [_bar(first, 200.0, 200.0, "XYZ", "OLD")]
        new = [
            _bar(third, 110.0, 100.0, "XYZ", "NEW"),
            _bar(fourth, 112.0, 110.0, "XYZ", "NEW"),
        ]
        merged, stitches = panel.stitch_isins({"OLD": old, "NEW": new}, calendar)
        self.assertNotIn("OLD", merged)
        self.assertEqual(len(stitches), 1)
        self.assertEqual(stitches[0]["old"], "OLD")
        self.assertEqual(stitches[0]["new"], "NEW")
        self.assertEqual(stitches[0]["symbol"], "XYZ")
        self.assertEqual(stitches[0]["sessions"], 2)
        actions, adjusted = panel.adjust_bars(merged["NEW"], calendar)
        self.assertEqual(len(actions), 1)
        self.assertAlmostEqual(actions[0]["factor"], 0.5)
        self.assertAlmostEqual(adjusted[0]["adj_close"], 100.0)
        # Ten sessions apart is not a stitch.
        far = [first + datetime.timedelta(days=i) for i in range(20)]
        late = far[12]
        apart, stitches = panel.stitch_isins({
            "OLD": [_bar(far[0], 10.0, 10.0, "XYZ", "OLD")],
            "NEW": [_bar(late, 10.0, 10.0, "XYZ", "NEW")],
        }, far)
        self.assertIn("OLD", apart)
        self.assertIn("NEW", apart)
        self.assertEqual(stitches, [])

    def test_results_drift_uses_only_past_reactions(self):
        batch = load("india/research", "batch22")
        # Ten past reactions, 0.01 through 0.10. The 90th-percentile index is 9,
        # so the cutoff is 0.10. A later 0.50 must not move that cutoff.
        day = datetime.date(2023, 12, 1)
        past = []
        for i in range(10):
            past.append((datetime.date(2023, 1, 2) + datetime.timedelta(days=20 * i), 0.01 * (i + 1)))
        future = [(datetime.date(2024, 3, 1), 0.50), (datetime.date(2024, 6, 1), 0.50)]
        events = past + [(day, 0.10)] + future
        seen = batch.past_reactions(events, day)
        self.assertEqual(seen, [0.01 * (i + 1) for i in range(10)])
        self.assertTrue(batch.is_top_decile(0.10, seen))
        self.assertFalse(batch.is_top_decile(0.09, seen))
        # Including the future reactions would push the cutoff to 0.50.
        leaked = [value for _when, value in events]
        self.assertFalse(batch.is_top_decile(0.10, leaked))


if __name__ == "__main__":
    unittest.main()
