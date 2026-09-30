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

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
sys.path.insert(0, str(ROOT / 'scripts'))
from ctw_adviser.build import build_snapshot
from ctw_adviser.queries import Queries, ResolutionError
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
        self.assertIn('health_below_25%', passive['summary'])
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
