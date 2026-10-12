"""#32 release gates: pinned game evidence; mutations/traces explicitly synthetic."""
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from ctw_adviser.combat import evaluate_matchup, _scenario, _simulate
from ctw_adviser.passives import resolve_passives, normalize_choices, transition, effective_unit
from ctw_adviser.mcp import call_tool, dispatch_method
from ctw_adviser.queries import Queries

A='wh2_main_skv_inf_clanrat_spearmen_0'
B='wh_main_grn_inf_goblin_spearmen'
SIN='wh2_main_unit_passive_strength_in_numbers'
SCURRY='wh2_main_unit_passive_scurry_away'
DB=Path(os.environ.get('CTW_ADVISER_DB',ROOT/'work/adviser.sqlite'))

def scenario(enabled=True):
    return {'baseline':'unmodified_ultra_rank_0','mode':'custom_battle','duration_seconds':120,
            'separation_metres':0,'line_of_sight':True,'terrain_speed_factor':1,
            'sides':{'a':{'order':'hold','facing':'front','fight':True,'fire':False,'active_contacts':8,
                          'charge_duration_seconds':0,'passives':[{'key':SIN,'initial_active':enabled}]},
                     'b':{'order':'hold','facing':'front','fight':True,'fire':False,'active_contacts':8,'charge_duration_seconds':0}}}

