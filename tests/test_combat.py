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


class SavedPacketQueries:
    def __init__(self, packet, snapshot):
        self.packet = packet
        self.snapshot = snapshot

    def get_matchup_evidence(self, *_args, **_kwargs):
        return copy.deepcopy(self.packet)


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

    def test_lethal_arrival_precedes_later_firing_opportunity(self):
        q = PacketQueries()
        q.mutate = lambda p: p["units"][1]["ranged"].__setitem__("base_damage", 100000)
        result = evaluate_matchup(q, "a", "b", scenario={"separation_metres": 10,
            "duration_seconds": 1, "sides": {
                "a": {"order": "hold", "facing": "rear", "first_shot_delay_seconds": 0,
                      "cycle_seconds": .5, "collision_probability": 1, "fight": False},
                "b": {"order": "hold", "first_shot_delay_seconds": 0,
                      "cycle_seconds": .5, "collision_probability": 1, "fight": False}}})
        self.assertEqual(result["derived"]["ledgers"][0]["shots_fired_per_shooter"], 1)
        self.assertLess(result["derived"]["ledgers"][0]["stopping"]["health_depleted_seconds"], .5)
        self.assertEqual(result["derived"]["ledgers"][1]["shots_fired_per_shooter"], 2)

    def test_missing_reload_gates_verdict_until_cycle_is_assumed(self):
        q = PacketQueries()
        scenario = {"separation_metres": 100}
        baseline = evaluate_matchup(q, "a", "b", scenario=scenario)
        self.assertGreater(baseline["derived"]["ledgers"][0]["shots_fired_per_shooter"], 0)
        q.mutate = lambda p: p["units"][0]["ranged"].__setitem__("reload_time", None)
        missing = evaluate_matchup(q, "a", "b", scenario=scenario)
        self.assertEqual(missing["derived"]["ledgers"][0]["shots_fired_per_shooter"], 0)
        self.assertTrue(missing["verdict"]["material_mechanic_unresolved"])
        self.assertEqual(missing["verdict"]["nominal_favored"], "indeterminate")
        self.assertIn("complete firing cycle unresolved", " ".join(missing["limitations"]))
        supplied = evaluate_matchup(q, "a", "b", scenario={
            **scenario, "sides": {"a": {"cycle_seconds": 13.75}}})
        self.assertGreater(supplied["derived"]["ledgers"][0]["shots_fired_per_shooter"], 0)
        self.assertNotIn("complete firing cycle unresolved", " ".join(supplied["limitations"]))

    def test_short_charge_window_is_integrated_before_decay(self):
        q = PacketQueries("wargor", "kroxigor")
        damage = []
        for seconds in (0, .1, .4):
            result = evaluate_matchup(q, "a", "b", scenario={
                "separation_metres": 0, "duration_seconds": 1,
                "sides": {"a": {"charge_duration_seconds": seconds, "fire": False,
                                "active_contacts": 1},
                          "b": {"fight": False, "fire": False}}})
            damage.append(result["derived"]["ledgers"][1]["incoming_damage"]["melee"])
        self.assertLess(damage[0], damage[1])
        self.assertLess(damage[1], damage[2])


