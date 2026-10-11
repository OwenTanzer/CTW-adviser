"""Check a local rebuild manifest against its supported SQLite snapshot.

The manifest checks identity and accidental corruption, not authorship. By
default its adviser revision must equal this checkout's HEAD; an independently
known revision can be supplied with --expected-adviser-commit.
"""
import argparse
from contextlib import closing
import hashlib
import json
import math
import re
import sqlite3
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from ctw_adviser.store import SUPPORTED_CONTRACT_SHA256, inspect_snapshot, open_snapshot

SHA40 = re.compile(r'[0-9a-f]{40}\Z')
SHA64 = re.compile(r'[0-9a-f]{64}\Z')
VERSION = re.compile(r'\d+\.\d+(?:\.\d+)?\Z')
TOP_KEYS = {'format', 'adviser_commit', 'adviser_worktree_dirty',
            'source_repository', 'source_commit', 'source_tree',
            'source_contract_sha256', 'artifact', 'build_seconds', 'runtime',
            'snapshot', 'counts', 'build_query_plans'}
SNAPSHOT_KEYS = {'id', 'schema_version', 'source_commit', 'contract_sha256',
                 'baseline_json', 'owners_json', 'coverage_json'}
PLAN_KEYS = {'unit_key', 'unit_name', 'source_unit_name', 'alias_key',
             'relations', 'reverse_edge', 'effect_key', 'effect_name',
             'unit_effects', 'effect_units', 'effect_variant_reverse'}


def sha256(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def fields(value, name, expected):
    if type(value) is not dict:
        raise ValueError(f'{name} must be a JSON object')
    missing, extra = expected - value.keys(), value.keys() - expected
    if missing or extra:
        raise ValueError(f'{name} fields differ: missing={sorted(missing)}, extra={sorted(extra)}')
    return value


def string(value, name, pattern=None, *, allow_empty=False):
    if type(value) is not str or (not value and not allow_empty):
        raise ValueError(f'{name} must be a nonempty string' if not allow_empty else f'{name} must be a string')
    if pattern and not pattern.fullmatch(value):
        raise ValueError(f'{name} has invalid format')
    return value


def integer(value, name, *, minimum=0):
    if type(value) is not int or value < minimum:
        raise ValueError(f'{name} must be an integer >= {minimum}')
    return value


def json_object(value, name):
    string(value, name)
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        raise ValueError(f'{name} is not valid JSON') from exc
    if type(parsed) is not dict:
        raise ValueError(f'{name} must encode a JSON object')
    return parsed


def validate_manifest(data, *, expected_adviser_commit=None):
    fields(data, 'manifest', TOP_KEYS)
    if data['format'] != 'ctw-adviser-local-rebuild-manifest-v1':
        raise ValueError('unsupported manifest format')
    string(data['adviser_commit'], 'adviser_commit', SHA40)
    if type(data['adviser_worktree_dirty']) is not bool:
        raise ValueError('adviser_worktree_dirty must be a boolean')
    if data['adviser_worktree_dirty']:
        raise ValueError('release artifact was built from a dirty adviser worktree')
    if expected_adviser_commit is None:
        result = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=ROOT,
                                capture_output=True, text=True, check=True)
        expected_adviser_commit = result.stdout.strip()
    string(expected_adviser_commit, 'expected_adviser_commit', SHA40)
    if data['adviser_commit'] != expected_adviser_commit:
        raise ValueError('adviser commit differs from expected revision')
    for name, pattern in (('source_commit', SHA40), ('source_tree', SHA40),
                          ('source_contract_sha256', SHA64)):
        string(data[name], name, pattern)
    string(data['source_repository'], 'source_repository')

    artifact = fields(data['artifact'], 'artifact', {'file', 'bytes', 'sha256'})
    name = string(artifact['file'], 'artifact.file')
    if name in ('.', '..') or Path(name).name != name or '/' in name or '\\' in name:
        raise ValueError('artifact.file must be a basename')
    integer(artifact['bytes'], 'artifact.bytes', minimum=1)
    string(artifact['sha256'], 'artifact.sha256', SHA64)
    if type(data['build_seconds']) not in (int, float) or not math.isfinite(data['build_seconds']) or data['build_seconds'] < 0:
        raise ValueError('build_seconds must be a finite nonnegative number')

    runtime = fields(data['runtime'], 'runtime', {'python', 'sqlite', 'os', 'machine', 'processor'})
    for name in ('python', 'sqlite'):
        string(runtime[name], f'runtime.{name}', VERSION)
    if tuple(int(x) for x in runtime['python'].split('.')[:2]) < (3, 11):
        raise ValueError('unsupported build Python version')
    if tuple(int(x) for x in runtime['sqlite'].split('.')[:2]) < (3, 37):
        raise ValueError('unsupported build SQLite version')
    string(runtime['os'], 'runtime.os')
    string(runtime['machine'], 'runtime.machine')
    string(runtime['processor'], 'runtime.processor', allow_empty=True)

    snapshot = fields(data['snapshot'], 'snapshot', SNAPSHOT_KEYS)
    integer(snapshot['schema_version'], 'snapshot.schema_version', minimum=4)
    if snapshot['schema_version'] != 4:
        raise ValueError('unsupported snapshot schema or import contract; rebuild from pinned sources')
    string(snapshot['id'], 'snapshot.id')
    string(snapshot['source_commit'], 'snapshot.source_commit', SHA40)
    string(snapshot['contract_sha256'], 'snapshot.contract_sha256', SHA64)
    baseline = json_object(snapshot['baseline_json'], 'snapshot.baseline_json')
    owners = json_object(snapshot['owners_json'], 'snapshot.owners_json')
    json_object(snapshot['coverage_json'], 'snapshot.coverage_json')

    counts = fields(data['counts'], 'counts', {'roster_rows', 'unit_profiles',
                                               'source_unit_keys', 'classifications'})
    for name in ('roster_rows', 'unit_profiles', 'source_unit_keys'):
        integer(counts[name], f'counts.{name}')
    classifications = counts['classifications']
    if type(classifications) is not dict:
        raise ValueError('counts.classifications must be a JSON object')
    for name, count in classifications.items():
        string(name, 'counts.classifications key')
        integer(count, f'counts.classifications.{name}')
    plans = fields(data['build_query_plans'], 'build_query_plans', PLAN_KEYS)
    for name, steps in plans.items():
        if type(steps) is not list or not steps:
            raise ValueError(f'build_query_plans.{name} must be a nonempty list')
        for step in steps:
            string(step, f'build_query_plans.{name} step')

    lock = json.loads((ROOT / 'source_lock.json').read_text(encoding='utf-8'))
    contract = json.loads((ROOT / 'schema/import_contract.json').read_text(encoding='utf-8'))
    actual_contract_hash = hashlib.sha256(json.dumps(contract, sort_keys=True,
        separators=(',', ':')).encode()).hexdigest()
    if actual_contract_hash != lock['contract_sha256'] or lock['contract_sha256'] != SUPPORTED_CONTRACT_SHA256:
        raise ValueError('checked-out source lock/import contract is unsupported or inconsistent')
    for name in ('source_repository', 'source_commit', 'source_tree'):
        if data[name] != lock[name]:
            raise ValueError(f'{name} differs from checked-out source lock')
    if (data['source_contract_sha256'] != lock['contract_sha256'] or
        snapshot['contract_sha256'] != lock['contract_sha256'] or
        snapshot['source_commit'] != lock['source_commit']):
        raise ValueError('manifest snapshot source or import contract differs from source lock')
    if snapshot['id'] != f"{lock['source_commit']}:{lock['contract_sha256']}:store4":
        raise ValueError('manifest snapshot ID differs from pinned identity')
    if baseline != contract['baseline'] or owners != lock['owners']:
        raise ValueError('manifest baseline or source owners differ from pin')
    return artifact


