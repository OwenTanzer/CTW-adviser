"""Reproducible issue #28 compact payload and warm latency measurements."""
import argparse
import json
from pathlib import Path
import statistics
import sys
from time import perf_counter
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from ctw_adviser.queries import Queries

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--db',required=True)
p.add_argument('--output',required=True)
a=p.parse_args()
base={'and':[{'field':'subculture_key','op':'eq','value':'wh2_main_sc_hef_high_elves'},
              {'field':'source_caste','op':'in','value':['lord','hero']}]}
cases={'high_elf_characters':{'filters':base,'limit':100},
       'high_elf_families':{'filters':base,'mode':'families','limit':100},
       'low_cost_ap_sort':{'filters':{'field':'multiplayer_cost','op':'lte','value':1000},
                          'sort':[{'field':'weapon_ap_damage','direction':'desc'}],
                          'fields':['multiplayer_cost','weapon_ap_damage'],'limit':50},
       'full_roster_first_page':{'limit':100}}
report={'method':'20 warm calls per case; Python perf_counter; compact UTF-8 JSON bytes; OS cache not cleared. Local library, not hosted network latency.', 'cases':{}}
with Queries(a.db) as q:
 report['snapshot']=q.snapshot
 for name,args in cases.items():
  times=[]
  for _ in range(20):
   t=perf_counter();result=q.search_units(**args);times.append((perf_counter()-t)*1000)
  report['cases'][name]={'arguments':args,'median_ms':round(statistics.median(times),3),
      'max_ms':round(max(times),3),'response_bytes':len(json.dumps(result,ensure_ascii=False,separators=(',',':')).encode()),
      'total_count':result['total_count'],'count_unit':result['count_unit'],
      'total_matching_variants':result['total_matching_variants'],'returned_count':result['returned_count'],
      'complete':result['complete']}
Path(a.output).write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report['cases'],indent=2))
