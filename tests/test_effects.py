"""Issue #19: specialized spell/activated-ability retrieval on the pinned store."""
from contextlib import closing
import copy
import json
import os
from pathlib import Path
import shutil
import sqlite3
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
sys.path.insert(0, str(ROOT / 'scripts'))
from ctw_adviser.build import build_snapshot, validate_effects
from ctw_adviser.queries import Queries, ResolutionError
from ctw_adviser.store import open_snapshot
from validate_packets import validate, packet_checks

SOURCE = Path(os.environ.get('CTW_DATA_ROOT', ROOT.parent / 'CTW-data'))

BOUND = 'wh2_main_spell_bound_khaines_ring_of_fury'          # bound spell (Teclis)
POTION = 'wh2_main_lord_abilities_potion_of_charoi'           # non-spell activated ability
COMET = 'wh_main_spell_heavens_comet_of_casandora'            # bombardment chain, has overcast
COMET_OVERCAST = COMET + '_upgraded'                          # overcast with miscast branch
SUMMON = 'wh2_dlc11_spell_vampires_drowned_dead'              # summon spell, unmapped land unit
HELL_HAMMER = 'wh3_dlc23_spell_bound_hell_hammer'                       # zero-damage projectile -> damaging explosion
THIRTEENTH = 'wh2_main_spell_grey_seer_the_dreaded_thirteenth_spell'    # zero-damage projectile -> shrapnel
REGENERATING = 'wh2_dlc10_quest_abilities_regenerating_head'            # zero-damage explosion -> healing phase
TECLIS = 'wh2_main_hef_cha_teclis_0'


