"""Bounded structured searches over the existing, immutable serving snapshot.

Only expressions in FIELDS become SQL. All caller values are bound parameters.
No stats are inferred from names, and no combat modifiers are applied.
"""
from __future__ import annotations

import base64
from contextlib import contextmanager
import hashlib
import json
import math
import sqlite3

VERSION = 'unit-search-1.0.0'
LIMITATIONS = [
    'Complete only within the imported snapshot, not all game or campaign availability.',
    'Some source labels contain unresolved localization tokens ({{tr:...}}); keys and numeric facts remain sourced, and replacement names are not guessed.',
    'Lord/hero uses native source_caste; legendary/special-character status is not classified.',
    'Family means connected explicit mount links plus deduplicated aliases; unrelated forms are not inferred.',
    'Stats are unmodified custom-battle, ultra, rank 0; conditional effects are not applied.',
    'Weapon stats describe the sourced primary melee weapon or selected default projectile, not all attacks.',
]
FIELDS = {}


def field(name, kind, units, meaning, expression=None, relation=None, category=False):
    FIELDS[name] = dict(type=kind, units=units, meaning=meaning,
                        expression=expression or 'p."' + name + '"', relation=relation,
                        categorical=category)


for name, meaning in {
    'unit_key': 'Canonical deduplicated profile key; resolves in existing tools.',
    'unit_name': 'Qualified display label including represented mount variants.',
    'source_unit_name': 'Original source label; may contain unresolved localization tokens. Not a family identifier.',
    'source_caste': 'Native main-unit caste; lord/hero are source classifications, not legendary status.',
    'tactical_category': 'Canonical coarse tactical body plan, including infantry and character.',
    'source_unit_class': 'Native class retained for provenance; use tactical_category for body plan.',
    'primary_component_role': 'Primary targetable body role; not every component.',
    'source_melee_weapon_key': 'Primary melee weapon namespace.',
    'source_projectile_key': 'Selected default projectile namespace.',
    'source_mount_entity_key': 'Source mount entity; null does not imply a missing mount variant link.',
    'source_engine_entity_key': 'Source engine body entity.',
}.items():
    field(name, 'string', 'identifier' if name.endswith('key') else 'label', meaning,
          category=name in ('source_caste', 'tactical_category', 'source_unit_class', 'primary_component_role'))

for name, units, meaning in [
    ('melee_attack', 'combat_rating', 'Base melee attack rating.'),
    ('melee_defence', 'combat_rating', 'Base melee defence rating.'),
    ('armour', 'armour_points', 'Base armour rating.'),
    ('leadership', 'leadership_points', 'Base leadership, not a rout prediction.'),
    ('speed', 'native_run_speed', 'Primary body native run_speed; no movement conversion.'),
    ('mass', 'native_mass', 'Primary body native mass, not total unit mass.'),
    ('entity_count', 'entities', 'Primary targetable bodies; excludes secondary crew/riders.'),
    ('hp_per_entity', 'hit_points_per_entity', 'Primary body health, not an average across components.'),
    ('total_hp', 'unit_hit_points', 'Whole source health pool, including crew where represented.'),
    ('weapon_base_damage', 'melee_damage_per_hit', 'Primary melee weapon base damage; not all weapon attachments.'),
    ('weapon_ap_damage', 'melee_damage_per_hit', 'Primary melee weapon armour-piercing damage per hit.'),
    ('charge_bonus', 'combat_rating', 'Base charge bonus, not an applied temporary bonus.'),
    ('multiplayer_cost', 'multiplayer_gold', 'Native custom-battle multiplayer cost.'),
    ('campaign_recruit_cost', 'campaign_gold', 'Base campaign recruitment cost; no campaign modifiers.'),
    ('campaign_upkeep', 'campaign_gold_per_turn', 'Base campaign upkeep per turn.'),
    ('range', 'metres', 'Selected default projectile effective range; other weapons may differ.'),
    ('missile_base_damage', 'projectile_damage', 'Selected default projectile direct base damage, excluding explosions.'),
    ('missile_ap_damage', 'projectile_damage', 'Selected default projectile direct armour-piercing damage.'),
    ('ammunition', 'native_ammo_pool', 'Selected default missile link ammo capacity, not a sum over attachments.'),
]:
    field(name, 'number', units, meaning)
