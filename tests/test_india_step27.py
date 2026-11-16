"""Step 27. Cash bhavcopy rows, a 1:2 split, a delisting, and one tax year."""

import datetime
import io
import unittest
import zipfile

from _load import load


OLD = "\n".join([
    "SYMBOL,SERIES,OPEN,HIGH,LOW,CLOSE,LAST,PREVCLOSE,TOTTRDQTY,TOTTRDVAL,TIMESTAMP,TOTALTRADES,ISIN,",
    "RELIANCE,EQ,2900.5,2920,2880,2910.25,2908,2895,1000,2910250.5,04-JAN-2024,50,INE002A01018,",
    "TCS,BE,100,110,90,105,104,99,10,1050,04-JAN-2024,2,INE467B01029,",
    "INFY,N1,1,1,1,1,1,1,04-JAN-2024,1,INE009A01021,",
])

NEW_HEADER = (
    "TradDt,BizDt,Sgmt,ISIN,TckrSymb,SctySrs,OpnPric,HghPric,LwPric,ClsPric,"
    "LastPric,PrvsClsgPric,TtlTradgVol,TtlTrfVal"
)


def _new_text():
    fields = NEW_HEADER.split(",")
    kept = {name: "" for name in fields}
    kept.update({
        "TradDt": "2024-07-08",
        "ISIN": "INE002A01018",
        "TckrSymb": "RELIANCE",
        "SctySrs": "EQ",
        "OpnPric": "3000",
        "HghPric": "3050",
        "LwPric": "2990",
        "ClsPric": "3020",
        "LastPric": "3018",
        "PrvsClsgPric": "3010",
        "TtlTradgVol": "2000",
        "TtlTrfVal": "6040000",
    })
    dropped = {name: "" for name in fields}
    dropped.update({
        "TradDt": "2024-07-08",
        "ISIN": "INE000000000",
        "TckrSymb": "FOO",
        "SctySrs": "SM",
        "OpnPric": "1",
        "HghPric": "1",
        "LwPric": "1",
        "ClsPric": "1",
        "LastPric": "1",
        "PrvsClsgPric": "1",
        "TtlTradgVol": "1",
        "TtlTrfVal": "1",
    })
    lines = [NEW_HEADER]
    for row in (kept, dropped):
        lines.append(",".join(row[name] for name in fields))
    return "\n".join(lines)


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


