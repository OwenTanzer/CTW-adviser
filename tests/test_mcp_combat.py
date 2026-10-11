"""Adapter contract for the independently developed combat evaluator."""

import importlib.util
import os
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ctw_adviser.mcp import BY_NAME, call_tool, dispatch_method
from ctw_adviser.queries import Queries, ResolutionError


class FakeQueries:
    snapshot = {"source_commit": "595e22764b22e748afdbafafcb0a6258973e2451"}


class CombatAdapterTests(unittest.TestCase):
    def test_discovery_delegation_and_version(self):
        tool = BY_NAME["evaluate_single_unit_matchup"]
        self.assertTrue(tool["annotations"]["readOnlyHint"])
        self.assertEqual(tool["inputSchema"]["properties"]["scenario"]["properties"]["sides"]["properties"]["a"]["type"], "object")
        calls = []

        def evaluate(queries, unit_a, unit_b, **options):
            calls.append((queries, unit_a, unit_b, options))
            return {"model_version": "combat-0.1.0", "verdict": {"status": "conditional"}}

        with patch.dict(sys.modules, {"ctw_adviser.combat": SimpleNamespace(evaluate_matchup=evaluate)}):
            result = call_tool(FakeQueries(), "evaluate_single_unit_matchup", {
                "unit_a": "Lothern Sea Guard (Shields)", "unit_b": "Blue Horrors of Tzeentch",
                "subculture_a": "wh2_main_hef", "scenario": {"duration_seconds": 120,
                    "sides": {"a": {"order": "hold"}}}})
        payload = result["structuredContent"]
        self.assertEqual(payload["model_version"], "combat-0.1.0")
        self.assertEqual(payload["data"]["verdict"]["status"], "conditional")
        self.assertEqual(calls[0][1:3], ("Lothern Sea Guard (Shields)", "Blue Horrors of Tzeentch"))
        self.assertEqual(calls[0][3]["scenario"]["sides"]["a"]["order"], "hold")

    def test_ambiguity_and_invalid_bounds(self):
        def ambiguous(*args, **kwargs):
            raise ResolutionError({"status": "ambiguous", "query": "Feral Manticore",
                                   "candidates": [{"unit_key": "one"}, {"unit_key": "two"}]})

        with patch.dict(sys.modules, {"ctw_adviser.combat": SimpleNamespace(evaluate_matchup=ambiguous)}):
            result = call_tool(FakeQueries(), "evaluate_single_unit_matchup", {
                "unit_a": "Feral Manticore", "unit_b": "Kroxigor"})
        self.assertTrue(result["isError"])
        self.assertEqual(result["structuredContent"]["status"], "ambiguous")
        self.assertEqual(len(result["structuredContent"]["data"]["candidates"]), 2)
        for scenario in ({"duration_seconds": 301}, {"sides": {"a": {"cycle_seconds": .001}}},
                         {"unsupported": 1}):
            response = dispatch_method(FakeQueries(), "tools/call", {"name": "evaluate_single_unit_matchup",
                "arguments": {"unit_a": "Reiksguard", "unit_b": "Kroxigor", "scenario": scenario}}, 1)
            self.assertEqual(response["error"]["code"], -32602)


DB = Path(os.environ.get("CTW_ADVISER_DB", "work/adviser.sqlite"))


@unittest.skipUnless(importlib.util.find_spec("ctw_adviser.combat") and DB.is_file(),
                     "requires the combat candidate plus a pinned SQLite artifact")
class RealCombatAdapterTests(unittest.TestCase):
    def test_library_and_mcp_result_agree(self):
        from ctw_adviser.combat import evaluate_matchup
        scenario = {"separation_metres": 100, "sides": {"a": {"active_contacts": 4}}}
        with Queries(DB) as queries:
            expected = evaluate_matchup(queries, "Lothern Sea Guard (Shields)",
                                        "Blue Horrors of Tzeentch", scenario=scenario)
            actual = call_tool(queries, "evaluate_single_unit_matchup", {
                "unit_a": "Lothern Sea Guard (Shields)", "unit_b": "Blue Horrors of Tzeentch",
                "scenario": scenario})["structuredContent"]
        self.assertEqual(actual["data"], expected)
        self.assertEqual(actual["model_version"], expected["model_version"])


if __name__ == "__main__":
    unittest.main()
