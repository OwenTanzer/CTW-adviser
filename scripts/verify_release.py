"""Check a local rebuild manifest against its SQLite file."""
import argparse
import hashlib
import json
import sqlite3
import sys
from pathlib import Path


def sha256(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--db', type=Path, required=True)
    args = parser.parse_args()
    data = json.loads(args.manifest.read_text(encoding='utf-8'))
    if data.get('format') != 'ctw-adviser-local-rebuild-manifest-v1':
        raise ValueError('unsupported manifest format')
    expected = data['artifact']
    if args.db.name != expected['file'] or args.db.stat().st_size != expected['bytes'] or sha256(args.db) != expected['sha256']:
        raise ValueError('database name, size or SHA-256 differs from manifest')
    with sqlite3.connect(f'{args.db.resolve().as_uri()}?mode=ro', uri=True) as db:
        source = db.execute('SELECT source_commit FROM snapshot').fetchone()[0]
        integrity = db.execute('PRAGMA integrity_check').fetchone()[0]
    if source != data['source_commit'] or integrity != 'ok':
        raise ValueError('database source commit or SQLite integrity differs from manifest')
    print(json.dumps({'status': 'passed', 'sha256': expected['sha256'], 'source_commit': source}))


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, KeyError, sqlite3.Error) as exc:
        print(json.dumps({'status': 'failed', 'error': str(exc)}), file=sys.stderr)
        raise SystemExit(1)
