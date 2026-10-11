"""Canned effect-search results link to their assembled inspection records."""
import html
import json
import os
from pathlib import Path
import re
import sqlite3
import sys
import unittest
from urllib.parse import parse_qs, urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from ctw_adviser.queries import Queries
from test_preview import inspection_plugin


def linked_ref(rendered):
    href = html.unescape(re.search(r'href="([^"]+)"', rendered).group(1))
    parsed = urlsplit(href)
    if parsed.path != '/inspect/detail':
        raise AssertionError(parsed.path)
    return parse_qs(parsed.query)['ref'][0]


class EffectSearchLinksTests(unittest.TestCase):
    def test_effect_key_and_name_are_escaped_and_url_encoded(self):
        plugin = inspection_plugin()
        row = {'ability_key': 'spell:one & "<two>', 'name': '<Comet & "fire">',
               'effect_kind': 'spell', 'source_type': 'spell', 'keywords_json': '[]'}
        for column in ('ability_key', 'name'):
            with self.subTest(column=column):
                rendered = plugin.render_cell(row, row[column], column, None, 'ctw', None)
                self.assertEqual(linked_ref(rendered), 'effect:' + row['ability_key'])
                self.assertIn('%26', rendered)
                self.assertIn('%3C', rendered)
                self.assertIn(html.escape(row[column], quote=True), rendered)
                self.assertNotIn('<Comet', rendered)
        self.assertIsNone(plugin.render_cell({'ability_key': 'x'}, 'x', 'ability_key',
                                              None, 'ctw', None))
        self.assertIsNone(plugin.render_cell(row, row['ability_key'], 'ability_key',
                                              None, 'other', None))

    def test_filtered_results_open_distinct_matching_details(self):
        db_path = Path(os.environ.get('CTW_ADVISER_DB', ''))
        if not db_path.is_file():
            self.skipTest('set CTW_ADVISER_DB to the pinned snapshot')
        query = json.loads((ROOT / 'datasette-metadata.json').read_text(encoding='utf-8'))[
            'databases']['ctw']['queries']['find_effects']['sql']
        with sqlite3.connect(db_path) as db:
            db.row_factory = sqlite3.Row
            rows = db.execute(query, {'name': 'Comet of Casandora'}).fetchall()
        self.assertGreaterEqual(len(rows), 3)
        self.assertTrue(all('comet of casandora' in row['name'].casefold() for row in rows))
        plugin = inspection_plugin()
        details = Queries(db_path)
        try:
            refs = set()
            for row in rows:
                with self.subTest(ability_key=row['ability_key']):
                    for column in ('ability_key', 'name'):
                        rendered = plugin.render_cell(row, row[column], column,
                                                      None, 'ctw', None)
                        ref = linked_ref(rendered)
                        self.assertEqual(ref, 'effect:' + row['ability_key'])
                        self.assertEqual(details.get_detail(ref)['effect']['identity']['ability_key'],
                                         row['ability_key'])
                        refs.add(ref)
            self.assertEqual(len(refs), len(rows))
        finally:
            details.close()


if __name__ == '__main__':
    unittest.main()
