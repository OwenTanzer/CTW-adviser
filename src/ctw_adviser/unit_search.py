"""Roster enumeration, structured unit search and field discovery (issue #28).

Reads the pinned SQLite snapshot through the shared query library. A search row
is a qualified variant: one canonical stat profile in one represented
subculture. Values are the imported unmodified baseline; no passive, activated
or modeled modifier is applied. Fields come only from the reviewed mapping in
FIELDS, so every predicate, sort and output is a whitelisted, parameterized
expression.
"""

from __future__ import annotations

import base64
import difflib
import hashlib
import json
import sqlite3

from .queries import PACKET_VERSION, compact

SEARCH_VERSION = 'unit-search-1.0.0'
MAX_CONDITIONS = 32
MAX_DEPTH = 4
MAX_LIST_VALUES = 64
MAX_FIELDS = 24
MAX_SORT = 3
MAX_LIMIT = 100
DEFAULT_LIMIT = 25
CATEGORY_PAGE = 64
INLINE_CATEGORIES = 32
MAX_VM_STEPS = 50_000_000  # progress-handler budget per call, in 1,000-instruction ticks

FOLLOW_UP = ('Pass a result unit_key with its subculture to get_unit_combat_profile, get_matchup_evidence or '
             'evaluate_single_unit_matchup (subculture/subculture_a/subculture_b); provenance_refs work with get_provenance.')
ROW_DEFINITION = ('qualified_variant: one canonical unit stat profile (unit_profiles) in one represented '
                  'subculture (unit_availability through unit_aliases). A profile available to several '
                  'subcultures appears once per subculture; filter by subculture for a roster.')
FAMILY_DEFINITION = ('mount_family: the on-foot base profile and its mounted variants from '
                     'unit_mount_variants, within one subculture; a profile with no mount relation is its own '
                     'family. Filters apply to variants before grouping; values are never merged across variants.')
COVERAGE = ('Complete within the imported pinned snapshot only: 2,379 stat profiles and 25 subcultures from '
            'CTW-data unit_profiles/unit_availability. This is not proof of complete game coverage; units the '
            'snapshot does not import cannot match.')
BASELINE_NOTE = ('Imported base values for the declared baseline. Passive abilities, activated abilities, '
                 'technologies, skills, items and campaign effects are not applied; no combat is simulated.')

PRIMARY_MELEE = ('Normalized primary melee weapon of the profile (land_units.primary_melee_weapon). '
                 'Secondary melee weapons and other components are not searched; inspect them with '
                 'get_unit_combat_profile section=weapons.')
PRIMARY_MISSILE = ('Normalized default projectile of the profile primary missile weapon. Null for profiles '
                   'without a primary missile weapon. Alternative projectiles and secondary missile weapons are '
                   'not searched.')
PRIMARY_EXPLOSION = ('Explosion attached to the default projectile of the primary missile weapon; null when that '
                     'projectile has no explosion.')

# The base relation: one row per (profile, subculture); the columns are field ids.
BASE_SQL = """
WITH contexts AS (
  SELECT al.profile_unit_key AS profile_key, a.subculture_key AS subculture_key,
         MIN(a.faction_key) AS faction_key, MIN(a.faction_name) AS faction_name,
         MIN(a.roster_scope) AS roster_scope, MIN(a.is_faction_exclusive) AS is_faction_exclusive,
         json_group_array(a.unit_key) AS source_keys_json,
         json_group_array(a.record_id) AS availability_json
  FROM unit_aliases al JOIN unit_availability a ON a.unit_key = al.unit_key
  GROUP BY al.profile_unit_key, a.subculture_key
), u AS (
  SELECT c.profile_key AS profile_unit_key, c.subculture_key AS subculture, c.faction_key AS faction,
         c.faction_name AS faction_name, c.roster_scope AS roster_scope,
         c.is_faction_exclusive AS faction_exclusive,
         c.source_keys_json, c.availability_json, p.record_id AS profile_record,
         p.unit_name AS name, p.source_unit_name AS source_name,
         COALESCE(mv.base_unit_key, p.unit_key) AS family_key,
         CASE WHEN mv.base_unit_key IS NOT NULL THEN 'mounted_variant'
              WHEN EXISTS (SELECT 1 FROM unit_mount_variants b WHERE b.base_unit_key = p.unit_key) THEN 'base_with_mounted_variants'
              ELSE 'no_mount_relation' END AS mount_relation,
         CASE WHEN p.source_mount_entity_key IS NOT NULL AND p.source_engine_entity_key IS NOT NULL THEN 'mount_and_engine'
              WHEN p.source_mount_entity_key IS NOT NULL THEN 'mount'
              WHEN p.source_engine_entity_key IS NOT NULL THEN 'engine'
              ELSE 'none' END AS mount_body,
         p.*
  FROM contexts c JOIN unit_profiles p ON p.unit_key = c.profile_key
  LEFT JOIN unit_mount_variants mv ON mv.mounted_unit_key = p.unit_key
)
"""


def _f(column, kind, label, *, dim=None, unit=None, scope='unit', desc=None, source=None, values=None):
    return {'column': column, 'type': kind, 'label': label, 'dimension': dim, 'unit': unit,
            'scope': scope, 'description': desc, 'source': source or 'unit_profiles.' + column,
            'values_sql': values}


