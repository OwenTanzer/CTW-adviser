"""Local artifact verification against pinned inputs and adversarial copies."""
from contextlib import closing
import copy
import hashlib
import json
from pathlib import Path
import platform
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from verify_release import verify

class ReleaseVerificationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.directory = Path(cls.temp.name)
        cls.database = cls.directory / 'adviser.sqlite'
        cls.manifest_path = cls.directory / 'adviser.manifest.json'
        lock = json.loads((ROOT / 'source_lock.json').read_text(encoding='utf-8'))
        contract = json.loads((ROOT / 'schema/import_contract.json').read_text(encoding='utf-8'))
        snapshot = {
            'id': lock['source_commit'] + ':' + lock['contract_sha256'] + ':store4',
            'schema_version': 4, 'source_commit': lock['source_commit'],
            'contract_sha256': lock['contract_sha256'],
            'baseline_json': json.dumps(contract['baseline'], sort_keys=True, separators=(',', ':')),
            'owners_json': json.dumps(lock['owners'], sort_keys=True, separators=(',', ':')),
            'coverage_json': '{}',
        }
        with closing(sqlite3.connect(cls.database)) as db, db:
            db.executescript((ROOT / 'schema/store.sql').read_text(encoding='utf-8'))
            db.executescript('CREATE TABLE unit_availability(id INTEGER); '
                             'CREATE TABLE unit_profiles(id INTEGER); '
                             'CREATE TABLE unit_aliases(id INTEGER);')
            db.execute('INSERT INTO snapshot VALUES(?,?,?,?,?,?,?)', tuple(snapshot.values()))
        head = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=ROOT, capture_output=True,
                              text=True, check=True).stdout.strip()
        cls.manifest = {
            'format': 'ctw-adviser-local-rebuild-manifest-v1',
            'adviser_commit': head, 'adviser_worktree_dirty': False,
            'source_repository': lock['source_repository'],
            'source_commit': lock['source_commit'], 'source_tree': lock['source_tree'],
            'source_contract_sha256': lock['contract_sha256'],
            'artifact': {'file': cls.database.name, 'bytes': cls.database.stat().st_size,
                         'sha256': hashlib.sha256(cls.database.read_bytes()).hexdigest()},
            'build_seconds': 1.0,
            'runtime': {'python': platform.python_version(), 'sqlite': sqlite3.sqlite_version,
                        'os': platform.platform(), 'machine': platform.machine() or 'test',
                        'processor': platform.processor()},
            'snapshot': snapshot,
            'counts': {'roster_rows': 0, 'unit_profiles': 0, 'source_unit_keys': 0,
                       'classifications': {}},
            'build_query_plans': {key: ['SEARCH synthetic fixture'] for key in
                ('unit_key', 'unit_name', 'source_unit_name', 'alias_key', 'relations', 'reverse_edge',
                 'effect_key', 'effect_name', 'unit_effects', 'effect_units', 'effect_variant_reverse')},
        }
        cls.manifest_path.write_text(json.dumps(cls.manifest), encoding='utf-8')

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def manifest_copy(self, name, data):
        path = self.directory / name
        path.write_text(json.dumps(data), encoding='utf-8')
        return path

    def database_copy(self, name, mutation):
        path = self.directory / name
        shutil.copyfile(self.database, path)
        with closing(sqlite3.connect(path)) as db, db:
            mutation(db)
        data = copy.deepcopy(self.manifest)
        data['artifact'] = {'file': name, 'bytes': path.stat().st_size,
                            'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
        return path, data

    def test_supported_fixture_and_expected_revision(self):
        result = verify(self.database, self.manifest_path,
                        expected_adviser_commit=self.manifest['adviser_commit'])
        self.assertEqual(result['sha256'], self.manifest['artifact']['sha256'])
        with self.assertRaisesRegex(ValueError, 'adviser commit differs'):
            verify(self.database, self.manifest_path, expected_adviser_commit='0' * 40)

    def test_manifest_shape_types_and_identity(self):
        mutations = [
            ('list', []),
            ('missing', {k: v for k, v in self.manifest.items() if k != 'snapshot'}),
            ('bad_artifact_type', {**self.manifest, 'artifact': []}),
            ('bad_size_type', {**self.manifest, 'artifact': {**self.manifest['artifact'], 'bytes': True}}),
            ('bad_adviser', {**self.manifest, 'adviser_commit': '0' * 40}),
            ('wrong_tree', {**self.manifest, 'source_tree': '0' * 40}),
            ('wrong_contract', {**self.manifest, 'source_contract_sha256': '0' * 64}),
            ('wrong_schema', {**self.manifest, 'snapshot': {**self.manifest['snapshot'], 'schema_version': 999}}),
            ('wrong_count', {**self.manifest, 'counts': {**self.manifest['counts'], 'unit_profiles': 1}}),
            ('bad_runtime', {**self.manifest, 'runtime': {**self.manifest['runtime'], 'python': 'old'}}),
            ('bad_build_time', {**self.manifest, 'build_seconds': -1}),
            ('dirty', {**self.manifest, 'adviser_worktree_dirty': True}),
            ('bad_plans', {**self.manifest, 'build_query_plans': []}),
        ]
        for name, data in mutations:
            with self.subTest(name=name), self.assertRaises(ValueError):
                verify(self.database, self.manifest_copy(name + '.json', data))

    def test_malformed_json_list_gets_structured_cli_failure(self):
        path = self.manifest_copy('list-cli.json', [])
        result = subprocess.run([sys.executable, str(ROOT / 'scripts/verify_release.py'),
            '--db', str(self.database), '--manifest', str(path)],
            capture_output=True, text=True)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(json.loads(result.stderr)['status'], 'failed')
        self.assertNotIn('Traceback', result.stderr)

    def test_recomputed_hash_does_not_hide_unsupported_schema(self):
        def mutate(db):
            db.execute('PRAGMA ignore_check_constraints=ON')
            db.execute('UPDATE snapshot SET schema_version=999')
        path, data = self.database_copy('wrong-schema.sqlite', mutate)
        with self.assertRaisesRegex(ValueError, 'unsupported snapshot schema'):
            verify(path, self.manifest_copy('wrong-schema.json', data))
        data['snapshot']['schema_version'] = 999
        with self.assertRaisesRegex(ValueError, 'unsupported snapshot schema'):
            verify(path, self.manifest_copy('wrong-schema-declared.json', data))

    def test_recomputed_hash_does_not_hide_unsupported_contract(self):
        path, data = self.database_copy('wrong-contract.sqlite',
            lambda db: db.execute('UPDATE snapshot SET contract_sha256=?', ('0' * 64,)))
        with self.assertRaisesRegex(ValueError, 'unsupported snapshot schema or import contract'):
            verify(path, self.manifest_copy('wrong-contract.json', data))

    def test_recomputed_hash_does_not_hide_foreign_key_error(self):
        def mutate(db):
            db.execute('PRAGMA foreign_keys=OFF')
            db.execute("INSERT INTO source_files VALUES(?,?,?,?,?,?,?,?,?)",
                ('invented.csv', 'missing-snapshot', '0' * 64, '0' * 64, 1,
                 'units', None, 0, 'invented test row'))
        path, data = self.database_copy('broken-fk.sqlite', mutate)
        with self.assertRaisesRegex(ValueError, 'foreign-key inspection'):
            verify(path, self.manifest_copy('broken-fk.json', data))

    def test_recomputed_hash_does_not_hide_snapshot_or_count_difference(self):
        path, data = self.database_copy('changed-coverage.sqlite',
            lambda db: db.execute('UPDATE snapshot SET coverage_json=?', ('{"changed":true}',)))
        with self.assertRaisesRegex(ValueError, 'snapshot metadata differs'):
            verify(path, self.manifest_copy('changed-coverage.json', data))
        altered = copy.deepcopy(self.manifest)
        altered['counts']['unit_profiles'] += 1
        with self.assertRaisesRegex(ValueError, 'unit_profiles differs'):
            verify(self.database, self.manifest_copy('changed-count.json', altered))

    def test_recomputed_hash_does_not_hide_second_snapshot_identity(self):
        def mutate(db):
            db.execute('INSERT INTO snapshot SELECT id || ":extra", schema_version, '
                       'source_commit, contract_sha256, baseline_json, owners_json, '
                       'coverage_json FROM snapshot')
        path, data = self.database_copy('second-snapshot.sqlite', mutate)
        with self.assertRaisesRegex(ValueError, 'exactly one snapshot'):
            verify(path, self.manifest_copy('second-snapshot.json', data))
