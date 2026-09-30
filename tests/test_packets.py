import copy
import importlib.util
import json
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('validate_packets',ROOT/'scripts/validate_packets.py')
v=importlib.util.module_from_spec(spec);spec.loader.exec_module(v)

class PacketContractTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.schema=json.loads((ROOT/'schema/evidence_packet.schema.json').read_text())
 def packet(self,name='source_backed/blue_horrors'):
  return json.loads((ROOT/f'fixtures/{name}.json').read_text())
 def check(self,p):v.validate(p,self.schema,self.schema);v.packet_checks(p)
 def reject(self,p):
  with self.assertRaises(ValueError):self.check(p)
 def test_all_registered_fixtures(self):
  v.check_schema(self.schema)
  for entry in json.loads((ROOT/'fixtures/manifest.json').read_text())['fixtures']:
   with self.subTest(entry=entry['path']):self.check(json.loads((ROOT/entry['path']).read_text()))
 def test_tags_cannot_leak_into_ranged_damage(self):
  p=self.packet();p['units'][0]['ranged']['flaming']=True;self.reject(p)
 def test_explosion_cannot_inherit_projectile_scope(self):
  p=self.packet('source_backed/queen_bess');p['units'][0]['passives']['attack_traits']['explosion']['scope']['attack_ref']='ranged:primary';self.reject(p)
 def test_unknown_ranged_is_not_known_none(self):
  p=self.packet('synthetic/unresolved_ranged');p['units'][0]['ranged']=None;self.reject(p)
 def test_missing_trait_explanation(self):
  p=self.packet();del p['trait_descriptions']['flaming'];self.reject(p)
 def test_passives_require_inline_effects_and_summary(self):
  for field in ['summary','effects']:
   p=self.packet();del p['units'][0]['passives']['abilities'][0][field];self.reject(p)
 def test_passive_qualifications_required(self):
  for field in ['requires_effect_enabling','classification_evidence']:
   p=self.packet();del p['units'][0]['passives']['abilities'][0][field];self.reject(p)
  p=self.packet();p['units'][0]['passives']['abilities'][0]['classification_evidence']=['missing'];self.reject(p)
 def test_qualified_source_passive(self):
  p=self.packet('source_backed/wargor');self.check(p)
  self.assertIs(p['units'][0]['passives']['abilities'][0]['requires_effect_enabling'],True)
 def test_trait_component_must_match_attachment(self):
  for kind in ['ranged','explosion']:
   p=self.packet('source_backed/queen_bess');u=p['units'][0]
   self.assertEqual(u['ranged']['component_ref'],'component:0')
   u['passives']['attack_traits'][kind]['scope']['component_ref']='component:0';self.check(p)
   u['passives']['attack_traits'][kind]['scope']['component_ref']='component:1';self.reject(p)
 def test_reviewed_passive_summary_rejects_invented_claim(self):
  p=self.packet();v.reviewed_summary_checks(p)
  p['units'][0]['passives']['abilities'][0]['summary']='While active: grants 999 armour.'
  with self.assertRaisesRegex(ValueError,'reviewed fixture text'):v.reviewed_summary_checks(p)
 def test_activated_options_cannot_contain_effect_payload(self):
  p=self.packet('synthetic/compound_and_variants');p['units'][0]['activated_options'][0]['effects']=[];self.reject(p)
 def test_overflow_cannot_silently_drop_cursor(self):
  p=self.packet('synthetic/passive_overflow')
  next(s for s in p['units'][0]['coverage']['sections'] if s['name']=='abilities')['cursor']=None;self.reject(p)
 def test_unknown_effect_kind_rejected(self):
  p=self.packet();p['units'][0]['passives']['abilities'][0]['effects'][0]['kind']='anything_goes';self.reject(p)
 def test_native_operation_cannot_change_meaning(self):
  p=self.packet('source_backed/kroxigor');p['units'][0]['passives']['abilities'][0]['effects'][0]['native_operation']='add';self.reject(p)
 def test_dangling_references_rejected(self):
  p=self.packet();p['units'][0]['provenance_refs']=['missing'];self.reject(p)
  p=self.packet('synthetic/compound_and_variants');p['payload_graph']['edges'][0]['to']='missing';self.reject(p)
 def test_cycles_and_distinct_repeated_edges_survive(self):
  p=self.packet('synthetic/compound_and_variants');self.check(p)
  self.assertEqual(len(p['payload_graph']['edges']),3)
 def test_null_is_not_zero_and_baseline_is_unmodified(self):
  p=self.packet('source_backed/kroxigor');self.check(p);u=p['units'][0]
  self.assertIsNone(u['ranged']);self.assertEqual(u['body']['barrier_health'],0)
  self.assertEqual(u['melee']['attack'],30)
 def test_native_missingness_and_sentinels_supported(self):
  p=self.packet('synthetic/compound_and_variants');self.check(p)
  self.assertEqual(p['units'][0]['passives']['abilities'][0]['phases'][0]['duration'],-1)
  self.assertIsNone(p['units'][0]['body']['components'][-1]['targetable'])
 def test_schema_changes_cannot_silently_exceed_validator(self):
  s=copy.deepcopy(self.schema);s['not']={}
  with self.assertRaisesRegex(ValueError,'unsupported schema'):v.check_schema(s)

if __name__=='__main__':unittest.main()
