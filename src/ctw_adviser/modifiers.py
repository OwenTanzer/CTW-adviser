"""Shared sourced-stat operations for passive phases and future #20 adapters.

Extracted from issue-20/effect-modifiers' field/application design. No activation,
recipient selection, source imports, or combat equations belong in this layer.
"""
import math
from .queries import STAT_NAMES

STAT_FIELDS = {
    'stat_melee_attack': [('melee', 'attack')],
    'stat_melee_defence': [('melee', 'defence')],
    'stat_melee_damage_base': [('melee', 'base_damage')],
    'stat_melee_damage_ap': [('melee', 'ap_damage')],
    'stat_charge_bonus': [('melee', 'charge_bonus')],
    'scalar_speed': [('movement', 'speed'), ('movement', 'ground_speed')],
    'stat_morale': [('unit', 'leadership')],
    'stat_armour': [('protection', 'armour')],
    'stat_resistance_physical': [('protection', 'physical_resistance')],
    'stat_resistance_missile': [('protection', 'missile_resistance')],
    'stat_resistance_magic': [('protection', 'spell_resistance')],
    'stat_resistance_flame': [('protection', 'fire_resistance')],
    'stat_resistance_all': [('protection', 'ward_save')],
    'stat_missile_block_chance': [('protection', 'shield_block_chance')],
    'scalar_missile_damage_base': [('ranged', 'base_damage')],
    'scalar_missile_damage_ap': [('ranged', 'ap_damage')],
    'stat_bonus_vs_large': [('melee_traits', 'bonus_vs_large')],
    'stat_bonus_vs_infantry': [('melee_traits', 'bonus_vs_infantry')],
}
NATIVE_STAT = {name: token for token, name in STAT_NAMES.items()}


def stat_token(effect):
    return NATIVE_STAT.get(effect['stat'], effect['stat'])


def targets(unit, area):
    if area in ('melee', 'ranged'):
        attack = unit.get(area)
        return [attack, *attack.get('variants', [])] if isinstance(attack, dict) and attack.get('status') != 'absent' else []
    if area == 'protection':
        return [unit['passives']['protection']]
    if area == 'movement':
        return [unit['movement']]
    if area == 'unit':
        return [unit]
    if area == 'melee_traits':
        trait = unit['passives']['attack_traits'].get('melee')
        return [trait] if trait else []
    raise ValueError('unsupported stat area')


def apply_modifiers(unit, effects):
    """Mutate only a caller-owned copy; reject missing/invalid arithmetic inputs."""
    changes = []
    for effect in effects:
        token = stat_token(effect)
        value, op = effect['value'], effect['operation']
        if op not in ('add', 'multiply'):
            raise ValueError('unsupported modifier operation')
        if type(value) not in (int, float) or not math.isfinite(value):
            raise ValueError('missing or invalid material effect value')
        for area, field in STAT_FIELDS[token]:
            for target in targets(unit, area):
                before = target.get(field)
                if before is None:
                    raise ValueError('missing base value for ' + area + '.' + field)
                after = before + value if op == 'add' else before * value
                if not math.isfinite(after):
                    raise ValueError('nonfinite effective stat')
                if field not in ('leadership', 'ward_save', 'physical_resistance', 'missile_resistance', 'spell_resistance', 'fire_resistance') and after < 0:
                    raise ValueError('effective stat outside supported domain')
                if field == 'shield_block_chance' and after > 100:
                    raise ValueError('effective shield block outside supported domain')
                target[field] = after
                changes.append({'stat_token': token, 'path': area + '.' + field,
                                'base': before, 'effective': after, 'operation': op,
                                'value': value, 'provenance_refs': effect['provenance_refs']})
    return changes
