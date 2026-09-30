# Evidence packet contract 1.2.0

The authoritative schema is `schema/evidence_packet.schema.json`. Phases 1–2
established reviewed design fixtures and the pinned SQLite snapshot; phase 3
implements `ctw_adviser.queries.Queries` and the offline command-line interface.
The schema still accepts the reviewed 1.1.0 examples. Runtime packets use 1.2.0.

## Ordinary output

A packet has one snapshot/baseline, one or more qualified `units`, shared trait
descriptions, compact source/provenance dictionaries and optional graph details.
Single-unit and two-unit requests use the same schema. No winner, calculated
damage, interpreted trigger satisfaction or modified baseline belongs here.

Each unit retains the approved groups: `identity`, `body`, `movement`,
`leadership`, `melee`, `ranged`, `passives`, `cost`, `activated_options`, coverage
and provenance. The examples in the issue are abbreviated design projections;
their approved content is preserved under `fixtures/design/approved-examples.json`.
The executable examples add identity references, actual components, native
conditions, source locators and explicit coverage.

Damage and ordinary timing remain in `melee` and `ranged`. **All magical/flaming
tags and numeric target bonuses occur only under `passives.attack_traits`.**
`melee`, `ranged` and `explosion` identify the default attack of each kind.
Each trait object includes an explicit attack reference and optional component
reference. An explicit trait component must agree with its attack attachment;
explosions inherit the component of their parent ranged profile. A null trait
component leaves the attack reference authoritative. Further profiles receive entries in `attack_traits.additional`, with
their own kind and scope. A unit-level trait never implicitly propagates to
every weapon, explosion, passive-damage event or transformed form.

The default ranged profile remains directly inside `ranged`; alternate profiles
are in its `variants` array. Melee variants work the same way. Each attack event
has a unique unit-local ID; repeated underlying weapon/projectile keys are valid.
An explosion attached to two attack profiles can have two event IDs referencing
the same source key. This does not create two attacks or imply both fire at once.
`ammunition_pool` identifies shared pools; it is not an independent ammunition
allocation per variant. `is_default` is source evidence, not an applicability rule.

For example, Blue Horrors retain separate `magical: true` and `flaming: true`
values for melee and ranged. Queen Bess has a separate explosion trait scope.
The packet includes each relevant trait explanation once. Numeric target bonuses
remain distinct from qualitative Anti-Infantry/Anti-Large bullet labels.

## Missingness, projection and pagination

`coverage.melee` and `coverage.ranged` use `present`, `known_none`, `unresolved`
or `omitted`. For ranged weapons:

| Representation | Meaning |
| --- | --- |
| `ranged: null`, coverage `known_none` | Supported evidence establishes no ranged weapon. |
| Object with `status: present` | A selected ranged profile is returned. Completeness of variants is reported separately. |
| `{ "status": "unresolved" }` | Missing/ambiguous weapon evidence; a specific gap is mandatory. |
| `{ "status": "omitted" }` | Explicit projection, with a gap explaining the omission; not proof of absence. |

For melee, `null` is disambiguated by the mandatory melee coverage state. Modes
`combined`, `melee` and `missile` are projections, not judgments about relevance or
active mechanics. Identity, body, movement, leadership, cost and coverage remain
visible. Unknown numeric values are null; observed zero remains zero. Negative
native sentinels remain literal. No array silently means "none" unless its
section's coverage is complete with zero returned/total.

Each unit reports coverage for components, weapons, attributes, abilities and
activated options. Counts refer to returned component records, attack profiles
(excluding nested explosions), attribute records, passive mechanics and option
records respectively. `complete` requires offset + returned = total and no cursor (offset defaults to zero);
`partial` requires an opaque expansion cursor, plus a larger total when known.
`unresolved`/`omitted` require a section-specific gap. Semantic gaps may coexist
with a structurally complete inventory.

Cursors bind to the source snapshot/store, packet version, selected source unit,
subculture, section, mode, page size and continuation position. Invalid or
stale/incompatible cursors are rejected. Their checksum detects accidental
changes; it is not an authorization signature. The database is public evidence.
Fixture cursors are invented schema examples and are not usable query tokens.
Expansion cannot silently change the snapshot. Deterministic ordering follows
qualified unit identity, attack role/slot/variant, and native phase order/recipient
identity; source-backed fixtures preserve deterministic pinned source order.

## Passives and activated options

A passive requires `requires_effect_enabling` (boolean or unknown/null) and
nonempty `classification_evidence`, alongside identity, name, culture, a concise summary, native casting
parameters, conditions, phases, typed effects, provenance and an optional-detail
reference. Essential explanation and supported effects remain inline. Unknown
names are null; missing explanations are explicit qualified statements with gaps.
Raw deactivation evidence does not establish activation, threshold equality,
refresh or hysteresis. Phase order and self/friend/enemy flags stay separate.

