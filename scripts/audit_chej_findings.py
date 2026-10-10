"""Audit supplement coverage, health reconciliation and ammunition disagreements."""
import argparse
from collections import Counter
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from ctw_adviser.queries import Queries

def audit(db):
 with Queries(db) as q:
  disagreements=[]; classes=Counter(); health=[]; missing=[]; override_links=0; units=0
  for row in q.db.execute('SELECT unit_key FROM unit_aliases ORDER BY unit_key'):
   key=row[0];u=q.get_unit_profile(key,limit=256)['units'][0];units+=1
   for field in ('ground_speed','flight_speed'):
    if u['movement'][field] is None:missing.append({'unit':key,'field':field})
   if sum(c['health_contribution'] or 0 for c in u['body']['components']) != u['body']['total_hp']:
    health.append(key)
   r=u['ranged']
   if not r or r.get('status')!='present':continue
   for a in [r,*r['variants']]:
    override_links+=bool(a['entity_stat_overrides'])
    if a['ammunition_supply']['assignment_status']=='source_disagreement':
     classes[a['slot']]+=1
     disagreements.append({'unit':key,'weapon':a['weapon_key'],'projectile':a['projectile_key'],
      'slot':a['slot'],'normalized_pool':a['ammunition_pool'],'normalized_ammunition':a['ammunition'],
      'native_pool':a['ammunition_supply']['native_weapon_pool'],'decision':'unresolved_engine_precedence'})
  return {'unit_keys':units,'health_reconciliation_failures':health,'missing_movement':missing,
   'override_attack_rows':override_links,'pool_disagreement_rows':len(disagreements),
   'pool_disagreement_unit_keys':len({r['unit'] for r in disagreements}),
   'disagreements_by_slot':dict(sorted(classes.items())),'disagreements':disagreements}
if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--db',type=Path,required=True);p.add_argument('--output',type=Path,required=True);args=p.parse_args()
 result=audit(args.db);args.output.write_text(json.dumps(result,indent=2)+'\n')
 print(json.dumps({k:v for k,v in result.items() if k!='disagreements'}))
 if result['health_reconciliation_failures']:raise SystemExit(1)
