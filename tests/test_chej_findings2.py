"""Named acceptance cases from the second Chej review; source values, not combat simulation."""
import copy
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'scripts')]
from ctw_adviser.build import build_snapshot
from ctw_adviser.queries import Queries, Packet
from validate_packets import validate, packet_checks
SOURCE=Path(os.environ.get('CTW_DATA_ROOT',ROOT.parent/'CTW-data'))
CAPS={'wh3_dlc29_hero_passive_dominate':('enemy',1),
 'wh2_dlc16_hero_passive_running_with_the_pack':('friendly',3),
 'wh2_pro08_character_passive_blood_oath':('friendly',2),
 'wh3_dlc29_character_passive_legion_commander':('friendly',4),
 'wh3_dlc29_unit_passive_locus_of_azyr':('friendly',3)}
SPREADS={'wh3_dlc25_unit_passive_tears_of_nurgle':('wh3_dlc25_unit_passive_tears_of_nurgle',35),
 'wh3_dlc29_hero_passive_daemon_flies':('wh3_dlc29_hero_passive_daemon_flies',40),
 'wh3_dlc29_unit_passive_little_plague_i':('wh3_dlc29_unit_passive_little_plague_v1',40),
 'wh3_dlc29_unit_passive_little_plague_ii':('wh3_dlc29_unit_passive_little_plague_v1',40)}
BRANCHES=['wh3_dlc20_unit_passive_giver_of_arcane_glory','wh3_dlc25_character_passive_befouled_charge',
 'wh3_dlc25_lord_passive_living_darkness','wh3_dlc27_unit_passive_dual_personality_defiler',
 'wh3_dlc29_lord_passive_arcane_leech','wh3_dlc29_unit_passive_humiliation_of_the_gods']

