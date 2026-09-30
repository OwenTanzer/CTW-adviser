# Evidence packet contract 1.0.0

This completes the packet-design portion of issue #2's Lock and validate work.
The authoritative schema is `schema/evidence_packet.schema.json`. The functions
described below are interface targets; the importer, SQLite store and query
library are not implemented by this increment.

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
records respectively. `complete` requires returned = total and no cursor;
`partial` requires an opaque expansion cursor, plus a larger total when known.
`unresolved`/`omitted` require a section-specific gap. Semantic gaps may coexist
with a structurally complete inventory.

The future query implementation must bind cursors to the source snapshot, unit,
section, mode and continuation position, and reject stale/incompatible cursors.
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

This increment establishes the output contract before Store and index work.
The importer must replace projection gaps with general inventories or explicit
source limitations; the design fixtures do not waive roster-wide acceptance.

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
