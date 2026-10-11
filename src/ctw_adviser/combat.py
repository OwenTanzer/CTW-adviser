"""First-order, deterministic two-unit combat projection over a Queries packet.

Every rate not supplied by the packet is an explicit scenario assumption.  This
is an expected-value calculation, not a battle simulation or calibrated forecast.
"""

from __future__ import annotations

import copy
import heapq
import math

from .model import ORDERS, _entry, _number
from .queries import Queries

MODEL_VERSION = "combat-0.1.3"
SIDES = ("a", "b")
FACING = {"front": 1.0, "side": 0.6, "rear": 0.3}


def _fraction(value, name):
    value = _number(value, name)
    if value > 1:
        raise ValueError(f"{name} must be between 0 and 1")
    return value


def _setting(data, key, default, name, *, fraction=False, positive=False):
    value = data.get(key, default)
    return _fraction(value, name) if fraction else _number(value, name, positive=positive)


def _attacks(unit, kind):
    value = unit.get(kind)
    if not isinstance(value, dict) or (kind == "ranged" and value.get("status") != "present"):
        return []
    return [value, *value.get("variants", [])]


def _traits(unit, attack_id):
    traits = unit["passives"]["attack_traits"]
    rows = [traits.get(k) for k in ("melee", "ranged", "explosion")]
    rows += [x["traits"] for x in traits.get("additional", [])]
    return next((x for x in rows if x and x["scope"]["attack_ref"] == attack_id), {})


def _armour_survival(armour):
    """Mean of max(0, 1 - uniform(.5*A, A)/100)."""
    armour = _number(armour, "armour")
    if armour == 0:
        return 1.0
    low, high = armour / 2, armour
    if low >= 100:
        return 0.0
    upper = min(high, 100.0)
    return ((upper - low) - (upper * upper - low * low) / 200) / (high - low)


def _target_class(target, component=None):
    if component is None:
        return target["body"].get("target_classification", {}).get("combat_class")
    return {"small": "infantry", "very_small": "infantry",
            "medium": "large", "large": "large", "very_large": "large"}.get(component.get("size"))


def _damage_per_hit(base, ap, target, traits, kind, facing, target_component=None, *, spell=False):
    base = _number(base, "base_damage")
    ap = _number(ap, "ap_damage")
    classification = _target_class(target, target_component)
    bonus_key = {"infantry": "bonus_vs_infantry", "large": "bonus_vs_large"}.get(classification)
    bonus = _number(traits.get(bonus_key) or 0, "size_bonus") if bonus_key else 0.0
    # The historical relation adds the size bonus to weapon strength. Its split
    # between base and AP is not established, so this conservative model assigns
    # it to base and reports that assumption.
    protection = target["passives"]["protection"]
    armour = protection.get("armour")
    if armour is None:
        return None
    resist = (protection.get("ward_save") or 0)
    if not traits.get("magical"):
        resist += protection.get("physical_resistance") or 0
    if kind == "missile":
        resist += protection.get("missile_resistance") or 0
    if traits.get("flaming"):
        resist += protection.get("fire_resistance") or 0
    if spell:
        resist += protection.get("spell_resistance") or 0
    resist = min(90.0, max(-100.0, resist))
    damage = ((base + bonus) * _armour_survival(armour) + ap) * (1 - resist / 100)
    shield = 0.0
    if kind == "missile" and facing == "front":
        shield = _fraction((protection.get("shield_block_chance") or 0) / 100, "shield_block_chance")
    return {"per_unblocked_hit": damage, "size_bonus_as_base": bonus,
            "armour_survival": _armour_survival(armour), "resistance_points": resist,
            "spell_resistance_applied": bool(spell),
            "shield_block_probability": shield}


def _pool(unit, target_role):
    body = unit["body"]
    components = body.get("components") or []
    if not components:
        components = [{"id": "primary", "role": "primary", "count": body["entity_count"],
                       "known_hp_total": body["total_hp"], "primary": True,
                       "size": body.get("size"), "targetable": True}]
    eligible = [c for c in components if c.get("primary") or c.get("health_contribution", 0)]
    if target_role == "primary":
        selected = next((c for c in eligible if c.get("primary")), None)
    else:
        selected = next((c for c in eligible if c.get("role") == target_role), None)
    if selected is None:
        raise ValueError(f"target component role {target_role!r} is unavailable")
    pools = {}
    for c in eligible:
        hp = c.get("health_contribution", c.get("known_hp_total"))
        count = c.get("count")
        if hp is None or count is None or hp <= 0 or count <= 0:
            raise ValueError("target component health and count must be known")
        pools[c["id"]] = {"role": c["role"], "initial_hp": float(hp), "remaining_hp": float(hp),
                          "initial_entities": float(count), "hp_per_entity": float(hp / count),
                          "primary": bool(c.get("primary"))}
    return pools, selected["id"], selected


def _primary_count(unit):
    pools, _, _ = _pool(unit, "primary")
    return next(p["initial_entities"] for p in pools.values() if p["primary"])


def _issue(side, path, code, calculation):
    return {"side": side, "source_path": path, "code": code, "calculation": calculation}


def _core_unresolved(units, scenario):
    """Health-pool inputs cannot be replaced with invented numeric defaults."""
    issues = []
    for i, unit in enumerate(units):
        side = SIDES[i]
        body = unit["body"]
        components = body.get("components") or []
        if not components:
            for field in ("entity_count", "total_hp"):
                if body.get(field) is None:
                    issues.append(_issue(side, f"body.{field}", "missing_source_value", "health_pool"))
        else:
            eligible = [c for c in components if c.get("primary") or c.get("health_contribution", 0)]
            target_role = scenario["sides"][side]["target_component_role"]
            if target_role != "primary":
                selected = next((c for c in components if c.get("role") == target_role), None)
                if selected and selected not in eligible:
                    issues.append(_issue(side, f"body.components.{target_role}.health_contribution",
                                         "missing_source_value", "health_pool"))
            if not any(c.get("primary") for c in eligible):
                issues.append(_issue(side, "body.components.primary", "missing_source_value", "health_pool"))
            for component in eligible:
                for field, value in (("count", component.get("count")),
                                     ("health_contribution", component.get(
                                         "health_contribution", component.get("known_hp_total")))):
                    if value is None or value <= 0:
                        issues.append(_issue(side, f"body.components.{component['role']}.{field}",
                                             "missing_or_invalid_source_value", "health_pool"))
    return issues


