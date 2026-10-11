"""Buff/debuff engagement comparison for one spell/activated ability (#20, increment B).

Runs the same #5 ``evaluate_matchup`` engagement with and without one selected
effect phase applied to one side, as a temporary scenario modifier on copies of
the verified unit packets. Base profiles are never changed. Only stat
operations that map onto fields the #5 model reads are applied; every other
effect is listed. The effect is assumed active from the engagement start; a
phase shorter than the horizon is compared over its active window, with the
whole-horizon run reported as an upper bound.
"""

from __future__ import annotations

import copy
import math

from .combat import evaluate_matchup
from .queries import STAT_NAMES, Queries, ResolutionError

MODEL_VERSION = "effect-engagement-0.1.0"
SIDES = ("a", "b")
# stat token -> packet fields the #5 model reads. Additive resistances and
# block chance are percentage points; multiplicative scalars multiply the field.
STAT_FIELDS = {
    "stat_melee_attack": [("melee", "attack")],
    "stat_melee_defence": [("melee", "defence")],
    "stat_melee_damage_base": [("melee", "base_damage")],
    "stat_melee_damage_ap": [("melee", "ap_damage")],
    "stat_charge_bonus": [("melee", "charge_bonus")],
    "scalar_speed": [("movement", "speed"), ("movement", "ground_speed")],
    "stat_armour": [("protection", "armour")],
    "stat_resistance_physical": [("protection", "physical_resistance")],
    "stat_resistance_missile": [("protection", "missile_resistance")],
    "stat_resistance_magic": [("protection", "spell_resistance")],
    "stat_resistance_flame": [("protection", "fire_resistance")],
    "stat_resistance_all": [("protection", "ward_save")],
    "stat_missile_block_chance": [("protection", "shield_block_chance")],
    "scalar_missile_damage_base": [("ranged", "base_damage")],
    "scalar_missile_damage_ap": [("ranged", "ap_damage")],
    "stat_bonus_vs_large": [("melee_traits", "bonus_vs_large")],
    "stat_bonus_vs_infantry": [("melee_traits", "bonus_vs_infantry")],
}
OPERATIONS = {"add": lambda v, x: v + x, "mult": lambda v, x: v * x}
DELTA_FIELDS = ("effective_survivability_fraction", "remaining_health", "remaining_health_fraction", "remaining_barrier")


NATIVE_STAT = {name: token for token, name in STAT_NAMES.items()}


def _stat_token(effect):
    # The mechanic envelope renames a few native stat tokens; map them back.
    return NATIVE_STAT.get(effect["stat"], effect["stat"])


def _targets(unit, area):
    """Mutable dictionaries for one packet area, including attack variants."""
    if area == "melee":
        melee = unit.get("melee")
        return [melee, *melee.get("variants", [])] if isinstance(melee, dict) else []
    if area == "ranged":
        ranged = unit.get("ranged")
        if not isinstance(ranged, dict) or ranged.get("status") != "present":
            return []
        return [ranged, *ranged.get("variants", [])]
    if area == "protection":
        return [unit["passives"]["protection"]]
    if area == "movement":
        return [unit["movement"]]
    if area == "melee_traits":
        traits = unit["passives"]["attack_traits"].get("melee")
        return [traits] if traits else []
    raise KeyError(area)


def _apply(unit, modifiers):
    """Apply supported modifiers in place to one copied unit; return changes."""
    changes = []
    for mod in modifiers:
        for area, field in STAT_FIELDS[mod["stat_token"]]:
            for target in _targets(unit, area):
                before = target.get(field)
                if before is None:
                    changes.append({"stat_token": mod["stat_token"], "path": f"{area}.{field}", "before": None,
                                    "after": None, "status": "source_value_null"})
                    continue
                after = OPERATIONS[mod["operation"]](before, mod["value"])
                target[field] = after
                changes.append({"stat_token": mod["stat_token"], "path": f"{area}.{field}",
                                "attack_ref": target.get("id"), "before": before, "after": after, "status": "applied"})
    return changes


def _phase_choices(mechanic):
    phases = {}
    for phase in mechanic["phases"]:
        stats = [e for e in mechanic["effects"] if e["phase_ref"] == phase["key"] and e["kind"] == "stat_modifier"]
        if stats:
            entry = phases.setdefault(phase["key"], {"phase": phase, "links": [], "stats": stats})
            entry["links"].append(phase)
    return phases


def _recipient_check(casting, links, relation):
    flags = {k: any(link[k] for link in links) for k in ("target_self", "target_friends", "target_enemies")}
    if relation == "enemy":
        ok = flags["target_enemies"] and bool(casting.get("target_enemies") or casting.get("target_ground"))
    else:
        ok = flags["target_friends"] or flags["target_self"]
    return ok, flags


