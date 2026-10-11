"""Issue #20 increment B: buff/debuff engagement comparison through the #5 model."""
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
from ctw_adviser.combat import evaluate_matchup
from ctw_adviser.effect_engagement import MODEL_VERSION, evaluate_effect_engagement
from ctw_adviser.mcp import call_tool
from ctw_adviser.queries import Queries, ResolutionError

SOURCE = Path(os.environ.get('CTW_DATA_ROOT', ROOT.parent / 'CTW-data'))
A, B = 'Lothern Sea Guard', 'Bloodletters of Khorne'
SCENARIO = {'separation_metres': 40, 'sides': {'a': {'order': 'hold'}, 'b': {'order': 'approach'}}}
HAND_OF_GLORY = 'wh2_main_spell_high_magic_hand_of_glory'          # friendly spell: melee attack +24 (+ reload, unsupported)
WITHER = 'wh2_main_spell_plague_wither'                             # enemy spell: armour -30
SHANTY = 'wh2_dlc11_army_abilities_shanty_verse_1'                  # non-spell friendly: melee defence +20
RALLY = 'wh2_dlc09_character_abilities_tomb_king_rally'             # morale only: not a model input
MANTLE = 'wh2_dlc17_spell_wild_mantle_of_ghorok_upgraded'           # mixed: attack up, armour down
AURA = 'wh2_dlc13_lord_abilities_aura_of_inertia'                   # self-cast, enemy phase debuff
POTION = 'wh2_main_lord_abilities_potion_of_charoi'                 # self-only protection phase


@unittest.skipUnless((SOURCE / 'data/unit_stats/dataset_manifest.json').exists() or os.environ.get('CTW_ADVISER_DB'),
                     'pinned CTW-data or CTW_ADVISER_DB required')
