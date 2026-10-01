"""Runtime retrieval checks against a freshly built pinned store."""
from contextlib import closing
import csv
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
sys.path.insert(0, str(ROOT / 'scripts'))
from ctw_adviser.build import build_snapshot
from ctw_adviser.queries import Queries, ResolutionError, RESEARCHED_PASSIVES, MURDEROUS_INDICATOR, MURDEROUS_BUFFS
from validate_packets import validate, packet_checks

SOURCE = Path(os.environ.get('CTW_DATA_ROOT', ROOT.parent / 'CTW-data'))


@unittest.skipUnless((SOURCE / 'data/unit_stats/dataset_manifest.json').exists(), 'pinned CTW-data required')
class QueryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.output = Path(cls.temp.name) / 'units.sqlite'
        build_snapshot(SOURCE, cls.output)
        cls.q = Queries(cls.output)
        cls.schema = json.loads((ROOT / 'schema/evidence_packet.schema.json').read_text())

    @classmethod
    def tearDownClass(cls):
        cls.q.close()
        cls.temp.cleanup()

    def check(self, packet):
        validate(packet, self.schema, self.schema)
        packet_checks(packet)
        return packet['units'][0]

    def test_murderous_indicator_consolidation_is_lossless_and_qualified(self):
        links = self.q.rows('unit_abilities', 'ability_key', MURDEROUS_INDICATOR)
        self.assertEqual(len(links), 115)
        for link in links:
            packet = self.q.get_unit_profile(link['unit_key'], section='abilities', limit=256)
            unit = self.check(packet)
            abilities = unit['passives']['abilities']
            self.assertNotIn(MURDEROUS_INDICATOR, {m['key'] for m in abilities})
            matched = [m for m in abilities if m['key'] in MURDEROUS_BUFFS and m['culture_key'] == link['culture_key']]
            self.assertEqual(len(matched), 1)
            self.assertIn(link['record_id'], matched[0]['provenance_refs'])
            original = self.q.get_passive_detail(matched[0]['key'])['mechanic']
            for field in ('effects', 'conditions', 'phases', 'native_parameters', 'summary'):
                self.assertEqual(matched[0][field], original[field])
            coverage = next(c for c in unit['coverage']['sections'] if c['name'] == 'abilities')
            self.assertEqual(coverage['total'], len(abilities))
        key = links[0]['unit_key']
        paged = []
        cursor = None
        while True:
            packet = self.q.get_unit_profile(key, section='abilities', limit=1, cursor=cursor)
            paged += [m['key'] for m in self.check(packet)['passives']['abilities']]
            cursor = next(c for c in packet['units'][0]['coverage']['sections'] if c['name'] == 'abilities')['cursor']
            if not cursor:
                break
        self.assertNotIn(MURDEROUS_INDICATOR, paged)
        self.assertEqual(len(paged), len(set(paged)))
        # If a future source has no equally qualified counterpart, retain it.
        rows = self.q.rows
        def without_buff(table, field, value, order='record_id'):
            result = rows(table, field, value, order)
            return [r for r in result if r['ability_key'] not in MURDEROUS_BUFFS] if table == 'unit_abilities' and field == 'unit_key' else result
        with patch.object(self.q, 'rows', side_effect=without_buff):
            packet = self.q.get_unit_profile(key, section='abilities', limit=256)
            self.assertIn(MURDEROUS_INDICATOR, {m['key'] for m in self.check(packet)['passives']['abilities']})
        self.assertEqual(self.q.get_passive_detail(MURDEROUS_INDICATOR)['mechanic']['key'], MURDEROUS_INDICATOR)

    def test_researched_passives_keep_values_recipients_and_optional_documentation(self):
        self.assertEqual(len(RESEARCHED_PASSIVES), 25)
        for key in RESEARCHED_PASSIVES:
            with self.subTest(key=key):
                detail = self.q.get_passive_detail(key)
                self.assertNotIn('explanation_documentation', detail)
                documented = self.q.get_passive_detail(key, include_documentation=True)
                self.assertIn('explanation_documentation', documented)
                self.assertEqual(detail['mechanic'], documented['mechanic'])
                link = self.q.rows('unit_abilities', 'ability_key', key)[0]
                packet = self.q.get_unit_profile(link['unit_key'], section='abilities', limit=256)
                self.check(packet)
        lucky = self.q.get_passive_detail('wh3_dlc23_hero_passive_lucky_git')['mechanic']
        heal = next(e for e in lucky['effects'] if e['kind'] == 'healing')
        self.assertEqual(heal['native_parameters']['heal_amount'], 0.006)
        self.assertEqual(heal['native_parameters']['hp_change_frequency'], 1.5)
        feast = self.q.get_passive_detail('wh3_dlc25_lord_passive_feast_of_the_maggot_lord')['mechanic']
        self.assertEqual([p['target_self'] for p in feast['phases']], [True, False])
        self.assertEqual([p['target_enemies'] for p in feast['phases']], [False, True])
        self.assertEqual(feast['conditions']['activates_when'][0]['key'], 'tamurkhan_death')
        mirror = self.q.get_passive_detail('wh3_twa08_unit_passive_redirecting_aura')['mechanic']
        self.assertEqual(mirror['native_parameters']['effect_range'], 55)
        self.assertTrue(mirror['phases'][0]['target_enemies'])
        self.assertFalse(mirror['phases'][0]['target_self'])

    def test_researched_damage_payloads_preserve_shared_definitions(self):
        detail = self.q.get_passive_detail('wh2_dlc15_unit_passive_rubble_and_ruin_tier_1_bombardment')
        link = self.q.rows('unit_abilities', 'ability_key', detail['mechanic']['key'])[0]
        packet = self.q.get_unit_profile(link['unit_key'], section='abilities', limit=256)
        self.check(packet)
        tiers = [m for m in packet['units'][0]['passives']['abilities']
                 if 'rubble_and_ruin_tier_' in m['key'] and m['key'].endswith('_bombardment')]
        self.assertEqual(len(tiers), 3)
        roots = [next(e['node_ref'] for e in m['effects'] if e['kind'] == 'payload_reference') for m in tiers]
        self.assertEqual(len(set(roots)), 1)
        self.assertEqual(sum(n['id'] == roots[0] for n in packet['payload_graph']['nodes']), 1)
        self.assertEqual({m['conditions']['deactivates_when'][0]['key'] for m in tiers},
                         {'health_above_75%', 'health_above_50%', 'health_above_25%'})
        for key in ('wh2_main_faction_abilities_murderous_prowess_indicator',):
            self.assertNotIn(key, RESEARCHED_PASSIVES)
            self.assertNotIn('explanation_documentation', self.q.get_passive_detail(key, include_documentation=True))

    def test_lightning_strike_targeting_and_damage_stay_separate(self):
        key = 'wh3_dlc29_passive_spell_lightning_strike'
        detail = self.q.get_passive_detail(key)
        m = detail['mechanic']; c = m['native_parameters']
        self.assertTrue(c['target_enemies'])
        self.assertFalse(c['target_ground'])
        self.assertFalse(c['target_self'])
        self.assertEqual((c['target_intercept_range'], c['recharge_time'], c['active_time'], c['shared_recharge_time']), (40, 10, 4, 5))
        self.assertTrue(all(not conditions for conditions in m['conditions'].values()))
        nodes = {n['kind']: n for n in detail['payload_graph']['nodes']}
        self.assertEqual(set(nodes), {'native_bombardments', 'projectiles', 'explosions'})
        bombardment = nodes['native_bombardments']['native_parameters']
        self.assertEqual((bombardment['launch_source'], bombardment['num_projectiles'], bombardment['radius_spread']), ('above_target', 1, 1))
        for kind in ('projectiles', 'explosions'):
            params = nodes[kind]['native_parameters']
            self.assertEqual((params['base_damage'], params['ap_damage']), (0, 18))
            self.assertTrue(params['is_magical'])
        self.assertTrue(nodes['projectiles']['native_parameters']['can_damage_allies'])
        self.assertTrue(nodes['explosions']['native_parameters']['affects_allies'])
        self.assertEqual(nodes['explosions']['native_parameters']['radius'], 8)
        edges = detail['payload_graph']['edges']
        self.assertTrue(any(e['from'] == nodes['projectiles']['id'] and e['to'] == nodes['explosions']['id'] for e in edges))
        packet = self.q.get_unit_profile('wh3_dlc29_emp_veh_celestial_hurricanum_0', limit=256)
        self.check(packet)
        self.assertIn('actual hit counts remain unverified', m['summary'])
        self.assertNotIn('explanation_documentation', detail)

    def test_reviewed_explanations_keep_calculation_payloads_separate(self):
        corpse_packet = self.q.get_unit_profile('wh2_dlc11_cst_mon_bloated_corpse_0')
        corpse = self.check(corpse_packet)
        self.assertEqual(corpse['melee']['base_damage'], 150)
        self.assertEqual(corpse['melee']['ap_damage'], 300)
        abilities = {m['key']: m for m in corpse['passives']['abilities']}
        self.assertIn('Corpse itself', abilities['wh2_dlc11_unit_passive_gaseous_demise']['summary'])
        routes = [next(e['node_ref'] for e in abilities[k]['effects'] if e['kind'] == 'payload_reference') for k in
                  ('wh2_dlc11_unit_passive_gaseous_demise', 'wh2_dlc11_unit_passive_noxious_unstable_mark_ii')]
        self.assertEqual(routes[0], routes[1])
        blasts = [n for n in corpse_packet['payload_graph']['nodes'] if n['id'] == routes[0]]
        self.assertEqual(len(blasts), 1)
        self.assertEqual(blasts[0]['native_parameters']['damage_ap'], 72)
        self.assertTrue(blasts[0]['native_parameters']['affects_allies'])
        squig_packet = self.q.get_unit_profile('wh_twa03_def_inf_squig_explosive_0')
        squig = self.check(squig_packet)
        self.assertIsNone(squig['ranged'])
        graph = squig_packet['payload_graph']
        projectile = next(n for n in graph['nodes'] if n['kind'] == 'projectiles')
        blast = next(n for n in graph['nodes'] if n['kind'] == 'explosions')
        self.assertEqual(projectile['native_parameters']['base_damage'], 0)
        self.assertEqual(projectile['native_parameters']['ap_damage'], 0)
        self.assertEqual(blast['native_parameters']['base_damage'], 100)
        self.assertEqual(blast['native_parameters']['ap_damage'], 200)
        self.assertTrue(any(e['from'] == projectile['id'] and e['to'] == blast['id'] for e in graph['edges']))
        detail = self.q.get_passive_detail('wh2_main_unit_passive_too_horrible_to_die')
        contact = next(n for n in detail['payload_graph']['nodes'] if n['kind'] == 'native_ability_phases')
        self.assertEqual(contact['native_parameters']['damage_amount'], 6650)
        self.assertFalse(contact['native_parameters']['affects_enemies'])
        self.assertNotIn('gaps', detail)
        self.assertNotIn('source_path', contact['native_parameters'])

    def test_abomination_failure_branch_is_conditional_and_separate(self):
        unit = self.check(self.q.get_unit_profile('wh2_main_skv_mon_hell_pit_abomination'))
        abilities = {m['key']: m for m in unit['passives']['abilities']}
        ability = abilities['wh2_main_unit_passive_too_horrible_to_die']
        branches = [e for e in ability['effects'] if 'failure_context' in e]
        self.assertEqual(len(branches), 1)
        f = branches[0]['failure_context']
        self.assertEqual(f['miscast_chance'], 0.5)
        self.assertEqual(f['explosion_base_damage'] + f['explosion_ap_damage'], 0)
        self.assertEqual(f['contact_damage_amount'], 6650)
        self.assertFalse(f['contact_affects_enemies'])
        self.assertIn('Failure chance: 50%', ability['summary'])
        self.assertIn('death summon is a separate mechanic', ability['summary'])
        self.assertFalse(any(e['kind'] == 'periodic_damage' for e in ability['effects']))
        rats = abilities['wh2_main_unit_passive_the_rats_emerge']
        self.assertFalse(any('failure_context' in e for e in rats['effects']))
        self.assertTrue(any(e.get('trigger') == 'on_death' for e in rats['effects']))

    def test_survival_family_preserves_different_sequences_and_conditional_damage(self):
        cases = {
            'wh2_dlc15_unit_passive_fiery_rebirth': (0.25, 2, True),
            'wh2_main_unit_passive_rebirth': (0.25, 2, False),
            'wh2_pro08_character_passive_heroic_fortitude': (0.12, 1, False),
            'wh3_main_daemon_body_passive_restore_the_blighted': (0.25, 2, False),
        }
        for key, (healing, phase_count, blast) in cases.items():
            with self.subTest(key=key):
                detail = self.q.get_passive_detail(key)
                m = detail['mechanic']
                self.assertEqual(len(m['phases']), phase_count)
                self.assertEqual(next(e for e in m['effects'] if e['kind'] == 'healing')['native_parameters']['heal_amount'], healing)
                failure = [e for e in m['effects'] if 'failure_context' in e]
                self.assertEqual(len(failure), 1)
                f = failure[0]['failure_context']
                self.assertEqual(f['miscast_chance'], 0.5)
                self.assertEqual(f['explosion_base_damage'] + f['explosion_ap_damage'], 0)
                self.assertEqual(f['contact_damage_amount'], 6650)
                self.assertFalse(f['contact_affects_enemies'])
                self.assertFalse(any(e['kind'] == 'periodic_damage' for e in m['effects']))
                self.assertEqual(any(n['kind'] == 'native_vortices' for n in detail['payload_graph']['nodes']), blast)
                self.assertIn('Failure chance: 50%', m['summary'])
                self.assertEqual(m['requires_effect_enabling'], key.endswith('restore_the_blighted'))
                unit_key = self.q.rows('unit_abilities', 'ability_key', key)[0]['unit_key']
                self.check(self.q.get_unit_profile(unit_key, limit=128))

    def test_death_payloads_explain_entity_scope_and_retain_contact_modifiers(self):
        from ctw_adviser.queries import DEATH_PAYLOAD_PASSIVES
        whole_unit = {'wh3_dlc25_unit_passive_abandon_ship', 'wh3_dlc27_unit_passive_split_up', 'wh3_dlc29_unit_passive_curse_of_the_fallen'}
        for key in DEATH_PAYLOAD_PASSIVES:
            with self.subTest(key=key):
                detail = self.q.get_passive_detail(key)
                m = detail['mechanic']; graph = detail['payload_graph']
                event = m['conditions']['activates_when'][0]
                self.assertEqual(event['key'], 'vortex_on_death' if key in whole_unit else 'vortex_on_entity_death')
                self.assertGreaterEqual(len(event['provenance_refs']), 2)
                self.assertTrue(any(n['kind'] == 'native_vortices' for n in graph['nodes']))
                self.assertFalse(any('failure_context' in e for e in m['effects']))
                self.assertNotIn('While active: linked', m['summary'])
                unit_key = self.q.rows('unit_abilities', 'ability_key', key)[0]['unit_key']
                self.check(self.q.get_unit_profile(unit_key))
        d = self.q.get_passive_detail('wh3_dlc29_unit_passive_pestilent_perfection')
        effect = next(n for n in d['payload_graph']['nodes'] if n['kind'] == 'native_phase_stat_effects')
        self.assertEqual(effect['native_parameters']['stat'], 'stat_morale')
        self.assertEqual(effect['native_parameters']['value'], -10)
        self.assertTrue(any(e['to'] == effect['id'] and e['relationship'] == 'phase_effect' for e in d['payload_graph']['edges']))
        self.assertIn('leadership -10', d['mechanic']['summary'])

    def test_split_up_keeps_low_health_summon_separate_from_death_blast(self):
        packet = self.q.get_unit_profile('wh3_dlc27_hef_mon_sea_elemental')
        unit = self.check(packet)
        abilities = {m['key']: m for m in unit['passives']['abilities']}
        death = abilities['wh3_dlc27_unit_passive_split_up']
        summon = abilities['wh3_dlc27_unit_passive_split_up_hidden']
        self.assertFalse(any(e['kind'] == 'summon' for e in death['effects']))
        spawn = next(e for e in summon['effects'] if e['kind'] == 'summon')
        self.assertEqual(spawn['unit_name'], 'Oceanids')
        self.assertNotEqual(spawn['trigger'], 'on_death')
        self.assertIn('25%', spawn['trigger_basis'])
        self.assertEqual(summon['conditions']['activates_when'], [])
        self.assertEqual(summon['conditions']['deactivates_when'][0]['key'], 'health_above_25%')
        pulses = [n['native_parameters'] for n in packet['payload_graph']['nodes'] if n['kind'] == 'native_vortices']
        self.assertEqual(sorted(n['damage'] for n in pulses), [0, 50])
        self.assertTrue(all(n['detonation_force'] == 350 for n in pulses))

    def test_death_gate_blasts_keep_contact_debuffs_and_self_damage_separate(self):
        for key, damage, ap in [('wh2_dlc13_unit_passive_kaboom', 10, 8),
                                ('wh3_dlc26_unit_abilities_blow_apart', 10, 20)]:
            with self.subTest(key=key):
                detail = self.q.get_passive_detail(key)
                m = detail['mechanic']; nodes = detail['payload_graph']['nodes']
                self.assertEqual(m['conditions']['activates_when'][0]['key'], 'on_death')
                self.assertIn('reviewed interpretation', m['conditions']['activates_when'][0]['summary'])
                vortex = next(n['native_parameters'] for n in nodes if n['kind'] == 'native_vortices')
                self.assertEqual((vortex['damage'], vortex['damage_ap']), (damage, ap))
                self.assertTrue(vortex['affects_allies'])
                modifiers = {n['native_parameters']['stat']: n['native_parameters']['value'] for n in nodes if n['kind'] == 'native_phase_stat_effects'}
                self.assertEqual(modifiers['stat_morale'], -8)
                if key.endswith('blow_apart'):
                    self.assertEqual(modifiers['scalar_speed'], 0.85)
                    self.assertTrue(m['phases'][0]['target_self'])
                    self.assertEqual(next(e for e in m['effects'] if e['kind'] == 'periodic_damage')['native_parameters']['damage_amount'], 26600)
                else:
                    self.assertFalse(any(e['kind'] == 'periodic_damage' for e in m['effects']))
                self.check(self.q.get_unit_profile(self.q.rows('unit_abilities', 'ability_key', key)[0]['unit_key']))

    def test_summons_preserve_host_versus_enemy_conditions_and_placement_uncertainty(self):
        cases = [('wh3_dlc29_lord_passive_arch_necromancer', 'Wight King', 1, 'unit_is_not_commander_class'),
                 ('wh3_dlc29_lord_passive_liche_ascendant', 'Zombies', 2, 'unit_is_commander_class'),
                 ('wh_dlc05_lord_abilities_spirit_essence_of_chaos', 'Chaos Spawn', 1, 'unit_is_commander_class')]
        for key, name, uses, excluded_class in cases:
            with self.subTest(key=key):
                m = self.q.get_passive_detail(key)['mechanic']
                summon = next(e for e in m['effects'] if e['kind'] == 'summon')
                self.assertEqual((summon['unit_name'], summon['num_uses']), (name, uses))
                self.assertEqual(summon['trigger'], 'unresolved')
                self.assertIn('whether summoning requires a kill', m['summary'])
                self.assertNotIn('at the host position', m['summary'])
                self.assertIn('caster-versus-target', summon['trigger_basis'])
                self.assertEqual(m['conditions']['deactivates_when'], [])
                self.assertIn(excluded_class, [c['key'] for c in m['conditions']['invalid_targets']])
                self.assertTrue(m['phases'][0]['target_enemies'])
                self.assertFalse(m['phases'][0]['target_self'])
                self.check(self.q.get_unit_profile(self.q.rows('unit_abilities', 'ability_key', key)[0]['unit_key'], limit=128))
        key = 'wh2_dlc11_unit_passive_abandon_ship'
        m = self.q.get_passive_detail(key)['mechanic']
        self.assertTrue(m['phases'][0]['target_self'])
        self.assertEqual(m['conditions']['deactivates_when'][0]['key'], 'health_above_50%')
        self.assertIn('50% host health', m['summary'])
        self.assertNotEqual(next(e for e in m['effects'] if e['kind'] == 'summon')['trigger'], 'on_death')
        self.check(self.q.get_unit_profile(self.q.rows('unit_abilities', 'ability_key', key)[0]['unit_key']))

    def test_exploding_unit_is_source_backed_visual_indicator(self):
        key = 'wh2_dlc15_unit_abilities_exploding_unit'
        detail = self.q.get_passive_detail(key, include_diagnostics=True)
        mechanic = detail['mechanic']
        self.assertEqual([e['kind'] for e in mechanic['effects']], ['visual_indicator'])
        effect = mechanic['effects'][0]
        self.assertIn('banner visual effect', mechanic['summary'])
        self.assertTrue(any('unit_abilities_tooltip_text_' + key in str(detail['provenance'][r]) for r in effect['provenance_refs']))
        self.assertFalse(any(g['code'] == 'phase_effect_unknown' for g in detail['gaps']))
        link = self.q.rows('unit_abilities', 'ability_key', key)[0]
        self.check(self.q.get_unit_profile(link['unit_key']))
        other = self.q.get_passive_detail('wh2_main_faction_abilities_murderous_prowess_indicator', include_diagnostics=True)
        self.assertTrue(any(g['code'] == 'phase_effect_unknown' for g in other['gaps']))

    def test_death_summons_expose_existing_casting_evidence(self):
        cases = (
            ('wh2_main_unit_passive_the_rats_emerge', 'wh2_main_skv_inf_skavenslave_spearmen_0_summoned'),
            ('wh3_dlc25_unit_passive_nurgling_emergence', 'wh3_dlc25_nur_inf_nurglings_summoned'),
        )
        for key, spawned in cases:
            detail = self.q.get_passive_detail(key, include_diagnostics=True)
            mechanic = detail['mechanic']
            summon = next(e for e in mechanic['effects'] if e['kind'] == 'summon')
            self.assertEqual(summon['unit_key'], spawned)
            self.assertEqual(summon['trigger'], 'on_death')
            self.assertEqual(summon['spawn_type'], 'unit_position')
            self.assertEqual(summon['num_uses'], 1)
            self.assertIn('upon the host dying', mechanic['summary'])
            self.assertIn('the host unit is alive', mechanic['summary'])
            self.assertNotIn('No mapped effects', mechanic['summary'])
            self.assertTrue(any(c['key'] == 'unit_alive' for c in mechanic['conditions']['deactivates_when']))
            link = self.q.rows('unit_abilities', 'ability_key', key)[0]
            unit = self.check(self.q.get_unit_profile(link['unit_key']))
            self.assertTrue(any(e['kind'] == 'summon' for m in unit['passives']['abilities'] if m['key'] == key for e in m['effects']))

    def test_ambiguous_mounts_and_exact_names(self):
        result = self.q.resolve_unit('Teclis')
        self.assertEqual(result['status'], 'ambiguous')
        self.assertEqual(len(result['candidates']), 3)
        for c in result['candidates']:
            self.assertEqual(self.q.resolve_unit(c['name'])['status'], 'resolved')
        with self.assertRaises(ResolutionError):
            self.q.get_unit_profile('Teclis')
        self.assertEqual(self.q.resolve_unit('Kroxi')['status'], 'not_found')
        self.assertEqual(self.q.resolve_unit("' OR 1=1 --")['status'], 'not_found')

    def test_alias_preserves_selected_identity_and_availability(self):
        key = 'wh2_main_lzd_mon_kroxigors_nakai'
        unit = self.check(self.q.get_unit_profile(key))
        self.assertEqual(unit['identity']['unit_key'], key)
        self.assertEqual(unit['identity']['profile_unit_key'], 'wh2_main_lzd_mon_kroxigors')
        detail = self.q.get_detail('availability:' + key)
        self.assertTrue(all(r['unit_key'] == key for r in detail['availability'] + detail['permissions']))
        self.assertEqual(self.q.resolve_unit(key, 'not_a_subculture')['status'], 'not_found')

    def test_multiroster_context_is_not_arbitrarily_selected(self):
        result = self.q.resolve_unit('wh3_main_tze_inf_blue_horrors_0')['resolved']
        self.assertGreater(len(result['subcultures']), 1)
        self.assertIsNone(result['subculture_key'])
        for context in result['subcultures']:
            unit = self.check(self.q.get_unit_profile(result['unit_key'], subculture=context))
            self.assertEqual(unit['identity']['subculture_key'], context)

    def test_resolved_shared_alias_discovery_keeps_context_and_continuation(self):
        resolved = self.q.resolve_unit('River Trolls')['resolved']
        self.assertIsNone(resolved['subculture_key'])
        self.assertGreater(len(resolved['source_unit_keys']), 1)
        direct = self.q.get_unit_profile('River Trolls', limit=1)
        from_identity = self.q.get_unit_profile(resolved, limit=1)
        self.assertEqual(direct, from_identity)
        coverage = next(s for s in direct['units'][0]['coverage']['sections'] if s['name'] == 'attributes')
        self.check(self.q.get_combat_relations(resolved, 'attributes', coverage['cursor'], limit=1))
        for subculture in resolved['subcultures']:
            scoped = self.q.get_unit_profile(resolved, subculture=subculture)
            unit = self.check(scoped)
            self.assertEqual(unit['identity']['subculture_key'], subculture)
            self.assertTrue(self.q.rows('unit_availability', 'unit_key', unit['identity']['unit_key']))
        forged = dict(resolved, source_unit_keys=resolved['source_unit_keys'] + ['wh3_main_tze_inf_blue_horrors_0'])
        with self.assertRaises(ValueError):
            self.q.get_unit_profile(forged)

    def test_fixture_core_values_and_effects_match_independent_source_examples(self):
        for name in ('sea_guard', 'blue_horrors', 'kroxigor', 'queen_bess', 'wargor'):
            fixture = json.loads((ROOT / f'fixtures/source_backed/{name}.json').read_text())['units'][0]
            unit = self.check(self.q.get_unit_profile(fixture['identity']['unit_key']))
            for group in ('movement', 'leadership', 'cost'):
                self.assertEqual(unit[group], fixture[group])
            for field in ('entity_count', 'hp_per_entity', 'total_hp', 'barrier_health', 'size'):
                self.assertEqual(unit['body'][field], fixture['body'][field])
            for field in ('attack', 'defence', 'base_damage', 'ap_damage', 'attack_interval', 'charge_bonus', 'max_splash_targets'):
                self.assertEqual(unit['melee'][field], fixture['melee'][field])
            self.assertEqual(unit['passives']['protection'], fixture['passives']['protection'])
            by_key = {m['key']: m for m in unit['passives']['abilities']}
            for m in fixture['passives']['abilities']:
                actual = by_key[m['key']]
                self.assertEqual(actual['requires_effect_enabling'], m['requires_effect_enabling'])
                for e in m['effects']:
                    if e['kind'] == 'unresolved':
                        continue
                    candidates = [x for x in actual['effects'] if x['kind'] == e['kind'] and x['phase_ref'] == e['phase_ref']]
                    expected = {k: v for k, v in e.items() if k != 'provenance_refs'}
                    self.assertIn(expected, [{k: v for k, v in x.items() if k != 'provenance_refs'} for x in candidates])
            if fixture['ranged']:
                for field in ('range', 'ammunition', 'reload_time', 'base_damage', 'ap_damage', 'projectiles_per_shot', 'shots_per_volley', 'burst_size', 'burst_shot_delay'):
                    self.assertEqual(unit['ranged'][field], fixture['ranged'][field])

    def test_all_named_pairs_and_an_arbitrary_pair(self):
        for a, b in [('Reiksguard', 'wh_main_grn_art_doom_diver_catapult'),
                     ('Lothern Sea Guard', 'Blue Horrors of Tzeentch'),
                     ('Bloodletters of Khorne', 'Kroxigor'),
                     ('wh_main_dwf_inf_ironbreakers', 'wh_main_vmp_mon_varghulf')]:
            self.check(self.q.get_matchup_evidence(a, b))

    def test_components_barrier_and_known_none(self):
        unit = self.check(self.q.get_unit_profile('wh_main_grn_art_doom_diver_catapult'))
        self.assertEqual(sorted(c['count'] for c in unit['body']['components']), [4, 40])
        crew = next(c for c in unit['body']['components'] if c['count'] == 40)
        self.assertIsNone(crew['targetable'])
        blue = self.check(self.q.get_unit_profile('Blue Horrors of Tzeentch'))
        self.assertEqual(blue['body']['barrier_health'], 1400)
        krox = self.check(self.q.get_unit_profile('Kroxigor'))
        self.assertIsNone(krox['ranged'])
        self.assertEqual(krox['coverage']['ranged'], 'known_none')

    def test_conditions_do_not_invert_ui_wording_or_modify_base(self):
        unit = self.check(self.q.get_unit_profile('Lothern Sea Guard'))
        self.assertEqual(unit['melee']['attack'], 22)
        passive = next(m for m in unit['passives']['abilities'] if m['key'].endswith('martial_prowess'))
        self.assertEqual(passive['conditions']['deactivates_when'][0]['key'], 'health_below_25%')
        self.assertIn('Deactivates when: health below 25%', passive['summary'])
        self.assertNotIn('Deactivation flags: Hit Points greater', passive['summary'])
        self.assertEqual(passive['phases'][0]['duration'], -1)

    def test_weapon_variants_and_shared_pools_keep_default_first(self):
        unit = self.check(self.q.get_unit_profile('Lothern Sea Guard'))
        self.assertEqual(unit['ranged']['slot'], 'primary')
        self.assertEqual(unit['ranged']['ammunition'], 22)
        extra = unit['ranged']['variants']
        self.assertTrue(extra)
        self.assertEqual(extra[0]['ammunition_pool'], 'secondary')
        self.assertEqual(extra[0]['ammunition'], 0)
        packet = self.q.get_unit_profile('wh_main_dwf_art_cannon', section='weapons', limit=1)
        refs = []
        while True:
            u = self.check(packet)
            if u['melee']:
                refs.append(u['melee']['id'])
            if u['ranged'] and u['ranged']['status'] == 'present':
                refs.append(u['ranged']['id'])
            coverage = next(s for s in u['coverage']['sections'] if s['name'] == 'weapons')
            if not coverage['cursor']:
                self.assertEqual(len(refs), coverage['total'])
                break
            packet = self.q.get_combat_relations('wh_main_dwf_art_cannon', 'weapons', coverage['cursor'], limit=1)
        self.assertEqual(len(refs), len(set(refs)))

    def test_real_healing_and_weapon_contact_payloads(self):
        unit = self.check(self.q.get_unit_profile('wh2_dlc09_tmb_art_casket_of_souls_0'))
        healing = [e for m in unit['passives']['abilities'] for e in m['effects'] if e['kind'] == 'healing']
        self.assertTrue(healing)
        self.assertIn('resurrect', healing[0]['native_parameters'])
        packet = self.q.get_unit_profile('wh2_main_skv_inf_clanrat_spearmen_0')
        self.check(packet)
        # Contact mechanics are scoped to attacks, with immediate effects inline.
        poison_key = self.q.db.execute("SELECT unit_key FROM unit_contact_effects WHERE effect_key='wh_main_unit_contact_poison' LIMIT 1").fetchone()[0]
        packet = self.q.get_unit_profile(poison_key)
        self.check(packet)
        self.assertTrue(any(n['kind'] == 'native_phase_stat_effects' for n in packet['payload_graph']['nodes']))

    def test_invented_cycle_and_parallel_edges_survive_detail(self):
        # Inject into a disposable snapshot, never the source or serving store.
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / 'cycle.sqlite'
            with closing(sqlite3.connect(output)) as db:
                self.q.db.backup(db)
                roots = [r[0] for r in db.execute('SELECT record_id FROM projectiles LIMIT 2')]
                a, b = roots
                for source, target, ordinal in [(a, b, 0), (a, b, 1), (b, a, 0)]:
                    db.execute('INSERT INTO relation_edges VALUES(?,?,?,?,?,?)',
                               (source, 'SYNTHETIC-NOT-GAME-DATA', '["test"]', target, 'resolved', ordinal))
                db.commit()
            with Queries(output) as q:
                graph = q.get_detail('record:' + a, limit=256)
                invented = [e for e in graph['edges'] if e['relation'] == 'SYNTHETIC-NOT-GAME-DATA']
                self.assertEqual(len(invented), 3)
                ids = [n['id'] for n in graph['nodes']]
                self.assertEqual(len(ids), len(set(ids)))

    def test_options_are_qualified_metadata_without_effects(self):
        unit = self.check(self.q.get_unit_profile('wh2_dlc17_bst_cha_wargor_0'))
        passive = next(m for m in unit['passives']['abilities'] if m['key'].endswith('will_of_the_dark_gods'))
        self.assertTrue(passive['requires_effect_enabling'])
        for option in unit['activated_options']:
            self.assertNotIn('effects', option)
            self.assertTrue(option['classification_evidence'])
            self.assertEqual(self.q.get_detail(option['detail_ref'])['status'], 'deferred')
        with self.assertRaises(ValueError):
            self.q.get_passive_detail('wh2_main_unit_passive_martial_prowess', culture='invented_culture')

    def test_diagnostics_are_opt_in_without_changing_combat_facts(self):
        key = 'Kroxigor'
        compact = self.q.get_unit_profile(key)
        inspection = self.q.get_unit_profile(key, include_diagnostics=True)
        self.check(compact)
        self.check(inspection)
        coverage = compact['units'][0]['coverage']
        self.assertNotIn('gaps', coverage)
        self.assertGreater(coverage['diagnostic_count'], 0)
        self.assertEqual(coverage['diagnostic_count'], len(inspection['units'][0]['coverage']['gaps']))
        for group in ('identity', 'body', 'movement', 'leadership', 'melee', 'ranged', 'passives', 'cost', 'activated_options'):
            self.assertEqual(compact['units'][0][group], inspection['units'][0][group])
        notes = self.q.get_coverage_notes(key)
        self.assertEqual(notes['units'][0]['coverage'], inspection['units'][0]['coverage'])
        self.assertNotIn('passives', notes['units'][0])
        for gap in notes['units'][0]['coverage']['gaps']:
            for ref in gap['provenance_refs']:
                self.assertIn(ref, notes['provenance'])
        passive_key = 'wh2_main_unit_passive_martial_prowess'
        passive = self.q.get_passive_detail(passive_key)
        detailed = self.q.get_passive_detail(passive_key, include_diagnostics=True)
        self.assertNotIn('gaps', passive)
        self.assertEqual(passive['mechanic'], detailed['mechanic'])
        self.assertEqual(passive['diagnostic_count'], len(detailed['gaps']))
        projected = self.q.get_combat_relations(key, 'abilities', limit=1)
        self.check(projected)
        self.assertEqual(projected['units'][0]['coverage']['ranged'], 'omitted')

    def test_native_phase_parameters_are_visible_without_invented_units(self):
        for key, field, value, text in (
            ('wh_main_character_abilities_arcane_conduit', 'mana_regen_mod', 0.4, 'Mana regeneration modifier: 0.4'),
            ('wh3_dlc24_unit_passive_solar_engine', 'fatigue_change_ratio', -0.0025, 'Fatigue change ratio: -0.0025'),
        ):
            mechanic = self.q.get_passive_detail(key)['mechanic']
            self.assertIn(text, mechanic['summary'])
            self.assertIn('not verified', mechanic['summary'])
            self.assertNotIn('scalar modifier', mechanic['summary'])
            self.assertNotIn('..', mechanic['summary'])
            effect = next(e for e in mechanic['effects'] if e.get('native_kind') == 'phase_behavior')
            self.assertEqual(effect['kind'], 'unresolved')
            self.assertEqual(effect['native_parameters'][field], value)
            self.assertEqual(mechanic['phases'][0]['lifecycle'][field], value)
        mechanic = self.q.get_passive_detail('wh2_dlc09_unit_passive_unstable_mark_ii_sand')['mechanic']
        self.assertIn('max amount: 1.3', mechanic['summary'])
        self.assertIn('effective scaling and stacking unverified', mechanic['summary'])
        self.assertNotIn('source path:', mechanic['summary'])

    def test_attribute_polarity_describes_application_not_benefit(self):
        from ctw_adviser.queries import Packet
        cases = (
            ('wh2_dlc10_lord_passive_boon_of_isha', 'immune_to_psychology', 'grant', 'Grants Immune to Psychology'),
            ('wh2_dlc11_unit_contact_disrupted', 'silenced', 'grant', 'Grants Silenced'),
            ('wh3_dlc26_character_passive_dreaded_aura', 'immune_to_psychology', 'remove', 'Removes Immune to Psychology'),
            ('wh3_dlc26_unit_passive_runes_of_binding', 'rampage', 'remove', 'Removes Rampage'),
        )
        for phase_key, attribute, operation, wording in cases:
            c = Packet(self.q)
            effects = c.phase_effects(self.q.one('native_ability_phases', 'id', phase_key), [])
            effect = next(e for e in effects if e.get('attribute_key') == attribute)
            self.assertEqual(effect['operation'], operation)
            self.assertEqual(effect['native_parameters']['attribute_type'], 'positive' if operation == 'grant' else 'negative')
            summary = c.summary({'effects': effects, 'phases': [], 'conditions': {'deactivates_when': []}})
            self.assertIn(wording, summary)
            self.assertNotIn('native type', summary)
            self.assertNotIn('native value', summary)

    def test_recharge_and_usage_conditions_are_visible_with_correct_roles(self):
        wounds = self.q.get_passive_detail('wh3_main_unit_passive_single_entity', include_diagnostics=True)
        mechanic = wounds['mechanic']
        self.assertEqual(mechanic['conditions']['recharges_when'][0]['key'], 'health_below_25%')
        self.assertEqual(mechanic['conditions']['activates_when'], [])
        self.assertEqual(mechanic['conditions']['deactivates_when'], [])
        self.assertEqual(mechanic['conditions']['unresolved'], [])
        self.assertIn('Readiness/recharge conditions: health below 25%', mechanic['summary'])
        self.assertIn('initial recharge: 5.0', mechanic['summary'])
        self.assertNotIn('greater than 25%', mechanic['summary'])
        self.assertTrue(any(g['code'] == 'recharge_activation_boundary' for g in wounds['gaps']))
        for key, wording in (
            ('wh3_main_unit_passive_cloud_of_flies', 'engaged in melee'),
            ('wh_dlc04_unit_passive_strength_of_the_penitent', 'losing melee combat'),
            ('wh2_main_unit_passive_another_takes_its_place', 'health below 50% of base health'),
            ('wh3_dlc23_unit_passive_extra_reload', 'ammunition below 80%'),
        ):
            mechanic = self.q.get_passive_detail(key)['mechanic']
            self.assertIn(wording, mechanic['summary'])
            self.assertTrue(mechanic['conditions']['recharges_when'])
            self.assertEqual(mechanic['conditions']['unresolved'], [])
        for row in self.q.db.execute('SELECT special_ability,invalid_usage_flag FROM native_special_ability_to_invalid_usage_flags'):
            mechanic = self.q.get_passive_detail(row['special_ability'])['mechanic']
            self.assertEqual(mechanic['conditions']['unavailable_when'][0]['key'], row['invalid_usage_flag'])
            self.assertIn('Unavailable when:', mechanic['summary'])
        packet = self.q.get_unit_profile('wh2_main_lzd_mon_kroxigors')
        self.check(packet)

    def test_section_pagination_exhausts_inventory_once(self):
        for section, field in [('attributes', 'attributes'), ('abilities', 'abilities')]:
            seen = []
            packet = self.q.get_combat_relations('Kroxigor', section, limit=1)
            while True:
                unit = self.check(packet)
                seen.extend(x['key'] for x in unit['passives'][field])
                coverage = next(s for s in unit['coverage']['sections'] if s['name'] == section)
                if coverage['cursor'] is None:
                    self.assertEqual(coverage['state'], 'complete')
                    self.assertEqual(len(seen), coverage['total'])
                    break
                packet = self.q.get_combat_relations('Kroxigor', section, coverage['cursor'], limit=1)
            self.assertEqual(len(seen), len(set(seen)))

    def test_stale_mismatched_and_corrupt_cursors_rejected(self):
        packet = self.q.get_unit_profile('Kroxigor', limit=1)
        cursor = next(s for s in packet['units'][0]['coverage']['sections'] if s['name'] == 'abilities')['cursor']
        for kwargs in ({'mode': 'melee'}, {'limit': 2}, {'section': 'attributes'}):
            options = dict(limit=1, cursor=cursor); options.update(kwargs)
            with self.assertRaises(ValueError):
                self.q.get_unit_profile('Kroxigor', **options)
        with self.assertRaises(ValueError):
            self.q.get_unit_profile('Kroxigor', cursor=cursor + 'x', limit=1)
        with self.assertRaises(ValueError):
            self.q.get_unit_profile('Blue Horrors of Tzeentch', cursor=cursor, limit=1)
        original = self.q.snapshot['id']
        try:
            self.q.snapshot['id'] = 'stale'
            with self.assertRaises(ValueError):
                self.q.get_unit_profile('Kroxigor', cursor=cursor, limit=1)
        finally:
            self.q.snapshot['id'] = original

    def test_modes_and_scenario_do_not_apply_effects(self):
        for mode in ('combined', 'melee', 'missile'):
            packet = self.q.get_unit_profile('Lothern Sea Guard', mode=mode, scenario={'health_fraction': 0.1})
            unit = self.check(packet)
            self.assertEqual(packet['scenario']['health_fraction'], 0.1)
            self.assertEqual(unit['leadership'], 70)
            if mode == 'melee':
                self.assertEqual(unit['ranged']['status'], 'omitted')
            if mode == 'missile':
                self.assertIsNone(unit['melee'])
            else:
                self.assertEqual(unit['melee']['defence'], 32)

    def test_provenance_expands_original_records_and_payload_lineage(self):
        packet = self.q.get_unit_profile('Queen Bess')
        self.check(packet)
        requested = packet['units'][0]['ranged']['provenance_refs']
        detail = self.q.get_provenance(requested)
        self.assertGreater(len(detail['provenance']), len(set(requested)))
        for evidence in detail['provenance'].values():
            path = SOURCE / detail['sources'][evidence['source_id']]['path']
            with path.open(encoding='utf-8', newline='') as f:
                rows = list(csv.DictReader(f, delimiter='\t' if path.suffix == '.tsv' else ','))
            row = rows[evidence['logical_record'] - 2]
            for key, value in evidence['key'].items():
                self.assertEqual(row[key], value)

    def test_detail_pagination_is_cycle_safe_and_keeps_edges(self):
        packet = self.q.get_unit_profile('Blue Horrors of Tzeentch')
        ref = packet['units'][0]['passives']['abilities'][0]['detail_ref']
        whole = self.q.get_detail(ref, limit=256)
        self.assertEqual(whole['state'], 'complete')
        nodes = []; edges = set(); cursor = None
        while True:
            page = self.q.get_detail(ref, limit=2, cursor=cursor)
            nodes.extend(n['id'] for n in page['nodes'])
            edges.update(json.dumps(e, sort_keys=True) for e in page['edges'])
            cursor = page['cursor']
            if cursor is None:
                break
        self.assertEqual(nodes, [n['id'] for n in whole['nodes']])
        self.assertEqual(len(nodes), len(set(nodes)))
        self.assertEqual(edges, {json.dumps(e, sort_keys=True) for e in whole['edges']})

    def test_determinism_read_only_and_indexed_access(self):
        first = self.q.get_unit_profile('Kroxigor')
        self.q.get_unit_profile('Blue Horrors of Tzeentch')
        self.assertEqual(first, self.q.get_unit_profile('Kroxigor'))
        with self.assertRaises(sqlite3.OperationalError):
            self.q.db.execute('DELETE FROM unit_profiles')
        for sql, key in [('SELECT * FROM unit_profiles WHERE unit_name=? COLLATE NOCASE', 'Kroxigor'),
                         ('SELECT * FROM unit_profiles WHERE source_unit_name=? COLLATE NOCASE', 'Teclis'),
                         ('SELECT * FROM unit_abilities WHERE unit_key=?', 'wh2_main_lzd_mon_kroxigors'),
                         ('SELECT * FROM native_phase_stat_effects WHERE phase=?', 'wh2_main_unit_passive_martial_prowess')]:
            self.assertTrue(all('SEARCH ' in row[3] for row in self.q.db.execute('EXPLAIN QUERY PLAN ' + sql, (key,))))

    def test_cli_queries_need_only_the_snapshot(self):
        command = [sys.executable, str(ROOT / 'scripts/query_snapshot.py')]
        for args, code in [(['unit', '--db', str(self.output), 'Teclis'], 2),
                           (['resolve', '--db', str(self.output), 'Kroxi'], 0),
                           (['unit', '--db', str(self.output), 'Kroxigor'], 0),
                           (['matchup', '--db', str(self.output), 'Kroxigor'], 1)]:
            result = subprocess.run(command + args, capture_output=True, text=True)
            self.assertEqual(result.returncode, code, result.stderr)
            output = json.loads(result.stdout)
            if output.get('units'):
                self.check(output)


if __name__ == '__main__':
    unittest.main()