def verify(db_path, manifest_path, *, expected_adviser_commit=None):
    data = json.loads(manifest_path.read_text(encoding='utf-8'))
    artifact = validate_manifest(data, expected_adviser_commit=expected_adviser_commit)
    if (db_path.name != artifact['file'] or db_path.stat().st_size != artifact['bytes'] or
            sha256(db_path) != artifact['sha256']):
        raise ValueError('database name, size or SHA-256 differs from manifest')
    inspection = inspect_snapshot(db_path)  # Same schema/contract gate as ordinary queries.
    with closing(open_snapshot(db_path)) as db:
        if db.execute('SELECT count(*) FROM snapshot').fetchone()[0] != 1:
            raise ValueError('database must contain exactly one snapshot identity')
    if inspection['integrity'] != 'ok' or inspection['foreign_key_errors']:
        raise ValueError('database failed SQLite integrity or foreign-key inspection')
    if inspection['snapshot'] != data['snapshot']:
        raise ValueError('database snapshot metadata differs from manifest')
    for name in ('roster_rows', 'unit_profiles', 'source_unit_keys', 'classifications'):
        if inspection[name] != data['counts'][name]:
            raise ValueError(f'database {name} differs from manifest')
    if db_path.stat().st_size != artifact['bytes'] or sha256(db_path) != artifact['sha256']:
        raise ValueError('database changed during verification')
    return {'status': 'passed', 'sha256': artifact['sha256'],
            'source_commit': data['source_commit'], 'adviser_commit': data['adviser_commit']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--db', type=Path, required=True)
    parser.add_argument('--expected-adviser-commit', help='Independently known adviser revision (default: this checkout HEAD)')
    args = parser.parse_args()
    print(json.dumps(verify(args.db, args.manifest,
                            expected_adviser_commit=args.expected_adviser_commit)))


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, KeyError, TypeError, IndexError, UnicodeError, sqlite3.Error,
            subprocess.CalledProcessError) as exc:
        print(json.dumps({'status': 'failed', 'error': str(exc)}), file=sys.stderr)
        raise SystemExit(1)
