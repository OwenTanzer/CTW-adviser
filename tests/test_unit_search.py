"""Issue #28 unit search; set CTW_ADVISER_DB to a pinned built snapshot.

Expected sets come from independent direct reads of the same snapshot tables,
not from the search module's SQL.
"""

import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

from ctw_adviser import unit_search
from ctw_adviser.mcp import BY_NAME, call_tool, dispatch_method
from ctw_adviser.queries import Queries
from ctw_adviser.unit_search import SearchError, UnitSearch

DB = Path(os.environ.get('CTW_ADVISER_DB', 'work/adviser.sqlite'))
HEF = 'wh2_main_sc_hef_high_elves'


@unittest.skipUnless(DB.is_file(), 'build work/adviser.sqlite first')
class UnitSearchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.q = Queries(DB)
        cls.s = UnitSearch(cls.q)
        db = cls.q.db
        profiles = {r['unit_key']: dict(r) for r in db.execute('SELECT * FROM unit_profiles')}
        alias = {r['unit_key']: r['profile_unit_key'] for r in db.execute('SELECT * FROM unit_aliases')}
        rows = {}
        for a in db.execute('SELECT unit_key, subculture_key FROM unit_availability'):
            profile = alias[a['unit_key']]
            rows.setdefault((profile, a['subculture_key']), set()).add(a['unit_key'])
        cls.mounts = {r['mounted_unit_key']: r['base_unit_key'] for r in db.execute('SELECT * FROM unit_mount_variants')}
        cls.rows = [dict(profiles[p], subculture=sc, source_keys=sorted(keys)) for (p, sc), keys in rows.items()]

    @classmethod
    def tearDownClass(cls):
        cls.q.close()

    def all_pages(self, limit=40, **query):
        first = self.s.search(limit=limit, **query)
        pages, results, cursor = [first], list(first['results']), first['next_cursor']
        while cursor:
            page = self.s.search(limit=limit, cursor=cursor, **query)
            self.assertEqual(page['offset'], len(results))
            self.assertEqual(page['total'], first['total'])
            pages.append(page); results += page['results']; cursor = page['next_cursor']
        self.assertTrue(pages[-1]['complete'])
        self.assertEqual(len(results), first['total'])
        return first, results

    def expect(self, predicate):
        return {(r['unit_key'], r['subculture']) for r in self.rows if predicate(r)}

    def found(self, results):
        keys = [(r.get('profile_unit_key', r['unit_key']), r['subculture']) for r in results]
        self.assertEqual(len(keys), len(set(keys)), 'duplicate rows')
        return set(keys)

    def where(self, *conditions):
        return {'all': list(conditions)}

    def test_discovery_without_repository_knowledge(self):
        d = self.s.discover()
        ids = {f['id']: f for f in d['fields']}
        for name in ('subculture', 'caste', 'unit_type', 'mount_relation', 'mount_body', 'melee_attack',
                     'armour', 'speed', 'multiplayer_cost', 'primary_melee_ap_damage', 'attributes'):
            self.assertIn(name, ids)
        subcultures = {c['value']: c for c in ids['subculture']['categories']}
        self.assertEqual(len(subcultures), 25)
        self.assertEqual(subcultures[HEF]['label'], 'High Elves')
        self.assertEqual({c['value'] for c in ids['caste']['categories']} >= {'lord', 'hero'}, True)
        self.assertEqual(ids['primary_missile_ap_damage']['null_rows'],
                         sum(r['missile_ap_damage'] is None for r in self.rows))
        self.assertIn('melee_defence', ids['melee_attack']['comparable_with'])
        self.assertNotIn('armour', ids['melee_attack']['comparable_with'])
        self.assertEqual(d['ambiguous_terms']['cost'][0], 'multiplayer_cost')
        self.assertTrue(any('legendary' in u['term'] for u in d['unsupported_classifications']))
        self.assertIn('not proof of complete game coverage', d['coverage'])
        attributes = self.s.discover('attributes', limit=20)
        values = list(attributes['categories']['values'])
        cursor = attributes['categories']['next_cursor']
        while cursor:
            page = self.s.discover('attributes', cursor=cursor, limit=20)
            values += page['categories']['values']; cursor = page['categories']['next_cursor']
        direct = [r[0] for r in self.q.db.execute('SELECT DISTINCT attribute_key FROM unit_attributes ORDER BY 1')]
        self.assertEqual([v['value'] for v in values], direct)
        self.assertLess(len(json.dumps(d)), 64_000)

    def test_high_elf_lords_and_heroes_complete_and_grouped(self):
        where = self.where({'field': 'subculture', 'op': '=', 'value': HEF},
                           {'field': 'caste', 'op': 'in', 'value': ['lord', 'hero']})
        first, results = self.all_pages(limit=17, where=where, fields=['caste', 'mount_body'])
        expected = self.expect(lambda r: r['subculture'] == HEF and r['source_caste'] in ('lord', 'hero'))
        self.assertEqual(self.found(results), expected)
        self.assertEqual(first['count_unit'], 'qualified_variant')
        self.assertGreater(len(expected), 100)
        grouped, families = self.all_pages(limit=9, where=where, group_by='mount_family', fields=['caste'])
        self.assertEqual(grouped['count_unit'], 'mount_family')
        self.assertEqual(grouped['matched_variants'], len(expected))
        members = [(v.get('profile_unit_key', v['unit_key']), f['subculture']) for f in families for v in f['variants']]
        self.assertEqual(sorted(members), sorted(expected))
        for family in families:
            self.assertNotIn('values', family)  # never a merged family stat
            self.assertEqual(family['matched_variant_count'], len(family['variants']))
            for variant in family['variants']:
                key = variant.get('profile_unit_key', variant['unit_key'])
                self.assertEqual(self.mounts.get(key, key), family['family_key'])
        prince = next(f for f in families if f['family_key'] == 'wh2_main_hef_cha_prince_0')
        self.assertEqual(len(prince['variants']), 6)
        teclis = [r for r in results if r['unit_key'].startswith('wh2_main_hef_cha_teclis')
                  or r['unit_key'].startswith('wh2_dlc15_hef_cha_teclis')]
        self.assertEqual(len(teclis), 3)

    def test_threshold_operators_and_exact_boundary(self):
        heroes = lambda r: r['subculture'] == HEF and r['source_caste'] == 'hero'
        values = sorted({r['melee_attack'] for r in self.rows if heroes(r)})
        threshold = 45
        self.assertIn(threshold, values)  # boundary is exercised, both sides nonempty
        ops = {'>': lambda v: v > threshold, '>=': lambda v: v >= threshold,
               '<': lambda v: v < threshold, '<=': lambda v: v <= threshold}
        for op, test in ops.items():
            _, results = self.all_pages(where=self.where(
                {'field': 'subculture', 'op': '=', 'value': HEF}, {'field': 'caste', 'op': '=', 'value': 'hero'},
                {'field': 'melee_attack', 'op': op, 'value': threshold}), fields=['melee_attack'])
            expected = self.expect(lambda r: heroes(r) and test(r['melee_attack']))
            self.assertTrue(expected, op)
            self.assertEqual(self.found(results), expected, op)
            for item in results:
                self.assertTrue(test(item['values']['melee_attack']))
        none = self.s.search(self.where({'field': 'subculture', 'op': '=', 'value': HEF},
                                        {'field': 'caste', 'op': '=', 'value': 'hero'},
                                        {'field': 'melee_attack', 'op': '>', 'value': 60}))
        self.assertEqual((none['total'], max(values)), (0, 55.0))
        lords = self.s.search(self.where({'field': 'subculture', 'op': '=', 'value': HEF},
                                         {'field': 'caste', 'op': '=', 'value': 'lord'},
                                         {'field': 'melee_attack', 'op': '>', 'value': 60}), limit=100)
        self.assertEqual(self.found(lords['results']), self.expect(
            lambda r: r['subculture'] == HEF and r['source_caste'] == 'lord' and r['melee_attack'] > 60))
        between = self.s.search({'field': 'melee_attack', 'op': 'between', 'value': [45, 45]}, limit=100)
        self.assertEqual(between['total'], len(self.expect(lambda r: r['melee_attack'] == 45)))

    def test_and_or_grouping_and_precedence(self):
        infantry = {'field': 'unit_type', 'op': '=', 'value': 'infantry'}
        armour = {'field': 'armour', 'op': '<', 'value': 40}
        fast = {'field': 'speed', 'op': '>', 'value': 4}
        _, both = self.all_pages(where={'all': [infantry, armour, fast]}, limit=100)
        expected = self.expect(lambda r: r['tactical_category'] == 'infantry' and r['armour'] < 40 and r['speed'] > 4)
        self.assertTrue(expected)
        self.assertEqual(self.found(both), expected)
        excluded = self.expect(lambda r: r['tactical_category'] == 'infantry' and r['armour'] < 40)
        self.assertTrue(excluded - expected)  # the speed condition removes rows
        very_fast = {'field': 'speed', 'op': '>', 'value': 8}
        _, grouped_or = self.all_pages(where={'all': [infantry, {'any': [armour, very_fast]}]}, limit=100)
        _, outer_or = self.all_pages(where={'any': [{'all': [infantry, armour]}, very_fast]}, limit=100)
        self.assertEqual(self.found(grouped_or), self.expect(
            lambda r: r['tactical_category'] == 'infantry' and (r['armour'] < 40 or r['speed'] > 8)))
        self.assertEqual(self.found(outer_or), self.expect(
            lambda r: (r['tactical_category'] == 'infantry' and r['armour'] < 40) or r['speed'] > 8))
        self.assertNotEqual(self.found(grouped_or), self.found(outer_or))
        with self.assertRaises(SearchError) as bare:
            self.s.search([infantry, armour])
        self.assertEqual(bare.exception.code, 'invalid_where')
        with self.assertRaises(SearchError):
            self.s.search({'all': [infantry], 'any': [armour]})

    def test_cost_with_explicit_weapon_sort(self):
        query = dict(where={'field': 'multiplayer_cost', 'op': '<=', 'value': 1000},
                     fields=['multiplayer_cost', 'primary_melee_ap_damage'],
                     sort=[{'field': 'primary_melee_ap_damage', 'direction': 'desc'}])
        first, results = self.all_pages(limit=100, **query)
        self.assertEqual(self.found(results), self.expect(lambda r: r['multiplayer_cost'] <= 1000))
        self.assertTrue(self.expect(lambda r: r['multiplayer_cost'] == 1000))
        keys = [(-r['values']['primary_melee_ap_damage'], r.get('profile_unit_key', r['unit_key']), r['subculture'])
                for r in results]
        self.assertEqual(keys, sorted(keys))  # descending value, stable identity tie-break
        direct = {(r['unit_key'], r['subculture']): r for r in self.rows}
        for item in results[:200]:
            row = direct[(item.get('profile_unit_key', item['unit_key']), item['subculture'])]
            self.assertEqual(item['values'], {'multiplayer_cost': row['multiplayer_cost'],
                                              'primary_melee_ap_damage': row['weapon_ap_damage']})
        self.assertIn('scope', next(f for f in self.s.discover()['fields'] if f['id'] == 'primary_melee_ap_damage'))
        for term in ('cost', 'ap_damage', 'damage'):
            with self.assertRaises(SearchError) as error:
                self.s.search({'field': term, 'op': '<=', 'value': 1000})
            self.assertEqual(error.exception.code, 'ambiguous_field')
            self.assertGreater(len(error.exception.detail['candidates']), 0)
        with self.assertRaises(SearchError) as error:
            self.s.search(sort=[{'field': 'ap_damage', 'direction': 'desc'}])
        self.assertIn('primary_missile_ap_damage', error.exception.detail['candidates'])

    def test_mounted_lords_field_comparison(self):
        _, results = self.all_pages(limit=100, where=self.where(
            {'field': 'caste', 'op': '=', 'value': 'lord'}, {'field': 'mount_body', 'op': '!=', 'value': 'none'},
            {'field': 'melee_defence', 'op': '>', 'other_field': 'melee_attack'}),
            fields=['melee_attack', 'melee_defence'])
        expected = self.expect(lambda r: r['source_caste'] == 'lord' and (
            r['source_mount_entity_key'] is not None or r['source_engine_entity_key'] is not None)
            and r['melee_defence'] > r['melee_attack'])
        self.assertTrue(expected)
        self.assertEqual(self.found(results), expected)
        excluded = self.expect(lambda r: r['source_caste'] == 'lord' and r['source_mount_entity_key'] is not None
                               and r['melee_defence'] <= r['melee_attack'])
        self.assertTrue(excluded)
        mounted = self.s.search({'field': 'mount_relation', 'op': '=', 'value': 'mounted_variant'}, limit=1)
        self.assertEqual(mounted['total'], len(self.expect(lambda r: r['unit_key'] in self.mounts)))

    def test_pagination_with_ties_and_grouped_counts(self):
        query = dict(sort=[{'field': 'caste', 'direction': 'asc'}], fields=['caste'])
        first, results = self.all_pages(limit=97, **query)
        self.assertEqual(self.found(results), {(r['unit_key'], r['subculture']) for r in self.rows})
        self.assertEqual(first['total'], len(self.rows))
        grouped, families = self.all_pages(limit=97, group_by='mount_family', **query)
        self.assertEqual(sum(f['matched_variant_count'] for f in families), len(self.rows))
        self.assertEqual(len({(f['family_key'], f['subculture']) for f in families}), grouped['total'])
        expected_families = {(self.mounts.get(r['unit_key'], r['unit_key']), r['subculture']) for r in self.rows}
        self.assertEqual(grouped['total'], len(expected_families))

    def test_cursor_validation(self):
        query = dict(where={'field': 'caste', 'op': '=', 'value': 'hero'})
        page = self.s.search(limit=5, **query)
        cursor = page['next_cursor']
        with self.assertRaises(SearchError) as error:
            self.s.search(limit=5, cursor=cursor, where={'field': 'caste', 'op': '=', 'value': 'lord'})
        self.assertEqual(error.exception.code, 'cursor_query_mismatch')
        with self.assertRaises(SearchError) as error:
            self.s.search(limit=5, cursor=cursor[:-1] + ('0' if cursor[-1] != '0' else '1'), **query)
        self.assertEqual(error.exception.code, 'invalid_cursor')
        with patch.dict(self.q.snapshot, {'id': 'other-snapshot'}):
            with self.assertRaises(SearchError) as error:
                self.s.search(limit=5, cursor=cursor, **query)
        self.assertEqual(error.exception.code, 'stale_cursor')
        changed_limit = self.s.search(limit=7, cursor=cursor, **query)
        self.assertEqual(changed_limit['offset'], 5)

    def test_null_versus_zero(self):
        null_missile = self.expect(lambda r: r['missile_ap_damage'] is None)
        self.assertTrue(null_missile)
        low, results = self.all_pages(limit=100, where={'field': 'primary_missile_ap_damage', 'op': '<', 'value': 1})
        self.assertFalse(self.found(results) & null_missile)
        self.assertEqual(self.found(results), self.expect(lambda r: r['missile_ap_damage'] is not None and r['missile_ap_damage'] < 1))
        not_equal = self.s.search({'field': 'primary_missile_ap_damage', 'op': '!=', 'value': 5}, limit=1)
        self.assertEqual(not_equal['total'], len(self.expect(lambda r: r['missile_ap_damage'] not in (None, 5))))
        is_null = self.s.search({'field': 'primary_missile_ap_damage', 'op': 'is_null'}, limit=1)
        self.assertEqual(is_null['total'], len(null_missile))
        zero_ward = self.s.search({'field': 'ward_save', 'op': '=', 'value': 0}, limit=1)
        self.assertEqual(zero_ward['total'], len(self.expect(lambda r: r['ward_save'] == 0)))
        self.assertGreater(zero_ward['total'], 0)
        page = self.s.search({'field': 'primary_missile_ap_damage', 'op': 'is_null'}, fields=['primary_missile_ap_damage'], limit=1)
        self.assertIsNone(page['results'][0]['values']['primary_missile_ap_damage'])

    def test_diagnostics_and_bounds(self):
        cases = [
            ({'field': 'melee_atack', 'op': '>', 'value': 1}, 'unknown_field'),
            ({'field': 'caste', 'op': '>', 'value': 'lord'}, 'unsupported_operator'),
            ({'field': 'armour', 'op': '>', 'other_field': 'speed'}, 'incompatible_units'),
            ({'field': 'caste', 'op': '=', 'other_field': 'unit_type'}, 'incompatible_comparison'),
            ({'field': 'caste', 'op': '=', 'value': 'legendary_lord'}, 'unknown_category'),
            ({'field': 'armour', 'op': '>', 'value': True}, 'invalid_value'),
            ({'field': 'armour', 'op': '>', 'value': '40'}, 'invalid_value'),
            ({'field': 'armour', 'op': 'between', 'value': [50, 40]}, 'invalid_value'),
            ({'field': 'armour', 'op': 'is_null', 'value': 1}, 'invalid_condition'),
            ({'field': 'armour', 'op': '>'}, 'missing_value'),
            ({'field': 'armour', 'op': 'in', 'value': list(range(65))}, 'invalid_value'),
            ({'all': [{'field': 'armour', 'op': '>', 'value': i} for i in range(33)]}, 'too_many_conditions'),
            ({'all': [{'any': [{'all': [{'any': [{'field': 'armour', 'op': '>', 'value': 1}]}]}]}]}, 'query_too_deep'),
            ({'field': 'armour', 'op': '>', 'value': 1, 'extra': 1}, 'invalid_condition'),
        ]
        for where, code in cases:
            with self.assertRaises(SearchError, msg=code) as error:
                self.s.search(where)
            self.assertEqual(error.exception.code, code, where)
        with self.assertRaises(SearchError) as error:
            self.s.search({'field': 'caste', 'op': '=', 'value': 'heros'})
        self.assertIn('hero', error.exception.detail['suggestions'])
        for kwargs, code in ((dict(limit=101), 'invalid_limit'), (dict(fields=['armour'] * 2), 'invalid_fields'),
                             (dict(fields=['armour'] * 25), 'invalid_fields'), (dict(fields=['attributes']), 'invalid_fields'),
                             (dict(sort=[{'field': 'armour'}] * 4), 'invalid_sort'), (dict(group_by='family'), 'invalid_group_by')):
            with self.assertRaises(SearchError) as error:
                self.s.search(**kwargs)
            self.assertEqual(error.exception.code, code)
        with patch.object(unit_search, 'MAX_VM_STEPS', 1000):
            with self.assertRaises(SearchError) as error:
                UnitSearch(self.q).search({'field': 'armour', 'op': '>', 'value': 1})
        self.assertEqual(error.exception.code, 'query_budget_exceeded')
        attribute = self.s.search({'all': [{'field': 'attributes', 'op': 'contains', 'value': 'flying'},
                                           {'field': 'caste', 'op': '=', 'value': 'hero'}]}, limit=1)
        flying = {r[0] for r in self.q.db.execute("SELECT unit_key FROM unit_attributes WHERE attribute_key='flying'")}
        self.assertEqual(attribute['total'], len(self.expect(lambda r: r['unit_key'] in flying and r['source_caste'] == 'hero')))

    def test_results_follow_into_existing_tools(self):
        _, results = self.all_pages(limit=100, where={'field': 'subculture', 'op': '=', 'value': HEF})
        for item in results:
            resolved = self.q.resolved(item['unit_key'], item['subculture'])
            self.assertEqual(resolved['profile_unit_key'], item.get('profile_unit_key', item['unit_key']))
        nakai = self.s.search({'field': 'unit_key', 'op': 'contains', 'value': 'temple_guards'}, limit=10)
        multi = next(r for r in nakai['results'] if 'source_unit_keys' in r)
        for key in multi['source_unit_keys']:  # equivalent source keys share one stat profile
            self.assertEqual(self.q.resolved(key, multi['subculture'])['profile_unit_key'], multi['unit_key'])
        item = results[0]
        profile = self.q.get_unit_profile(item['unit_key'], subculture=item['subculture'], section='attributes')
        self.assertEqual(profile['units'][0]['identity']['unit_key'], item['unit_key'])
        provenance = self.q.get_provenance(item['provenance_refs'])
        self.assertEqual(set(provenance['provenance']), set(item['provenance_refs']))

    def test_mcp_adapter_matches_library(self):
        self.assertIn('search_units', BY_NAME)
        self.assertIn('discover_unit_fields', BY_NAME)
        listed = dispatch_method(self.q, 'tools/list', {}, 1)['result']['tools']
        self.assertEqual(len(listed), 10)
        args = {'where': {'all': [{'field': 'subculture', 'op': '=', 'value': HEF},
                                  {'field': 'caste', 'op': 'in', 'value': ['lord', 'hero']}]},
                'fields': ['melee_attack'], 'sort': [{'field': 'melee_attack', 'direction': 'desc'}],
                'group_by': 'mount_family', 'limit': 10}
        result = call_tool(self.q, 'search_units', args)['structuredContent']
        self.assertEqual(result['status'], 'ok')
        library = self.s.search(args['where'], fields=args['fields'], sort=args['sort'], group_by='mount_family', limit=10)
        self.assertEqual(json.loads(json.dumps(result['data'])), json.loads(json.dumps(library)))
        nxt = call_tool(self.q, 'search_units', {**args, 'cursor': result['data']['next_cursor']})['structuredContent']
        self.assertEqual(nxt['data']['offset'], 10)
        invalid = call_tool(self.q, 'search_units', {'where': {'field': 'cost', 'op': '<', 'value': 1}})
        self.assertTrue(invalid['isError'])
        self.assertEqual(invalid['structuredContent']['data']['code'], 'ambiguous_field')
        discovered = call_tool(self.q, 'discover_unit_fields', {'field': 'subculture'})['structuredContent']
        self.assertEqual(discovered['data']['categories']['total'], 25)
        with self.assertRaises(ValueError):
            call_tool(self.q, 'search_units', {'fields': 'armour'})
        with self.assertRaises(ValueError):
            call_tool(self.q, 'search_units', {'limit': 101})


if __name__ == '__main__':
    unittest.main()
