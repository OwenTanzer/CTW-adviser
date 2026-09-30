"""Build an indexed SQLite snapshot from verified, pinned CTW-data inputs."""
from __future__ import annotations

from collections import defaultdict, deque
import csv
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import time

from .store import convert, create_native_table, quote

ROOT = Path(__file__).resolve().parents[2]
# The existing verifier remains the owner of the locked byte/type/owner gates.
import sys
sys.path.insert(0, str(ROOT / 'scripts'))
from verify_sources import verify, safe_path

UNIT = 'data/unit_stats/'
TABLE = UNIT + 'abilities/tables/'
LOOKUP = UNIT + 'lookups/'
DEFINITION = TABLE + 'ability_definitions.csv'
CASTING = TABLE + 'ability_casting.csv'
PHASE = TABLE + 'ability_phases.csv'
ABILITY_LINK = LOOKUP + 'unit_abilities__wh3__9.0__ultra.csv'


def compact(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False)


def record_id(path, logical_record):
    return hashlib.sha256(path.encode()).hexdigest()[:20] + ':' + str(logical_record)


def load_records(root, spec):
    with safe_path(root, spec['path']).open(encoding='utf-8', newline='') as stream:
        reader = csv.DictReader(stream, delimiter=spec.get('delimiter', ','))
        return {record_id(spec['path'], i): (i, row)
                for i, row in enumerate(reader, 2)
                if not (spec.get('rpfm_metadata') and
                        next(iter(row.values()), '').startswith('#'))}


def classification(definition, casting):
    if definition is None or casting is None or casting.get('passive') not in ('true', 'false'):
        return 'unresolved'
    return 'core_passive' if casting['passive'] == 'true' else 'activated_option'


def dependency_edges(contract):
    edges = [dict(e, reverse=False) for e in contract['joins']]
    # Inbound rows attach conditions/effects to an owner. Reverse only these
    # specific owner edges; arbitrary reverse joins would pull unrelated spells.
    attachments = {
        'ability_phase_links.csv': 'special_ability',
        'phase_stat_effects.csv': 'phase',
        'phase_attribute_effects.csv': 'phase',
        'special_ability_to_auto_deactivate_flags.csv': 'special_ability',
        'special_ability_to_invalid_target_flags.csv': 'special_ability',
        'special_ability_to_invalid_usage_flags.csv': 'special_ability',
        'special_ability_to_recharge_contexts.csv': 'special_ability',
        'special_ability_intensity_settings.csv': 'ability',
        'special_ability_behaviour_groups_to_types.csv': 'group',
        'unit_ability_superseded_abilities_set_elements.csv': 'set_key',
        'special_ability_contact_phase_groups.csv': 'contact_phase_id',
        'unit_stat_modifiers.csv': 'stat',
    }
    for e in edges:
        if attachments.get(Path(e['source']).name) == e['source_columns'][0]:
            e['reverse'] = True

    def add(source, field, target, target_field, reverse=False, **policies):
        edges.append({'name': source + '.' + field, 'source': source,
                      'source_columns': [field], 'target': target,
                      'target_columns': [target_field], 'reverse': reverse,
                      'unresolved_policy': 'record_gap', **policies})

    projectile = LOOKUP + 'projectiles__wh3__9.0.csv'
    explosion = LOOKUP + 'explosions__wh3__9.0.csv'
    for source, fields in [(projectile, [('homing_params', 'projectile_homing_params.csv', 'key'),
        ('projectile_penetration', 'projectile_penetration_junctions.csv', 'key'),
        ('scaling_damage', 'projectiles_scaling_damages.csv', 'key'),
        ('shrapnel_key', 'projectile_shrapnels.csv', 'key'),
        ('contact_stat_effect', 'ability_phases.csv', 'id'),
        ('overhead_stat_effect', 'ability_phases.csv', 'id'),
        ('spawned_vortex', 'vortices.csv', 'vortex_key')]),
        (explosion, [('shrapnel_key', 'projectile_shrapnels.csv', 'key'),
                    ('contact_phase_effect', 'ability_phases.csv', 'id')])]:
        for field, target, key in fields:
            add(source, field, TABLE + target, key)
    add(TABLE + 'projectile_shrapnels.csv', 'projectile', projectile, 'projectile_key')
    add(TABLE + 'bombardments.csv', 'projectile_type', projectile, 'projectile_key')
    add(CASTING, 'activated_projectile', projectile, 'projectile_key')
    add(CASTING, 'miscast_explosion', explosion, 'explosion_key')
    add(CASTING, 'mom_vortex_key', TABLE + 'vortices.csv', 'vortex_key')
    add(UNIT + 'source_exports/db/melee_weapons_tables/data__.tsv', 'contact_phase', PHASE, 'id')
    add(UNIT + 'source_exports/db/melee_weapons_tables/data__.tsv', 'scaling_damage',
        TABLE + 'projectiles_scaling_damages.csv', 'key')
    add(UNIT + 'source_exports/db/missile_weapons_tables/data__.tsv', 'default_projectile',
        projectile, 'projectile_key')
    add(LOOKUP + 'unit_contact_effects__wh3__9.0__ultra.csv', 'effect_key', PHASE, 'id')
    add(TABLE + 'special_ability_behaviour_groups_to_types.csv', 'behaviour',
        TABLE + 'special_ability_behaviour_to_ability_junctions.csv', 'behaviour', optional_attachment=True)
    # Contact tokens can identify a phase OR a contact group. Group membership
    # is a one-to-many relation, not an arbitrarily chosen first phase.
    group_path = TABLE + 'special_ability_contact_phase_groups.csv'
    for e in list(edges):
        if e['target'] == PHASE and e['source_columns'][0] in (
                'contact_phase', 'contact_stat_effect', 'overhead_stat_effect',
                'contact_phase_effect', 'effect_key', 'contact_effect', 'imbue_contact'):
            e['contact_alternative'] = True
            add(e['source'], e['source_columns'][0], group_path, 'contact_phase_group_id',
                contact_alternative=True, multiple=True)
            edges[-1]['name'] += '.contact_group'
    return edges


