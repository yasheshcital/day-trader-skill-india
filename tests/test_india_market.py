"""NSE calendar and clock."""

import datetime
import inspect
import unittest

from _load import load

nse = load("india", "nse_market")
entry = load("trader-entry", "entry")
exitp = load("trader-exit", "exit")
tm = load("trader-timemachine", "timemachine")

DT = datetime.datetime
DAY = datetime.date(2026, 1, 2)  # Friday, and not a weekend


class NseMarket(unittest.TestCase):
    def test_a_weekday_is_open(self):
        self.assertEqual(nse.trading_day(DAY), (True, ""))
        self.assertEqual(nse.session(DAY), (DT(2026, 1, 2, 3, 45), DT(2026, 1, 2, 10, 0)))
        self.assertEqual(nse.OPEN, datetime.time(9, 15))
        self.assertEqual(nse.CLOSE, datetime.time(15, 30))
        self.assertEqual(nse.SESSION_MINUTES, 375)

    def test_saturday_and_sunday_are_closed(self):
        for day in (datetime.date(2026, 1, 3), datetime.date(2026, 1, 4)):
            self.assertEqual(nse.trading_day(day), (False, "weekend"), day)
            self.assertIsNone(nse.session(day), day)

    def test_a_sample_holiday_is_closed_once_added(self):
        day = datetime.date(2026, 1, 26)  # Monday
        key = day.isoformat()
        saved = nse.NSE_HOLIDAYS.get(key)
        nse.NSE_HOLIDAYS[key] = "Republic Day"
        try:
            self.assertEqual(nse.trading_day(day), (False, "NSE holiday: Republic Day"))
            self.assertIsNone(nse.session(day))
        finally:
            if saved is None:
                nse.NSE_HOLIDAYS.pop(key, None)
            else:
                nse.NSE_HOLIDAYS[key] = saved

    def test_ist_is_a_fixed_five_and_a_half_hours_ahead(self):
        # 09:15 IST = 03:45 UTC, 15:30 IST = 10:00 UTC. No daylight saving.
        self.assertEqual(nse.ist_to_utc(DT(2026, 1, 2, 9, 15)), DT(2026, 1, 2, 3, 45))
        self.assertEqual(nse.to_ist(DT(2026, 1, 2, 3, 45)), DT(2026, 1, 2, 9, 15))
        self.assertEqual(nse.ist_to_utc(DT(2026, 6, 15, 15, 30)), DT(2026, 6, 15, 10, 0))
        self.assertEqual(nse.to_ist(DT(2026, 12, 1, 10, 0)), DT(2026, 12, 1, 15, 30))
        self.assertEqual(nse.IST, datetime.timedelta(hours=5, minutes=30))

    def test_tick_for_follows_the_cash_bands_and_indices_stay_at_five_paise(self):
        cases = (
            (249.99, None, 0.01),
            (250, None, 0.05),
            (1000, None, 0.05),
            (1000.05, None, 0.10),
            (5000, None, 0.10),
            (5000.50, None, 0.50),
            (10000, None, 0.50),
            (10001, None, 1.00),
            (20000, None, 1.00),
            (20005, None, 5.00),
            (22990.25, "NIFTY", 0.05),
        )
        for price, symbol, tick in cases:
            self.assertEqual(nse.tick_for(price, symbol), tick, (price, symbol))
            self.assertEqual(exitp.tick_for(price, symbol), tick, (price, symbol))
            self.assertEqual(tm.tick_for(price, symbol), tick, (price, symbol))
        for name in nse.INDEX_SYMBOLS:
            self.assertEqual(nse.tick_for(50000, name), 0.05, name)
        # 260 is in the 0.05 band. An explicit tick still floors and ceils.
        self.assertEqual(nse.round_to_tick(260.07, "RELIANCE"), 260.05)
        self.assertEqual(nse.round_to_tick(260.07, "RELIANCE", down=False), 260.10)
        self.assertEqual(nse.round_to_tick(101.07, tick=0.05), 101.05)
        self.assertEqual(nse.round_to_tick(101.07, down=False, tick=0.05), 101.10)
        self.assertEqual(nse.round_to_tick(1162.55, "RELIANCE"), 1162.50)
        self.assertEqual(nse.round_to_tick(1162.55, "RELIANCE", down=False), 1162.60)

    def test_tick_for_is_the_same_copy_in_exit_and_timemachine(self):
        self.assertEqual(exitp.INDEX_SYMBOLS, nse.INDEX_SYMBOLS)
        self.assertEqual(tm.INDEX_SYMBOLS, nse.INDEX_SYMBOLS)
        self.assertEqual(inspect.getsource(exitp.tick_for), inspect.getsource(nse.tick_for))
        self.assertEqual(inspect.getsource(tm.tick_for), inspect.getsource(nse.tick_for))

    def test_entry_uses_the_same_holiday_list(self):
        self.assertEqual(entry.NSE_HOLIDAYS, nse.NSE_HOLIDAYS)
        self.assertEqual(exitp.NSE_HOLIDAYS, nse.NSE_HOLIDAYS)
        self.assertEqual(tm.NSE_HOLIDAYS, nse.NSE_HOLIDAYS)
        self.assertEqual(nse.NSE_HOLIDAYS.get("2026-11-10"), "Diwali Balipratipada")

    def test_guru_nanak_and_christmas_are_closed_and_the_monday_before_is_open(self):
        for mod in (nse, entry):
            closed, why = mod.trading_day(datetime.date(2026, 11, 24))
            self.assertFalse(closed, mod.__name__)
            self.assertIn("Guru Nanak", why)
            closed, why = mod.trading_day(datetime.date(2026, 12, 25))
            self.assertFalse(closed, mod.__name__)
            self.assertIn("Christmas", why)
            self.assertEqual(mod.trading_day(datetime.date(2026, 11, 23)), (True, ""))

    def test_next_open_skips_the_weekend(self):
        self.assertEqual(nse.next_open(datetime.date(2026, 1, 2)), "2026-01-05 09:15")
        self.assertEqual(nse.next_open(datetime.date(2026, 1, 3)), "2026-01-05 09:15")


if __name__ == "__main__":
    unittest.main()