for name in ('is_renown', 'is_single_entity', 'has_missile_weapon'):
    field(name, 'boolean', 'boolean', 'Sourced normalized ' + name + ' flag.', category=True)
field('is_mounted', 'boolean', 'boolean',
      'Has a source mount/engine body or is the mounted endpoint of an explicit mount link; includes platforms.',
      "(p.source_mount_entity_key IS NOT NULL OR p.source_engine_entity_key IS NOT NULL OR EXISTS "
      "(SELECT 1 FROM unit_mount_variants m JOIN unit_aliases k ON k.unit_key=m.mounted_unit_key WHERE k.profile_unit_key=p.unit_key))", category=True)

# Relation predicates use existential membership; negatives mean NO matching member.
AVAIL = 'unit_availability v JOIN unit_aliases k ON k.unit_key=v.unit_key'
for name in ('subculture_key', 'faction_key', 'faction_name'):
    field(name, 'string', 'identifier' if name.endswith('key') else 'label',
          'Distinct represented roster memberships across profile aliases; not campaign recruitment permission.',
          relation=(AVAIL, 'k.profile_unit_key=p.unit_key', 'v.' + name), category=True)
field('attribute_key', 'string', 'identifier', 'Distinct sourced attributes across equivalent aliases.',
      relation=('unit_attributes v JOIN unit_aliases k ON k.unit_key=v.unit_key',
                'k.profile_unit_key=p.unit_key', 'v.attribute_key'), category=True)
field('source_unit_keys', 'string', 'identifier', 'All original main-unit keys aliased to this profile.',
      relation=('unit_aliases k', 'k.profile_unit_key=p.unit_key', 'k.unit_key'))
DEFAULT_FIELDS = ['unit_key', 'unit_name', 'subculture_key', 'source_caste', 'is_mounted']


def operators(spec):
    result = ['eq', 'ne', 'in', 'not_in', 'is_null', 'is_not_null']
    if spec['type'] == 'number':
        result += ['gt', 'gte', 'lt', 'lte', 'between']
    if spec['type'] == 'string':
        result += ['contains']
    return result


def _field(name):
    if not isinstance(name, str) or name not in FIELDS:
        raise ValueError(f'Unsupported field {name!r}; call discover_unit_fields')
    return FIELDS[name]


def _value(value, spec):
    kind = spec['type']
    if kind == 'number':
        if type(value) not in (int, float) or abs(value) > 1e12 or not math.isfinite(value):
            raise ValueError('Numeric values must be finite and within +/-1e12; null needs is_null')
    elif kind == 'boolean':
        if type(value) is not bool:
            raise ValueError('Boolean field requires true/false')
    elif not isinstance(value, str) or not value or len(value) > 256:
        raise ValueError('String values must contain 1..256 characters')
    return value


