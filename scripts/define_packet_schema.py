"""Author the v1 evidence schema; no source data or combat calculation."""
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
S={'type':'string','minLength':1}; N={'type':['number','null']}; B={'type':['boolean','null']}
def enum(*values):return {'enum':list(values)}
def arr(item,minimum=0):return {'type':'array','items':item,'minItems':minimum}
def obj(props,required=None):return {'type':'object','properties':props,'required':list(props) if required is None else required,'additionalProperties':False}
def ref(name):return {'$ref':'#/$defs/'+name}
def mapping(value):return {'type':'object','additionalProperties':value}
def nullable(value):return {'anyOf':[{'type':'null'},value]}
def numbers(*keys):return {k:N for k in keys}
def const(value):return {'const':value}
refs=arr(S,1)
native=mapping({'type':['string','number','boolean','null']})
defs={}
defs['gap']=obj({'code':S,'section':S,'summary':S,'provenance_refs':arr(S)},['code','section','summary','provenance_refs'])
defs['section']=obj({'name':enum('components','weapons','attributes','abilities','activated_options'),'state':enum('complete','partial','omitted','unresolved'),'returned':{'type':'integer','minimum':0},'total':{'type':['integer','null'],'minimum':0},'cursor':nullable(S)})
defs['coverage']=obj({'melee':enum('present','known_none','unresolved','omitted'),'ranged':enum('present','known_none','unresolved','omitted'),'sections':arr(ref('section'),5),'gaps':arr(ref('gap'))})
defs['identity']=obj({'unit_key':S,'subculture_key':S,'faction_name':arr(S,1),'name':nullable(S),'unit_type':S,'traits':arr(S)},['unit_key','subculture_key','faction_name','name','unit_type'])
defs['component']=obj({'id':S,'role':S,'count':N,'hp_per_component':N,'bonus_hp_per_component':N,'known_hp_total':N,'size':nullable(S),'targetable':B,'primary':B,'provenance_refs':refs})
defs['body']=obj({**numbers('entity_count','hp_per_entity','total_hp','barrier_health'),'size':nullable(S),'components':arr(ref('component'))})
defs['scope']=obj({'attack_ref':S,'component_ref':nullable(S)})
defs['traits']=obj({'scope':ref('scope'),**numbers('bonus_vs_infantry','bonus_vs_large'),'magical':B,'flaming':B,'provenance_refs':refs})
defs['extra_traits']=obj({'kind':enum('melee','ranged','explosion'),'traits':ref('traits')})
defs['melee_attack']=obj({'id':S,'weapon_key':nullable(S),**numbers('attack','defence','base_damage','ap_damage','attack_interval','charge_bonus','max_splash_targets'),'provenance_refs':refs})
defs['explosion']=obj({'id':S,'key':S,**numbers('base_damage','ap_damage','radius'),'provenance_refs':refs})
defs['ranged_attack']=obj({'id':S,'weapon_key':nullable(S),'projectile_key':nullable(S),'component_ref':nullable(S),'slot':S,'ammunition_pool':nullable(S),'is_default':B,
 **numbers('range','minimum_range','ammunition','reload_time','base_damage','ap_damage','projectiles_per_shot','shots_per_volley','burst_size','burst_shot_delay','velocity','accuracy','spread','marksmanship_bonus','calibration_distance','calibration_area'),
 'explosion':nullable(ref('explosion')),'detail_ref':S,'provenance_refs':refs})
defs['melee']=obj({**defs['melee_attack']['properties'],'variants':arr(ref('melee_attack'))})
defs['ranged_present']=obj({'status':const('present'),**defs['ranged_attack']['properties'],'variants':arr(ref('ranged_attack'))})
defs['ranged']= {'oneOf':[{'type':'null'},ref('ranged_present'),obj({'status':enum('unresolved','omitted')})]}
defs['condition']=obj({'key':S,'summary':S,'provenance_refs':refs})
defs['conditions']=obj({'activates_when':arr(ref('condition')),'deactivates_when':arr(ref('condition')),'recipient_requirements':arr(ref('condition')),'unresolved':arr(ref('condition'))})
defs['phase']=obj({'key':S,'order':{'type':['integer','null']},'target_self':B,'target_friends':B,'target_enemies':B,'duration':N,'lifecycle':native,'provenance_refs':refs})
effect_common={'phase_ref':nullable(S),'provenance_refs':refs}
effects={
 'stat_modifier':{'stat':S,'operation':enum('add','multiply','native'),'native_operation':S,'value':N},
 'attribute_effect':{'attribute_key':S,'operation':enum('grant','remove','native'),'recipient':nullable(S),'native_parameters':native},
 'periodic_damage':{'native_parameters':obj(numbers('damage_amount','hp_change_frequency','max_damaged_entities'))},
 'healing':{'native_parameters':obj({**numbers('heal_amount','barrier_heal_amount','hp_change_frequency'),'resurrect':B,'limits':native})},
 'payload_reference':{'node_ref':S,'relationship':S},
 'unresolved':{'native_kind':S,'native_parameters':native,'reason':S}}
