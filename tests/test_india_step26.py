"""Step 26. Downloader resume, the expiry rule, and the FII direction."""

import csv
import datetime
import gzip
import io
import os
import shutil
import tempfile
import unittest

from _load import load


OLD = "\n".join([
    "INSTRUMENT,SYMBOL,EXPIRY_DT,STRIKE_PR,OPTION_TYP,OPEN,HIGH,LOW,CLOSE,SETTLE_PR,CONTRACTS,VAL_INLAKH,OPEN_INT,CHG_IN_OI,TIMESTAMP,",
    "FUTIDX,NIFTY,25-Jan-2024,0,XX,21455,21474.15,21243,21325.45,21352.6,145154,1547037.97,2964250,-2321100,25-JAN-2024,",
])

NEW_HEADER = (
    "TradDt,BizDt,Sgmt,Src,FinInstrmTp,FinInstrmId,ISIN,TckrSymb,SctySrs,XpryDt,"
    "FininstrmActlXpryDt,StrkPric,OptnTp,FinInstrmNm,OpnPric,HghPric,LwPric,ClsPric,"
    "LastPric,PrvsClsgPric,UndrlygPric,SttlmPric,OpnIntrst,ChngInOpnIntrst,TtlTradgVol,"
    "TtlTrfVal,TtlNbOfTxsExctd,SsnId,NewBrdLotQty,Rmks,Rsvd1,Rsvd2,Rsvd3,Rsvd4"
)


def _new_text():
    fields = NEW_HEADER.split(",")
    row = {name: "" for name in fields}
    row.update({
        "TradDt": "2024-07-08",
        "BizDt": "2024-07-08",
        "Sgmt": "FO",
        "Src": "NSE",
        "FinInstrmTp": "IDO",
        "TckrSymb": "NIFTY",
        "XpryDt": "2024-07-25",
        "StrkPric": "25000.00",
        "OptnTp": "PE",
        "OpnPric": "120.5",
        "HghPric": "130",
        "LwPric": "110.25",
        "ClsPric": "125",
        "SttlmPric": "124.5",
        "TtlTradgVol": "4000",
        "OpnIntrst": "88000",
        "ChngInOpnIntrst": "-1500",
    })
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    writer.writerow(row)
    return buf.getvalue()


