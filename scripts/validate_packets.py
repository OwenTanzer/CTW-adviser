"""Validate the closed v1 schema subset, packet references, and fixture assertions.

This is intentionally not a general JSON Schema engine. Unsupported keywords
fail schema checking; supported keywords are those used by our checked-in schema.
"""
import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
import re

ROOT=Path(__file__).resolve().parents[1]
ANNOTATIONS={'$schema','$id','title','description','$defs'}
KEYWORDS={'$ref','type','properties','required','additionalProperties','items','minItems','minimum','minLength','pattern','enum','const','oneOf','anyOf'}

def check_schema(s):
    if not isinstance(s,dict):raise ValueError('only object schemas supported')
    unsupported=set(s)-KEYWORDS-ANNOTATIONS
    if unsupported:raise ValueError('unsupported schema keywords: '+str(unsupported))
    for key in ('properties','$defs'):
        for child in s.get(key,{}).values():check_schema(child)
    for key in ('oneOf','anyOf'):
        for child in s.get(key,[]):check_schema(child)
    for key in ('items','additionalProperties'):
        if isinstance(s.get(key),dict):check_schema(s[key])

def validate(value,s,root,path='$'):
    if '$ref' in s:
        prefix='#/$defs/'
        if not s['$ref'].startswith(prefix):raise ValueError('external schema references unsupported')
        return validate(value,root['$defs'][s['$ref'][len(prefix):]],root,path)
    for keyword in ('oneOf','anyOf'):
        if keyword in s:
            matched=0
            for branch in s[keyword]:
                try:validate(value,branch,root,path);matched+=1
                except ValueError:pass
            if (keyword=='oneOf' and matched!=1) or (keyword=='anyOf' and matched==0):raise ValueError(path+': '+keyword+' failed')
    typ='null' if value is None else 'boolean' if isinstance(value,bool) else 'integer' if isinstance(value,int) else 'number' if isinstance(value,float) else 'string' if isinstance(value,str) else 'array' if isinstance(value,list) else 'object' if isinstance(value,dict) else 'invalid'
    if isinstance(value,float) and not math.isfinite(value):raise ValueError(path+': nonfinite number')
    if 'type' in s:
        types=s['type'] if isinstance(s['type'],list) else [s['type']]
        if typ not in types and not (typ=='integer' and 'number' in types):raise ValueError(path+': wrong type')
    if 'const' in s and (value!=s['const'] or isinstance(value,bool)!=isinstance(s['const'],bool)):raise ValueError(path+': wrong constant')
    if 'enum' in s and value not in s['enum']:raise ValueError(path+': unknown enum')
    if typ=='object':
        missing=set(s.get('required',[]))-set(value)
        if missing:raise ValueError(path+': missing '+str(sorted(missing)))
        for k,v in value.items():
            child=s.get('properties',{}).get(k,s.get('additionalProperties',True))
            if child is False:raise ValueError(path+': unexpected '+k)
            if isinstance(child,dict):validate(v,child,root,path+'/'+k)
    if typ=='array':
        if len(value)<s.get('minItems',0):raise ValueError(path+': too few items')
        for i,v in enumerate(value):
            if 'items' in s:validate(v,s['items'],root,path+'/'+str(i))
    if typ=='string':
        if len(value)<s.get('minLength',0):raise ValueError(path+': empty string')
        if 'pattern' in s and re.search(s['pattern'],value) is None:raise ValueError(path+': pattern mismatch')
    if typ in ('integer','number') and 'minimum' in s and value<s['minimum']:raise ValueError(path+': below minimum')

