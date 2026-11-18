"""Step 33. The one-sided t tail used by the luck test."""

import unittest

from _load import load


class Step33Test(unittest.TestCase):
    def test_student_t_upper_tail(self):
        step = load("india/research", "step33")
        # Published one-sided 5% points of Student's t.
        self.assertAlmostEqual(step.student_t_sf(1.8124611228, 10), 0.05, places=4)
        self.assertAlmostEqual(step.student_t_sf(1.697261, 30), 0.05, places=4)
        self.assertAlmostEqual(step.student_t_sf(0.0, 20), 0.5, places=6)


if __name__ == "__main__":
    unittest.main()