def compile_filter(node):
    """Compile a validated AND/OR tree with SQL three-valued scalar semantics."""
    count = 0

    def visit(n, depth=0):
        nonlocal count
        count += 1
        if depth > 5 or count > 32:
            raise ValueError('Filters allow at most depth 5 and 32 total nodes')
        if not isinstance(n, dict) or not n:
            raise ValueError('Each filter must be a nonempty object')
        if set(n) in ({'and'}, {'or'}):
            key = next(iter(n)); children = n[key]
            if not isinstance(children, list) or not 1 <= len(children) <= 32:
                raise ValueError('AND/OR needs 1..32 child filters')
            terms = [visit(child, depth + 1) for child in children]
            return '(' + (' AND ' if key == 'and' else ' OR ').join(t[0] for t in terms) + ')', [v for t in terms for v in t[1]]
        if set(n) - {'field', 'op', 'value', 'value_field'} or not {'field', 'op'} <= set(n):
            raise ValueError('Predicate requires field/op and value or value_field')
        spec = _field(n['field']); op = n['op']
        if not isinstance(op, str) or op not in operators(spec):
            raise ValueError(f'Unsupported operator for {n["field"]}; allowed: {operators(spec)}')
        rel = spec['relation']; expr = rel[2] if rel else spec['expression']
        params = []
        if op in ('is_null', 'is_not_null'):
            if set(n) != {'field', 'op'}:
                raise ValueError('Null checks take no value')
            predicate = expr + (' IS NULL' if op == 'is_null' else ' IS NOT NULL')
            if rel:
                # Empty/no-known-member, not an invented NULL relation value.
                inner = f'SELECT 1 FROM {rel[0]} WHERE {rel[1]} AND {expr} IS NOT NULL'
                return ('NOT ' if op == 'is_null' else '') + f'EXISTS ({inner})', []
        elif 'value_field' in n:
            if 'value' in n or rel or op not in ('eq', 'ne', 'gt', 'gte', 'lt', 'lte'):
                raise ValueError('Field comparison requires two compatible scalar numeric fields')
            other = _field(n['value_field'])
            if other['relation'] or spec['type'] != 'number' or other['type'] != 'number' or spec['units'] != other['units']:
                raise ValueError('Field comparison requires compatible numeric types, units and scopes')
            predicate = expr + ' ' + {'eq':'=', 'ne':'!=', 'gt':'>', 'gte':'>=', 'lt':'<', 'lte':'<='}[op] + ' ' + other['expression']
        else:
            if 'value' not in n:
                raise ValueError('Predicate needs value (or value_field)')
            value = n['value']
            if op in ('in', 'not_in', 'between'):
                if not isinstance(value, list) or not 1 <= len(value) <= 32 or (op == 'between' and len(value) != 2):
                    raise ValueError('Membership requires 1..32 values; between requires two ordered endpoints')
                params = [_value(v, spec) for v in value]
                if op == 'between':
                    if params[0] > params[1]:
                        raise ValueError('Range lower endpoint exceeds upper endpoint')
                    predicate = expr + ' BETWEEN ? AND ?'
                else:
                    negative = op == 'not_in' and not rel
                    predicate = expr + (' NOT IN (' if negative else ' IN (') + ','.join('?' for _ in params) + ')'
            else:
                params = [_value(value, spec)]
                if op == 'contains':
                    predicate = f'instr(lower({expr}),lower(?))>0'
                else:
                    sqlop = {'eq':'=', 'ne':'=' if rel else '!=', 'gt':'>', 'gte':'>=', 'lt':'<', 'lte':'<='}[op]
                    predicate = expr + ' ' + sqlop + ' ?'
        if rel:
            inner = f'EXISTS (SELECT 1 FROM {rel[0]} WHERE {rel[1]} AND ({predicate}))'
            # Missing relation is unknown, not evidence of a negative membership.
            if op in ('ne', 'not_in'):
                inner = f'EXISTS (SELECT 1 FROM {rel[0]} WHERE {rel[1]} AND {expr} IS NOT NULL) AND NOT ' + inner
            return '(' + inner + ')', params
        return '(' + predicate + ')', params

    return ('1', []) if node is None else visit(node)


@contextmanager
def budget(db):
    ticks = 0
    def progress():
        nonlocal ticks
        ticks += 1
        return ticks > 2000  # At most 20 million SQLite VM instructions per call.
    db.set_progress_handler(progress, 10000)
    try:
        yield
    except sqlite3.OperationalError as exc:
        if 'interrupted' in str(exc):
            raise ValueError('Search execution budget exceeded; narrow filters') from exc
        raise
    finally:
        db.set_progress_handler(None, 0)


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def _offset(cursor, binding):
    if cursor is None:
        return 0
    try:
        if not isinstance(cursor, str) or len(cursor) > 2048:
            raise ValueError()
        obj = json.loads(base64.b64decode(cursor, altchars=b'-_', validate=True))
        if set(obj) != {'binding', 'offset'} or obj['binding'] != binding or type(obj['offset']) is not int or not 0 <= obj['offset'] <= 100000:
            raise ValueError()
        return obj['offset']
    except (ValueError, TypeError, KeyError):
        raise ValueError('Invalid/stale cursor; retain identical query and snapshot or restart') from None


