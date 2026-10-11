# Unit search and field discovery (issue #28)

Two read-only tools answer roster and stat questions directly from the pinned
serving snapshot. Callers need no unit names, no schema knowledge and no external
roster list. They reuse the #2 query library and the #3 adapter (stdio and HTTP).
They add no database, server, copied roster or name-specific branch. Search
version: `unit-search-1.0.0`.

| Tool | CLI | Purpose |
| --- | --- | --- |
| `discover_unit_fields` | `unit-fields [FIELD]` | Field ids, labels, types, units, operators, null counts, source scope, comparable fields, ambiguous terms, unsupported classifications, grammar and examples. With `field`, pages that field's categorical values. |
| `search_units` | `search-units --where JSON` | Filtered, sorted, paginated qualified unit keys with requested values and completeness metadata. |

```sh
PYTHONPATH=src python -m ctw_adviser.cli unit-fields --db work/adviser.sqlite subculture
PYTHONPATH=src python -m ctw_adviser.cli search-units --db work/adviser.sqlite --group-by mount_family \
  --where '{"all":[{"field":"subculture","op":"=","value":"wh2_main_sc_hef_high_elves"},
                   {"field":"caste","op":"in","value":["lord","hero"]}]}'
```

## What a row and a count mean

- **Rows (`qualified_variant`).** One canonical stat profile (`unit_profiles`)
  in one represented subculture (`unit_availability` through `unit_aliases`).
  A profile on several rosters appears once per subculture, so filter by
  `subculture` for a roster. The pinned snapshot has 3,172 rows covering 2,379
  profiles and 25 subcultures. Within one row, faction and roster scope are
  single-valued; this is checked against the source.
- **Groups (`mount_family`, `group_by: "mount_family"`).** The on-foot base
  profile and its mounted variants from `unit_mount_variants`, within one
  subculture. A profile with no mount relation is its own family. Filters apply
  to each variant **before** grouping. A family lists its matching variants,
  each with its own values, plus `family_variant_count` and
  `unmatched_variant_keys`. No stat is ever merged across mounts.
- **Totals.** `total` counts `count_unit` items (variants or families), and
  `matched_variants` always counts variants. `complete` and `next_cursor` show
  whether more pages remain.
- **Coverage.** Results are complete within the imported pinned snapshot only.
  That is not proof of complete game coverage: units the snapshot does not
  import cannot match.

Each result returns:

- `unit_key` and `subculture`, which pass directly to `get_unit_combat_profile`,
  `get_matchup_evidence` and `evaluate_single_unit_matchup` (as `subculture` or
  `subculture_a`/`subculture_b`).
- `provenance_refs`, which work with `get_provenance`.
- `source_unit_keys`, when more than one source key shares the profile in that
  subculture (for example Nakai Temple Guard). Each of these keys resolves to
  the same profile.
- `name_status: "source_placeholder"`, on the 104 profiles whose imported names
  contain unresolved `{{tr:...}}` text. Searching `unit_key` finds them.

Responses stay compact. Full combat packets are never returned per hit.

## Baseline semantics

Values are the imported base values for the snapshot baseline: unmodified custom
battle, ultra scale, rank 0, patch 9.0. Passive and activated abilities,
technologies, skills, items and campaign effects are not applied, and no combat
is simulated. `speed` is the normalized primary-body run speed used by the combat
model (range 0 to 11.6). No conversion to the in-game displayed speed scale is
established, so a displayed threshold such as "speed above 35" has no verified
equivalent here. The acceptance example uses native `speed > 4` instead.

## Fields

Fields come from a reviewed mapping (`FIELDS` in `src/ctw_adviser/unit_search.py`)
to the serving schema. Discovery describes each one; the main groups are:

- **Roster and identity:**
  - `subculture` (labeled with faction names), `faction`, `roster_scope`, `faction_exclusive`
  - `name` (`contains` matches the display or source name) and `unit_key`
- **Classification:**
  - `caste`: lord, hero and the unit castes
  - `unit_type`, `unit_class`, `target_size`, `weight`
  - `primary_body`: man, mount or engine
  - `mount_relation`: mounted_variant, base_with_mounted_variants or no_mount_relation
  - `mount_body`: none, mount, engine or mount_and_engine
  - `is_large`, `is_single_entity`, `is_renown`, `in_encyclopedia`, `has_missile_weapon`
  - `attributes`: a multivalued set
- **Numeric stats,** each with a unit and a dimension:
  - costs: `multiplayer_cost`, `campaign_recruit_cost`, `campaign_upkeep`
  - health, barrier, leadership, speed and mass
  - armour, missile block chance, resistances and ward save
  - melee attack, melee defence and charge bonus
  - primary melee, primary missile and primary explosion values

**Weapon and component scope is explicit.** `primary_melee_*` fields read the
profile's normalized primary melee weapon. `primary_missile_*` fields read the
default projectile of the primary missile weapon. `primary_explosion_*` fields
read the explosion on that projectile. Secondary weapons, alternative projectiles
and other components are not searched, and no unit row is duplicated per
weapon; `get_unit_combat_profile section=weapons` shows them.

`attributes` is the one multivalued field:

- `contains` and `not_contains` test a single attribute key.
- `any_of` tests membership of at least one key.
- It is filter-only and cannot be an output column.

