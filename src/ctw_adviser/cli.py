"""Offline build, inspection, resolution and evidence commands."""
import argparse
import json
import sqlite3
from pathlib import Path

from .build import build_snapshot
from .store import inspect_snapshot
from .queries import Queries, ResolutionError
from .model import movement_phase
from .combat import evaluate_matchup


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    build = commands.add_parser('build')
    build.add_argument('--ctw-root', type=Path, required=True)
    build.add_argument('--output', type=Path, required=True)
    inspect = commands.add_parser('inspect')
    inspect.add_argument('snapshot', type=Path)
    movement = commands.add_parser('movement-phase', help='Illustrative straight-line contact and range-entry timing')
    movement.add_argument('--db', type=Path, required=True)
    movement.add_argument('unit_a')
    movement.add_argument('unit_b')
    movement.add_argument('--separation-metres', type=float, required=True)
    movement.add_argument('--order-a', choices=('approach', 'hold', 'retreat'), default='approach')
    movement.add_argument('--order-b', choices=('approach', 'hold', 'retreat'), default='approach')
    movement.add_argument('--metres-per-second-per-speed-point', type=float, default=1.0)
    movement.add_argument('--subculture-a')
    movement.add_argument('--subculture-b')
    evaluate = commands.add_parser('evaluate', help='Conditional first-order two-unit combat calculation')
    evaluate.add_argument('--db', type=Path, required=True)
    evaluate.add_argument('unit_a')
    evaluate.add_argument('unit_b')
    evaluate.add_argument('--scenario', help='JSON scenario object; defaults are illustrative, not calibrated')
    evaluate.add_argument('--subculture-a')
    evaluate.add_argument('--subculture-b')
    for command in ('resolve', 'unit', 'matchup', 'relations', 'coverage', 'passive', 'detail', 'provenance',
                    'resolve-effect', 'effect', 'unit-effects', 'resolve-character', 'character'):
        query = commands.add_parser(command)
        query.add_argument('--db', type=Path, required=True)
        query.add_argument('keys', nargs='+' if command in ('matchup', 'provenance') else 1)
        query.add_argument('--subculture')
        query.add_argument('--subculture-b')
        query.add_argument('--culture', default=None, help='Source-qualified culture for passive (default *) or effect detail')
        query.add_argument('--unit', help='Restrict effect name resolution to effects linked to this unit')
        query.add_argument('--skill', action='append', help='Exact SKILL_KEY:RANK for character effects (repeatable)')
        query.add_argument('--mode', choices=('combined', 'melee', 'missile'), default='combined')
        query.add_argument('--section', choices=('components', 'weapons', 'attributes', 'abilities', 'activated_options'))
        query.add_argument('--limit', type=int, default=32)
        query.add_argument('--cursor')
        query.add_argument('--include-diagnostics', action='store_true', help='Include development coverage notes for inspection')
        query.add_argument('--include-provenance', action='store_true', help='Expand source and provenance dictionaries (default: deferred)')
        if command == 'passive':
            query.add_argument('--include-graph', action='store_true', help='Expand the raw source graph and lineage')
            query.add_argument('--include-documentation', action='store_true', help='Include the optional reviewed explanation source-documentation link')
        query.add_argument('--scenario', help='JSON object echoed as caller context; never applied')
    args = parser.parse_args()
    try:
        if args.command == 'build':
            result = build_snapshot(args.ctw_root, args.output)
        elif args.command == 'inspect':
            result = inspect_snapshot(args.snapshot)
        elif args.command == 'movement-phase':
            with Queries(args.db) as queries:
                result = movement_phase(queries, args.unit_a, args.unit_b,
                                        separation_metres=args.separation_metres,
                                        order_a=args.order_a, order_b=args.order_b,
                                        metres_per_second_per_speed_point=args.metres_per_second_per_speed_point,
                                        subculture_a=args.subculture_a, subculture_b=args.subculture_b)
        elif args.command == 'evaluate':
            with Queries(args.db) as queries:
                result = evaluate_matchup(queries, args.unit_a, args.unit_b,
                                          scenario=json.loads(args.scenario) if args.scenario else None,
                                          subculture_a=args.subculture_a, subculture_b=args.subculture_b)
        else:
            with Queries(args.db) as queries:
                key = args.keys[0]
                options = dict(mode=args.mode, subculture=args.subculture, section=args.section,
                               cursor=args.cursor, limit=args.limit,
                               scenario=json.loads(args.scenario) if args.scenario else None,
                               include_diagnostics=args.include_diagnostics, include_provenance=args.include_provenance)
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
                    result = queries.get_passive_detail(key, culture=args.culture or '*', limit=args.limit, cursor=args.cursor,
                                                        include_diagnostics=args.include_diagnostics,
                                                        include_provenance=args.include_provenance,
                                                        include_documentation=args.include_documentation, include_graph=args.include_graph)
                elif args.command == 'resolve-effect':
                    result = queries.resolve_effect(key, args.unit, args.subculture)
                elif args.command == 'effect':
                    result = queries.get_effect(key, unit=args.unit, subculture=args.subculture, culture=args.culture,
                                                limit=args.limit, cursor=args.cursor,
                                                include_diagnostics=args.include_diagnostics,
                                                include_provenance=args.include_provenance)
                elif args.command == 'resolve-character':
                    result = queries.resolve_character(key)
                elif args.command == 'character':
                    result = queries.get_character_effects(key, skills=args.skill,
                                                           limit=args.limit, cursor=args.cursor,
                                                           include_provenance=args.include_provenance)
                elif args.command == 'unit-effects':
                    result = queries.get_unit_effects(key, subculture=args.subculture,
                                                      include_provenance=args.include_provenance)
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