def select_records(specs, records, edges):
    selected = set()
    queue = deque()
    owner = {rid: path for path, rows in records.items() for rid in rows}
    definition_by_key = {r['key']: rid for rid, (_, r) in records[DEFINITION].items()}
    casting_by_key = {r['key']: rid for rid, (_, r) in records[CASTING].items()}
    options = {}

    def option(key):
        if key not in options:
            did, cid = definition_by_key.get(key), casting_by_key.get(key)
            d = records[DEFINITION][did][1] if did else None
            c = records[CASTING][cid][1] if cid else None
            options[key] = (classification(d, c), did, cid)
        return options[key]

    def enqueue(rid):
        if rid in selected:
            return
        selected.add(rid)
        path = owner[rid]
        if path in (DEFINITION, CASTING):
            kind, did, cid = option(records[path][rid][1]['key'])
            # Preserve both classification sources, but never follow activated
            # or unresolved payload roots, including ones reached through graphs.
            for related in (did, cid):
                if related and related != rid:
                    enqueue(related)
            if kind != 'core_passive':
                return
        queue.append(rid)

    outgoing = defaultdict(list)
    incoming = defaultdict(list)
    indexes = {}
    for i, e in enumerate(edges):
        outgoing[e['source']].append((i, e))
        indexes[(i, 'target')] = defaultdict(list)
        indexes[(i, 'source')] = defaultdict(list)
        for rid, (_, r) in records[e['target']].items():
            indexes[(i, 'target')][tuple(r[k] for k in e['target_columns'])].append(rid)
        if e['reverse']:
            incoming[e['target']].append((i, e))
            for rid, (_, r) in records[e['source']].items():
                indexes[(i, 'source')][tuple(r[k] for k in e['source_columns'])].append(rid)

    for _, row in records[ABILITY_LINK].values():
        option(row['ability_key'])
    # Roster and normalized unit relations are complete roots. Projectile,
    # explosion and raw weapon catalogs are selected through attachments.
    for path, spec in specs.items():
        if spec['role'] in ('roster', 'unit_relation') or 'unit_mount_variants__' in path:
            for rid in records[path]:
                enqueue(rid)
    while queue:
        rid = queue.popleft()
        path, r = owner[rid], records[owner[rid]][rid][1]
        for i, e in outgoing[path]:
            values = tuple(r[k] for k in e['source_columns'])
            if all(v != '' for v in values):
                for target in indexes[(i, 'target')].get(values, []):
                    enqueue(target)
        for i, e in incoming[path]:
            values = tuple(r[k] for k in e['target_columns'])
            for target in indexes[(i, 'source')].get(values, []):
                enqueue(target)
    return selected, options, indexes


