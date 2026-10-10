"""Capture bounded before/after ordinary-output evidence for Chej's second review."""
import argparse
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]

def main():
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('--db',type=Path,required=True);p.add_argument('--code-root',type=Path,default=ROOT)
 p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 sys.path.insert(0,str(a.code_root/'src'))
 from ctw_adviser.queries import Queries
 sys.path.insert(0,str(ROOT/'tests'))
 from test_chej_findings2 import CAPS,SPREADS,BRANCHES
 with Queries(a.db) as q:
  result={'snapshot':q.get_unit_profile('Lothern Sea Guard')['snapshot'],'schema_version':q.get_unit_profile('Lothern Sea Guard')['schema_version'],'chains':[],'units':{},'passives':{}}
  for case in json.loads((ROOT/'fixtures/design/chej2-chains.json').read_text()):
   for unit in case['units']:
    packet=q.get_unit_profile(unit,limit=256);r=packet['units'][0]['ranged']
    attack=next(a for a in [r,*r['variants']] if a['projectile_key']==case['chain'][0])
    graph=packet['payload_graph'];nodes={n['id']:n for n in graph['nodes']}
    reachable={'attack_payload:'+attack['id']}
    if attack['explosion']:reachable.add('attack_payload:'+attack['explosion']['id'])
    for _ in range(len(nodes)):
     more={e['to'] for e in graph['edges'] if e['from'] in reachable}
     if more<=reachable:break
     reachable|=more
    explosions=[n for i,n in nodes.items() if i in reachable and n['kind']=='explosions' and n['native_parameters']['explosion_key']==case['chain'][3]]
    raw=q.one('explosions','explosion_key',case['chain'][3])
    result['chains'].append({'unit':unit,'root':case['chain'][0],'child_explosion':case['chain'][3],
      'ordinary_present':bool(explosions),'retained_values':{k:raw[k] for k in ['base_damage','ap_damage','radius','affects_allies']}})
  keys=['wh_main_emp_cav_reiksguard','wh_main_emp_cav_pistoliers_1','wh_main_emp_cav_outriders_0','wh_main_emp_cav_demigryph_knights_0',
   'wh_main_emp_inf_swordsmen','wh2_main_hef_mon_star_dragon','wh_main_emp_inf_handgunners','wh2_main_hef_inf_lothern_sea_guard_0','wh_main_emp_art_mortar',
   'wh_main_dwf_inf_miners_0','wh2_dlc14_skv_inf_warp_grinder_0','wh_main_emp_inf_spearmen_0','wh2_dlc11_cst_art_queen_bess','wh3_main_ksl_veh_little_grom_0',
   'wh2_dlc09_tmb_cav_hexwraiths','wh3_main_tze_inf_blue_horrors_0','wh_main_dwf_art_flame_cannon']
  for key in keys:
   packet=q.get_unit_profile(key,limit=256);u=packet['units'][0];attacks=[]
   for kind in ['melee','ranged']:
    r=u[kind]
    if r and (kind=='melee' or r.get('status')=='present'):
     for attack in [r,*r['variants']]:
      fields=['building_damage_multiplier']+(['trajectory_sight','fixed_elevation','max_elevation'] if kind=='ranged' else [])
      attacks.append({'kind':kind,'weapon':attack['weapon_key'],'projectile':attack.get('projectile_key'),
       'parameters':{f:attack['native_parameters'][f] for f in fields if f in attack['native_parameters']}})
   result['units'][key]={'size':u['body']['size'],'classification':u['body'].get('target_classification'),'attacks':attacks,'flaming':packet['trait_descriptions'].get('flaming')}
  for key in [*CAPS,*SPREADS,*BRANCHES,'wh3_main_unit_passive_defensive_stance']:
   link=q.rows('unit_abilities','ability_key',key)[0]
   packet=q.get_unit_profile(link['unit_key'],limit=256)
   m=next(m for m in packet['units'][0]['passives']['abilities'] if m['key']==key)
   detail=q.get_passive_detail(key)['mechanic']
   if m['summary']!=detail['summary']:raise ValueError('ordinary/detail explanation differs: '+key)
   result['passives'][key]={'unit':link['unit_key'],'summary':m['summary'],'spreadings':m.get('spreadings'),
    'phases':[{k:ph[k] for k in ['key','order','target_self','target_friends','target_enemies']} for ph in m['phases']],
    'caps':{k:v for k,v in m['native_parameters'].items() if k.startswith('num_effected_')}}
  a.output.parent.mkdir(parents=True,exist_ok=True)
  a.output.write_text(json.dumps(result,indent=2)+'\n')
  print(json.dumps({'version':result['schema_version'],'chain_instances':len(result['chains']),'child_explosions_visible':sum(x['ordinary_present'] for x in result['chains']),'units':len(keys),'passives':len(result['passives'])}))
if __name__=='__main__':main()
