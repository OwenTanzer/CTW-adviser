"""Check that the benchmark's fresh timer covers connection opening."""
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('benchmark_packets', ROOT / 'scripts/benchmark_packets.py')
benchmark = importlib.util.module_from_spec(spec)
spec.loader.exec_module(benchmark)


class FreshTimingTests(unittest.TestCase):
    def test_fresh_measurement_includes_open_and_serialization(self):
        clock = [1.0]

        class Connection:
            def __init__(self, _db):
                clock[0] += .007

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                pass

        def packet(_connection, _case):
            clock[0] += .005

        with patch.object(benchmark, 'perf_counter', side_effect=lambda: clock[0]), \
             patch.object(benchmark, 'Queries', Connection), \
             patch.object(benchmark, 'packet_bytes', side_effect=packet):
            elapsed = benchmark.fresh_packet_ms('unused.sqlite', 'example')
        self.assertAlmostEqual(elapsed, 12.0)


if __name__ == '__main__':
    unittest.main()
