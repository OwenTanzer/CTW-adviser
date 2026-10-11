"""Issue #20 increment A: single-cast spell/ability damage against one unit."""
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from ctw_adviser.build import build_snapshot
from ctw_adviser.combat import _damage_per_hit
from ctw_adviser.effect_calc import MODEL_VERSION, evaluate_effect_damage
from ctw_adviser.mcp import call_tool
from ctw_adviser.queries import Queries, ResolutionError

SOURCE = Path(os.environ.get('CTW_DATA_ROOT', ROOT.parent / 'CTW-data'))
TARGET = 'Lothern Sea Guard'
COMET = 'wh_main_spell_heavens_comet_of_casandora'          # spell: bombardment -> projectile -> explosion
OVERCAST = COMET + '_upgraded'                             # overcast variant with miscast branch
HELL_HAMMER = 'wh3_dlc23_spell_bound_hell_hammer'           # bound: zero-damage projectile -> explosion (+ vortex)
THIRTEENTH = 'wh2_main_spell_grey_seer_the_dreaded_thirteenth_spell'  # shrapnel x6, shared shrapnel definition
PYROMANIAC = 'wh2_dlc11_character_abilities_pyromaniac'     # non-spell: projectile + explosion + contact phase
FIERY = 'wh2_main_spell_bound_khaines_ring_of_fury'         # vortex-only bound spell
POTION = 'wh2_main_lord_abilities_potion_of_charoi'         # self-only buff, no outward payload
WARPBOMB = 'wh2_main_army_abilities_warpbomb'               # friendly-target ability with damaging contact
TECLIS = 'wh2_main_hef_cha_teclis_0'


@unittest.skipUnless((SOURCE / 'data/unit_stats/dataset_manifest.json').exists() or os.environ.get('CTW_ADVISER_DB'),
                     'pinned CTW-data or CTW_ADVISER_DB required')
class EffectDamageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        if os.environ.get('CTW_ADVISER_DB'):
            cls.db = Path(os.environ['CTW_ADVISER_DB'])
        else:
            cls.db = Path(cls.temp.name) / 'units.sqlite'
            build_snapshot(SOURCE, cls.db)
        cls.q = Queries(cls.db)

    @classmethod
    def tearDownClass(cls):
        cls.q.close()
        cls.temp.cleanup()

    def run_case(self, effect, target=TARGET, **kwargs):
        return evaluate_effect_damage(self.q, effect, target, **kwargs)

    def channels(self, result):
        return [(c['channel'], c['route_role']) for c in result['derived']['components']]

    def test_spell_chain_uses_shared_damage_relation(self):
        result = self.run_case(COMET)
        self.assertEqual(result['status'], 'calculated')
        self.assertEqual(result['model_version'], MODEL_VERSION)
        unit = self.q.get_unit_profile(TARGET, limit=256)['units'][0]
        projectile = next(c for c in result['derived']['components'] if c['channel'] == 'direct_projectile')
        explosion = next(c for c in result['derived']['components'] if c['channel'] == 'explosion')
        expected = _damage_per_hit(864, 864, unit, {'magical': True, 'flaming': False}, 'missile', 'front',
                                   spell=bool(projectile['per_entity']['spell_resistance_applied']))
        self.assertAlmostEqual(projectile['per_entity']['per_unblocked_hit'], expected['per_unblocked_hit'])
        self.assertAlmostEqual(projectile['expected_hits'], 0.5 * (1 - expected['shield_block_probability']))
        # 0 base / 72 AP explosion: AP ignores armour; one assumed entity.
        self.assertAlmostEqual(explosion['expected_damage'], explosion['per_entity']['per_unblocked_hit'])
        totals = result['derived']['totals']
        self.assertAlmostEqual(totals['attempted_damage'], projectile['expected_damage'] + explosion['expected_damage'])
        casualties = totals['casualties']
        self.assertLessEqual(casualties['lower'], casualties['expected_pooled'])
        self.assertLessEqual(casualties['expected_pooled'], casualties['upper'])
        self.assertLessEqual(totals['health_damage_capped'], result['source_facts']['target_health']['health'])

    def test_non_spell_ability_through_same_path(self):
        result = self.run_case(PYROMANIAC, scenario={'contact_phase_ticks': 4})
        self.assertEqual(result['identities']['effect']['effect_kind'], 'activated_ability')
        channels = {c for c, _ in self.channels(result)}
        self.assertTrue({'direct_projectile', 'explosion', 'contact_phase'} <= channels)
        contact = [c for c in result['derived']['components'] if c['channel'] == 'contact_phase']
        self.assertTrue(all(c['expected_damage'] == c['per_application_per_entity_raw'] * c['entities_affected'] * 4
                            for c in contact))
        self.assertTrue(any('protections unverified' in item for item in result['limitations']))

    def test_zero_direct_damage_transport_still_delivers(self):
        result = self.run_case(HELL_HAMMER)
        components = result['derived']['components']
        projectile = next(c for c in components if c['channel'] == 'direct_projectile')
        explosion = next(c for c in components if c['channel'] == 'explosion')
        self.assertEqual(projectile['expected_damage'], 0)
        self.assertGreater(explosion['expected_damage'], 0)
        # The linked vortex is visible and blocks only its own total.
        self.assertEqual(result['status'], 'partial')
        self.assertIn('vortex_application_count_required', [u['code'] for u in result['unresolved_inputs']])
        self.assertAlmostEqual(result['derived']['totals']['attempted_damage'], explosion['expected_damage'])

    def test_overcast_variant_and_failure_branch(self):
        normal, overcast = self.run_case(COMET), self.run_case(OVERCAST)
        self.assertGreater(overcast['derived']['totals']['attempted_damage'], normal['derived']['totals']['attempted_damage'])
        self.assertEqual(overcast['identities']['effect']['ability_key'], OVERCAST)
        self.assertIn('overcast', overcast['identities']['effect']['keywords'])
        branch = overcast['conditional_branches']
        self.assertEqual([b['key'] for b in branch], [{'explosion_key': 'wh_main_heavens_miscast'}])
        self.assertEqual(branch[0]['miscast_chance'], 0.5)
        self.assertFalse(any(c['key'] == {'explosion_key': 'wh_main_heavens_miscast'}
                             for c in overcast['derived']['components']))

    def test_shared_definition_counted_once_with_upper_bound(self):
        result = self.run_case(THIRTEENTH)
        shrapnel = [c for c in result['derived']['components'] if c['key'].get('projectile_key', '').endswith('_shrapnel')]
        self.assertEqual({c['launched'] for c in shrapnel}, {6.0})
        self.assertEqual(sorted(c['route_role'] for c in shrapnel), ['alternate_route', 'nominal'])
        totals = result['derived']['totals']
        nominal = sum(c['expected_damage'] for c in result['derived']['components'] if c['route_role'] == 'nominal')
        self.assertAlmostEqual(totals['attempted_damage'], nominal)
        self.assertGreater(totals['upper_all_routes_attempted_damage'], totals['attempted_damage'])
        self.assertIn('shared_definition_multiplicity', [u['code'] for u in result['unresolved_inputs']])
        self.assertEqual(result['status'], 'partial')

    def test_vortex_requires_explicit_application_counts(self):
        missing = self.run_case(FIERY)
        vortex = missing['derived']['components'][0]
        self.assertIsNone(vortex['expected_damage'])
        self.assertGreater(vortex['per_application_per_entity'], 0)
        self.assertEqual(missing['derived']['totals']['attempted_damage'], 0)
        self.assertFalse(missing['derived']['totals']['complete'])
        supplied = self.run_case(FIERY, scenario={'vortex_entities_per_application': 10, 'vortex_applications': 3})
        self.assertEqual(supplied['status'], 'calculated')
        self.assertAlmostEqual(supplied['derived']['totals']['attempted_damage'], vortex['per_application_per_entity'] * 30)
        doubled = self.run_case(FIERY, scenario={'vortex_entities_per_application': 10, 'vortex_applications': 6})
        self.assertAlmostEqual(doubled['derived']['totals']['attempted_damage'],
                               2 * supplied['derived']['totals']['attempted_damage'])

    def test_recipient_and_range_blocks(self):
        result = self.run_case(POTION)
        self.assertEqual(result['status'], 'blocked')
        self.assertEqual([b['code'] for b in result['blocked']], ['ineligible_recipient'])
        self.assertEqual(result['derived']['totals']['attempted_damage'], 0)
        # Warpbomb is friendly-cast; its contact phase sets affects_enemies=false,
        # so that 2660-damage phase is never counted against an enemy target.
        warpbomb = self.run_case(WARPBOMB)
        self.assertIn({'id': 'wh2_main_unit_contact_kill_self'}, [x['key'] for x in warpbomb['self_effects']])
        self.assertNotIn({'id': 'wh2_main_unit_contact_kill_self'}, [c['key'] for c in warpbomb['derived']['components']])
        self.assertTrue(any(u['kind'] in ('healing', 'stat_modifier') for u in self.run_case(POTION)['unsupported_components']))
        intercept = self.q.get_effect(COMET)['effect']['distances']['target_intercept_range']['value']
        inside = self.run_case(COMET, scenario={'cast_distance_metres': intercept})
        self.assertEqual(inside['range']['status'], 'within')
        beyond = self.run_case(COMET, scenario={'cast_distance_metres': intercept + 1})
        self.assertEqual(beyond['status'], 'blocked')
        self.assertEqual(beyond['range']['status'], 'beyond_target_intercept_range')
        self.assertTrue(all(c['expected_damage'] is None for c in beyond['derived']['components']))

    def test_outward_phase_damage_and_self_damage_split(self):
        leech = self.run_case('wh2_dlc09_spell_death_spirit_leech_bound')
        phase = next(c for c in leech['derived']['components'] if c['channel'] == 'phase_damage')
        self.assertEqual(leech['status'], 'calculated')
        self.assertEqual((phase['per_application_per_entity_raw'], phase['applications'], phase['entities_affected']), (67, 13, 1))
        self.assertEqual(phase['applications_basis'], 'source_implied_duration_over_frequency')
        self.assertEqual(phase['expected_damage'], 67 * 13)
        overridden = self.run_case('wh2_dlc09_spell_death_spirit_leech_bound', scenario={'phase_damage_applications': 5})
        self.assertEqual(overridden['derived']['totals']['attempted_damage'], 67 * 5)
        # Self-cast blast: outward vortex is target damage, the 50-damage self phase is not.
        cellular = self.run_case('wh2_dlc16_unit_abilities_cellular_instability',
                                 scenario={'vortex_entities_per_application': 5, 'vortex_applications': 1})
        self.assertEqual([x['damage_amount'] for x in cellular['self_effects']], [50])
        self.assertEqual({c['channel'] for c in cellular['derived']['components']}, {'vortex'})
        self.assertTrue(any('self/friendly-cast' in item for item in cellular['limitations']))

    def test_caster_access_is_qualified(self):
        linked = self.run_case('Bound Fiery Convocation', caster=TECLIS,
                               scenario={'vortex_entities_per_application': 1, 'vortex_applications': 1})
        self.assertEqual(linked['access']['status'], 'linked')
        self.assertIn('not proof', linked['access']['note'])
        unlinked = self.run_case(COMET, caster=TECLIS)
        self.assertEqual(unlinked['access']['status'], 'not_established')
        self.assertIn('access_not_established', [u['code'] for u in unlinked['unresolved_inputs']])

    def test_sensitivity_and_no_spurious_change(self):
        base = self.run_case(COMET)
        half = self.run_case(COMET, scenario={'projectile_hit_probability': 0.25})
        projectile = lambda r: next(c for c in r['derived']['components'] if c['channel'] == 'direct_projectile')
        self.assertAlmostEqual(projectile(half)['expected_damage'], projectile(base)['expected_damage'] / 2)
        same = self.run_case(COMET, scenario={'projectile_hit_probability': 0.5, 'entities_per_explosion': 1})
        self.assertEqual(json.dumps(same, sort_keys=True), json.dumps(base, sort_keys=True))
        none = self.run_case(COMET, scenario={'projectile_hit_probability': 0, 'entities_per_explosion': 0})
        self.assertEqual(none['derived']['totals']['attempted_damage'], 0)
        disabled = self.run_case(COMET, scenario={'historical_relations_apply_to_patch_9': False})
        self.assertIn('historical_relation_rejected', [u['code'] for u in disabled['unresolved_inputs']])

    def test_base_profiles_unchanged_and_inputs_validated(self):
        before = self.q.get_unit_profile(TARGET, limit=256)
        self.run_case(OVERCAST)
        self.assertEqual(self.q.get_unit_profile(TARGET, limit=256), before)
        for bad in ({'projectile_hit_probability': 1.5}, {'unknown': 1}, {'facing': 'up'},
                    {'barrier_damage_order': 'entity_cap_first'}, {'vortex_applications': float('nan')}):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                self.run_case(COMET, scenario=bad)
        with self.assertRaises(ResolutionError):
            self.run_case('Fiery Convocation')
        with self.assertRaises(ResolutionError):
            self.run_case(COMET, target='Teclis')

    def test_cli_and_mcp_return_the_same_calculation(self):
        scenario = {'projectile_hit_probability': 0.4}
        library = self.run_case(OVERCAST, scenario=scenario)
        env = dict(os.environ, PYTHONPATH=str(ROOT / 'src'))
        cli = subprocess.run([sys.executable, '-m', 'ctw_adviser.cli', 'effect-damage', '--db', str(self.db),
                              OVERCAST, TARGET, '--scenario', json.dumps(scenario)],
                             capture_output=True, text=True, env=env, check=True)
        self.assertEqual(json.loads(cli.stdout), json.loads(json.dumps(library)))
        mcp = call_tool(self.q, 'evaluate_effect_damage', {'effect': OVERCAST, 'target': TARGET, 'scenario': scenario})
        payload = mcp['structuredContent']
        self.assertEqual(payload['model_version'], MODEL_VERSION)
        self.assertEqual(payload['data'], json.loads(json.dumps(library)))
        # Invalid hosted arguments are rejected before dispatch, as for the matchup tool.
        with self.assertRaisesRegex(ValueError, 'hosted range'):
            call_tool(self.q, 'evaluate_effect_damage', {'effect': OVERCAST, 'target': TARGET,
                                                         'scenario': {'projectile_hit_probability': 2}})

    def test_results_keep_cross_references(self):
        result = self.run_case(COMET)
        self.assertEqual(result['identities']['effect_detail_ref'], 'effect:' + COMET)
        self.assertEqual(self.q.resolve_unit(result['identities']['target']['unit_key'])['status'], 'resolved')
        for component in result['derived']['components']:
            self.assertTrue(component['provenance_refs'])
            provenance = self.q.get_provenance(component['provenance_refs'])
            self.assertEqual(len(provenance['records']), len(set(component['provenance_refs'])))
        self.assertEqual(result['snapshot']['commit'], self.q.snapshot['source_commit'])


if __name__ == '__main__':
    unittest.main()
