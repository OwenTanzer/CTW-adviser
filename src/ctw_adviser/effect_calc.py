"""Single-cast damage from a specified spell/activated ability against one unit (#20).

Consumes the #19 specialized effect packet and the canonical target unit packet,
and reuses the #5 damage relation. Every rate the source does not supply is an
explicit scenario assumption. This is an expected-value calculation for one
cast, not a battle simulation, spell selection or calibrated forecast.
"""

from __future__ import annotations

import copy
import json
import math

from .combat import _damage_per_hit, _pool
from .model import _number
from .queries import Queries, ResolutionError

MODEL_VERSION = "effect-damage-0.1.0"
MAX_ROUTE_DEPTH = 10
DEFAULTS = {
    "projectile_hit_probability": 0.5,
    "entities_per_explosion": 1.0,
    "vortex_entities_per_application": None,
    "vortex_applications": None,
    "contact_phase_ticks": None,
    "facing": "front",
    "target_component_role": "primary",
    "cast_distance_metres": None,
    "barrier_damage_order": "barrier_first",
    "historical_relations_apply_to_patch_9": True,
}
ASSUMPTION_NOTES = {
    "projectile_hit_probability": "Expected fraction of launched projectiles that strike the target; uncalibrated (combat default 0.5).",
    "entities_per_explosion": "Target entities inside each explosion radius; geometry is not modeled.",
    "vortex_entities_per_application": "Target entities touched per vortex damage application; required for vortex totals.",
    "vortex_applications": "Damage applications per touched entity over the vortex lifetime; required for vortex totals.",
    "contact_phase_ticks": "Contact-phase damage applications per affected entity; required for contact-phase totals.",
    "cast_distance_metres": "Caster-to-target distance used for the range check; omitted means range is not checked.",
}
FAILURE_SUFFIX = ".miscast_explosion"


def _assumption(scenario, key):
    value = scenario[key]
    if key in ("facing", "target_component_role", "barrier_damage_order", "historical_relations_apply_to_patch_9"):
        return value
    if value is None:
        return None
    value = _number(value, key)
    if key == "projectile_hit_probability" and value > 1:
        raise ValueError("projectile_hit_probability must be between 0 and 1")
    return value


def _scenario(value):
    if value is None:
        value = {}
    if not isinstance(value, dict):
        raise ValueError("scenario must be an object")
    unknown = set(value) - set(DEFAULTS)
    if unknown:
        raise ValueError("unsupported scenario field: " + ", ".join(sorted(unknown)))
    scenario = {**DEFAULTS, **json.loads(json.dumps(value, allow_nan=False))}
    if scenario["facing"] not in ("front", "side", "rear"):
        raise ValueError("facing must be front, side or rear")
    if scenario["barrier_damage_order"] != "barrier_first":
        raise ValueError("only barrier_first is represented for single-cast damage")
    if type(scenario["historical_relations_apply_to_patch_9"]) is not bool:
        raise ValueError("historical_relations_apply_to_patch_9 must be boolean")
    for key in DEFAULTS:
        value = _assumption(scenario, key)
        if isinstance(value, float):
            scenario[key] = value  # 1 and 1.0 are one assumption; echo a canonical number
    return scenario


def _traits(params):
    ignition = params.get("ignition_amount")
    return {"magical": bool(params.get("is_magical")),
            "flaming": None if ignition is None else ignition > 0}