def _scenario(value):
    if value is None:
        value = {}
    if not isinstance(value, dict):
        raise ValueError("scenario must be an object")
    allowed = {"mode", "baseline", "separation_metres", "duration_seconds", "metres_per_second_per_speed_point",
               "path_length_factor", "terrain_speed_factor", "line_of_sight", "sides",
               "historical_relations_apply_to_patch_9", "barrier_damage_order"}
    if set(value) - allowed:
        raise ValueError("unsupported scenario fields: " + ", ".join(sorted(set(value) - allowed)))
    sides = value.get("sides", {})
    if not isinstance(sides, dict) or set(sides) - set(SIDES):
        raise ValueError("sides must contain only a and b objects")
    normalized = {
        "mode": value.get("mode", "custom_battle"),
        "baseline": value.get("baseline", "unmodified_ultra_rank_0"),
        "separation_metres": _setting(value, "separation_metres", 200, "separation_metres"),
        "duration_seconds": _setting(value, "duration_seconds", 120, "duration_seconds", positive=True),
        "metres_per_second_per_speed_point": _setting(value, "metres_per_second_per_speed_point", 1, "speed_scale", positive=True),
        "path_length_factor": _setting(value, "path_length_factor", 1, "path_length_factor", positive=True),
        "terrain_speed_factor": _setting(value, "terrain_speed_factor", 1, "terrain_speed_factor", positive=True),
        "line_of_sight": value.get("line_of_sight", True),
        "historical_relations_apply_to_patch_9": value.get("historical_relations_apply_to_patch_9", True),
        "barrier_damage_order": value.get("barrier_damage_order", "barrier_first"),
        "barrier_damage_order_explicit": "barrier_damage_order" in value,
        "sides": {},
    }
    if normalized["mode"] != "custom_battle" or normalized["baseline"] != "unmodified_ultra_rank_0":
        raise ValueError("only the pinned unmodified custom-battle baseline is supported")
    for key in ("line_of_sight", "historical_relations_apply_to_patch_9"):
        if type(normalized[key]) is not bool:
            raise ValueError(f"{key} must be boolean")
    if normalized["barrier_damage_order"] not in ("barrier_first", "entity_cap_first"):
        raise ValueError("barrier_damage_order must be barrier_first or entity_cap_first")
    allowed_side = {"order", "fire", "fight", "facing", "ranged_attack_id", "collision_probability", "firing_entities",
                    "cycle_seconds", "first_shot_delay_seconds", "projectiles_per_cycle", "explosion_entities_per_collision",
                    "active_contacts", "charge_duration_seconds", "target_component_role", "combat_effective_fraction",
                    "flight_seconds", "assume_targetable", "assume_unit_protection_for_component"}
    for side in SIDES:
        user = sides.get(side, {})
        if not isinstance(user, dict) or set(user) - allowed_side:
            raise ValueError(f"unsupported {side} side settings")
        order = user.get("order", "approach")
        facing = user.get("facing", "front")
        if order not in ORDERS or facing not in FACING:
            raise ValueError("order or facing is unsupported")
        if type(user.get("fire", True)) is not bool or type(user.get("fight", True)) is not bool:
            raise ValueError("fire and fight must be boolean")
        for name in ("assume_targetable", "assume_unit_protection_for_component"):
            if type(user.get(name, False)) is not bool:
                raise ValueError(f"{name} must be boolean")
        normalized["sides"][side] = {
            "order": order, "fire": user.get("fire", True), "fight": user.get("fight", True), "facing": facing,
            "ranged_attack_id": user.get("ranged_attack_id"),
            "collision_probability": _setting(user, "collision_probability", .5, f"{side}.collision_probability", fraction=True),
            "firing_entities": None if user.get("firing_entities") is None else _setting(user, "firing_entities", 1, f"{side}.firing_entities"),
            "cycle_seconds": None if user.get("cycle_seconds") is None else _setting(user, "cycle_seconds", 1, f"{side}.cycle_seconds", positive=True),
            "first_shot_delay_seconds": _setting(user, "first_shot_delay_seconds", 1, f"{side}.first_shot_delay_seconds"),
            "projectiles_per_cycle": None if user.get("projectiles_per_cycle") is None else _setting(user, "projectiles_per_cycle", 1, f"{side}.projectiles_per_cycle", positive=True),
            "flight_seconds": None if user.get("flight_seconds") is None else _setting(user, "flight_seconds", 0, f"{side}.flight_seconds"),
            "explosion_entities_per_collision": _setting(user, "explosion_entities_per_collision", 1, f"{side}.explosion_entities_per_collision"),
            "active_contacts": None if user.get("active_contacts") is None else _setting(user, "active_contacts", 1, f"{side}.active_contacts"),
            "charge_duration_seconds": _setting(user, "charge_duration_seconds", 0, f"{side}.charge_duration_seconds"),
            "target_component_role": user.get("target_component_role", "primary"),
            "assume_targetable": user.get("assume_targetable", False),
            "assume_unit_protection_for_component": user.get("assume_unit_protection_for_component", False),
            "combat_effective_fraction": _setting(user, "combat_effective_fraction", .5, f"{side}.combat_effective_fraction", fraction=True),
        }
    return normalized


def _validate_source(packet, scenario):
    snapshot = packet["snapshot"]
    if snapshot["commit"] != "595e22764b22e748afdbafafcb0a6258973e2451":
        raise ValueError("unsupported CTW-data commit")
    base = snapshot["baseline"]
    if base.get("unit_scale") != "ultra" or base.get("rank") != 0:
        raise ValueError("snapshot scale or rank does not match the model baseline")
    owners = snapshot.get("owners", {})
    patches = {str(owner.get("patch")) for owner in owners.values()}
    if not patches <= {"9.0", "9.0.1"} or "9.0" not in patches:
        raise ValueError("snapshot owner patches are incompatible")