def packet_checks(p):
    evidence=p['provenance'];details=p['detail_refs']
    for e in evidence.values():
        if e['source_id'] not in p['sources']:raise ValueError('dangling source')
        if any(r not in evidence for r in e.get('lineage_refs',[])):raise ValueError('dangling lineage')
    for s in p['sources'].values():
        if s['owner'] not in p['snapshot']['owners']:raise ValueError('dangling owner')
    def walk(x):
        if isinstance(x,dict):
            for k,v in x.items():
                if k in ('provenance_refs','classification_evidence'):
                    if any(r not in evidence for r in v):raise ValueError('dangling evidence')
                if k=='detail_ref' and v not in details:raise ValueError('dangling detail reference')
                walk(v)
        elif isinstance(x,list):
            for v in x:walk(v)
    walk(p)
    seen_units=set()
    for u in p['units']:
        identity=(u['identity']['subculture_key'],u['identity']['unit_key'])
        if identity in seen_units:raise ValueError('duplicate qualified unit')
        seen_units.add(identity)
        names=u['identity']['faction_name']
        if names!=sorted(set(names)):raise ValueError('faction_name must be sorted and unique')
        ranged=u['ranged'];status=u['coverage']['ranged']
        melee_status=u['coverage']['melee']
        gaps=u['coverage'].get('gaps')
        if gaps is None and (p['schema_version'] not in ('1.3.0','1.4.0','1.5.0') or 'diagnostic_count' not in u['coverage']):raise ValueError('missing diagnostic coverage')
        if gaps is not None and 'diagnostic_count' in u['coverage'] and u['coverage']['diagnostic_count']!=len(gaps):raise ValueError('diagnostic count mismatch')
        if (u['melee'] is None)==(melee_status=='present'):raise ValueError('melee absence/status contradiction')
        if gaps is not None and melee_status in ('unresolved','omitted') and not any(g['section']=='melee' for g in gaps):raise ValueError('missing melee gap')
        if (ranged is None and status!='known_none') or (ranged is not None and ranged['status']!=status):raise ValueError('ranged absence/status contradiction')
        sections=u['coverage']['sections'];names=[s['name'] for s in sections]
        if sorted(names)!=sorted(['components','weapons','attributes','abilities','activated_options']):raise ValueError('section coverage must be unique and exhaustive')
        for s in sections:
            if s['total'] is not None and s['returned']>s['total']:raise ValueError('invalid coverage counts')
            offset=s.get('offset',0)
            if s['state']=='complete' and (s['total']!=s['returned']+offset or s['cursor'] is not None):raise ValueError('false complete section')
            if s['state']=='partial' and (s['cursor'] is None or (s['total'] is not None and s['total']<=s['returned']+offset)):raise ValueError('partial section needs overflow/cursor')
            if gaps is not None and s['state'] in ('unresolved','omitted') and not any(g['section']==s['name'] for g in gaps):raise ValueError('unqualified unresolved/omitted section')
        if gaps is not None and status in ('unresolved','omitted') and not any(g['section']=='ranged' for g in gaps):raise ValueError('missing ranged gap')
        attacks={};components={c['id'] for c in u['body']['components']}
        if len(components)!=len(u['body']['components']):raise ValueError('duplicate component id')
        def add(a,kind,component=None):
            if a['id'] in attacks:raise ValueError('duplicate attack id')
            attacks[a['id']]={'kind':kind,'component':component}
        if u['melee']:
            add(u['melee'],'melee',u['melee'].get('component_ref'))
            for a in u['melee']['variants']:add(a,'melee',a.get('component_ref'))
        if ranged and status=='present':
            for a in [ranged,*ranged['variants']]:
                add(a,'ranged',a['component_ref'])
                if a['component_ref'] is not None and a['component_ref'] not in components:raise ValueError('unknown component')
                if a['explosion']:add(a['explosion'],'explosion',a['component_ref'])
        traits=u['passives']['attack_traits'];scoped=[]
        for kind in ('melee','ranged','explosion'):
            if traits[kind] is not None:scoped.append((kind,traits[kind]))
        scoped.extend((t['kind'],t['traits']) for t in traits['additional'])
        seen=set()
        for kind,t in scoped:
            target=t['scope']['attack_ref']
            if attacks.get(target,{}).get('kind')!=kind or target in seen:raise ValueError('wrong/duplicate attack trait scope')
            if t['scope']['component_ref'] is not None and t['scope']['component_ref'] not in components:raise ValueError('unknown trait component')
            component=t['scope']['component_ref']
            if component is not None and attacks[target]['component'] is not None and component!=attacks[target]['component']:raise ValueError('trait component conflicts with attack attachment')
            seen.add(target)
            for tag in ('magical','flaming','bonus_vs_infantry','bonus_vs_large'):
                if t[tag] not in (False,0,None) and tag not in p['trait_descriptions']:raise ValueError('missing trait explanation')
        if set(attacks)!=seen:raise ValueError('attack lacks scoped traits')
        for m in u['passives']['abilities']:
            phases={x['key'] for x in m['phases']}
            for e in m['effects']:
                if e['phase_ref'] is not None and e['phase_ref'] not in phases:raise ValueError('unknown effect phase')
                if e['kind']=='stat_modifier' and e['operation']!='native' and e['native_operation']!={'add':'add','multiply':'mult'}[e['operation']]:raise ValueError('operation mapping mismatch')
        actual={'components':len(u['body']['components']),'weapons':sum(v['kind']!='explosion' for v in attacks.values()),'attributes':len(u['passives']['attributes']),'abilities':len(u['passives']['abilities']),'activated_options':len(u['activated_options'])}
        if any(s['returned']!=actual[s['name']] for s in sections):raise ValueError('returned count differs from packet')
    graph=p['payload_graph'];nodes={n['id'] for n in graph['nodes']}
    if len(nodes)!=len(graph['nodes']):raise ValueError('duplicate graph node')
    if any(e['from'] not in nodes or e['to'] not in nodes for e in graph['edges']):raise ValueError('dangling graph edge')
    for u in p['units']:
        for m in u['passives']['abilities']:
            for effect in m['effects']:
                if effect['kind']=='payload_reference' and effect['node_ref'] not in nodes and effect['node_ref'] not in details:raise ValueError('dangling payload reference')

def pointer(p,path):
    for part in path.strip('/').split('/'):
        part=part.replace('~1','/').replace('~0','~');p=p[int(part)] if isinstance(p,list) else p[part]
    return p

QUALIFIED_PASSIVE_SUMMARY='Source classifies this linked mechanic as passive and requires effect enabling; access and effect behavior are not established by this fixture.'

