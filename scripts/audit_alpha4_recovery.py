"""Reproduce Alpha 4 inventory, old/new mechanics and compact-evidence checks.

Requires a built pinned snapshot and Git history containing the published review
baseline. Writes only a reproducible report under ignored work/ by default.
"""
import argparse
from collections import defaultdict
import copy
import json
from pathlib import Path
import re
import subprocess
import sys
import types

ROOT = Path(__file__).resolve().parents[1]
BASELINE = '804206d7fbf4edd3581de1f6446dbf0c2d028211'
sys.path.insert(0, str(ROOT / 'src'))
from ctw_adviser.queries import PACKET_VERSION, Queries
from validate_packets import packet_checks, validate


def require(condition, context):
    if not condition:
        raise ValueError(context)


def mechanical_content(value):
    """Exclude prose and evidence expansion, never numerical or relationship facts."""
    if isinstance(value, dict):
        return {k: mechanical_content(v) for k, v in value.items()
                if k not in ('summary', 'reason', 'provenance_refs', 'trigger_basis')}
    if isinstance(value, list):
        return [mechanical_content(v) for v in value]
    return value


def mechanic_facts(mechanic):
    effects = []
    settings = defaultdict(dict)
    for effect in mechanic['effects']:
        if effect.get('native_kind') == 'phase_behavior':
            # Reviewed fields move from unresolved to explained effects; preserve
            # the exact union of native settings and their owning phase.
            parameters = effect['native_parameters']
            require(not settings[effect['phase_ref']].keys() & parameters.keys(), 'duplicate phase setting')
            settings[effect['phase_ref']].update(parameters)
        else:
            effects.append(mechanical_content(effect))
    return (mechanical_content({k: v for k, v in mechanic.items() if k != 'effects'}),
            effects, dict(settings))


def size(packet):
    return len(json.dumps(packet, separators=(',', ':'), ensure_ascii=False).encode())


