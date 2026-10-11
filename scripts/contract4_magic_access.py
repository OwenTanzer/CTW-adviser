"""Reviewed contract-4 migration for issue #19: lock CTW-data magic access outputs.

Run once from the adviser repository against a CTW-data checkout at the locked
commit. It never edits CTW-data. Each added file is hashed, compared with its
Git blob at the pinned commit and with CTW-data's own data/magic output
manifest; any mismatch aborts instead of refreshing an expected value.
"""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
MAGIC = 'data/magic/'
GROUP_MEMBERS = 'data/unit_stats/abilities/tables/ability_group_members.csv'
PIPELINE = 'scripts/magic_pipeline.py'


def column(name, kind, nullable, evidence):
    return {'name': name, 'type': kind, 'nullable': nullable, 'evidence': evidence}


BINDING_COLUMNS = [column(name, kind, name == 'ability_key', PIPELINE + '#character binding cols')
                   for name, kind in (
    ('agent_subtype_key', 'TEXT'), ('node_set_key', 'TEXT'), ('node_key', 'TEXT'), ('skill_key', 'TEXT'),
    ('skill_level', 'INTEGER'), ('effect_key', 'TEXT'), ('skill_source_path', 'TEXT'),
    ('skill_source_line', 'INTEGER'), ('ability_key', 'TEXT'), ('binding_table', 'TEXT'),
    ('binding_source_path', 'TEXT'), ('binding_source_line', 'INTEGER'), ('bonus_value_id', 'TEXT'),
    ('target_kind', 'TEXT'), ('target_key', 'TEXT'))]
INDEX_COLUMNS = [column(name, kind, name == 'path', PIPELINE + '#character index')
                 for name, kind in (
    ('agent_subtype_key', 'TEXT'), ('character_name', 'TEXT'), ('character_class', 'TEXT'),
    ('is_caster', 'BOOLEAN'), ('path', 'TEXT'), ('skill_source_path', 'TEXT'),
    ('relation_count', 'INTEGER'), ('direct_ability_count', 'INTEGER'))]
MEMBER_EVIDENCE = 'data/unit_stats/abilities/schema_inventory.json#special_ability_groups_to_unit_abilities_junctions_tables/definition/fields/'
MEMBER_COLUMNS = [
    {**column('special_ability_groups', 'TEXT', False, MEMBER_EVIDENCE + 'special_ability_groups'),
     'native_type': 'StringU8', 'native_reference': 'special_ability_groups.ability_group'},
    {**column('unit_special_abilities', 'TEXT', False, MEMBER_EVIDENCE + 'unit_special_abilities'),
     'native_type': 'StringU8', 'native_reference': 'unit_special_abilities.key'},
    {'name': 'source_path', 'type': 'TEXT', 'nullable': False},
    {'name': 'source_line', 'type': 'INTEGER', 'nullable': False},
    {'name': 'source_patch', 'type': 'TEXT', 'nullable': False},
]


