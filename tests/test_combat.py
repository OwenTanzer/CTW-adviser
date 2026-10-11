"""Combat arithmetic and packet-contract checks; full-store probes are optional."""

import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from ctw_adviser.combat import _armour_survival, _damage_per_hit, evaluate_matchup
from ctw_adviser.queries import Queries

DB = Path(os.environ.get("CTW_ADVISER_DB", ROOT / "work" / "adviser.sqlite"))


class PacketQueries:
    """Source-backed design packets exercise the same Queries return shape."""

    def __init__(self, left="sea_guard", right="blue_horrors"):
        self.left = left
        self.right = right
        self.mutate = None

    def get_matchup_evidence(self, unit_a, unit_b, **options):
        if options:
            assert options["limit"] == 256 and options["include_diagnostics"] and options["include_provenance"]
        a = json.loads((ROOT / "fixtures" / "source_backed" / f"{self.left}.json").read_text(encoding="utf-8"))
        b = json.loads((ROOT / "fixtures" / "source_backed" / f"{self.right}.json").read_text(encoding="utf-8"))
        a["units"] = [a["units"][0], b["units"][0]]
        for unit in a["units"]:
            unit["body"].setdefault("target_classification", {
                "combat_class": "large" if unit["body"]["size"] in ("medium", "large", "very_large") else "infantry"})
        if self.mutate:
            self.mutate(a)
        return a