@unittest.skipUnless((SOURCE / 'data/unit_stats/dataset_manifest.json').exists(), 'pinned CTW-data required')
class EffectTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.output = Path(cls.temp.name) / 'units.sqlite'
        build_snapshot(SOURCE, cls.output)
        cls.q = Queries(cls.output)
        cls.schema = json.loads((ROOT / 'schema/evidence_packet.schema.json').read_text())
        cls.effect_schema = json.loads((ROOT / 'schema/effect_packet.schema.json').read_text())

    @classmethod
    def tearDownClass(cls):
        cls.q.close()
        cls.temp.cleanup()

    def effect(self, key, **kwargs):
        return self.q.get_effect(key, **kwargs)['effect']

    def test_distinct_linked_tables_keep_unit_rows_narrow(self):
        db = self.q.db
        unit_columns = {r[1] for r in db.execute('PRAGMA table_info(unit_profiles)')}
        self.assertFalse(unit_columns & {'mana_cost', 'recharge_time', 'bombardment', 'vortex', 'keywords_json'})
        activated = db.execute("SELECT count(*) FROM ability_option_metadata WHERE classification='activated_option'").fetchone()[0]
        self.assertEqual(db.execute('SELECT count(*) FROM effect_abilities').fetchone()[0], activated)
        self.assertEqual(db.execute('SELECT count(*) FROM effect_access').fetchone()[0],
                         db.execute('SELECT count(*) FROM unit_abilities JOIN effect_abilities USING(ability_key)').fetchone()[0])
        self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(), [])
        # Both spells and non-spell activated abilities are represented.
        kinds = dict(db.execute('SELECT effect_kind,count(*) FROM effect_abilities GROUP BY 1').fetchall())
        self.assertGreater(kinds['spell'], 0)
        self.assertGreater(kinds['activated_ability'], 0)
        # Every effect is reachable through indexed SEARCH access.
        for sql, params in (('SELECT * FROM effect_abilities WHERE ability_key=?', (BOUND,)),
                            ('SELECT * FROM effect_abilities WHERE name=? COLLATE NOCASE', ('Chain Lightning',)),
                            ('SELECT * FROM effect_access WHERE unit_key=?', (TECLIS,)),
                            ('SELECT * FROM effect_access WHERE ability_key=?', (BOUND,)),
                            ('SELECT * FROM effect_variants WHERE variant_key=?', (COMET_OVERCAST,)),
                            ('SELECT * FROM unit_profiles WHERE source_land_unit_key=?', ('x',))):
            plan = ' '.join(r[3] for r in db.execute('EXPLAIN QUERY PLAN ' + sql, params))
            self.assertNotIn('SCAN', plan, sql)

    def test_spell_and_activated_ability_detailed_retrieval(self):
        bound = self.effect(BOUND)
        self.assertEqual(bound['identity']['effect_kind'], 'spell')
        self.assertEqual(bound['identity']['source_type'], 'bound')
        self.assertIn('bound', bound['identity']['keywords'])
        values = bound['activation']['values']
        self.assertEqual((values['wind_up_time'], values['active_time'], values['recharge_time'], values['num_uses']),
                         (5.0, 10.0, 120.0, 2))
        # Negative native settings are reported as sentinels, never as resources.
        self.assertIn('shared_recharge_time', bound['activation']['native_sentinels'])
        self.assertEqual(bound['distances']['target_intercept_range']['value'], 150.0)
        self.assertEqual(bound['distances']['effect_range']['value'], 0.0)
        self.assertTrue(bound['targeting']['values']['target_enemies'])
        self.assertFalse(bound['targeting']['values']['target_friends'])
        vortex = bound['payload']['chains'][0]
        self.assertEqual(vortex['root_relationship'], 'unit_special_abilities_tables.vortex')
        self.assertIn('damage_ap 35', vortex['path'][0])
        self.assertIn('bound spell', bound['summary'])

        potion = self.effect(POTION)
        self.assertEqual(potion['identity']['effect_kind'], 'activated_ability')
        kinds = {e['kind'] for e in potion['mechanic']['effects']}
        self.assertTrue({'healing', 'stat_modifier'} <= kinds)
        self.assertIn('Ward save +40', potion['mechanic']['summary'])
        self.assertTrue(potion['mechanic']['phases'][0]['target_self'])

    def test_chained_zero_direct_damage_and_failure_branch(self):
        comet = self.effect(COMET)
        paths = [' -> '.join(c['path']) for c in comet['payload']['chains']]
        self.assertTrue(any(p.startswith('bombardments') and 'projectiles' in p and 'explosions' in p for p in paths))
        # The explosion has 0 base damage but still carries AP damage and a contact phase.
        self.assertTrue(any('explosions ' + COMET + ' (base_damage 0, ap_damage 72, radius 20' in p for p in paths))
        self.assertTrue(any('projectiles ' + COMET + ' (base_damage 864, ap_damage 864)' in p for p in paths))
        self.assertTrue(all(c['branch'] == 'activation' for c in comet['payload']['chains']))
        # Penetration is a modifier, so a projectile is not a transport merely by linking it.
        self.assertFalse(any('transports' in p for p in paths if p.endswith('projectile_penetration_junctions all')))
        for key, delivered in ((HELL_HAMMER, '[zero direct damage; transports linked payload] -> explosions '
                                             'wh3_dlc23_spell_hashut_hell_hammer_dummy_explosion (base_damage 24, ap_damage 24'),
                               (THIRTEENTH, '[zero direct damage; transports linked payload] -> projectile_shrapnels dreaded_fireworks (amount 6) -> projectiles'),
                               (REGENERATING, '[zero direct damage; transports linked payload] -> ability_phases')):
            chains = [' -> '.join(c['path']) for c in self.effect(key)['payload']['chains']]
            # Zero direct damage is not a terminal no-effect result.
            self.assertTrue(any(delivered in chain for chain in chains), key)
        self.assertIn('heal_amount 0.016', ' '.join(' '.join(c['path']) for c in self.effect(REGENERATING)['payload']['chains']))
        # A projectile with nonzero direct damage is not labelled a transport.
        self.assertFalse(any('pyromanianc (base_damage 1, ap_damage 0) [zero' in ' '.join(c['path'])
                             for c in self.effect('wh2_dlc11_character_abilities_pyromaniac')['payload']['chains']))
        self.assertTrue(comet['payload']['complete'])

        overcast = self.effect(COMET_OVERCAST)
        failure = [c for c in overcast['payload']['chains'] if c['branch'] == 'conditional_failure']
        self.assertEqual(len(failure), 1)
        self.assertEqual(failure[0]['condition']['miscast_chance'], 0.5)
        self.assertIn('wh_main_heavens_miscast', failure[0]['path'][0])
        # The failure branch is separate from, not a replacement for, the activation payload.
        self.assertTrue(any(c['branch'] == 'activation' for c in overcast['payload']['chains']))
        self.assertIn('Failure branch:', overcast['summary'])

    def test_overcast_variants_link_both_ways_without_crossing(self):
        normal = self.effect(COMET)
        self.assertIn({'direction': 'outgoing', 'relation': 'overcast_option', 'ability_key': COMET_OVERCAST},
                      [{k: v[k] for k in ('direction', 'relation', 'ability_key')} for v in normal['variants']])
        overcast = self.effect(COMET_OVERCAST)
        incoming = {v['ability_key'] for v in overcast['variants'] if v['direction'] == 'incoming'}
        self.assertIn(COMET, incoming)
        self.assertIn('overcast', overcast['identity']['keywords'])
        self.assertIn('has_overcast', normal['identity']['keywords'])
        # Distinct variant identities keep their own values.
        self.assertNotEqual(normal['activation']['values']['mana_cost'], overcast['activation']['values']['mana_cost'])

    def test_shared_labels_return_candidates_and_unit_filter(self):
        result = self.q.resolve_effect('Fiery Convocation')
        self.assertEqual(result['status'], 'ambiguous')
        keys = {c['ability_key'] for c in result['candidates']}
        self.assertIn('wh2_dlc10_spell_bound_magic_fiery_convocation', keys)
        with self.assertRaises(ResolutionError):
            self.q.get_effect('Fiery Convocation')
        self.assertEqual(self.q.resolve_effect('Bound Fiery Convocation', TECLIS)['resolved']['ability_key'], BOUND)
        self.assertEqual(self.q.resolve_effect('Fiery Convocation', TECLIS)['status'], 'not_found')
        self.assertEqual(self.q.resolve_effect('no such spell')['status'], 'not_found')

    def test_round_trip_unit_effect_unit(self):
        unit_effects = self.q.get_unit_effects(TECLIS)
        refs = {e['ability_key']: e for e in unit_effects['effects']}
        self.assertIn(BOUND, refs)
        self.assertIn(POTION, refs)
        entry = refs[BOUND]
        self.assertEqual(entry['detail_ref'], 'effect:' + BOUND)
        self.assertTrue(entry['requires_effect_enabling'])
        self.assertEqual(set(entry) & {'activation', 'mechanic', 'payload'}, set())
        effect = self.q.get_detail(entry['detail_ref'])['effect']
        linked = {a['unit_key']: a for a in effect['access']['links']}
        self.assertIn(TECLIS, linked)
        self.assertEqual(linked[TECLIS]['mapping'], 'roster_profile')
        self.assertIn('not proof', linked[TECLIS]['qualification'])
        # Linked units resolve through the existing unit lookup interface.
        resolved = self.q.resolve_unit(linked[TECLIS]['unit_key'])
        self.assertEqual(resolved['resolved']['unit_key'], TECLIS)
        # Each mount/form variant keeps its own access record.
        self.assertIn('wh2_main_hef_cha_teclis_1', linked)
        self.assertIn('wh2_dlc15_hef_cha_teclis_2', linked)

    def test_unit_packet_lists_keywords_and_references_only(self):
        packet = self.q.get_unit_profile(TECLIS, limit=256)
        validate(packet, self.schema, self.schema)
        packet_checks(packet, provenance_resolver=self.q.get_provenance)
        self.assertEqual(packet['schema_version'], '1.21.0')
        options = {o['key']: o for o in packet['units'][0]['activated_options']}
        bound = options[BOUND]
        self.assertEqual(bound['effect_kind'], 'spell')
        self.assertIn('vortex', bound['keywords'])
        self.assertEqual(bound['detail_ref'], 'effect:' + BOUND)
        self.assertNotIn('mechanic', bound)
        self.assertNotIn('payload', json.dumps(bound))
        self.assertEqual(packet['detail_refs']['effect:' + BOUND], {'kind': 'effect', 'key': BOUND})
        # Legacy option references now point at the specialized lookup.
        self.assertEqual(self.q.get_detail('option:' + BOUND)['effect_ref'], 'effect:' + BOUND)

    def test_summon_mapping_is_explicit_without_name_match(self):
        summon = self.effect(SUMMON)
        self.assertEqual(summon['summons'][0]['land_unit_key'], 'wh2_dlc11_cst_inf_zombie_deckhands_mob_summoned_0')
        self.assertEqual(summon['summons'][0]['mapping'], 'unmapped_land_unit')
        self.assertEqual(summon['summons'][0]['units'], [])
        self.assertEqual(summon['summons'][0]['trigger'], 'on_activation')
        mapped = self.q.db.execute(
            'SELECT c.key,c.spawned_unit FROM native_ability_casting c JOIN effect_abilities e ON e.ability_key=c.key '
            'JOIN unit_profiles p ON p.source_land_unit_key=c.spawned_unit ORDER BY c.key LIMIT 1').fetchone()
        effect = self.effect(mapped['key'])
        self.assertEqual(effect['summons'][0]['mapping'], 'roster_profiles')
        for unit in effect['summons'][0]['units']:
            profile = self.q.one('unit_profiles', 'unit_key', unit['unit_key'])
            self.assertEqual(profile['source_land_unit_key'], mapped['spawned_unit'])

    def test_every_represented_effect_uses_one_bounded_lookup(self):
        keys = [r[0] for r in self.q.db.execute('SELECT ability_key FROM effect_abilities ORDER BY ability_key')]
        timings, sizes = [], []
        for key in keys:
            started = time.perf_counter()
            packet = self.q.get_effect(key)
            timings.append(time.perf_counter() - started)
            sizes.append(len(json.dumps(packet)))
            effect = packet['effect']
            self.assertEqual(effect['identity']['ability_key'], key)
            self.assertTrue(effect['mechanic']['effects'])
            self.assertEqual(packet['sources'], {})  # provenance deferred by default
            for node in packet['payload_graph']['nodes']:
                self.assertTrue(node['provenance_refs'])
        timings.sort(); sizes.sort()
        self.assertLess(timings[int(len(timings) * 0.95)], 0.25)
        self.assertLess(sizes[-1], 64_000)

    def test_access_pagination_and_provenance_expansion(self):
        key = self.q.db.execute('SELECT ability_key FROM effect_access GROUP BY ability_key '
                                'ORDER BY count(*) DESC, ability_key LIMIT 1').fetchone()[0]
        first = self.effect(key, limit=1)['access']
        seen = [first['links'][0]['provenance_refs'][0]]
        cursor = first['cursor']
        while cursor:
            page = self.effect(key, limit=1, cursor=cursor)['access']
            seen.append(page['links'][0]['provenance_refs'][0])
            cursor = page['cursor']
        self.assertEqual(len(seen), first['total'])
        self.assertEqual(len(set(seen)), len(seen))
        with self.assertRaisesRegex(ValueError, 'cursor'):
            self.q.get_effect(BOUND, limit=1, cursor=first['cursor'])
        expanded = self.q.get_effect(BOUND, include_provenance=True)
        refs = expanded['effect']['identity']['provenance_refs']
        self.assertTrue(set(refs) <= set(expanded['provenance']))
        self.assertTrue(expanded['sources'])

    def test_unresolved_payload_references_stay_explicit(self):
        gaps = self.q.db.execute("SELECT detail FROM coverage_gaps WHERE kind='unresolved_reference' "
                                 "AND detail LIKE '%mom_vortex_key%'").fetchall()
        self.assertTrue(gaps)
        edges = self.q.db.execute("SELECT count(*) FROM relation_edges WHERE status!='resolved'").fetchone()[0]
        self.assertEqual(edges, len(gaps))

    def tamper(self, *statements):
        copy = Path(self.temp.name) / 'tampered.sqlite'
        shutil.copyfile(self.output, copy)
        with closing(sqlite3.connect(copy)) as db:
            db.execute('PRAGMA foreign_keys=OFF')
            db.execute('PRAGMA ignore_check_constraints=ON')
            for sql in statements:
                db.execute(sql)
            db.commit()
        return copy

    def options(self, db):
        return {k: (c, None, None) for k, c in db.execute('SELECT ability_key,classification FROM ability_option_metadata')}

    def test_negative_corrupt_and_crossed_artifacts_fail(self):
        crossed = self.tamper(f"UPDATE effect_variants SET variant_ability='{BOUND}' WHERE ability_key='{COMET}'")
        with closing(sqlite3.connect(crossed)) as db, self.assertRaisesRegex(ValueError, 'crossed'):
            validate_effects(db, self.options(db))
        dropped = self.tamper(f"DELETE FROM effect_access WHERE ability_key='{BOUND}'")
        with closing(sqlite3.connect(dropped)) as db, self.assertRaisesRegex(ValueError, 'access reconciliation'):
            validate_effects(db, self.options(db))
        wrong_unit = self.tamper("UPDATE effect_access SET unit_key=("
            "SELECT unit_key FROM unit_identity WHERE namespace='roster' AND unit_key != "
            "(SELECT unit_key FROM effect_access LIMIT 1) LIMIT 1) "
            "WHERE link_record=(SELECT link_record FROM effect_access LIMIT 1)")
        with closing(sqlite3.connect(wrong_unit)) as db:
            self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(), [])
            with self.assertRaisesRegex(ValueError, 'access reconciliation'):
                validate_effects(db, self.options(db))
        wrong_overcast = self.tamper(f"UPDATE effect_variants SET variant_key='{BOUND}', "
            f"variant_ability='{BOUND}' WHERE rowid=(SELECT rowid FROM effect_variants "
            "WHERE relation='overcast_option' LIMIT 1)")
        with closing(sqlite3.connect(wrong_overcast)) as db:
            self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(), [])
            with self.assertRaisesRegex(ValueError, 'variant source reconciliation'):
                validate_effects(db, self.options(db))
        missing = self.tamper(f"DELETE FROM effect_abilities WHERE ability_key='{POTION}'")
        with closing(sqlite3.connect(missing)) as db:
            self.assertTrue(db.execute('PRAGMA foreign_key_check').fetchall())
            with self.assertRaisesRegex(ValueError, 'effect reconciliation'):
                validate_effects(db, self.options(db))
        partial = self.tamper(f"UPDATE record_provenance SET retention='option_metadata' WHERE id="
                              f"(SELECT casting_record FROM effect_abilities WHERE ability_key='{BOUND}')")
        with closing(sqlite3.connect(partial)) as db, self.assertRaisesRegex(ValueError, 'without full payload'):
            validate_effects(db, self.options(db))
        stale = self.tamper('UPDATE snapshot SET schema_version=3')
        with self.assertRaisesRegex(ValueError, 'unsupported snapshot schema'):
            open_snapshot(stale)
        foreign = self.tamper("UPDATE snapshot SET contract_sha256='0'")
        with self.assertRaisesRegex(ValueError, 'unsupported snapshot schema'):
            open_snapshot(foreign)

    def test_missing_and_null_source_fields_are_not_invented(self):
        nulled = self.tamper(f"UPDATE native_ability_casting SET mana_cost=NULL WHERE key='{COMET}'")
        with Queries(nulled) as q:
            self.assertIsNone(q.get_effect(COMET)['effect']['activation']['values']['mana_cost'])
        gone = self.tamper(f"DELETE FROM native_ability_casting WHERE key='{POTION}'")
        with Queries(gone) as q, self.assertRaisesRegex(ValueError, 'missing retained casting'):
            q.get_effect(POTION)

    def test_specialized_effect_packet_contract(self):
        for key in (COMET, COMET_OVERCAST, BOUND, POTION, SUMMON):
            packet = self.q.get_effect(key, include_provenance=True, include_diagnostics=True)
            validate(packet, self.effect_schema, self.effect_schema)
            packet_checks(packet)
        packet = self.q.get_effect(COMET, include_provenance=True)
        for field in ('effect', 'sources', 'provenance', 'detail_refs', 'payload_graph', 'diagnostic_count'):
            broken = copy.deepcopy(packet)
            del broken[field]
            with self.subTest(field=field), self.assertRaises(ValueError):
                validate(broken, self.effect_schema, self.effect_schema)
        for group, fields in (('activation', ('mana_cost', 'recharge_time', 'num_uses')),
                              ('targeting', ('target_enemies', 'num_effected_enemy_units'))):
            for field in fields:
                broken = copy.deepcopy(packet)
                del broken['effect'][group]['values'][field]
                with self.subTest(group=group, field=field), self.assertRaises(ValueError):
                    validate(broken, self.effect_schema, self.effect_schema)
        packet['effect']['activation']['values']['mana_cost'] = None
        validate(packet, self.effect_schema, self.effect_schema)

    def test_per_kind_omission_and_explicit_null(self):
        common = {'phase_ref': None, 'provenance_refs': ['source']}
        cases = {
            'stat_modifier': ({'stat':'armour','operation':'add','native_operation':'add','value':None}, ('value',)),
            'attribute_effect': ({'attribute_key':'flaming','operation':'grant','recipient':None,'native_parameters':{}}, ('recipient',)),
            'periodic_damage': ({'native_parameters':{'damage_amount':None,'hp_change_frequency':None,'max_damaged_entities':None}}, ('native_parameters','damage_amount')),
            'healing': ({'native_parameters':{'heal_amount':None,'barrier_heal_amount':None,'hp_change_frequency':None,'resurrect':None,'limits':{}}}, ('native_parameters','heal_amount')),
            'summon': ({'unit_key':'land_unit','unit_name':None,'trigger':'on_activation','trigger_basis':'source','spawn_type':None,'num_uses':None,'native_parameters':{}}, ('unit_name',)),
            'phase_behavior': ({'native_kind':'phase_behavior','native_parameters':{'imbue_contact':None},'reason':'source'}, ('native_parameters','imbue_contact')),
            'phase_role': ({'native_kind':'phase_role','native_parameters':{'setting':None},'reason':'source'}, ('phase_ref',)),
            'visual_indicator': ({'purpose':'source'}, ('phase_ref',)),
            'payload_reference': ({'node_ref':'node','relationship':'source'}, ('phase_ref',)),
            'unresolved': ({'native_kind':'unresolved','native_parameters':{'setting':None},'reason':'source'}, ('phase_ref',)),
        }
        for kind, (fields, nullable_path) in cases.items():
            effect = {'kind':kind, **common, **fields}
            with self.subTest(kind=kind):
                validate(effect, {'$ref':'#/$defs/effect'}, self.effect_schema)
                broken = copy.deepcopy(effect)
                target = broken
                for part in nullable_path[:-1]:
                    target = target[part]
                del target[nullable_path[-1]]
                with self.assertRaises(ValueError):
                    validate(broken, {'$ref':'#/$defs/effect'}, self.effect_schema)


    # -- Increment 2: character skill/rank access (contract 4) --------------

    def test_character_routes_round_trip_with_exact_skill_rank(self):
        routes = self.effect(COMET)['access']['characters']
        self.assertGreater(routes['total'], 0)
        mage = next(e for e in routes['entries'] if e['agent_subtype_key'] == 'wh2_dlc10_hef_mage_heavens')
        roles = {(b['role'], b['skill_key'], b['skill_level']) for b in mage['bindings']}
        self.assertIn(('enables', 'wh_main_skill_all_magic_heavens_09_comet_of_casandora', 1), roles)
        # Successive ranks remain separate records; nothing is summed.
        self.assertIn(('enables', 'wh_main_skill_all_magic_heavens_09_comet_of_casandora', 2), roles)
        self.assertTrue(any(b['role'] == 'enables_overcast' for b in mage['bindings']))
        form = mage['unit_forms'][0]
        self.assertEqual(form['mapping'], 'roster_unit')
        self.assertEqual(self.q.resolve_unit(form['unit_key'])['status'], 'resolved')
        character = self.q.get_character_effects(mage['agent_subtype_key'])
        self.assertIn(COMET, {e['ability_key'] for e in character['effects']})
        back = self.q.get_unit_effects(form['unit_key'])['character_skill_effects']
        self.assertIn(COMET, {e['ability_key'] for c in back for e in c['effects']})
        self.assertIn('not selected skills', routes['note'])

    def test_supplied_skills_filter_without_solver(self):
        full = self.q.get_character_effects('Teclis')
        self.assertIsNone(full['supplied_skills'])
        picked = self.q.get_character_effects('Teclis', skills=['wh2_main_skill_magic_dark_flock_of_doom_teclis:1', 'invented:3'])
        self.assertEqual({e['ability_key'] for e in picked['effects']}, {'wh_dlc03_spell_beasts_flock_of_doom'})
        self.assertEqual(picked['unknown_supplied_skills'], ['invented:3'])
        self.assertTrue(all(b['skill_level'] == 1 for e in picked['effects'] for b in e['bindings']))
        with self.assertRaisesRegex(ValueError, 'SKILL_KEY:RANK'):
            self.q.get_character_effects('Teclis', skills=['no_rank'])
        self.assertEqual(self.q.resolve_character('Tomb King')['status'], 'ambiguous')
        with self.assertRaises(ResolutionError):
            self.q.get_character_effects('Tomb King')

    def test_group_bindings_are_modifiers_not_grants(self):
        teclis = self.q.get_character_effects('Teclis')
        groups = [o for o in teclis['other_bindings'] if o['target_kind'] == 'ability_group']
        self.assertTrue(groups)
        self.assertIn('never grant', teclis['note'])
        modifiers = self.effect('wh_main_spell_heavens_chain_lightning')['access']['group_modifiers']
        self.assertTrue(modifiers)
        self.assertTrue(all('do not grant' in g['note'] for g in modifiers))
        # Group bindings never create per-spell access rows.
        self.assertEqual(self.q.db.execute("SELECT count(*) FROM effect_character_access a JOIN magic_skill_bindings b "
                                           "ON b.record_id=a.binding_record WHERE b.target_kind!='ability'").fetchone()[0], 0)

    def test_unmapped_character_forms_stay_explicit(self):
        unmapped = [tuple(r) for r in self.q.db.execute(
            "SELECT agent_subtype_key,main_unit_key FROM character_unit_forms WHERE mapping='unmapped' ORDER BY 1")]
        self.assertIn(('wh3_main_pro_slavin_0', 'wh3_main_pro_ksl_cha_slavin_0'), unmapped)
        form = next(f for f in self.q.get_character_effects('wh3_main_pro_slavin_0')['character']['unit_forms']
                    if f['main_unit_key'] == 'wh3_main_pro_ksl_cha_slavin_0')
        self.assertIsNone(form['unit_key'])
        self.assertEqual(form['mapping'], 'unmapped')
        gaps = self.q.db.execute("SELECT count(*) FROM coverage_gaps WHERE kind='character_form_unmapped'").fetchone()[0]
        self.assertEqual(gaps, len(unmapped))

    def test_character_access_reconciles_and_detects_tampering(self):
        db = self.q.db
        self.assertEqual(db.execute('SELECT count(*) FROM magic_characters').fetchone()[0], 550)
        self.assertEqual(db.execute("SELECT count(*) FROM effect_character_access").fetchone()[0],
                         db.execute("SELECT count(*) FROM magic_skill_bindings WHERE target_kind='ability'").fetchone()[0])
        self.assertEqual(db.execute("SELECT count(*) FROM effect_character_access WHERE status='missing_definition'").fetchone()[0], 0)
        from ctw_adviser.build import validate_character_access
        dropped = self.tamper("DELETE FROM effect_character_access WHERE rowid IN (SELECT rowid FROM effect_character_access LIMIT 1)")
        with closing(sqlite3.connect(dropped)) as tampered, self.assertRaisesRegex(ValueError, 'reconciliation'):
            validate_character_access(tampered)
        crossed = self.tamper(f"UPDATE effect_character_access SET ability_key='{BOUND}' WHERE rowid IN "
                              f"(SELECT rowid FROM effect_character_access WHERE ability_key='{COMET}' LIMIT 1)")
        with closing(sqlite3.connect(crossed)) as tampered, self.assertRaisesRegex(ValueError, 'crossed'):
            validate_character_access(tampered)
        drift = self.tamper("DELETE FROM magic_skill_bindings WHERE rowid IN (SELECT rowid FROM magic_skill_bindings "
                            "WHERE target_kind!='ability' LIMIT 1)")
        with closing(sqlite3.connect(drift)) as tampered, self.assertRaisesRegex(ValueError, 'count drift'):
            validate_character_access(tampered)
        for sql, params in (('SELECT * FROM effect_character_access WHERE ability_key=?', (COMET,)),
                            ('SELECT * FROM effect_character_access WHERE agent_subtype_key=?', ('x',)),
                            ('SELECT * FROM character_unit_forms WHERE unit_key=?', (TECLIS,)),
                            ('SELECT * FROM magic_skill_bindings WHERE target_kind=? AND target_key=?', ('ability_group', 'x'))):
            plan = ' '.join(r[3] for r in db.execute('EXPLAIN QUERY PLAN ' + sql, params))
            self.assertNotIn('SCAN', plan, sql)


if __name__ == '__main__':
    unittest.main()