Effect kinds are closed and versioned:

| Kind | Preserved evidence |
| --- | --- |
| `stat_modifier` | Stat, value, serving operation and exact native operation. `mult` maps to `multiply`; opaque tokens use `native`. |
| `attribute_effect` | Attribute, grant/removal/native semantics, recipient and native parameters. |
| `periodic_damage` | Native damage amount, cadence and entity limit; no invented unit-wide rate. |
| `healing` | Healing, barrier healing, resurrection, cadence and native limits remain distinct. |
| `payload_reference` | Exact typed node/detail reference and relationship. |
| `unresolved` | Native kind/parameters and a truthful explanation of missing semantics. |

Each effect points to its phase where known. Definitions are not automatically
applied to base fields. Whole-life simulations, conditional application and
combat arithmetic belong to issues #5/#6. Additional recurring effect families
require a deliberate schema/fixture change.

`activated_options` contains only qualified identity, classification evidence,
culture/enabling requirements and deferred detail references. Its schema rejects
an effect payload. An unresolved classification remains explicit and is never
silently promoted to a passive. The source-backed design projections do not claim
an exhaustive option classification; their coverage says so.

Payload graphs store nodes once, with all distinct edges including cycles.
References must resolve to nodes or declared lazy detail entries. The validator
checks references without recursively traversing edges, so cycles are safe.
Native scalar parameters can include opaque tokens. External/unresolved targets
must be represented explicitly, with a qualified node/detail entry and gap.

## Field mappings and evidence

Packet version 1.1.0 requires `identity.faction_name` as a sorted, unique array
of roster labels, including for a single-faction unit. These labels describe
shared inclusion; they do not transfer availability restrictions. A resolved
`subculture_key` is the selected lookup context, not ownership of the shared
base profile. Runtime output uses null when several contexts exist and none was
selected; a unique context can be resolved without guessing. The store retains each context and its evidence in
`unit_availability`; profiles and list-valued labels are deduplicated.
Store schema 3 maps every original key through `unit_aliases` to a shared profile.
Resolve the supplied key before profile retrieval; retain the supplied identity
when querying availability and evidence. `unit_keys` lists all represented keys.
Only exact profile and linked-combat-evidence matches consolidate; mount and
mechanical variants remain distinct. Selected source identity and permissions
must never be inferred from the canonical profile's representative key.

`identity.unit_type` maps to canonical `tactical_category`. Costs map as follows:
`multiplayer` ← `multiplayer_cost`, `campaign_recruitment` ← `campaign_recruit_cost`,
`campaign_upkeep` ← `campaign_upkeep`. These do not establish recruitment access.
Speed/mass/timing retain native units; percentage-like resistance values retain
percentage points. Count nesting, effective cycles and collision probability
remain interpretation questions. A schema-valid packet is not a combat model.

Source dictionaries pin paths/hashes and owner identities. Evidence entries use
1-based logical records including the CSV/TSV header and any metadata row.
Upstream physical `source_line` and `source_patch` remain separate. Every fixture
source locator is checked against its exact key. Assertion sidecars compare
numeric/boolean/text values to those rows and verify operation mappings. These
sidecars are testing artifacts, not ordinary query output.

The schema's version is independent of the import-contract version. This change
does not alter the source pin or import contract. Names and conditions are source
evidence; summaries are either the previously approved prose or concise authored
descriptions tied to localization/source rows. Prose is not treated as an
additional numeric modifier. Unresolved localization substitutions remain visible
and receive a gap.

## Fixtures and validation

`fixtures/manifest.json` lists a small reviewed set: Sea Guard, Blue Horrors,
Kroxigor, Wargor (enabling qualification) and Queen Bess (explosion scope), plus
structurally distinct synthetic cases. These packets and their assertion sidecars
are contract examples, not database contents. The generator also rebuilds the
shielded Sea Guard, Reiksguard, Doom Diver, Bloodletters and all three named pairs
under ignored `work/generated_examples/`. Their manifest is validated with
`--generated-examples`; neither repeated pair packets nor every test projection
needs to be committed. Source data and generation rules remain pinned.

Synthetic cases use conspicuously invented identities, a zero source commit and
`SYNTHETIC-NOT-GAME-DATA` provenance. They exercise compound effects, recipient
phases, healing/resurrection, unknown kinds, shared ammunition/variants, component
targetability, activated/unresolved options, cycles, overflow and omitted versus
unknown versus known-none weapons. Their values must never support game claims.

```sh
python scripts/verify_sources.py --ctw-root ../CTW-data
python scripts/define_packet_schema.py
python scripts/build_packet_fixtures.py --ctw-root ../CTW-data
python scripts/build_synthetic_fixtures.py
python scripts/validate_packets.py --ctw-root ../CTW-data
python scripts/validate_packets.py --ctw-root ../CTW-data --generated-examples
python -m unittest discover -s tests -v
```