def _prepare(unit, side, setting):
    pools, target, target_source = _pool(unit, setting["target_component_role"])
    primary = next(p for p in pools.values() if p["primary"])
    ranged = _attacks(unit, "ranged")
    selected = ([x for x in ranged if x["id"] == setting["ranged_attack_id"]]
                if setting["ranged_attack_id"] else
                [x for x in ranged if x.get("is_default") and x.get("slot") == "primary"] or
                [x for x in ranged if x.get("is_default")])
    if setting["ranged_attack_id"] and len(selected) != 1:
        raise ValueError(f"{side}: ranged_attack_id does not resolve to one attached attack")
    attack = selected[0] if selected else None
    melee = _attacks(unit, "melee")
    m = melee[0] if melee else None
    gaps = []
    target_supported = True
    if target_source.get("targetable") is False:
        gaps.append("selected target component is marked untargetable; damage omitted")
        target_supported = False
    elif target_source.get("targetable") is not True and not setting["assume_targetable"]:
        gaps.append("selected target component has unknown targetability; damage omitted unless assumed targetable")
        target_supported = False
    if not target_source.get("primary") and not setting["assume_unit_protection_for_component"]:
        gaps.append("nonprimary component has no verified armour/resistance profile; damage omitted unless unit protection is assumed")
        target_supported = False
    elif not target_source.get("primary"):
        gaps.append("nonprimary component uses unit-card protection and melee defence by explicit scenario assumption")
    if target_source.get("size") not in ("very_small", "small", "medium", "large", "very_large"):
        gaps.append("selected target component size is unresolved; damage omitted")
        target_supported = False
    weapon_state = next((x["state"] for x in unit["coverage"]["sections"] if x["name"] == "weapons"), "unresolved")
    if weapon_state != "complete":
        gaps.append("weapon section is " + weapon_state + "; selected attacks may omit alternatives")
    if unit["coverage"].get("melee") == "unresolved" or unit["coverage"].get("ranged") == "unresolved":
        gaps.append("one or more attack capabilities are unresolved")
    if len(ranged) > 1:
        gaps.append("multiple ranged attachments or variants exist; only one selected attack is evaluated, with simultaneous firing unresolved")
    if len(melee) > 1:
        gaps.append("multiple melee attachments exist; only the primary attack is evaluated")
    if m and (any(m.get(field) is None for field in ("attack", "base_damage", "ap_damage", "attack_interval"))
              or m["attack_interval"] <= 0):
        gaps.append("primary melee attack has missing calculation fields; melee damage omitted")
        m = None
    if m and (m.get("max_splash_targets") or 1) > 1:
        gaps.append("melee splash target selection and damage distribution are not modeled as extra damage")
    if m and m.get("native_parameters", {}).get("collision_attack_max_targets"):
        gaps.append("collision attacks have separate timing and are not included")
    if attack:
        if any(attack.get(field) is None for field in ("range", "base_damage", "ap_damage")):
            gaps.append("selected ranged attack has missing range or damage; shots omitted")
            attack = None
        elif setting["fire"] and setting["flight_seconds"] is None and (attack.get("velocity") is None or attack["velocity"] <= 0):
            gaps.append("projectile velocity is missing or nonpositive; firing opportunities use an immediate-arrival approximation")
    if attack:
        counts = [attack.get(k) for k in ("projectiles_per_shot", "shots_per_volley", "burst_size")]
        if setting["projectiles_per_cycle"] is None and any(x != 1 for x in counts):
            gaps.append("projectile/volley/burst nesting unresolved or count missing; set projectiles_per_cycle")
            attack = None
        elif setting["projectiles_per_cycle"] is None:
            setting["projectiles_per_cycle"] = 1.0
        if attack and setting["cycle_seconds"] is None and (attack.get("reload_time") or 0) > 0:
            setting["cycle_seconds"] = 1.25 * _number(attack["reload_time"], "reload_time", positive=True)
            gaps.append("complete firing cycle assumes 1.25 times listed projectile reload; uncalibrated")
        supply = attack.get("ammunition_supply") if attack else None
        if supply and (supply.get("assignment_status") != "sources_agree" or supply.get("unlimited")):
            gaps.append("ammunition pool or finite exhaustion unresolved")
    return {"unit": unit, "pools": pools, "target": target, "target_source": target_source,
            "target_supported": target_supported, "primary": primary,
            "initial_barrier": _number(unit["body"].get("barrier_health") or 0, "barrier_health"),
            "remaining_barrier": _number(unit["body"].get("barrier_health") or 0, "barrier_health"),
            "ranged": attack, "melee": m, "gaps": gaps, "shot_events": 0,
            "next_shot": None, "shots_fired": 0, "ledger": {"direct": 0.0, "explosion": 0.0, "melee": 0.0,
                                                    "overkill": 0.0, "attempted_damage": 0.0},
            "stops": {"health_depleted_seconds": None, "combat_ineffective_seconds": None,
                      "firing_ceased_seconds": None}}


def _ammo_limit(attack):
    supply = attack.get("ammunition_supply") or {}
    if supply.get("unlimited") is True:
        return math.inf
    return supply.get("capacity", attack.get("ammunition"))


def _living(pool):
    return min(pool["initial_entities"], math.ceil(max(0, pool["remaining_hp"]) / pool["hp_per_entity"]))


def _apply(state, channel, attempts, damage, barrier_order):
    if attempts <= 0 or damage is None:
        return
    pool = state["pools"][state["target"]]
    nominal = attempts * damage
    state["ledger"]["attempted_damage"] += nominal
    if barrier_order == "barrier_first":
        absorbed = min(state["remaining_barrier"], nominal)
        # Spread barrier absorption over expected hits before the per-entity
        # health cap. This is an explicit scenario ordering, not a game claim.
        unabsorbed = nominal - absorbed
        capped = min(unabsorbed, attempts * pool["hp_per_entity"])
        state["ledger"]["overkill"] += unabsorbed - capped
    else:
        capped = attempts * min(damage, pool["hp_per_entity"])
        state["ledger"]["overkill"] += nominal - capped
        absorbed = min(state["remaining_barrier"], capped)
        capped -= absorbed
    state["remaining_barrier"] -= absorbed
    state["ledger"].setdefault("barrier_absorbed", 0.0)
    state["ledger"]["barrier_absorbed"] += absorbed
    actual = min(pool["remaining_hp"], capped)
    pool["remaining_hp"] -= actual
    state["ledger"][channel] += actual


def _score(states):
    return [(sum(p["remaining_hp"] for p in s["pools"].values()) + s["remaining_barrier"]) /
            (sum(p["initial_hp"] for p in s["pools"].values()) + s["initial_barrier"]) for s in states]