class CombatTests(unittest.TestCase):
    def test_armour_integral_and_attack_type(self):
        self.assertEqual(_armour_survival(0), 1)
        self.assertAlmostEqual(_armour_survival(80), .4)
        self.assertAlmostEqual(_armour_survival(200), 0)
        unit = PacketQueries().get_matchup_evidence("a", "b")["units"][1]
        ordinary = _damage_per_hit(20, 5, unit, {"magical": False}, "missile", "front")
        magical = _damage_per_hit(20, 5, unit, {"magical": True}, "missile", "front")
        self.assertGreater(magical["per_unblocked_hit"], ordinary["per_unblocked_hit"])
        self.assertGreaterEqual(magical["per_unblocked_hit"], 5)

    def test_two_sided_mixed_ledger_and_reproducibility(self):
        q = PacketQueries()
        scenario = {"separation_metres": 200, "duration_seconds": 90,
                    "sides": {"a": {"cycle_seconds": 12, "active_contacts": 10},
                              "b": {"cycle_seconds": 9, "active_contacts": 8}}}
        result = evaluate_matchup(q, "Sea Guard", "Blue Horrors", scenario=scenario)
        self.assertEqual(result, evaluate_matchup(q, "Sea Guard", "Blue Horrors", scenario=scenario))
        self.assertEqual(result["snapshot"]["commit"], "595e22764b22e748afdbafafcb0a6258973e2451")
        self.assertEqual(result["empirical_calibration"], None)
        self.assertIsNotNone(result["derived"]["phase_timing"]["contact"]["seconds"])
        for row in result["derived"]["ledgers"]:
            self.assertGreater(row["incoming_damage"]["direct"] +
                               row["incoming_damage"].get("barrier_absorbed", 0), 0)
            self.assertGreater(row["incoming_damage"]["melee"], 0)
            self.assertGreater(row["discrete_firing_events"], 0)
            self.assertIn(row["stopping"]["routing"],
                          ("unknown_no_morale_model", "not_applicable_daemonic_attribute_instability_unmodeled"))
        self.assertGreater(result["derived"]["ledgers"][1]["incoming_damage"]["barrier_absorbed"], 0)
        self.assertTrue(result["verdict"]["one_parameter_flip_thresholds"])
        self.assertIn("unresolved", " ".join(result["limitations"]))

    def test_distance_orders_contacts_and_shield_facing(self):
        q = PacketQueries()
        close = evaluate_matchup(q, "a", "b", scenario={"separation_metres": 100})
        far = evaluate_matchup(q, "a", "b", scenario={"separation_metres": 200})
        self.assertLess(close["derived"]["phase_timing"]["contact"]["seconds"],
                        far["derived"]["phase_timing"]["contact"]["seconds"])
        hold = evaluate_matchup(q, "a", "b", scenario={"separation_metres": 100,
                                 "sides": {"a": {"order": "hold", "fight": False},
                                           "b": {"order": "hold", "fight": False}}})
        self.assertIsNone(hold["derived"]["phase_timing"]["contact"]["seconds"])
        self.assertEqual(hold["derived"]["ledgers"][0]["incoming_damage"]["melee"], 0)
        low_contact = evaluate_matchup(q, "a", "b", scenario={"separation_metres": 0,
                                         "sides": {"a": {"active_contacts": 1, "fire": False},
                                                   "b": {"fight": False, "fire": False}}})
        high_contact = evaluate_matchup(q, "a", "b", scenario={"separation_metres": 0,
                                          "sides": {"a": {"active_contacts": 10, "fire": False},
                                                    "b": {"fight": False, "fire": False}}})
        self.assertGreater(high_contact["derived"]["ledgers"][1]["incoming_damage"]["melee"],
                           low_contact["derived"]["ledgers"][1]["incoming_damage"]["melee"])
        artillery = PacketQueries("queen_bess", "wargor")
        front = evaluate_matchup(artillery, "a", "b", scenario={"separation_metres": 100,
                                  "sides": {"a": {"order": "hold", "fight": False},
                                            "b": {"order": "hold", "fight": False, "facing": "front"}}})
        rear = evaluate_matchup(artillery, "a", "b", scenario={"separation_metres": 100,
                                 "sides": {"a": {"order": "hold", "fight": False},
                                           "b": {"order": "hold", "fight": False, "facing": "rear"}}})
        self.assertGreater(rear["derived"]["ledgers"][1]["incoming_damage"]["direct"],
                           front["derived"]["ledgers"][1]["incoming_damage"]["direct"])
        self.assertGreater(front["derived"]["ledgers"][1]["incoming_damage"]["explosion"], 0)

    def test_melee_only_unsupported_rules_and_packet_mutation(self):
        q = PacketQueries("wargor", "kroxigor")
        base = evaluate_matchup(q, "a", "b", scenario={"separation_metres": 0,
                                 "sides": {"a": {"charge_duration_seconds": 0},
                                           "b": {"fight": False}}})
        charged = evaluate_matchup(q, "a", "b", scenario={"separation_metres": 0,
                                    "sides": {"a": {"charge_duration_seconds": 10},
                                              "b": {"fight": False}}})
        self.assertGreater(charged["derived"]["ledgers"][1]["incoming_damage"]["melee"],
                           base["derived"]["ledgers"][1]["incoming_damage"]["melee"])
        q.mutate = lambda p: p["units"][0]["melee"].__setitem__("base_damage", 300)
        changed = evaluate_matchup(q, "a", "b", scenario={"separation_metres": 0,
                                    "sides": {"b": {"fight": False}}})
        self.assertGreater(changed["derived"]["ledgers"][1]["incoming_damage"]["melee"],
                           base["derived"]["ledgers"][1]["incoming_damage"]["melee"])
        disabled = evaluate_matchup(q, "a", "b", scenario={"historical_relations_apply_to_patch_9": False})
        self.assertEqual(disabled["verdict"]["nominal_favored"], "indeterminate")

    def test_rejects_unsupported_baseline_and_nested_volley_without_assumption(self):
        q = PacketQueries()
        with self.assertRaisesRegex(ValueError, "baseline"):
            evaluate_matchup(q, "a", "b", scenario={"baseline": "campaign"})
        q.mutate = lambda p: p["units"][0]["ranged"].__setitem__("burst_size", 3)
        result = evaluate_matchup(q, "a", "b")
        self.assertEqual(result["derived"]["ledgers"][0]["shots_fired_per_shooter"], 0)
        self.assertIn("nesting unresolved", " ".join(result["limitations"]))
        overridden = evaluate_matchup(q, "a", "b", scenario={"sides": {"a": {"projectiles_per_cycle": 3}}})
        self.assertGreater(overridden["derived"]["ledgers"][0]["shots_fired_per_shooter"], 0)


