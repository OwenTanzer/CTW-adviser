"""Conditional self-passive lifecycle; source predicates are not activation rules."""
import copy
import math
from .modifiers import STAT_FIELDS, stat_token, apply_modifiers

EPSILON = 1e-9  # fraction of source base health; equality band is explicit
HEALTH = 'health_below_50%_base'


def normalize_choices(value):
    if not isinstance(value, list) or len(value) > 8:
        raise ValueError('passives must be a list of at most eight explicit choices')
    result = []
    for row in value:
        if not isinstance(row, dict) or set(row) - {'key', 'initial_active', 'equality', 'reactivation', 'condition_assumptions'}:
            raise ValueError('invalid passive choice')
        if not isinstance(row.get('key'), str) or not row['key'] or type(row.get('initial_active')) is not bool:
            raise ValueError('passive requires key and explicit initial_active boolean')
        equality = row.get('equality', 'active')
        reactivation = row.get('reactivation', 'unresolved')
        conditions = row.get('condition_assumptions', {})
        if equality not in ('active', 'inactive') or reactivation not in ('unresolved', 'when_eligible', 'never'):
            raise ValueError('invalid equality/reactivation assumption')
        if not isinstance(conditions, dict) or any(type(v) is not bool for v in conditions.values()):
            raise ValueError('condition assumptions must be predicate:boolean pairs')
        if any(x['key'] == row['key'] for x in result):
            raise ValueError('duplicate passive: stacking/refresh unsupported')
        result.append(dict(key=row['key'], initial_active=row['initial_active'], equality=equality,
                           reactivation=reactivation, condition_assumptions=copy.deepcopy(conditions)))
    return result


def resolve_passives(unit, choices, provenance):
    resolved = []
    used = set()
    for choice in choices:
        matches = [a for a in unit['passives'].get('abilities', []) if a['key'] == choice['key']]
        if len(matches) != 1:
            raise ValueError('passive does not resolve to one attached recipient ability: ' + choice['key'])
        ability = matches[0]
        phases = ability['phases']
        if len(phases) != 1 or not phases[0]['target_self'] or phases[0]['target_friends'] or phases[0]['target_enemies']:
            raise ValueError('only one self-only passive phase is supported')
        phase = phases[0]
        if phase['duration'] != -1 or ability.get('requires_effect_enabling'):
            raise ValueError('finite duration/enabling requires unsupported lifecycle')
        if ability.get('spreadings') or ability['native_parameters'].get('intensity_based_activation'):
            raise ValueError('spreading/intensity lifecycle unsupported')
        conditions = ability['conditions']
        if any(conditions.get(k) for k in ('activates_when','recipient_requirements','recharges_when','unavailable_when','invalid_targets','unresolved')):
            raise ValueError('unsupported activation/recipient/refresh conditions')
        predicates = [x['key'] for x in conditions['deactivates_when']]
        if set(choice['condition_assumptions']) - (set(predicates) - {HEALTH}):
            raise ValueError('condition assumption must reference an attached non-health predicate')
        if set(predicates) - {HEALTH} - set(choice['condition_assumptions']):
            raise ValueError('non-health predicate needs explicit condition assumption')
        effects = ability['effects']
        unsupported = []
        supported = []
        refs = list(ability['provenance_refs']) + phase['provenance_refs']
        for condition in conditions['deactivates_when']:
            refs += condition['provenance_refs']
        for effect in effects:
            if effect.get('phase_ref') != phase['key']:
                raise ValueError('dangling or wrong effect phase reference')
            refs += effect.get('provenance_refs', [])
            if not effect.get('provenance_refs'):
                raise ValueError('effect has no source reference')
            if effect['kind'] != 'stat_modifier' or stat_token(effect) not in STAT_FIELDS:
                unsupported.append(copy.deepcopy(effect))
                continue
            if effect['operation'] not in ('add', 'multiply') or effect.get('native_operation') != {'add':'add','multiply':'mult'}[effect['operation']]:
                raise ValueError('invalid or inconsistent modifier operation')
            value = effect.get('value')
            if type(value) not in (int, float) or not math.isfinite(value):
                raise ValueError('missing or invalid material effect value')
            token = stat_token(effect)
            if token in used:
                raise ValueError('overlapping stat stacking/refresh unsupported')
            used.add(token)
            supported.append(effect)
        if any(ref not in provenance for ref in refs):
            raise ValueError('dangling passive provenance reference')
        # A phase's additional non-stat channels must stay visible even if stats work.
        lifecycle = phase.get('lifecycle', {})
        extra = {k:v for k,v in lifecycle.items() if v not in (None, False, 0, '') and k not in ('effect_type','affects_allies','affects_enemies')}
        resolved.append({'choice': choice, 'ability': ability, 'effects': supported,
                         'unsupported_effects': unsupported, 'unsupported_lifecycle': extra,
                         'source_refs': list(dict.fromkeys(refs)), 'predicates': predicates,
                         'active': False, 'ever_active': False, 'last_eligible': None,
                         'diagnostics': []})
    return resolved


def transition(item, health_fraction, *, initial=False):
    """Also usable with controlled recovery traces; no healing simulation implied."""
    c = item['choice']
    disabled = any(c['condition_assumptions'].get(p, False) for p in item['predicates'] if p != HEALTH)
    if HEALTH in item['predicates']:
        at = abs(health_fraction - .5) <= EPSILON
        disabled |= health_fraction < .5 - EPSILON or (at and c['equality'] == 'inactive')
    eligible = not disabled
    old = item['active']
    if initial:
        item['active'] = c['initial_active'] and eligible
    elif not eligible:
        item['active'] = False
    elif not old and item['last_eligible'] is False:
        if c['reactivation'] == 'when_eligible':
            item['active'] = True
        elif c['reactivation'] == 'unresolved':
            item['diagnostics'].append('recovery observed; reactivation unresolved, kept inactive')
    item['last_eligible'] = eligible
    item['ever_active'] |= item['active']
    return old != item['active']


def effective_unit(base, items):
    unit = copy.deepcopy(base)
    ledger = []
    for item in items:
        if item['active']:
            changes = apply_modifiers(unit, item['effects'])
            ledger.extend(dict(change, ability_key=item['choice']['key']) for change in changes)
    return unit, ledger