def table_name(path, role):
    if role == 'roster':
        return 'unit_roster_records'
    if '/source_exports/db/' in path:
        return Path(path).parent.name.removesuffix('_tables')
    if role == 'selected_native_definition':
        return 'native_' + Path(path).stem
    return Path(path).stem.split('__')[0]


def owner_name(path):
    if '/effect_semantics/' in path:
        return 'effect_semantics'
    if '/abilities/' in path:
        return 'shared_abilities'
    return 'units'


def build_snapshot(source_root: Path, output: Path, *, before_install=None) -> dict:
    started = time.perf_counter()
    source_root, output = source_root.resolve(), output.resolve()
    if output.is_relative_to(source_root):
        raise ValueError('snapshot output must not modify the source directory')
    lock = json.loads((ROOT / 'source_lock.json').read_text(encoding='utf-8'))
    contract = json.loads((ROOT / 'schema/import_contract.json').read_text(encoding='utf-8'))
    verification = verify(source_root, lock, contract)
    if verification['status'] != 'passed':
        raise ValueError('source verification failed: ' + compact(verification['errors']))
    specs = {s['path']: dict(s, columns=contract['column_schemas'][s['columns_ref']]
             if 'columns_ref' in s else s['columns']) for s in contract['datasets']}
    original_hashes = {e['path']: hashlib.sha256(safe_path(source_root, e['path']).read_bytes()).hexdigest()
                       for e in lock['files']}
    records = {p: load_records(source_root, s) for p, s in specs.items()}
    edges = dependency_edges(contract)
    selected, options, indexes = select_records(specs, records, edges)
    # Detect source changes while reading, before creating the candidate.
    second_verification = verify(source_root, lock, contract)
    if second_verification['status'] != 'passed':
        raise ValueError('source changed during import')
    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    fd, candidate = tempfile.mkstemp(prefix=output.name + '.', suffix='.candidate', dir=output.parent)
    os.close(fd)
    candidate = Path(candidate)
    try:
        db = sqlite3.connect(candidate)
        try:
            db.executescript((ROOT / 'schema/store.sql').read_text(encoding='utf-8'))
            db.execute('BEGIN IMMEDIATE')
            snapshot_id = lock['source_commit'] + ':' + lock['contract_sha256'] + ':store2'
            db.execute('INSERT INTO snapshot VALUES(?,?,?,?,?,?,?)',
                       (snapshot_id, 2, lock['source_commit'], lock['contract_sha256'],
                        compact(contract['baseline']), compact(lock['owners']),
                        compact({'structural': 'validated selected records and dependency edges',
                                 'semantic': 'partial; raw conditions/effects retained without application',
                                 'runtime': 'unverified; engine behavior is not fully reconstructed',
                                 'activated_payloads': 'deferred',
                                 'packet_interface': 'phase 3, not implemented'})))
            for entry in lock['files']:
                path = entry['path']
                raw = safe_path(source_root, path).read_bytes()
                if hashlib.sha256(raw).hexdigest() != original_hashes[path]:
                    raise ValueError('source changed during import: ' + path)
                db.execute('INSERT INTO source_files VALUES(?,?,?,?,?,?,?,?,?)',
                    (path, snapshot_id, original_hashes[path], entry['sha256'], len(raw), owner_name(path),
                     len(records[path]) if path in records else None, 0,
                     'complete roster/relations; otherwise passive/weapon closure or classification metadata'
                     if path in records else 'authority only'))
            roster_units = {r['unit_key'] for p, rows in records.items() if specs[p]['role'] == 'roster'
                            for _, r in rows.values()}
            external_units = {r[c] for p, rows in records.items() for _, r in rows.values()
                              for c in ('base_unit_key', 'mounted_unit_key') if r.get(c)} - roster_units
            for key in sorted(roster_units | external_units):
                db.execute('INSERT INTO unit_identity VALUES(?,?,?)',
                           (key, snapshot_id, 'roster' if key in roster_units else 'external'))
            metadata_fields = {
                DEFINITION: {'key', 'requires_effect_enabling', 'type', 'source_type',
                             'source_path', 'source_line', 'source_patch'},
                CASTING: {'key', 'passive', 'source_path', 'source_line', 'source_patch'},
            }
            created = set()
            for path, spec in specs.items():
                name = table_name(path, spec['role'])
                if name not in created:
                    create_native_table(db, name, spec['columns'], spec['keys'])
                    created.add(name)
                db.execute('INSERT INTO dataset_tables VALUES(?,?,?)',
                           (path, name, compact(spec['columns'])))
                count = 0
                for rid, (logical, row) in records[path].items():
                    if rid not in selected:
                        continue
                    retention = 'full'
                    if path in metadata_fields and options[row['key']][0] != 'core_passive':
                        retention = 'option_metadata'
                    db.execute('INSERT INTO record_provenance VALUES(?,?,?,?,?,?,?,?)',
                        (rid, path, logical, compact({k: row[k] for k in spec['keys']}),
                         row.get('source_path') or None, int(row['source_line']) if row.get('source_line') else None,
                         row.get('source_patch') or None, retention))
                    # Metadata-only definitions/casting use separate narrow tables;
                    # payload fields are absent, rather than populated with false NULLs.
                    actual_name, cols = name, spec['columns']
                    if retention == 'option_metadata':
                        actual_name += '_metadata'
                        cols = [c for c in cols if c['name'] in metadata_fields[path]]
                        if actual_name not in created:
                            create_native_table(db, actual_name, cols, ['key'])
                            created.add(actual_name)
                    names = ['record_id'] + [c['name'] for c in cols]
                    db.execute(f'INSERT INTO {quote(actual_name)} ({",".join(map(quote,names))}) '
                               f'VALUES({",".join("?" for _ in names)})',
                               [rid] + [convert(row[c['name']], c['type']) for c in cols])
                    if row.get('unit_key'):
                        db.execute('INSERT INTO unit_records VALUES(?,?)', (rid, row['unit_key']))
                    count += 1
                db.execute('UPDATE source_files SET retained_rows=? WHERE path=?', (count, path))
            for key, (kind, did, cid) in sorted(options.items()):
                definition = records[DEFINITION][did][1] if did else {}
                evidence = {'rule': 'definition present and casting.passive',
                            'version': 1, 'definition_record': did, 'casting_record': cid,
                            'passive': records[CASTING][cid][1]['passive'] if cid else None}
                db.execute('INSERT INTO ability_option_metadata VALUES(?,?,?,?,?,?)',
                           (key, kind, convert(definition.get('requires_effect_enabling', ''), 'BOOLEAN'),
                            did, cid, compact(evidence)))
                if kind == 'unresolved':
                    db.execute('INSERT INTO coverage_gaps(record_id,kind,detail) VALUES(?,?,?)',
                               (did or cid, 'classification_unresolved', key))
            for i, edge in enumerate(edges):
                for rid, (_, row) in records[edge['source']].items():
                    if rid not in selected:
                        continue
                    if edge['source'] in (DEFINITION, CASTING) and options[row['key']][0] != 'core_passive':
                        continue
                    values = tuple(row[c] for c in edge['source_columns'])
                    if not all(v != '' for v in values):
                        continue
                    targets = indexes[(i, 'target')].get(values, [])
                    if len(targets) > 1 and not edge.get('multiple'):
                        raise ValueError('ambiguous dependency: ' + edge['name'])
                    if not targets and edge.get('optional_attachment'):
                        continue
                    if not targets and edge.get('contact_alternative'):
                        if any(indexes[(j, 'target')].get(values) for j, other in enumerate(edges)
                               if other.get('contact_alternative') and other['source'] == edge['source']
                               and other['source_columns'] == edge['source_columns']):
                            continue
                    for ordinal, target in enumerate(targets or [None]):
                        status = 'resolved' if target in selected else 'unresolved'
                        db.execute('INSERT INTO relation_edges VALUES(?,?,?,?,?,?)',
                                   (rid, edge['name'], compact(values), target if status == 'resolved' else None,
                                    status, ordinal))
                        if target and edge['target'] in (DEFINITION, CASTING) and edge['source'] != ABILITY_LINK:
                            target_key = records[edge['target']][target][1]['key']
                            if options[target_key][0] != 'core_passive':
                                db.execute('INSERT OR IGNORE INTO coverage_gaps(record_id,kind,detail) VALUES(?,?,?)',
                                    (rid, 'nonpassive_dependency_deferred', edge['name'] + ':' + target_key))
                    if not targets:
                        if edge['unresolved_policy'] == 'reject':
                            raise ValueError('unresolved required relation: ' + edge['name'])
                        db.execute('INSERT INTO coverage_gaps(record_id,kind,detail) VALUES(?,?,?)',
                                   (rid, 'unresolved_reference', edge['name'] + ':' + compact(values)))
            normalize_roster(db, next(s for s in specs.values() if s['role'] == 'roster'))
            import_payload_lineage(db, source_root)
            import_localization(db, source_root, lock, options)
            record_semantic_gaps(db)
            validate_candidate(db, specs, records, selected)
            db.commit()
            db.execute('ANALYZE')
            db.commit()
            report = report_candidate(db)
        finally:
            db.close()
        # Recheck bytes immediately before installation, including raw metadata.
        for path, digest in original_hashes.items():
            if hashlib.sha256(safe_path(source_root, path).read_bytes()).hexdigest() != digest:
                raise ValueError('source changed before installation: ' + path)
        if before_install is not None:
            before_install(candidate)
        with candidate.open('r+b') as stream:
            os.fsync(stream.fileno())
        os.replace(candidate, output)
        return dict(report, status='passed', seconds=round(time.perf_counter() - started, 3),
                    bytes=output.stat().st_size, source_commit=lock['source_commit'])
    finally:
        candidate.unlink(missing_ok=True)


