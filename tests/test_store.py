"""Phase-2 integration checks against the pinned source, with no committed DB."""
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from ctw_adviser.build import (build_snapshot, classification, compact, load_records,
                              select_records, table_name, ROOT as BUILD_ROOT)
from ctw_adviser.store import convert, open_snapshot, quote


class StoreContractTests(unittest.TestCase):
    def test_missing_classification_is_unresolved(self):
        self.assertEqual(classification({}, None), 'unresolved')
        self.assertEqual(classification(None, {'passive': 'true'}), 'unresolved')
        self.assertEqual(classification({}, {'passive': 'false'}), 'activated_option')
        self.assertEqual(classification({}, {'passive': 'true'}), 'core_passive')

    def test_cycle_and_distinct_recipient_edges_survive_selection(self):
        # Tiny invented graph tests traversal, never game claims.
        from ctw_adviser.build import DEFINITION, CASTING, ABILITY_LINK
        a, b = 'a.csv', 'b.csv'
        specs = {a: {'role': 'unit_relation'}, b: {'role': 'selected_native_definition'},
                 DEFINITION: {'role': 'selected_native_definition'},
                 CASTING: {'role': 'selected_native_definition'}, ABILITY_LINK: {'role': 'unit_relation'}}
        records = {a: {'a1': (2, {'key': 'one', 'next': 'two'}),
                       'a2': (3, {'key': 'one-friends', 'next': 'two'})},
                   b: {'b1': (2, {'key': 'two', 'next': 'one'})},
                   DEFINITION: {}, CASTING: {}, ABILITY_LINK: {}}
        edges = [{'source': a, 'target': b, 'source_columns': ['next'], 'target_columns': ['key'], 'reverse': False},
                 {'source': b, 'target': a, 'source_columns': ['next'], 'target_columns': ['key'], 'reverse': False}]
        selected, _, _ = select_records(specs, records, edges)
        self.assertEqual(selected, {'a1', 'a2', 'b1'})


SOURCE = Path(os.environ.get('CTW_DATA_ROOT', ROOT.parent / 'CTW-data'))


@unittest.skipUnless((SOURCE / 'data/unit_stats/dataset_manifest.json').exists(),
                     'set CTW_DATA_ROOT to the pinned CTW-data checkout for integration checks')
class PinnedStoreTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.directory = Path(cls.temp.name)
        cls.output = cls.directory / 'units.sqlite'
        cls.report = build_snapshot(SOURCE, cls.output)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_complete_roster_and_shared_identity(self):
        self.assertEqual(self.report['roster_rows'], 3181)
        self.assertEqual(self.report['unit_identities']['roster'], 2409)
        self.assertEqual(self.report['integrity'], 'ok')
        self.assertFalse(self.report['foreign_key_errors'])
        with closing(open_snapshot(self.output)) as db:
            # Shared inclusion is several profile rows, with one main-unit identity.
            self.assertGreater(db.execute('SELECT count(*) FROM unit_profiles WHERE unit_key=?',
                                         ('wh3_main_tze_inf_blue_horrors_0',)).fetchone()[0], 1)
            self.assertEqual(db.execute('SELECT count(*) FROM unit_identity WHERE unit_key=?',
                                       ('wh3_main_tze_inf_blue_horrors_0',)).fetchone()[0], 1)

    def test_every_retained_native_field_matches_source(self):
        contract = json.loads((ROOT / 'schema/import_contract.json').read_text(encoding='utf-8'))
        with closing(open_snapshot(self.output)) as db:
            for spec in contract['datasets']:
                spec = dict(spec, columns=contract['column_schemas'][spec['columns_ref']]
                            if 'columns_ref' in spec else spec['columns'])
                path = spec['path']
                rows = load_records(SOURCE, spec)
                for provenance in db.execute('SELECT id,retention FROM record_provenance WHERE source_file=?', (path,)):
                    rid, retention = provenance
                    name = table_name(path, spec['role']) + ('_metadata' if retention == 'option_metadata' else '')
                    actual = dict(db.execute(f'SELECT * FROM {quote(name)} WHERE record_id=?', (rid,)).fetchone())
                    source = rows[rid][1]
                    expected = {c['name']: convert(source[c['name']], c['type']) for c in spec['columns']
                                if c['name'] in actual}
                    self.assertEqual({k: v for k, v in actual.items() if k != 'record_id'}, expected, rid)

    def test_passive_roots_and_activated_payload_exclusion(self):
        with closing(open_snapshot(self.output)) as db:
            for key in ('wh2_main_unit_passive_martial_prowess', 'wh3_dlc24_unit_passive_spawn_kin_kroxigors'):
                self.assertEqual(db.execute('SELECT classification FROM ability_option_metadata WHERE ability_key=?',
                                            (key,)).fetchone()[0], 'core_passive')
                self.assertGreater(db.execute('SELECT count(*) FROM native_ability_phase_links WHERE special_ability=?',
                                              (key,)).fetchone()[0], 0)
            for cid, in db.execute("SELECT casting_record FROM ability_option_metadata WHERE classification='activated_option'"):
                self.assertIsNone(db.execute('SELECT record_id FROM native_ability_casting WHERE record_id=?', (cid,)).fetchone())
                self.assertIsNotNone(db.execute('SELECT record_id FROM native_ability_casting_metadata WHERE record_id=?', (cid,)).fetchone())
            self.assertEqual(db.execute('SELECT count(*) FROM unit_abilities').fetchone()[0], 8065)

    def test_native_nulls_components_and_contact_groups(self):
        with closing(open_snapshot(self.output)) as db:
            self.assertEqual([tuple(r) for r in db.execute(
                'SELECT component_count,can_be_targeted FROM unit_components WHERE unit_key=? ORDER BY component_count',
                ('wh_main_grn_art_doom_diver_catapult',))], [(4.0, 1), (40.0, None)])
            self.assertEqual(db.execute('SELECT count(*) FROM native_special_ability_contact_phase_groups').fetchone()[0], 4)
            self.assertEqual(db.execute('SELECT count(*) FROM relation_edges WHERE relation LIKE ? AND target_key_json=?',
                ('%.contact_group', compact(('wh3_dlc29_vmp_morghast_halberd_ror_contact_group',)))).fetchone()[0], 4)
            self.assertGreater(db.execute('SELECT count(*) FROM native_ability_casting WHERE target_intercept_range<0').fetchone()[0], 0)
            self.assertEqual(db.execute('SELECT barrier_health FROM unit_profiles WHERE unit_key=? LIMIT 1',
                ('wh3_main_tze_inf_blue_horrors_0',)).fetchone()[0], 1400)

    def test_payload_lineage_and_condition_text(self):
        with closing(open_snapshot(self.output)) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM record_lineage').fetchone()[0],
                             db.execute('SELECT count(*) FROM projectiles').fetchone()[0] +
                             db.execute('SELECT count(*) FROM explosions').fetchone()[0])
            self.assertIsNotNone(db.execute('SELECT text FROM localization WHERE key=?',
                ('special_ability_invalid_usage_flags_alt_description_health_below_25%',)).fetchone())

    def test_read_only_and_indexed_access(self):
        with closing(open_snapshot(self.output)) as db:
            with self.assertRaises(sqlite3.OperationalError):
                db.execute('DELETE FROM snapshot')
        for plan in self.report['query_plans'].values():
            self.assertTrue(all('SEARCH ' in step for step in plan))

    def test_failed_candidate_preserves_installed_bytes(self):
        before = self.output.read_bytes()
        def reject(candidate):
            raise ValueError('injected pre-install failure')
        with self.assertRaisesRegex(ValueError, 'injected'):
            build_snapshot(SOURCE, self.output, before_install=reject)
        self.assertEqual(self.output.read_bytes(), before)
        self.assertFalse(list(self.directory.glob('*.candidate')))

    def test_corrupt_input_and_failed_metadata_leave_artifact(self):
        lock = json.loads((ROOT / 'source_lock.json').read_text(encoding='utf-8'))
        copied = self.directory / 'source'
        for entry in lock['files']:
            dest = copied / entry['path']
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(SOURCE / entry['path'], dest)
        before = self.output.read_bytes()
        path = copied / 'data/unit_stats/audit_report.json'
        path.write_text('{"status":"failed","errors":["injected"]}', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'source verification failed'):
            build_snapshot(copied, self.output)
        self.assertEqual(self.output.read_bytes(), before)

    def test_deterministic_rebuild(self):
        other = self.directory / 'second.sqlite'
        build_snapshot(SOURCE, other)
        self.assertEqual(hashlib.sha256(self.output.read_bytes()).digest(),
                         hashlib.sha256(other.read_bytes()).digest())

    def test_refuse_output_in_source_tree(self):
        with self.assertRaisesRegex(ValueError, 'source directory'):
            build_snapshot(SOURCE, SOURCE / 'do-not-create.sqlite')


if __name__ == '__main__':
    unittest.main()