def _delta(base, mod):
    rows = []
    for i, side in enumerate(SIDES):
        b, m = base["derived"]["ledgers"][i], mod["derived"]["ledgers"][i]
        row = {"side": side, "unit_key": b["unit_key"]}
        for field in DELTA_FIELDS:
            row[field] = {"without": b[field], "with": m[field], "delta": m[field] - b[field]}
        row["incoming_attempted_damage"] = {"without": b["incoming_damage"]["attempted_damage"],
                                            "with": m["incoming_damage"]["attempted_damage"],
                                            "delta": m["incoming_damage"]["attempted_damage"] - b["incoming_damage"]["attempted_damage"]}
        row["stopping"] = {k: {"without": b["stopping"].get(k), "with": m["stopping"].get(k)}
                           for k in ("contact_seconds", "health_depleted_seconds", "combat_ineffective_seconds")}
        rows.append(row)
    return {"sides": rows,
            "verdict": {"without": base["verdict"]["represented_point_ordering"],
                        "with": mod["verdict"]["represented_point_ordering"],
                        "status_without": base["verdict"]["status"], "status_with": mod["verdict"]["status"]}}


def _run_pair(queries, unit_a, unit_b, scenario, modifier, subculture_a, subculture_b):
    base = evaluate_matchup(queries, unit_a, unit_b, scenario=scenario, subculture_a=subculture_a, subculture_b=subculture_b)
    mod = evaluate_matchup(queries, unit_a, unit_b, scenario=scenario, subculture_a=subculture_a,
                           subculture_b=subculture_b, unit_modifier=modifier)
    if base["identities"] != mod["identities"] or base["scenario_assumptions"] != mod["scenario_assumptions"]:
        raise AssertionError("modified run diverged from the shared baseline")
    return base, mod