def import_payload_lineage(db, root):
    path = TABLE.removesuffix('tables/') + 'payload_provenance.csv'
    targets = {}
    for kind, table, key in [('projectile', 'projectiles', 'projectile_key'),
                             ('explosion', 'explosions', 'explosion_key')]:
        for rid, value in db.execute(f'SELECT record_id,{quote(key)} FROM {quote(table)}'):
            targets[(kind, value)] = rid
    count = total = 0
    seen = set()
    with safe_path(root, path).open(encoding='utf-8', newline='') as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames != ['kind', 'key', 'source_path', 'source_line', 'source_patch']:
            raise ValueError('payload lineage header drift')
        for i, row in enumerate(reader, 2):
            total += 1
            key = (row['kind'], row['key'])
            if key in seen:
                raise ValueError('duplicate payload lineage identity')
            seen.add(key)
            if key not in targets:
                continue
            rid = record_id(path, i)
            db.execute('INSERT INTO record_provenance VALUES(?,?,?,?,?,?,?,?)',
                       (rid, path, i, compact({'kind': key[0], 'key': key[1]}), row['source_path'],
                        int(row['source_line']), row['source_patch'], 'full'))
            db.execute('INSERT INTO record_lineage VALUES(?,?)', (targets[key], rid))
            db.execute('UPDATE record_provenance SET source_path=?,source_line=?,source_patch=? WHERE id=?',
                       (row['source_path'], int(row['source_line']), row['source_patch'], targets[key]))
            count += 1
    missing = set(targets) - seen
    if missing:
        raise ValueError('missing payload lineage: ' + compact(sorted(missing)))
    db.execute('UPDATE source_files SET input_rows=?,retained_rows=?,selection_policy=? WHERE path=?',
               (total, count, 'exact lineage for selected weapon/passive payloads', path))


