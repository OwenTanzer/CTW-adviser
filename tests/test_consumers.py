"""Consumer contract checks; optional full-store probes use a built pinned snapshot."""
from contextlib import closing
import io
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from ctw_adviser.mcp import TOOLS, call_tool, serve
from ctw_adviser.model import _entry, movement_phase
from ctw_adviser.queries import Queries

DB = Path(os.environ.get("CTW_ADVISER_DB", ROOT / "work" / "adviser.sqlite"))


class MovementArithmeticTests(unittest.TestCase):
    def test_entry_edges_and_monotonicity(self):
        self.assertEqual(_entry(100, 100, 0), {"status": "already_reached", "seconds": 0.0})
        self.assertEqual(_entry(100, 20, 0)["status"], "not_reached_under_assumptions")
        self.assertEqual(_entry(100, 20, -1)["seconds"], None)
        self.assertEqual(_entry(100, 20, 4)["seconds"], 20)
        self.assertGreater(_entry(120, 20, 4)["seconds"], _entry(100, 20, 4)["seconds"])
        self.assertLess(_entry(100, 20, 8)["seconds"], _entry(100, 20, 4)["seconds"])


@unittest.skipUnless(DB.exists(), "set CTW_ADVISER_DB to a built pinned snapshot")
class RealConsumerTests(unittest.TestCase):
    def test_model_reads_store_and_changes_with_store(self):
        with Queries(DB) as q:
            base = movement_phase(q, "Lothern Sea Guard", "Blue Horrors of Tzeentch", separation_metres=200)
            self.assertEqual(base["snapshot"]["commit"], "595e22764b22e748afdbafafcb0a6258973e2451")
            self.assertEqual(base["sourced_inputs"][0]["native_speed"], q.get_unit_profile("Lothern Sea Guard")["units"][0]["movement"]["speed"])
            self.assertEqual(len(base["derived"]["range_entry"][0]["attacks"]), len(base["sourced_inputs"][0]["ranged_attacks"]))
            path = ROOT / "work" / "consumer-mutated-test.sqlite"
            try:
                path.unlink(missing_ok=True)
                with closing(sqlite3.connect(path)) as db:
                    q.db.backup(db)
                    db.execute("UPDATE unit_profiles SET speed=speed+1 WHERE unit_key=?",
                               (base["sourced_inputs"][0]["identity"]["profile_unit_key"],))
                    attack_ref = base["sourced_inputs"][0]["ranged_attacks"][0]["provenance_refs"][-1]
                    db.execute("UPDATE projectiles SET effective_range=effective_range+10 WHERE record_id=?", (attack_ref,))
                    db.commit()
                with Queries(path) as changed:
                    result = movement_phase(changed, "Lothern Sea Guard", "Blue Horrors of Tzeentch", separation_metres=200)
                self.assertEqual(result["sourced_inputs"][0]["native_speed"], base["sourced_inputs"][0]["native_speed"] + 1)
                self.assertLess(result["derived"]["contact"]["seconds"], base["derived"]["contact"]["seconds"])
                self.assertNotEqual(result["sourced_inputs"][0]["ranged_attacks"][0]["range_metres"],
                                    base["sourced_inputs"][0]["ranged_attacks"][0]["range_metres"])
            finally:
                path.unlink(missing_ok=True)

    def test_orders_ambiguity_errors_and_cli(self):
        with Queries(DB) as q:
            held = movement_phase(q, "Lothern Sea Guard", "Blue Horrors of Tzeentch",
                                  separation_metres=200, order_a="hold", order_b="hold")
            self.assertEqual(held["derived"]["contact"]["status"], "not_reached_under_assumptions")
            self.assertEqual(held["derived"]["closing_speed_metres_per_second"], 0)
            already = movement_phase(q, "Lothern Sea Guard", "Blue Horrors of Tzeentch",
                                     separation_metres=0)
            self.assertEqual(already["derived"]["contact"]["seconds"], 0)
            for bad in (-1, float("nan")):
                with self.assertRaises(ValueError):
                    movement_phase(q, "Lothern Sea Guard", "Blue Horrors of Tzeentch", separation_metres=bad)
            with self.assertRaises(ValueError):
                movement_phase(q, "Lothern Sea Guard", "Blue Horrors of Tzeentch",
                               separation_metres=200, metres_per_second_per_speed_point=0)
            with self.assertRaisesRegex(Exception, "ambiguous"):
                movement_phase(q, "Feral Manticore", "Kroxigor", separation_metres=200)
            with self.assertRaisesRegex(Exception, "not_found"):
                movement_phase(q, "Bloodletters", "Kroxigor", separation_metres=200)
        env = dict(os.environ, PYTHONPATH=str(ROOT / "src"))
        cli = subprocess.run([sys.executable, "-m", "ctw_adviser.cli", "movement-phase", "--db", str(DB),
                              "Lothern Sea Guard", "Blue Horrors of Tzeentch", "--separation-metres", "200"],
                             text=True, capture_output=True, env=env, check=True)
        with Queries(DB) as q:
            expected = movement_phase(q, "Lothern Sea Guard", "Blue Horrors of Tzeentch",
                                      separation_metres=200)
        self.assertEqual(json.loads(cli.stdout)["derived"]["contact"]["seconds"],
                         expected["derived"]["contact"]["seconds"])

    def test_mcp_protocol_discovery_pagination_detail_and_provenance(self):
        with Queries(DB) as q:
            messages = [
                {"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"test","version":"1"}}},
                {"jsonrpc":"2.0","method":"notifications/initialized"},
                {"jsonrpc":"2.0","id":2,"method":"tools/list"},
                {"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"resolve_unit","arguments":{"name_or_key":"Kroxigor"}}},
                {"jsonrpc":"2.0","id":4,"method":"tools/call","params":{"name":"get_unit_combat_profile","arguments":{"unit_key":"Lothern Sea Guard","section":"weapons","limit":1}}},
            ]
            out = io.StringIO()
            serve(q, io.StringIO("".join(json.dumps(m) + "\n" for m in messages)), out)
            replies = [json.loads(line) for line in out.getvalue().splitlines()]
            self.assertEqual([r["id"] for r in replies], [1, 2, 3, 4])
            self.assertTrue({"resolve_unit", "get_unit_combat_profile", "get_matchup_evidence", "get_detail", "get_provenance"}
                            <= {t["name"] for t in replies[1]["result"]["tools"]})
            self.assertEqual(replies[2]["result"]["structuredContent"]["data"]["status"], "resolved")
            packet = replies[3]["result"]["structuredContent"]["data"]
            section = next(s for s in packet["units"][0]["coverage"]["sections"] if s["name"] == "weapons")
            self.assertEqual(section["state"], "partial")
            next_page = call_tool(q, "get_unit_combat_profile", {"unit_key":"Lothern Sea Guard", "section":"weapons",
                                                                "limit":1, "cursor":section["cursor"]})
            self.assertEqual(next_page["structuredContent"]["data"]["units"][0]["coverage"]["sections"][1]["offset"], 1)
            ref = packet["units"][0]["provenance_refs"][0]
            self.assertIn(ref, call_tool(q, "get_provenance", {"record_ids":[ref]})["structuredContent"]["data"]["provenance"])
            self.assertEqual(call_tool(q, "get_detail", {"ref":"record:" + ref, "limit":1})["structuredContent"]["status"], "ok")
            self.assertTrue(call_tool(q, "get_unit_combat_profile", {"unit_key":"absent"})["isError"])
            with self.assertRaises(ValueError):
                call_tool(q, "get_unit_combat_profile", {"unit_key":"Lothern Sea Guard", "limit":0})

    def test_four_pairs_and_ambiguous_mcp_name(self):
        pairs = [("Reiksguard", "Doom Diver Catapults"),
                 ("Lothern Sea Guard", "Blue Horrors of Tzeentch"),
                 ("Bloodletters of Khorne", "Kroxigor"),
                 ("Queen Bess", "Reiksguard")]
        with Queries(DB) as q:
            for a, b in pairs:
                with self.subTest(a=a, b=b):
                    response = call_tool(q, "get_matchup_evidence", {"unit_a":a, "unit_b":b, "limit":256})
                    self.assertFalse(response.get("isError"))
                    packet = response["structuredContent"]["data"]
                    self.assertEqual(len(packet["units"]), 2)
                    self.assertEqual(packet["snapshot"]["commit"], q.snapshot["source_commit"])
                    self.assertTrue(all(u["identity"]["unit_key"] and u["provenance_refs"] for u in packet["units"]))
                    self.assertEqual(len(movement_phase(q, a, b, separation_metres=200)["sourced_inputs"]), 2)
            artillery = call_tool(q, "get_unit_combat_profile", {"unit_key":"Doom Diver Catapults", "limit":256})["structuredContent"]["data"]["units"][0]
            self.assertGreaterEqual(len(artillery["body"]["components"]), 2)
            self.assertIsNotNone(artillery["ranged"])
            ambiguous = call_tool(q, "resolve_unit", {"name_or_key":"Feral Manticore"})["structuredContent"]["data"]
            self.assertEqual(ambiguous["status"], "ambiguous")
            self.assertGreater(len(ambiguous["candidates"]), 1)

    def test_mcp_stdio_process(self):
        messages = [
            {"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"test","version":"1"}}},
            {"jsonrpc":"2.0","method":"notifications/initialized"},
            {"jsonrpc":"2.0","id":2,"method":"tools/list"},
            {"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"get_matchup_evidence",
               "arguments":{"unit_a":"Bloodletters of Khorne","unit_b":"Kroxigor","limit":256}}},
        ]
        env = dict(os.environ, PYTHONPATH=str(ROOT / "src"))
        run = subprocess.run([sys.executable, "-m", "ctw_adviser.mcp", "--db", str(DB)],
                             input="".join(json.dumps(m) + "\n" for m in messages),
                             capture_output=True, text=True, env=env, check=True)
        responses = [json.loads(line) for line in run.stdout.splitlines()]
        self.assertEqual([r["id"] for r in responses], [1, 2, 3])
        self.assertEqual(responses[0]["result"]["protocolVersion"], "2025-06-18")
        self.assertEqual(responses[2]["result"]["structuredContent"]["data"]["units"][0]["identity"]["name"],
                         "Bloodletters of Khorne")


if __name__ == "__main__":
    unittest.main()