def _run(states, scenario, timing):
    """Advance impacts, shots and contact in time order; integrate melee between events."""
    duration = scenario["duration_seconds"]
    contact = timing["contact"]["seconds"]
    closing = timing["closing_speed_metres_per_second"] or 0.0
    separation = scenario["separation_metres"]
    queue = []
    epsilon = 1e-9

    def distance_at(t):
        return max(0.0, separation - closing * t)

    def update_stops(t):
        for i, state in enumerate(states):
            cfg = scenario["sides"][SIDES[i]]
            pools = state["pools"]
            if sum(p["remaining_hp"] for p in pools.values()) <= 0 and state["stops"]["health_depleted_seconds"] is None:
                state["stops"]["health_depleted_seconds"] = t
            if (_living(state["primary"]) / state["primary"]["initial_entities"] <= cfg["combat_effective_fraction"]
                    and state["stops"]["combat_ineffective_seconds"] is None):
                state["stops"]["combat_ineffective_seconds"] = t
            attack = state["ranged"]
            if attack and state["stops"]["firing_ceased_seconds"] is None:
                firing_component = pools.get(attack.get("component_ref"), state["primary"])
                ammo = _ammo_limit(attack)
                if (_living(firing_component) == 0 or (ammo is not None and state["shots_fired"] >= ammo)
                        or (contact is not None and t >= contact)):
                    state["stops"]["firing_ceased_seconds"] = t

    def melee_between(start, end):
        if contact is None or end <= contact or end <= start:
            return
        start = max(start, contact)
        events = []
        for i, attacker in enumerate(states):
            cfg = scenario["sides"][SIDES[i]]
            defender = states[1 - i]
            attack = attacker["melee"]
            if not cfg["fight"] or not attack or not defender["target_supported"] or not _living(attacker["primary"]):
                continue
            contacts = cfg["active_contacts"]
            if contacts is None:
                contacts = min(8, attacker["primary"]["initial_entities"])
            contacts = min(contacts, _living(attacker["primary"]))
            traits = _traits(attacker["unit"], attack["id"])
            classification = _target_class(defender["unit"], defender["target_source"])
            bonus_field = {"infantry": "bonus_vs_infantry", "large": "bonus_vs_large"}.get(classification)
            bonus = traits.get(bonus_field, 0) or 0
            facing = scenario["sides"][SIDES[1 - i]]["facing"]
            defence = (defender["melee"] or {}).get("defence") or 0
            decay = cfg["charge_duration_seconds"]
            split = contact + decay if decay else None
            boundaries = [start, end]
            if split is not None and start < split < end:
                boundaries.insert(1, split)
            for left, right in zip(boundaries, boundaries[1:]):
                midpoint = (left + right) / 2
                elapsed = max(0.0, midpoint - contact)
                charge_fraction = min(1.0, max(0.0, 1 - elapsed / decay)) if decay else 0.0
                charge = (attack.get("charge_bonus") or 0) * charge_fraction
                hit = min(.90, max(.08, .35 + ((attack["attack"] + bonus + charge -
                                             defence * FACING[facing]) / 100)))
                damage = _damage_per_hit(attack["base_damage"] + charge, attack["ap_damage"],
                                         defender["unit"], traits, "melee", facing, defender["target_source"])
                if damage and attack.get("attack_interval"):
                    events.append((1 - i, contacts * (right - left) / attack["attack_interval"] * hit,
                                   damage["per_unblocked_hit"]))
        # Both directions use the same pre-segment living counts.
        for target, hits, damage in events:
            _apply(states[target], "melee", hits, damage, scenario["barrier_damage_order"])

    def impacts_due(t):
        while queue and queue[0][0] <= t + epsilon:
            _, i, projectiles = heapq.heappop(queue)
            attacker, defender = states[i], states[1 - i]
            if not defender["target_supported"]:
                continue
            attack = attacker["ranged"]
            cfg = scenario["sides"][SIDES[i]]
            facing = scenario["sides"][SIDES[1 - i]]["facing"]
            traits = _traits(attacker["unit"], attack["id"])
            direct = _damage_per_hit(attack["base_damage"], attack["ap_damage"], defender["unit"],
                                     traits, "missile", facing, defender["target_source"])
            if direct:
                hits = projectiles * cfg["collision_probability"] * (1 - direct["shield_block_probability"])
                _apply(defender, "direct", hits, direct["per_unblocked_hit"], scenario["barrier_damage_order"])
            explosion = attack.get("explosion")
            if explosion and explosion.get("base_damage") is not None and explosion.get("ap_damage") is not None:
                ex = _damage_per_hit(explosion["base_damage"], explosion["ap_damage"], defender["unit"],
                                      _traits(attacker["unit"], explosion["id"]), "explosion", facing,
                                      defender["target_source"],
                                      spell=explosion.get("native_parameters", {}).get("is_spell") is True)
                if ex:
                    _apply(defender, "explosion", projectiles * cfg["collision_probability"] *
                           cfg["explosion_entities_per_collision"], ex["per_unblocked_hit"],
                           scenario["barrier_damage_order"])
            update_stops(t)

    def shots_due(t):
        if t >= duration - epsilon:
            return
        for i, state in enumerate(states):
            attack = state["ranged"]
            due = state["next_shot"]
            if attack is None or due is None or due > t + epsilon:
                continue
            cfg = scenario["sides"][SIDES[i]]
            ammo = _ammo_limit(attack)
            cycle = cfg["cycle_seconds"]
            if not cfg["fire"] or not scenario["line_of_sight"] or cycle is None or ammo is None:
                state["next_shot"] = None
                continue
            if (contact is not None and due >= contact - epsilon) or state["shots_fired"] >= ammo:
                state["next_shot"] = None
                continue
            distance = distance_at(due)
            component = state["pools"].get(attack.get("component_ref"), state["primary"])
            shooters = cfg["firing_entities"] if cfg["firing_entities"] is not None else component["initial_entities"]
            shooters = min(shooters, _living(component))
            if shooters > 0 and (attack.get("minimum_range") or 0) <= distance <= attack["range"]:
                flight = (cfg["flight_seconds"] if cfg["flight_seconds"] is not None else
                          distance / attack["velocity"] if (attack.get("velocity") or 0) > 0 else 0)
                heapq.heappush(queue, (due + flight, i, shooters * cfg["projectiles_per_cycle"]))
                state["shot_events"] += 1
                state["shots_fired"] += 1
            state["next_shot"] = due + cycle if shooters > 0 and state["shots_fired"] < ammo else None
        update_stops(t)

    for i, state in enumerate(states):
        attack = state["ranged"]
        cfg = scenario["sides"][SIDES[i]]
        entry = timing["range_entry"][i]["seconds"]
        if attack and cfg["fire"] and cfg["cycle_seconds"] is not None and entry is not None:
            state["next_shot"] = entry + cfg["first_shot_delay_seconds"]
    t = 0.0
    update_stops(t)
    shots_due(t)
    impacts_due(t)
    while t < duration - epsilon:
        candidates = [duration, math.floor(t + epsilon) + 1.0]
        if contact is not None and contact > t + epsilon:
            candidates.append(contact)
        if queue:
            candidates.append(queue[0][0])
        candidates += [state["next_shot"] for state in states
                       if state["next_shot"] is not None and state["next_shot"] > t + epsilon]
        next_t = min(x for x in candidates if x > t + epsilon)
        melee_between(t, next_t)
        t = next_t
        update_stops(t)
        # Arrivals at a timestamp precede any new shot. Simultaneous new shots
        # are scheduled together before zero-flight impacts are applied.
        impacts_due(t)
        shots_due(t)
        impacts_due(t)
    return states

