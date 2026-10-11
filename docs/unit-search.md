# General unit lookup — issue #28

`discover_unit_fields` and `search_units` share the existing SQLite `Queries`
library across CLI, stdio and HTTP. This is query-only: no new database, import
scope, source pin, combat formula or applied modifier. The implementation is
`src/ctw_adviser/unit_search.py`; its explicit field mapping is the allowlist.

## Discover, query, follow through

Call `discover_unit_fields({})` for field meanings, types, units, operators,
null semantics and capabilities. For a categorical field, call
`discover_unit_fields({"field":"subculture_key"})` (or `source_caste`,
`tactical_category`, `attribute_key`, etc.). Follow category `next_cursor` if
present. No repository/schema knowledge or guessed unit names is required.

For all High Elf lord and hero units:

```json
{"filters":{"and":[
  {"field":"subculture_key","op":"eq","value":"wh2_main_sc_hef_high_elves"},
  {"field":"source_caste","op":"in","value":["lord","hero"]}
]},"mode":"families","fields":["source_caste","is_mounted","melee_attack","melee_defence"],"limit":50}
```

At the pinned snapshot this is **126 profiles in 35 mount-linked families**.
Native caste includes represented special characters (for example Hand of the
Shadow Crown is a hero), but does not certify legendary/special-character
status as a separate classification. Never infer that status from a name.

Use `mode:"variants"` for individual profiles. Source aliases are deduplicated;
`unit_key`, qualified `unit_name`, all represented `subculture_key` memberships
and `source_unit_keys` always remain in results. Pass a returned `unit_key` to
`resolve_unit`, `get_unit_combat_profile`, or subsequent evidence tools.
Roster fields are existential memberships over all equivalent aliases, not a
claim of campaign recruitment permissions. When selecting a specific roster
context for a follow-up, resolve a returned source alias that belongs to it.

More predicates (put each under `filters`):

```json
{"and":[
  {"field":"subculture_key","op":"eq","value":"wh2_main_sc_hef_high_elves"},
  {"field":"source_caste","op":"eq","value":"hero"},
  {"field":"melee_attack","op":"gt","value":60}
]}
```

```json
{"and":[
  {"field":"tactical_category","op":"eq","value":"infantry"},
  {"field":"armour","op":"lt","value":40},
  {"field":"speed","op":"gt","value":35}
]}
```

Both requested examples are empty in this pin: High Elf hero melee attack tops
out at 55, and `speed` is the source's **native run_speed**, not a converted
unit-card speed. The API reports the units instead of silently converting the
threshold. Acceptance also uses attack 40 and native speed 3.5 to exercise
nonempty matches, exclusions and exact boundary values.

```json
{"filters":{"field":"multiplayer_cost","op":"lte","value":1000},
 "fields":["multiplayer_cost","weapon_ap_damage"],
 "sort":[{"field":"weapon_ap_damage","direction":"desc"}]}
```

```json
{"filters":{"and":[
 {"field":"source_caste","op":"eq","value":"lord"},
 {"field":"is_mounted","op":"eq","value":true},
 {"field":"melee_defence","op":"gt","value_field":"melee_attack"}
]}}
```

The filter language supports `and`/`or` objects containing child predicates;
leaves have `field`, `op`, and `value` or compatible numeric `value_field`.
Operators are `eq`, `ne`, `gt`, `gte`, `lt`, `lte`, `in`, `not_in`, `between`
(inclusive), `contains` (literal substring, ASCII case folding), `is_null` and
`is_not_null`. Null checks take no value. Equality/category keys are exact.
General NOT is intentionally unavailable; use explicit negative operators.

## Semantics and boundaries

The pinned source has 104 profiles whose display labels contain untranslated
`{{tr:...}}` tokens. Search preserves those values and their stable keys; it does
not guess replacement names. This is a source-label coverage limit, independent
of roster completeness and numeric filtering.

- Numeric ordinary predicates exclude NULL, including `ne` and `not_in`.
  Zero remains zero. No missingness-to-zero conversion occurs.
- Multivalued roster/attribute fields return distinct sorted lists. Positive
  filters mean any member. `ne`/`not_in` require at least one known member and
  no matching member; empty relations remain excluded. `is_null` means no
  known members. Separate AND predicates may match different members; they do
  not certify one shared underlying availability row. No same-row relational
  predicate is offered in this increment.
- Multivalued sorting and field comparisons are rejected. Numeric field
  comparisons require the same declared units and scope. Whole-unit versus
  entity health, campaign versus multiplayer gold, melee versus projectile
  damage, and armour versus speed cannot be silently compared.