_CAT = 'category'
_NUM = 'number'
_BOOL = 'boolean'
FIELDS = {
    # identity and roster
    'name': _f('name', 'text', 'Display name', source='unit_profiles.unit_name',
               desc='Imported display name. 104 profiles carry unresolved {{tr:...}} source placeholders; search unit_key as well.'),
    'unit_key': _f('profile_unit_key', 'text', 'Canonical profile key', source='unit_profiles.unit_key'),
    'subculture': _f('subculture', _CAT, 'Represented subculture (roster)', source='unit_availability.subculture_key',
                     desc='Roster membership through unit_availability; values are subculture keys labeled with their faction names.'),
    'faction': _f('faction', _CAT, 'Roster faction key', source='unit_availability.faction_key'),
    'roster_scope': _f('roster_scope', _CAT, 'Roster scope', source='unit_availability.roster_scope',
                       desc='CTW-data roster scope (race_core, race_core_and_variant, faction_exclusive, shared_variant).'),
    'faction_exclusive': _f('faction_exclusive', _BOOL, 'Faction-exclusive roster entry', source='unit_availability.is_faction_exclusive'),
    'caste': _f('source_caste', _CAT, 'Caste (lord, hero, unit castes)', source='unit_profiles.source_caste',
                desc='Native caste. Lord and hero are the supported character classifications; legendary versus generic characters is not represented.'),
    'unit_type': _f('tactical_category', _CAT, 'Unit type', source='unit_profiles.tactical_category',
                    desc='CTW-data tactical category: character, infantry, cavalry, monster, artillery.'),
    'unit_class': _f('source_unit_class', _CAT, 'Native unit class', source='unit_profiles.source_unit_class'),
    'target_size': _f('primary_target_size', _CAT, 'Primary body size', source='unit_profiles.primary_target_size'),
    'weight': _f('weight', _CAT, 'Weight class'),
    'primary_body': _f('primary_component_role', _CAT, 'Primary health body (man, mount, engine)', source='unit_profiles.primary_component_role'),
    'mount_relation': _f('mount_relation', _CAT, 'Mount-variant relation', source='unit_mount_variants',
                         desc='mounted_variant, base_with_mounted_variants or no_mount_relation, from the character mount table.'),
    'mount_body': _f('mount_body', _CAT, 'Mount or engine body present', source='unit_profiles.source_mount_entity_key, source_engine_entity_key',
                     desc='none, mount, engine or mount_and_engine. A profile can ride a mount without a mount-variant relation (for example a character only fielded mounted).'),
    'is_large': _f('is_large', _BOOL, 'Normalized large flag'),
    'is_single_entity': _f('is_single_entity', _BOOL, 'Single entity'),
    'is_renown': _f('is_renown', _BOOL, 'Regiment of Renown'),
    'in_encyclopedia': _f('in_encyclopedia', _BOOL, 'Listed in encyclopedia'),
    'has_missile_weapon': _f('has_missile_weapon', _BOOL, 'Has a primary missile weapon'),
    'attributes': _f(None, 'set', 'Unit attributes', source='unit_attributes.attribute_key',
                     desc='Multivalued. contains/not_contains test one attribute key; any_of tests membership of at least one.'),
    # cost
    'multiplayer_cost': _f('multiplayer_cost', _NUM, 'Custom-battle cost', dim='gold', unit='gold',
                           desc='Native value. 23 profiles have 0 or negative values (for example The Blue Scribes, -700); these are values, not nulls.'),
    'campaign_recruit_cost': _f('campaign_recruit_cost', _NUM, 'Campaign recruitment cost', dim='gold', unit='gold'),
    'campaign_upkeep': _f('campaign_upkeep', _NUM, 'Campaign upkeep', dim='gold', unit='gold'),
    'tier': _f('tier', _NUM, 'Tier', dim='tier', unit='tier'),
    # body
    'entity_count': _f('entity_count', _NUM, 'Entities', dim='entities', unit='entities'),
    'hp_per_entity': _f('hp_per_entity', _NUM, 'Hit points per entity', dim='hp', unit='hp'),
    'total_hp': _f('total_hp', _NUM, 'Unit hit points', dim='hp', unit='hp'),
    'barrier_health': _f('barrier_health', _NUM, 'Barrier', dim='hp', unit='hp'),
    'leadership': _f('leadership', _NUM, 'Leadership', dim='leadership', unit='points'),
    'speed': _f('speed', _NUM, 'Speed', dim='speed', unit='native run speed',
                desc=('Normalized primary-body run speed, as in get_unit_combat_profile movement.speed (range 0 to 11.6). '
                      'No conversion to the in-game displayed speed scale is established or applied.')),
    'mass': _f('mass', _NUM, 'Mass', dim='mass', unit='native mass'),
    # protection
    'armour': _f('armour', _NUM, 'Armour', dim='armour', unit='points'),
    'shield_block_chance': _f('shield_block_chance', _NUM, 'Missile block chance', dim='percent', unit='percent'),
    'physical_resistance': _f('physical_resistance', _NUM, 'Physical resistance', dim='percent', unit='percent'),
    'missile_resistance': _f('missile_resistance', _NUM, 'Missile resistance', dim='percent', unit='percent'),
    'spell_resistance': _f('spell_resistance', _NUM, 'Spell resistance', dim='percent', unit='percent'),
    'fire_resistance': _f('fire_resistance', _NUM, 'Fire resistance', dim='percent', unit='percent'),
    'ward_save': _f('ward_save', _NUM, 'Ward save', dim='percent', unit='percent'),
    # melee (unit skill plus primary melee weapon)
    'melee_attack': _f('melee_attack', _NUM, 'Melee attack', dim='melee_skill', unit='points'),
    'melee_defence': _f('melee_defence', _NUM, 'Melee defence', dim='melee_skill', unit='points'),
    'charge_bonus': _f('charge_bonus', _NUM, 'Charge bonus', dim='charge_bonus', unit='points'),
    'primary_melee_base_damage': _f('weapon_base_damage', _NUM, 'Primary melee base damage', dim='damage', unit='damage per hit', scope='primary_melee_weapon', desc=PRIMARY_MELEE),
    'primary_melee_ap_damage': _f('weapon_ap_damage', _NUM, 'Primary melee armour-piercing damage', dim='damage', unit='damage per hit', scope='primary_melee_weapon', desc=PRIMARY_MELEE),
    'primary_melee_bonus_vs_infantry': _f('bonus_vs_infantry', _NUM, 'Primary melee bonus vs infantry', dim='bonus', unit='points', scope='primary_melee_weapon', desc=PRIMARY_MELEE),
    'primary_melee_bonus_vs_large': _f('bonus_vs_large', _NUM, 'Primary melee bonus vs large', dim='bonus', unit='points', scope='primary_melee_weapon', desc=PRIMARY_MELEE),
    'primary_melee_attack_interval': _f('attack_interval', _NUM, 'Primary melee attack interval', dim='seconds', unit='seconds', scope='primary_melee_weapon', desc=PRIMARY_MELEE),
    'primary_melee_max_splash_targets': _f('max_splash_targets', _NUM, 'Primary melee splash targets', dim='targets', unit='targets', scope='primary_melee_weapon', desc=PRIMARY_MELEE),
    'primary_melee_is_magical': _f('melee_is_magical', _BOOL, 'Primary melee magical', scope='primary_melee_weapon', desc=PRIMARY_MELEE),
    'primary_melee_is_flaming': _f('melee_is_flaming', _BOOL, 'Primary melee flaming', scope='primary_melee_weapon', desc=PRIMARY_MELEE),
    # primary missile
    'primary_missile_base_damage': _f('missile_base_damage', _NUM, 'Primary missile base damage', dim='damage', unit='damage per projectile', scope='primary_missile_attack', desc=PRIMARY_MISSILE),
    'primary_missile_ap_damage': _f('missile_ap_damage', _NUM, 'Primary missile armour-piercing damage', dim='damage', unit='damage per projectile', scope='primary_missile_attack', desc=PRIMARY_MISSILE),
    'primary_missile_bonus_vs_infantry': _f('missile_bonus_vs_infantry', _NUM, 'Primary missile bonus vs infantry', dim='bonus', unit='points', scope='primary_missile_attack', desc=PRIMARY_MISSILE),
    'primary_missile_bonus_vs_large': _f('missile_bonus_vs_large', _NUM, 'Primary missile bonus vs large', dim='bonus', unit='points', scope='primary_missile_attack', desc=PRIMARY_MISSILE),
    'primary_missile_range': _f('range', _NUM, 'Primary missile range', dim='metres', unit='metres', scope='primary_missile_attack', desc=PRIMARY_MISSILE),
    'primary_missile_reload_time': _f('reload_time', _NUM, 'Primary missile base reload time', dim='seconds', unit='seconds', scope='primary_missile_attack', desc=PRIMARY_MISSILE),
    'primary_missile_ammunition': _f('ammunition', _NUM, 'Primary missile ammunition', dim='ammunition', unit='shots', scope='primary_missile_attack', desc=PRIMARY_MISSILE),
    'primary_missile_accuracy': _f('accuracy', _NUM, 'Accuracy', dim='accuracy', unit='points', scope='primary_missile_attack', desc=PRIMARY_MISSILE),
    'primary_missile_projectiles_per_shot': _f('projectiles_per_shot', _NUM, 'Projectiles per shot', dim='projectiles', unit='projectiles', scope='primary_missile_attack', desc=PRIMARY_MISSILE),
    'primary_missile_shots_per_volley': _f('shots_per_volley', _NUM, 'Shots per volley', dim='projectiles', unit='shots', scope='primary_missile_attack', desc=PRIMARY_MISSILE),
    'primary_missile_burst_size': _f('burst_size', _NUM, 'Burst size', dim='projectiles', unit='shots', scope='primary_missile_attack', desc=PRIMARY_MISSILE),
    'primary_missile_velocity': _f('projectile_velocity', _NUM, 'Projectile muzzle velocity', dim='velocity', unit='native velocity', scope='primary_missile_attack', desc=PRIMARY_MISSILE),
    'primary_missile_is_magical': _f('missile_is_magical', _BOOL, 'Primary missile magical', scope='primary_missile_attack', desc=PRIMARY_MISSILE),
    'primary_missile_is_flaming': _f('missile_is_flaming', _BOOL, 'Primary missile flaming', scope='primary_missile_attack', desc=PRIMARY_MISSILE),
    'primary_missile_shot_type': _f('projectile_shot_type', _CAT, 'Projectile shot type', scope='primary_missile_attack', desc=PRIMARY_MISSILE),
    'primary_explosion_base_damage': _f('explosion_base_damage', _NUM, 'Explosion base damage', dim='damage', unit='damage per entity hit', scope='primary_missile_explosion', desc=PRIMARY_EXPLOSION),
    'primary_explosion_ap_damage': _f('explosion_ap_damage', _NUM, 'Explosion armour-piercing damage', dim='damage', unit='damage per entity hit', scope='primary_missile_explosion', desc=PRIMARY_EXPLOSION),
    'primary_explosion_radius': _f('explosion_radius', _NUM, 'Explosion radius', dim='metres', unit='metres', scope='primary_missile_explosion', desc=PRIMARY_EXPLOSION),
}
# Plain terms that name several fields; callers must choose one explicitly.
AMBIGUOUS = {
    'cost': ('multiplayer_cost', 'campaign_recruit_cost', 'campaign_upkeep'),
    'price': ('multiplayer_cost', 'campaign_recruit_cost'),
    'damage': ('primary_melee_base_damage', 'primary_missile_base_damage', 'primary_explosion_base_damage'),
    'base_damage': ('primary_melee_base_damage', 'primary_missile_base_damage', 'primary_explosion_base_damage'),
    'ap_damage': ('primary_melee_ap_damage', 'primary_missile_ap_damage', 'primary_explosion_ap_damage'),
    'armour_piercing_damage': ('primary_melee_ap_damage', 'primary_missile_ap_damage', 'primary_explosion_ap_damage'),
    'weapon_damage': ('primary_melee_base_damage', 'primary_melee_ap_damage', 'primary_missile_base_damage', 'primary_missile_ap_damage'),
    'bonus_vs_large': ('primary_melee_bonus_vs_large', 'primary_missile_bonus_vs_large'),
    'bonus_vs_infantry': ('primary_melee_bonus_vs_infantry', 'primary_missile_bonus_vs_infantry'),
    'hp': ('hp_per_entity', 'total_hp'), 'health': ('hp_per_entity', 'total_hp', 'barrier_health'),
    'resistance': ('physical_resistance', 'missile_resistance', 'spell_resistance', 'fire_resistance', 'ward_save'),
    'range': ('primary_missile_range',), 'ammunition': ('primary_missile_ammunition',),
    'attack': ('melee_attack',), 'defence': ('melee_defence',), 'faction_key': ('faction',), 'subculture_key': ('subculture',),
    'race': ('subculture',), 'category': ('unit_type', 'unit_class', 'caste'),
}
UNSUPPORTED_CLASSIFICATIONS = [
    {'term': 'legendary_lord / legendary_hero', 'status': 'not_represented',
     'detail': 'The snapshot does not import agent subtype or legendary flags. Lord and hero come from caste; legendary status is never inferred from names.'},
    {'term': 'spellcaster / lore of magic', 'status': 'not_in_unit_search',
     'detail': 'Spell and ability access is retrieved with resolve_effect/get_effect (#19), not unit search.'},
    {'term': 'abilities / passives as search fields', 'status': 'not_in_unit_search',
     'detail': 'Inspect a result with get_unit_combat_profile section=abilities or activated_options.'},
]
OPERATORS = {
    _NUM: ('=', '!=', '>', '>=', '<', '<=', 'between', 'in', 'not_in', 'is_null', 'is_not_null'),
    _CAT: ('=', '!=', 'in', 'not_in', 'is_null', 'is_not_null'),
    _BOOL: ('=', '!=', 'is_null', 'is_not_null'),
    'text': ('=', 'contains'),
    'set': ('contains', 'not_contains', 'any_of'),
}
COMPARISONS = ('=', '!=', '>', '>=', '<', '<=')
DEFAULT_FIELDS = ('caste', 'unit_type', 'mount_relation')