def _timing(states, scenario):
    speed = [s["unit"]["movement"].get("speed") for s in states]
    order = [ORDERS[scenario["sides"][SIDES[i]]["order"]] for i in range(2)]
    closing = (None if any(speed[i] is None and order[i] != 0 for i in range(2)) else
               sum(order[i] * (speed[i] if speed[i] is not None else 0) for i in range(2)) *
               scenario["metres_per_second_per_speed_point"] * scenario["terrain_speed_factor"] /
               scenario["path_length_factor"])
    distance = scenario["separation_metres"]
    def entry(threshold):
        return {"status": "unknown_input", "seconds": None} if closing is None or threshold is None else _entry(distance, threshold, closing)
    return {"closing_speed_metres_per_second": closing, "contact": entry(0),
            "range_entry": [entry(s["ranged"].get("range") if s["ranged"] else None) for s in states],
            "minimum_range": [s["ranged"].get("minimum_range") if s["ranged"] else None for s in states],
            "flight_speed": [s["ranged"].get("velocity") if s["ranged"] else None for s in states]}


def _unresolved_inputs(units, scenario, timing):
    """Record nullable source inputs used by enabled calculation paths.

    Null is unknown, while numeric zero, false, known omission and disabled
    channels retain their distinct meanings. These records, not prose gaps,
    determine whether a projected ordering can be reported as a verdict.
    """
    issues = []
    if not scenario["historical_relations_apply_to_patch_9"]:
        return issues
    seen = set()

    def add(i, path, code, calculation):
        key = (i, path, code, calculation)
        if key not in seen:
            seen.add(key)
            issues.append(_issue(SIDES[i], path, code, calculation))

    def require(i, path, value, calculation):
        if value is None:
            add(i, path, "missing_source_value", calculation)

    contact = timing["contact"]["seconds"]
    moving = scenario["separation_metres"] > 0 and any(
        ORDERS[scenario["sides"][side]["order"]] != 0 for side in SIDES)
    possible_contact = (contact is not None and contact < scenario["duration_seconds"] or
                        contact is None and moving)
    ranged = []
    melee = []
    fires = []
    fights = []
    for i, unit in enumerate(units):
        cfg = scenario["sides"][SIDES[i]]
        options = _attacks(unit, "ranged")
        requested = cfg["ranged_attack_id"]
        selected = (next((a for a in options if a["id"] == requested), None) if requested else
                    next((a for a in options if a.get("is_default") and a.get("slot") == "primary"), None) or
                    next((a for a in options if a.get("is_default")), None))
        attack = _attacks(unit, "melee")
        ranged.append(selected)
        melee.append(attack[0] if attack else None)
        can_fire = bool(cfg["fire"] and scenario["line_of_sight"] and
                        scenario["separation_metres"] > 0 and
                        (contact is None or contact > cfg["first_shot_delay_seconds"]) and
                        cfg["first_shot_delay_seconds"] < scenario["duration_seconds"])
        fires.append(can_fire)
        fights.append(bool(cfg["fight"] and possible_contact))
        if can_fire and (unit.get("ranged") or {}).get("status") == "unresolved":
            add(i, "ranged.status", "unresolved_source_status", "ranged")
        if can_fire and (unit.get("ranged") or {}).get("status") == "present" and selected is None:
            add(i, "ranged.is_default", "unresolved_source_selection", "ranged")
        if fights[i] and melee[i] is None and unit["coverage"].get("melee") == "unresolved":
            add(i, "melee", "unresolved_source_status", "melee")

    if moving and (any(fires) or any(fights)):
        for i, unit in enumerate(units):
            if (ORDERS[scenario["sides"][SIDES[i]]["order"]] != 0 and
                    unit["movement"].get("speed") is None):
                add(i, "movement.speed", "missing_source_value", "phase_timing")

    for i, attack in enumerate(ranged):
        if not fires[i] or attack is None:
            continue
        cfg = scenario["sides"][SIDES[i]]
        for field in ("range", "minimum_range", "base_damage", "ap_damage"):
            require(i, f"ranged.{field}", attack.get(field), "ranged")
        for field in ("range", "minimum_range"):
            if attack.get(field) is not None and attack[field] < 0:
                add(i, f"ranged.{field}", "invalid_native_value", "ranged")
        if cfg["cycle_seconds"] is None and (attack.get("reload_time") is None or attack["reload_time"] <= 0):
            add(i, "ranged.reload_time", "missing_cycle_assumption", "ranged_schedule")
        if cfg["projectiles_per_cycle"] is None:
            counts = [attack.get(field) for field in ("projectiles_per_shot", "shots_per_volley", "burst_size")]
            if any(count is None for count in counts):
                for field in ("projectiles_per_shot", "shots_per_volley", "burst_size"):
                    require(i, f"ranged.{field}", attack.get(field), "ranged_schedule")
            elif any(count != 1 for count in counts):
                add(i, "ranged.projectile_volley_burst", "requires_scenario_assumption", "ranged_schedule")
        supply = attack.get("ammunition_supply")
        if supply is None:
            require(i, "ranged.ammunition", attack.get("ammunition"), "ranged_schedule")
            if attack.get("ammunition") is not None and attack["ammunition"] < 0:
                add(i, "ranged.ammunition", "invalid_native_value", "ranged_schedule")
        else:
            if supply.get("assignment_status") != "sources_agree":
                add(i, "ranged.ammunition_supply.assignment_status", "unresolved_source_status", "ranged_schedule")
            if supply.get("unlimited") is None:
                add(i, "ranged.ammunition_supply.unlimited", "missing_source_value", "ranged_schedule")
            elif supply["unlimited"] is False:
                require(i, "ranged.ammunition_supply.capacity", supply.get("capacity"), "ranged_schedule")
                if supply.get("capacity") is not None and supply["capacity"] < 0:
                    add(i, "ranged.ammunition_supply.capacity", "invalid_native_value", "ranged_schedule")
        explosion = attack.get("explosion")
        if explosion:
            for field in ("base_damage", "ap_damage"):
                require(i, f"ranged.explosion.{field}", explosion.get(field), "explosion")

    for i, attack in enumerate(melee):
        if not fights[i] or attack is None:
            continue
        for field in ("attack", "base_damage", "ap_damage", "attack_interval"):
            require(i, f"melee.{field}", attack.get(field), "melee")
        if attack.get("attack_interval") is not None and attack["attack_interval"] <= 0:
            add(i, "melee.attack_interval", "invalid_native_value", "melee")
        if scenario["sides"][SIDES[i]]["charge_duration_seconds"] > 0:
            require(i, "melee.charge_bonus", attack.get("charge_bonus"), "charge")
        defence = melee[1 - i]
        require(1 - i, "melee.defence", defence.get("defence") if defence else None, "melee_defence")

    def defence_inputs(attacker_i, kind, attack, traits, *, spell_tag=None):
        defender_i = 1 - attacker_i
        defender = units[defender_i]
        cfg = scenario["sides"][SIDES[defender_i]]
        trait_path = {"missile": "ranged", "explosion": "explosion", "melee": "melee"}[kind]
        if not traits:
            add(attacker_i, f"passives.attack_traits.{trait_path}",
                "missing_source_value", "damage_traits")
        components = defender["body"].get("components") or []
        component = (next((c for c in components if c.get("role") == cfg["target_component_role"]), None)
                     if cfg["target_component_role"] != "primary" else
                     next((c for c in components if c.get("primary")), None))
        if component and component.get("targetable") is False:
            return
        if component and component.get("targetable") is None and not cfg["assume_targetable"]:
            add(defender_i, f"body.components.{component['role']}.targetable",
                "missing_source_value", "target_eligibility")
        if component and not component.get("primary") and not cfg["assume_unit_protection_for_component"]:
            add(defender_i, f"body.components.{component['role']}.protection",
                "requires_scenario_assumption", "defence")
        size = component.get("size") if component else defender["body"].get("size")
        require(defender_i, "body.target_component.size", size, "size_bonus")
        protection = defender["passives"]["protection"]
        for field in ("armour", "ward_save", "barrier_health"):
            value = defender["body"].get(field) if field == "barrier_health" else protection.get(field)
            require(defender_i, f"body.{field}" if field == "barrier_health" else f"passives.protection.{field}",
                    value, "defence")
        magical = traits.get("magical")
        if magical is None and protection.get("physical_resistance") != 0:
            add(attacker_i, f"passives.attack_traits.{trait_path}.magical",
                "missing_source_value", "resistance")
        if magical is not True:
            require(defender_i, "passives.protection.physical_resistance",
                    protection.get("physical_resistance"), "resistance")
        if kind == "missile":
            require(defender_i, "passives.protection.missile_resistance",
                    protection.get("missile_resistance"), "resistance")
            if cfg["facing"] == "front":
                require(defender_i, "passives.protection.shield_block_chance",
                        protection.get("shield_block_chance"), "shield")
        flaming = traits.get("flaming")
        if flaming is None and protection.get("fire_resistance") != 0:
            add(attacker_i, f"passives.attack_traits.{trait_path}.flaming",
                "missing_source_value", "resistance")
        if flaming is True:
            require(defender_i, "passives.protection.fire_resistance",
                    protection.get("fire_resistance"), "resistance")
        if spell_tag is None and kind == "explosion" and protection.get("spell_resistance") != 0:
            add(attacker_i, "ranged.explosion.native_parameters.is_spell",
                "missing_source_value", "spell_resistance")
        if spell_tag is True:
            require(defender_i, "passives.protection.spell_resistance",
                    protection.get("spell_resistance"), "spell_resistance")
        classification = _target_class(defender, component)
        bonus_field = {"infantry": "bonus_vs_infantry", "large": "bonus_vs_large"}.get(classification)
        if bonus_field and kind != "explosion":
            require(attacker_i, f"passives.attack_traits.{trait_path}.{bonus_field}",
                    traits.get(bonus_field), "size_bonus")

    for i in range(2):
        if fires[i] and ranged[i]:
            attack = ranged[i]
            defence_inputs(i, "missile", attack, _traits(units[i], attack["id"]))
            if attack.get("explosion"):
                ex = attack["explosion"]
                defence_inputs(i, "explosion", ex, _traits(units[i], ex["id"]),
                               spell_tag=ex.get("native_parameters", {}).get("is_spell"))
        if fights[i] and melee[i]:
            defence_inputs(i, "melee", melee[i], _traits(units[i], melee[i]["id"]))
    return issues