def import_localization(db, root, lock, options):
    # Retain relevant text, raw markup and placeholders for phase-3 reviewed
    # explanations. Text is evidence, never a grant or a numeric modifier.
    attributes = {r[0] for r in db.execute('SELECT DISTINCT attribute_key FROM unit_attributes')}
    flags = {r[0] for r in db.execute('SELECT flag_key FROM native_special_ability_invalid_usage_flags')}
    wanted = {f'unit_attributes_{prefix}_{key}' for key in attributes
              for prefix in ('onscreen_name', 'bullet_text')}
    wanted |= {f'unit_abilities_{prefix}_{key}' for key in options for prefix in ('onscreen_name', 'tooltip_text')}
    wanted |= {f'special_ability_invalid_usage_flags_{prefix}_{key}' for key in flags
               for prefix in ('alt_description', 'flag_description')}
    for entry in lock['files']:
        path = entry['path']
        if not path.endswith('.loc.tsv'):
            continue
        count = total = 0
        with safe_path(root, path).open(encoding='utf-8', newline='') as stream:
            for i, row in enumerate(csv.DictReader(stream, delimiter='\t'), 2):
                if row['key'].startswith('#'):
                    continue
                total += 1
                # Stat and bullet dictionaries are small semantic catalogs.
                if row['key'] not in wanted and not path.endswith(('unit_stat_localisations__.loc.tsv',
                                                                 'ui_unit_bullet_point_enums__.loc.tsv')):
                    continue
                rid = record_id(path, i)
                db.execute('INSERT INTO record_provenance VALUES(?,?,?,?,?,?,?,?)',
                           (rid, path, i, compact({'key': row['key']}), None, None, None, 'localization'))
                db.execute('INSERT INTO localization VALUES(?,?,?,?)',
                           (rid, row['key'], row['text'], convert(row['tooltip'], 'BOOLEAN')))
                count += 1
        db.execute('UPDATE source_files SET input_rows=?,retained_rows=?,selection_policy=? WHERE path=?',
                   (total, count, 'linked labels/condition text and stat/trait dictionaries', path))


