"""Record ordinary/detail agreement and all classified uses of the reviewed casting flag."""
import argparse
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from ctw_adviser.queries import Queries

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--db',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 with Queries(a.db) as q:
  keys=['wh2_dlc16_hero_passive_running_with_the_pack','wh_dlc04_unit_passive_balefire','wh3_main_lord_passive_blaze_of_devotion',
   'wh2_dlc16_hero_passive_blood_shield','wh3_dlc26_character_passive_blood_thirst','wh3_dlc20_character_passive_acid_ichor','wh3_dlc23_unit_passive_blazing_body']
  flag='other_abilities_just_activated_after_wind_up'
  rows=q.rows('native_special_ability_to_auto_deactivate_flags','deactivate_flag',flag)
  supported=[];deferred=[]
  for row in rows:
   key=row['special_ability'];option=q.one('ability_option_metadata','ability_key',key)
   links=q.rows('unit_abilities','ability_key',key)
   if option and option['classification']=='core_passive' and links:supported.append(key)
   else:deferred.append(key)
  native=json.loads((ROOT/'fixtures/design/chej3-casting-flag-uses.json').read_text())['special_ability_to_auto_deactivate_flags.csv']
  report={'native_casting_flag_junctions':len(native),'source_commit':q.snapshot['source_commit'],'casting_flag_junctions':len(rows),'classified_casting_uses':len(set(supported)),'outside_core_passive_projection':sorted(set(deferred)),'mechanics':{}}
  for key in sorted(set(keys+supported)):
   links=q.rows('unit_abilities','ability_key',key)
   link=next((l for l in links if l['culture_key']=='*'),links[0])
   detail=q.get_passive_detail(key,culture=link['culture_key'])['mechanic']
   packet=q.get_unit_profile(link['unit_key'])
   ordinary=next((m for m in packet['units'][0]['passives']['abilities'] if m['key']==key and m['culture_key']==link['culture_key']),None)
   if ordinary is None:raise ValueError('Ordinary mechanic missing: '+key)
   if ordinary['summary']!=detail['summary']:raise ValueError('Ordinary/detail mismatch: '+key)
   if key in supported and 'exact predicate and timing unresolved' not in detail['summary']:raise ValueError('Casting timing asserted: '+key)
   report['mechanics'][key]={'unit_key':link['unit_key'],'culture_key':link['culture_key'],'summary':detail['summary']}
  a.output.write_text(json.dumps(report,indent=2)+'\n')
  print(json.dumps({k:v for k,v in report.items() if k!='mechanics'}))
if __name__=='__main__':main()