def _cursor(offset, binding):
    return base64.urlsafe_b64encode(json.dumps(dict(binding=binding, offset=offset)).encode()).decode()


def _limit(limit):
    if type(limit) is not int or not 1 <= limit <= 100:
        raise ValueError('limit must be an integer from 1 to 100')


def discover_unit_fields(q, field=None, cursor=None, limit=50):
    _limit(limit)
    binding = _digest([VERSION, q.snapshot, 'discover', field, limit])
    offset = _offset(cursor, binding)
    if field is not None:
        spec = _field(field)
        if not spec['categorical']:
            raise ValueError('Category discovery is supported only for fields marked categorical')
        rel = spec['relation']
        sql = (f'SELECT DISTINCT {rel[2]} AS value FROM {rel[0]} WHERE {rel[2]} IS NOT NULL' if rel else
               f'SELECT DISTINCT {spec["expression"]} AS value FROM unit_profiles p WHERE {spec["expression"]} IS NOT NULL')
        with budget(q.db):
            values = [r[0] for r in q.db.execute(sql + ' ORDER BY value')]
        if spec['type'] == 'boolean':
            values = [bool(v) for v in values]
        items = values
    else:
        items = [dict(name=name, type=s['type'], units=s['units'], meaning=s['meaning'],
                      multivalued=bool(s['relation']), operators=operators(s), sortable=not bool(s['relation']),
                      field_comparison=s['type'] == 'number' and not s['relation'],
                      categorical=s['categorical'], nullable=name not in ('unit_key', 'unit_name', 'source_unit_name', 'is_mounted'),
                      source_mapping=('existential distinct membership' if s['relation'] else s['expression'])) for name, s in FIELDS.items()]
    page = items[offset:offset + limit]
    return dict(schema_version=VERSION, snapshot=q.snapshot, baseline=json.loads(q.snapshot['baseline_json']), field=field, items=page,
                total_count=len(items), returned_count=len(page),
                next_cursor=_cursor(offset + len(page), binding) if offset + len(page) < len(items) else None,
                complete=offset + len(page) >= len(items), limitations=LIMITATIONS,
                null_semantics='Scalar ordinary predicates exclude null, including ne/not_in. Relation predicates use any-member; ne/not_in require a known member and no matching member. Relation is_null means no known members.',
                query_shape={'leaf': {'field': 'melee_attack', 'op': 'gt', 'value': 60},
                             'field_comparison': {'field': 'melee_defence', 'op': 'gt', 'value_field': 'melee_attack'},
                             'groups': 'Use {and:[...]} or {or:[...]}; no implicit precedence or general NOT.'})


def _families(db):
    """Connected mount components, never localized-name heuristics."""
    aliases = dict(db.execute('SELECT unit_key,profile_unit_key FROM unit_aliases'))
    parent = {key: key for key in aliases.values()}
    def root(key):
        while parent[key] != key:
            parent[key] = parent[parent[key]]
            key = parent[key]
        return key
    for base, mounted in db.execute('SELECT base_unit_key,mounted_unit_key FROM unit_mount_variants'):
        if base in aliases and mounted in aliases:
            a, b = root(aliases[base]), root(aliases[mounted])
            parent[max(a, b)] = min(a, b)
    return {key: root(key) for key in parent}


