"""Record representative #20 predictions and full-inventory sweeps.

Writes exact inputs and key outputs for named cases, plus status counts and
latency for every represented effect through both calculation paths. These are
model predictions and regression evidence, not live-battle observations.

    python scripts/record_effect_predictions.py --db work/adviser.sqlite --output docs/effect-predictions.json
"""
import argparse
import collections
import json
from pathlib import Path
import platform
import sqlite3
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from ctw_adviser.effect_calc import MODEL_VERSION as DAMAGE_MODEL, evaluate_effect_damage
from ctw_adviser.effect_engagement import MODEL_VERSION as ENGAGEMENT_MODEL, evaluate_effect_engagement
from ctw_adviser.queries import Queries

TARGET = 'Lothern Sea Guard'
OPPONENT = 'Bloodletters of Khorne'
MELEE = {'separation_metres': 40, 'sides': {'a': {'order': 'hold'}, 'b': {'order': 'approach'}}}
DAMAGE_CASES = [
    ('wh_main_spell_heavens_comet_of_casandora', {}),
    ('wh_main_spell_heavens_comet_of_casandora_upgraded', {}),
    ('wh3_dlc23_spell_bound_hell_hammer', {'vortex_entities_per_application': 4, 'vortex_applications': 2}),
    ('wh2_main_spell_grey_seer_the_dreaded_thirteenth_spell', {}),
    ('wh2_dlc09_spell_death_spirit_leech_bound', {}),
    ('wh2_dlc11_character_abilities_pyromaniac', {'contact_phase_ticks': 4}),
]
ENGAGEMENT_CASES = [
    ('wh2_main_spell_high_magic_hand_of_glory', TARGET, OPPONENT, 'a', 'friendly'),
    ('wh2_main_spell_plague_wither', TARGET, OPPONENT, 'b', 'enemy'),
    ('wh2_dlc11_army_abilities_shanty_verse_1', TARGET, OPPONENT, 'a', 'friendly'),
    ('wh2_dlc17_spell_wild_mantle_of_ghorok_upgraded', TARGET, OPPONENT, 'a', 'friendly'),
    ('wh2_dlc10_lord_abilities_gaze_of_khaine', 'wh2_dlc10_def_cha_crone_0', OPPONENT, 'a', 'friendly'),
]


def damage_case(q, effect, scenario):
    r = evaluate_effect_damage(q, effect, TARGET, scenario=scenario)
    t = r['derived']['totals']
    return {'inputs': {'effect': effect, 'target': TARGET, 'scenario': scenario},
            'resolved': {'effect': r['identities']['effect']['ability_key'], 'target': r['identities']['target']['unit_key']},
            'status': r['status'], 'unresolved': [u['code'] for u in r['unresolved_inputs']],
            'components': [{'channel': c['channel'], 'key': c['key'], 'route_role': c['route_role'],
                            'expected_damage': c['expected_damage']} for c in r['derived']['components']],
            'attempted_damage': t['attempted_damage'], 'upper_all_routes': t['upper_all_routes_attempted_damage'],
            'health_damage_capped': t['health_damage_capped'], 'fraction_of_health': t['fraction_of_health'],
            'casualties': {k: v for k, v in t['casualties'].items() if k != 'basis'}}


def engagement_case(q, effect, a, b, recipient, relation):
    r = evaluate_effect_engagement(q, effect, a, b, recipient=recipient, relation=relation, scenario=MELEE)
    primary = r['comparisons'].get('active_window') or r['comparisons'].get('horizon')
    return {'inputs': {'effect': effect, 'unit_a': a, 'unit_b': b, 'recipient': recipient, 'relation': relation,
                       'scenario': MELEE},
            'status': r['status'], 'window': r['window'],
            'changed_inputs': [(c['path'], c['before'], c['after']) for c in r['modifiers']['changed_inputs']],
            'unsupported': [u.get('stat_token', u.get('kind')) for u in r['modifiers']['unsupported']],
            'primary_comparison': 'active_window' if 'active_window' in r['comparisons'] else 'horizon',
            'survivability': {s['side']: s['effective_survivability_fraction'] for s in primary['sides']} if primary else None,
            'verdict': primary['verdict'] if primary else None,
            'corners_changed': len(primary['sensitivity']['effect_changes_favored_at']) if primary else None}