- Melee damage is the source primary melee weapon. Missile fields are the
  selected default projectile, excluding explosions; they are not all weapons
  or a sum over components. Other component/weapon queries require detailed
  evidence tools; unsupported search fields fail with a discovery hint.
- `is_mounted` means source mount/engine body or mounted endpoint of an
  explicit mount link, including platforms. Families are connected components
  of explicit mount links after profile deduplication. No name, suffix or
  legendary-status guessing; unrelated transformations remain distinct.
- Filters apply **before grouping**. A family contains only matching variants
  and their individual selected stats, never a fabricated aggregate stat.
  Family identity is the stable smallest canonical profile key in its complete
  mount component. Disconnected or non-roster endpoints cannot merge families.
- Sort uses up to three scalar fields (asc/desc), NULLS LAST, then canonical
  identity. Family order is its first matching variant's position in that
  ordering. Counts explicitly distinguish profiles and mount-linked families.
- Follow `next_cursor` using identical arguments until `complete:true`.
  Cursors bind source snapshot, search version, filters, selected fields, sort,
  grouping and limit. They are opaque continuation state, not authorization.
  Invalid/stale cursors are rejected. Completeness is only within the imported
  snapshot; it never establishes complete game coverage.

Limits: 100 rows/families per page; 16 requested columns plus mandatory
identities; 3 sort fields; filter depth 5 and 32 total nodes; 32 membership
values; 256 characters per literal; finite numeric magnitude at most 1e12;
10,000 matched profiles; 20 million SQLite virtual-machine instructions per
call. Result items have a 60,000-byte page budget with explicit continuation.
An individually oversized family fails with instructions to request fewer
columns or variants. Progress-handler cleanup restores the connection after
failure. Existing HTTP request/response/concurrency/rate limits remain intact.

## CLI and validation

```sh
python scripts/query_snapshot.py discover-unit-fields --db work/adviser.sqlite
python scripts/query_snapshot.py search-units --db work/adviser.sqlite --query '{"filters":{"field":"melee_attack","op":"gt","value":60}}'
CTW_TEST_DB=work/adviser.sqlite python -m unittest discover -s tests -p test_unit_search.py -v
python scripts/benchmark_unit_search.py --db work/adviser.sqlite --output work/unit-search-verification.json
```

Tests compare exact keys and returned values with independent direct SQL,
traverse the source mount graph independently, exercise sort ties, full
pagination, AND/OR, null/zero, relations, bad types/operators, injection strings,
query limits, cursor drift and profile follow-through. The official Model
Context Protocol SDK acceptance script now discovers fields/categories,
searches both family pages and retrieves a returned combat profile, alongside
all existing four pair/four calculation checks.

Local measurements are in [unit-search-verification.json](unit-search-verification.json):
20 warm calls per case, compact UTF-8 bytes, no cleared OS cache or hosted
network latency claim. Representative medians were 2.2 ms for High Elf
characters, 4.7 ms grouped, 10.0 ms cost/damage sort and 18.4 ms full-roster first
page. Responses were approximately 15–35 KB for those selected pages.

## Release gates

Implementation and local protocol acceptance do not establish deployment or
real ChatGPT conversation acceptance. After review/merge/deploy, refresh the
CTW Advisor connector metadata, discover the two new callable tools, run the
roster query through all pages, follow a result to its combat profile, and
compare exact source identity sets to this acceptance. Synchronize the installed
CTW Matchup skill with the canonical workflow instructions once the tools are
live; Claude consumes the same discovery/search path. Keep #28 open until these
live gates are verified. No source pin or import-contract update is required.

### Main-branch reconciliation, 11 October 2026

During implementation, main advanced to `fd370a37afeecff3c91bc57f25ded2ca50fb7c78`
via PR #29, reverting the separate activated-effects increment for combined
review. This search branch incorporates that change and preserves its removal:
store 3 / import contract 2, six existing tools plus the two new search tools.
The database was rebuilt from the unchanged source pin, then protocol acceptance
and regression checks rerun. Earlier store-4 test receipts are historical, not
the final branch baseline. Live deployment and installed instructions remain
separate release gates.

Final reconciled local acceptance: **198 tests passed, zero failures/errors/skips**
(`CTW_TEST_DB=work/adviser.sqlite python -m unittest discover -s tests -v`).
Official SDK local HTTP acceptance passed with all eight tools, 35 family
results/126 variants across two pages, profile follow-through, four evidence
pairs, four combat evaluations, error handling and reconnect. Both new CLI
commands passed on the rebuilt store-3 artifact. This supersedes the earlier
210-test store-4 run. No hosted deployment or connected-chat acceptance claimed.
