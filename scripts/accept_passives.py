#!/usr/bin/env python3
"""Record reproducible #32 library/CLI/local-adapter cases; no live acceptance claim."""
import argparse
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from ctw_adviser.combat import evaluate_matchup, _scenario, _simulate
from ctw_adviser.passives import resolve_passives
from ctw_adviser.queries import Queries
from ctw_adviser.mcp import call_tool

A='wh2_main_skv_inf_clanrat_spearmen_0'
B='wh_main_grn_inf_goblin_spearmen'
KEY='wh2_main_unit_passive_strength_in_numbers'
SCENARIO={'baseline':'unmodified_ultra_rank_0','mode':'custom_battle','duration_seconds':120,
          'separation_metres':0,'line_of_sight':True,'terrain_speed_factor':1,
          'sides':{s:{'order':'hold','facing':'front','fight':True,'fire':False,'active_contacts':8,'charge_duration_seconds':0} for s in ('a','b')}}
SCENARIO['sides']['a']['passives']=[{'key':KEY,'initial_active':True,'equality':'active','reactivation':'unresolved'}]

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--db',required=True);parser.add_argument('--output',required=True);args=parser.parse_args()
    with Queries(args.db) as q:
        on=evaluate_matchup(q,A,B,scenario=SCENARIO)
        disabled=copy.deepcopy(SCENARIO);disabled['sides']['a']['passives'][0]['initial_active']=False
        off=evaluate_matchup(q,A,B,scenario=disabled)
        adapter=call_tool(q,'evaluate_single_unit_matchup',{'unit_a':A,'unit_b':B,'scenario':SCENARIO})['structuredContent']['data']
        env=dict(os.environ,PYTHONPATH=str(Path(__file__).resolve().parents[1]/'src'))
        cli=json.loads(subprocess.check_output([sys.executable,'-m','ctw_adviser.cli','evaluate','--db',args.db,A,B,'--scenario',json.dumps(SCENARIO)],env=env))
        assert on==adapter==cli
        for row,expected in zip(off['derived']['ledgers'],(1199.086956521741,1095.3488372093004)):
            assert abs(row['incoming_damage']['melee']-expected)<1e-7
        packet=q.get_matchup_evidence(A,B,limit=256,include_diagnostics=True,include_provenance=True)
        crossing=[]
        for step in (.1,.05,.025):
            sc=copy.deepcopy(SCENARIO);sc['passive_step_seconds']=step;sc['duration_seconds']=10;sc['sides']['a']['initial_health_fraction']=.5001
            normalized=_scenario(sc);normalized['_resolved_passives']=[resolve_passives(u,normalized['sides'][s]['passives'],packet['provenance']) for u,s in zip(packet['units'],('a','b'))]
            timing,rows=_simulate(packet['units'],normalized)
            crossing.append({'request':sc,'timing':timing,'ledgers':rows})
        damage=[c['ledgers'][0]['incoming_damage']['melee'] for c in crossing]
        assert max(damage)-min(damage)<.5
        receipt={'adviser_commit':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
            'source_snapshot':on['snapshot'],'model_version':on['model_version'],'packet_version':on['source_packet_version'],
            'tolerances':{'historical_damage_health_absolute':1e-7,'equality_health_fraction':1e-9,'crossing_fixture_damage_convergence':.5},
            'requests':{'unit_a':A,'unit_b':B,'enabled':SCENARIO,'disabled':disabled},
            'library_cli_local_adapter_exact_equal':True,'actual_connected_tool_new_model':'pending_release',
            'enabled':on,'disabled':off,'crossing_cases':crossing,
            'calibration':'no battle observations; #5 unchanged'}
        target=Path(args.output);target.parent.mkdir(parents=True,exist_ok=True);target.write_text(json.dumps(receipt,indent=2)+'\n')
        print(json.dumps({'status':'passed','output':str(target),'goblin_damage_enabled':on['derived']['ledgers'][0]['incoming_damage']['melee'],
            'goblin_damage_disabled':off['derived']['ledgers'][0]['incoming_damage']['melee'],'convergence_damage_range':max(damage)-min(damage)}))
if __name__=='__main__':main()
