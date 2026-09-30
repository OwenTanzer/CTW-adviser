"""Invented structural examples. NONE of these values are game evidence."""
import copy
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
def dump(path,value):path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(value,indent=2)+'\n')
def synthetic():
 p=json.loads((ROOT/'fixtures/source_backed/blue_horrors.json').read_text())
 p['snapshot']['commit']='0'*40
 p['sources']={'synthetic':{'path':'SYNTHETIC-NOT-GAME-DATA','sha256':'0'*64,'owner':'units'}}
 p['provenance']={'synthetic':{'source_id':'synthetic','logical_record':2,'key':{'kind':'invented'},'source_line':None,'source_patch':None}}
 def rewrite(x):
  if isinstance(x,dict):
   for k,v in list(x.items()):
    if k in ('provenance_refs','classification_evidence'):x[k]=['synthetic']
    else:rewrite(v)
  elif isinstance(x,list):
   for v in x:rewrite(v)
 rewrite(p)
 u=p['units'][0];u['identity']={'unit_key':'synthetic_hybrid','subculture_key':'synthetic_roster','faction_name':['Synthetic faction'],'name':'SYNTHETIC hybrid — invented schema exercise','unit_type':'synthetic_monster'}
 u['passives']['attributes']=[{'key':'synthetic_attribute','name':'Synthetic attribute','summary':'Invented behavioral tag for schema validation.','provenance_refs':['synthetic']}]
 for i,c in enumerate(u['body']['components']):c['id']='component:'+str(i)
 u['coverage']['gaps']=[{'code':'synthetic','section':s,'summary':'Invented test case; no assertion about game behavior.','provenance_refs':['synthetic']} for s in ['weapons','abilities','activated_options']]
 phases=[{'key':'synthetic_phase_a','order':1,'target_self':True,'target_friends':False,'target_enemies':False,'duration':-1,'lifecycle':{'native_intensity':'unknown_token'},'provenance_refs':['synthetic']},{'key':'synthetic_phase_b','order':2,'target_self':False,'target_friends':True,'target_enemies':False,'duration':10,'lifecycle':{'replacement':'unresolved'},'provenance_refs':['synthetic']}]
 common={'phase_ref':'synthetic_phase_a','provenance_refs':['synthetic']}
 effects=[
  {'kind':'stat_modifier',**common,'stat':'melee_attack','operation':'add','native_operation':'add','value':5},
  {'kind':'stat_modifier',**common,'stat':'speed','operation':'multiply','native_operation':'mult','value':1.1},
  {'kind':'attribute_effect',**common,'attribute_key':'synthetic_stalk','operation':'grant','recipient':'phase recipients','native_parameters':{'native_grant':True}},
  {'kind':'periodic_damage',**common,'native_parameters':{'damage_amount':3,'hp_change_frequency':1,'max_damaged_entities':2}},
  {'kind':'healing',**common,'phase_ref':'synthetic_phase_b','native_parameters':{'heal_amount':0.01,'barrier_heal_amount':0,'hp_change_frequency':2,'resurrect':True,'limits':{'native_cap':-1}}},
  {'kind':'payload_reference',**common,'node_ref':'payload:a','relationship':'imbues_attack'},
  {'kind':'unresolved',**common,'native_kind':'synthetic_transformation','native_parameters':{'spawned_land_unit':'synthetic_land_key'},'reason':'Invented unknown effect; no numeric substitute.'}]
 u['passives']['abilities']=[{'requires_effect_enabling':True,'classification_evidence':['synthetic'],'key':'synthetic_compound','name':'Synthetic compound passive','culture_key':'*','summary':'Invented compound passive; effect variants and lifecycle remain separate.','native_parameters':{'effect_range':15},'conditions':{'activates_when':[],'deactivates_when':[{'key':'synthetic_health_above_50','summary':'Synthetic deactivation threshold; equality behavior unknown.','provenance_refs':['synthetic']}],'recipient_requirements':[],'unresolved':[]},'phases':phases,'effects':effects,'provenance_refs':['synthetic'],'detail_ref':'synthetic:compound'}]
 p['detail_refs']['synthetic:compound']={'kind':'passive','key':'synthetic_compound'}
 u['activated_options']=[{'key':'synthetic_button','name':'Synthetic deliberate option','classification':'activated_option','culture_key':'synthetic_culture','requires_effect_enabling':True,'classification_evidence':['synthetic'],'provenance_refs':['synthetic'],'detail_ref':'synthetic:option'},{'key':'synthetic_ambiguous','name':None,'classification':'unresolved','culture_key':'*','requires_effect_enabling':None,'classification_evidence':['synthetic'],'provenance_refs':['synthetic'],'detail_ref':'synthetic:ambiguous'}]
 for key in ['option','ambiguous']:p['detail_refs']['synthetic:'+key]={'kind':'option','key':'synthetic_'+key}
 a=copy.deepcopy(u['ranged']);a.pop('status');a.pop('variants');a['id']='ranged:alternate';a['projectile_key']='synthetic_alternate';a['is_default']=False;a['ammunition_pool']=u['ranged']['ammunition_pool'];a['base_damage']=9;u['ranged']['variants']=[a]
 traits=copy.deepcopy(u['passives']['attack_traits']['ranged']);traits['scope']['attack_ref']=a['id'];traits['magical']=False;traits['flaming']=False
 u['passives']['attack_traits']['additional']=[{'kind':'ranged','traits':traits}]
 u['body']['components'].append({'id':'component:secondary','role':'synthetic_crew','count':4,'hp_per_component':10,'bonus_hp_per_component':0,'known_hp_total':40,'size':'small','targetable':None,'primary':False,'provenance_refs':['synthetic']})
 p['payload_graph']={'nodes':[{'id':'payload:'+key,'kind':'synthetic_payload','key':'synthetic_'+key,'native_parameters':{},'provenance_refs':['synthetic']} for key in ['a','b']],
 'edges':[{'from':'payload:a','to':'payload:b','relationship':'shrapnel','order':1,'provenance_refs':['synthetic']},{'from':'payload:a','to':'payload:b','relationship':'contact','order':2,'provenance_refs':['synthetic']},{'from':'payload:b','to':'payload:a','relationship':'cycle','order':None,'provenance_refs':['synthetic']}]}
 for section in u['coverage']['sections']:
  counts={'components':len(u['body']['components']),'weapons':3,'attributes':1,'abilities':1,'activated_options':2}
  section.update(returned=counts[section['name']])
  if section['state']=='complete':section['total']=section['returned']
 return p

