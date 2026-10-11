"""Independent SQL/set checks for issue #28, plus adversarial query grammar."""
import copy
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from ctw_adviser.queries import Queries
from ctw_adviser.unit_search import compile_filter, search_units, budget
from ctw_adviser.mcp import call_tool, dispatch_method, BY_NAME
from ctw_adviser.build import build_snapshot

HEF = 'wh2_main_sc_hef_high_elves'
def leaf(f, op, v):
    return dict(field=f, op=op, value=v)
HE = leaf('subculture_key', 'eq', HEF)
CHAR = leaf('source_caste', 'in', ['lord', 'hero'])


class SearchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        db = os.environ.get('CTW_TEST_DB')
        if not db:
            db = Path(cls.tmp.name) / 'adviser.sqlite'
            build_snapshot(Path(os.environ.get('CTW_DATA_ROOT', ROOT.parent / 'CTW-data')), db)
        cls.q = Queries(db)

    @classmethod
    def tearDownClass(cls):
        cls.q.close(); cls.tmp.cleanup()

    def all(self, **options):
        result = []; cursor = None
        while True:
            page = self.q.search_units(**options, cursor=cursor)
            result.extend(page['results'])
            if page['complete']:
                self.assertIsNone(page['next_cursor']); break
            self.assertTrue(page['next_cursor']); cursor = page['next_cursor']
        self.assertEqual(len(result), page['total_count'])
        return result

    def sqlkeys(self, sql, params=()):
        return {r[0] for r in self.q.db.execute(sql, params)}

    def test_high_elf_thresholds_exact_sets_and_values(self):
        for op, sqlop in [('gt','>'),('gte','>='),('lt','<'),('lte','<='),('eq','='),('ne','!=')]:
            opts = dict(filters={'and':[HE, leaf('source_caste','eq','hero'), leaf('melee_attack',op,40)]},
                        fields=['melee_attack','melee_defence'],limit=7)
            rows = self.all(**opts)
            expected = self.sqlkeys('SELECT DISTINCT k.profile_unit_key FROM unit_aliases k JOIN unit_availability a ON a.unit_key=k.unit_key JOIN unit_profiles p ON p.unit_key=k.profile_unit_key WHERE a.subculture_key=? AND p.source_caste=? AND p.melee_attack '+sqlop+' ?', (HEF,'hero',40))
            self.assertEqual({r['unit_key'] for r in rows}, expected)
            self.assertTrue(expected, op)
            for row in rows:
                raw = self.q.db.execute('SELECT melee_attack,melee_defence FROM unit_profiles WHERE unit_key=?',(row['unit_key'],)).fetchone()
                self.assertEqual((row['melee_attack'],row['melee_defence']),tuple(raw))

    def test_requested_60_threshold_and_native_speed(self):
        # The requested >60 hero example is truly empty in this pin; 40 tests real boundaries above.
        for op, sqlop in [('gt','>'),('gte','>='),('lt','<'),('lte','<=')]:
            rows=self.all(filters={'and':[HE,leaf('source_caste','eq','hero'),leaf('melee_attack',op,60)]})
            expected=self.sqlkeys("SELECT DISTINCT k.profile_unit_key FROM unit_aliases k JOIN unit_availability a ON a.unit_key=k.unit_key JOIN unit_profiles p ON p.unit_key=k.profile_unit_key WHERE a.subculture_key=? AND source_caste='hero' AND melee_attack "+sqlop+" 60",(HEF,))
            self.assertEqual({r['unit_key'] for r in rows},expected)
        for speed in (35,3.5):
            rows=self.all(filters={'and':[leaf('tactical_category','eq','infantry'),leaf('armour','lt',40),leaf('speed','gt',speed)]})
            expected=self.sqlkeys("SELECT unit_key FROM unit_profiles WHERE tactical_category='infantry' AND armour<40 AND speed>?",(speed,))
            self.assertEqual({r['unit_key'] for r in rows},expected)
            if speed == 3.5:self.assertTrue(expected)

    def test_roster_family_pagination_and_profile_followthrough(self):
        filters = {'and':[HE,CHAR]}
        variants = self.all(filters=filters,limit=7)
        expected = self.sqlkeys("SELECT DISTINCT k.profile_unit_key FROM unit_aliases k JOIN unit_availability a ON a.unit_key=k.unit_key JOIN unit_profiles p ON p.unit_key=k.profile_unit_key WHERE a.subculture_key=? AND p.source_caste IN ('lord','hero')",(HEF,))
        self.assertEqual({r['unit_key'] for r in variants},expected)
        self.assertEqual(len(variants),len(expected))
        groups = self.all(filters=filters,mode='families',limit=3)
        keys = [v['unit_key'] for g in groups for v in g['matching_variants']]
        self.assertEqual(set(keys),expected);self.assertEqual(len(keys),len(expected))
        self.assertLess(len(groups),len(variants))
        self.assertEqual(len({g['family_key'] for g in groups}),len(groups))
        # Independent graph traversal of the native relation, not the implementation's union-find.
        aliases=dict(self.q.db.execute('SELECT unit_key,profile_unit_key FROM unit_aliases'))
        adjacency={k:set() for k in aliases.values()}
        for a,b in self.q.db.execute('SELECT base_unit_key,mounted_unit_key FROM unit_mount_variants'):
            if a in aliases and b in aliases:
                a,b=aliases[a],aliases[b];adjacency[a].add(b);adjacency[b].add(a)
        for group in groups:
            seen=set(); pending=[group['family_key']]
            while pending:
                k=pending.pop()
                if k not in seen:
                    seen.add(k);pending.extend(adjacency[k]-seen)
            self.assertEqual({v['unit_key'] for v in group['matching_variants']},seen & expected)
        key=variants[0]['unit_key']
        self.assertEqual(self.q.resolve_unit(key)['status'],'resolved')
        self.assertEqual(self.q.get_unit_profile(key)['units'][0]['identity']['unit_key'],key)

    def test_and_or_cost_sort_and_field_comparison(self):
        for group, conjunction in [('and','AND'),('or','OR')]:
            filters={group:[leaf('tactical_category','eq','infantry'), {'and':[leaf('armour','lt',40),leaf('speed','gt',35)]}]}
            expected=self.sqlkeys("SELECT unit_key FROM unit_profiles WHERE tactical_category='infantry' "+conjunction+" (armour<40 AND speed>35)")
            self.assertEqual({r['unit_key'] for r in self.all(filters=filters,limit=31)},expected)
        rows=self.all(filters=leaf('multiplayer_cost','lte',1000),sort=[dict(field='weapon_ap_damage',direction='desc')],fields=['weapon_ap_damage'],limit=43)
        expected=[r[0] for r in self.q.db.execute('SELECT unit_key FROM unit_profiles WHERE multiplayer_cost<=1000 ORDER BY weapon_ap_damage DESC NULLS LAST,unit_key ASC')]
        self.assertEqual([r['unit_key'] for r in rows],expected)
        f={'and':[leaf('source_caste','eq','lord'),leaf('is_mounted','eq',True),dict(field='melee_defence',op='gt',value_field='melee_attack')]}
        rows=self.all(filters=f,limit=11)
        expected=self.sqlkeys("SELECT p.unit_key FROM unit_profiles p WHERE source_caste='lord' AND melee_defence>melee_attack AND (source_mount_entity_key IS NOT NULL OR source_engine_entity_key IS NOT NULL OR unit_key IN (SELECT k.profile_unit_key FROM unit_aliases k JOIN unit_mount_variants m ON m.mounted_unit_key=k.unit_key))")
        self.assertTrue(expected);self.assertEqual({r['unit_key'] for r in rows},expected)

    def test_discovery_categories_and_adapter(self):
        fields=self.q.discover_unit_fields(limit=100)['items']
        self.assertIn('melee_attack',{f['name'] for f in fields})
        self.assertIn(HEF,self.q.discover_unit_fields(field='subculture_key')['items'])
        values=[];cursor=None
        while True:
            page=self.q.discover_unit_fields(field='attribute_key',cursor=cursor,limit=7)
            values.extend(page['items']);cursor=page['next_cursor']
            if page['complete']:break
        expected=[r[0] for r in self.q.db.execute('SELECT DISTINCT attribute_key FROM unit_attributes WHERE attribute_key IS NOT NULL ORDER BY attribute_key')]
        self.assertEqual(values,expected)
        args=dict(filters={'and':[HE,CHAR]},limit=5)
        data=call_tool(self.q,'search_units',args)['structuredContent']
        self.assertEqual(data['status'],'ok');self.assertEqual(data['data'],self.q.search_units(**args))
        self.assertTrue(BY_NAME['search_units']['annotations']['readOnlyHint'])
        response=dispatch_method(self.q,'tools/call',dict(name='search_units',arguments={'sort':[{'field':'subculture_key','direction':'asc'}]}),1)
        self.assertTrue(response['result']['isError'])

    def test_cursor_binds_all_semantics_and_snapshot(self):
        options=dict(filters=HE,limit=2)
        cursor=self.q.search_units(**options)['next_cursor']
        for mutation in [dict(filters=CHAR),dict(fields=['armour']),dict(mode='families'),dict(limit=3),dict(sort=[dict(field='armour',direction='asc')])]:
            with self.assertRaisesRegex(ValueError,'cursor'):
                self.q.search_units(**(options|mutation),cursor=cursor)
        snapshot=copy.deepcopy(self.q.snapshot)
        try:
            self.q.snapshot['test_revision']='changed'
            with self.assertRaisesRegex(ValueError,'cursor'):self.q.search_units(**options,cursor=cursor)
        finally:self.q.snapshot=snapshot
        for bad in ['???', 'a'*2049,[],42]:
            with self.assertRaises(ValueError):self.q.search_units(cursor=bad)

    def test_invalid_queries_and_bounds(self):
        bad=[leaf('unknown','eq',1),leaf('melee_attack','eq',None),leaf('melee_attack','eq',True),
             leaf('melee_attack','contains','x'),leaf('melee_attack','gt',float('nan')),
             leaf('melee_attack','in',[]),leaf('melee_attack','between',[60,10]),
             {'field':'armour','op':'gt','value_field':'speed'},
             {'field':'subculture_key','op':'eq','value_field':'unit_name'},
             {'field':'armour','op':'is_null','value':0},{'and':[]}, {'and':[leaf('armour','gt',0)]*33},
             {'field':'unit_name; DROP TABLE unit_profiles','op':'eq','value':'x'}]
        deep=leaf('armour','gt',0)
        for _ in range(7):deep={'and':[deep]}
        bad.append(deep)
        for filters in bad:
            with self.subTest(filters=filters),self.assertRaises(ValueError):self.q.search_units(filters=filters)
        self.assertEqual(self.q.search_units(filters=leaf('unit_name','eq',"' OR 1=1 --"))['total_count'],0)
        for options in [dict(fields=[]),dict(fields=['armour']*2),dict(limit=True),dict(limit=101),dict(sort=[]),dict(mode='guess')]:
            with self.assertRaises(ValueError):self.q.search_units(**options)

    def test_relation_membership_no_duplicate_profiles(self):
        attribute=self.q.db.execute('SELECT attribute_key FROM unit_attributes GROUP BY attribute_key ORDER BY count(*) DESC LIMIT 1').fetchone()[0]
        rows=self.all(filters=leaf('attribute_key','eq',attribute),fields=['attribute_key'],limit=33)
        expected=self.sqlkeys('SELECT DISTINCT k.profile_unit_key FROM unit_aliases k JOIN unit_attributes a ON a.unit_key=k.unit_key WHERE a.attribute_key=?',(attribute,))
        self.assertEqual({r['unit_key'] for r in rows},expected);self.assertEqual(len(rows),len(expected))
        self.assertTrue(all(attribute in r['attribute_key'] for r in rows))


