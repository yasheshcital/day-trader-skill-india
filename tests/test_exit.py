"""trader-exit tests. Bars for the ATR stop are the NIFTY 30 Oct 2026
five-minute session in tests/fixtures/trader-exit/."""

import io
import json
import os
import shutil
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr
from decimal import Decimal

from _load import load, FIX, ROOT

exitp = load("trader-exit", "exit")
entry = load("trader-entry", "entry")

NIFTY = os.path.join(FIX, "trader-exit", "NIFTY-2026-10-30-5m.json")
DAY = "2026-10-30"
OH, OL = 22980.35, 22919.85

# trader/plan.json for the NIFTY opening-range plan, exactly as the contract writes it
PLAN_1R = {"created_by": "trader-exit", "symbol": "NIFTY", "side": "buy", "date": DAY, "setup": "orb",
           "entry": 22990.25, "entry_time": "9:35 AM", "entry_bar": 3, "interval": "5m",
           "opening_range": {"high": OH, "low": OL, "minutes": 15},
           "stop": 22950.10, "stop_rule": "or_mid", "stop_label": "opening-range midpoint",
           "target": 23030.40, "target_r": 1.0, "target_label": "1R (one times the risk)",
           "risk_per_share": 40.15, "reward_risk": 1.0, "flat_by": "15:10"}
ENTRY = {"created_by": "trader-entry", "symbol": "NIFTY", "setup": "orb", "side": "buy", "date": DAY,
         "status": "triggered", "time": "9:35 AM", "bar_start": "09:30", "bar_index": 3, "price": 22990.25,
         "level": OH, "interval": "5m", "opening_range": {"high": OH, "low": OL, "minutes": 15},
         "source": "yahoo", "checked_at": "2026-10-30T04:10:00Z"}


def run(mod, argv):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = mod.main(argv)
    return code, out.getvalue(), err.getvalue()


def c(entry_px, stop, target="2R", oh=OH, ol=OL, atr=None, n=None, symbol="NIFTY"):
    sr, sp = exitp.parse_stop(stop)
    tr, tp = exitp.parse_target(target)
    return exitp.compute(entry_px, sr, sp, tr, tp, oh, ol, atr, n, symbol)