The schema uses standard JSON Schema 2020-12 constructs. The standard-library
validator implements only the explicitly checked subset used here and refuses
unsupported keywords. It is not advertised as a general JSON Schema engine.
Cross-field/reference and source checks supplement structural validation. Future
query responses must pass these same structural and semantic checks.

Runtime retrieval assembles general inventories and explicit source limitations
from the store. Design fixtures remain independent examples; their deliberate
projection gaps are not copied into runtime output or used as unit-specific code.

## Runtime API and commands

Use `with Queries(path) as q:` with one reusable read-only connection. No source
CSV/TSV or network access is needed for these methods. Startup loads the bounded
table/type registry, not unit records, and does not rehash the database.

| Method | Result |
| --- | --- |
| `resolve_unit(query, subculture=None)` | Exact key or case-insensitive exact serving/original name; resolved identity, ambiguous candidates or not_found. No fuzzy selection. |
| `get_unit_profile(resolved_id, ...)` | One assembled evidence packet with base facts and linked combat sections. |
| `get_combat_relations(resolved_id, section=None, cursor=None, ...)` | The same packet contract, optionally projecting or continuing one section. |
| `get_matchup_evidence(unit_a, unit_b=None, mode="combined", scenario=None, ...)` | One or two units through the same general retrieval path. |
| `get_passive_detail(key, culture="*", limit=128, cursor=None)` | Inline mechanic plus bounded native graph/lineage details; the supplied culture does not establish unit access. |
| `get_detail(ref, limit=128, cursor=None)` | Native record graph, exact-key availability/permissions, or deferred option metadata. |
| `get_provenance(record_ids)` | Exact source locators, physical source path/line/patch, and payload lineage. |

`get_unit_profile` and `get_combat_relations` accept resolved identity dictionaries
or key/name strings. Dictionaries are re-resolved rather than trusted. An exact
alias keeps that original source key; name discovery consolidates equivalent
profiles but returns different mechanical/mount variants as candidates. A named
shared profile's representative key does not establish campaign permissions.
`identity.profile_unit_key` and `identity.unit_keys` make that distinction visible;
`availability:<original-key>` expands only that key's records and permissions.

```sh
python scripts/query_snapshot.py resolve --db work/units.sqlite Teclis
python scripts/query_snapshot.py unit --db work/units.sqlite "Teclis (Arcane Phoenix)"
python scripts/query_snapshot.py matchup --db work/units.sqlite "Lothern Sea Guard" "Blue Horrors of Tzeentch" --mode combined
python scripts/query_snapshot.py relations --db work/units.sqlite Kroxigor --section abilities --limit 1
python scripts/query_snapshot.py passive --db work/units.sqlite wh2_main_unit_passive_martial_prowess
python scripts/query_snapshot.py detail --db work/units.sqlite record:RECORD_ID
python scripts/query_snapshot.py provenance --db work/units.sqlite RECORD_ID
```

Use `--subculture` and `--subculture-b` for pair-specific lookup contexts. Ambiguous
unit commands return candidate JSON with exit code 2; other failures use exit
code 1. `resolve` returns discovery status with exit code 0. `--scenario` accepts
a JSON object which is echoed once as caller context and is never applied to
statistics, effects, classifications or retrieved inventories.

### Projection and continuation

`section` accepts components, weapons, attributes, abilities or activated_options.
The five inventory coverage entries remain visible; unrequested inventories have
an explicit omitted state and gap. Base identity, health, movement, leadership,
protection and costs remain present. Weapon projections also return component
evidence for attachment scope. Modes project attacks only; they do not decide
whether passives are applicable. A missile mode omits melee, and a melee mode
omits ranged, even when the underlying unit has no missile weapon.

`limit` is a **record-count budget per inventory**, default 32, allowed 1–256.
It is not a byte/token promise and never splits one passive's essential inline
effects or conditions. Larger individual mechanics can still produce larger
packets; use section projections and measure bytes. Each partial inventory
returns a total and cursor. Continue one unit/section using that cursor and the
same mode and limit. Explicit section mismatches fail. With no section argument,
the cursor's section is selected automatically. Pair responses can contain
independent cursors; expand each unit separately.

Runtime coverage includes an `offset`. `returned` counts this page; `total`
counts the whole selected inventory. A terminal complete page has
`offset + returned == total` and no cursor. It completes the continuation,
not proof that this page alone contains earlier records. Legacy fixtures omit
offset and therefore use zero. Sections retain semantic gaps even when their
record inventory is complete. Default attacks are ordered first using exact
normalized weapon/projectile identities; other slots/variants and shared or
secondary ammunition pools remain distinct, including zero ammunition.