def _routes(packet):
    """Root-to-leaf walk over the bounded payload graph with route multiplicity."""
    graph = packet["payload_graph"]
    nodes = {n["id"]: n for n in graph["nodes"]}
    children = {}
    for edge in graph["edges"]:
        if edge["relationship"] != "phase_effect":
            children.setdefault(edge["from"], []).append(edge)
    roots = [(e["relationship"], e["node_ref"]) for e in packet["effect"]["mechanic"]["effects"]
             if e["kind"] == "payload_reference" and e["node_ref"] in nodes]
    events = []

    def walk(node_id, launched, branch, path, via):
        node = nodes[node_id]
        kind, params = node["kind"], node["native_parameters"]
        path = path + [node_id]
        events.append({"node": node, "launched": launched, "branch": branch, "path": path, "via": via})
        if len(path) >= MAX_ROUTE_DEPTH:
            return
        for edge in children.get(node_id, []):
            child = edge["to"]
            if child in path or child not in nodes:
                continue
            factor = 1.0
            if kind == "native_bombardments" and nodes[child]["kind"] == "projectiles":
                factor = params.get("num_projectiles")
            elif kind == "native_projectile_shrapnels" and nodes[child]["kind"] == "projectiles":
                factor = params.get("amount")
            walk(child, None if launched is None or factor is None else launched * factor,
                 branch, path, edge["relationship"])

    for relationship, node_id in roots:
        branch = "conditional_failure" if relationship.endswith(FAILURE_SUFFIX) else "activation"
        walk(node_id, 1.0, branch, [], relationship)
    return events


def _health(unit, role):
    pools, selected, component = _pool(unit, role)
    pool = pools[selected]
    barrier = unit["body"].get("barrier_health") or 0.0
    return pool, component, float(barrier)


