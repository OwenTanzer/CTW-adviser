#!/usr/bin/env python3
"""Compare frozen Claude fixtures with the source-backed local calculator."""

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db', required=True)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    manifest = json.loads((ROOT / 'docs/claude-fixtures.json').read_text(encoding='utf-8'))
    results = []
    for case in manifest['cases']:
        params = case['arguments']
        expected = json.loads((ROOT / case['expected_result']).read_text(encoding='utf-8'))
        command = [sys.executable, '-m', 'ctw_adviser.cli', 'evaluate', '--db', args.db,
                   params['unit_a'], params['unit_b'], '--scenario',
                   json.dumps(params['scenario'])]
        run = subprocess.run(command, cwd=ROOT, capture_output=True, text=True,
                             encoding='utf-8', env={**os.environ, 'PYTHONPATH': 'src',
                                                     'PYTHONIOENCODING': 'utf-8'})
        actual = json.loads(run.stdout) if run.returncode == 0 else None
        ok = (actual == expected and expected['snapshot']['commit'] ==
              case['expected_source_commit'] and expected['model_version'] ==
              case['expected_model_version'])
        results.append({'id': case['id'], 'equal': ok, 'exit_code': run.returncode,
                        'stderr': run.stderr})
    report = {'status': 'passed' if len(results) == 10 and all(x['equal'] for x in results)
              else 'failed', 'cases': len(results), 'results': results}
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'status': report['status'], 'cases': report['cases']}))
    return 0 if report['status'] == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