class SearchError(ValueError):
    """Actionable query diagnostic (unknown field, operator, stale cursor, bounds)."""
    def __init__(self, code, message, **detail):
        self.code = code
        self.detail = {'code': code, 'message': message, **detail}
        super().__init__(f'{code}: {message}')


def _field(name, path):
    if not isinstance(name, str) or not name:
        raise SearchError('invalid_field', f'{path} must be a field id string')
    if name in FIELDS:
        return FIELDS[name]
    if name in AMBIGUOUS:
        choices = AMBIGUOUS[name]
        raise SearchError('ambiguous_field', f'{path}: "{name}" is ambiguous or not a field id; choose one explicitly',
                          field=name, candidates=list(choices))
    raise SearchError('unknown_field', f'{path}: unknown field "{name}"', field=name,
                      suggestions=difflib.get_close_matches(name, list(FIELDS), n=5, cutoff=0.5),
                      hint='Call discover_unit_fields for supported fields.')


class UnitSearch:
    def __init__(self, queries):
        self.q = queries
        self.db = queries.db
        self._categories = {}
        self._nulls = None

    # ---------- discovery ----------
    def categories(self, name):
        if name not in self._categories:
            spec = FIELDS[name]
            if name == 'attributes':
                rows = self.db.execute(
                    'SELECT attribute_key, COUNT(DISTINCT unit_key) FROM unit_attributes GROUP BY 1 ORDER BY 1').fetchall()
                values = []
                for key, count in rows:
                    text = self.db.execute('SELECT text FROM localization WHERE key=?',
                                           ('unit_attributes_bullet_text_' + key,)).fetchone()
                    values.append({'value': key, 'label': text[0].split('||')[0] if text else None,
                                   'profile_count': count})
            elif name in ('subculture', 'faction'):
                rows = self.db.execute(
                    BASE_SQL + f'SELECT {spec["column"]}, group_concat(DISTINCT faction_name), COUNT(*) FROM u '
                    'GROUP BY 1 ORDER BY 1').fetchall()
                values = [{'value': v, 'label': label, 'row_count': n} for v, label, n in rows]
            else:
                rows = self.db.execute(BASE_SQL + f'SELECT "{spec["column"]}", COUNT(*) FROM u GROUP BY 1 ORDER BY 1').fetchall()
                values = [{'value': v, 'row_count': n} for v, n in rows]
            self._categories[name] = values
        return self._categories[name]

    def describe(self, name, spec, inline=True):
        out = {'id': name, 'label': spec['label'], 'type': spec['type'], 'operators': list(OPERATORS[spec['type']]),
               'scope': spec['scope'], 'source': spec['source'], 'sortable': spec['type'] in (_NUM, _CAT, _BOOL, 'text'),
               'filterable': True, 'output': spec['type'] != 'set'}
        if spec['type'] == _NUM:
            out.update(unit=spec['unit'], dimension=spec['dimension'], field_comparison=True,
                       comparable_with=sorted(k for k, s in FIELDS.items() if s['type'] == _NUM and
                                              s['dimension'] == spec['dimension'] and k != name))
        if spec['type'] in (_CAT, 'set') and inline:
            values = self.categories(name)
            if len(values) <= INLINE_CATEGORIES:
                out['categories'] = values
            else:
                out['categories'] = {'count': len(values), 'page_with': {'discover_unit_fields': {'field': name}}}
        if spec['type'] == _BOOL:
            out['values'] = [True, False]
        if spec['description']:
            out['description'] = spec['description']
        if spec['column'] and spec['type'] != 'text':
            if self._nulls is None:
                columns = [s['column'] for s in FIELDS.values() if s['column'] and s['type'] != 'text']
                row = self.db.execute(BASE_SQL + 'SELECT ' + ', '.join(f'COUNT(*) - COUNT("{c}")' for c in columns) + ' FROM u').fetchone()
                self._nulls = dict(zip(columns, row))
            out['null_rows'] = self._nulls[spec['column']]
        return out

    def discover(self, field=None, *, cursor=None, limit=CATEGORY_PAGE):
        if type(limit) is not int or not 1 <= limit <= 256:
            raise SearchError('invalid_limit', 'limit must be an integer from 1 to 256')
        head = {'search_version': SEARCH_VERSION, 'packet_version': PACKET_VERSION,
                'snapshot': self._snapshot()}
        if field is None:
            if cursor is not None:
                raise SearchError('invalid_cursor', 'a cursor pages one field\'s categories; pass field too')
            return {**head, 'row_definition': ROW_DEFINITION, 'family_definition': FAMILY_DEFINITION,
                    'baseline_semantics': BASELINE_NOTE, 'coverage': COVERAGE,
                    'fields': [self.describe(k, s) for k, s in FIELDS.items()],
                    'ambiguous_terms': {k: list(v) for k, v in AMBIGUOUS.items()},
                    'unsupported_classifications': UNSUPPORTED_CLASSIFICATIONS,
                    'query_grammar': {
                        'condition': {'field': 'field id', 'op': 'operator', 'value': 'literal; list for in/not_in/any_of; [low, high] inclusive for between; omitted for is_null/is_not_null'},
                        'field_comparison': {'field': 'numeric field id', 'op': list(COMPARISONS), 'other_field': 'numeric field with the same dimension'},
                        'groups': {'all': '[conditions or groups] (AND)', 'any': '[conditions or groups] (OR)'},
                        'precedence': 'Grouping is explicit; there is no implicit precedence. A bare list is not accepted.',
                        'null_semantics': ('Ordinary predicates never match a null value: missing is not zero. != and not_in also exclude nulls; '
                                           'use is_null/is_not_null explicitly. There is no generic NOT operator.'),
                        'sort': '[{"field": id, "direction": "asc"|"desc"}], at most 3; nulls sort last in either direction; ties break on unit_key then subculture.',
                        'group_by': ['variant', 'mount_family'],
                        'limits': {'conditions': MAX_CONDITIONS, 'depth': MAX_DEPTH, 'list_values': MAX_LIST_VALUES,
                                   'fields': MAX_FIELDS, 'sort': MAX_SORT, 'limit': MAX_LIMIT}},
                    'examples': EXAMPLES}
        spec = _field(field, 'field')
        result = {**head, 'field': self.describe(field, spec, inline=False)}
        if spec['type'] in (_CAT, 'set'):
            values = self.categories(field)
            offset = 0
            if cursor is not None:
                data = self._decode(cursor, {'kind': 'categories', 'field': field})
                offset = data['offset']
                if offset >= len(values):
                    raise SearchError('invalid_cursor', 'cursor offset is outside the category list')
            page = values[offset:offset + limit]
            more = offset + len(page) < len(values)
            result['categories'] = {'values': page, 'total': len(values), 'offset': offset, 'returned': len(page),
                                    'complete': not more,
                                    'next_cursor': self._encode({'kind': 'categories', 'field': field}, offset + len(page)) if more else None}
        return result

    # ---------- query compilation ----------
    def _compile(self, node, path, counter, depth):
        if not isinstance(node, dict):
            raise SearchError('invalid_where', f'{path} must be an object (condition or all/any group)')
        if depth > MAX_DEPTH:
            raise SearchError('query_too_deep', f'{path}: nesting exceeds {MAX_DEPTH} levels')
        groups = [k for k in ('all', 'any') if k in node]
        if groups:
            if len(node) != 1:
                raise SearchError('invalid_where', f'{path}: a group has exactly one key, all or any')
            key = groups[0]
            items = node[key]
            if not isinstance(items, list) or not items:
                raise SearchError('invalid_where', f'{path}.{key} must be a nonempty list')
            parts, params, normalized = [], [], []
            for i, item in enumerate(items):
                sql, p, n = self._compile(item, f'{path}.{key}[{i}]', counter, depth + 1)
                parts.append(sql); params += p; normalized.append(n)
            joiner = ' AND ' if key == 'all' else ' OR '
            return '(' + joiner.join(parts) + ')', params, {key: normalized}
        counter[0] += 1
        if counter[0] > MAX_CONDITIONS:
            raise SearchError('too_many_conditions', f'at most {MAX_CONDITIONS} conditions per query')
        extra = set(node) - {'field', 'op', 'value', 'other_field'}
        if extra:
            raise SearchError('invalid_condition', f'{path}: unsupported keys {sorted(extra)}')
        name = node.get('field')
        spec = _field(name, path + '.field')
        op = node.get('op')
        kind = spec['type']
        if op not in OPERATORS[kind] and not ('other_field' in node and op in COMPARISONS):
            raise SearchError('unsupported_operator', f'{path}: operator {op!r} is not supported for {kind} field {name}',
                              field=name, supported=list(OPERATORS[kind]))
        col = f'u."{spec["column"]}"' if spec['column'] else None
        if 'other_field' in node:
            if 'value' in node:
                raise SearchError('invalid_condition', f'{path}: give value or other_field, not both')
            other = _field(node['other_field'], path + '.other_field')
            if kind != _NUM or other['type'] != _NUM or op not in COMPARISONS:
                raise SearchError('incompatible_comparison', f'{path}: field-to-field comparison needs two numeric fields and one of {list(COMPARISONS)}')
            if spec['dimension'] != other['dimension']:
                raise SearchError('incompatible_units', f'{path}: {name} ({spec["unit"]}, {spec["dimension"]}) cannot be compared with '
                                  f'{node["other_field"]} ({other["unit"]}, {other["dimension"]})',
                                  comparable_with=self.describe(name, spec)['comparable_with'])
            return f'({col} {op} u."{other["column"]}")', [], dict(node)
        if op in ('is_null', 'is_not_null'):
            if 'value' in node:
                raise SearchError('invalid_condition', f'{path}: {op} takes no value')
            return f'({col} IS {"" if op == "is_null" else "NOT "}NULL)', [], {'field': name, 'op': op}
        if 'value' not in node:
            raise SearchError('missing_value', f'{path}: operator {op} needs a value')
        value = node['value']
        if op in ('in', 'not_in', 'any_of', 'between'):
            if not isinstance(value, list) or not value or len(value) > MAX_LIST_VALUES or (op == 'between' and len(value) != 2):
                raise SearchError('invalid_value', f'{path}: {op} needs ' + ('[low, high]' if op == 'between' else f'a list of 1 to {MAX_LIST_VALUES} values'))
            values = [self._literal(v, name, spec, path) for v in value]
        else:
            values = [self._literal(value, name, spec, path)]
        normalized = {'field': name, 'op': op, 'value': values if isinstance(value, list) else values[0]}
        if kind == 'set':
            exists = 'EXISTS (SELECT 1 FROM unit_attributes ua WHERE ua.unit_key = u.profile_unit_key AND ua.attribute_key {})'
            if op == 'any_of':
                return '(' + exists.format('IN (' + ','.join('?' * len(values)) + ')') + ')', values, normalized
            sql = exists.format('= ?')
            return ('(' + sql + ')' if op == 'contains' else '(NOT ' + sql + ')'), values, normalized
        if kind == 'text':
            if op == '=':
                return f'({col} = ? COLLATE NOCASE)', values, normalized
            pattern = '%' + values[0].replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_') + '%'
            if name == 'name':
                return "(u.name LIKE ? ESCAPE '\\' OR u.source_name LIKE ? ESCAPE '\\')", [pattern, pattern], normalized
            return f"({col} LIKE ? ESCAPE '\\')", [pattern], normalized
        if op == 'between':
            if values[0] > values[1]:
                raise SearchError('invalid_value', f'{path}: between needs low <= high')
            return f'({col} BETWEEN ? AND ?)', values, normalized
        if op in ('in', 'not_in'):
            return f'({col} {"NOT " if op == "not_in" else ""}IN ({",".join("?" * len(values))}))', values, normalized
        return f'({col} {op} ?)', values, normalized

    def _literal(self, value, name, spec, path):
        kind = spec['type']
        if kind == _NUM:
            if type(value) not in (int, float) or value != value or value in (float('inf'), float('-inf')):
                raise SearchError('invalid_value', f'{path}: {name} needs a finite number', field=name)
            return value
        if kind == _BOOL:
            if type(value) is not bool:
                raise SearchError('invalid_value', f'{path}: {name} needs true or false', field=name)
            return int(value)
        if not isinstance(value, str) or not value.strip() or len(value) > 200:
            raise SearchError('invalid_value', f'{path}: {name} needs a nonempty string of at most 200 characters', field=name)
        if kind in (_CAT, 'set'):
            known = {c['value'] for c in self.categories(name)}
            if value not in known:
                raise SearchError('unknown_category', f'{path}: {value!r} is not a {name} value in this snapshot', field=name,
                                  suggestions=difflib.get_close_matches(value, sorted(v for v in known if v), n=5, cutoff=0.4),
                                  hint=f'discover_unit_fields(field="{name}") lists values.')
        return value

    # ---------- search ----------
    def search(self, where=None, *, fields=None, sort=None, group_by='variant', limit=DEFAULT_LIMIT, cursor=None):
        if group_by not in ('variant', 'mount_family'):
            raise SearchError('invalid_group_by', 'group_by must be variant or mount_family')
        if type(limit) is not int or not 1 <= limit <= MAX_LIMIT:
            raise SearchError('invalid_limit', f'limit must be an integer from 1 to {MAX_LIMIT}')
        fields = list(DEFAULT_FIELDS) if fields is None else fields
        if not isinstance(fields, list) or len(fields) > MAX_FIELDS or len(set(map(str, fields))) != len(fields):
            raise SearchError('invalid_fields', f'fields must be a list of at most {MAX_FIELDS} distinct field ids')
        for i, name in enumerate(fields):
            if _field(name, f'fields[{i}]')['type'] == 'set':
                raise SearchError('invalid_fields', f'fields[{i}]: {name} is filter-only; inspect attributes with get_unit_combat_profile')
        sort = [] if sort is None else sort
        if not isinstance(sort, list) or len(sort) > MAX_SORT:
            raise SearchError('invalid_sort', f'sort must be a list of at most {MAX_SORT} keys')
        order, sort_norm = [], []
        for i, item in enumerate(sort):
            if not isinstance(item, dict) or set(item) - {'field', 'direction'} or 'field' not in item:
                raise SearchError('invalid_sort', f'sort[{i}] must be {{"field": id, "direction": "asc"|"desc"}}')
            spec = _field(item['field'], f'sort[{i}].field')
            direction = item.get('direction', 'asc')
            if direction not in ('asc', 'desc') or spec['type'] == 'set':
                raise SearchError('invalid_sort', f'sort[{i}]: direction must be asc or desc on a sortable field')
            col = f'u."{spec["column"]}"'
            order.append(f'({col} IS NULL), {col} {direction.upper()}')
            sort_norm.append({'field': item['field'], 'direction': direction})
        order.append('u.profile_unit_key, u.subculture')
        if where is None:
            clause, params, where_norm = '1', [], None
        else:
            clause, params, where_norm = self._compile(where, 'where', [0], 1)
        interpreted = {'where': where_norm, 'fields': fields, 'sort': sort_norm, 'group_by': group_by,
                       'tie_breaker': ['unit_key', 'subculture'], 'limit': limit}
        query_id = hashlib.sha256(compact({k: v for k, v in interpreted.items() if k != 'limit'}).encode()).hexdigest()[:24]
        offset = 0
        if cursor is not None:
            offset = self._decode(cursor, {'kind': 'search', 'query': query_id})['offset']
        sql = BASE_SQL + f'SELECT u.profile_unit_key, u.subculture, u.family_key FROM u WHERE {clause} ORDER BY {", ".join(order)}'
        matches = self._run(sql, params)
        variant_total = len(matches)
        if group_by == 'variant':
            total = variant_total
            if offset and offset >= total:
                raise SearchError('invalid_cursor', 'cursor offset is outside the result set')
            page_keys = matches[offset:offset + limit]
            items = self._rows(page_keys, fields)
            results = [items[(k[0], k[1])] for k in page_keys]
        else:
            families, order_keys = {}, []
            for key in matches:
                fam = (key[2], key[1])
                if fam not in families:
                    families[fam] = []; order_keys.append(fam)
                families[fam].append(key)
            total = len(order_keys)
            if offset and offset >= total:
                raise SearchError('invalid_cursor', 'cursor offset is outside the result set')
            page_fams = order_keys[offset:offset + limit]
            items = self._rows([k for fam in page_fams for k in families[fam]], fields)
            results = []
            for family_key, subculture in page_fams:
                members = self._run(BASE_SQL + 'SELECT u.profile_unit_key FROM u WHERE u.family_key=? AND u.subculture=? ORDER BY 1',
                                    [family_key, subculture])
                base = self.db.execute('SELECT unit_name FROM unit_profiles WHERE unit_key=?', (family_key,)).fetchone()
                matched = [{k: v for k, v in items[(m[0], m[1])].items() if k not in ('subculture', 'family_key')}
                           for m in families[(family_key, subculture)]]
                results.append({'family_key': family_key, 'subculture': subculture,
                                'name': base[0] if base else None,
                                'matched_variant_count': len(matched), 'family_variant_count': len(members),
                                'unmatched_variant_keys': sorted({m[0] for m in members} - {k[0] for k in families[(family_key, subculture)]}),
                                'variants': matched})
        returned = len(results)
        more = offset + returned < total
        return {'search_version': SEARCH_VERSION, 'packet_version': PACKET_VERSION, 'snapshot': self._snapshot(),
                'baseline': json.loads(self.q.snapshot['baseline_json']), 'baseline_semantics': BASELINE_NOTE,
                'interpreted_query': interpreted,
                'count_unit': 'mount_family' if group_by == 'mount_family' else 'qualified_variant',
                'row_definition': ROW_DEFINITION if group_by == 'variant' else FAMILY_DEFINITION,
                'total': total, 'matched_variants': variant_total, 'offset': offset, 'returned': returned,
                'complete': not more,
                'next_cursor': self._encode({'kind': 'search', 'query': query_id}, offset + returned) if more else None,
                'coverage': COVERAGE, 'follow_up': FOLLOW_UP, 'results': results}

    def _rows(self, keys, fields):
        if not keys:
            return {}
        cols = ', '.join(f'u."{FIELDS[f]["column"]}" AS "f:{f}"' for f in fields)
        pairs = ' OR '.join('(u.profile_unit_key=? AND u.subculture=?)' for _ in keys)
        params = [v for k in keys for v in (k[0], k[1])]
        rows = self._run(BASE_SQL + f'SELECT u.profile_unit_key, u.subculture, u.name, u.family_key, u.mount_relation, '
                         f'u.source_keys_json, u.availability_json, u.profile_record{", " + cols if cols else ""} '
                         f'FROM u WHERE {pairs}', params, rows=True)
        out = {}
        for r in rows:
            keys_in_context = sorted(set(json.loads(r['source_keys_json'])))
            unit_key = r['profile_unit_key'] if r['profile_unit_key'] in keys_in_context else keys_in_context[0]
            values = {}
            for f in fields:
                v = r['f:' + f]
                values[f] = bool(v) if FIELDS[f]['type'] == _BOOL and v is not None else v
            item = {'unit_key': unit_key, 'subculture': r['subculture'], 'name': r['name']}
            if '{{tr:' in r['name']:
                item['name_status'] = 'source_placeholder'
            if r['profile_unit_key'] != unit_key:
                item['profile_unit_key'] = r['profile_unit_key']
            if len(keys_in_context) > 1:
                item['source_unit_keys'] = keys_in_context
            item.update(family_key=r['family_key'], mount_relation=r['mount_relation'], values=values,
                        provenance_refs=sorted({r['profile_record'], *json.loads(r['availability_json'])}))
            out[(r['profile_unit_key'], r['subculture'])] = item
        return out

    def _run(self, sql, params, rows=False):
        ticks = [0]

        def budget():
            ticks[0] += 1
            return 1 if ticks[0] * 1000 > MAX_VM_STEPS else 0
        self.db.set_progress_handler(budget, 1000)
        try:
            result = self.db.execute(sql, params).fetchall()
        except sqlite3.OperationalError as exc:
            if 'interrupt' in str(exc):
                raise SearchError('query_budget_exceeded', 'query exceeded the execution budget; narrow it') from exc
            raise
        finally:
            self.db.set_progress_handler(None, 0)
        return result if rows else [tuple(r) for r in result]

    # ---------- cursors ----------
    def _snapshot(self):
        s = self.q.snapshot
        return {'id': s['id'], 'source_commit': s['source_commit'], 'contract_sha256': s['contract_sha256'],
                'schema_version': s['schema_version']}

    def _encode(self, scope, offset):
        data = {'v': SEARCH_VERSION, 'snapshot': self.q.snapshot['id'], **scope, 'offset': offset}
        raw = compact(data).encode()
        return base64.urlsafe_b64encode(raw).decode().rstrip('=') + '.' + hashlib.sha256(raw).hexdigest()[:16]

    def _decode(self, token, scope):
        try:
            if not isinstance(token, str) or len(token) > 1024:
                raise ValueError
            encoded, digest = token.split('.')
            raw = base64.urlsafe_b64decode(encoded + '=' * (-len(encoded) % 4))
            if hashlib.sha256(raw).hexdigest()[:16] != digest:
                raise ValueError
            data = json.loads(raw)
        except (ValueError, TypeError):
            raise SearchError('invalid_cursor', 'cursor is malformed or altered; rerun the query without a cursor') from None
        if data.get('snapshot') != self.q.snapshot['id'] or data.get('v') != SEARCH_VERSION:
            raise SearchError('stale_cursor', 'cursor belongs to a different snapshot or search version; rerun the query without a cursor')
        if any(data.get(k) != v for k, v in scope.items()):
            raise SearchError('cursor_query_mismatch', 'cursor belongs to a different query; resend the original where/fields/sort/group_by with it')
        if type(data.get('offset')) is not int or data['offset'] < 1:
            raise SearchError('invalid_cursor', 'cursor offset is invalid')
        return data