**Ambiguous terms are rejected with candidates and never guessed.** These
include `cost`, `damage`, `ap_damage`, `bonus_vs_large`, `hp` and `resistance`.
For example, "cost" must become `multiplayer_cost`, `campaign_recruit_cost` or
`campaign_upkeep`.

**Unsupported classifications are reported, not inferred:**

- Legendary versus generic lords and heroes: the snapshot has no agent-subtype
  or legendary flag.
- Spell and lore access: use the #19 effect tools.
- Abilities as search fields.

The native custom-battle cost is kept even where it is 0 or negative. This
affects 23 profiles; for example, The Blue Scribes cost -700.

## Query grammar

- **Condition:** `{"field": id, "op": op, "value": literal}`.
  - Numbers: `=`, `!=`, `>`, `>=`, `<`, `<=`, `between [low, high]` (inclusive),
    `in`, `not_in`, `is_null`, `is_not_null`.
  - Categories: `=`, `!=`, `in`, `not_in`, `is_null`, `is_not_null`. Values
    must exist in the snapshot.
  - Booleans: `=`, `!=` and the null checks.
  - Text: `=` (case-insensitive) and `contains`.
- **Field-to-field comparison:** `{"field": "melee_defence", "op": ">", "other_field": "melee_attack"}`.
  Both fields must be numeric with the same dimension. Comparing `armour` with
  `melee_attack` (armour versus melee skill) or `armour` with `speed` returns
  `incompatible_units`.
- **Groups:** `{"all": [...]}` (AND) and `{"any": [...]}` (OR). Grouping is
  explicit: there is no implicit precedence, a bare list is rejected, and a
  group has exactly one key.
- **Nulls:**
  - Missing is not zero, and no ordinary predicate matches a null. For example,
    `primary_missile_ap_damage < 1` excludes the 1,876 profiles that have no
    missile weapon.
  - `!=` and `not_in` also exclude nulls.
  - There is no generic NOT; use `is_null` or `is_not_null` explicitly.
- **Sort:** at most three `{field, direction}` keys. Nulls sort last in either
  direction. Ties always break on unit key, then subculture, so ordering and
  pagination are deterministic.
- **Bounds:**
  - 32 conditions, nesting depth 4, and 64 list values
  - 24 output fields, 3 sort keys, and 100 results per page
  - a SQLite progress-handler execution budget
- **Cursors.** A cursor is bound to the snapshot id, the search version and the
  interpreted query: where, fields, sort and group_by. The page size may change
  between pages.
  - A cursor from another snapshot gives `stale_cursor`.
  - A cursor sent with a different query gives `cursor_query_mismatch`.
  - An altered cursor gives `invalid_cursor`.

Errors are actionable: `unknown_field` includes suggestions, and
`unknown_category` points to the discovery call for that field.

## Examples and measurements

[`unit-search-measurements.json`](unit-search-measurements.json) is produced
by `scripts/measure_unit_search.py`. It records exact arguments, totals, page
counts, first results, MCP response size and median warm latency for each case.
On this snapshot:

| Query | Total | First page | Median |
| --- | --- | --- | --- |
| High Elf lords and heroes, by mount family | 35 families / 126 variants | 34.7 KB | 29 ms |
| The same, one row per variant (limit 100) | 126 variants (2 pages) | 40.5 KB | 3 ms |
| High Elf heroes, melee attack > / >= / < / <= 45 | 5 / 6 / 37 / 38 | ≤ 15.3 KB | ≤ 2 ms |
| High Elf heroes, melee attack > 60 | 0 (hero maximum is 55) | 3.4 KB | 1 ms |
| Infantry, armour < 40 AND speed > 4 | 215 | 11.4 KB | 19 ms |
| Infantry AND (armour < 40 OR speed > 8) | 454 | 11.6 KB | 17 ms |
| Custom-battle cost ≤ 1,000, sorted by primary melee AP damage | 1,702 | 12.5 KB | 21 ms |
| Mounted lords with melee defence > melee attack | 121 | 13.3 KB | 16 ms |
| Every qualified variant (limit 100) | 3,172 (32 pages) | 40.7 KB | 20 ms |
| Field discovery | 67 fields | 47.9 KB | < 1 ms (cached) |

The largest response is well under the hosted 1 MiB cap.

## Verification

`tests/test_unit_search.py` derives every expected set from independent direct
reads of `unit_profiles`, `unit_aliases`, `unit_availability`,
`unit_mount_variants` and `unit_attributes`. It never reuses the search SQL. It
covers:

- discovery
- the complete High Elf lord and hero set, plus its mount families
- each threshold operator at an exact 45 boundary, with matches on both sides
- AND/OR precedence
- cost with explicit weapon-field sorting and descending tie order
- mounted lords with a field comparison, with exclusions present
- full pagination over 3,172 rows sorted on a heavily tied field, with no
  duplicates or omissions, and grouped totals
- cursor invalidation
- null versus zero
- unknown, ambiguous and incompatible fields
- query bounds and the execution budget
- follow-up into the existing resolve, profile and provenance tools
- library/MCP equality

`scripts/accept_mcp_http.mjs` runs a connected session over HTTP. It discovers
the subculture by its label, lists the High Elf roster to completion, follows a
result into its combat profile and checks the ambiguous-cost diagnostic.

Not yet done: a real connected ChatGPT/Claude conversation against the deployed
service. That needs the hosted MCP rebuilt after review (see
[hosted MCP](hosted-mcp.md)).
