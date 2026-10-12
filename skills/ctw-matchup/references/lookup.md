# Unit lookup semantics

Contract source: [PR #31 unit-search documentation](https://github.com/OwenTanzer/CTW-adviser/blob/331fbe8cc06cee2ed6019c2c25539ef0fa270b51/docs/unit-search.md), verified against its MCP schemas. Discover current schemas before using these examples; no example establishes present connector availability.

## Discovery and query shape

`discover_unit_fields({})` pages field definitions. With `field:"subculture_key"`, `"source_caste"`, `"tactical_category"` or another supported categorical field, it pages observed values. Follow `next_cursor` with unchanged arguments. `search_units` accepts `filters`, `fields`, `sort`, `mode`, `limit` and `cursor`.

Leaves use `field`, `op` and `value`, or numeric `value_field` with compatible declared units and scope. `and`/`or` objects contain child predicates. Supported operators are `eq`, `ne`, `gt`, `gte`, `lt`, `lte`, `in`, `not_in`, inclusive `between`, literal-substring `contains` (ASCII case folding), `is_null` and `is_not_null`. Null checks omit values; no general NOT. Equality/category keys are exact. Use only discovered fields/operators.

After verifying category keys, High Elf characters grouped by explicit mount links:

```json
{"filters":{"and":[{"field":"subculture_key","op":"eq","value":"wh2_main_sc_hef_high_elves"},{"field":"source_caste","op":"in","value":["lord","hero"]}]},"mode":"families","fields":["source_caste","is_mounted","melee_attack","melee_defence"],"limit":50}
```

Use `variants` for individual profiles. At the reviewed source pin, independent tests found 126 profiles in 35 families; rerun all pages before presenting that as a current result. To add a threshold, add a leaf such as `{"field":"melee_attack","op":"gt","value":60}` inside the intended AND. A genuine empty result stays empty, not a reason to loosen the user's predicate.

Base cost <= 1000, descending primary melee AP damage:

```json
{"filters":{"field":"multiplayer_cost","op":"lte","value":1000},"fields":["multiplayer_cost","weapon_ap_damage"],"sort":[{"field":"weapon_ap_damage","direction":"desc"}]}
```

Mounted lords with base defence greater than attack:

```json
{"filters":{"and":[{"field":"source_caste","op":"eq","value":"lord"},{"field":"is_mounted","op":"eq","value":true},{"field":"melee_defence","op":"gt","value_field":"melee_attack"}]}}
```

## Meaning and coverage

- `speed` is native ground `run_speed`, neither unit-card speed nor flight speed. Do not silently change a threshold or invent a conversion. Clarify if the user means displayed speed.
- `source_caste` is native; `tactical_category` is coarse. Infantry may include monstrous/unconventional units. Ordinary humanoid infantry is not certified by a search category. Define scope before derived comparisons; for client-side Pareto analysis, state tie rules.
- Imported `multiplayer_cost` is a base source value. Membership/cost do not establish custom-battle availability or fully equipped lord/hero prices.
- Melee damage covers the primary melee weapon; missile fields cover the selected default projectile and exclude explosions. For other weapons/components, use detailed evidence tools. Search is not a combat calculation.
- Multivalued memberships are existential over aliases; separate AND leaves can match different underlying members. They do not prove same-row recruitment conditions. Positive tests mean any member. Negative tests require at least one known member and no matching member; empty relations are excluded except by `is_null`.
- Numeric ordinary predicates, including `ne`/`not_in`, exclude nulls. Zero is not missing. Compatible numeric field comparisons require the same units/scope; multivalued sorting/comparison is rejected.
- `is_mounted` includes source mount/engine bodies or mounted endpoints, including platforms. Families are explicit connected mount components, never guessed from names. Filters run before grouping, retaining each matching variant's stats without invented family aggregates.
- Mandatory results retain canonical `unit_key`, qualified `unit_name`, roster memberships and `source_unit_keys`. For a specific roster follow-through, resolve a source alias belonging to that roster.
- Legendary/special status is unsupported as a separate classification. Preserve untranslated labels and stable keys; 104 profiles had translation placeholders at the reviewed pin, a labeling limitation independent of numeric completeness.
- Conditional passives and activated effects are not added to base search stats. Do not combine protection totals without resolving source overlap and enabling conditions through supported evidence.

## Pagination and bounds

Follow `next_cursor` with the identical filters, fields, sort, mode and limit until `complete:true`. Cursors bind snapshot and search version too; restart on stale-cursor errors rather than mixing pages. Sort allows three scalar fields, nulls last, canonical-key tie-break; families order by first matching variant. Counts distinguish profiles, families and matching variants.

Limits: 100 rows/families per page, 16 selected columns plus identities, three sort fields, filter depth five/32 nodes, 32 membership values, 256 characters per literal, finite numeric magnitude <= 1e12, and 10,000 matched profiles. Result-item budget is 60,000 bytes with explicit continuation. If one family exceeds it, request fewer fields or variants and restart the query. An execution-budget error is not an empty roster. Explain actual diagnostics and narrow the query without silently changing the user's scope.
