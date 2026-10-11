#!/usr/bin/env python3
"""Replay recorded successful connector evaluations through the shared CLI."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db', required=True)
    parser.add_argument('--receipts', default='docs/evidence/closure-20261011/conversations')
    parser.add_argument('--output')
    args = parser.parse_args()
    results = []
    for path in sorted(Path(args.receipts).glob('*/calls.json')):
        for index, call in enumerate(json.loads(path.read_text())):
            name = call.get('tool', call.get('name', ''))
            if not name.endswith('evaluate_single_unit_matchup'):
                continue
            result = call['result']
            result = result.get('value', result)
            envelope = result.get('structuredContent')
            if not envelope or envelope.get('status') != 'ok':
                continue
            inputs = call['arguments']
            command = [sys.executable, '-m', 'ctw_adviser.cli', 'evaluate',
                       '--db', args.db, inputs['unit_a'], inputs['unit_b'],
                       '--scenario', json.dumps(inputs.get('scenario', {}))]
            for side in ('a', 'b'):
                if inputs.get('subculture_' + side):
                    command.extend(['--subculture-' + side, inputs['subculture_' + side]])
            run = subprocess.run(command, capture_output=True, text=True,
                                 env={**os.environ, 'PYTHONPATH': 'src'})
            actual = json.loads(run.stdout) if run.returncode == 0 else None
            results.append({'conversation': path.parent.name, 'call_index': index,
                            'arguments': inputs, 'exit_code': run.returncode,
                            'data_equal': actual == envelope['data'],
                            'stderr': run.stderr})
    passed = bool(results) and all(x['data_equal'] and x['exit_code'] == 0 for x in results)
    report = {'status': 'passed' if passed else 'failed',
              'comparison': 'Parsed JSON equality; object key order and integral-float formatting are not semantic differences.',
              'evaluations': len(results), 'results': results}
    rendered = json.dumps(report, indent=2) + '\n'
    if args.output:
        Path(args.output).write_text(rendered)
    print(json.dumps({'status': report['status'], 'evaluations': len(results)}))
    return 0 if passed else 1


if __name__ == '__main__':
    raise SystemExit(main())