def search_units(q, filters=None, fields=None, sort=None, mode='variants', cursor=None, limit=50):
    _limit(limit)
    if mode not in ('variants', 'families'):
        raise ValueError('mode must be variants or families')
    fields = DEFAULT_FIELDS if fields is None else fields
    if not isinstance(fields, list) or not 1 <= len(fields) <= 16 or any(not isinstance(f, str) for f in fields) or len(set(fields)) != len(fields):
        raise ValueError('fields must contain 1..16 distinct supported field names')
    for f in fields:
        _field(f)
    fields = list(dict.fromkeys(['unit_key', 'unit_name', 'subculture_key', 'source_unit_keys', *fields]))
    sort = [{'field': 'unit_name', 'direction': 'asc'}] if sort is None else sort
    if not isinstance(sort, list) or not 1 <= len(sort) <= 3:
        raise ValueError('sort must contain 1..3 field/direction objects')
    ordering = []
    for item in sort:
        if not isinstance(item, dict) or set(item) != {'field', 'direction'} or item['direction'] not in ('asc', 'desc'):
            raise ValueError('Each sort requires field and asc/desc direction')
        s = _field(item['field'])
        if s['relation']:
            raise ValueError('Multivalued fields cannot be sorted; choose an explicit scalar field')
        ordering += [s['expression'] + ' ' + item['direction'].upper() + ' NULLS LAST']
    ordering.append('p.unit_key ASC')
    predicate, params = compile_filter(filters)
    binding = _digest([VERSION, q.snapshot, filters, fields, sort, mode, limit])
    offset = _offset(cursor, binding)
    expressions = []
    for f in fields:
        s = FIELDS[f]; rel = s['relation']
        expr = (f'(SELECT json_group_array(value) FROM (SELECT DISTINCT {rel[2]} AS value FROM {rel[0]} WHERE {rel[1]} AND {rel[2]} IS NOT NULL ORDER BY value))'
                if rel else s['expression'])
        expressions.append(expr + ' AS "' + f + '"')
    with budget(q.db):
        # At most 10k profiles; early LIMIT avoids unbounded materialization if scope grows.
        rows = [dict(r) for r in q.db.execute('SELECT ' + ','.join(expressions) +
                ' FROM unit_profiles p WHERE ' + predicate + ' ORDER BY ' + ','.join(ordering) + ' LIMIT 10001', params)]
        if len(rows) > 10000:
            raise ValueError('Search exceeds 10000 matching profiles; narrow filters')
        for row in rows:
            for f in fields:
                if FIELDS[f]['relation']:
                    row[f] = json.loads(row[f])
                elif FIELDS[f]['type'] == 'boolean' and row[f] is not None:
                    row[f] = bool(row[f])
        variant_count = len(rows)
        if mode == 'families':
            families = _families(q.db)
            groups = {}
            for row in rows:
                key = families[row['unit_key']]
                groups.setdefault(key, dict(family_key=key, matching_variants=[]))['matching_variants'].append(row)
            rows = list(groups.values())  # Family order = first matching variant in requested sort.
    # Bound bytes without dropping identities: retry smaller fields/variant mode for a huge family.
    page = []; byte_count = 0
    for row in rows[offset:offset + limit]:
        size = len(json.dumps(row, ensure_ascii=False).encode())
        if byte_count + size > 60000:
            if not page:
                raise ValueError('One family/row exceeds 60000 bytes; request fewer fields or variants mode')
            break
        page.append(row); byte_count += size
    next_offset = offset + len(page)
    return dict(schema_version=VERSION, snapshot=q.snapshot, baseline=json.loads(q.snapshot['baseline_json']), results=page,
                query=dict(filters=filters, fields=fields, sort=sort, mode=mode,
                           grouping='Filters before grouping; mount-linked connected families; stats remain per matching variant.',
                           ordering='Nulls last; canonical key tie-breaker; families ordered by first matching variant.'),
                total_count=len(rows), count_unit='profiles' if mode == 'variants' else 'mount_linked_families',
                total_matching_variants=variant_count, returned_count=len(page),
                returned_variants=len(page) if mode == 'variants' else sum(len(r['matching_variants']) for r in page),
                next_cursor=_cursor(next_offset, binding) if next_offset < len(rows) else None,
                complete=next_offset >= len(rows), limitations=LIMITATIONS)