def reviewed_summary_checks(packet):
    # Fixture-only reviewed text gate, not a general prose interpretation engine.
    approved=json.loads((ROOT/'fixtures/design/approved-examples.json').read_text())
    summaries={(m['key'],m['culture_key']):m['summary'] for u in approved.values() for m in u['passives']['abilities']}
    summaries[('wh2_dlc17_hero_passive_will_of_the_dark_gods','*')]=QUALIFIED_PASSIVE_SUMMARY
    for u in packet['units']:
        for m in u['passives']['abilities']:
            if summaries.get((m['key'],m['culture_key']))!=m['summary']:raise ValueError('passive summary differs from reviewed fixture text')

def source_assertions(packet,assertions,source_root):
    reviewed_summary_checks(packet)
    cache={}
    for s in packet['sources'].values():
        path=(source_root/s['path']).resolve()
        if not path.is_relative_to(source_root.resolve()):raise ValueError('source path escape')
        b=path.read_bytes();lf=b.replace(b'\r\n',b'\n')
        if not any(hashlib.sha256(x).hexdigest()==s['sha256'] for x in [b,lf,lf.replace(b'\n',b'\r\n')]):raise ValueError('source hash mismatch')
    # Check every evidence locator, including prose/classification references,
    # not just references used by numeric assertions.
    for e in packet['provenance'].values():
        src=packet['sources'][e['source_id']]['path']
        if src not in cache:
            with (source_root/src).open(encoding='utf-8',newline='') as f:cache[src]=list(csv.DictReader(f,delimiter='\t' if src.endswith('.tsv') else ','))
        row=cache[src][e['logical_record']-2]
        if any(row[k]!=v for k,v in e['key'].items()):raise ValueError('evidence locator mismatch')
        if e['source_line'] is not None and str(e['source_line'])!=row.get('source_line'):raise ValueError('native source line mismatch')
        if e['source_patch'] is not None and e['source_patch']!=row.get('source_patch'):raise ValueError('native patch mismatch')
    for a in assertions:
        e=packet['provenance'][a['evidence_ref']];src=packet['sources'][e['source_id']]['path']
        if src not in cache:
            with (source_root/src).open(encoding='utf-8',newline='') as f:cache[src]=list(csv.DictReader(f,delimiter='\t' if src.endswith('.tsv') else ','))
        row=cache[src][e['logical_record']-2]
        if any(row[k]!=v for k,v in e['key'].items()):raise ValueError('evidence locator mismatch')
        value=row[a['column']];conversion=a['conversion']
        if conversion=='number':value=None if value=='' else float(value)
        elif conversion=='boolean':
            if value not in ('','true','false'):raise ValueError('invalid source boolean')
            value=None if value=='' else value=='true'
        elif conversion=='operation':value={'add':'add','mult':'multiply'}.get(value,'native')
        elif conversion!='text':raise ValueError('unknown assertion conversion')
        if pointer(packet,a['pointer'])!=value:raise ValueError('source mismatch: '+a['pointer'])

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--ctw-root',type=Path,required=True);parser.add_argument('--generated-examples',action='store_true',help='also validate reproducible, ignored unit and pair packets');a=parser.parse_args()
    schema=json.loads((ROOT/'schema/evidence_packet.schema.json').read_text());check_schema(schema)
    from verify_sources import verify
    lock=json.loads((ROOT/'source_lock.json').read_text());contract=json.loads((ROOT/'schema/import_contract.json').read_text())
    checked=verify(a.ctw_root,lock,contract)
    if checked['status']!='passed':raise ValueError(checked['errors'])
    locked_paths={f['path'] for f in lock['files']}
    index=json.loads((ROOT/'fixtures/manifest.json').read_text())
    if a.generated_examples:index['fixtures']+=json.loads((ROOT/'work/generated_examples/manifest.json').read_text())['fixtures']
    for f in index['fixtures']:
        packet=json.loads((ROOT/f['path']).read_text());validate(packet,schema,schema);packet_checks(packet)
        if f['kind']=='source_backed':
            if packet['snapshot']['commit']!=lock['source_commit']:raise ValueError('fixture source commit differs from lock')
            if any(s['path'] not in locked_paths for s in packet['sources'].values()):raise ValueError('fixture uses unpinned source')
            expected_owners={'units':{'patch':lock['owners']['units']['patch'],'build':lock['owners']['units']['build'],'schema':lock['owners']['units']['schema']},'abilities':{'patch':lock['owners']['shared_abilities']['extraction_patch'],'build':lock['owners']['shared_abilities']['build'],'schema':lock['owners']['shared_abilities']['schema']}}
            if packet['snapshot']['owners']!=expected_owners:raise ValueError('fixture owner scope differs from lock')
            source_assertions(packet,json.loads((ROOT/f['assertions']).read_text()),a.ctw_root)
    print(json.dumps({'status':'passed','fixtures':len(index['fixtures']),'source_backed':sum(f['kind']=='source_backed' for f in index['fixtures'])}))
if __name__=='__main__':main()