for name,properties in effects.items():defs['effect_'+name]=obj({'kind':const(name),**effect_common,**properties})
defs['effect']={'oneOf':[ref('effect_'+name) for name in effects]}
defs['mechanic']=obj({'requires_effect_enabling':B,'classification_evidence':refs,'key':S,'name':nullable(S),'culture_key':S,'summary':S,'native_parameters':native,'conditions':ref('conditions'),'phases':arr(ref('phase')),'effects':arr(ref('effect'),1),'provenance_refs':refs,'detail_ref':S})
defs['attribute']=obj({'key':S,'name':nullable(S),'summary':S,'provenance_refs':refs})
defs['option']=obj({'key':S,'name':nullable(S),'classification':enum('activated_option','unresolved'),'culture_key':S,'requires_effect_enabling':B,'classification_evidence':refs,'provenance_refs':refs,'detail_ref':S})
defs['passives']=obj({'protection':obj(numbers('armour','shield_block_chance','physical_resistance','missile_resistance','spell_resistance','fire_resistance','ward_save')),
 'attack_traits':obj({'melee':nullable(ref('traits')),'ranged':nullable(ref('traits')),'explosion':nullable(ref('traits')),'additional':arr(ref('extra_traits'))}),
 'attributes':arr(ref('attribute')),'abilities':arr(ref('mechanic'))})
defs['unit']=obj({'identity':ref('identity'),'body':ref('body'),'movement':obj(numbers('speed','mass')),'leadership':N,'melee':nullable(ref('melee')),'ranged':ref('ranged'),'passives':ref('passives'),
 'cost':obj(numbers('multiplayer','campaign_recruitment','campaign_upkeep')),'activated_options':arr(ref('option')),'coverage':ref('coverage'),'provenance_refs':refs})
defs['source']=obj({'path':S,'sha256':{'type':'string','pattern':'^[0-9a-f]{64}$'},'owner':S})
defs['evidence']=obj({'source_id':S,'logical_record':{'type':'integer','minimum':2},'key':mapping({'type':'string'}),'source_line':{'type':['integer','null'],'minimum':1},'source_patch':nullable(S)})
defs['owner']=obj({'patch':S,'build':S,'schema':{'type':'integer','minimum':1}})
defs['snapshot']=obj({'commit':{'type':'string','pattern':'^[0-9a-f]{40}$'},'owners':mapping(ref('owner')),'baseline':obj({'game':const('warhammer_3'),'unit_scale':S,'rank':{'type':'integer','minimum':0},'context':S})})
defs['description']=obj({'summary':S,'provenance_refs':refs})
defs['node']=obj({'id':S,'kind':S,'key':S,'native_parameters':native,'provenance_refs':refs})
defs['edge']=obj({'from':S,'to':S,'relationship':S,'order':{'type':['integer','null']},'provenance_refs':refs})
schema={'$schema':'https://json-schema.org/draft/2020-12/schema','$id':'urn:ctw-adviser:evidence-packet:1.1.0','title':'CTW adviser evidence packet v1.1',
 **obj({'schema_version':const('1.1.0'),'mode':enum('combined','melee','missile'),'snapshot':ref('snapshot'),'units':arr(ref('unit'),1),
 'trait_descriptions':mapping(ref('description')),'sources':mapping(ref('source')),'provenance':mapping(ref('evidence')),'detail_refs':mapping(obj({'kind':S,'key':S})),
 'payload_graph':obj({'nodes':arr(ref('node')),'edges':arr(ref('edge'))})}),'$defs':defs}
if __name__=='__main__':
 (ROOT/'schema/evidence_packet.schema.json').write_text(json.dumps(schema,indent=2)+'\n')
