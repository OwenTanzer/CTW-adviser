"""Build a verified local SQLite artifact and write its distributable manifest.

No package installation is needed. Both outputs are local files; neither is
committed or uploaded by this command.
"""
import argparse
import hashlib
import json
import platform
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from ctw_adviser.build import build_snapshot
from ctw_adviser.store import inspect_snapshot


def file_sha256(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def git_head():
    result = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=ROOT,
                            capture_output=True, text=True, check=True)
    return result.stdout.strip()


def git_dirty():
    result = subprocess.run(['git', 'status', '--porcelain'], cwd=ROOT,
                            capture_output=True, text=True, check=True)
    return bool(result.stdout.strip())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ctw-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--manifest', type=Path, required=True)
    args = parser.parse_args()
    output, manifest = args.output.resolve(), args.manifest.resolve()
    if output == manifest:
        parser.error('database and manifest paths must differ')
    if manifest.is_relative_to(args.ctw_root.resolve()):
        parser.error('manifest must not modify the CTW-data source directory')
    started = time.perf_counter()
    build_report = build_snapshot(args.ctw_root, output)
    build_seconds = time.perf_counter() - started
    inspection = inspect_snapshot(output)
    if inspection['integrity'] != 'ok' or inspection['foreign_key_errors']:
        raise ValueError('built artifact failed integrity or foreign-key inspection')
    lock = json.loads((ROOT / 'source_lock.json').read_text(encoding='utf-8'))
    if inspection['snapshot']['source_commit'] != lock['source_commit']:
        raise ValueError('built artifact source commit differs from lock')
    report = {
        'format': 'ctw-adviser-local-rebuild-manifest-v1',
        'adviser_commit': git_head(),
        'adviser_worktree_dirty': git_dirty(),
        'source_repository': lock['source_repository'],
        'source_commit': lock['source_commit'],
        'source_tree': lock['source_tree'],
        'source_contract_sha256': lock['contract_sha256'],
        'artifact': {'file': output.name, 'bytes': output.stat().st_size,
                     'sha256': file_sha256(output)},
        'build_seconds': build_seconds,
        'runtime': {'python': platform.python_version(), 'sqlite': sqlite3.sqlite_version,
                    'os': platform.platform(), 'machine': platform.machine(),
                    'processor': platform.processor()},
        'snapshot': inspection['snapshot'],
        'counts': {key: inspection[key] for key in
                   ('roster_rows', 'unit_profiles', 'source_unit_keys', 'classifications')},
        'build_query_plans': build_report['query_plans'],
    }
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(json.dumps(report, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    print(json.dumps({'status': 'passed', 'database': str(output), 'manifest': str(manifest),
                      'sha256': report['artifact']['sha256'], 'bytes': report['artifact']['bytes'],
                      'build_seconds': build_seconds}))


if __name__ == '__main__':
    main()
