"""Rebuild explicitly selected design examples; not a production importer."""
import argparse
import copy
import csv
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
CASES=[('wargor','beastmen','wh2_dlc17_bst_cha_wargor_0'),('sea_guard','high_elves','wh2_main_hef_inf_lothern_sea_guard_0'),('sea_guard_shields','high_elves','wh2_main_hef_inf_lothern_sea_guard_1'),('blue_horrors','tzeentch','wh3_main_tze_inf_blue_horrors_0'),('kroxigor','lizardmen','wh2_main_lzd_mon_kroxigors'),('reiksguard','empire','wh_main_emp_cav_reiksguard'),('doom_diver','greenskins','wh_main_grn_art_doom_diver_catapult'),('bloodletters','khorne','wh3_main_kho_inf_bloodletters_0'),('queen_bess','vampire_coast','wh2_dlc11_cst_art_queen_bess')]
UNIT='data/unit_stats/';TABLE=UNIT+'abilities/tables/'
def dump(path,value):path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(value,indent=2)+'\n')

class Example:
 def __init__(self,root):
  self.root=root;self.cache={};self.assertions=[];self.packet={'schema_version':'1.0.0','mode':'combined','snapshot':{'commit':'3b5d13d94c5ed3eb4b9c6ce61cc75854b4426196','owners':{'units':{'patch':'9.0','build':'25507028','schema':4},'abilities':{'patch':'9.0.1','build':'25546563','schema':1}},'baseline':{'game':'warhammer_3','unit_scale':'ultra','rank':0,'context':'unmodified custom battle'}},'units':[],'trait_descriptions':{},'sources':{},'provenance':{},'detail_refs':{},'payload_graph':{'nodes':[],'edges':[]}}
 def records(self,path):
  if path not in self.cache:
   with (self.root/path).open(encoding='utf-8',newline='') as f:self.cache[path]=list(enumerate(csv.DictReader(f,delimiter='\t' if path.endswith('.tsv') else ','),2))
  return self.cache[path]
 def evidence(self,path,index,row,key):
  sid='s_'+hashlib.sha256(path.encode()).hexdigest()[:12];eid=sid+'_'+str(index)
  self.packet['sources'][sid]={'path':path,'sha256':hashlib.sha256((self.root/path).read_bytes()).hexdigest(),'owner':'abilities' if '/abilities/' in path else 'units'}
  self.packet['provenance'][eid]={'source_id':sid,'logical_record':index,'key':{k:row[k] for k in key},'source_line':int(row['source_line']) if row.get('source_line') else None,'source_patch':row.get('source_patch') or None}
  return eid
 def select(self,path,**keys):
  found=[(i,r) for i,r in self.records(path) if all(r[k]==v for k,v in keys.items())]
  if len(found)!=1:raise ValueError((path,keys,len(found)))
  i,r=found[0];return r,self.evidence(path,i,r,keys)
 def get(self,row,eid,column,pointer,conversion='number'):
  v=row[column]
  value=(None if v=='' else float(v)) if conversion=='number' else (None if v=='' else v=='true') if conversion=='boolean' else {'add':'add','mult':'multiply'}.get(v,'native') if conversion=='operation' else v
  self.assertions.append({'pointer':pointer,'evidence_ref':eid,'column':column,'conversion':conversion});return value
 def detail(self,kind,key):
  ref=kind+':'+key;self.packet['detail_refs'][ref]={'kind':kind,'key':key};return ref