@unittest.skipUnless(DB.exists(), "set CTW_ADVISER_DB to a built pinned snapshot")
class PinnedStoreTests(unittest.TestCase):
    def test_nullable_active_ranged_and_defence_inputs_gate_verdict(self):
        scenario = {"separation_metres": 80, "duration_seconds": 60,
                    "barrier_damage_order": "barrier_first",
                    "sides": {"a": {"order": "hold"}, "b": {"order": "hold"}}}
        cases = [
            (1, ("passives", "protection", "armour"), "passives.protection.armour"),
            (1, ("passives", "protection", "ward_save"), "passives.protection.ward_save"),
            (1, ("passives", "protection", "physical_resistance"), "passives.protection.physical_resistance"),
            (1, ("passives", "protection", "missile_resistance"), "passives.protection.missile_resistance"),
            (1, ("passives", "protection", "shield_block_chance"), "passives.protection.shield_block_chance"),
            (1, ("body", "barrier_health"), "body.barrier_health"),
            (0, ("ranged", "range"), "ranged.range"),
            (0, ("ranged", "minimum_range"), "ranged.minimum_range"),
            (0, ("ranged", "base_damage"), "ranged.base_damage"),
            (0, ("ranged", "ap_damage"), "ranged.ap_damage"),
            (0, ("ranged", "reload_time"), "ranged.reload_time"),
            (0, ("ranged", "projectiles_per_shot"), "ranged.projectiles_per_shot"),
            (0, ("ranged", "velocity"), "ranged.velocity"),
            (0, ("ranged", "ammunition_supply", "capacity"), "ranged.ammunition_supply.capacity"),
            (0, ("ranged", "ammunition_supply", "unlimited"), "ranged.ammunition_supply.unlimited"),
        ]
        with Queries(DB) as q:
            packet = q.get_matchup_evidence("Lothern Sea Guard (Shields)", "Blue Horrors of Tzeentch",
                                            limit=256, include_diagnostics=True, include_provenance=True)
            baseline = evaluate_matchup(SavedPacketQueries(packet, q.snapshot), "a", "b", scenario=scenario)
            self.assertEqual(baseline["verdict"]["status"], "conditional")
            self.assertFalse(baseline["verdict"]["unresolved_inputs"])
            for side, path, expected in cases:
                with self.subTest(path=path):
                    changed = copy.deepcopy(packet)
                    node = changed["units"][side]
                    for key in path[:-1]:
                        node = node[key]
                    node[path[-1]] = None
                    result = evaluate_matchup(SavedPacketQueries(changed, q.snapshot), "a", "b",
                                              scenario=scenario)
                    self.assertEqual(result["verdict"]["status"], "indeterminate")
                    self.assertTrue(result["verdict"]["material_mechanic_unresolved"])
                    self.assertIn(("a" if side == 0 else "b", expected),
                                  {(item["side"], item["source_path"])
                                   for item in result["verdict"]["unresolved_inputs"]})
            disputed = copy.deepcopy(packet)
            disputed["units"][0]["ranged"]["ammunition_supply"]["assignment_status"] = "source_disagreement"
            result = evaluate_matchup(SavedPacketQueries(disputed, q.snapshot), "a", "b", scenario=scenario)
            self.assertEqual(result["verdict"]["status"], "indeterminate")
            self.assertIn("ranged.ammunition_supply.assignment_status",
                          {item["source_path"] for item in result["verdict"]["unresolved_inputs"]})

    def test_nullable_melee_timing_and_health_inputs_gate_without_crashing(self):
        melee_scenario = {"separation_metres": 0, "duration_seconds": 2,
                          "barrier_damage_order": "barrier_first",
                          "sides": {"a": {"fire": False}, "b": {"fight": False, "fire": False}}}
        with Queries(DB) as q:
            packet = q.get_matchup_evidence("Lothern Sea Guard (Shields)", "Blue Horrors of Tzeentch",
                                            limit=256, include_diagnostics=True, include_provenance=True)
            for side, section, field in ((0, "melee", "attack"), (0, "melee", "base_damage"),
                                         (0, "melee", "ap_damage"), (0, "melee", "attack_interval"),
                                         (1, "melee", "defence")):
                with self.subTest(field=field):
                    changed = copy.deepcopy(packet)
                    changed["units"][side][section][field] = None
                    result = evaluate_matchup(SavedPacketQueries(changed, q.snapshot), "a", "b",
                                              scenario=melee_scenario)
                    self.assertEqual(result["verdict"]["status"], "indeterminate")
                    self.assertIn(f"melee.{field}",
                                  {item["source_path"] for item in result["verdict"]["unresolved_inputs"]})
            missing_health = copy.deepcopy(packet)
            missing_health["units"][1]["body"]["components"][0]["health_contribution"] = None
            result = evaluate_matchup(SavedPacketQueries(missing_health, q.snapshot), "a", "b",
                                      scenario=melee_scenario)
            self.assertIsNone(result["derived"]["ledgers"])
            self.assertEqual(result["verdict"]["status"], "indeterminate")
            missing_speed = copy.deepcopy(packet)
            missing_speed["units"][0]["movement"]["speed"] = None
            result = evaluate_matchup(SavedPacketQueries(missing_speed, q.snapshot), "a", "b",
                                      scenario={"separation_metres": 80, "duration_seconds": 2,
                                                "barrier_damage_order": "barrier_first",
                                                "sides": {"a": {"order": "approach"},
                                                          "b": {"order": "hold"}}})
            self.assertIn("movement.speed",
                          {item["source_path"] for item in result["verdict"]["unresolved_inputs"]})

    def test_known_zero_and_disabled_inputs_are_not_unknown(self):
        with Queries(DB) as q:
            packet = q.get_matchup_evidence("Lothern Sea Guard (Shields)", "Blue Horrors of Tzeentch",
                                            limit=256, include_diagnostics=True, include_provenance=True)
            scenario = {"separation_metres": 80, "barrier_damage_order": "barrier_first",
                        "sides": {"a": {"order": "hold"}, "b": {"order": "hold"}}}
            changed = copy.deepcopy(packet)
            changed["units"][1]["passives"]["protection"]["armour"] = 0
            changed["units"][0]["movement"]["speed"] = None
            changed["units"][0]["ranged"]["ammunition"] = None  # Agreed supply capacity is authoritative.
            result = evaluate_matchup(SavedPacketQueries(changed, q.snapshot), "a", "b",
                                      scenario=scenario)
            self.assertFalse(result["verdict"]["material_mechanic_unresolved"])
            self.assertEqual(result["verdict"]["unresolved_inputs"], [])
            changed["units"][0]["ranged"]["base_damage"] = None
            changed["units"][1]["passives"]["protection"]["armour"] = None
            scenario["sides"]["a"]["fire"] = False
            scenario["sides"]["b"]["fire"] = False
            disabled = evaluate_matchup(SavedPacketQueries(changed, q.snapshot), "a", "b",
                                        scenario=scenario)
            self.assertFalse(disabled["verdict"]["material_mechanic_unresolved"])
            self.assertEqual(disabled["verdict"]["unresolved_inputs"], [])

    def test_spell_tagged_explosion_uses_sourced_spell_resistance(self):
        scenario = {"separation_metres": 100, "duration_seconds": 3,
                    "sides": {"a": {"order": "hold", "first_shot_delay_seconds": 0,
                                    "cycle_seconds": 20, "collision_probability": 1,
                                    "flight_seconds": 1, "fight": False},
                              "b": {"order": "hold", "fire": False, "fight": False}}}
        with Queries(DB) as q:
            packet = q.get_matchup_evidence("wh3_dlc29_skv_art_plagueclaw_catapult_ror",
                                            "Blessed Carnosaur", limit=256,
                                            include_diagnostics=True, include_provenance=True)
            self.assertIs(packet["units"][0]["ranged"]["explosion"]["native_parameters"]["is_spell"], True)
            self.assertEqual(packet["units"][1]["passives"]["protection"]["spell_resistance"], 50)
            with_resistance = evaluate_matchup(
                SavedPacketQueries(packet, q.snapshot), "a", "b", scenario=scenario)
            packet["units"][1]["passives"]["protection"]["spell_resistance"] = 0
            without_resistance = evaluate_matchup(
                SavedPacketQueries(packet, q.snapshot), "a", "b", scenario=scenario)
        hit_with = with_resistance["derived"]["event_mechanics"][0]["missile"]["explosion"]["damage"]
        hit_without = without_resistance["derived"]["event_mechanics"][0]["missile"]["explosion"]["damage"]
        self.assertTrue(hit_with["spell_resistance_applied"])
        self.assertEqual(hit_with["resistance_points"], 50)
        self.assertAlmostEqual(hit_with["per_unblocked_hit"], hit_without["per_unblocked_hit"] / 2)
        self.assertLess(with_resistance["derived"]["ledgers"][1]["incoming_damage"]["explosion"],
                        without_resistance["derived"]["ledgers"][1]["incoming_damage"]["explosion"])

    def test_nullable_explosion_inputs_gate_without_crashing(self):
        scenario = {"separation_metres": 100, "duration_seconds": 3,
                    "sides": {"a": {"order": "hold", "first_shot_delay_seconds": 0,
                                    "cycle_seconds": 20, "flight_seconds": 1, "fight": False},
                              "b": {"order": "hold", "fire": False, "fight": False}}}
        with Queries(DB) as q:
            packet = q.get_matchup_evidence("wh3_dlc29_skv_art_plagueclaw_catapult_ror",
                                            "Blessed Carnosaur", limit=256,
                                            include_diagnostics=True, include_provenance=True)
            for path in (("base_damage",), ("ap_damage",), ("native_parameters", "is_spell")):
                with self.subTest(path=path):
                    changed = copy.deepcopy(packet)
                    node = changed["units"][0]["ranged"]["explosion"]
                    for key in path[:-1]:
                        node = node[key]
                    node[path[-1]] = None
                    result = evaluate_matchup(SavedPacketQueries(changed, q.snapshot), "a", "b",
                                              scenario=scenario)
                    self.assertEqual(result["verdict"]["status"], "indeterminate")
                    self.assertTrue(result["verdict"]["unresolved_inputs"])
                    self.assertIn("ranged.explosion." + ".".join(path),
                                  {item["source_path"] for item in result["verdict"]["unresolved_inputs"]})

    def test_barrier_order_exposes_overkill_and_gates_default_verdict(self):
        scenario = {"separation_metres": 100, "duration_seconds": 2,
                    "sides": {"a": {"order": "hold", "first_shot_delay_seconds": 0,
                                    "cycle_seconds": 20, "collision_probability": 1, "fight": False},
                              "b": {"order": "hold", "fire": False, "fight": False}}}
        with Queries(DB) as q:
            default = evaluate_matchup(q, "Queen Bess", "Blue Horrors of Tzeentch", scenario=scenario)
            scenario["barrier_damage_order"] = "entity_cap_first"
            cap_first = evaluate_matchup(q, "Queen Bess", "Blue Horrors of Tzeentch", scenario=scenario)
        self.assertEqual(default["verdict"]["status"], "indeterminate")
        self.assertTrue(default["verdict"]["material_mechanic_unresolved"])
        self.assertEqual(default["scenario_assumptions"]["barrier_damage_order"], "barrier_first")
        self.assertFalse(default["scenario_assumptions"]["barrier_damage_order_explicit"])
        self.assertEqual(default["derived"]["ledgers"][1]["incoming_damage"]["overkill"], 0)
        self.assertGreater(cap_first["derived"]["ledgers"][1]["incoming_damage"]["overkill"], 200)
        self.assertLess(cap_first["derived"]["ledgers"][1]["incoming_damage"]["barrier_absorbed"],
                        default["derived"]["ledgers"][1]["incoming_damage"]["barrier_absorbed"])
        self.assertEqual(len(default["verdict"]["barrier_damage_order_sensitivity"]), 2)
        self.assertFalse(cap_first["verdict"]["material_mechanic_unresolved"])

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

    def test_nonpositive_velocity_and_exact_fire_range(self):
        with Queries(DB) as q:
            artillery = evaluate_matchup(q, "Reiksguard", "Doom Diver Catapults", scenario={
                "separation_metres": 200, "duration_seconds": 1,
                "sides": {"a": {"order": "hold", "fight": False},
                          "b": {"order": "hold", "fight": False, "first_shot_delay_seconds": 0}}})
            self.assertEqual(artillery["source_facts"][1]["ranged"]["velocity"], -1)
            self.assertEqual(artillery["derived"]["ledgers"][0]["incoming_damage"]["direct"], 0)
            self.assertEqual(artillery["verdict"]["status"], "indeterminate")
            explicit = evaluate_matchup(q, "Reiksguard", "Doom Diver Catapults", scenario={
                "separation_metres": 200, "duration_seconds": 1,
                "sides": {"a": {"order": "hold", "fight": False},
                          "b": {"order": "hold", "fight": False, "first_shot_delay_seconds": 0,
                                "flight_seconds": .25}}})
            self.assertGreater(explicit["derived"]["ledgers"][0]["incoming_damage"]["direct"], 0)
            bess = evaluate_matchup(q, "Queen Bess", "Reiksguard", scenario={
                "separation_metres": 55, "duration_seconds": 2,
                "sides": {"a": {"order": "hold", "first_shot_delay_seconds": .75,
                                "cycle_seconds": 10, "fight": False},
                          "b": {"order": "approach", "fire": False, "fight": False}}})
            self.assertEqual(bess["derived"]["ledgers"][0]["shots_fired_per_shooter"], 0)
            self.assertEqual(bess["derived"]["ledgers"][1]["incoming_damage"]["direct"], 0)

    def test_component_target_class_and_targetability(self):
        with Queries(DB) as q:
            scenario = {"separation_metres": 0, "duration_seconds": 1,
                        "sides": {"a": {"fire": False},
                                  "b": {"fire": False, "fight": False,
                                        "target_component_role": "crew_or_rider"}}}
            crew = evaluate_matchup(q, "Lothern Sea Guard (Shields)", "Doom Diver Catapults",
                                    scenario=scenario)
            mechanics = crew["derived"]["event_mechanics"][0]["melee"]
            self.assertEqual(mechanics["target_combat_class"], "infantry")
            self.assertIsNone(mechanics["per_hit"])
            self.assertEqual(crew["derived"]["ledgers"][1]["incoming_damage"]["melee"], 0)
            self.assertEqual(crew["verdict"]["status"], "indeterminate")
            scenario["sides"]["b"].update(assume_targetable=True,
                                           assume_unit_protection_for_component=True)
            assumed_crew = evaluate_matchup(q, "Lothern Sea Guard (Shields)", "Doom Diver Catapults",
                                            scenario=scenario)
            engine = evaluate_matchup(q, "Lothern Sea Guard (Shields)", "Doom Diver Catapults",
                                      scenario={"separation_metres": 0, "duration_seconds": 1,
                                                "sides": {"a": {"fire": False},
                                                          "b": {"fire": False, "fight": False}}})
            crew_hit = assumed_crew["derived"]["event_mechanics"][0]["melee"]
            engine_hit = engine["derived"]["event_mechanics"][0]["melee"]
            self.assertEqual(crew_hit["per_hit"]["size_bonus_as_base"], 0)
            self.assertEqual(engine_hit["per_hit"]["size_bonus_as_base"], 16)
            self.assertLess(crew_hit["unmodified_hit_probability"], engine_hit["unmodified_hit_probability"])

    def test_melee_contact_flip_and_fractional_charge(self):
        with Queries(DB) as q:
            base = {"separation_metres": 0, "sides": {"b": {"active_contacts": 1}}}
            one = evaluate_matchup(q, "Bloodletters of Khorne", "Kroxigor", scenario=base)
            base["sides"]["b"]["active_contacts"] = 2
            two = evaluate_matchup(q, "Bloodletters of Khorne", "Kroxigor", scenario=base)
            self.assertNotEqual(one["verdict"]["represented_point_ordering"],
                                two["verdict"]["represented_point_ordering"])
            self.assertTrue(one["verdict"]["bounds_cross"])
            self.assertTrue(two["verdict"]["bounds_cross"])
            charge = evaluate_matchup(q, "Reiksguard", "Doom Diver Catapults", scenario={
                "separation_metres": 4.9, "duration_seconds": 1,
                "sides": {"a": {"fire": False, "active_contacts": 1,
                                "charge_duration_seconds": 1},
                          "b": {"fire": False, "fight": False}}})
            self.assertAlmostEqual(charge["derived"]["phase_timing"]["contact"]["seconds"], .5)
            self.assertLess(charge["derived"]["ledgers"][1]["incoming_damage"]["melee"], 8.12)

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