class Math(unittest.TestCase):
    def test_the_reel_or_mid_1r(self):
        p = c(22990.25, "or-mid", "1R")
        self.assertEqual(p["stop"], Decimal("22950.10"))
        self.assertEqual(p["risk"], Decimal("40.15"))
        self.assertEqual(p["target"], Decimal("23030.40"))
        self.assertEqual(p["reward_risk"], Decimal("1.00"))
        self.assertEqual(p["target_label"], "1R (one times the risk)")
        self.assertIn("= ₹22,950.10", p["stop_detail"])

    def test_the_default_2r(self):
        p = c(22990.25, "or-mid")
        self.assertEqual(p["stop"], Decimal("22950.10"))
        self.assertEqual(p["risk"], Decimal("40.15"))
        self.assertEqual(p["target"], Decimal("23070.55"))
        self.assertEqual(p["reward_risk"], Decimal("2.00"))
        self.assertEqual(p["target_label"], "2R (two times the risk)")

    def test_raw_yahoo_floats_give_the_same_ticks(self):
        p = c(22990.250000000004, "or-mid", "1R", 22980.349999999997, 22919.850000000002)
        self.assertEqual((p["entry"], p["stop"], p["target"]),
                         (Decimal("22990.25"), Decimal("22950.10"), Decimal("23030.40")))

    def test_other_stops(self):
        p = c(22990.25, "or-low")
        self.assertEqual((p["stop"], p["risk"], p["target"]),
                         (Decimal("22919.85"), Decimal("70.40"), Decimal("23131.05")))
        p = c(22990.25, "price:₹22950.12")
        self.assertEqual(p["stop"], Decimal("22950.10"))              # down to the tick, away from the entry
        self.assertIn("rounded down", p["stop_detail"])
        p = c(22990.25, "pct:0.3")
        self.assertEqual(p["stop"], Decimal("22921.25"))              # 22990.25 x 0.997 = 22921.27925
        self.assertIn("rounded down", p["stop_detail"])
        p = c(22990.25, "atr:1.5", atr=45.1875, n=4)
        self.assertEqual(p["stop"], Decimal("22922.45"))              # 22990.25 - 67.78125 = 22922.46875
        self.assertEqual(p["stop"] % Decimal("0.05"), 0)
        self.assertEqual(p["tick"], Decimal("0.05"))
        self.assertEqual(p["stop_label"], "1.5 x ATR(4) under the entry")

    def test_reliance_floors_the_stop_to_ten_paise(self):
        p = c(1166.00, "pct:0.3", symbol="RELIANCE")
        self.assertEqual(p["entry"], Decimal("1166.00"))
        self.assertEqual(p["stop"], Decimal("1162.50"))          # 1166 x 0.997 = 1162.502
        self.assertEqual(p["risk"], Decimal("3.50"))
        self.assertEqual(p["target"], Decimal("1173.00"))
        self.assertEqual(p["tick"], Decimal("0.1"))
        p = c(1166.00, "pct:0.3", "1R", symbol="RELIANCE")
        self.assertEqual(p["target"], Decimal("1169.50"))
        p = c(1166.00, "price:1162.55", symbol="RELIANCE")
        self.assertEqual(p["stop"], Decimal("1162.50"))

    def test_target_rounds_half_up_and_price_targets(self):
        p = c(22990.25, "or-mid", "1.5R")
        self.assertEqual(p["target"], Decimal("23050.50"))            # 22990.25 + 60.225 = 23050.475
        self.assertEqual(p["target_label"], "1.5R (1.5 times the risk)")
        p = c(22990.25, "or-mid", "price:₹23070.57")
        self.assertEqual(p["target"], Decimal("23070.55"))
        p = c(22990.25, "or-mid", "price:23070.58")
        self.assertEqual(p["target"], Decimal("23070.60"))
        p = c(22990.25, "or-mid", "price:23043.65")
        self.assertEqual(p["reward_risk"], Decimal("1.33"))
        self.assertEqual(p["target_label"], "your price (1.33R)")
        self.assertEqual(p["target_r"], Decimal("1.33"))

    def test_refusals_say_why(self):
        cases = [("price:22990.25", "2R", "at or above the entry"),
                 ("price:23000", "2R", "at or above the entry"),
                 ("or-mid", "price:22990", "at or below the entry"),
                 ("price:22978.80", "2R", "too tight to survive the spread"),
                 ("pct:0.04", "2R", "too tight to survive the spread")]
        for stop, target, why in cases:
            with self.assertRaises(exitp.PlanError) as cm:
                c(22990.25, stop, target)
            self.assertIn(why, str(cm.exception), stop)
        # 0.05% of 22990.25 is 11.495125: a ₹11.50 risk is allowed, ₹11.45 is not
        self.assertEqual(c(22990.25, "price:22978.75")["risk"], Decimal("11.50"))
        with self.assertRaises(exitp.PlanError):
            c(22990.25, "price:22978.80")
        with self.assertRaises(exitp.PlanError):
            c(22900, "or-mid")                                          # the midpoint is above this entry
        for bad in ("mid-ish", "pct:100", "price:0", "atr:-1"):
            with self.assertRaises(exitp.PlanError):
                exitp.parse_stop(bad)
        for bad in ("0R", "R", "lots", "price:x"):
            with self.assertRaises(exitp.PlanError):
                exitp.parse_target(bad)
        with self.assertRaises(exitp.PlanError):
            c(22990.25, "or-mid", oh=None, ol=None)
        with self.assertRaises(exitp.PlanError):
            c(22990.25, "or-mid", oh=OL, ol=OH)

    def test_atr_on_the_session_bars(self):
        ch = exitp.load_chart("NIFTY", "5m", None, NIFTY)
        day = exitp.datetime.date(2026, 10, 30)
        bars = exitp.session_bars(ch, day, "5m", upto_slot=3)
        self.assertEqual(len(bars), 4)                              # 09:15 ... the 09:30 entry bar
        trs, prev = [], None
        for b in bars:
            r = b["h"] - b["l"]
            if prev is not None:
                r = max(r, abs(b["h"] - prev), abs(b["l"] - prev))
            trs.append(r)
            prev = b["c"]
        self.assertAlmostEqual(trs[0], 22976.6 - 22923.8, places=4)
        atr, n = exitp.atr_of(bars)
        self.assertEqual(n, 4)
        self.assertAlmostEqual(atr, sum(trs) / 4, places=9)
        stop = c(22990.25, "atr:1.5", atr=atr, n=n)["stop"]
        self.assertEqual((n, round(atr, 4), stop), (4, 45.1875, Decimal("22922.45")))
        self.assertEqual(stop % Decimal("0.05"), 0)
        all_bars = exitp.session_bars(ch, day, "5m")
        self.assertEqual(len(all_bars), 75)
        self.assertEqual(exitp.atr_of(all_bars)[1], 14)