@unittest.skipUnless(DB.exists(), "set CTW_ADVISER_DB to a built pinned snapshot")
class PinnedStoreTests(unittest.TestCase):
    def test_named_and_outside_pairs_via_queries(self):
        pairs = [("Reiksguard", "Doom Diver Catapults"),
                 ("Lothern Sea Guard (Shields)", "Blue Horrors of Tzeentch"),
                 ("Bloodletters of Khorne", "Kroxigor"),
                 ("Queen Bess", "Reiksguard")]
        with Queries(DB) as q:
            for a, b in pairs:
                with self.subTest(a=a, b=b):
                    result = evaluate_matchup(q, a, b)
                    self.assertEqual(len(result["derived"]["ledgers"]), 2)
                    self.assertEqual(result["snapshot"]["commit"], "595e22764b22e748afdbafafcb0a6258973e2451")
                    self.assertTrue(result["snapshot"]["serving_contract_sha256"])
                    self.assertTrue(all(item["sha256"] for item in result["source_fingerprints"].values()))

    def test_controlled_real_scenario_changes(self):
        with Queries(DB) as q:
            far = evaluate_matchup(q, "Lothern Sea Guard (Shields)", "Blue Horrors of Tzeentch",
                                   scenario={"separation_metres": 200})
            near = evaluate_matchup(q, "Lothern Sea Guard (Shields)", "Blue Horrors of Tzeentch",
                                    scenario={"separation_metres": 100})
            self.assertLess(near["derived"]["phase_timing"]["contact"]["seconds"],
                            far["derived"]["phase_timing"]["contact"]["seconds"])
            held = evaluate_matchup(q, "Lothern Sea Guard (Shields)", "Blue Horrors of Tzeentch",
                                    scenario={"separation_metres": 100, "sides": {
                                        "a": {"order": "hold"}, "b": {"order": "hold"}}})
            self.assertIsNone(held["derived"]["phase_timing"]["contact"]["seconds"])
            self.assertEqual(held["derived"]["ledgers"][0]["incoming_damage"]["melee"], 0)
            sparse = evaluate_matchup(q, "Bloodletters of Khorne", "Kroxigor",
                                      scenario={"separation_metres": 0, "sides": {
                                          "a": {"active_contacts": 1}, "b": {"fight": False}}})
            dense = evaluate_matchup(q, "Bloodletters of Khorne", "Kroxigor",
                                     scenario={"separation_metres": 0, "sides": {
                                         "a": {"active_contacts": 12}, "b": {"fight": False}}})
            self.assertGreater(dense["derived"]["ledgers"][1]["incoming_damage"]["melee"],
                               sparse["derived"]["ledgers"][1]["incoming_damage"]["melee"])

    def test_cli_library_equality(self):
        scenario = {"separation_metres": 100, "sides": {"a": {"active_contacts": 4}}}
        with Queries(DB) as q:
            expected = evaluate_matchup(q, "Lothern Sea Guard (Shields)", "Blue Horrors of Tzeentch", scenario=scenario)
        command = [sys.executable, "-m", "ctw_adviser.cli", "evaluate", "--db", str(DB),
                   "Lothern Sea Guard (Shields)", "Blue Horrors of Tzeentch", "--scenario", json.dumps(scenario)]
        run = subprocess.run(command, capture_output=True, text=True,
                             env=dict(os.environ, PYTHONPATH=str(ROOT / "src")), check=True)
        self.assertEqual(json.loads(run.stdout), expected)


if __name__ == "__main__":
    unittest.main()