def evaluate_effect_damage(queries: Queries, effect: str, target: str, *, scenario: dict | None = None,
                           caster: str | None = None, subculture: str | None = None,
                           target_subculture: str | None = None) -> dict:
    """Expected single-cast damage of one exact effect variant against one unit."""
    cfg = _scenario(scenario)
    resolution = queries.resolve_effect(effect)
    if resolution["status"] != "resolved":
        raise ResolutionError(resolution)
    packet = queries.get_effect(resolution["resolved"]["ability_key"], limit=256, include_diagnostics=True)
    target_packet = queries.get_unit_profile(target, subculture=target_subculture, limit=256, include_diagnostics=True)
    if packet["snapshot"]["commit"] != target_packet["snapshot"]["commit"]:
        raise ValueError("effect and target evidence come from different snapshots")
    unit = target_packet["units"][0]
    baseline = copy.deepcopy(unit)
    eff = packet["effect"]
    identity = eff["identity"]
    unresolved, unsupported, limitations = [], [], []

    def issue(code, detail, calculation, refs=()):
        item = {"code": code, "detail": detail, "calculation": calculation, "provenance_refs": list(refs)}
        if item not in unresolved:
            unresolved.append(item)

    access = {"caster": None, "status": "not_checked"}
    if caster is not None:
        resolved = queries.resolved(caster, subculture)
        keys = set(resolved["source_unit_keys"])
        links = [a for a in queries.rows("effect_access", "ability_key", identity["ability_key"], "unit_key,link_record")
                 if a["unit_key"] in keys]
        access = {"caster": {"unit_key": resolved["unit_key"], "name": resolved["name"]},
                  "status": "linked" if links else "not_established",
                  "links": [{"unit_key": a["unit_key"], "culture_key": a["culture_key"],
                             "requires_effect_enabling": bool(a["requires_effect_enabling"]),
                             "link_record": a["link_record"]} for a in links],
                  "note": "A source link is qualified access, not proof the ability is acquired or active."}
        if not links:
            issue("access_not_established", "No source unit ability link connects this caster to the effect.", "access",
                  identity["provenance_refs"])

    targeting = eff["targeting"]["values"]
    blocked = []
    if not (targeting.get("target_enemies") or targeting.get("target_ground")):
        blocked.append({"code": "ineligible_recipient",
                        "detail": "The effect does not target enemies or ground; an enemy unit is not a selectable recipient."})
    distance = cfg["cast_distance_metres"]
    intercept = eff["distances"]["target_intercept_range"]["value"]
    minimum = eff["distances"]["min_range"]["value"]
    range_check = {"cast_distance_metres": distance, "target_intercept_range": intercept, "min_range": minimum,
                   "status": "not_checked" if distance is None else "within"}
    if distance is not None:
        if intercept is not None and intercept > 0 and distance > intercept:
            range_check["status"] = "beyond_target_intercept_range"
            blocked.append({"code": "out_of_range", "detail": f"{distance:g} m exceeds the {intercept:g} m targeting setting."})
        elif minimum is not None and minimum > 0 and distance < minimum:
            range_check["status"] = "inside_min_range"
            blocked.append({"code": "inside_min_range", "detail": f"{distance:g} m is inside the {minimum:g} m minimum."})
        elif intercept is None or intercept <= 0:
            range_check["status"] = "no_positive_target_range"
            issue("range_setting_unusable", "No positive target_intercept_range; range not established.", "range",
                  eff["targeting"]["provenance_refs"])

    pool, component, barrier = _health(unit, cfg["target_component_role"])
    living = pool["initial_entities"]
    components, conditional = [], []
    hit_p = _assumption(cfg, "projectile_hit_probability")
    for event in _routes(packet):
        node, launched = event["node"], event["launched"]
        kind, params = node["kind"], node["native_parameters"]
        record = {"node_ref": node["id"], "kind": kind.removeprefix("native_"), "key": json.loads(node["key"]),
                  "route": event["via"], "path": event["path"], "provenance_refs": node["provenance_refs"]}
        if kind not in ("projectiles", "explosions", "native_vortices", "native_ability_phases"):
            continue
        if kind == "native_ability_phases":
            amount = params.get("damage_amount")
            if not amount:
                if any(params.get(k) for k in ("heal_amount", "barrier_heal_amount")):
                    unsupported.append({**record, "reason": "Healing phase; not damage to the target."})
                continue
        if event["branch"] == "conditional_failure":
            conditional.append({**record, "reason": "Miscast failure branch; it is not added to target damage.",
                                "miscast_chance": eff["activation"]["values"].get("miscast_chance")})
            continue
        if launched is None:
            issue("route_count_unknown", "A route multiplier (projectile or shrapnel count) is missing.", record["kind"],
                  node["provenance_refs"])
            continue
        if kind == "projectiles":
            base, ap = params.get("base_damage"), params.get("ap_damage")
            if params.get("projectile_number") not in (None, 1):
                limitations.append(f"{record['key']}: projectile_number {params['projectile_number']} is not composed with "
                                   "bombardment counts; one projectile per launch is used.")
            spell = bool(params.get("is_spell"))
            per = None if None in (base, ap) else _damage_per_hit(base, ap, unit, _traits(params), "missile",
                                                                   cfg["facing"], component, spell=spell)
            if per is None:
                issue("damage_input_missing", "Projectile damage or target armour is null.", "projectile", node["provenance_refs"])
                continue
            hits = launched * hit_p * (1 - per["shield_block_probability"])
            components.append({**record, "channel": "direct_projectile", "launched": launched, "expected_hits": hits,
                               "entities_affected": min(hits, living), "per_entity": per,
                               "expected_damage": per["per_unblocked_hit"] * hits,
                               "basis": "launched x projectile_hit_probability x (1 - shield block); one entity per hit"})
        elif kind == "explosions":
            if params.get("affects_enemies") is False:
                continue
            base, ap = params.get("base_damage"), params.get("ap_damage")
            per = None if None in (base, ap) else _damage_per_hit(base, ap, unit, _traits(params), "explosion",
                                                                   cfg["facing"], component, spell=bool(params.get("is_spell")))
            if per is None:
                issue("damage_input_missing", "Explosion damage or target armour is null.", "explosion", node["provenance_refs"])
                continue
            entities = launched * cfg["entities_per_explosion"]
            components.append({**record, "channel": "explosion", "launched": launched,
                               "entities_affected": min(entities, living), "per_entity": per,
                               "expected_damage": per["per_unblocked_hit"] * entities,
                               "basis": "launched x entities_per_explosion; radius geometry not modeled"})
        elif kind == "native_vortices":
            if params.get("affects_enemies") is False:
                continue
            count = params.get("num_vortexes") or 1
            per = None if None in (params.get("damage"), params.get("damage_ap")) else _damage_per_hit(
                params["damage"], params["damage_ap"], unit, _traits(params), "vortex", cfg["facing"], component,
                spell=bool(params.get("is_spell")))
            if per is None:
                issue("damage_input_missing", "Vortex damage or target armour is null.", "vortex", node["provenance_refs"])
                continue
            entry = {**record, "channel": "vortex", "launched": launched * count, "per_entity": per,
                     "per_application_per_entity": per["per_unblocked_hit"],
                     "basis": "num_vortexes x vortex_entities_per_application x vortex_applications"}
            touched, applications = cfg["vortex_entities_per_application"], cfg["vortex_applications"]
            if touched is None or applications is None:
                entry.update(expected_damage=None, entities_affected=None)
                issue("vortex_application_count_required",
                      "Vortex damage cadence and contact count are not source-established; supply "
                      "vortex_entities_per_application and vortex_applications to total this component.",
                      "vortex", node["provenance_refs"])
            else:
                entry.update(entities_affected=min(launched * count * touched, living),
                             expected_damage=per["per_unblocked_hit"] * launched * count * touched * applications)
            components.append(entry)
        else:
            entry = {**record, "channel": "contact_phase", "launched": launched,
                     "per_application_per_entity_raw": params.get("damage_amount"),
                     "max_damaged_entities": params.get("max_damaged_entities"),
                     "basis": "raw damage_amount; armour/resistance application is unresolved",
                     "expected_damage": None, "entities_affected": None}
            if cfg["contact_phase_ticks"] is None:
                issue("contact_phase_ticks_required",
                      "Contact-phase tick count is not source-established; supply contact_phase_ticks.",
                      "contact_phase", node["provenance_refs"])
            else:
                entities = min(launched, living)
                if (params.get("max_damaged_entities") or 0) > 0:
                    entities = min(entities, params["max_damaged_entities"])
                entry.update(entities_affected=entities,
                             expected_damage=params["damage_amount"] * entities * cfg["contact_phase_ticks"])
                limitations.append(f"{record['key']}: contact-phase damage applied raw; protections unverified.")
            components.append(entry)

    for effect in eff["mechanic"]["effects"]:
        if effect["kind"] in ("summon", "healing", "stat_modifier", "attribute_effect"):
            unsupported.append({"kind": effect["kind"], "phase_ref": effect.get("phase_ref"),
                                "reason": "Not target damage; buff/debuff and summon application are separate (#20 later increments).",
                                "provenance_refs": effect["provenance_refs"]})

    if not cfg["historical_relations_apply_to_patch_9"]:
        for c in components:
            c["expected_damage"] = None
        issue("historical_relation_rejected", "Damage relation disabled by scenario.", "damage")
    if blocked:
        for c in components:
            c["expected_damage"] = None

    # A definition reached by several routes within one cast (e.g. projectile and
    # its explosion both naming one shrapnel record) is counted once nominally;
    # the all-routes sum is reported as an upper bound, never silently added.
    first_route = {}
    for c in components:
        key = (c["node_ref"], c["path"][0])
        c["route_role"] = "nominal" if key not in first_route else "alternate_route"
        first_route.setdefault(key, c)
    for c in components:
        if c["route_role"] == "alternate_route":
            issue("shared_definition_multiplicity",
                  f"{c['kind']} {c['node_ref']} is reached by more than one route in one cast; whether each route "
                  "is a separate event is not source-established. Nominal counts it once; totals.upper_all_routes adds every route.",
                  c["kind"], c["provenance_refs"])
    # Descendants of an alternate route are alternates too.
    alternate_paths = [c["path"] for c in components if c["route_role"] == "alternate_route"]
    for c in components:
        if any(c["path"][:len(a)] == a for a in alternate_paths):
            c["route_role"] = "alternate_route"
    known = [c for c in components if c.get("expected_damage") is not None and c["route_role"] == "nominal"]
    upper_all_routes = sum(c["expected_damage"] for c in components if c.get("expected_damage") is not None)
    attempted = sum(c["expected_damage"] for c in known)
    absorbed = min(barrier, attempted)
    to_health = attempted - absorbed
    hp_entity = pool["hp_per_entity"]
    capped, overkill, lethal = 0.0, 0.0, 0.0
    for c in known:
        affected = c.get("entities_affected") or 0
        if affected <= 0 or not c["expected_damage"]:
            continue
        share = c["expected_damage"] / attempted * to_health if attempted else 0.0
        per_entity = share / affected
        if per_entity >= hp_entity:
            capped += hp_entity * affected
            overkill += (per_entity - hp_entity) * affected
            lethal += affected
        else:
            capped += share
    capped = min(capped, pool["initial_hp"])
    expected = min(capped / hp_entity, living)
    casualties = {"lower": min(math.floor(lethal), math.floor(expected)),
                  "expected_pooled": expected,
                  "upper": min(math.ceil(expected - 1e-9), living),
                  "basis": "expected_pooled: capped health damage / health per entity; lower: whole entities from "
                           "hits whose per-entity damage reaches entity health; upper: next whole entity above the "
                           "expectation. Bounds bracket the expectation, not individual hit allocation."}
    if not components and not blocked:
        blocked.append({"code": "no_damage_payload",
                        "detail": "No outward projectile, explosion, vortex or damaging contact phase in the retained "
                                  "activation payload; buffs, healing and summons are listed separately."})
    status = ("blocked" if blocked or not components else
              "partial" if unresolved or any(c.get("expected_damage") is None for c in components) else "calculated")
    if unit != baseline:
        raise AssertionError("target profile mutated during calculation")
    limitations += [
        "Single cast, expected values; no projectile dispersion, penetration, collision physics or AoE geometry.",
        "Phase stat/attribute effects, healing and summons are not applied to the target in this increment.",
        "The 8.1.1-era damage relation is used for the 9.0 baseline as in the #5 model.",
        "Failure branches are reported, not added; their recipients are unverified.",
    ]
    return {
        "model_version": MODEL_VERSION, "source_packet_version": packet["schema_version"],
        "snapshot": {"commit": packet["snapshot"]["commit"], "serving_contract_sha256": queries.snapshot["contract_sha256"]},
        "status": status,
        "identities": {"effect": {k: identity[k] for k in ("ability_key", "name", "effect_kind", "source_type", "keywords")},
                       "effect_detail_ref": "effect:" + identity["ability_key"],
                       "variants": eff["variants"], "target": unit["identity"]},
        "access": access, "range": range_check, "blocked": blocked,
        "source_facts": {"activation": eff["activation"]["values"], "targeting": targeting,
                         "target_protection": unit["passives"]["protection"],
                         "target_health": {"component": component.get("role"), "entities": living,
                                           "hp_per_entity": hp_entity, "health": pool["initial_hp"],
                                           "barrier": barrier}},
        "scenario_assumptions": {k: {"value": cfg[k], "note": ASSUMPTION_NOTES.get(k)} for k in DEFAULTS},
        "derived": {"components": components,
                    "totals": {"attempted_damage": attempted, "barrier_absorbed": absorbed,
                               "health_damage_capped": capped, "overkill": overkill,
                               "fraction_of_health": capped / pool["initial_hp"] if pool["initial_hp"] else None,
                               "casualties": casualties, "upper_all_routes_attempted_damage": upper_all_routes,
                               "complete": status == "calculated"}},
        "conditional_branches": conditional, "unsupported_components": unsupported,
        "unresolved_inputs": unresolved, "limitations": limitations,
        "empirical_calibration": None,
    }