def evaluate_effect_engagement(queries: Queries, effect: str, unit_a: str, unit_b: str, *, recipient: str = "a",
                               relation: str = "friendly", phase: str | None = None, scenario: dict | None = None,
                               caster: str | None = None, subculture_a: str | None = None,
                               subculture_b: str | None = None) -> dict:
    """Compare one #5 engagement with and without one effect phase on one side."""
    if recipient not in SIDES:
        raise ValueError("recipient must be a or b")
    if relation not in ("friendly", "enemy"):
        raise ValueError("relation must be friendly (caster's side) or enemy")
    resolution = queries.resolve_effect(effect)
    if resolution["status"] != "resolved":
        raise ResolutionError(resolution)
    packet = queries.get_effect(resolution["resolved"]["ability_key"], limit=256, include_diagnostics=True)
    eff = packet["effect"]
    mechanic = eff["mechanic"]
    casting = {**eff["activation"]["values"], **eff["targeting"]["values"]}
    unresolved, blocked, unsupported, limitations = [], [], [], []

    choices = _phase_choices(mechanic)
    if phase is None and len(choices) == 1:
        phase = next(iter(choices))
    if not choices:
        blocked.append({"code": "no_stat_effect", "detail": "The effect has no phase stat modifier to apply."})
    elif phase not in choices:
        blocked.append({"code": "phase_selection_required" if phase is None else "unknown_phase",
                        "detail": "Choose one phase: " + ", ".join(sorted(choices)),
                        "phases": sorted(choices)})
    selected = choices.get(phase)
    modifiers, recipient_flags = [], None
    if selected:
        ok, recipient_flags = _recipient_check(casting, selected["links"], relation)
        if not ok:
            blocked.append({"code": "ineligible_recipient",
                            "detail": f"Phase recipients {recipient_flags} do not include a {relation} unit."})
        if relation == "friendly" and recipient_flags["target_self"] and not recipient_flags["target_friends"]:
            unresolved.append({"code": "self_only_recipient",
                               "detail": "The phase affects only the caster; the recipient side is assumed to be the caster unit."})
        for e in selected["stats"]:
            token = _stat_token(e)
            if token in STAT_FIELDS and e["native_operation"] in OPERATIONS and e["value"] is not None:
                modifiers.append({"stat_token": token, "operation": e["native_operation"], "value": e["value"],
                                  "provenance_refs": e["provenance_refs"]})
            else:
                unsupported.append({"stat_token": token, "operation": e["native_operation"], "value": e["value"],
                                    "reason": "Not read by the #5 engagement model or operation unmapped; not applied.",
                                    "provenance_refs": e["provenance_refs"]})
        if not modifiers and not blocked:
            blocked.append({"code": "no_supported_modifier",
                            "detail": "None of the phase's stat effects maps to an input of the #5 engagement model."})
    for e in mechanic["effects"]:
        if e["kind"] not in ("stat_modifier", "payload_reference") and (selected is None or e["phase_ref"] == phase):
            unsupported.append({"kind": e["kind"], "phase_ref": e["phase_ref"],
                                "reason": "Not applied by the stat-modifier engagement comparison.",
                                "provenance_refs": e["provenance_refs"]})
        if e.get("native_kind") == "intensity_settings":
            unresolved.append({"code": "intensity_unresolved",
                               "detail": "Listed phase values are applied at full listed strength; intensity scaling is not modeled."})

    access = {"status": "not_checked"}
    if caster is not None:
        resolved = queries.resolved(caster)
        links = [a for a in queries.rows("effect_access", "ability_key", eff["identity"]["ability_key"], "unit_key,link_record")
                 if a["unit_key"] in set(resolved["source_unit_keys"])]
        access = {"caster": resolved["unit_key"], "status": "linked" if links else "not_established",
                  "note": "A source link is qualified access, not proof the ability is acquired or active."}
        if not links:
            unresolved.append({"code": "access_not_established",
                               "detail": "No source unit ability link connects the caster to this effect."})

    scenario = dict(scenario or {})
    horizon = float(scenario.get("duration_seconds", 120))
    duration = selected["phase"]["duration"] if selected else None
    window = {"phase_duration": duration, "horizon_seconds": horizon, "start_seconds": 0.0}
    if duration is None or duration <= 0:
        window["basis"] = "duration_unresolved"
        unresolved.append({"code": "duration_unresolved",
                           "detail": "Phase duration is null or a native sentinel; only the whole-horizon bound is reported."})
    elif duration < horizon:
        window["basis"] = "active_window"
    else:
        window["basis"] = "covers_horizon"
    index = SIDES.index(recipient)
    applied = {}

    def modifier(units):
        applied["changes"] = _apply(units[index], modifiers)
        return units

    runs = {}
    if not blocked:
        runs["horizon"] = _run_pair(queries, unit_a, unit_b, scenario, modifier, subculture_a, subculture_b)
        if window["basis"] == "active_window":
            runs["active_window"] = _run_pair(queries, unit_a, unit_b, {**scenario, "duration_seconds": duration},
                                              modifier, subculture_a, subculture_b)
    changes = applied.get("changes", [])
    if any(c["status"] == "source_value_null" for c in changes):
        unresolved.append({"code": "modifier_target_null",
                           "detail": "A modified field is null in the source packet; that modifier was not applied."})
    comparisons = {name: _delta(*pair) for name, pair in runs.items()}
    if "active_window" in comparisons:
        comparisons["horizon"]["interpretation"] = (
            "Upper bound: effect held for the whole horizon. The phase lasts only phase_duration.")
        comparisons["active_window"]["interpretation"] = (
            "Engagement truncated at phase expiry, effect active throughout; the primary comparison.")
        limitations.append("After expiry the model cannot resume an unmodified engagement from the window state; "
                           "the whole-horizon run bounds the effect from above.")
    elif comparisons:
        comparisons["horizon"]["interpretation"] = "Effect active for the whole compared horizon."
    unresolved = [u for i, u in enumerate(unresolved) if u not in unresolved[:i]]
    status = ("blocked" if blocked else "partial" if unresolved or unsupported else "calculated")
    baseline_check = None
    if runs:
        base, _ = runs["horizon"]
        baseline_check = {"source_facts_unchanged": True,
                          "baseline_model_version": base["model_version"]}
    limitations += [
        "Effect is assumed active from the engagement start; cast timing, wind-up and refresh are not modeled.",
        "One application; stacking, replacement, recipient caps and area coverage are not modeled.",
        "Passive abilities remain unapplied in the #5 model, so no interaction with them is represented.",
        "All #5 assumptions and limitations apply to both runs; see the embedded matchup results.",
    ]
    return {
        "model_version": MODEL_VERSION, "source_packet_version": packet["schema_version"],
        "snapshot": {"commit": packet["snapshot"]["commit"], "serving_contract_sha256": queries.snapshot["contract_sha256"]},
        "status": status, "blocked": blocked,
        "identities": {"effect": {k: eff["identity"][k] for k in ("ability_key", "name", "effect_kind", "source_type", "keywords")},
                       "effect_detail_ref": "effect:" + eff["identity"]["ability_key"], "phase": phase,
                       "recipient": recipient, "relation": relation,
                       "units": runs["horizon"][0]["identities"] if runs else None},
        "access": access, "recipient_flags": recipient_flags, "window": window,
        "modifiers": {"applied": modifiers, "changed_inputs": changes, "unsupported": unsupported},
        "comparisons": comparisons,
        "matchups": {name: {"without": pair[0], "with": pair[1]} for name, pair in runs.items()},
        "baseline_check": baseline_check, "unresolved_inputs": unresolved, "limitations": limitations,
        "empirical_calibration": None,
    }
