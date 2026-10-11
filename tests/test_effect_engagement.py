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
        result = self.run_case(HAND_OF_GLORY, recipient='a')
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


if __name__ == '__main__':
    unittest.main()