def before_chej_unit_shape(unit):
    """Compare Alpha 4 fields while retaining all of their mechanical values."""
    unit = copy.deepcopy(unit)
    unit['body'].pop('firing_arc', None)
    unit['body'].pop('health_aggregation', None)
    for component in unit['body']['components']:
        component.pop('health_contribution', None)
    for field in ('ground_speed', 'flight_speed', 'speed_basis', 'primary_body_key',
                  'provenance_refs'):
        unit['movement'].pop(field, None)
    ranged = unit['ranged']
    if ranged:
        for attack in [ranged, *ranged['variants']]:
            for field in ('firing_policy', 'reload', 'ammunition_supply', 'entity_stat_overrides'):
                attack.pop(field, None)
            if attack.get('explosion'):
                attack['explosion'].pop('native_parameters', None)
                attack['explosion'].pop('detail_ref', None)
    return unit


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db', type=Path, required=True)
    parser.add_argument('--output', type=Path, default=ROOT / 'work/alpha4-recovery-audit.json')
    args = parser.parse_args()
    inventory = json.loads((ROOT / 'fixtures/design/alpha4-review-inventory.json').read_text())
    require(inventory['reviewed_baseline'] == BASELINE, 'review baseline drift')
    for name, expected in (('aura', 193), ('qualification', 175)):
        require(len(inventory[name]) == len(set(inventory[name])) == expected, name + ' inventory drift')
    schema = json.loads((ROOT / 'schema/evidence_packet.schema.json').read_text())
    baseline = types.ModuleType('ctw_adviser.alpha4_published_baseline')
    baseline.__package__ = 'ctw_adviser'
    # Fixed repository-owned revision only, not caller-supplied executable code.
    exec(subprocess.check_output(['git', 'show', BASELINE + ':src/ctw_adviser/queries.py'],
                                 cwd=ROOT, text=True), baseline.__dict__)
    with baseline.Queries(args.db) as before, Queries(args.db) as after:
        combinations = [tuple(row) for row in after.db.execute(
            "SELECT DISTINCT ability_key,culture_key FROM unit_abilities JOIN ability_option_metadata USING(ability_key) "
            "WHERE classification='core_passive' ORDER BY 1,2")]
        current = {}; changed = set()
        for key, culture in combinations:
            a = before.get_passive_detail(key, culture=culture)
            b = after.get_passive_detail(key, culture=culture)
            require(mechanic_facts(a['mechanic']) == mechanic_facts(b['mechanic']), key + ': mechanical change')
            require(a['payload_graph'] == b['payload_graph'], key + ': payload change')
            current[key] = b['mechanic']
            validate(b['mechanic'], schema['$defs']['mechanic'], schema)
            if a['mechanic']['summary'] != b['mechanic']['summary']:
                changed.add(key)
        require(len(current) == 499 and len(combinations) == 503, 'passive inventory drift')
        require(set(inventory['aura'] + inventory['qualification']) <= current.keys(), 'missing review key')
        for key in inventory['aura']:
            radius = current[key]['native_parameters']['effect_range']
            require(f'within {radius:g} metres' in current[key]['summary'], key + ': missing radius')
            require('Affects ' in current[key]['summary'], key + ': missing recipient scope')
        obsolete = ('time units not verified', 'absolute amount versus ammunition fraction not verified',
                    'regeneration unit scale and timing not verified', 'amount units, effective timing')
        for key, mechanic in current.items():
            require('stat_' not in mechanic['summary'], key + ': unreadable stat')
            require(not any(text in mechanic['summary'] for text in obsolete), key + ': obsolete qualification')
        contexts = 0
        for key, subculture in after.db.execute('SELECT unit_key,subculture_key FROM unit_availability ORDER BY 1,2'):
            a = before.get_unit_profile(key, subculture=subculture, limit=256)
            b = after.get_unit_profile(key, subculture=subculture, limit=256, include_provenance=True)
            compact = after.get_unit_profile(key, subculture=subculture, limit=256)
            validate(b, schema, schema); packet_checks(b)
            validate(compact, schema, schema); packet_checks(compact, after.get_provenance)
            for field in ('units', 'payload_graph', 'detail_refs', 'trait_descriptions'):
                require(b[field] == compact[field], key + ': compact/expanded ' + field)
            comparable = before_chej_unit_shape(b['units'][0])
            for field in ('identity', 'body', 'movement', 'leadership', 'melee', 'ranged', 'cost', 'activated_options'):
                require(a['units'][0][field] == comparable[field], key + ': changed ' + field)
            require(a['payload_graph'] == b['payload_graph'], key + ': changed unit payload')
            contexts += 1
        require(contexts == 3181, 'roster context drift')
        report = {
            'status': 'passed', 'baseline_commit': BASELINE, 'packet_version': PACKET_VERSION,
            'source_commit': after.get_unit_profile('Lothern Sea Guard')['snapshot']['commit'],
            'ability_culture_combinations': len(combinations), 'definitions': len(current),
            'changed_summaries': len(changed),
            'qualified_summaries': sum(bool(re.search(r'unverified|not verified', m['summary'])) for m in current.values()),
            'raw_stat_identifiers': 0, 'obsolete_shared_qualifications': 0,
            'aura_inventory': len(inventory['aura']), 'qualification_inventory': len(inventory['qualification']),
            'roster_contexts': contexts, 'compact_and_expanded_validated': True,
            'native_mechanical_facts_unchanged': True, 'payload_graphs_unchanged': True,
            'sea_guard_baseline_bytes': size(before.get_unit_profile('Lothern Sea Guard')),
            'sea_guard_compact_bytes': size(after.get_unit_profile('Lothern Sea Guard')),
            'sea_guard_expanded_bytes': size(after.get_unit_profile('Lothern Sea Guard', include_provenance=True)),
        }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report))


if __name__ == '__main__':
    main()