class NullTests(unittest.TestCase):
    def test_relation_empty_negative_membership(self):
        db=sqlite3.connect(':memory:')
        db.executescript("CREATE TABLE unit_profiles(unit_key TEXT); CREATE TABLE unit_aliases(unit_key TEXT,profile_unit_key TEXT); CREATE TABLE unit_attributes(unit_key TEXT,attribute_key TEXT);")
        db.executemany('INSERT INTO unit_profiles VALUES(?)',[('empty',),('a',),('b',),('both',)])
        db.execute('INSERT INTO unit_aliases SELECT unit_key,unit_key FROM unit_profiles')
        db.executemany('INSERT INTO unit_attributes VALUES(?,?)',[('a','A'),('b','B'),('both','A'),('both','B')])
        for f,expected in [(leaf('attribute_key','eq','A'),{'a','both'}),
                           (leaf('attribute_key','ne','A'),{'b'}),
                           (leaf('attribute_key','not_in',['A']),{'b'}),
                           ({'field':'attribute_key','op':'is_null'},{'empty'})]:
            sql,params=compile_filter(f)
            self.assertEqual({r[0] for r in db.execute('SELECT unit_key FROM unit_profiles p WHERE '+sql,params)},expected)
        db.close()

    def test_execution_budget_resets_connection(self):
        db=sqlite3.connect(':memory:')
        with self.assertRaisesRegex(ValueError,'budget'):
            with budget(db):
                db.execute('WITH RECURSIVE n(x) AS (VALUES(1) UNION ALL SELECT x+1 FROM n WHERE x<100000000) SELECT sum(x) FROM n').fetchone()
        self.assertEqual(db.execute('SELECT 42').fetchone()[0],42)
        db.close()

    def test_scalar_null_zero_and_negation(self):
        db=sqlite3.connect(':memory:')
        db.execute('CREATE TABLE unit_profiles(unit_key TEXT,armour REAL,melee_attack REAL,melee_defence REAL)')
        db.executemany('INSERT INTO unit_profiles VALUES(?,?,?,?)',[('unknown',None,None,None),('zero',0,0,0),('positive',40,60,70)])
        for f,expected in [(leaf('armour','eq',0),{'zero'}),(leaf('armour','ne',0),{'positive'}),
                           (leaf('armour','not_in',[0]),{'positive'}),({'field':'armour','op':'is_null'},{'unknown'}),
                           ({'field':'melee_defence','op':'gt','value_field':'melee_attack'},{'positive'})]:
            sql,params=compile_filter(f)
            self.assertEqual({r[0] for r in db.execute('SELECT unit_key FROM unit_profiles p WHERE '+sql,params)},expected)
        db.close()

if __name__=='__main__':unittest.main()
