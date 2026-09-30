"""Offline build, inspection, resolution and evidence commands."""
import argparse
import json
import sqlite3
from pathlib import Path

from .build import build_snapshot
from .store import inspect_snapshot
from .queries import Queries, ResolutionError


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    build = commands.add_parser('build')
    build.add_argument('--ctw-root', type=Path, required=True)
    build.add_argument('--output', type=Path, required=True)
    inspect = commands.add_parser('inspect')
    inspect.add_argument('snapshot', type=Path)
    for command in ('resolve', 'unit', 'matchup', 'relations', 'coverage', 'passive', 'detail', 'provenance'):
        query = commands.add_parser(command)
        query.add_argument('--db', type=Path, required=True)
        query.add_argument('keys', nargs='+' if command in ('matchup', 'provenance') else 1)
        query.add_argument('--subculture')
        query.add_argument('--subculture-b')
        query.add_argument('--culture', default='*', help='Source-qualified culture for passive detail')
        query.add_argument('--mode', choices=('combined', 'melee', 'missile'), default='combined')
        query.add_argument('--section', choices=('components', 'weapons', 'attributes', 'abilities', 'activated_options'))
        query.add_argument('--limit', type=int, default=32)
        query.add_argument('--cursor')
        query.add_argument('--include-diagnostics', action='store_true', help='Include development coverage notes for inspection')
        query.add_argument('--scenario', help='JSON object echoed as caller context; never applied')
    args = parser.parse_args()
    try:
        if args.command == 'build':
            result = build_snapshot(args.ctw_root, args.output)
        elif args.command == 'inspect':
            result = inspect_snapshot(args.snapshot)
        else:
            with Queries(args.db) as queries:
                key = args.keys[0]
                options = dict(mode=args.mode, subculture=args.subculture, section=args.section,
                               cursor=args.cursor, limit=args.limit,
                               scenario=json.loads(args.scenario) if args.scenario else None,
                               include_diagnostics=args.include_diagnostics)
                if args.command == 'resolve':
                    result = queries.resolve_unit(key, args.subculture)
                elif args.command == 'matchup':
                    if len(args.keys) != 2:
                        raise ValueError('matchup requires two units')
                    result = queries.get_matchup_evidence(*args.keys, subculture_b=args.subculture_b, **options)
                elif args.command in ('unit', 'relations'):
                    result = queries.get_unit_profile(key, **options)
                elif args.command == 'coverage':
                    result = queries.get_coverage_notes(key, **options)
                elif args.command == 'passive':
                    result = queries.get_passive_detail(key, culture=args.culture, limit=args.limit, cursor=args.cursor,
                                                        include_diagnostics=args.include_diagnostics)
                elif args.command == 'detail':
                    result = queries.get_detail(key, limit=args.limit, cursor=args.cursor)
                else:
                    result = queries.get_provenance(args.keys)
    except ResolutionError as exc:
        print(json.dumps(exc.result, ensure_ascii=False))
        return 2
    except (ValueError, OSError, KeyError, sqlite3.Error) as exc:
        print(json.dumps({'status': 'failed', 'error': str(exc)}))
        return 1
    print(json.dumps(result, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