def build(root,slug,race,key,approved):
 e=Example(root);p=UNIT+f'normalized/{race}__wh3__9.0__ultra.csv';r,ev=e.select(p,unit_key=key)
 base='/units/0';u={};e.packet['units']=[u]
 def get(col,path,typ='number'):return e.get(r,ev,col,base+path,typ)
 u['identity']={k:get(c,'/identity/'+k,'text') for k,c in [('unit_key','unit_key'),('subculture_key','subculture_key'),('name','unit_name'),('unit_type','tactical_category')]}
 u['body']={k:get(k,'/body/'+k) for k in ['entity_count','hp_per_entity','total_hp','barrier_health']};u['body']['size']=get('primary_target_size','/body/size','text');u['body']['components']=[]
 cp=UNIT+'lookups/unit_components__wh3__9.0__ultra.csv'
 for index,c in e.records(cp):
  if c['unit_key']!=key:continue
  cev=e.evidence(cp,index,c,['unit_key','component_role','relationship_key','battle_entity_key']);i=len(u['body']['components']);prefix=base+'/body/components/'+str(i)
  component={'id':'component:'+str(i),'role':c['component_role'],'count':None,'hp_per_component':None,'bonus_hp_per_component':None,'known_hp_total':None,'size':c['size_class'] or None,'targetable':None,'primary':None,'provenance_refs':[cev]}
  for out,src,typ in [('role','component_role','text'),('count','component_count','number'),('hp_per_component','base_hp_per_component','number'),('bonus_hp_per_component','bonus_hp_per_component','number'),('known_hp_total','known_hp_total','number'),('targetable','can_be_targeted','boolean'),('primary','is_primary_health_pool','boolean')]:component[out]=e.get(c,cev,src,prefix+'/'+out,typ)
  u['body']['components'].append(component)
 u['movement']={k:get(k,'/movement/'+k) for k in ['speed','mass']};u['leadership']=get('leadership','/leadership')
 mm={'attack':'melee_attack','defence':'melee_defence','base_damage':'weapon_base_damage','ap_damage':'weapon_ap_damage','attack_interval':'attack_interval','charge_bonus':'charge_bonus','max_splash_targets':'max_splash_targets'}
 u['melee']={'id':'melee:primary','weapon_key':r['source_melee_weapon_key'] or None,**{k:get(c,'/melee/'+k) for k,c in mm.items()},'provenance_refs':[ev],'variants':[]}
 has=r['has_missile_weapon']=='true'
 if has:
  projectile,pev=e.select(UNIT+'lookups/projectiles__wh3__9.0.csv',projectile_key=r['source_projectile_key'])
  rm={'range':'range','ammunition':'ammunition','reload_time':'reload_time','base_damage':'missile_base_damage','ap_damage':'missile_ap_damage','projectiles_per_shot':'projectiles_per_shot','shots_per_volley':'shots_per_volley','burst_size':'burst_size','burst_shot_delay':'burst_shot_delay','velocity':'projectile_velocity','accuracy':'accuracy','spread':'projectile_spread','marksmanship_bonus':'marksmanship_bonus','calibration_distance':'calibration_distance','calibration_area':'calibration_area'}
  a={'id':'ranged:primary','weapon_key':r['source_missile_weapon_key'],'projectile_key':r['source_projectile_key'],'component_ref':None,'slot':'primary','ammunition_pool':None,'is_default':True,**{k:get(c,'/ranged/'+k) for k,c in rm.items()},'minimum_range':e.get(projectile,pev,'minimum_range',base+'/ranged/minimum_range'),'explosion':None,'detail_ref':e.detail('projectile',r['source_projectile_key']),'provenance_refs':[ev,pev]}
  # Exact attachment scope and ammunition pool from the selected default link.
  wp=UNIT+'lookups/unit_weapon_links__wh3__9.0__ultra.csv'
  links=[(i,w) for i,w in e.records(wp) if w['unit_key']==key and w['projectile_key']==r['source_projectile_key'] and w['missile_weapon_key']==r['source_missile_weapon_key']]
  if len(links)!=1:raise ValueError('fixture default attachment ambiguous')
  i,w=links[0];wev=e.evidence(wp,i,w,['unit_key','component_role','slot','projectile_key']);a['provenance_refs'].append(wev)
  for field,typ in [('slot','text'),('ammunition_pool','text'),('is_default_projectile','boolean')]:a['is_default' if field=='is_default_projectile' else field]=e.get(w,wev,field,base+'/ranged/'+('is_default' if field=='is_default_projectile' else field),typ)
  matching=[c['id'] for c in u['body']['components'] if c['role']==w['component_role']]
  a['component_ref']=matching[0] if len(matching)==1 else None
  if r['explosion_key']:
   x,xev=e.select(UNIT+'lookups/explosions__wh3__9.0.csv',explosion_key=r['explosion_key'])
   a['explosion']={'id':'explosion:primary','key':r['explosion_key'],**{k:e.get(x,xev,k,base+'/ranged/explosion/'+k) for k in ['base_damage','ap_damage','radius']},'provenance_refs':[xev]}
  u['ranged']={'status':'present',**a,'variants':[]}
 else:u['ranged']=None
 protection=['armour','shield_block_chance','physical_resistance','missile_resistance','spell_resistance','fire_resistance','ward_save']
 u['passives']={'protection':{k:get(k,'/passives/protection/'+k) for k in protection},'attack_traits':{'melee':None,'ranged':None,'explosion':None,'additional':[]},'attributes':[],'abilities':[]}
 for kind,prefix,present in [('melee','melee',True),('ranged','missile',has),('explosion','explosion',has and bool(r['explosion_key']))]:
  if not present:continue
  loc='/passives/attack_traits/'+kind
  t={'scope':{'attack_ref':kind+':primary','component_ref':None},'bonus_vs_infantry':None,'bonus_vs_large':None,'magical':get(prefix+'_is_magical',loc+'/magical','boolean'),'flaming':get(prefix+'_is_flaming',loc+'/flaming','boolean'),'provenance_refs':[ev]}
  if kind!='explosion':
   for bonus in ['bonus_vs_infantry','bonus_vs_large']:t[bonus]=get(('missile_' if kind=='ranged' else '')+bonus,loc+'/'+bonus)
  u['passives']['attack_traits'][kind]=t
 u['cost']={k:get(c,'/cost/'+k) for k,c in [('multiplayer','multiplayer_cost'),('campaign_recruitment','campaign_recruit_cost'),('campaign_upkeep','campaign_upkeep')]}
 u['activated_options']=[];u['provenance_refs']=[ev]
 gaps=[{'code':'fixture_projection','section':s,'summary':text,'provenance_refs':[ev]} for s,text in [('weapons','Selected default attacks are shown; complete variant/payload closure is not demonstrated.'),('abilities','Only reviewed example passives are expanded; exhaustive passive classification and lifecycle reconstruction remain outstanding.'),('activated_options','Activated-option inventory is not demonstrated by this design projection.')]]
 if any(c['targetable'] is None for c in u['body']['components']):gaps.append({'code':'targetability_unknown','section':'components','summary':'Secondary-component targetability is not encoded by these joins.','provenance_refs':[ev]})
 ap=UNIT+'lookups/unit_attributes__wh3__9.0__ultra.csv';loc=UNIT+'source_exports/text/db/unit_attributes__.loc.tsv'
 for index,attribute in e.records(ap):
  if attribute['unit_key']!=key:continue
  akey=attribute['attribute_key'];aev=e.evidence(ap,index,attribute,['unit_key','attribute_key']);i=len(u['passives']['attributes'])
  source_name=[(j,x) for j,x in e.records(loc) if x['key']=='unit_attributes_onscreen_name_'+akey]
  source_text=[(j,x) for j,x in e.records(loc) if x['key']=='unit_attributes_bullet_text_'+akey]
  import re
  summary='Meaning unresolved in selected localization.';name=None;arefs=[aev]
  if source_name:
   j,x=source_name[0];name=x['text'];arefs.append(e.evidence(loc,j,x,['key']))
  if source_text:
   j,x=source_text[0];summary=re.sub(r'\[\[.*?\]\]','',x['text']).replace('\\\\n',' ').strip();arefs.append(e.evidence(loc,j,x,['key']))
  if '{{' in summary:gaps.append({'code':'unresolved_localization','section':'attributes','summary':akey+': localization contains unresolved substitutions.','provenance_refs':arefs})
  if not source_text:gaps.append({'code':'attribute_meaning_unknown','section':'attributes','summary':akey+': no selected mechanical localization.','provenance_refs':[aev]})
  u['passives']['attributes'].append({'key':e.get(attribute,aev,'attribute_key',base+f'/passives/attributes/{i}/key','text'),'name':name,'summary':summary,'provenance_refs':arefs})
 if slug=='wargor':
  ability='wh2_dlc17_hero_passive_will_of_the_dark_gods';mp=base+'/passives/abilities/0'
  definition,dev=e.select(TABLE+'ability_definitions.csv',key=ability);casting,cev=e.select(TABLE+'ability_casting.csv',key=ability)
  if casting['passive']!='true':raise ValueError('qualification fixture is not passive')
  link,lev=e.select(UNIT+'lookups/unit_abilities__wh3__9.0__ultra.csv',unit_key=key,ability_key=ability,culture_key='*')
  from validate_packets import QUALIFIED_PASSIVE_SUMMARY
  u['passives']['abilities'].append({'key':ability,'name':None,'culture_key':e.get(link,lev,'culture_key',mp+'/culture_key','text'),'requires_effect_enabling':e.get(definition,dev,'requires_effect_enabling',mp+'/requires_effect_enabling','boolean'),'classification_evidence':[dev,cev],'summary':QUALIFIED_PASSIVE_SUMMARY,'native_parameters':{},'conditions':{'activates_when':[],'deactivates_when':[],'recipient_requirements':[],'unresolved':[]},'phases':[],'effects':[{'kind':'unresolved','phase_ref':None,'native_kind':'passive_definition','native_parameters':{},'reason':'Effect expansion is outside this qualification fixture.','provenance_refs':[dev,cev]}],'provenance_refs':[dev,cev,lev],'detail_ref':e.detail('passive',ability)})
  gaps.append({'code':'qualification_projection','section':'abilities','summary':'Passive classification and enabling requirement are shown; effects and activation conditions remain unresolved in this fixture.','provenance_refs':[dev,cev,lev]})
 design=approved.get(r['unit_name'])
 if design:
  for original in design['passives']['abilities']:
   m=copy.deepcopy(original);mi=len(u['passives']['abilities']);mp=base+f'/passives/abilities/{mi}'
   definition,dev=e.select(TABLE+'ability_definitions.csv',key=m['key']);casting,cev=e.select(TABLE+'ability_casting.csv',key=m['key'])
   if casting['passive']!='true':raise ValueError('approved passive not supported by casting definition')
   m['requires_effect_enabling']=e.get(definition,dev,'requires_effect_enabling',mp+'/requires_effect_enabling','boolean')
   m['classification_evidence']=[dev,cev]
   m['native_parameters']={field:e.get(casting,cev,field,mp+'/native_parameters/'+field) for field in ['effect_range','target_intercept_range','active_time','recharge_time','num_uses']}
   link,linkev=e.select(UNIT+'lookups/unit_abilities__wh3__9.0__ultra.csv',unit_key=key,ability_key=m['key'],culture_key=m['culture_key'])
   m['culture_key']=e.get(link,linkev,'culture_key',mp+'/culture_key','text')
   m.pop('phase_duration',None);m['conditions']={'activates_when':[],'deactivates_when':[],'recipient_requirements':[],'unresolved':[]};m['phases']=[];m['provenance_refs']=[dev,cev,linkev];m['detail_ref']=e.detail('passive',m['key'])
   phase_path=TABLE+'ability_phase_links.csv'
   for j,x in e.records(phase_path):
    if x['special_ability']!=m['key']:continue
    lev=e.evidence(phase_path,j,x,['order','special_ability','target_self','target_friends','target_enemies']);phase,ph_ev=e.select(TABLE+'ability_phases.csv',id=x['phase']);pi=len(m['phases']);pp=mp+f'/phases/{pi}'
    ph={'key':x['phase'],'order':int(x['order']),'duration':e.get(phase,ph_ev,'duration',pp+'/duration'),'lifecycle':{},'provenance_refs':[lev,ph_ev]}
    for field in ['target_self','target_friends','target_enemies']:ph[field]=e.get(x,lev,field,pp+'/'+field,'boolean')
    m['phases'].append(ph)
   cp=TABLE+'special_ability_to_auto_deactivate_flags.csv'
   for j,x in e.records(cp):
    if x['special_ability']!=m['key']:continue
    cev2=e.evidence(cp,j,x,['special_ability','deactivate_flag']);ci=len(m['conditions']['deactivates_when'])
    condition=e.get(x,cev2,'deactivate_flag',mp+f'/conditions/deactivates_when/{ci}/key','text')
    m['conditions']['deactivates_when'].append({'key':condition,'summary':'Source deactivation condition: '+condition+'. Activation and equality behavior are not established.','provenance_refs':[cev2]})
   for ei,effect in enumerate(m['effects']):
    ep=mp+f'/effects/{ei}';effect['phase_ref']=m['phases'][0]['key']
    if effect['kind']=='stat_modifier':
     stat={'speed':'scalar_speed','physical_resistance':'stat_resistance_physical','charge_bonus':'stat_charge_bonus','melee_ap_damage':'stat_melee_damage_ap','melee_base_damage':'stat_melee_damage_base'}.get(effect['stat'],'stat_'+effect['stat'])
     matches=[(j,x) for j,x in e.records(TABLE+'phase_stat_effects.csv') if x['phase'] in [p['key'] for p in m['phases']] and x['stat']==stat]
     if len(matches)!=1:raise ValueError((m['key'],stat,matches))
     j,x=matches[0];eev=e.evidence(TABLE+'phase_stat_effects.csv',j,x,['phase','stat']);effect['phase_ref']=x['phase'];source_value=e.get(x,eev,'value',ep+'/value');assert source_value==effect['value'], 'approved summary/effect value drift';effect['value']=source_value;effect['native_operation']=e.get(x,eev,'how',ep+'/native_operation','text');effect['operation']=e.get(x,eev,'how',ep+'/operation','operation');effect['provenance_refs']=[eev]
    else:
     phase,eev=e.select(TABLE+'ability_phases.csv',id=effect['phase_ref']);effect['provenance_refs']=[eev]
     for field in effect['native_parameters']:effect['native_parameters'][field]=e.get(phase,eev,field,ep+'/native_parameters/'+field)
   u['passives']['abilities'].append(m)
  for gap in design['coverage']['gaps']:gaps.append({'code':'reviewed_source_gap','section':'abilities','summary':gap,'provenance_refs':[ev]})
 # Descriptions are concise authored scope explanations; numerical semantics stay downstream.
 descriptions={'magical':'Magical attacks bypass physical resistance; the tag applies only to the referenced attack.','flaming':'Flaming attacks interact with fire vulnerability and halve healing while the target is on fire.','bonus_vs_infantry':'Numeric bonus against infantry-sized targets; distinct from the qualitative Anti-Infantry bullet.','bonus_vs_large':'Numeric bonus against large targets; distinct from the qualitative Anti-Large bullet.'}
 for tag,summary in descriptions.items():
  if any(t and t[tag] not in (False,0,None) for k,t in u['passives']['attack_traits'].items() if k!='additional'):
   loc_path=UNIT+'source_exports/text/db/'+('ui_unit_bullet_point_enums__.loc.tsv' if tag in ('magical','flaming') else 'unit_stat_localisations__.loc.tsv')
   loc_key={'magical':'ui_unit_bullet_point_enums_tooltip_ward_physical','flaming':'ui_unit_bullet_point_enums_tooltip_flaming_attacks','bonus_vs_infantry':'unit_stat_localisations_tooltip_text_stat_bonus_vs_infantry','bonus_vs_large':'unit_stat_localisations_tooltip_text_stat_bonus_vs_large'}[tag]
   _,tev=e.select(loc_path,key=loc_key)
   e.packet['trait_descriptions'][tag]={'summary':summary,'provenance_refs':[ev,tev]}
 counts={'components':len(u['body']['components']),'weapons':1+int(has),'attributes':len(u['passives']['attributes']),'abilities':len(u['passives']['abilities']),'activated_options':0}
 u['coverage']={'melee':'present','ranged':'present' if has else 'known_none','sections':[{'name':s,'state':'complete' if s in ('components','attributes') else 'unresolved','returned':n,'total':n if s in ('components','attributes') else None,'cursor':None} for s,n in counts.items()],'gaps':gaps}
 return e.packet,e.assertions

