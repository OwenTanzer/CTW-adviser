"""Third-review semantic regressions at ordinary default limits."""
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'scripts')]
from ctw_adviser.build import build_snapshot
from ctw_adviser.queries import Queries
from validate_packets import validate,packet_checks
SOURCE=Path(os.environ.get('CTW_DATA_ROOT',ROOT.parent/'CTW-data'))
@unittest.skipUnless((SOURCE/'data/unit_stats/dataset_manifest.json').exists(),'source required')
class ChejFindings3(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.temp=tempfile.TemporaryDirectory();p=Path(cls.temp.name)/'units.sqlite';build_snapshot(SOURCE,p);cls.q=Queries(p)
  cls.schema=json.loads((ROOT/'schema/evidence_packet.schema.json').read_text())
 @classmethod
 def tearDownClass(cls):cls.q.close();cls.temp.cleanup()
 def mechanic(self,key,unit=None):
  d=self.q.get_passive_detail(key)['mechanic']
  unit=unit or self.q.rows('unit_abilities','ability_key',key)[0]['unit_key']
  p=self.q.get_unit_profile(unit)
  validate(p,self.schema,self.schema);packet_checks(p,self.q.get_provenance)
  m=next(m for m in p['units'][0]['passives']['abilities'] if m['key']==key)
  self.assertEqual(m['summary'],d['summary'])
  return m,p
 def test_moulder_polarity_and_source_wording(self):
  m,_=self.mechanic('wh2_dlc16_hero_passive_running_with_the_pack','wh2_dlc16_skv_cha_packmaster_0')
  self.assertIn('target is not a Clan Moulder Monster',m['summary'])
  self.assertIn('up to 3 friendly units',m['summary']);self.assertIn('35 metres',m['summary'])
  condition=next(c for c in m['conditions']['invalid_targets'] if c['key']=='unit_is_moulder_monster')
  self.assertGreaterEqual(len(condition['provenance_refs']),3)
  c,_=self.mechanic('wh_main_hero_passive_forgefire')
  self.assertNotIn('not not',c['summary'])
  c,_=self.mechanic('wh3_dlc29_unit_passive_locus_of_azyr')
  self.assertIn('Excluded target conditions: cannot cast spells',c['summary'])
 def test_phase_flaming_uses_shared_explanation(self):
  for key,unit in [('wh_dlc04_unit_passive_balefire','wh_dlc04_vmp_veh_corpse_cart_1'),('wh3_main_lord_passive_blaze_of_devotion',None)]:
   m,p=self.mechanic(key,unit)
   for text in ['Grants flaming attacks','phase’s recipients while active','halve healing','+50%','fire-vulnerable']:
    self.assertIn(text,m['summary'])
   effects=[e for e in m['effects'] if e.get('native_parameters',{}).get('imbue_ignition',0)>0]
   self.assertTrue(effects)
   self.assertTrue(all(len(e['provenance_refs'])>=2 for e in effects))
   if unit=='wh_dlc04_vmp_veh_corpse_cart_1':
    self.assertFalse(p['units'][0]['passives']['attack_traits']['melee']['flaming'])
  innate=self.q.get_unit_profile('wh3_main_tze_inf_blue_horrors_0')
  self.assertIn('halve healing',innate['trait_descriptions']['flaming']['summary'])
  plain=self.q.get_unit_profile('wh_main_emp_inf_swordsmen')
  self.assertNotIn('flaming',plain['trait_descriptions'])
 def test_labels_preserve_values_operations(self):
  for key,stat,label,operation,value in [
   ('wh2_dlc16_hero_passive_blood_shield','stat_resistance_magic','Spell Resistance','add',20),
   ('wh3_dlc26_character_passive_blood_thirst','stat_healing_power','Incoming Healing Modifier','multiply',1.5),
   ('wh3_dlc20_character_passive_acid_ichor','stat_damage_reflection','Melee Damage Reflection','add',6),
   ('wh3_dlc23_unit_passive_blazing_body','stat_damage_reflection','Melee Damage Reflection','add',25)]:
   m,_=self.mechanic(key);self.assertIn(label,m['summary'])
   e=next(e for e in m['effects'] if e.get('stat')==stat)
   self.assertEqual((e['operation'],e['value']),(operation,value))
   self.assertGreaterEqual(len(e['provenance_refs']),3)
  m,_=self.mechanic('wh3_dlc26_character_passive_blood_thirst');self.assertIn('regeneration received',m['summary'])
 def test_casting_flag_inventory_and_named_cases(self):
  flag='other_abilities_just_activated_after_wind_up'
  rows=self.q.rows('native_special_ability_to_auto_deactivate_flags','deactivate_flag',flag)
  self.assertTrue(rows)
  for key in ['wh3_dlc29_hero_passive_daemon_flies','wh3_main_lore_passive_children_of_nurgle',*[f'wh3_cp1_character_passive_kamau_{x}' for x in ['magic','offence','protect']]]:
   m,_=self.mechanic(key)
   self.assertIn('exact predicate and timing unresolved',m['summary'])
   self.assertIn('casting is absent',m['summary'])
   self.assertNotIn('Deactivates when: other abilities just activated after wind up.',m['summary'])
   c=next(c for c in m['conditions']['deactivates_when'] if c['key']==flag)
   self.assertGreaterEqual(len(c['provenance_refs']),3)
 def test_all_missile_supply_and_ror(self):
  checked=0
  for (key,) in self.q.db.execute('select unit_key from unit_aliases'):
   u=self.q.get_unit_profile(key,limit=256)['units'][0];r=u['ranged']
   if not r or r.get('status')!='present':continue
   for attack in [r,*r['variants']]:
    supply=attack['ammunition_supply'];self.assertEqual(supply['assignment_status'],'sources_agree')
    self.assertEqual(supply['capacity'],attack['ammunition']);checked+=1
  self.assertEqual(checked,772)
  r=self.q.get_unit_profile('wh3_dlc23_chd_veh_iron_daemon_ror_1dreadquake')['units'][0]['ranged']
  values={(a['ammunition_pool'],a['ammunition']) for a in [r,*r['variants']]}
  self.assertEqual(values,{('primary',15),('secondary',560)})