def main():
 p=synthetic();cases=[('compound_and_variants',p)]
 no=copy.deepcopy(p);u=no['units'][0];u['identity']['unit_key']='synthetic_melee_only';u['identity']['name']='SYNTHETIC melee-only unit';u['ranged']=None;u['coverage']['ranged']='known_none';u['passives']['attack_traits'].update(ranged=None,explosion=None,additional=[])
 for s in u['coverage']['sections']:
  if s['name']=='weapons':s['returned']=1
 # A complete two-unit dummy demonstrates ranged and known-none together.
 combo=copy.deepcopy(p);combo['units'].append(u);cases.append(('complete_dummy',combo))
 missing=copy.deepcopy(no);u=missing['units'][0];u['ranged']={'status':'unresolved'};u['coverage']['ranged']='unresolved';u['coverage']['gaps'].append({'code':'unresolved_weapon_join','section':'ranged','summary':'Synthetic weapon link exists but its payload is unavailable.','provenance_refs':['synthetic']});cases.append(('unresolved_ranged',missing))
 omitted=copy.deepcopy(missing);omitted['mode']='melee';u=omitted['units'][0];u['ranged']={'status':'omitted'};u['coverage']['ranged']='omitted';u['coverage']['gaps'][-1]={'code':'section_projection','section':'ranged','summary':'Ranged evidence intentionally omitted by this melee projection; absence is not established.','provenance_refs':['synthetic']};cases.append(('melee_projection',omitted))
 overflow=copy.deepcopy(p)
 for s in overflow['units'][0]['coverage']['sections']:
  if s['name']=='abilities':s.update(state='partial',total=3,cursor='synthetic:next-passives')
 cases.append(('passive_overflow',overflow))
 index=json.loads((ROOT/'fixtures/manifest.json').read_text());index['fixtures']=[x for x in index['fixtures'] if x['kind']=='source_backed']
 for name,value in cases:
  path=f'fixtures/synthetic/{name}.json';dump(ROOT/path,value);index['fixtures'].append({'path':path,'kind':'synthetic','purpose':'Invented structural fixture; never game evidence.'})
 dump(ROOT/'fixtures/manifest.json',index)
if __name__=='__main__':main()
