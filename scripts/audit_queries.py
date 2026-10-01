"""Reproduce roster-wide retrieval, source-locator and performance evidence."""
import argparse
import csv
import json
from pathlib import Path
import platform
import sqlite3
import statistics
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from ctw_adviser.queries import Queries
from validate_packets import validate, packet_checks


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db', type=Path, required=True)
    parser.add_argument('--ctw-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, default=ROOT / 'work/query-audit.json')
    args = parser.parse_args()
    schema = json.loads((ROOT / 'schema/evidence_packet.schema.json').read_text())
    started = time.perf_counter()
    q = Queries(args.db)
    startup = time.perf_counter() - started
    source_rows = {}; checked = set(); errors = []; sizes = []; latencies = []; partials = []; maximum = (0, None)
    unit_count = 0
    with q:
        keys = [r[0] for r in q.db.execute('SELECT unit_key FROM unit_aliases ORDER BY unit_key')]
        for index, key in enumerate(keys):
            try:
                start = time.perf_counter(); packet = q.get_unit_profile(key)
                latencies.append(time.perf_counter() - start)
                validate(packet, schema, schema); packet_checks(packet)
                size = len(json.dumps(packet, separators=(',', ':'), ensure_ascii=False).encode())
                sizes.append(size)
                if size > maximum[0]:
                    maximum = (size, key)
                for section in packet['units'][0]['coverage']['sections']:
                    if section['state'] == 'partial':
                        partials.append({'unit': key, 'section': section['name'], 'total': section['total']})
                for rid, evidence in packet['provenance'].items():
                    if rid in checked:
                        continue
                    path = packet['sources'][evidence['source_id']]['path']
                    if path not in source_rows:
                        with (args.ctw_root / path).open(encoding='utf-8', newline='') as f:
                            source_rows[path] = list(csv.DictReader(f, delimiter='\t' if path.endswith('.tsv') else ','))
                    row = source_rows[path][evidence['logical_record'] - 2]
                    if any(row[k] != v for k, v in evidence['key'].items()):
                        raise ValueError('source locator mismatch: ' + rid)
                    physical = row
                    if 'source_line' not in row and evidence.get('lineage_refs'):
                        lineage = packet['provenance'][evidence['lineage_refs'][0]]
                        lineage_path = packet['sources'][lineage['source_id']]['path']
                        if lineage_path not in source_rows:
                            with (args.ctw_root / lineage_path).open(encoding='utf-8', newline='') as f:
                                source_rows[lineage_path] = list(csv.DictReader(f, delimiter='\t' if lineage_path.endswith('.tsv') else ','))
                        physical = source_rows[lineage_path][lineage['logical_record'] - 2]
                    if evidence['source_line'] is not None and str(evidence['source_line']) != physical.get('source_line'):
                        raise ValueError('native physical source line mismatch: ' + rid)
                    if evidence['source_patch'] is not None and evidence['source_patch'] != physical.get('source_patch'):
                        raise ValueError('native source patch mismatch: ' + rid)
                    if evidence.get('source_path') is not None and evidence['source_path'] != physical.get('source_path'):
                        raise ValueError('native source path mismatch: ' + rid)
                    checked.add(rid)
                unit_count += 1
            except Exception as exc:
                errors.append({'unit': key, 'error': str(exc)})
            if index % 400 == 0:
                print(json.dumps({'checked': index, 'errors': len(errors)}), flush=True)
        samples = []
        for _ in range(100):
            start = time.perf_counter()
            q.get_matchup_evidence('Lothern Sea Guard', 'Blue Horrors of Tzeentch')
            samples.append(time.perf_counter() - start)
        plans = {}
        for label, sql, key in [('name', 'SELECT * FROM unit_profiles WHERE unit_name=? COLLATE NOCASE', 'Kroxigor'),
                                ('source_name', 'SELECT * FROM unit_profiles WHERE source_unit_name=? COLLATE NOCASE', 'Teclis'),
                                ('abilities', 'SELECT * FROM unit_abilities WHERE unit_key=?', 'wh2_main_lzd_mon_kroxigors'),
                                ('phase_effects', 'SELECT * FROM native_phase_stat_effects WHERE phase=?', 'wh2_main_unit_passive_martial_prowess')]:
            plans[label] = [r[3] for r in q.db.execute('EXPLAIN QUERY PLAN ' + sql, (key,))]
        report = {'status': 'passed' if not errors else 'failed', 'source_commit': q.snapshot['source_commit'],
                  'packet_version': packet['schema_version'], 'runtime': {'python': platform.python_version(), 'sqlite': sqlite3.sqlite_version,
                                                       'os': platform.platform(), 'machine': platform.machine(), 'processor': platform.processor()},
                  'checked_unit_keys': unit_count, 'checked_source_locators': len(checked), 'errors': errors,
                  'partial_sections': partials, 'startup_seconds': startup,
                  'unit_latency_median_ms': statistics.median(latencies) * 1000,
                  'unit_latency_p95_ms': sorted(latencies)[int(len(latencies) * .95)] * 1000,
                  'pair_latency_median_ms': statistics.median(samples) * 1000,
                  'packet_bytes_median': statistics.median(sizes), 'largest_packet': {'bytes': maximum[0], 'unit': maximum[1]},
                  'database_bytes': args.db.stat().st_size, 'query_plans': plans,
                  'elapsed_seconds': time.perf_counter() - started}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k: v for k, v in report.items() if k not in ('errors', 'partial_sections', 'query_plans')}))
    return int(bool(errors))


if __name__ == '__main__':
    raise SystemExit(main())
