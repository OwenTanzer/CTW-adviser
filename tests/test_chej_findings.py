"""Named source-backed acceptance cases for the broader unit findings."""
import copy
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'scripts')]
from ctw_adviser.build import build_snapshot
from ctw_adviser.queries import Queries
from validate_packets import validate, packet_checks
from audit_chej_findings import audit, acceptance_errors
SOURCE=Path(os.environ.get('CTW_DATA_ROOT',ROOT.parent/'CTW-data'))

@unittest.skipUnless((SOURCE/'data/unit_stats/dataset_manifest.json').exists(),'pinned source required')
class ChejFindings(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.temp=tempfile.TemporaryDirectory(); db=Path(cls.temp.name)/'units.sqlite'
  build_snapshot(SOURCE,db);cls.q=Queries(db)
  cls.schema=json.loads((ROOT/'schema/evidence_packet.schema.json').read_text())
 @classmethod
 def tearDownClass(cls):cls.q.close();cls.temp.cleanup()
 def packet(self,key,**kwargs):
  kwargs.setdefault('limit',256)
  p=self.q.get_unit_profile(key,**kwargs)
  validate(p,self.schema,self.schema);packet_checks(p,provenance_resolver=self.q.get_provenance)
  return p
 def unit(self,key):return self.packet(key)['units'][0]
 def test_precursor_families_and_control(self):
  for key in ['wh2_dlc17_lzd_inf_chameleon_stalkers_0','wh2_dlc17_lzd_inf_chameleon_stalkers_0_blessed','wh3_dlc23_chd_inf_hobgoblin_sneaky_gits','wh3_main_kho_mon_soul_grinder_0']:
   r=self.unit(key)['ranged']
   for a in [r,*r['variants']]:
    self.assertIs(a['firing_policy']['precursor'],True)
    self.assertIn('ordered charge target',a['firing_policy']['summary'])
  self.assertIs(self.unit('wh2_main_hef_inf_lothern_sea_guard_0')['ranged']['firing_policy']['precursor'],False)
 def test_pool_conflicts_not_silently_resolved(self):
  for key,weapon in [('wh2_main_hef_inf_lothern_sea_guard_0','wh3_dlc27_hef_sea_guard_bow_anti_infantry'),('wh3_dlc23_chd_veh_iron_daemon_1dreadquake','wh3_dlc23_chd_veh_iron_daemon_cannonade_secondary')]:
   r=self.unit(key)['ranged'];a=next(a for a in [r,*r['variants']] if a['weapon_key']==weapon)
   self.assertEqual(a['ammunition_supply']['assignment_status'],'source_disagreement')
   self.assertIsNone(a['ammunition_supply']['effective_pool'])
 def test_infinite_and_override_identity(self):
  self.assertIs(self.unit('wh2_main_hef_inf_lothern_sea_guard_0')['ranged']['ammunition_supply']['infinite_secondary'],False)
  for suffix in ['','_grungni','_grungni_mp']:
   r=self.unit('wh3_dlc25_dwf_veh_thunderbarge'+suffix)['ranged']
   self.assertIs(r['ammunition_supply']['infinite_secondary'],True)
   if suffix=='_grungni_mp':self.assertEqual(r['variants'],[])
  r=self.unit('wh3_dlc25_emp_veh_marienburg_land_ship')['ranged']
  overrides=[o for a in r['variants'] for o in a['entity_stat_overrides']]
  self.assertEqual({o['key'] for o in overrides},{'wh3_dlc25_emp_mnt_veh_land_ship_crew_repeater','wh3_dlc25_emp_veh_land_ship_crows_nest_hochland_long_rifle'})
  for o in overrides:
   self.assertIsNotNone(o['base_missile_weapon']);self.q.get_detail(o['detail_ref'])
 def test_explosion_types_and_own_settings(self):
  x=self.unit('wh2_dlc11_cst_art_queen_bess')['ranged']['explosion']
  self.assertIs(x['native_parameters']['affects_allies'],True)
  self.assertEqual(x['native_parameters']['force'],450)
  x=self.unit('wh_main_dwf_art_flame_cannon_grudge_reward')['ranged']['explosion']
  self.assertEqual(x['native_parameters']['fuse_distance_from_target'],'40.0000')
  self.assertEqual(x['native_parameters']['duration'],1)
 def test_movement_reload_arcs_health(self):
  mounted=self.unit('wh2_dlc10_def_cha_crone_5')['movement']
  self.assertEqual(mounted['primary_body_key'],'wh_dlc01_mnt_flying_manticore_blood')
  self.assertEqual((mounted['ground_speed'],mounted['flight_speed']),(7,8.5))
  for key,ground,flight in [('wh2_main_hef_mon_sun_dragon',6.5,10),('wh2_main_hef_mon_star_dragon',6.5,8.5),('wh_main_dwf_veh_gyrocopter_0',7,10)]:
   m=self.unit(key)['movement'];self.assertEqual((m['ground_speed'],m['flight_speed']),(ground,flight))
  for key,skill in [('wh2_dlc10_hef_inf_the_storm_riders_ror_0',18),('wh2_main_hef_inf_lothern_sea_guard_0',0)]:
   r=self.unit(key)['ranged']['reload'];self.assertEqual((r['projectile_base_interval'],r['unit_reload_skill']),(11,skill))
  for key,arc in [('wh_main_emp_cav_pistoliers_1',360),('wh_main_emp_cav_outriders_0',70)]:
   self.assertEqual(self.unit(key)['body']['firing_arc']['native_fire_arc_close'],arc)
  for key,total in [('wh2_dlc11_cst_art_queen_bess',7300),('wh_main_grn_cav_goblin_wolf_chariot',6240)]:
   b=self.unit(key)['body'];self.assertEqual(sum(c['health_contribution'] for c in b['components']),total)
 def test_required_fields_rejected_and_projection_stable(self):
  p=self.packet('wh2_dlc11_cst_art_queen_bess')
  for field in ['firing_policy','reload','ammunition_supply','entity_stat_overrides']:
   damaged=copy.deepcopy(p);del damaged['units'][0]['ranged'][field]
   with self.assertRaises(ValueError):validate(damaged,self.schema,self.schema)
  damaged=copy.deepcopy(p);damaged['units'][0]['ranged']['explosion']['native_parameters']['affects_allies']='true'
  with self.assertRaises(ValueError):validate(damaged,self.schema,self.schema)
  expanded=self.packet('wh2_dlc11_cst_art_queen_bess',include_provenance=True)
  self.assertEqual(p['units'],expanded['units']);self.assertEqual(p['sources'],{})
 def test_relationship_contradictions_rejected(self):
  for key,change in [
   ('wh2_main_hef_inf_lothern_sea_guard_0',lambda u:u['movement'].__setitem__('speed',999)),
   ('wh2_main_hef_inf_lothern_sea_guard_0',lambda u:u['body']['firing_arc'].__setitem__('primary_body_key','wrong')),
   ('wh2_main_hef_inf_lothern_sea_guard_0',lambda u:u['ranged']['reload'].__setitem__('projectile_base_interval',999)),
   ('wh2_main_hef_inf_lothern_sea_guard_0',lambda u:u['ranged']['ammunition_supply'].__setitem__('effective_pool',None)),
   ('wh2_main_hef_inf_lothern_sea_guard_0',lambda u:u['ranged']['variants'][0]['ammunition_supply'].__setitem__('assignment_status','sources_agree')),
   ('wh2_dlc11_cst_art_queen_bess',lambda u:u['body']['components'][0].__setitem__('health_contribution',1)),
   ('wh2_dlc11_cst_art_queen_bess',lambda u:u['body']['health_aggregation'].__setitem__('rule','primary_body_only')),
  ]:
   with self.subTest(key=key,change=change):
    damaged=copy.deepcopy(self.packet(key));change(damaged['units'][0])
    validate(damaged,self.schema,self.schema)
    with self.assertRaises(ValueError):packet_checks(damaged,self.q.get_provenance)
 def test_audit_fails_missing_native_movement(self):
  damaged=Path(self.temp.name)/'missing-speed.sqlite'
  with sqlite3.connect(damaged) as out:self.q.db.backup(out)
  with sqlite3.connect(damaged) as db:
   db.execute("UPDATE battle_entities SET run_speed=NULL WHERE key=(SELECT source_battle_entity_key FROM unit_profiles WHERE unit_key='wh2_main_hef_inf_lothern_sea_guard_0')")
  result=audit(damaged)
  self.assertIn('missing_movement',acceptance_errors(result))
  self.assertTrue(result['missing_movement'])
 def test_final_component_page_does_not_claim_whole_unit_health(self):
  key='wh2_dlc11_cst_art_queen_bess'
  first=self.packet(key,section='components',limit=1)
  section=next(s for s in first['units'][0]['coverage']['sections'] if s['name']=='components')
  self.assertEqual(section['state'],'partial')
  last=self.packet(key,section='components',limit=1,cursor=section['cursor'])
  section=next(s for s in last['units'][0]['coverage']['sections'] if s['name']=='components')
  self.assertEqual((section['state'],section['offset'],section['returned']),('complete',1,1))
  self.assertNotEqual(last['units'][0]['body']['components'][0]['health_contribution'],last['units'][0]['body']['total_hp'])