class EffectEngagementTests(unittest.TestCase):
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

    def run_case(self, effect, **kwargs):
        kwargs.setdefault('scenario', SCENARIO)
        return evaluate_effect_engagement(self.q, effect, A, B, **kwargs)

    @staticmethod
    def surv(result, window, side, which):
        row = result['comparisons'][window]['sides']['ab'.index(side)]
        return row['effective_survivability_fraction'][which]

    def test_friendly_spell_buff_hurts_the_enemy(self):
        result = self.run_case(HAND_OF_GLORY, recipient='a')
        changes = result['modifiers']['changed_inputs']
        self.assertEqual([(c['path'], c['after'] - c['before']) for c in changes], [('melee.attack', 24.0)])
        self.assertEqual([u['stat_token'] for u in result['modifiers']['unsupported'] if 'stat_token' in u], ['stat_reloading'])
        self.assertEqual(result['window']['basis'], 'active_window')
        self.assertLess(self.surv(result, 'active_window', 'b', 'with'), self.surv(result, 'active_window', 'b', 'without'))
        self.assertEqual(self.surv(result, 'active_window', 'a', 'with'), self.surv(result, 'active_window', 'a', 'without'))
        self.assertEqual(result['status'], 'partial')

    def test_enemy_debuff_applies_to_target_side_only(self):
        result = self.run_case(WITHER, recipient='b', relation='enemy')
        self.assertEqual([(c['path'], c['before'], c['after']) for c in result['modifiers']['changed_inputs']],
                         [('protection.armour', 35.0, 5.0)])
        self.assertLess(self.surv(result, 'active_window', 'b', 'with'), self.surv(result, 'active_window', 'b', 'without'))
        self.assertEqual(self.surv(result, 'active_window', 'a', 'with'), self.surv(result, 'active_window', 'a', 'without'))
        wrong = self.run_case(WITHER, recipient='b', relation='friendly')
        self.assertEqual([b['code'] for b in wrong['blocked']], ['ineligible_recipient'])
        self.assertEqual(wrong['comparisons'], {})

    def test_enemy_phase_can_radiate_from_self_cast(self):
        result = self.run_case(AURA, recipient='b', relation='enemy')
        self.assertNotEqual(result['status'], 'blocked')
        self.assertTrue(result['recipient_flags']['target_enemies'])
        self.assertIn('outward_phase_geometry_unresolved', [u['code'] for u in result['unresolved_inputs']])
        self.assertTrue(result['modifiers']['changed_inputs'])

    def test_self_only_phase_requires_matching_caster(self):
        missing = self.run_case(POTION, recipient='a')
        self.assertIn('self_only_caster_required', [b['code'] for b in missing['blocked']])
        self.assertEqual(missing['comparisons'], {})
        mismatch = self.run_case(POTION, recipient='a', caster='wh2_dlc15_hef_cha_teclis_2')
        self.assertIn('self_only_recipient_mismatch', [b['code'] for b in mismatch['blocked']])
        self.assertEqual(mismatch['comparisons'], {})
        self.assertEqual(mismatch['modifiers']['changed_inputs'], [])

    def test_later_stage_start_is_unresolved(self):
        result = self.run_case('wh3_dlc23_hero_abilities_crooked_dice',
                               phase='wh3_dlc23_hero_abilities_crooked_dice_iii', recipient='a')
        self.assertEqual(result['window']['phase_order'], 3)
        self.assertIsNone(result['window']['start_seconds'])
        self.assertEqual(result['window']['comparison_origin'], 'selected_phase_onset')
        self.assertIn('phase_start_unresolved', [u['code'] for u in result['unresolved_inputs']])

    def test_non_spell_ability_through_same_path(self):
        result = self.run_case(SHANTY, recipient='a')
        self.assertEqual(result['identities']['effect']['effect_kind'], 'activated_ability')
        self.assertEqual([c['path'] for c in result['modifiers']['changed_inputs']], ['melee.defence'])
        self.assertGreater(self.surv(result, 'active_window', 'a', 'with'), self.surv(result, 'active_window', 'a', 'without'))

    def test_inverse_effects_are_not_flipped(self):
        result = self.run_case(MANTLE, recipient='a')
        paths = {c['path']: c for c in result['modifiers']['changed_inputs']}
        self.assertLess(paths['protection.armour']['after'], paths['protection.armour']['before'])
        self.assertGreater(paths['melee.attack']['after'], paths['melee.attack']['before'])
        self.assertAlmostEqual(paths['melee.base_damage']['after'], paths['melee.base_damage']['before'] * 1.5)
        # Lower armour costs A survivability even as the attack buff damages B.
        self.assertLess(self.surv(result, 'active_window', 'a', 'with'), self.surv(result, 'active_window', 'a', 'without'))
        self.assertLess(self.surv(result, 'active_window', 'b', 'with'), self.surv(result, 'active_window', 'b', 'without'))

    def test_unsupported_only_effect_blocks(self):
        result = self.run_case(RALLY, recipient='a')
        self.assertEqual(result['status'], 'blocked')
        self.assertEqual([b['code'] for b in result['blocked']], ['no_supported_modifier'])
        self.assertEqual([u['stat_token'] for u in result['modifiers']['unsupported'] if 'stat_token' in u], ['stat_morale'])

    def test_window_expiry_and_shared_baseline(self):
        result = self.run_case(HAND_OF_GLORY, recipient='a', include_matchups=True)
        window = result['matchups']['active_window']
        duration = result['window']['phase_duration']
        self.assertLess(duration, result['window']['horizon_seconds'])
        for run in window.values():
            self.assertEqual(run['scenario_assumptions']['duration_seconds'], duration)
        horizon = result['matchups']['horizon']
        self.assertEqual(horizon['without']['scenario_assumptions'], horizon['with']['scenario_assumptions'])
        # The unmodified run is exactly the standalone #5 result.
        direct = evaluate_matchup(self.q, A, B, scenario=SCENARIO)
        self.assertEqual(json.dumps(horizon['without'], sort_keys=True), json.dumps(direct, sort_keys=True))
        # Source facts in the modified run still report base profiles.
        self.assertEqual(horizon['with']['source_facts'], horizon['without']['source_facts'])
        covers = self.run_case(HAND_OF_GLORY, recipient='a', scenario={**SCENARIO, 'duration_seconds': duration})
        self.assertEqual(covers['window']['basis'], 'covers_horizon')
        self.assertEqual(set(covers['comparisons']), {'horizon'})

    def test_compact_default_fits_response_budget(self):
        prince = 'wh3_main_dae_cha_daemon_prince_0'
        compact = evaluate_effect_engagement(self.q, HAND_OF_GLORY, prince, B, scenario=SCENARIO)
        full = evaluate_effect_engagement(self.q, HAND_OF_GLORY, prince, B, scenario=SCENARIO, include_matchups=True)
        self.assertLess(len(json.dumps(compact)), 64 * 1024)
        self.assertGreater(len(json.dumps(full)), len(json.dumps(compact)))
        # Compact and full agree on every comparison number and verdict.
        self.assertEqual(compact['comparisons'], full['comparisons'])
        for name, pair in full['matchups'].items():
            for which in ('without', 'with'):
                self.assertEqual(compact['matchups'][name][which]['verdict']['represented_point_ordering'],
                                 pair[which]['verdict']['represented_point_ordering'])
        corners = compact['comparisons']['horizon']['sensitivity']['collision_corners']
        self.assertEqual(len(corners), 4)

    def test_zero_modifier_does_not_change_result(self):
        import ctw_adviser.effect_engagement as module
        original = module._apply
        module._apply = lambda unit, mods: original(unit, [dict(m, value=0.0 if m['operation'] == 'add' else 1.0) for m in mods])
        try:
            result = self.run_case(HAND_OF_GLORY, recipient='a')
        finally:
            module._apply = original
        for comparison in result['comparisons'].values():
            for row in comparison['sides']:
                self.assertEqual(row['effective_survivability_fraction']['delta'], 0)

    def test_base_profiles_unchanged_and_inputs_validated(self):
        before = copy.deepcopy(self.q.get_matchup_evidence(A, B, limit=256))
        self.run_case(MANTLE, recipient='a')
        self.assertEqual(self.q.get_matchup_evidence(A, B, limit=256), before)
        for kwargs in ({'recipient': 'c'}, {'relation': 'ally'}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                self.run_case(HAND_OF_GLORY, **kwargs)
        with self.assertRaises(ResolutionError):
            self.run_case('Fiery Convocation')
        unknown = self.run_case(HAND_OF_GLORY, phase='no_such_phase')
        self.assertEqual([b['code'] for b in unknown['blocked']], ['unknown_phase'])

    def test_cli_and_mcp_match_library(self):
        library = self.run_case(WITHER, recipient='b', relation='enemy')
        env = dict(os.environ, PYTHONPATH=str(ROOT / 'src'))
        cli = subprocess.run([sys.executable, '-m', 'ctw_adviser.cli', 'effect-engagement', '--db', str(self.db),
                              WITHER, A, B, '--recipient', 'b', '--relation', 'enemy', '--scenario', json.dumps(SCENARIO)],
                             capture_output=True, text=True, env=env, check=True)
        self.assertEqual(json.loads(cli.stdout), json.loads(json.dumps(library)))
        mcp = call_tool(self.q, 'evaluate_effect_engagement', {'effect': WITHER, 'unit_a': A, 'unit_b': B,
                                                              'recipient': 'b', 'relation': 'enemy', 'scenario': SCENARIO})
        self.assertEqual(mcp['structuredContent']['model_version'], MODEL_VERSION)
        self.assertEqual(mcp['structuredContent']['data'], json.loads(json.dumps(library)))


    def test_end_to_end_from_unit_activated_options(self):
        crone = 'wh2_dlc10_def_cha_crone_0'
        packet = self.q.get_unit_profile(crone, limit=256)
        option = next(o for o in packet['units'][0]['activated_options']
                      if o['key'] == 'wh2_dlc10_lord_abilities_gaze_of_khaine')
        self.assertIn('stat_modifier', option['keywords'])
        effect = self.q.get_detail(option['detail_ref'])['effect']
        from_unit = evaluate_effect_engagement(self.q, effect['identity']['ability_key'], crone, B,
                                               recipient='a', caster=crone, scenario=SCENARIO)
        from_name = evaluate_effect_engagement(self.q, 'wh2_dlc10_lord_abilities_gaze_of_khaine', crone, B,
                                               recipient='a', caster=crone, scenario=SCENARIO)
        self.assertEqual(from_unit, from_name)
        self.assertEqual(from_unit['access']['status'], 'linked')
        self.assertEqual(from_unit['identities']['units'][0]['unit_key'], crone)
        paths = {c['path']: c for c in from_unit['modifiers']['changed_inputs']}
        self.assertEqual(paths['melee.attack']['after'] - paths['melee.attack']['before'], 24.0)
        self.assertAlmostEqual(paths['melee.base_damage']['after'], paths['melee.base_damage']['before'] * 1.25)

    def test_replacement_is_reported_not_stacked(self):
        waaagh = 'wh2_dlc15_army_abilities_azhags_big_waaagh'
        result = self.run_case(waaagh, recipient='a')
        self.assertIn('wh2_dlc15_army_abilities_azhags_waaagh', result['replacement']['supersedes'])
        own = {(m['stat_token'], m['operation'], m['value']) for m in result['modifiers']['applied']}
        superseded = self.q.get_effect('wh2_dlc15_army_abilities_azhags_waaagh')['effect']['mechanic']['effects']
        # Changed inputs come only from the selected effect's own phase rows.
        self.assertTrue(result['modifiers']['changed_inputs'])
        self.assertTrue(all(c['stat_token'] in {m[0] for m in own} for c in result['modifiers']['changed_inputs']))
        # Each supported own modifier changes each mapped field exactly once (no stacking with superseded rows).
        applied = [c for c in result['modifiers']['changed_inputs'] if c['status'] == 'applied']
        self.assertEqual(len(applied), len({(c['stat_token'], c['path'], c.get('attack_ref')) for c in applied}))
        self.assertTrue(superseded)

    def test_overcast_duration_and_held_out_spell(self):
        normal = self.run_case('wh2_dlc14_spell_ruin_flensing_ruin', recipient='b', relation='enemy')
        overcast = self.run_case('wh2_dlc14_spell_ruin_flensing_ruin_upgraded', recipient='b', relation='enemy')
        self.assertEqual((normal['window']['phase_duration'], overcast['window']['phase_duration']), (22.0, 34.0))
        self.assertEqual(normal['modifiers']['applied'][0]['value'], overcast['modifiers']['applied'][0]['value'])
        self.assertIn('wh2_dlc14_spell_ruin_flensing_ruin_upgraded',
                      [v['ability_key'] for v in normal['variants'] if v['relation'] == 'overcast_option'])
        held_out = self.run_case('wh2_dlc10_spell_bound_soulblight', recipient='b', relation='enemy')
        paths = {c['path'] for c in held_out['modifiers']['changed_inputs']}
        self.assertEqual(paths, {'protection.armour', 'melee.ap_damage', 'melee.base_damage'})
        a_side, b_side = held_out['comparisons']['active_window']['sides']
        # Debuffed enemy (lower armour) takes more damage; its weaker melee hurts the friendly side less.
        self.assertGreater(b_side['incoming_attempted_damage']['delta'], 0)
        self.assertLess(b_side['effective_survivability_fraction']['delta'], 0)
        self.assertLess(a_side['incoming_attempted_damage']['delta'], 0)

    def test_wrong_variant_and_incompatible_evidence(self):
        effect = 'wh2_dlc12_unit_abilities_burning_alignment'
        linked = self.run_case(effect, recipient='b', relation='enemy', caster='wh2_dlc12_lzd_cha_skink_priest_beasts_4')
        other_form = self.run_case(effect, recipient='b', relation='enemy', caster='wh2_main_lzd_cha_skink_priest_beasts_0')
        self.assertEqual(linked['access']['status'], 'linked')
        self.assertEqual(other_form['access']['status'], 'not_established')
        with self.assertRaises(ResolutionError):
            evaluate_effect_engagement(self.q, HAND_OF_GLORY, A, B, subculture_a='wh_main_sc_emp_empire', scenario=SCENARIO)
        from unittest.mock import patch
        original = self.q.get_effect
        def stale(*args, **kwargs):
            packet = original(*args, **kwargs)
            packet['snapshot'] = dict(packet['snapshot'], commit='0' * 40)
            return packet
        with patch.object(self.q, 'get_effect', stale), self.assertRaisesRegex(ValueError, 'different snapshots'):
            self.run_case(HAND_OF_GLORY, recipient='a')


    def test_out_of_domain_modifier_is_clamped_and_flagged(self):
        # Found by the full-inventory sweep: this debuff drives armour below zero.
        result = self.run_case('wh2_dlc09_character_abilities_curse_of_khsar', recipient='b', relation='enemy')
        clamped = [c for c in result['modifiers']['changed_inputs'] if c['status'] == 'clamped']
        self.assertTrue(clamped)
        for change in clamped:
            self.assertEqual(change['after'], 0.0)
            self.assertLess(change['unclamped'], 0)
        self.assertIn('modifier_clamped', [u['code'] for u in result['unresolved_inputs']])
        self.assertTrue(result['comparisons'])


if __name__ == '__main__':
    unittest.main()