def _summary(states, scenario):
    out = []
    for i, state in enumerate(states):
        pools = state["pools"]
        total = sum(p["initial_hp"] for p in pools.values())
        remaining = sum(p["remaining_hp"] for p in pools.values())
        attack = state["ranged"]
        out.append({"unit_key": state["unit"]["identity"]["unit_key"], "incoming_damage": state["ledger"],
                    "remaining_health": remaining, "initial_health": total,
                    "remaining_health_fraction": remaining / total,
                    "remaining_barrier": state["remaining_barrier"], "initial_barrier": state["initial_barrier"],
                    "effective_survivability_fraction": (remaining + state["remaining_barrier"]) /
                                                        (total + state["initial_barrier"]),
                    "components": [{"role": p["role"], "primary": p["primary"], "remaining_health": p["remaining_hp"],
                                    "initial_health": p["initial_hp"], "estimated_living_entities": _living(p),
                                    "initial_entities": p["initial_entities"]} for p in pools.values()],
                    "shots_fired_per_shooter": state["shots_fired"], "discrete_firing_events": state["shot_events"],
                    "stopping": {**state["stops"], "contact_seconds": None,
                                 "routing": ("not_applicable_daemonic_attribute_instability_unmodeled" if any(
                                     a.get("key") == "daemonic" for a in state["unit"]["passives"].get("attributes", []))
                                             else "unknown_no_morale_model"),
                                 "firing_cessation_basis": "ammo, firing-component depletion or modeled contact policy",
                                 "engine_disabled": "unknown_no_component_disable_rule" if len(pools) > 1 else "not_applicable",
                                 "crew_firing_cessation": "unknown_no_crew_threshold" if len(pools) > 1 else "not_applicable",
                                 "ammunition_exhausted": bool(attack and _ammo_limit(attack) is not None and
                                                               state["shots_fired"] >= _ammo_limit(attack))},
                    "coverage_gaps": state["gaps"]})
    return out