@unittest.skipUnless((SOURCE/'data/unit_stats/dataset_manifest.json').exists(),'pinned source required')
class ChejFindings2(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.temp=tempfile.TemporaryDirectory();db=Path(cls.temp.name)/'units.sqlite'
  build_snapshot(SOURCE,db);cls.q=Queries(db)
  cls.schema=json.loads((ROOT/'schema/evidence_packet.schema.json').read_text())
 @classmethod
 def tearDownClass(cls):cls.q.close();cls.temp.cleanup()
 def packet(self,key):
  p=self.q.get_unit_profile(key,limit=256)
  validate(p,self.schema,self.schema);packet_checks(p,self.q.get_provenance)
  return p
 def unit(self,key):return self.packet(key)['units'][0]
 def mechanic(self,key):
  detail=self.q.get_passive_detail(key)['mechanic']
  validate(detail,self.schema['$defs']['mechanic'],self.schema)
  # Also require the same explanation in an ordinary packet.
  link=self.q.rows('unit_abilities','ability_key',key)[0]
  p=self.packet(link['unit_key'])
  ordinary=next(m for m in p['units'][0]['passives']['abilities'] if m['key']==key)
  self.assertEqual(ordinary['summary'],detail['summary'])
  return detail
 def test_all_twelve_child_chains(self):
  chains=json.loads((ROOT/'fixtures/design/chej2-chains.json').read_text())
  self.assertEqual(len(chains),12)
  self.assertEqual(len({u for c in chains for u in c['units']}),13)
  for case in chains:
   for unit in case['units']:
    with self.subTest(unit=unit,root=case['chain'][0]):
     p=self.packet(unit);r=p['units'][0]['ranged']
     attack=next(a for a in [r,*r['variants']] if a['projectile_key']==case['chain'][0])
     graph=p['payload_graph'];nodes={n['id']:n for n in graph['nodes']}
     reachable={'attack_payload:'+attack['id']}
     if attack['explosion']:reachable.add('attack_payload:'+attack['explosion']['id'])
     for _ in range(len(nodes)):
      more={e['to'] for e in graph['edges'] if e['from'] in reachable}
      if more<=reachable:break
      reachable|=more
     x=next(n for i,n in nodes.items() if i in reachable and n['kind']=='explosions' and n['native_parameters']['explosion_key']==case['chain'][3])
     source=self.q.one('explosions','explosion_key',case['chain'][3])
     for field in ['base_damage','ap_damage','radius','affects_allies']:
      expected=bool(source[field]) if field=='affects_allies' and source[field] is not None else source[field]
      self.assertEqual(x['native_parameters'][field],expected)
     self.q.get_detail(x['id'])
     if attack['explosion']:
      self.assertFalse(any(n['kind']=='explosions' and n['native_parameters']['explosion_key']==attack['explosion']['key'] for i,n in nodes.items() if i in reachable))
 def test_target_class_controls(self):
  for key in ['wh_main_emp_cav_reiksguard','wh_main_emp_cav_pistoliers_1','wh_main_emp_cav_outriders_0','wh_main_emp_cav_demigryph_knights_0']:
   body=self.unit(key)['body'];self.assertEqual(body['size'],'medium');self.assertEqual(body['target_classification']['combat_class'],'large')
  self.assertEqual(self.unit('wh_main_emp_inf_swordsmen')['body']['target_classification']['combat_class'],'infantry')
  self.assertEqual(self.unit('wh2_main_hef_mon_star_dragon')['body']['target_classification']['combat_class'],'large')
 def test_trajectory_and_variants(self):
  for key,mode,elev,maxe in [('wh_main_emp_inf_handgunners','low',0,30),('wh2_main_hef_inf_lothern_sea_guard_0','dual_low_fixed',45,88),('wh_main_emp_art_mortar','fixed',50,56)]:
   r=self.unit(key)['ranged'];n=r['native_parameters']
   self.assertEqual(n['trajectory_sight'],mode)
   if mode!='low':self.assertEqual((n['fixed_elevation'],n['max_elevation']),(str(elev),str(maxe)))
   for a in [r,*r['variants']]:
    native=self.q.one('projectiles','projectile_key',a['projectile_key'])
    for field in ['trajectory_sight','fixed_elevation','max_elevation']:
     self.assertEqual(a['native_parameters'][field],native[field])
 def test_building_multipliers(self):
  for key,value in [('wh_main_dwf_inf_miners_0',3),('wh2_dlc14_skv_inf_warp_grinder_0',2.5),('wh_main_emp_inf_swordsmen',.75),('wh_main_emp_inf_spearmen_0',.5)]:
   self.assertEqual(self.unit(key)['melee']['native_parameters']['building_damage_multiplier'],value)
  self.assertEqual(self.unit('wh2_dlc11_cst_art_queen_bess')['ranged']['native_parameters']['building_damage_multiplier'],2)
  r=self.unit('wh3_main_ksl_veh_little_grom_0')['ranged']
  self.assertEqual({a['native_parameters']['building_damage_multiplier'] for a in [r,*r['variants']]},{2,4})
  r=self.unit('wh2_main_hef_inf_lothern_sea_guard_0')['ranged']
  self.assertFalse(r['native_parameters']['can_damage_buildings']);self.assertEqual(r['native_parameters']['building_damage_multiplier'],.25)
 def test_flaming_scope(self):
  scopes=set();control=False
  for key in ['wh2_dlc09_tmb_cav_hexwraiths','wh3_main_tze_inf_blue_horrors_0','wh_main_dwf_art_flame_cannon','wh_main_emp_inf_swordsmen']:
   p=self.packet(key);traits=p['units'][0]['passives']['attack_traits']
   for kind,t in traits.items():
    values=[item['traits'] for item in t] if kind=='additional' else [t]
    for a in values:
     if not a:continue
     if a['flaming']:
      scopes.add(a['scope']['attack_ref'].split(':')[0])
      summary=p['trait_descriptions']['flaming']['summary']
      self.assertIn('halve healing',summary);self.assertIn('+50%',summary)
     else:control=True
  self.assertTrue(control);self.assertTrue({'melee','ranged','explosion'}<=scopes)
 def test_all_finite_caps(self):
  for key,(group,cap) in CAPS.items():
   m=self.mechanic(key);self.assertIn(f'up to {cap} {group} unit',m['summary'])
  m=self.mechanic('wh3_dlc29_hero_passive_dominate')
  self.assertTrue(any(e['kind']=='periodic_damage' and e['native_parameters']['max_damaged_entities']==25 for e in m['effects']))
  # Unknown and zero remain native values, not invented finite limits.
  c=Packet(self.q)
  for cap in [None,0,-1]:
   text=c.phase_scope({'target_friends':True},{'native_parameters':{'num_effected_friendly_units':cap}})
   self.assertNotIn('up to',text)
 def test_all_spread_links(self):
  for key,(phase,radius) in SPREADS.items():
   m=self.mechanic(key);self.assertTrue(m['spreadings'])
   for s in m['spreadings']:
    self.assertEqual((s['phase_key'],s['radius']),(phase,radius))
    self.assertIn(phase,m['summary']);self.assertIn('native spread radius',m['summary'])
    self.assertNotIn('Spreading reference:',m['summary'])
    self.q.get_detail(s['detail_ref']);self.q.get_detail(s['phase_detail_ref'])
 def test_same_order_and_staged_control(self):
  for key in BRANCHES:
   m=self.mechanic(key);self.assertEqual({p['order'] for p in m['phases']},{1})
   self.assertNotIn('Phase 2',m['summary']);self.assertIn('Recipient branch',m['summary'])
  m=self.mechanic('wh3_main_unit_passive_defensive_stance')
  self.assertIn('successive phases',m['summary']);self.assertIn('Phase 2',m['summary'])
 def test_new_required_fields(self):
  p=self.packet('wh2_main_hef_inf_lothern_sea_guard_0')
  for path in [('body','target_classification'),('ranged','parameter_explanations')]:
   broken=copy.deepcopy(p);del broken['units'][0][path[0]][path[1]]
   with self.assertRaises(ValueError):validate(broken,self.schema,self.schema)
  for field in ['trajectory_sight','fixed_elevation','max_elevation','building_damage_multiplier']:
   broken=copy.deepcopy(p);del broken['units'][0]['ranged']['native_parameters'][field]
   with self.assertRaises(ValueError):validate(broken,self.schema,self.schema)