class Step26(unittest.TestCase):
    def test_old_and_new_bhavcopy_rows(self):
        arch = load("india", "nse_archive")
        old = arch.parse_bhav(OLD)
        self.assertEqual(len(old), 1)
        row = old[0]
        self.assertEqual(row["date"], "2024-01-25")
        self.assertEqual(row["symbol"], "NIFTY")
        self.assertEqual(row["instrument"], "FUTIDX")
        self.assertEqual(row["expiry"], "2024-01-25")
        self.assertEqual(row["strike"], "0")
        self.assertEqual(row["option_type"], "")
        self.assertEqual(row["open"], "21455")
        self.assertEqual(row["high"], "21474.15")
        self.assertEqual(row["low"], "21243")
        self.assertEqual(row["close"], "21325.45")
        self.assertEqual(row["settle"], "21352.6")
        self.assertEqual(row["contracts"], "145154")
        self.assertEqual(row["open_interest"], "2964250")
        self.assertEqual(row["change_in_oi"], "-2321100")

        new = arch.parse_bhav(_new_text())
        self.assertEqual(len(new), 1)
        row = new[0]
        self.assertEqual(row["date"], "2024-07-08")
        self.assertEqual(row["symbol"], "NIFTY")
        self.assertEqual(row["instrument"], "IDO")
        self.assertEqual(row["expiry"], "2024-07-25")
        self.assertEqual(row["strike"], "25000")
        self.assertEqual(row["option_type"], "PE")
        self.assertEqual(row["open"], "120.5")
        self.assertEqual(row["high"], "130")
        self.assertEqual(row["low"], "110.25")
        self.assertEqual(row["close"], "125")
        self.assertEqual(row["settle"], "124.5")
        self.assertEqual(row["contracts"], "4000")
        self.assertEqual(row["open_interest"], "88000")
        self.assertEqual(row["change_in_oi"], "-1500")

    def test_resume_after_two_failures(self):
        arch = load("india", "nse_archive")
        root = tempfile.mkdtemp()
        try:
            calls = {"n": 0}

            def fetch(url, accept, timeout):
                self.assertEqual(timeout, 20)
                calls["n"] += 1
                if calls["n"] < 3:
                    raise TimeoutError("timed out")
                return 200, b"Client Type,Future Index Long\nFII,1\n"

            slept = []
            client = arch.Client(fetch=fetch, sleep=slept.append)
            day = datetime.date(2024, 1, 2)
            progress = {}
            result = arch._fetch_day(
                client, root, progress, "participant", day,
                ["http://example/a"], lambda _line: None)
            self.assertEqual(result, "ok")
            self.assertEqual(calls["n"], 3)
            self.assertIn(2, slept)
            self.assertIn(4, slept)
            self.assertTrue(os.path.isfile(arch.participant_path(root, day)))
            saved = arch._load_progress(root)
            self.assertEqual(saved["participant"][day.isoformat()], "ok")
            result = arch._fetch_day(
                client, root, saved, "participant", day,
                ["http://example/a"], lambda _line: None)
            self.assertEqual(result, "skip")
            self.assertEqual(calls["n"], 3)
        finally:
            shutil.rmtree(root)

    def test_expiry_rule_around_2025_08_31(self):
        ev = load("india/research", "events")
        holidays = load("india/research", "nse_holidays")
        closed = [datetime.date.fromisoformat(key) for key in holidays.HOLIDAYS]
        start = datetime.date(2025, 4, 1)
        end = datetime.date(2025, 9, 30)
        monthly, weekly = ev.rule_expiries(start, end, closed)
        self.assertEqual(datetime.date(2025, 8, 28).weekday(), 3)
        self.assertEqual(datetime.date(2025, 8, 26).weekday(), 1)
        self.assertEqual(datetime.date(2025, 9, 2).weekday(), 1)
        self.assertEqual(datetime.date(2025, 9, 4).weekday(), 3)
        self.assertIn(datetime.date(2025, 8, 28), monthly)
        self.assertNotIn(datetime.date(2025, 8, 28), weekly)
        self.assertNotIn(datetime.date(2025, 8, 26), monthly)
        self.assertNotIn(datetime.date(2025, 8, 26), weekly)
        self.assertIn(datetime.date(2025, 9, 2), weekly)
        self.assertNotIn(datetime.date(2025, 9, 4), weekly)
        self.assertNotIn(datetime.date(2025, 9, 4), monthly)
        self.assertIn(datetime.date(2025, 9, 30), monthly)
        self.assertNotIn(datetime.date(2025, 9, 30), weekly)
        # 10 Apr 2025 is a Thursday holiday, so the weekly expiry is the day before.
        self.assertIn(datetime.date(2025, 4, 10), closed)
        self.assertNotIn(datetime.date(2025, 4, 10), weekly)
        self.assertNotIn(datetime.date(2025, 4, 10), monthly)
        self.assertIn(datetime.date(2025, 4, 9), weekly)
        root = tempfile.mkdtemp()
        try:
            futures = os.path.join(root, "futures")
            os.makedirs(futures)
            payload = "\n".join([
                "datetime_start_ist,open,high,low,close,volume,oi,expiry",
                "2024-01-02 00:00:00,1,1,1,1,1,1,2024-01-10",
            ]) + "\n"
            with gzip.open(os.path.join(futures, "NIFTY.csv.gz"), "wb") as fh:
                fh.write(payload.encode("utf-8"))
            plain = os.path.join(futures, "BANKNIFTY.csv.gz")
            with gzip.open(plain, "wb") as fh:
                fh.write(b"datetime_start_ist,open,high,low,close,volume,oi\n")
            found = ev.futures_expiries(futures)
            self.assertEqual(found, set([datetime.date(2024, 1, 10)]))
            sessions = [
                datetime.date(2024, 1, 2),
                datetime.date(2024, 1, 4),
                datetime.date(2024, 1, 10),
                datetime.date(2024, 1, 11),
            ]
            out = os.path.join(root, "events.csv")
            ev.build(root, sessions, out, futures)
            rows = ev.read_events(out)
            kinds = {}
            for row in rows:
                if row["kind"].startswith("expiry"):
                    kinds.setdefault(row["date"], set()).add(row["kind"])
            # 10 Jan 2024 is a Wednesday. The weekday rule does not emit it.
            self.assertEqual(datetime.date(2024, 1, 10).weekday(), 2)
            self.assertIn(datetime.date(2024, 1, 10), kinds)
            self.assertEqual(
                [row["source"] for row in rows if row["date"] == datetime.date(2024, 1, 10)],
                ["continuous futures file, expiry column"])
            with open(out, encoding="utf-8") as fh:
                self.assertNotIn("\u2014", fh.read())
        finally:
            shutil.rmtree(root)

    def test_the_switch_on_synthetic_vix(self):
        batch = load("india/research", "batch20")
        high = [10.0] * 249 + [50.0]
        self.assertTrue(batch.vix_top30(high))
        self.assertTrue(batch.switch_on(high, False))
        low = [50.0] * 249 + [10.0]
        self.assertFalse(batch.vix_top30(low))
        self.assertFalse(batch.switch_on(low, False))
        self.assertTrue(batch.switch_on(low, True))
        short = [50.0] * 249
        self.assertFalse(batch.switch_on(short, False))
        tied = [12.0] * 250
        self.assertTrue(batch.switch_on(tied, False))
        on_day = datetime.date(2024, 1, 10)
        off_day = datetime.date(2024, 1, 11)
        signals = {on_day: ("buy", 600), off_day: ("sell", 600)}
        kept = batch.filter_signals(signals, set([on_day]))
        self.assertEqual(list(kept), [on_day])
        self.assertNotIn(off_day, kept)

    def test_rules_land_before_forward_test(self):
        batch = load("india/research", "batch20")
        root = tempfile.mkdtemp()
        try:
            path = os.path.join(root, "EXPERIMENTS.md")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write("# log\n\n## Attempt 19\n\nkept\n\n## Forward test\n\nlater\n")
            batch.write_rules(path, datetime.date(2026, 11, 8))
            with open(path, encoding="utf-8") as fh:
                text = fh.read()
            self.assertLess(text.find("\n## Attempt 19\n"), text.find("\n## Attempt 20\n"))
            self.assertLess(text.find("\n## Attempt 20\n"), text.find("\n## Forward test\n"))
            self.assertIn("kept", text)
            self.assertIn("later", text)
            self.assertIn("expiry column", text)
            self.assertIn("top 30 percent", text)
            self.assertIn("13:55", text)
            self.assertIn(batch.END_RULE if hasattr(batch, "END_RULE") else
                          "If no attempt 20 or 21 variant passes in-sample AND its holdout, intraday is Closed for good.",
                          text)
            later = load("india/research", "batch21")
            later.write_rules(path, datetime.date(2026, 11, 10))
            with open(path, encoding="utf-8") as fh:
                text = fh.read()
            self.assertLess(text.find("\n## Attempt 20\n"), text.find("\n## Attempt 21\n"))
            self.assertLess(text.find("\n## Attempt 21\n"), text.find("\n## Forward test\n"))
            self.assertEqual(text.count(later.END_RULE), 2)
            self.assertNotIn("\u2014", text)
            with open(batch.__file__, encoding="utf-8") as fh:
                src = fh.read()
            self.assertEqual(src.count("final=True)"), 1)
            with open(later.__file__, encoding="utf-8") as fh:
                src = fh.read()
            self.assertEqual(src.count("final=True)"), 1)
        finally:
            shutil.rmtree(root)

    def test_fii_direction(self):
        batch = load("india/research", "batch21")
        big = [10.0] * 249 + [80.0]
        self.assertFalse(batch.is_small(big))
        self.assertEqual(batch.direction_of(5), "buy")
        self.assertEqual(batch.direction_of(-5), "sell")
        self.assertIsNone(batch.direction_of(0))
        self.assertTrue(batch.fii_take("buy", 5, big))
        self.assertFalse(batch.fii_take("sell", 5, big))
        self.assertTrue(batch.fii_take("sell", -5, big))
        self.assertFalse(batch.fii_take("buy", -5, big))
        self.assertFalse(batch.fii_take("buy", 0, big))
        tied = [4.0] * 250
        self.assertTrue(batch.is_small(tied))
        self.assertFalse(batch.fii_take("buy", 4, tied))
        short = [80.0] * 249
        self.assertTrue(batch.is_small(short))
        self.assertFalse(batch.fii_take("buy", 80, short))
        # Index 74 is the 75th smallest. A last value sitting on it is skipped.
        window = [1.0] * 74 + [5.0] + [10.0] * 175
        self.assertEqual(len(window), 250)
        self.assertEqual(sorted(window)[74], 5.0)
        on_cutoff = [1.0] * 74 + [10.0] * 175 + [5.0]
        self.assertTrue(batch.is_small(on_cutoff))
        above = [1.0] * 74 + [5.0] + [10.0] * 174 + [6.0]
        self.assertFalse(batch.is_small(above))
        self.assertTrue(batch.fii_take("sell", -6, above))


if __name__ == "__main__":
    unittest.main()
