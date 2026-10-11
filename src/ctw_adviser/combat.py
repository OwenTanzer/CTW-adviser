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

MODEL_VERSION = "combat-0.1.0"
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


def _damage_per_hit(base, ap, target, traits, kind, facing):
    base = _number(base, "base_damage")
    ap = _number(ap, "ap_damage")
    classification = target["body"].get("target_classification", {}).get("combat_class")
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
    resist = min(90.0, max(-100.0, resist))
    damage = ((base + bonus) * _armour_survival(armour) + ap) * (1 - resist / 100)
    shield = 0.0
    if kind == "missile" and facing == "front":
        shield = _fraction((protection.get("shield_block_chance") or 0) / 100, "shield_block_chance")
    return {"per_unblocked_hit": damage, "size_bonus_as_base": bonus,
            "armour_survival": _armour_survival(armour), "resistance_points": resist,
            "shield_block_probability": shield}


def _pool(unit, target_role):
    body = unit["body"]
    components = body.get("components") or []
    if not components:
        components = [{"id": "primary", "role": "primary", "count": body["entity_count"],
                       "known_hp_total": body["total_hp"], "primary": True}]
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
    return pools, selected["id"]


def _scenario(value):
    if value is None:
        value = {}
    if not isinstance(value, dict):
        raise ValueError("scenario must be an object")
    allowed = {"mode", "baseline", "separation_metres", "duration_seconds", "metres_per_second_per_speed_point",
               "path_length_factor", "terrain_speed_factor", "line_of_sight", "sides",
               "historical_relations_apply_to_patch_9"}
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
        "sides": {},
    }
    if normalized["mode"] != "custom_battle" or normalized["baseline"] != "unmodified_ultra_rank_0":
        raise ValueError("only the pinned unmodified custom-battle baseline is supported")
    for key in ("line_of_sight", "historical_relations_apply_to_patch_9"):
        if type(normalized[key]) is not bool:
            raise ValueError(f"{key} must be boolean")
    allowed_side = {"order", "fire", "fight", "facing", "ranged_attack_id", "collision_probability", "firing_entities",
                    "cycle_seconds", "first_shot_delay_seconds", "projectiles_per_cycle", "explosion_entities_per_collision",
                    "active_contacts", "charge_duration_seconds", "target_component_role", "combat_effective_fraction"}
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
        normalized["sides"][side] = {
            "order": order, "fire": user.get("fire", True), "fight": user.get("fight", True), "facing": facing,
            "ranged_attack_id": user.get("ranged_attack_id"),
            "collision_probability": _setting(user, "collision_probability", .5, f"{side}.collision_probability", fraction=True),
            "firing_entities": None if user.get("firing_entities") is None else _setting(user, "firing_entities", 1, f"{side}.firing_entities"),
            "cycle_seconds": None if user.get("cycle_seconds") is None else _setting(user, "cycle_seconds", 1, f"{side}.cycle_seconds", positive=True),
            "first_shot_delay_seconds": _setting(user, "first_shot_delay_seconds", 1, f"{side}.first_shot_delay_seconds"),
            "projectiles_per_cycle": None if user.get("projectiles_per_cycle") is None else _setting(user, "projectiles_per_cycle", 1, f"{side}.projectiles_per_cycle", positive=True),
            "explosion_entities_per_collision": _setting(user, "explosion_entities_per_collision", 1, f"{side}.explosion_entities_per_collision"),
            "active_contacts": None if user.get("active_contacts") is None else _setting(user, "active_contacts", 1, f"{side}.active_contacts"),
            "charge_duration_seconds": _setting(user, "charge_duration_seconds", 0, f"{side}.charge_duration_seconds"),
            "target_component_role": user.get("target_component_role", "primary"),
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
    pools, target = _pool(unit, setting["target_component_role"])
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
    weapon_state = next((x["state"] for x in unit["coverage"]["sections"] if x["name"] == "weapons"), "unresolved")
    if weapon_state != "complete":
        gaps.append("weapon section is " + weapon_state + "; selected attacks may omit alternatives")
    if unit["coverage"].get("melee") == "unresolved" or unit["coverage"].get("ranged") == "unresolved":
        gaps.append("one or more attack capabilities are unresolved")
    if len(ranged) > 1:
        gaps.append("multiple ranged attachments or variants exist; only one selected attack is evaluated, with simultaneous firing unresolved")
    if len(melee) > 1:
        gaps.append("multiple melee attachments exist; only the primary attack is evaluated")
    if m and any(m.get(field) is None for field in ("attack", "base_damage", "ap_damage", "attack_interval")):
        gaps.append("primary melee attack has missing calculation fields; melee damage omitted")
        m = None
    if m and (m.get("max_splash_targets") or 1) > 1:
        gaps.append("melee splash target selection and damage distribution are not modeled as extra damage")
    if m and m.get("native_parameters", {}).get("collision_attack_max_targets"):
        gaps.append("collision attacks have separate timing and are not included")
    if attack:
        if any(attack.get(field) is None for field in ("range", "base_damage", "ap_damage", "velocity")):
            gaps.append("selected ranged attack has missing range, damage or velocity; shots omitted")
            attack = None
    if attack:
        counts = [attack.get(k) for k in ("projectiles_per_shot", "shots_per_volley", "burst_size")]
        if setting["projectiles_per_cycle"] is None and any(x not in (None, 1, 1.0) for x in counts):
            gaps.append("projectile/volley/burst nesting unresolved; set projectiles_per_cycle")
            attack = None
        elif setting["projectiles_per_cycle"] is None:
            setting["projectiles_per_cycle"] = 1.0
        if attack and setting["cycle_seconds"] is None and attack.get("reload_time") is not None:
            setting["cycle_seconds"] = 1.25 * _number(attack["reload_time"], "reload_time", positive=True)
            gaps.append("complete firing cycle assumes 1.25 times listed projectile reload; uncalibrated")
        supply = attack.get("ammunition_supply") if attack else None
        if supply and (supply.get("assignment_status") != "sources_agree" or supply.get("unlimited")):
            gaps.append("ammunition pool or finite exhaustion unresolved")
    return {"unit": unit, "pools": pools, "target": target, "primary": primary,
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


def _apply(state, channel, attempts, damage):
    if attempts <= 0 or damage is None:
        return
    pool = state["pools"][state["target"]]
    nominal = attempts * damage
    capped = attempts * min(damage, pool["hp_per_entity"])
    state["ledger"]["attempted_damage"] += nominal
    state["ledger"]["overkill"] += nominal - capped
    absorbed = min(state["remaining_barrier"], capped)
    state["remaining_barrier"] -= absorbed
    state["ledger"].setdefault("barrier_absorbed", 0.0)
    state["ledger"]["barrier_absorbed"] += absorbed
    capped -= absorbed
    actual = min(pool["remaining_hp"], capped)
    pool["remaining_hp"] -= actual
    state["ledger"][channel] += actual


def _score(states):
    return [(sum(p["remaining_hp"] for p in s["pools"].values()) + s["remaining_barrier"]) /
            (sum(p["initial_hp"] for p in s["pools"].values()) + s["initial_barrier"]) for s in states]


def _run(states, scenario, timing):
    duration = scenario["duration_seconds"]
    contact = timing["contact"]["seconds"]
    closing = timing["closing_speed_metres_per_second"]
    speed = closing if closing is not None else 0
    separation = scenario["separation_metres"]
    queue = []
    for i, state in enumerate(states):
        attack = state["ranged"]
        if attack:
            state["next_shot"] = timing["range_entry"][i]["seconds"]
            if state["next_shot"] is not None:
                state["next_shot"] += scenario["sides"][SIDES[i]]["first_shot_delay_seconds"]
    # One-second expected-value ticks. Shot events retain discrete complete-cycle
    # times and arrival times; melee contributes rate-integrated one-second terms.
    for tick in range(math.ceil(duration)):
        t = float(tick)
        dt = min(1.0, duration - t)
        distance = max(0, separation - speed * t)
        for i, state in enumerate(states):
            cfg = scenario["sides"][SIDES[i]]
            attack = state["ranged"]
            if not cfg["fire"] or not scenario["line_of_sight"] or not attack or state["next_shot"] is None:
                continue
            if contact is not None and t >= contact:
                continue
            if not (attack["minimum_range"] or 0) <= distance <= attack["range"]:
                continue
            cycle = cfg["cycle_seconds"]
            if cycle is None:
                continue
            ammo = _ammo_limit(attack)
            if ammo is None:
                continue
            while state["next_shot"] <= t + dt - 1e-9 and state["shots_fired"] < ammo:
                fired_at = state["next_shot"]
                if contact is not None and fired_at >= contact:
                    break
                shooter_count = cfg["firing_entities"]
                if shooter_count is None:
                    component = state["pools"].get(attack.get("component_ref"))
                    shooter_count = component["initial_entities"] if component else state["primary"]["initial_entities"]
                component = state["pools"].get(attack.get("component_ref"), state["primary"])
                shooter_count = min(shooter_count, _living(component))
                if shooter_count <= 0:
                    break
                flight = distance / attack["velocity"] if attack.get("velocity") else None
                if flight is not None:
                    heapq.heappush(queue, (fired_at + flight, i, shooter_count * cfg["projectiles_per_cycle"], distance))
                state["shot_events"] += 1
                state["shots_fired"] += 1
                state["next_shot"] += cycle
        while queue and queue[0][0] <= t + dt:
            arrived, i, projectiles, _ = heapq.heappop(queue)
            attacker, defender = states[i], states[1 - i]
            attack = attacker["ranged"]
            cfg = scenario["sides"][SIDES[i]]
            facing = scenario["sides"][SIDES[1 - i]]["facing"]
            traits = _traits(attacker["unit"], attack["id"])
            direct = _damage_per_hit(attack["base_damage"], attack["ap_damage"], defender["unit"], traits, "missile", facing)
            if direct:
                hits = projectiles * cfg["collision_probability"] * (1 - direct["shield_block_probability"])
                _apply(defender, "direct", hits, direct["per_unblocked_hit"])
            explosion = attack.get("explosion")
            if explosion:
                ex_traits = _traits(attacker["unit"], explosion["id"])
                ex = _damage_per_hit(explosion["base_damage"], explosion["ap_damage"], defender["unit"], ex_traits, "explosion", facing)
                if ex:
                    _apply(defender, "explosion", projectiles * cfg["collision_probability"] *
                           cfg["explosion_entities_per_collision"], ex["per_unblocked_hit"])
        if contact is not None and t + dt > contact:
            melee_dt = t + dt - max(t, contact)
            # Simultaneous expected attacks use pre-tick living counts.
            events = []
            for i, attacker in enumerate(states):
                cfg = scenario["sides"][SIDES[i]]
                attack = attacker["melee"]
                defender = states[1 - i]
                if not cfg["fight"] or not attack or not _living(attacker["primary"]):
                    continue
                target_cfg = scenario["sides"][SIDES[1 - i]]
                contacts = cfg["active_contacts"]
                if contacts is None:
                    contacts = min(8, attacker["primary"]["initial_entities"])
                contacts = min(contacts, _living(attacker["primary"]))
                traits = _traits(attacker["unit"], attack["id"])
                classification = defender["unit"]["body"].get("target_classification", {}).get("combat_class")
                bonus_field = {"infantry": "bonus_vs_infantry", "large": "bonus_vs_large"}.get(classification)
                bonus = traits.get(bonus_field, 0) or 0
                charge = 0.0
                if cfg["charge_duration_seconds"] and t - contact < cfg["charge_duration_seconds"]:
                    charge = (attack.get("charge_bonus") or 0) * max(0, 1 - (t - contact) / cfg["charge_duration_seconds"])
                facing = target_cfg["facing"]
                hit = min(.90, max(.08, .35 + ((attack.get("attack") or 0) + bonus + charge -
                                             (defender["melee"] or {}).get("defence", 0) * FACING[facing]) / 100))
                damage = _damage_per_hit(attack["base_damage"] + charge, attack["ap_damage"],
                                         defender["unit"], traits, "melee", facing)
                if damage and attack.get("attack_interval"):
                    events.append((1 - i, contacts * melee_dt / attack["attack_interval"] * hit,
                                   damage["per_unblocked_hit"]))
            for target, hits, damage in events:
                _apply(states[target], "melee", hits, damage)
        for i, state in enumerate(states):
            own_cfg = scenario["sides"][SIDES[i]]
            all_hp = sum(p["remaining_hp"] for p in state["pools"].values())
            primary_living = _living(state["primary"])
            if all_hp <= 0 and state["stops"]["health_depleted_seconds"] is None:
                state["stops"]["health_depleted_seconds"] = t + dt
            if primary_living / state["primary"]["initial_entities"] <= own_cfg["combat_effective_fraction"] and state["stops"]["combat_ineffective_seconds"] is None:
                state["stops"]["combat_ineffective_seconds"] = t + dt
            attack = state["ranged"]
            if attack and state["stops"]["firing_ceased_seconds"] is None:
                ammo = _ammo_limit(attack)
                firing_component = state["pools"].get(attack.get("component_ref"), state["primary"])
                if _living(firing_component) == 0 or (ammo is not None and state["shots_fired"] >= ammo) or (contact is not None and t + dt >= contact):
                    state["stops"]["firing_ceased_seconds"] = t + dt
    return states


def _timing(states, scenario):
    speed = [s["unit"]["movement"].get("speed") for s in states]
    closing = None if None in speed else sum(ORDERS[scenario["sides"][SIDES[i]]["order"]] * speed[i]
                                                  for i in range(2)) * scenario["metres_per_second_per_speed_point"] * scenario["terrain_speed_factor"] / scenario["path_length_factor"]
    distance = scenario["separation_metres"]
    def entry(threshold):
        return {"status": "unknown_input", "seconds": None} if closing is None or threshold is None else _entry(distance, threshold, closing)
    return {"closing_speed_metres_per_second": closing, "contact": entry(0),
            "range_entry": [entry(s["ranged"].get("range") if s["ranged"] else None) for s in states],
            "minimum_range": [s["ranged"].get("minimum_range") if s["ranged"] else None for s in states],
            "flight_speed": [s["ranged"].get("velocity") if s["ranged"] else None for s in states]}


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
        facing = scenario["sides"][SIDES[1 - i]]["facing"]
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
                           "direct": _damage_per_hit(selected["base_damage"], selected["ap_damage"],
                                                     defender, traits, "missile", facing), "explosion": None}
                ex = selected.get("explosion")
                if ex:
                    missile["explosion"] = {"radius_source_metres": ex.get("radius"),
                                            "affected_entities_assumed": cfg["explosion_entities_per_collision"],
                                            "damage": _damage_per_hit(ex["base_damage"], ex["ap_damage"], defender,
                                                                      _traits(attacker, ex["id"]), "explosion", facing)}
        melee = None
        attack = _attacks(attacker, "melee")
        defending_attack = _attacks(defender, "melee")
        if attack and defending_attack:
            a = attack[0]
            classification = defender["body"].get("target_classification", {}).get("combat_class")
            bonus_field = {"infantry": "bonus_vs_infantry", "large": "bonus_vs_large"}.get(classification)
            bonus = (_traits(attacker, a["id"]).get(bonus_field) or 0) if bonus_field else 0
            hit = min(.90, max(.08, .35 + ((a.get("attack") or 0) + bonus -
                                         (defending_attack[0].get("defence") or 0) * FACING[facing]) / 100))
            melee = {"attack_id": a["id"], "unmodified_hit_probability": hit,
                     "target_facing": facing, "active_contacts_assumed": cfg["active_contacts"] if cfg["active_contacts"] is not None else min(8, attacker["body"]["entity_count"]),
                     "attack_interval_source_seconds": a.get("attack_interval"),
                     "charge_bonus_source": a.get("charge_bonus"),
                     "charge_decay_duration_assumed_seconds": cfg["charge_duration_seconds"],
                     "per_hit": _damage_per_hit(a.get("base_damage"), a.get("ap_damage"), defender,
                                                _traits(attacker, a["id"]), "melee", facing) if a.get("base_damage") is not None and a.get("ap_damage") is not None else None}
        result.append({"side": SIDES[i], "missile": missile, "melee": melee})
    return result


def _simulate(units, scenario):
    states = [_prepare(units[i], SIDES[i], scenario["sides"][SIDES[i]]) for i in range(2)]
    timing = _timing(states, scenario)
    for i, state in enumerate(states):
        cfg = scenario["sides"][SIDES[i]]
        attack = state["ranged"]
        if attack and cfg["cycle_seconds"] is None:
            state["gaps"].append("effective complete firing cycle not supplied; no shots scheduled")
        if attack and not attack.get("velocity"):
            state["gaps"].append("projectile velocity missing; flight and impact not scheduled")
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
                    current = min(8, units[SIDES.index(side)]["body"]["entity_count"])
                high = units[SIDES.index(side)]["body"]["entity_count"]
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
    timing, summary = _simulate(units, sc)
    for row in summary:
        row["stopping"]["contact_seconds"] = timing["contact"]["seconds"]
    nominal = _winner(summary) if sc["historical_relations_apply_to_patch_9"] else "indeterminate"
    corners = []
    for pa, pb in ((0, 0), (0, 1), (1, 0), (1, 1)):
        test = copy.deepcopy(sc)
        test["sides"]["a"]["collision_probability"] = pa
        test["sides"]["b"]["collision_probability"] = pb
        _, rows = _simulate(units, test)
        corners.append({"collision_probability_a": pa, "collision_probability_b": pb,
                        "favored": _winner(rows), "effective_survivability_fraction": [r["effective_survivability_fraction"] for r in rows]})
    sensitivity = _sensitivity(units, sc, nominal) if sc["historical_relations_apply_to_patch_9"] else []
    gaps = [*summary[0]["coverage_gaps"], *summary[1]["coverage_gaps"]]
    gaps.extend("source coverage: " + g["code"] + " - " + g["summary"] for u in units for g in u["coverage"].get("gaps", []))
    gaps += ["no routing or morale model",
             "entity casualties use pooled expected damage, not hit allocation", "shield facing and projectile block eligibility are simplified",
             "passive and activated modifiers, penetration, collision attacks, shrapnel and special death behavior are not applied"]
    if sc["historical_relations_apply_to_patch_9"]:
        gaps.append("8.1.1 relations are assumed applicable to 9.0; no live validation")
    if any(u["body"].get("barrier_health") for u in units):
        gaps.append("barrier absorbs damage first; recharge and barrier-specific rules are unmodeled")
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
                                 "Straight flight time is distance divided by listed muzzle velocity; trajectory and obstruction effects are unknown.",
                                 "Historical 8.1.1 hit, armour and resistance relations are assumed applicable to 9.0 only when enabled."],
            "derived": {"phase_timing": timing,
                        "event_mechanics": _mechanics(units, sc) if sc["historical_relations_apply_to_patch_9"] else None,
                        "ledgers": summary},
            "verdict": {"status": "conditional" if nominal not in ("tie", "indeterminate") else "indeterminate",
                        "nominal_favored": nominal, "criterion": "remaining modeled health plus barrier fraction at horizon",
                        "collision_probability_corners": corners,
                        "bounds_cross": len({c["favored"] for c in corners}) > 1,
                        "one_parameter_flip_thresholds": sensitivity,
                        "qualification": "Nominal result depends on uncalibrated firing/contact assumptions; routing is unknown."},
            "limitations": list(dict.fromkeys(gaps)),
            "tactical_contingencies": ["Distance, sight obstruction and terrain alter firing windows.",
                                       "Facing can change shield blocking and melee defence.",
                                       "Formation and interception change actual firing entities and active contacts.",
                                       "Fatigue, charge disruption, passives and target selection require separate validation."]}