EXAMPLES = [
    {'question': 'All High Elf lords and heroes, grouped by mount family',
     'search_units': {'where': {'all': [{'field': 'subculture', 'op': '=', 'value': 'wh2_main_sc_hef_high_elves'},
                                        {'field': 'caste', 'op': 'in', 'value': ['lord', 'hero']}]},
                      'group_by': 'mount_family', 'fields': ['caste', 'mount_body', 'multiplayer_cost']}},
    {'question': 'High Elf heroes with melee attack above 60',
     'search_units': {'where': {'all': [{'field': 'subculture', 'op': '=', 'value': 'wh2_main_sc_hef_high_elves'},
                                        {'field': 'caste', 'op': '=', 'value': 'hero'},
                                        {'field': 'melee_attack', 'op': '>', 'value': 60}]},
                      'fields': ['melee_attack'], 'sort': [{'field': 'melee_attack', 'direction': 'desc'}]}},
    {'question': 'Infantry with armour below 40 and speed above 4 (native run speed, not the displayed scale)',
     'search_units': {'where': {'all': [{'field': 'unit_type', 'op': '=', 'value': 'infantry'},
                                        {'field': 'armour', 'op': '<', 'value': 40},
                                        {'field': 'speed', 'op': '>', 'value': 4}]}, 'fields': ['armour', 'speed']}},
    {'question': 'Units costing at most 1,000 in custom battle, by primary melee armour-piercing damage',
     'search_units': {'where': {'field': 'multiplayer_cost', 'op': '<=', 'value': 1000},
                      'fields': ['multiplayer_cost', 'primary_melee_ap_damage'],
                      'sort': [{'field': 'primary_melee_ap_damage', 'direction': 'desc'}]}},
    {'question': 'Mounted lords whose melee defence exceeds melee attack',
     'search_units': {'where': {'all': [{'field': 'caste', 'op': '=', 'value': 'lord'},
                                        {'field': 'mount_body', 'op': '!=', 'value': 'none'},
                                        {'field': 'melee_defence', 'op': '>', 'other_field': 'melee_attack'}]},
                      'fields': ['melee_attack', 'melee_defence', 'mount_body']}},
]