def _mechanics(units, scenario):
    """Expose per-event assumptions separately from aggregate ledgers."""
    result = []
    for i, attacker in enumerate(units):
        defender = units[1 - i]
        cfg = scenario["sides"][SIDES[i]]
        target_cfg = scenario["sides"][SIDES[1 - i]]
        facing = target_cfg["facing"]
        _, _, component = _pool(defender, target_cfg["target_component_role"])
        target_supported = (component.get("targetable") is True or
                            (component.get("targetable") is None and target_cfg["assume_targetable"]))
        target_supported = (target_supported and component.get("size") in
                            ("very_small", "small", "medium", "large", "very_large") and
                            (component.get("primary") or target_cfg["assume_unit_protection_for_component"]))
        ranged = _attacks(attacker, "ranged")
        requested = cfg["ranged_attack_id"]
        selected = (next((a for a in ranged if a["id"] == requested), None) if requested else
                    next((a for a in ranged if a.get("is_default") and a.get("slot") == "primary"), None) or
                    next((a for a in ranged if a.get("is_default")), None))
        missile = None
        if selected:
            traits = _traits(attacker, selected["id"])
            if selected.get("base_damage") is not None and selected.get("ap_damage") is not None:
                missile = {"attack_id": selected["id"], "collision_probability": cfg["collision_probability"],
                           "complete_cycle_seconds_assumed": cfg["cycle_seconds"],
                           "projectiles_per_cycle_assumed": cfg["projectiles_per_cycle"],
                           "scheduled": bool(cfg["fire"] and cfg["cycle_seconds"] is not None),
                           "flight_basis": ("scenario_flight_seconds" if cfg["flight_seconds"] is not None else
                                            "source_velocity" if (selected.get("velocity") or 0) > 0 else
                                            "firing_opportunity_immediate_arrival"),
                           "direct": _damage_per_hit(selected["base_damage"], selected["ap_damage"],
                                                     defender, traits, "missile", facing, component) if target_supported else None,
                           "explosion": None}
                ex = selected.get("explosion")
                if ex and ex.get("base_damage") is not None and ex.get("ap_damage") is not None:
                    missile["explosion"] = {"radius_source_metres": ex.get("radius"),
                                            "affected_entities_assumed": cfg["explosion_entities_per_collision"],
                                            "damage": _damage_per_hit(ex["base_damage"], ex["ap_damage"], defender,
                                                                      _traits(attacker, ex["id"]), "explosion", facing,
                                                                      component, spell=ex.get("native_parameters", {}).get("is_spell") is True)
                                            if target_supported else None}
        melee = None
        attack = _attacks(attacker, "melee")
        defending_attack = _attacks(defender, "melee")
        if attack and defending_attack:
            a = attack[0]
            classification = _target_class(defender, component)
            bonus_field = {"infantry": "bonus_vs_infantry", "large": "bonus_vs_large"}.get(classification)
            bonus = (_traits(attacker, a["id"]).get(bonus_field) or 0) if bonus_field else 0
            hit = min(.90, max(.08, .35 + ((a.get("attack") or 0) + bonus -
                                         (defending_attack[0].get("defence") or 0) * FACING[facing]) / 100))
            melee = {"attack_id": a["id"], "unmodified_hit_probability": hit if target_supported else None,
                     "target_combat_class": classification, "target_component_role": component["role"],
                     "targetability_source": component.get("targetable"), "target_supported": bool(target_supported),
                     "target_facing": facing, "active_contacts_assumed": cfg["active_contacts"] if cfg["active_contacts"] is not None else min(8, _primary_count(attacker)),
                     "attack_interval_source_seconds": a.get("attack_interval"),
                     "charge_bonus_source": a.get("charge_bonus"),
                     "charge_decay_duration_assumed_seconds": cfg["charge_duration_seconds"],
                     "per_hit": _damage_per_hit(a.get("base_damage"), a.get("ap_damage"), defender,
                                                _traits(attacker, a["id"]), "melee", facing, component)
                     if target_supported and a.get("base_damage") is not None and a.get("ap_damage") is not None else None}
        result.append({"side": SIDES[i], "missile": missile, "melee": melee})
    return result


def _simulate(units, scenario):
    states = [_prepare(units[i], SIDES[i], scenario["sides"][SIDES[i]]) for i in range(2)]
    timing = _timing(states, scenario)
    for i, state in enumerate(states):
        cfg = scenario["sides"][SIDES[i]]
        attack = state["ranged"]
        if attack and cfg["fire"] and scenario["line_of_sight"] and cfg["cycle_seconds"] is None:
            state["gaps"].append("complete firing cycle unresolved; no shots scheduled")
        if attack and cfg["flight_seconds"] is not None:
            state["gaps"].append("projectile flight duration supplied as a scenario assumption")
        if attack and attack.get("explosion") and cfg["explosion_entities_per_collision"] == 1:
            state["gaps"].append("splash reach assumes one entity per colliding projectile")
        if state["melee"] and cfg["active_contacts"] is None:
            state["gaps"].append("active contacts default to min(8, living primary entities)")
    if scenario["historical_relations_apply_to_patch_9"]:
        _run(states, scenario, timing)
    return timing, _summary(states, scenario)


def _winner(summary):
    a, b = [row["effective_survivability_fraction"] for row in summary]
    if math.isclose(a, b, abs_tol=1e-9):
        return "tie"
    return "a" if a > b else "b"


def _sensitivity(units, scenario, nominal):
    """Find the nearest sampled one-parameter outcome switch, then refine it."""
    if nominal not in SIDES:
        return []
    results = []
    for side in SIDES:
        for field in ("collision_probability", "active_contacts"):
            current = scenario["sides"][side][field]
            if field == "active_contacts":
                if current is None:
                    current = min(8, _primary_count(units[SIDES.index(side)]))
                high = _primary_count(units[SIDES.index(side)])
            else:
                high = 1.0
            def winner_at(value):
                trial = copy.deepcopy(scenario)
                trial["sides"][side][field] = value
                return _winner(_simulate(units, trial)[1])
            grid = [high * n / 16 for n in range(17)]
            grid.append(current)
            grid = sorted(set(grid))
            switches = []
            for left, right in zip(grid, grid[1:]):
                w_left, w_right = winner_at(left), winner_at(right)
                if w_left == w_right:
                    continue
                lo, hi = left, right
                for _ in range(15):
                    mid = (lo + hi) / 2
                    if winner_at(mid) == w_left:
                        lo = mid
                    else:
                        hi = mid
                boundary = (lo + hi) / 2
                switches.append(boundary)
            if switches:
                threshold = min(switches, key=lambda x: abs(x - current))
                results.append({"side": side, "parameter": field, "current": current,
                                "approximate_flip_threshold": threshold,
                                "absolute_change": abs(threshold - current),
                                "method": "one-at-a-time sampled threshold; not a global minimum"})
    return results