def sweep(q, keys, run):
    statuses, timings, sizes, errors = collections.Counter(), [], [], []
    for key in keys:
        started = time.perf_counter()
        try:
            result = run(key)
        except Exception as exc:  # recorded, never hidden
            errors.append({'effect': key, 'error': repr(exc)[:200]})
            continue
        timings.append(time.perf_counter() - started)
        sizes.append(len(json.dumps(result)))
        statuses[result['status'] + (':' + ','.join(b['code'] for b in result['blocked']) if result['blocked'] else '')] += 1
    timings.sort(); sizes.sort()
    pct = lambda xs, p: xs[min(len(xs) - 1, int(len(xs) * p))]
    return {'checked': len(keys), 'errors': errors, 'statuses': dict(sorted(statuses.items())),
            'latency_ms': {'median': round(pct(timings, .5) * 1e3, 2), 'p95': round(pct(timings, .95) * 1e3, 2),
                           'max': round(timings[-1] * 1e3, 2)},
            'bytes': {'median': pct(sizes, .5), 'max': sizes[-1]}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    with Queries(args.db) as q:
        keys = [r[0] for r in q.db.execute('SELECT ability_key FROM effect_abilities ORDER BY ability_key')]
        stat_keys = [r[0] for r in q.db.execute(
            "SELECT DISTINCT l.special_ability FROM native_ability_phase_links l JOIN native_phase_stat_effects s "
            "ON s.phase=l.phase JOIN effect_abilities e ON e.ability_key=l.special_ability ORDER BY 1")]
        record = {
            'note': 'Model predictions and regression evidence; no live-battle observation or calibration is claimed.',
            'models': {'damage': DAMAGE_MODEL, 'engagement': ENGAGEMENT_MODEL},
            'snapshot': {'source_commit': q.snapshot['source_commit'], 'contract_sha256': q.snapshot['contract_sha256']},
            'runtime': {'python': platform.python_version(), 'sqlite': sqlite3.sqlite_version},
            'damage_cases': [damage_case(q, e, s) for e, s in DAMAGE_CASES],
            'engagement_cases': [engagement_case(q, *case) for case in ENGAGEMENT_CASES],
            'damage_sweep': {'target': TARGET, **sweep(q, keys, lambda k: evaluate_effect_damage(q, k, TARGET))},
            'engagement_sweep': {'units': [TARGET, OPPONENT], 'scenario': MELEE,
                                 'policy': 'recipient a when a phase targets friends/self, else b as enemy',
                                 **sweep(q, stat_keys, lambda k: engagement_for(q, k))},
        }
    args.output.write_bytes((json.dumps(record, indent=2, ensure_ascii=False) + '\n').encode())
    print(json.dumps({k: record[k]['statuses'] for k in ('damage_sweep', 'engagement_sweep')}, indent=1))
    print(json.dumps({k: (record[k]['errors'][:3], record[k]['latency_ms'], record[k]['bytes']) for k in ('damage_sweep', 'engagement_sweep')}))


def engagement_for(q, key):
    phases = q.get_effect(key)['effect']['mechanic']['phases']
    friendly = any(p['target_friends'] or p['target_self'] for p in phases)
    first = next((p['key'] for p in phases), None)
    try:
        return evaluate_effect_engagement(q, key, TARGET, OPPONENT, recipient='a' if friendly else 'b',
                                          relation='friendly' if friendly else 'enemy', scenario=MELEE)
    except Exception:
        raise


if __name__ == '__main__':
    main()
