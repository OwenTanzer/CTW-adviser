"""Origin evidence and readable inspection for issue #19."""
import copy
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from ctw_adviser.build import build_snapshot
from ctw_adviser.queries import Queries
from test_preview import inspection_plugin

SOURCE = Path(os.environ.get('CTW_DATA_ROOT', ROOT.parent / 'CTW-data'))
EXISTING_DB = Path(os.environ.get('CTW_ADVISER_DB', ''))
SHARED = 'wh2_dlc09_character_abilities_restore'
ITEM = 'wh3_dlc24_item_abilities_wind_bow'
SPELL = 'wh_main_spell_heavens_comet_of_casandora'


@unittest.skipUnless((SOURCE / 'data/unit_stats/dataset_manifest.json').exists() or EXISTING_DB.is_file(),
                     'pinned CTW-data or snapshot required')
class OriginInspectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = None
        if EXISTING_DB.is_file():
            cls.path = EXISTING_DB
        else:
            cls.temp = tempfile.TemporaryDirectory()
            cls.path = Path(cls.temp.name) / 'snapshot.sqlite'
            build_snapshot(SOURCE, cls.path)
        cls.q = Queries(cls.path)
        cls.plugin = inspection_plugin()

    @classmethod
    def tearDownClass(cls):
        cls.q.close()
        if cls.temp:
            cls.temp.cleanup()

    def test_shared_unit_and_skill_origins_retain_independent_evidence(self):
        effect = self.q.get_effect(SHARED)['effect']
        tags = effect['origins']['tags']
        self.assertEqual([tag['origin'] for tag in tags], ['unit', 'skill/trait'])
        self.assertTrue(all(tag['relation_count'] and tag['evidence_refs'] for tag in tags))
        self.assertTrue(effect['origins']['represented_grant_route'])
        self.assertEqual(effect['origins']['coverage'], 'partial')
        rendered = self.plugin.effect_html({'effect': effect}, {'ref': 'effect:' + SHARED})
        self.assertIn('Direct unit links', rendered)
        self.assertIn('verified skill link', rendered)
        self.assertIn('/inspect?unit=', rendered)
        self.assertIn('/inspect/detail?ref=character%3A', rendered)
        self.assertIn('<summary>Full source packet, parameters and provenance</summary>', rendered)

    def test_item_label_is_not_a_verified_item_grant(self):
        effect = self.q.get_effect(ITEM)['effect']
        self.assertFalse(effect['origins']['represented_grant_route'])
        self.assertEqual([(tag['origin'], tag['status'], tag['relation_count'])
                          for tag in effect['origins']['tags']], [('item', 'source_labeled_only', 0)])
        rendered = self.plugin.effect_html({'effect': effect}, {'ref': 'effect:' + ITEM})
        self.assertIn('source label only', rendered)
        self.assertIn('No direct unit link represented', rendered)
        self.assertIn('remain unresolved', rendered)

    def test_skill_only_and_missing_route_are_explicit(self):
        spell = self.q.get_effect(SPELL)['effect']
        self.assertEqual([tag['origin'] for tag in spell['origins']['tags']], ['skill/trait'])
        spell_html = self.plugin.effect_html({'effect': spell}, {'ref': 'effect:' + SPELL})
        self.assertIn('Payload paths', spell_html)
        self.assertIn('Character skill bindings', spell_html)
        row = self.q.db.execute(
            "SELECT ability_key FROM effect_abilities e WHERE source_type!='item' "
            "AND NOT EXISTS(SELECT 1 FROM effect_access u WHERE u.ability_key=e.ability_key) "
            "AND NOT EXISTS(SELECT 1 FROM effect_character_access s WHERE s.ability_key=e.ability_key "
            "AND s.status='activated_effect' AND s.role IN ('enables','enables_overcast')) LIMIT 1").fetchone()
        missing = self.q.get_effect(row[0])['effect']['origins']
        self.assertEqual(missing['tags'], [])
        self.assertFalse(missing['represented_grant_route'])
        self.assertIn('No represented', missing['unknown'])
        modifier_only = self.q.db.execute(
            "SELECT e.ability_key FROM effect_abilities e WHERE EXISTS "
            "(SELECT 1 FROM effect_character_access s WHERE s.ability_key=e.ability_key "
            "AND s.status='activated_effect' AND s.role='modifies') "
            "AND NOT EXISTS(SELECT 1 FROM effect_character_access s WHERE s.ability_key=e.ability_key "
            "AND s.status='activated_effect' AND s.role IN ('enables','enables_overcast')) LIMIT 1").fetchone()
        self.assertNotIn('skill/trait', [tag['origin'] for tag in
                         self.q.get_effect(modifier_only[0])['effect']['origins']['tags']])

    def test_search_summary_uses_exact_links_and_partial_label(self):
        sql = json.loads((ROOT / 'datasette-metadata.json').read_text(encoding='utf-8'))[
            'databases']['ctw']['queries']['find_effects']['sql']
        for key, expected in ((SHARED, 'Unit link; Skill link'), (ITEM, 'Item source label'),
                              (SPELL, 'Skill link')):
            row = next(r for r in self.q.db.execute(sql, {'name': self.q.one('effect_abilities', 'ability_key', key)['name']})
                       if r['ability_key'] == key)
            self.assertIn(expected, row['origin_evidence'])
            self.assertIn('Other routes unresolved', row['origin_evidence'])

    def test_character_page_and_navigation_are_scannable(self):
        rendered = self.plugin.character_html(self.q.get_detail('character:wh2_main_hef_teclis'))
        self.assertIn('Character unit', rendered)
        self.assertIn('Unit forms', rendered)
        self.assertIn('Linked effects on this page', rendered)
        self.assertIn('/inspect/detail?ref=effect%3A', rendered)
        page = self.plugin.page('')
        self.assertIn('/ctw/find_effects?name=', page)
        self.assertIn('/ctw/find_characters?name=', page)
        self.assertIn('@media(max-width:620px)', page)

    def test_all_dynamic_effect_content_is_escaped(self):
        packet = copy.deepcopy(self.q.get_effect(SHARED))
        packet['effect']['identity']['name'] = '<img src=x onerror=alert(1)>'
        packet['effect']['origins']['tags'][0]['route'] = '<script>alert(1)</script>'
        packet['effect']['access']['links'][0]['unit_name'] = '<svg onload=alert(1)>'
        rendered = self.plugin.effect_html(packet, {'ref': 'effect:' + SHARED})
        self.assertNotIn('<script>', rendered)
        self.assertNotIn('<img src=x', rendered)
        self.assertNotIn('<svg onload=', rendered)
        self.assertIn('&lt;script&gt;', rendered)
        self.assertIn('&lt;img src=x', rendered)


if __name__ == '__main__':
    unittest.main()