def main():
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--ctw-root',type=Path,required=True);args=parser.parse_args()
 from verify_sources import verify
 lock=json.loads((ROOT/'source_lock.json').read_text());contract=json.loads((ROOT/'schema/import_contract.json').read_text())
 if lock['source_commit']!='3b5d13d94c5ed3eb4b9c6ce61cc75854b4426196':raise ValueError('fixture definitions require explicit review for a new source pin')
 checked=verify(args.ctw_root,lock,contract)
 if checked['status']!='passed':raise ValueError(checked['errors'])
 approved=json.loads((ROOT/'fixtures/design/approved-examples.json').read_text());entries=[];built={}
 for slug,race,key in CASES:
  packet,assertions=build(args.ctw_root,slug,race,key,approved)
  built[slug]=(packet,assertions)
  path=f'fixtures/source_backed/{slug}.json';ap=f'fixtures/source_backed/{slug}.assertions.json';dump(ROOT/path,packet);dump(ROOT/ap,assertions)
  entries.append({'path':path,'kind':'source_backed','assertions':ap,'purpose':'Selected source projection; coverage gaps remain explicit.'})
 for a,b in [('reiksguard','doom_diver'),('sea_guard','blue_horrors'),('bloodletters','kroxigor')]:
  packet,assertions=copy.deepcopy(built[a]);second,second_assertions=copy.deepcopy(built[b]);packet['units']+=second['units']
  for field in ['sources','provenance','detail_refs','trait_descriptions']:packet[field].update(second[field])
  for assertion in second_assertions:assertion['pointer']=assertion['pointer'].replace('/units/0/','/units/1/');assertions.append(assertion)
  path=f'fixtures/source_backed/{a}_vs_{b}.json';ap=f'fixtures/source_backed/{a}_vs_{b}.assertions.json';dump(ROOT/path,packet);dump(ROOT/ap,assertions);entries.append({'path':path,'kind':'source_backed','assertions':ap,'purpose':'Named pair uses the same packet schema and unchanged source profiles.'})
 dump(ROOT/'fixtures/manifest.json',{'schema_version':'1.0.0','fixtures':entries})
if __name__=='__main__':main()
