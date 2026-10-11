"""Bounded, deterministic movement phase consumer of the serving query library."""

from __future__ import annotations

import math

from .queries import Queries

MODEL_VERSION = "movement-1.0.0"
ORDERS = {"approach": 1, "hold": 0, "retreat": -1}


def _number(value, name, *, positive=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{name} must be a finite number")
    invalid_sign = value <= 0 if positive else value < 0
    if invalid_sign:
        raise ValueError(f"{name} must be {'positive' if positive else 'nonnegative'}")
    return float(value)


def _entry(distance, threshold, closing):
    if distance <= threshold:
        return {"status": "already_reached", "seconds": 0.0}
    if closing <= 0:
        return {"status": "not_reached_under_assumptions", "seconds": None}
    return {"status": "reached_under_assumptions", "seconds": (distance - threshold) / closing}


def movement_phase(queries: Queries, unit_a: str, unit_b: str, *, separation_metres: float,
                   order_a: str = "approach", order_b: str = "approach",
                   metres_per_second_per_speed_point: float = 1.0,
                   subculture_a: str | None = None, subculture_b: str | None = None):
    """Project straight-line separation; never infer firing, damage, or a winner."""
    distance = _number(separation_metres, "separation_metres")
    scale = _number(metres_per_second_per_speed_point,
                    "metres_per_second_per_speed_point", positive=True)
    if order_a not in ORDERS or order_b not in ORDERS:
        raise ValueError("orders must be approach, hold, or retreat")
    packet = queries.get_matchup_evidence(unit_a, unit_b, subculture=subculture_a,
                                          subculture_b=subculture_b, limit=256)
    facts = []
    for unit in packet["units"]:
        movement = unit["movement"]
        speed = movement["speed"]
        if speed is not None:
            speed = _number(speed, "sourced speed")
        ranged = unit["ranged"]
        weapons_state = next(s for s in unit["coverage"]["sections"] if s["name"] == "weapons")
        attacks = []
        if ranged and ranged.get("status") == "present":
            for attack in [ranged] + ranged.get("variants", []):
                range_value = attack.get("range")
                if range_value is not None:
                    range_value = _number(range_value, "sourced range")
                attacks.append({"attack_id": attack["id"], "weapon_key": attack["weapon_key"],
                                "projectile_key": attack["projectile_key"], "range_metres": range_value,
                                "provenance_refs": attack["provenance_refs"]})
        facts.append({"identity": unit["identity"], "native_speed": speed,
                      "speed_basis": movement.get("speed_basis"),
                      "speed_provenance_refs": movement["provenance_refs"],
                      "ranged_coverage": unit["coverage"]["ranged"],
                      "weapons_section": weapons_state, "ranged_attacks": attacks})
    speeds = [f["native_speed"] for f in facts]
    closing = None if None in speeds else scale * (ORDERS[order_a] * speeds[0] + ORDERS[order_b] * speeds[1])
    def timing(threshold):
        if threshold is None or closing is None:
            return {"status": "unknown_input", "seconds": None}
        return _entry(distance, threshold, closing)
    range_entries = []
    for fact in facts:
        results = []
        if fact["weapons_section"]["state"] == "complete":
            for attack in fact["ranged_attacks"]:
                results.append({"attack_id": attack["attack_id"], **timing(attack["range_metres"])})
        range_entries.append({"unit_key": fact["identity"]["unit_key"],
                              "status": "complete" if fact["weapons_section"]["state"] == "complete" else "partial",
                              "attacks": results})
    return {"model_version": MODEL_VERSION, "source_packet_version": packet["schema_version"],
            "snapshot": packet["snapshot"], "sourced_inputs": facts,
            "model_assumptions": {"starting_separation_metres": distance, "order_a": order_a,
                                  "order_b": order_b,
                                  "metres_per_second_per_speed_point": scale,
                                  "path": "straight_line_unobstructed", "speed": "constant_primary_body_run_speed"},
            "derived": {"closing_speed_metres_per_second": closing, "contact": timing(0),
                        "range_entry": range_entries},
            "unmodeled": ["acceleration and charge speed", "terrain and pathfinding", "line of sight and firing arcs",
                          "projectile flight and firing cycles", "damage and casualties", "passive/activated modifiers",
                          "leadership and routing", "campaign availability"]}