### Mechanical and explanatory mappings

Primary melee values retain normalized meanings; linked weapon supplements do
not overwrite them. Other melee slots use their own native weapon values and
carry explicit slot/component scope. Ranged direct damage/timing/counts come
from the exact linked projectile; ammunition comes from the attachment pool.
Explosion events are separate scoped attacks. Conflicting default/native values
produce discrepancies rather than a second fictitious attack.

Optional attack `native_parameters` retain collision/splash, penetration, homing,
contact and other selected mechanical parameters. Weapon length is native
evidence, not a certified reach model. Immediate payload/contact nodes and phase
stat/attribute effects appear in `payload_graph` with attack-scoped roots and
exact record references; this graph is a bounded projection, not full closure.
Every node can be expanded by its record detail reference. Detail traversal
preserves cycles and distinct parallel edges, follows only supported inbound
owner attachments, and stops at activated/unresolved metadata. A page includes
boundary references for edges whose other endpoint is on another page.

Passive stat names use only the explicit serving mappings below; other native
tokens remain unchanged. Native `add` becomes add and `mult` becomes multiply;
unknown operations remain native.

| Native stat | Serving stat |
| --- | --- |
| stat_melee_attack | melee_attack |
| stat_melee_defence | melee_defence |
| stat_charge_bonus | charge_bonus |
| stat_resistance_physical | physical_resistance |
| stat_melee_damage_ap | melee_ap_damage |
| stat_melee_damage_base | melee_base_damage |
| scalar_speed | speed |

Phase recipient edges, order and duration remain separate from effects. Damage,
healing, resurrection and barrier healing retain native quantities/cadence.
Attribute positive/negative tokens remain native unless a reviewed semantic
mapping establishes grant/removal. Other phase behavior and intensity settings
use the explicit unresolved subtype with raw values and gaps. Detail references
retain replacement, behavior and payload dependencies. No modifiers are applied.

Summaries use deterministic templates built from the emitted effects and exact
deactivation flags. Condition localization is labeled **source UI wording**:
it can describe an eligibility requirement rather than the meaning of the
deactivation token. It is never inverted into an activation rule. Unresolved
localization substitutions stay visible with gaps. Flavor ability tooltips are
available through localization/provenance, not substituted for numeric effects.

Runtime provenance now includes optional `source_path` and `lineage_refs`.
The source dictionary's path and logical record identify the retained table row;
physical path/line/patch can identify an upstream row named by the payload lineage
table. They need not refer to the same file. Lineage entries are included once
and checked against the pinned provenance source, preserving the scoped 9.0.1
payload evidence without relabeling the whole snapshot.

Passive detail requires an actual unit link carrying the supplied culture; it
never manufactures a culture qualification from caller input. The link is
evidence of a listed option, not proof of obtainable or active access.

### Verification

Run `python -m unittest discover -s tests -v` for source/store/packet/runtime
checks. Run `python scripts/audit_queries.py --db work/units.sqlite --ctw-root
../CTW-data` for every original unit key, packet schema/reference checks, exact
source/lineage locators, coverage overflow, bytes and measured query performance.
The audit legitimately reads source files for verification; ordinary queries do
not. Reports and generated packets stay under ignored work/. Platform timing is
observational evidence, not an engine comparison or token estimate.

The 2026-09-30 schema-3 audit passed all 2,409 original unit keys and 32,692
unique source/lineage locators. On Windows 11 ARM64 (Qualcomm), Python 3.12.10
and SQLite 3.49.1, connection startup was 10.7 ms, median roster-unit lookup
16.5 ms (95th percentile 30.1 ms), and median Sea Guard/Blue Horrors pair lookup
25.8 ms over 100 repetitions. Compact JSON's median size was 28,626 bytes;
the largest was 217,654 bytes for the Daemon Prince, whose 62 activated options
explicitly overflow the default 32-record budget. The database was 57,663,488
bytes. These timings exclude schema validation/serialization and reflect this
runtime, not cross-platform performance. Checked name, original-name, ability
and phase-effect plans all used indexed SEARCH operations. Full reports remain
under ignored work/ and can be reproduced with the audit command above.

### Review corrections

Source-backed passive fixtures copy and assert `requires_effect_enabling` from
ability definitions and retain definition/casting classification references.
The Wargor qualification fixture demonstrates a source-confirmed true flag;
its effect expansion is explicitly unresolved, and the link does not establish
access or activity. Synthetic cases exercise the same required envelope.

Source validation also checks passive summaries against the reviewed examples
or the fixed qualification-only template. This rejects edited fixture prose;
it is a bounded fixture gate, not a general free-text semantic validator.
Changes to approved explanations require review alongside their typed effects.