def record_semantic_gaps(db):
    # Engine behaviors and summons remain source evidence, not implemented
    # mechanics. Absence of a behavior-to-ability row is not a broken join.
    for rid, behavior in db.execute('SELECT record_id,behaviour FROM native_special_ability_behaviour_groups_to_types'):
        db.execute('INSERT INTO coverage_gaps(record_id,kind,detail) VALUES(?,?,?)',
                   (rid, 'engine_behavior_unverified', behavior))
    for rid, unit in db.execute('SELECT record_id,spawned_unit FROM native_ability_casting WHERE spawned_unit IS NOT NULL'):
        db.execute('INSERT INTO coverage_gaps(record_id,kind,detail) VALUES(?,?,?)',
                   (rid, 'summon_runtime_unverified', unit))
    for rid in db.execute('SELECT record_id FROM unit_components WHERE can_be_targeted IS NULL'):
        db.execute('INSERT INTO coverage_gaps(record_id,kind,detail) VALUES(?,?,?)',
                   (rid[0], 'targetability_unknown', 'Source does not establish secondary-component targetability.'))


AVAILABILITY_FIELDS = {
    'faction_name', 'faction_key', 'subculture_key', 'military_group',
    'roster_scope', 'is_faction_exclusive', 'military_group_count',
    'permitted_faction_count', 'availability_notes',
}


def normalize_roster(db, spec):
    """Split source roster records into shared profiles and qualified availability."""
    columns = spec['columns']
    profile_columns = [c for c in columns if c['name'] not in AVAILABILITY_FIELDS]
    availability_columns = [c for c in columns if c['name'] in AVAILABILITY_FIELDS or c['name'] == 'unit_key']
    db.row_factory = sqlite3.Row
    rows = [dict(r) for r in db.execute('SELECT * FROM unit_roster_records ORDER BY unit_key,record_id')]
    db.row_factory = None
    profiles = {}
    factions = defaultdict(set)
    for row in rows:
        key = row['unit_key']
        values = tuple(row[c['name']] for c in profile_columns)
        if key in profiles and profiles[key][1] != values:
            raise ValueError('conflicting base profile fields: ' + key)
        profiles.setdefault(key, (row['record_id'], values))
        factions[key].add(row['faction_name'])
    create_native_table(db, 'unit_profiles', profile_columns, ['unit_key'])
    db.execute('CREATE UNIQUE INDEX profile_identity ON unit_profiles(unit_key)')
    db.execute("ALTER TABLE unit_profiles ADD COLUMN faction_name TEXT NOT NULL DEFAULT '[]' "
               "CHECK(json_valid(faction_name) AND json_type(faction_name)='array')")
    create_native_table(db, 'unit_availability', availability_columns, ['unit_key', 'faction_key', 'subculture_key'],
                        constraints=['FOREIGN KEY(unit_key) REFERENCES unit_profiles(unit_key)'])
    for key, (rid, values) in sorted(profiles.items()):
        names = ['record_id'] + [c['name'] for c in profile_columns] + ['faction_name']
        db.execute(f'INSERT INTO unit_profiles ({",".join(map(quote,names))}) '
                   f'VALUES({",".join("?" for _ in names)})',
                   (rid, *values, compact(sorted(factions[key]))))
    names = ['record_id'] + [c['name'] for c in availability_columns]
    db.executemany(f'INSERT INTO unit_availability ({",".join(map(quote,names))}) '
                   f'VALUES({",".join("?" for _ in names)})',
                   [tuple(row[n] for n in names) for row in rows])
    # The compatibility view reconstructs every original roster field and locator,
    # without storing repeated combat statistics. dataset_tables points here.
    db.execute('DROP TABLE unit_roster_records')
    projection = ['a.record_id'] + [f'{"a" if c["name"] in AVAILABILITY_FIELDS else "p"}.{quote(c["name"])}'
                                  for c in columns]
    db.execute('CREATE VIEW unit_roster_records AS SELECT ' + ','.join(projection) +
               ' FROM unit_availability a JOIN unit_profiles p ON p.unit_key=a.unit_key')