def evaluate_matchup(queries: Queries, unit_a: str, unit_b: str, *, scenario: dict | None = None,
                     subculture_a: str | None = None, subculture_b: str | None = None) -> dict:
    """Return JSON-safe evidence, assumptions, timing, two ledgers and sensitivity.

    The same function is the intended CLI and MCP adapter entry point. Ambiguous
    names propagate Queries.ResolutionError with candidates; callers must resolve.
    """
    sc = _scenario(scenario)
    packet = queries.get_matchup_evidence(unit_a, unit_b, subculture=subculture_a,
                                          subculture_b=subculture_b, limit=256,
                                          include_diagnostics=True, include_provenance=True)
    _validate_source(packet, sc)
    units = packet["units"]
    unresolved_inputs = _core_unresolved(units, sc)
    timing = None
    summary = None
    nominal = "indeterminate"
    corners = []
    sensitivity = []
    barrier_sensitivity = []
    barrier_material = False
    if not unresolved_inputs:
        timing, summary = _simulate(units, sc)
        unresolved_inputs = _unresolved_inputs(units, sc, timing)
        for row in summary:
            row["stopping"]["contact_seconds"] = timing["contact"]["seconds"]
        nominal = _winner(summary) if sc["historical_relations_apply_to_patch_9"] else "indeterminate"
        for pa, pb in ((0, 0), (0, 1), (1, 0), (1, 1)):
            test = copy.deepcopy(sc)
            test["sides"]["a"]["collision_probability"] = pa
            test["sides"]["b"]["collision_probability"] = pb
            _, rows = _simulate(units, test)
            corners.append({"collision_probability_a": pa, "collision_probability_b": pb,
                            "favored": _winner(rows), "effective_survivability_fraction":
                            [r["effective_survivability_fraction"] for r in rows]})
        sensitivity = _sensitivity(units, sc, nominal) if sc["historical_relations_apply_to_patch_9"] else []
    if summary is not None and sc["historical_relations_apply_to_patch_9"] and any(
            u["body"].get("barrier_health") for u in units):
        alternate = copy.deepcopy(sc)
        alternate["barrier_damage_order"] = ("entity_cap_first" if sc["barrier_damage_order"] == "barrier_first"
                                             else "barrier_first")
        _, alternate_rows = _simulate(units, alternate)
        for order, rows in ((sc["barrier_damage_order"], summary),
                            (alternate["barrier_damage_order"], alternate_rows)):
            barrier_sensitivity.append({"barrier_damage_order": order, "favored": _winner(rows),
                                        "effective_survivability_fraction":
                                        [r["effective_survivability_fraction"] for r in rows],
                                        "barrier_absorbed":
                                        [r["incoming_damage"].get("barrier_absorbed", 0.0) for r in rows],
                                        "overkill": [r["incoming_damage"]["overkill"] for r in rows]})
        barrier_material = any(
            not math.isclose(summary[i][field], alternate_rows[i][field], abs_tol=1e-9)
            for i in range(2) for field in ("remaining_health", "remaining_barrier")) or any(
                not math.isclose(summary[i]["incoming_damage"]["overkill"],
                                 alternate_rows[i]["incoming_damage"]["overkill"], abs_tol=1e-9)
                for i in range(2))
    gaps = ([*summary[0]["coverage_gaps"], *summary[1]["coverage_gaps"]]
            if summary is not None else ["health-pool inputs unresolved; calculation withheld"])
    material_unresolved = bool(unresolved_inputs)
    gaps.extend(f"unresolved input {item['side']}.{item['source_path']} "
                f"({item['code']}) affects {item['calculation']}" for item in unresolved_inputs)
    if barrier_material and not sc["barrier_damage_order_explicit"]:
        material_unresolved = True
        gaps.append("barrier damage order changes the projection; supply barrier_damage_order for a conditional verdict")
    gaps.extend("source coverage: " + g["code"] + " - " + g["summary"] for u in units for g in u["coverage"].get("gaps", []))
    gaps += ["no routing or morale model",
             "entity casualties use pooled expected damage, not hit allocation", "shield facing and projectile block eligibility are simplified",
             "passive and activated modifiers, penetration, collision attacks, shrapnel and special death behavior are not applied"]
    if sc["historical_relations_apply_to_patch_9"]:
        gaps.append("8.1.1 relations are assumed applicable to 9.0; no live validation")
    if any(u["body"].get("barrier_health") for u in units):
        gaps.append("barrier damage order is a scenario assumption; recharge and barrier-specific rules are unmodeled")
    return {"model_version": MODEL_VERSION, "source_packet_version": packet["schema_version"],
            "snapshot": {**packet["snapshot"],
                         "serving_contract_sha256": getattr(queries, "snapshot", {}).get("contract_sha256")},
            "source_fingerprints": packet.get("sources", {}),
            "source_provenance": packet.get("provenance", {}),
            "source_payload_graph": packet.get("payload_graph", {}),
            "identities": [u["identity"] for u in units],
            "source_facts": [{"identity": u["identity"], "body": u["body"], "movement": u["movement"],
                              "leadership": u["leadership"], "melee": u["melee"], "ranged": u["ranged"],
                              "protection": u["passives"]["protection"], "attack_traits": u["passives"]["attack_traits"],
                              "attributes": u["passives"].get("attributes"),
                              "abilities": u["passives"].get("abilities"),
                              "activated_options": u.get("activated_options"),
                              "coverage": u["coverage"]} for u in units],
            "scenario_assumptions": sc, "empirical_calibration": None,
            "assumption_notes": ["Speed scale, path factor and terrain factor are illustrative; no measured map coordinates or acceleration.",
                                 "Default collision probability 0.5 is uncalibrated and is not the card accuracy value.",
                                 "When omitted, complete cycle is illustratively 1.25 times projectile reload; it is not an engine rule.",
                                 "Unspecified active contacts use min(8, living primary bodies); firing entities use the attached component count.",
                                 "Direct and explosion are separate expected hit events; default splash reach is one entity per collision.",
                                 "Positive listed velocity gives straight flight time from exact shot distance. Missing or nonpositive velocity uses an immediate-arrival firing-opportunity approximation unless flight_seconds is supplied; collision probability remains independent.",
                                 "Charge decays from the sourced bonus over the assumed duration and is bounded between zero and that bonus.",
                                 "Barrier-before-entity-cap is the represented default, not a verified game damage order; the alternate order is tested.",
                                 "Sourced explosion is_spell tags add the target's spell resistance to the assumed historical relation.",
                                 "Historical 8.1.1 hit, armour and resistance relations are assumed applicable to 9.0 only when enabled."],
            "derived": {"phase_timing": timing,
                        "event_mechanics": _mechanics(units, sc) if summary is not None and sc["historical_relations_apply_to_patch_9"] else None,
                        "ledgers": summary},
            "verdict": {"status": "conditional" if nominal not in ("tie", "indeterminate") and not material_unresolved else "indeterminate",
                        "nominal_favored": nominal if not material_unresolved else "indeterminate",
                        "represented_point_ordering": nominal,
                        "criterion": "remaining modeled health plus barrier fraction at horizon",
                        "collision_probability_corners": corners,
                        "barrier_damage_order_sensitivity": barrier_sensitivity,
                        "bounds_cross": len({c["favored"] for c in corners}) > 1 or bool(sensitivity) or
                                        len({case["favored"] for case in barrier_sensitivity}) > 1,
                        "material_mechanic_unresolved": material_unresolved,
                        "unresolved_inputs": unresolved_inputs,
                        "one_parameter_flip_thresholds": sensitivity,
                        "qualification": "Nominal result depends on uncalibrated firing/contact assumptions; routing is unknown."},
            "limitations": list(dict.fromkeys(gaps)),
            "tactical_contingencies": ["Distance, sight obstruction and terrain alter firing windows.",
                                       "Facing can change shield blocking and melee defence.",
                                       "Formation and interception change actual firing entities and active contacts.",
                                       "Fatigue, charge disruption, passives and target selection require separate validation."]}
