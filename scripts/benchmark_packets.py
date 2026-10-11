"""Measure fixed compact-packet cases with a local SQLite snapshot.

Times include query and JSON serialization, not network or service latency.
Warm repetitions reuse one connection; fresh repetitions include connection
opening and query/serialization, but do not clear the operating system's file cache.
"""
import argparse
import json
import platform
import sqlite3
import statistics
import sys
import tracemalloc
from pathlib import Path
from time import perf_counter

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from ctw_adviser.queries import Queries

SINGLES = [
    'Lothern Sea Guard', 'Blue Horrors of Tzeentch', 'Reiksguard', 'Queen Bess',
    'wh2_dlc16_skv_cha_packmaster_0', 'wh_dlc04_vmp_veh_corpse_cart_1',
    'wh3_dlc23_chd_veh_iron_daemon_ror_1dreadquake', 'wh_main_emp_cav_outriders_0',
    'wh2_main_hef_mon_star_dragon', 'wh3_main_dae_cha_daemon_prince_0',
    'wh2_dlc11_cst_inf_count_noctilus_1',
    'wh3_main_nur_cha_exalted_great_unclean_one_nurgle_0',
]
PAIRS = [
    ('Lothern Sea Guard', 'Blue Horrors of Tzeentch'),
    ('Reiksguard', 'Doom Diver Catapults'),
    ('Bloodletters of Khorne', 'Kroxigor'),
]


def packet_bytes(queries, case):
    packet = (queries.get_unit_profile(case) if isinstance(case, str)
              else queries.get_matchup_evidence(*case))
    return json.dumps(packet, ensure_ascii=False, sort_keys=True,
                      separators=(',', ':')).encode('utf-8')


def fresh_packet_ms(db, case):
    """Measure connection opening plus first packet and serialization."""
    begin = perf_counter()
    with Queries(db) as fresh:
        packet_bytes(fresh, case)
        return (perf_counter() - begin) * 1000


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--repetitions', type=int, default=25)
    args = parser.parse_args()
    if args.repetitions < 2:
        parser.error('repetitions must be at least 2')
    started = perf_counter()
    cases = []
    with Queries(args.db) as queries:
        for case in [*SINGLES, *PAIRS]:
            packet_bytes(queries, case)  # warm-up
            samples = []
            for _ in range(args.repetitions):
                begin = perf_counter()
                blob = packet_bytes(queries, case)
                samples.append((perf_counter() - begin) * 1000)
            fresh_ms = fresh_packet_ms(args.db, case)
            cases.append({'case': case, 'kind': 'single' if isinstance(case, str) else 'pair',
                          'bytes': len(blob), 'warm_median_ms': statistics.median(samples),
                          'warm_p95_ms': sorted(samples)[min(len(samples) - 1,
                                                             int(len(samples) * .95))],
                          'fresh_connection_ms': fresh_ms})
    singles = [row for row in cases if row['kind'] == 'single']
    pairs = [row for row in cases if row['kind'] == 'pair']
    tracemalloc.start()
    with Queries(args.db) as queries:
        packet_bytes(queries, 'wh3_main_dae_cha_daemon_prince_0')
    _, heap_peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    report = {
        'scope': 'warm: local query plus compact UTF-8 JSON serialization; fresh: connection opening plus first query and serialization; no network or cold disk cache',
        'repetitions': args.repetitions,
        'runtime': {'python': platform.python_version(), 'sqlite': sqlite3.sqlite_version,
                    'os': platform.platform(), 'machine': platform.machine(),
                    'processor': platform.processor()},
        'single_median_bytes': statistics.median(row['bytes'] for row in singles),
        'single_max_bytes': max(row['bytes'] for row in singles),
        'pair_median_bytes': statistics.median(row['bytes'] for row in pairs),
        'pair_max_bytes': max(row['bytes'] for row in pairs),
        'max_warm_median_ms': max(row['warm_median_ms'] for row in cases),
        'max_warm_p95_ms': max(row['warm_p95_ms'] for row in cases),
        'max_fresh_connection_ms': max(row['fresh_connection_ms'] for row in cases),
        'representative_python_heap_peak_bytes': heap_peak,
        'memory_scope': 'tracemalloc peak for one Daemon Prince query and serialization on a fresh connection; excludes SQLite native memory and process RSS',
        'elapsed_seconds': perf_counter() - started,
        'cases': cases,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k: v for k, v in report.items() if k != 'cases'}))


if __name__ == '__main__':
    main()
