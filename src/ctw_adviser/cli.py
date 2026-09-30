"""Snapshot build/inspection commands; evidence queries follow in phase 3."""
import argparse
import json
import sqlite3
from pathlib import Path

from .build import build_snapshot
from .store import inspect_snapshot


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    build = commands.add_parser('build')
    build.add_argument('--ctw-root', type=Path, required=True)
    build.add_argument('--output', type=Path, required=True)
    inspect = commands.add_parser('inspect')
    inspect.add_argument('snapshot', type=Path)
    args = parser.parse_args()
    try:
        result = (build_snapshot(args.ctw_root, args.output) if args.command == 'build'
                  else inspect_snapshot(args.snapshot))
    except (ValueError, OSError, KeyError, sqlite3.Error) as exc:
        print(json.dumps({'status': 'failed', 'error': str(exc)}))
        return 1
    print(json.dumps(result, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
