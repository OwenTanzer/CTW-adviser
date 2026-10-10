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
  disagreements=[]; classes=Counter(); health=[]; missing=[]; returned_overrides=set(); units=0
  expected_overrides={row[0] for row in q.db.execute(
   'SELECT id FROM unit_missile_weapon_junctions WHERE battle_entity_stats_override IS NOT NULL')}
  for row in q.db.execute('SELECT unit_key FROM unit_aliases ORDER BY unit_key'):
   key=row[0];u=q.get_unit_profile(key,limit=256)['units'][0];units+=1
   for field in ('ground_speed','flight_speed'):
    if u['movement'][field] is None:missing.append({'unit':key,'field':field})
   if sum(c['health_contribution'] or 0 for c in u['body']['components']) != u['body']['total_hp']:
    health.append(key)
   r=u['ranged']
   if not r or r.get('status')!='present':continue
   for a in [r,*r['variants']]:
    returned_overrides.update(o['junction_id'] for o in a['entity_stat_overrides'])
    if a['ammunition_supply']['assignment_status']=='source_disagreement':
     classes[a['slot']]+=1
     disagreements.append({'unit':key,'weapon':a['weapon_key'],'projectile':a['projectile_key'],
      'slot':a['slot'],'normalized_pool':a['ammunition_pool'],'normalized_ammunition':a['ammunition'],
      'native_pool':a['ammunition_supply']['native_weapon_pool'],'decision':'normalized_source_mapping_mismatch'})
  return {'unit_keys':units,'health_reconciliation_failures':health,'missing_movement':missing,
   'override_attack_rows':len(returned_overrides),
   'missing_override_junctions':sorted(expected_overrides-returned_overrides),
   'unexpected_override_junctions':sorted(returned_overrides-expected_overrides),
   'pool_disagreement_rows':len(disagreements),
   'pool_disagreement_unit_keys':len({r['unit'] for r in disagreements}),
   'disagreements_by_slot':dict(sorted(classes.items())),'disagreements':disagreements}

def acceptance_errors(result):
 errors=[]
 for field in ('health_reconciliation_failures','missing_movement',
               'missing_override_junctions','unexpected_override_junctions'):
  if result[field]:errors.append(field)
 return errors

if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--db',type=Path,required=True);p.add_argument('--output',type=Path,required=True);args=p.parse_args()
 result=audit(args.db);args.output.write_text(json.dumps(result,indent=2)+'\n')
 print(json.dumps({k:v for k,v in result.items() if k!='disagreements'}))
 if acceptance_errors(result):raise SystemExit(1)