def validate_candidate(db, specs, records, selected):
    if db.execute('PRAGMA integrity_check').fetchone() != ('ok',):
        raise ValueError('candidate integrity failure')
    if db.execute('PRAGMA foreign_key_check').fetchall():
        raise ValueError('candidate foreign key failure')
    expected = sum(len(records[p]) for p, s in specs.items() if s['role'] == 'roster')
    if db.execute('SELECT count(*) FROM unit_availability').fetchone()[0] != expected:
        raise ValueError('roster reconciliation failure')
    expected_profiles = {r['unit_key'] for p, s in specs.items() if s['role'] == 'roster'
                         for _, r in records[p].values()}
    if db.execute('SELECT count(*) FROM unit_profiles').fetchone()[0] != len(expected_profiles):
        raise ValueError('profile reconciliation failure')
    for path, spec in specs.items():
        expected = sum(rid in selected for rid in records[path])
        actual = db.execute('SELECT count(*) FROM record_provenance WHERE source_file=?', (path,)).fetchone()[0]
        if actual != expected:
            raise ValueError('source accounting failure: ' + path)
        # Uniqueness checked on original strings, including blank key components,
        # and retained as a separate provenance key rather than SQL NULL equality.
        duplicate = db.execute('SELECT native_key_json,count(*) FROM record_provenance '
                               'WHERE source_file=? GROUP BY native_key_json HAVING count(*)>1', (path,)).fetchall()
        if duplicate:
            raise ValueError('duplicate native identity: ' + path)
    db.execute('CREATE UNIQUE INDEX roster_identity ON unit_availability(subculture_key,unit_key)')


def report_candidate(db):
    plans = {}
    for label, sql, params in [
        ('unit_key', 'SELECT record_id FROM unit_profiles WHERE unit_key=?', ('wh2_main_lzd_mon_kroxigors',)),
        ('unit_name', 'SELECT record_id FROM unit_profiles WHERE unit_name=? COLLATE NOCASE', ('Kroxigor',)),
        ('relations', 'SELECT record_id FROM unit_records WHERE unit_key=?', ('wh2_main_lzd_mon_kroxigors',)),
        ('reverse_edge', 'SELECT source_record FROM relation_edges WHERE target_record=?', ('example',)),
    ]:
        plans[label] = [r[3] for r in db.execute('EXPLAIN QUERY PLAN ' + sql, params)]
        if any('SCAN ' in detail for detail in plans[label]):
            raise ValueError('unindexed ordinary access: ' + label)
    return {'roster_rows': db.execute('SELECT count(*) FROM unit_availability').fetchone()[0],
            'unit_profiles': db.execute('SELECT count(*) FROM unit_profiles').fetchone()[0],
            'unit_identities': dict(db.execute('SELECT namespace,count(*) FROM unit_identity GROUP BY namespace')),
            'classifications': dict(db.execute('SELECT classification,count(*) FROM ability_option_metadata GROUP BY classification')),
            'retained_records': db.execute('SELECT count(*) FROM record_provenance').fetchone()[0],
            'relations': dict(db.execute('SELECT status,count(*) FROM relation_edges GROUP BY status')),
            'coverage_gaps': db.execute('SELECT count(*) FROM coverage_gaps').fetchone()[0],
            'query_plans': plans,
            'integrity': 'ok', 'foreign_key_errors': [],
            'datasets': [{'path': r[0], 'input': r[1], 'retained': r[2], 'excluded': r[1]-r[2]}
                         for r in db.execute('SELECT path,input_rows,retained_rows FROM source_files '
                                             'WHERE input_rows IS NOT NULL ORDER BY path')]}
