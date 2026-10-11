"""Record #28 unit-search acceptance queries with totals, response size and latency.

Sizes are the MCP adapter's compact JSON text; latency is the median of five warm
library calls on one open snapshot. These are reproducibility measurements, not
hosted service-level guarantees.

    python scripts/measure_unit_search.py --db work/adviser.sqlite --output docs/unit-search-measurements.json
"""
import argparse
import json
from pathlib import Path
import platform
import sqlite3
import statistics
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from ctw_adviser.mcp import call_tool
from ctw_adviser.queries import Queries
from ctw_adviser.unit_search import EXAMPLES, SEARCH_VERSION

HEF = 'wh2_main_sc_hef_high_elves'
HEF_HEROES = [{'field': 'subculture', 'op': '=', 'value': HEF}, {'field': 'caste', 'op': '=', 'value': 'hero'}]
CASES = [(e['question'], e['search_units']) for e in EXAMPLES] + [
    ('High Elf lords and heroes, one row per variant', {
        'where': {'all': [HEF_HEROES[0], {'field': 'caste', 'op': 'in', 'value': ['lord', 'hero']}]},
        'fields': ['caste', 'mount_relation', 'mount_body'], 'limit': 100}),
] + [(f'High Elf heroes with melee attack {op} 45', {
    'where': {'all': HEF_HEROES + [{'field': 'melee_attack', 'op': op, 'value': 45}]},
    'fields': ['melee_attack'], 'sort': [{'field': 'melee_attack', 'direction': 'desc'}], 'limit': 100})
    for op in ('>', '>=', '<', '<=')] + [
    ('OR-grouped: infantry with armour below 40 or speed above 8', {
        'where': {'all': [{'field': 'unit_type', 'op': '=', 'value': 'infantry'},
                          {'any': [{'field': 'armour', 'op': '<', 'value': 40}, {'field': 'speed', 'op': '>', 'value': 8}]}]},
        'fields': ['armour', 'speed']}),
    ('Every qualified variant, 100 per page', {'fields': ['caste', 'unit_type', 'multiplayer_cost'], 'limit': 100}),
]


def timed(fn, repeat=5):
    times = []
    for _ in range(repeat):
        started = time.perf_counter()
        result = fn()
        times.append(time.perf_counter() - started)
    return result, round(statistics.median(times) * 1000, 2)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    with Queries(args.db) as q:
        record = {'note': 'Snapshot query results and local measurements; complete within the imported snapshot only.',
                  'search_version': SEARCH_VERSION,
                  'snapshot': {'source_commit': q.snapshot['source_commit'], 'contract_sha256': q.snapshot['contract_sha256']},
                  'runtime': {'python': platform.python_version(), 'sqlite': sqlite3.sqlite_version}, 'cases': []}
        discovery, ms = timed(lambda: call_tool(q, 'discover_unit_fields', {}))
        record['discovery'] = {'fields': len(discovery['structuredContent']['data']['fields']),
                               'bytes': len(discovery['content'][0]['text']), 'median_ms': ms}
        for question, arguments in CASES:
            result, ms = timed(lambda: call_tool(q, 'search_units', arguments))
            data = result['structuredContent']['data']
            pages, cursor = 1, data['next_cursor']
            while cursor:
                cursor = call_tool(q, 'search_units', {**arguments, 'cursor': cursor})['structuredContent']['data']['next_cursor']
                pages += 1
            first = data['results'][:3]
            record['cases'].append({
                'question': question, 'arguments': arguments, 'count_unit': data['count_unit'], 'total': data['total'],
                'matched_variants': data['matched_variants'], 'pages': pages,
                'first_results': [{'unit_key': r.get('unit_key', r.get('family_key')), 'name': r['name'],
                                   'values': r.get('values')} for r in first],
                'first_page_bytes': len(result['content'][0]['text']), 'median_ms': ms})
    args.output.write_bytes((json.dumps(record, indent=2, ensure_ascii=False) + '\n').encode())
    for case in record['cases']:
        print(f"{case['total']:>5} {case['count_unit']:<17} {case['first_page_bytes']:>7} B {case['median_ms']:>7} ms  {case['question']}")
    print('discovery', record['discovery'])


if __name__ == '__main__':
    main()