class Step27Test(unittest.TestCase):
    def test_cash_bhavcopy_old_and_new(self):
        archive = load("india", "nse_archive")
        old = archive.parse_cm(OLD, datetime.date(2024, 1, 4))
        self.assertEqual(len(old), 2)
        self.assertEqual(old[0]["symbol"], "RELIANCE")
        self.assertEqual(old[0]["series"], "EQ")
        self.assertEqual(old[0]["isin"], "INE002A01018")
        self.assertEqual(old[0]["date"], "2024-01-04")
        self.assertEqual(old[0]["close"], "2910.25")
        self.assertEqual(old[0]["prev_close"], "2895")
        self.assertEqual(old[0]["volume"], "1000")
        self.assertEqual(old[0]["turnover"], "2910250.5")
        self.assertEqual(old[1]["symbol"], "TCS")
        self.assertEqual(old[1]["series"], "BE")
        new = archive.parse_cm(_new_text(), datetime.date(2024, 7, 8))
        self.assertEqual(len(new), 1)
        self.assertEqual(new[0]["symbol"], "RELIANCE")
        self.assertEqual(new[0]["series"], "EQ")
        self.assertEqual(new[0]["isin"], "INE002A01018")
        self.assertEqual(new[0]["date"], "2024-07-08")
        self.assertEqual(new[0]["close"], "3020")
        self.assertEqual(new[0]["prev_close"], "3010")
        self.assertEqual(new[0]["volume"], "2000")
        self.assertEqual(new[0]["turnover"], "6040000")
        self.assertNotEqual(
            archive.progress_path("data/nse", "cm"),
            archive.progress_path("data/nse"))
        self.assertTrue(archive.progress_path("data/nse", "delivery").endswith("progress-delivery.json"))
        self.assertTrue(archive.progress_path("data/nse", "indices").endswith("progress-indices.json"))

    def test_delivery_xlsx_named_csv(self):
        # 8 Aug 2022 is an xlsx workbook served with a .csv name. The first
        # zip member is Content_Types.xml, so the sheet has to be read.
        archive = load("india", "nse_archive")
        shared = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            "<si><t>SYMBOL</t></si><si><t> SERIES</t></si>"
            "<si><t> DELIV_QTY</t></si><si><t> DELIV_PER</t></si>"
            "<si><t>RELIANCE</t></si><si><t>EQ</t></si>"
            "<si><t>TCS</t></si><si><t>N1</t></si>"
            "</sst>"
        )
        sheet = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            "<sheetData>"
            '<row r="1"><c r="A1" t="s"><v>0</v></c><c r="B1" t="s"><v>1</v></c>'
            '<c r="C1" t="s"><v>2</v></c><c r="D1" t="s"><v>3</v></c></row>'
            '<row r="2"><c r="A2" t="s"><v>4</v></c><c r="B2" t="s"><v>5</v></c>'
            '<c r="C2"><v>571768</v></c><c r="D2"><v>33.89</v></c></row>'
            '<row r="3"><c r="A3" t="s"><v>6</v></c><c r="B3" t="s"><v>7</v></c>'
            '<c r="C3"><v>10</v></c><c r="D3"><v>1</v></c></row>'
            "</sheetData></worksheet>"
        )
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("[Content_Types].xml", "<Types></Types>")
            zf.writestr("xl/sharedStrings.xml", shared)
            zf.writestr("xl/worksheets/sheet1.xml", sheet)
        rows = archive.parse_delivery(
            archive._zip_text(buf.getvalue()), datetime.date(2022, 8, 8))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["symbol"], "RELIANCE")
        self.assertEqual(rows[0]["series"], "EQ")
        self.assertEqual(rows[0]["deliverable_qty"], "571768")
        self.assertEqual(rows[0]["deliverable_pct"], "33.89")
        self.assertEqual(rows[0]["date"], "2022-08-08")

    def test_one_for_two_split(self):
        panel = load("india/research", "panel")
        first = datetime.date(2024, 1, 2)
        second = datetime.date(2024, 1, 3)
        actions, adjusted = panel.adjust_bars([
            _bar(first, 200.0, 195.0),
            _bar(second, 110.0, 100.0),
        ])
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0]["date"], second)
        self.assertAlmostEqual(actions[0]["factor"], 0.5)
        self.assertAlmostEqual(adjusted[0]["adj_close"], 100.0)
        self.assertAlmostEqual(adjusted[0]["adj_open"], 100.0)
        self.assertAlmostEqual(adjusted[1]["adj_close"], 110.0)
        self.assertAlmostEqual(adjusted[1]["adj_factor"], 1.0)
        quiet, quiet_bars = panel.adjust_bars([
            _bar(first, 100.0, 100.0),
            _bar(second, 101.0, 100.4),
        ])
        self.assertEqual(quiet, [])
        self.assertAlmostEqual(quiet_bars[0]["adj_close"], 100.0)

    def test_delisting_exit_keeps_the_loss(self):
        invest = load("india/research", "invest")
        first = datetime.date(2023, 1, 2)
        second = datetime.date(2023, 1, 3)
        third = datetime.date(2023, 1, 4)
        bars = {
            "AAA": [
                _bar(first, 100.0, 100.0, "AAA", "AAA"),
                _bar(second, 80.0, 100.0, "AAA", "AAA"),
            ],
            "BBB": [
                _bar(first, 50.0, 50.0, "BBB", "BBB"),
                _bar(second, 50.0, 50.0, "BBB", "BBB"),
                _bar(third, 50.0, 50.0, "BBB", "BBB"),
            ],
        }
        bars["AAA"][1]["last"] = True
        bars["AAA"][1]["adj_close"] = 80.0
        bars["AAA"][0]["adj_close"] = 100.0
        for row in bars["BBB"]:
            row["adj_close"] = 50.0

        def score(day, names, history):
            return {"AAA": 2.0, "BBB": 1.0}

        result = invest.simulate(bars, score, 1, end=third, capital=100000.0)
        self.assertEqual(result["open_shares"].get("AAA", 0), 0)
        self.assertEqual(len(result["trades"]), 1)
        self.assertEqual(result["trades"][0]["isin"], "AAA")
        self.assertEqual(result["trades"][0]["price"], 80.0)
        self.assertLess(result["trades"][0]["gain"], 0)
        self.assertLess(result["final_equity"], 100000.0)
        with self.assertRaises(invest.data.HoldoutError):
            invest.simulate(bars, score, 1, end=datetime.date(2025, 1, 2))

    def test_tax_on_three_trades_with_one_loss(self):
        invest = load("india/research", "invest")
        # STCG +100000, LTCG +250000, STCG loss -40000, all sold in 2023.
        # The loss cuts the STCG to 60000. Tax is 60000 * 15% plus
        # (250000 - 100000) * 10% = 24000.
        trades = [
            {"buy": datetime.date(2023, 1, 2), "sell": datetime.date(2023, 3, 1), "gain": 100000.0},
            {"buy": datetime.date(2021, 1, 4), "sell": datetime.date(2023, 6, 1), "gain": 250000.0},
            {"buy": datetime.date(2023, 8, 1), "sell": datetime.date(2023, 9, 1), "gain": -40000.0},
        ]
        self.assertEqual(invest.tax_due(trades), 24000.0)
        # A sale on the cutoff date uses 20% STCG.
        later = [{
            "buy": datetime.date(2024, 7, 1),
            "sell": datetime.date(2024, 7, 23),
            "gain": 10000.0,
        }]
        self.assertEqual(invest.tax_due(later), 2000.0)


if __name__ == "__main__":
    unittest.main()