def rows(path):
    with path.open(encoding='utf-8', newline='') as stream:
        return list(csv.DictReader(stream))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ctw-root', type=Path, required=True)
    args = parser.parse_args()
    root = args.ctw_root.resolve()
    lock_path, contract_path = ROOT / 'source_lock.json', ROOT / 'schema/import_contract.json'
    lock = json.loads(lock_path.read_text(encoding='utf-8'))
    contract = json.loads(contract_path.read_text(encoding='utf-8'))
    if contract['contract_version'] != 3:
        raise SystemExit('expected contract 3 as the migration base')
    head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip()
    if head != lock['source_commit']:
        raise SystemExit(f'CTW-data checkout {head} is not the locked commit')
    manifest = json.loads((root / MAGIC / 'output_manifest.json').read_text(encoding='utf-8'))
    index = rows(root / MAGIC / 'character_index.csv')
    paths = [MAGIC + 'character_index.csv', GROUP_MEMBERS]
    paths += sorted(MAGIC + r['path'] for r in index if r['path'])
    paths += sorted(MAGIC + 'access/' + r['agent_subtype_key'] + '.json' for r in index)
    if len(set(paths)) != len(paths):
        raise SystemExit('duplicate magic path')
    existing = {e['path'] for e in lock['files']}
    blobs = dict(line.split('\t', 1)[::-1] for line in subprocess.check_output(
        ['git', 'ls-tree', '-r', '--format=%(objectname)\t%(path)', lock['source_commit'], '--', 'data/magic',
         GROUP_MEMBERS], cwd=root, text=True).splitlines())
    added = []
    for path in paths:
        if path in existing:
            raise SystemExit('already locked: ' + path)
        data = (root / path).read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        blob = subprocess.run(['git', 'hash-object', '--stdin'], input=data, capture_output=True,
                              cwd=root, check=True).stdout.decode().strip()
        if blobs.get(path) != blob:
            raise SystemExit('git blob mismatch: ' + path)
        entry = {'path': path, 'bytes': len(data), 'sha256': digest, 'git_blob_sha': blob}
        if path.startswith(MAGIC):
            if manifest.get(path) != digest:
                raise SystemExit('magic output manifest mismatch: ' + path)
            entry['upstream_fingerprints'] = [{'authority': MAGIC + 'output_manifest.json',
                                               'bytes': len(data), 'sha256': digest}]
        added.append(entry)
    lock['files'] = lock['files'] + added  # existing order preserved; additions appended
    lock['owners']['magic'] = {'schema': 1, 'base_patch': '9.0', 'extraction_patch': '9.0.1',
                               'build': '25546563', 'coverage': 'partial', 'issue': 14}

    contract['contract_version'] = 4
    contract['column_schemas']['magic_skill_bindings'] = BINDING_COLUMNS
    contract['column_schemas']['magic_character_index'] = INDEX_COLUMNS
    contract['datasets'].append({'path': MAGIC + 'character_index.csv', 'role': 'magic_character_index',
                                 'keys': ['agent_subtype_key'], 'expected_rows': len(index),
                                 'columns_ref': 'magic_character_index',
                                 'row_selection': 'All indexed characters, including those with no skill binding.'})
    contract['datasets'].append({'path': GROUP_MEMBERS, 'role': 'effect_group_membership',
                                 'keys': ['special_ability_groups', 'unit_special_abilities'],
                                 'expected_rows': len(rows(root / GROUP_MEMBERS)), 'columns': MEMBER_COLUMNS,
                                 'row_selection': 'Complete exact lore/group membership; membership never grants a spell.'})
    for r in index:
        if r['path']:
            contract['datasets'].append({'path': MAGIC + r['path'], 'role': 'magic_skill_bindings',
                                         'keys': ['skill_source_line', 'binding_table', 'binding_source_line'],
                                         'expected_rows': len(rows(root / MAGIC / r['path'])),
                                         'columns_ref': 'magic_skill_bindings',
                                         'row_selection': 'All derived skill-effect bindings for this character.'})
    contract['metadata_gates'] += [
        {'path': MAGIC + 'dataset_manifest.json', 'keys': ['schema_version'], 'equals': 1},
        {'path': MAGIC + 'dataset_manifest.json', 'keys': ['extraction_build'], 'equals': '25546563'},
        {'path': MAGIC + 'coverage.json', 'keys': ['characters'], 'equals': len(index)},
    ]
    contract['classification']['character_access'] = (
        'Character skill bindings are conditional possibilities tied to exact skill/rank records. enable on an '
        'ability binding enables that ability once the skill rank is taken; other bonus values modify it. '
        'Group, phase, unit-set, army, pre-battle and context bindings never grant individual spells. '
        'Character-to-unit forms come only from the indexed access files; unmapped forms stay explicit.')
    contract['coverage_boundary']['activated_effects'] = (
        'Structural closure from activated roots through the existing joins; runtime arithmetic, '
        'scheduling, targeting priority and stacking remain unverified.')
    contract['coverage_boundary']['character_access'] = (
        'Indexed skill bindings and unit forms only; items, traits, mounts unlocks, scripted forms and campaign '
        'legality remain unresolved. No build solver; ranks are never summed.')
    contract['coverage_boundary']['next_step'] = 'Issue #20: calculate spell and activated-ability effects on units.'
    contract_path.write_bytes((json.dumps(contract, indent=2, ensure_ascii=False) + '\n').encode())
    digest = hashlib.sha256(json.dumps(contract, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    old = lock['contract_sha256']
    lock['contract_sha256'] = digest
    lock_path.write_bytes((json.dumps(lock, indent=2, ensure_ascii=False) + '\n').encode())
    store = ROOT / 'src/ctw_adviser/store.py'
    text = store.read_text(encoding='utf-8')
    if text.count(old) != 1:
        raise SystemExit('store contract constant not found')
    store.write_bytes(text.replace(old, digest).encode())
    print(json.dumps({'added_files': len(added), 'contract_sha256': digest,
                      'binding_files': sum(1 for r in index if r['path']), 'characters': len(index)}))


if __name__ == '__main__':
    main()
