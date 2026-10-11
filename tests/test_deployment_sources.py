"""Exercise the Docker locked-file fetch path without external network access."""
import io
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'src'))
from ctw_adviser.build import build_snapshot
from scripts import fetch_locked_sources, verify_sources

SOURCE = Path(os.environ.get('CTW_DATA_ROOT', ROOT.parent / 'CTW-data'))


@unittest.skipUnless((SOURCE / 'data/magic/dataset_manifest.json').exists(),
                     'set CTW_DATA_ROOT to the pinned CTW-data checkout')
class DockerLockedSourceTests(unittest.TestCase):
    def test_fetch_verify_and_build_from_only_locked_files(self):
        lock = json.loads((ROOT / 'source_lock.json').read_text(encoding='utf-8'))
        contract = json.loads((ROOT / 'schema/import_contract.json').read_text(encoding='utf-8'))
        expected = {entry['path'] for entry in lock['files']}
        self.assertEqual(len(expected), len(lock['files']))
        required = ({gate['path'] for gate in contract['metadata_gates']}
                    | {dataset['path'] for dataset in contract['datasets']})
        self.assertFalse(required - expected)
        prefix = (f"https://raw.githubusercontent.com/OwenTanzer/CTW-data/"
                  f"{lock['source_commit']}/")

        def pinned_source_response(url, timeout):
            self.assertTrue(url.startswith(prefix), url)
            relative = unquote(url[len(prefix):])
            self.assertIn(relative, expected)
            return io.BytesIO((SOURCE / relative).read_bytes())

        with tempfile.TemporaryDirectory() as folder:
            destination = Path(folder) / 'ctw-source'
            # Resolve paths deterministically while the threaded fetch populates files.
            for entry in lock['files']:
                (destination / entry['path']).parent.mkdir(parents=True, exist_ok=True)
            with patch.object(fetch_locked_sources, 'urlopen', pinned_source_response), \
                    patch.object(sys, 'argv', ['fetch_locked_sources.py', str(destination)]):
                fetch_locked_sources.main()
            fetched = {path.relative_to(destination).as_posix()
                       for path in destination.rglob('*') if path.is_file()}
            self.assertEqual(fetched, expected)
            verified = verify_sources.verify(destination, lock, contract)
            self.assertEqual(verified['status'], 'passed', verified['errors'])
            self.assertEqual(verified['files_verified'], len(expected))

            output = Path(folder) / 'ctw.sqlite'
            report = build_snapshot(destination, output)
            self.assertTrue(output.is_file())
            with sqlite3.connect(output) as db:
                self.assertEqual(db.execute('PRAGMA integrity_check').fetchone()[0], 'ok')
                self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(), [])
            self.assertEqual(report['status'], 'passed')
            self.assertEqual(report['source_commit'], lock['source_commit'])
            self.assertEqual(report['characters'], 550)