class Cli(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.cwd = os.getcwd()
        os.chdir(self.d)
        os.mkdir("trader")

    def tearDown(self):
        os.chdir(self.cwd)
        shutil.rmtree(self.d)

    def write(self, path, doc):
        with open(path, "w") as fh:
            json.dump(doc, fh)

    def plan(self, *args):
        return run(exitp, ["plan", "--now", DAY + " 09:40"] + list(args))

    def read_plan(self):
        with open(os.path.join("trader", "plan.json")) as fh:
            return json.load(fh)

    def test_entry_to_plan_end_to_end(self):
        code, _, err = run(entry, ["check", "NIFTY", "--offline", NIFTY, "--now", DAY + " 09:40", "--write"])
        self.assertEqual(code, 0, err)
        code, text, err = self.plan("--stop", "or-mid", "--target", "1R", "--write")
        self.assertEqual(code, 0, err)
        p = self.read_plan()
        for k, v in PLAN_1R.items():
            self.assertEqual(p[k], v, k)
        self.assertIn("Stop          ₹22,950.10  opening-range midpoint", text)
        self.assertIn("Target        ₹23,030.40  1R (one times the risk)", text)
        self.assertIn("Risk a share  ₹40.15 (0.17% of the entry)", text)
        self.assertIn("Reward:risk   1.0", text)
        self.assertIn("Flat by       15:10 IST", text)
        self.assertIn("Tick ₹0.05", text)
        self.assertIn("not a guarantee", text)
        self.assertIn("/trader-timemachine", text)
        self.assertNotIn("$", text)
        self.assertNotIn(" ET", text)
        self.assertNotIn("pro" + "fit", text.lower())   # never on screen
        code, text, _ = self.plan("--write")                       # the defaults: or-mid, 2R
        self.assertEqual(self.read_plan()["target"], 23070.55)
        self.assertEqual(self.read_plan()["target_r"], 2.0)
        self.assertEqual(self.read_plan()["flat_by"], "15:10")
        self.assertIn("₹23,070.55", text)
        code, text, _ = run(exitp, ["show", "--now", DAY + " 09:50"])
        self.assertEqual(code, 0)
        self.assertIn("₹23,070.55", text)
        self.assertNotIn("not today", text)
        code, text, _ = run(exitp, ["show", "--now", "2026-11-02 10:00"])
        self.assertIn("not today", text)

    def test_manual_flags_and_json(self):
        code, text, _ = self.plan("--symbol", "nifty", "--entry", "22990.25", "--or-high", "22980.35",
                                  "--or-low", "22919.85", "--time", "9:35", "--entry-bar", "3", "--date", DAY,
                                  "--target", "1R", "--json")
        self.assertEqual(code, 0)
        p = json.loads(text)
        for k, v in PLAN_1R.items():
            self.assertEqual(p[k], v, k)
        self.assertEqual(p["warnings"], [])

    def test_atr_stop_reads_bars(self):
        self.write(os.path.join("trader", "entry.json"), ENTRY)
        code, text, err = self.plan("--stop", "atr:1.5", "--offline", NIFTY, "--json")
        self.assertEqual(code, 0, err)
        p = json.loads(text)
        self.assertEqual(Decimal(str(p["stop"])) % Decimal("0.05"), 0)
        self.assertEqual((p["stop_rule"], p["atr_bars"]), ("atr", 4))
        bars = exitp.session_bars(exitp.load_chart("NIFTY", "5m", None, NIFTY),
                                  exitp.datetime.date(2026, 10, 30), "5m", upto_slot=3,
                                  now_utc=exitp.parse_now(DAY + " 09:40"))
        atr, n = exitp.atr_of(bars)
        got = c(22990.25, "atr:1.5", atr=atr, n=n)
        self.assertEqual(p["stop"], float(got["stop"]))
        self.assertEqual((p["atr_bars"], p["stop"]), (n, 22922.45))
        code, _, err = self.plan("--stop", "atr:1.5", "--offline", NIFTY, "--entry-bar", "1")
        self.assertEqual(code, 1)
        self.assertIn("at least 3 closed", err)

    def test_refusals_from_the_cli(self):
        self.write(os.path.join("trader", "entry.json"), dict(ENTRY, status="waiting", time=None, price=None,
                                                              bar_index=None, bar_start=None))
        code, _, err = self.plan()
        self.assertEqual(code, 1)
        self.assertIn("NIFTY is waiting, not triggered", err)
        code, text, _ = self.plan("--entry", "22980.40", "--json")    # plan ahead at the level
        self.assertEqual(code, 0)
        p = json.loads(text)
        self.assertEqual((p["entry"], p["stop"], p["entry_time"]), (22980.40, 22950.10, None))

        self.write(os.path.join("trader", "entry.json"), dict(ENTRY, setup="level", level=22980.35))
        code, _, err = self.plan()
        self.assertIn("level setup has no opening-range stop", err)
        self.assertEqual(self.plan("--stop", "pct:1")[0], 0)

        code, _, err = self.plan("--side", "sell")
        self.assertIn("v2 plans longs only", err)
        self.write(os.path.join("trader", "entry.json"), dict(ENTRY, side="sell"))
        code, _, err = self.plan()
        self.assertIn("longs only", err)
        code, _, err = self.plan("--stop", "price:22950")
        self.assertIn("longs only", err)
        os.remove(os.path.join("trader", "entry.json"))
        code, _, err = self.plan()
        self.assertIn("no entry", err)
        code, _, err = self.plan("--symbol", "NIFTY")
        self.assertIn("needs --entry", err)
        code, _, err = self.plan("--symbol", "NIFTY", "--from", "x.json", "--entry", "1")
        self.assertIn("not both", err)
        code, _, err = self.plan("--symbol", "NIFTY", "--entry", "22990.25", "--or-high", "22980.35")
        self.assertIn("both --or-high and --or-low", err)
        self.assertNotIn("Traceback", err)

    def test_flat_by_config_and_late_entries(self):
        self.write(os.path.join("trader", "entry.json"), ENTRY)
        self.write(os.path.join("trader", "config.json"), {"flat_by": "15:00", "min_reward_risk": 1.5})
        code, text, _ = self.plan("--target", "1R", "--json")
        p = json.loads(text)
        self.assertEqual(p["flat_by"], "15:00")
        self.assertIn("under your min_reward_risk 1.5", p["warnings"][0])
        os.remove(os.path.join("trader", "config.json"))

        code, text, err = self.plan("--json")
        self.assertEqual(code, 0, err)
        self.assertEqual(json.loads(text)["flat_by"], "15:10")
        code, _, err = self.plan("--flat-by", "15:30")
        self.assertEqual(code, 1)
        self.assertIn("at or after the 3:30 PM close", err)

        self.write(os.path.join("trader", "entry.json"), dict(ENTRY, time="3:12 PM"))
        code, _, err = self.plan()
        self.assertEqual(code, 1)
        self.assertIn("no time left to hold it", err)

    def test_show_without_a_plan(self):
        code, text, _ = run(exitp, ["show"])
        self.assertEqual(code, 1)
        self.assertIn("No plan", text)


class SkillDoc(unittest.TestCase):
    def test_skill_md(self):
        with open(os.path.join(ROOT, "trader-exit", "SKILL.md"), encoding="utf-8") as fh:
            text = fh.read()
        with open(os.path.join(ROOT, "trader-risk", "SKILL.md"), encoding="utf-8") as fh:
            risk = fh.read()
        self.assertTrue(text.startswith("---\nname: trader-exit\n"))
        self.assertGreater(len(text.splitlines()), 60)
        self.assertEqual(text[text.index("## Safety"):], risk[risk.index("## Safety"):])
        low = " ".join(text.lower().split())
        for must in ("before the entry", "a stop is a plan, not a guarantee", "day trading loses most people money", "/trader-timemachine", "/trader-budget", "longs only", "$358.32", "$370.04", "$5.86", "375.90", "too tight to survive the spread"):
            self.assertIn(must, low)
        for never in ("\u2014", "tick " + "by tick", "real " + "time", "pro" + "fit"):
            self.assertNotIn(never, low)


if __name__ == "__main__":
    unittest.main()