@unittest.skipUnless(DB.exists(),'requires pinned snapshot')
class PassiveGates(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.q=Queries(DB)
        cls.packet=cls.q.get_matchup_evidence(A,B,limit=256,include_diagnostics=True,include_provenance=True)
        cls.on=evaluate_matchup(cls.q,A,B,scenario=scenario())
        cls.off=evaluate_matchup(cls.q,A,B,scenario=scenario(False))
    @classmethod
    def tearDownClass(cls):
        cls.q.close()
    def fast(self, sc, packet=None):
        p=packet or self.packet
        normalized=_scenario(sc)
        normalized['_resolved_passives']=[resolve_passives(u,normalized['sides'][side]['passives'],p['provenance']) for u,side in zip(p['units'],('a','b'))]
        return _simulate(p['units'],normalized)
    def item(self, choice=None):
        return resolve_passives(self.packet['units'][0],normalize_choices([choice or {'key':SIN,'initial_active':True}]),self.packet['provenance'])[0]
    def test_exact_initial_active_and_disabled_historical_control(self):
        on,off=self.on,self.off
        base=on['source_facts'][0]
        self.assertEqual((base['melee']['defence'],base['leadership'],base['movement']['speed']),(24,45,4.2))
        phases=on['derived']['ledgers'][0]['effect_phases']
        self.assertEqual(len(phases),1)
        self.assertEqual((phases[0]['start_seconds'],phases[0]['end_seconds']),(0,120))
        e=phases[0]['effective_inputs']
        self.assertEqual((e['melee']['defence'],e['leadership']),(32,51))
        self.assertAlmostEqual(e['movement']['ground_speed'],3.78)
        self.assertLess(on['derived']['ledgers'][0]['incoming_damage']['melee'],off['derived']['ledgers'][0]['incoming_damage']['melee'])
        for row,damage,hp in zip(off['derived']['ledgers'],[1199.086956521741,1095.3488372093004],[8400.913043478286,7864.6511627906875]):
            self.assertAlmostEqual(row['incoming_damage']['melee'],damage,delta=1e-7)
            self.assertAlmostEqual(row['remaining_health'],hp,delta=1e-7)
        self.assertEqual(on['derived']['ledgers'][0]['stopping']['routing'],'unknown_no_morale_model')
    def test_above_at_below_equality(self):
        for equality in ('active','inactive'):
            for fraction,expected in ((.50001,True),(.5,equality=='active'),(.49999,False)):
                sc=scenario();sc['duration_seconds']=.01;sc['sides']['a']['initial_health_fraction']=fraction
                sc['sides']['a']['passives'][0]['equality']=equality
                sc['sides']['b']['fight']=False
                phase=self.fast(sc)[1][0]['effect_phases'][0]
                self.assertEqual(bool(phase['active_keys']),expected)
    def test_threshold_crossing_and_convergence(self):
        results=[]
        for step in (.1,.05,.025):
            sc=scenario();sc['duration_seconds']=10;sc['passive_step_seconds']=step;sc['sides']['a']['initial_health_fraction']=.5001
            rows=self.fast(sc)[1];phases=rows[0]['effect_phases']
            self.assertEqual(len(phases),2);self.assertEqual(phases[0]['end_seconds'],phases[1]['start_seconds'])
            self.assertEqual(phases[1]['active_keys'],[])
            self.assertEqual(phases[1]['effective_inputs']['melee']['defence'],24)
            self.assertEqual(phases[1]['transition_cause'],'health_condition')
            self.assertLess(phases[1]['start_seconds'],1)
            results.append(rows[0]['incoming_damage']['melee'])
        self.assertLess(max(results)-min(results),.5) # bounded fixture, not universal error bound
        sc['sides']['a']['passives'][0]['initial_active']=False
        self.assertGreater(self.fast(sc)[1][0]['incoming_damage']['melee'],results[-1])
    def test_recovery_trace_explicit_vs_unresolved_and_never(self):
        for policy,expected in (('unresolved',False),('never',False),('when_eligible',True)):
            item=self.item({'key':SIN,'initial_active':True,'reactivation':policy})
            transition(item,1,initial=True);self.assertTrue(item['active'])
            transition(item,.49);self.assertFalse(item['active'])
            transition(item,.6);self.assertEqual(item['active'],expected)
            self.assertEqual(bool(item['diagnostics']),policy=='unresolved')
    def test_separate_channels_and_source_backed_second_passive(self):
        sc=scenario();sc['separation_metres']=40;sc['sides']['a']['order']='approach';sc['duration_seconds']=20
        on=self.fast(sc);sc['sides']['a']['passives'][0]['initial_active']=False;off=self.fast(sc)
        self.assertGreater(on[0]['contact']['seconds'],off[0]['contact']['seconds'])
        for enabled,predicate,expected in ((True,False,4.62),(False,False,4.2),(True,True,4.2)):
            sc['sides']['a']['passives']=[{'key':SCURRY,'initial_active':enabled,
                'condition_assumptions':{'morale_is_higher_than_wavering':predicate}}]
            effective=self.fast(sc)[1][0]['effect_phases'][0]['effective_inputs']
            self.assertAlmostEqual(effective['movement']['speed'],expected)
            self.assertEqual(effective['melee']['defence'],24)
            self.assertEqual(effective['leadership'],45)
    def test_projectile_crossing_recomputes_remaining_approach(self):
        p=self.q.get_matchup_evidence(A,'wh2_main_hef_inf_lothern_sea_guard_1',limit=256,include_diagnostics=True,include_provenance=True)
        sc=scenario();sc['separation_metres']=70;sc['duration_seconds']=30
        sc['sides']['a'].update(order='approach',initial_health_fraction=.5001)
        sc['sides']['b'].update(fire=True,cycle_seconds=5,first_shot_delay_seconds=1)
        timing,rows=self.fast(sc,p)
        event=timing['movement_transitions'][0]
        self.assertAlmostEqual(event['closing_speed_metres_per_second'],4.2)
        self.assertAlmostEqual(timing['contact']['seconds'],event['seconds']+event['distance_metres']/4.2)
        self.assertLess(timing['contact']['seconds'],70/3.78)
        self.assertEqual(rows[0]['effect_phases'][1]['start_seconds'],event['seconds'])
        self.assertEqual(rows[0]['effect_phases'][1]['active_keys'],[])

    def test_negative_source_recipient_operation_refs_and_missing_values(self):
        with self.assertRaises(ValueError): resolve_passives(self.packet['units'][1],normalize_choices([{'key':SIN,'initial_active':True}]),self.packet['provenance'])
        for field,value in (('value',None),('value',float('nan')),('operation','divide'),('phase_ref','missing'),('provenance_refs',['missing'])):
            p=copy.deepcopy(self.packet);a=next(a for a in p['units'][0]['passives']['abilities'] if a['key']==SIN);a['effects'][0][field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):self.fast(scenario(),p)
        with self.assertRaises(ValueError):self.item({'key':SCURRY,'initial_active':True})
        with self.assertRaises(ValueError):normalize_choices([{'key':SIN,'initial_active':True}]*2)
        p=copy.deepcopy(self.packet);p['snapshot']['commit']='incompatible'
        class Bad:
            def get_matchup_evidence(self,*a,**k):return p
        with self.assertRaises(ValueError):evaluate_matchup(Bad(),A,B,scenario=scenario())
    def test_unsupported_channel_stays_visible(self):
        p=copy.deepcopy(self.packet);ability=next(a for a in p['units'][0]['passives']['abilities'] if a['key']==SIN)
        extra=copy.deepcopy(ability['effects'][0]);extra['stat']='unknown_stat';ability['effects'].append(extra)
        item=resolve_passives(p['units'][0],normalize_choices([{'key':SIN,'initial_active':True}]),p['provenance'])[0]
        self.assertEqual(len(item['unsupported_effects']),1)
    def test_isolation_repeated_toggle_and_side_swap(self):
        before=copy.deepcopy(self.packet)
        a=self.fast(scenario())[1];self.fast(scenario(False));b=self.fast(scenario())[1]
        self.assertEqual(a,b);self.assertEqual(self.packet,before)
        p=copy.deepcopy(self.packet);p['units'].reverse();sc=scenario();sc['sides']['a'],sc['sides']['b']=sc['sides']['b'],sc['sides']['a']
        swapped=self.fast(sc,p)[1]
        for x,y in zip(a,reversed(swapped)):self.assertEqual(x,y)
    def test_library_cli_adapter_parity_and_hosted_schema(self):
        sc=scenario();sc['duration_seconds']=2
        library=evaluate_matchup(self.q,A,B,scenario=sc)
        env=dict(os.environ,PYTHONPATH=str(ROOT/'src'))
        cli=json.loads(subprocess.check_output([sys.executable,'-m','ctw_adviser.cli','evaluate','--db',str(DB),A,B,'--scenario',json.dumps(sc)],cwd=ROOT,env=env))
        adapter=call_tool(self.q,'evaluate_single_unit_matchup',{'unit_a':A,'unit_b':B,'scenario':sc})['structuredContent']['data']
        self.assertEqual(library,cli);self.assertEqual(library,adapter)
        for invalid in ([{'key':SIN}], 'bad', [{'key':SIN,'initial_active':'yes'}]):
            sc['sides']['a']['passives']=invalid
            r=dispatch_method(self.q,'tools/call',{'name':'evaluate_single_unit_matchup','arguments':{'unit_a':A,'unit_b':B,'scenario':sc}},1)
            self.assertEqual(r['error']['code'],-32602)

if __name__=='__main__':unittest.main()
