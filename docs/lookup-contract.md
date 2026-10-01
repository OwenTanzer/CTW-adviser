# Evidence packet contract 1.8.0

The authoritative schema is `schema/evidence_packet.schema.json`. Phases 1–2
established reviewed design fixtures and the pinned SQLite snapshot; phase 3
implements `ctw_adviser.queries.Queries` and the offline command-line interface.
The schema still accepts earlier reviewed examples. Runtime packets use 1.8.0.

Development diagnostics are separate from ordinary agent output. Default packets
omit `coverage.gaps` prose and include only `coverage.diagnostic_count`, alongside
the existing section states, counts/cursors and explicit melee/ranged status.
The count signals available notes, not missing mechanics or a completeness score.
Raw conditions, unresolved effects, nulls, provenance and source-specific
qualifications stay in combat facts. Absence of diagnostic prose never certifies
complete mechanical interpretation.

Use `get_coverage_notes(unit, ...)` (CLI `coverage --db ... UNIT`) for a separate
diagnostic response with identity, coverage notes and their evidence. It accepts
the same context, mode and page options as ordinary queries. For inspection of
the complete packet, pass `include_diagnostics=True` or CLI
`--include-diagnostics`; passive detail supports the same opt-in. The read-only
site includes diagnostics in its human view; JSON downloads default to compact
agent output. Stored `coverage_gaps` and generated query caveats remain available
without copying diagnostic notes into a second serving file. Stable interpretation
rules belong in this contract and issue #6's skill guidance.

Phase behavior with unmapped semantics is still `kind: unresolved`, but
its summary names the available parameters and exact values (for example,
`Mana regeneration modifier: 0.4` or `Fatigue change ratio: -0.0025`). These
labels describe source fields; they do not establish percent units, per-second
rates, recipient applicability or engine arithmetic. The corresponding native
keys, values, phase links and evidence remain intact. Intensity summaries expose
their settings with scaling/stacking qualification, excluding repeated source
locator metadata from the prose. Generic implementation notes stay in diagnostics.

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
Attribute polarity is mapped to `operation: grant` for `positive` and
`operation: remove` for `negative`, while the exact original token remains in
`native_parameters.attribute_type`. This is a serving interpretation of the
source application flag, supported by contrasting retained rows: positive
Immune to Psychology/Silenced/Rampage versus negative Immune to Psychology,
Rampage and charge defence against large. Positive does not mean beneficial.
The phase links retain recipient and duration scope; the mapping does not
certify activation, stacking or post-phase restoration. Unknown tokens stay
unmapped with an explicit gap. Summaries say “Grants” or “Removes” and display
the attribute name. Other phase behavior and intensity settings
use the explicit unresolved subtype with raw values and gaps. Detail references
retain replacement, behavior and payload dependencies. No modifiers are applied.

Summaries use deterministic templates built from the emitted effects and exact
deactivation flags. Plain-language summaries describe mechanical facts rather
than calling them “native values” or “native types”. Unknown quantity units,
timing, scaling and engine behavior are qualified explicitly, without replacing
available numbers or claiming the uncertainty has been solved.
Condition summaries explain the encoded predicate rather than substituting UI
wording, which often describes the opposite eligibility state. Original keys and
localization provenance remain available. Missing UI text does not make a clear
predicate such as climbing or manning equipment unknowable. Composite/state
definitions still receive specific qualifications.

Conditions have distinct roles: `recharges_when` comes from recharge contexts,
`unavailable_when` from invalid-usage flags, and `invalid_targets` from target
exclusions. Deactivation remains `deactivates_when`; `activates_when` is not
filled by mechanically inverting another category. Every populated role appears
in the ordinary passive summary. `unresolved` is reserved for unclassified
conditions rather than a catch-all for recharge or usage evidence. Legacy
`recipient_requirements` remains accepted for earlier fixtures.

The pinned recharge inventory is 22 passives with seven predicate keys. Wounds
has `health_below_25%`, initial recharge 5 and no health-based deactivation link.
Its threshold is a readiness gate, not proof of immediate activation or automatic
removal after healing. Summaries expose nonnegative initial/subsequent timer
settings; negative sentinels remain unchanged in casting evidence. Progress
reset/pause, threshold equality and reactivation remain separate runtime gaps.
The ammunition threshold is absent from the condition key, but selected UI text
says ammunition above 80%; the below-threshold predicate therefore exposes 80%
as an explicitly labeled UI-derived interpretation, with an inspection diagnostic.

Flavor ability tooltips are
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

## Passive summons

Casting definitions with a populated `spawned_unit` produce a `summon` effect
containing the exact unit key, localized name where retained, spawn type, use
limit and transformation/decoy/shared-health settings. Ordinary summaries expose
these facts; no imported base stat is changed. Unknown summon names keep the key.

The Rats Emerge and Nurgling Emergence are reviewed death-spawn interpretations:
the casting passive flag, one-use summon at unit_position and unit_alive
deactivation predicate support `trigger: on_death`. Their condition records remain
unchanged. This mapping does not generically invert other deactivation predicates.
The Rats Emerge tooltip additionally describes spawning on death. Exact scheduling,
spawn entity counts, degradation and other runtime rules are not established here;
the retained summon-runtime diagnostic stays available through coverage opt-in.
Other passive summons retain an unresolved trigger unless separately established.
The structured trigger_basis records the interpretation and its limitation.

The two death-spawn display names are reviewed labels from the pinned CTW-data
`data/unit_stats/source_exports/text/db/land_units__.loc.tsv`: keys
`land_units_onscreen_name_wh2_main_skv_inf_skavenslave_spearmen_0_summoned`
(Skavenslave Spears) and
`land_units_onscreen_name_wh3_dlc25_nur_inf_nurglings_summoned` (Nurglings).
This catalog is not imported; no retained localization record is fabricated.
Summon unit identity and mechanics retain their casting-record provenance.

## Exploding Unit visual indicator

`wh2_dlc15_unit_abilities_exploding_unit` exposes a `visual_indicator`
effect with a concise purpose, based on its retained tooltip explicitly describing
a hidden persistent banner visual effect indicating that a unit explodes.
The mapping requires that supporting tooltip and includes its provenance.
It is not a damage event or numerical modifier; attack/projectile/explosion
evidence remains separately represented. Its empty phase therefore does not
produce a phase_effect_unknown warning. No other empty phase is reclassified.

## Too Horrible to Die failure branch

Its existing miscast payload reference now carries optional `failure_context`:
casting failure chance and global-bonus flag, explosion direct damage/radius,
and linked contact-phase damage, timing and recipient flags. The default summary
interprets miscast_chance 0.5 as a 50% failure chance and qualifies runtime execution.
The explosion's zero direct damage does not erase its damaging contact effect.
This is conditional failure evidence, not an unconditional extra damage event.
The Rats Emerge remains a separately conditioned death summon; no mutually
exclusive heal-versus-summon coin flip or guaranteed death is asserted.
Full casting/explosion/contact provenance remains available on request.

## Reviewed explanations and calculation payloads

The three traced examples use concise, reviewed summaries in the existing mechanic
envelope. No additional unit-mechanic schema is introduced. Literal conditions,
phase sequence, self-damage/healing and summon fields remain accessible.
Bloated Corpse, Explosive Squig and Hell Pit Abomination explanations distinguish
self-damage, outward payloads and conditional failure. See issue #2 comment
5911263008 for the source trace and remaining execution questions.

For individually reviewed abilities, existing payload references also expand into
the packet's existing payload_graph: bombardments, projectiles, explosions,
vortices and contact phases keep their original mechanical parameters and record
identity. Shared definitions appear once; separate ability references remain.
Expansion is bounded to four edges/64 visited records per mechanic, with explicit
detail-required diagnostics at a boundary. Passive detail exposes the same compact
payload_graph alongside its existing full source graph. Ordinary source documentation
remains optional. Retained parameters support downstream calculations but do not
certify per-target hit counts, damage totals or engine scheduling. Payload damage
is never copied into ordinary melee or ranged weapon statistics.

The next reviewed batch extends this treatment to Fiery Rebirth, Rebirth,
Heroic Fortitude and Restore the Blighted, plus seven death-payload abilities
and the hidden Split Up summon companion. These changes use the existing 1.8.0
packet fields; no additional mechanic schema or source import is introduced.
The four survival abilities expose the conditional failure explosion/contact
chain without treating it as an unconditional periodic effect. Their differences
remain explicit: Heroic Fortitude has no buffer phase; Fiery Rebirth also has an
outward blast; Restore the Blighted requires effect enabling. Negative use and
recharge sentinels do not establish repeatability or a fixed use count.

For the seven reviewed death-payload abilities, `activates_when` explains the
blast's death event using the casting behavior and group-to-type record as
provenance. `vortex_on_entity_death` means an individual entity's death;
`vortex_on_death` means the host unit's death. These are reviewed interpretations
of behavior evidence, not inversions of deactivation flags or proof of exact
engine scheduling. Force of Total Destruction's self-damage phase remains
separate from its death-triggered outward blast; the behavior does not establish
the self-damage phase's timing. Condition-table coverage alone cannot establish
complete trigger coverage.

Sea Elemental's Split Up death blast and hidden low-health summon remain two
records. The latter is disabled above 25% health, summons Oceanids once at the
host position and carries a zero-damage pulse with a force setting. Its exact
activation boundary remains unverified; its summon is not labeled `on_death`.
Oceanids is a reviewed display label from the pinned land-unit localization,
using the same convention as the previously reviewed summoned-unit labels.

Contact phases include their owning stat/attribute effect rows in the bounded
calculation graph, following the same reverse ownership links as weapon contact
payloads. Pestilent Perfection therefore exposes both its outward damage and
its leadership -10 contact effect (duration setting 10). Ordinary summaries
retain essential timing/overlap qualifications; full source documentation and
development diagnostics remain opt-in. The reviewed buffer's role is described,
but its existing diagnostic is retained until engine timing is established.

Kaboom! and Blow Apart use the same explanation/payload approach. Their host-death
event is an individually reviewed interpretation of the unit-alive exclusion and
the associated blast/tooltip evidence, not a generic inversion rule. Their contact
penalties remain in the payload graph: leadership -8 for both, and speed x0.85 for
Blow Apart, duration setting 10. The blasts affect allies and enemies; the contact
phases affect enemies only. Blow Apart's self-targeted damage remains separate.

The Necrofex Abandon Ship! is a one-use low-host-health summon disabled above 50%,
with a separate self-damage phase. Death to All, Absolute Supremacy and Spirit-Essence
of Chaos instead damage eligible enemy targets and summon Wight King, Zombies and
Chaos Spawn respectively. Their above-20%-health exclusion applies to the target.
Death to All excludes non-commanders; the other two exclude commanders. The Nagash
abilities retain requires_effect_enabling. No caster-health or death trigger is
invented. Their unit-position spawn setting does not establish caster-versus-target
placement, a required kill, summon timing or lifetime. The existing trigger_basis
and summary describe these specific unknowns; trigger remains unresolved. Summoned
unit labels follow the same pinned-localization convention as earlier passes.

## Focused passive research

This pass covers the 24 entries in `RESEARCHED_PASSIVES` in `queries.py`.
Lightning Strike (`wh3_dlc29_passive_spell_lightning_strike`) and Murderous
Prowess Indicator (`wh2_main_faction_abilities_murderous_prowess_indicator`)
are deliberately unchanged. Their target-selection and indicator-state questions
remain outside this increment. This is explanation enrichment, not a claim that
all 24 engine implementations have been reconstructed.

The summaries are reviewed interpretations. Numerical values, recipient edges,
condition roles, sentinel values and payloads come from the existing pinned
CTW-data commit, with base 9.0 / shared 9.0.1 scope unchanged. External sources
corroborate the meaning of those records; they neither overwrite numerical values
nor establish compatibility with every patch. Research was consulted on
2026-10-01 UTC (2026-09-30 Pacific). Wiki pages are unversioned secondary sources;
CA release articles are historical descriptions, not current-value authorities.

| Cases | Source basis and supported interpretation |
| --- | --- |
| Conjoined Destiny | Pinned countdown/heal phase order and above-20% deactivation; [ability reference](https://totalwarwarhammer.fandom.com/wiki/Conjoined_Destiny) corroborates 30-second preparation and the advertised 25% heal. Keep source duration 1.1, not the reference's rounded 1 second. Repeatability, resets and caps remain unverified. |
| Lucky Git | Pinned one-use, above-25%, 5-second preparation and 30-second healing records; [ability reference](https://totalwarwarhammer.fandom.com/wiki/Lucky_Git) corroborates that sequence. Its advertised 0.60% rate does not resolve the pinned 1.5 interval setting; do not calculate a total heal from the tooltip. |
| Bloodborn | Pinned one-use, above-25%, shared 1-second buffer and self-heal records, with resurrection false. [Ability reference](https://totalwarwarhammer.fandom.com/wiki/Bloodborn) corroborates a healing ability. Effective healing arithmetic remains qualified. |
| Implacable Spirit | Pinned 25-second first phase, self-recipient links, movement restriction and modifiers; [CA Update 8.0](https://community.creative-assembly.com/total-war/total-war-warhammer/blogs/98) explicitly identifies stationary preparation. Wall Veteran is a separate allied-buff interaction, not a reason to relabel these self-effects as an aura. |
| Dig in! | Pinned 25-second preparation, movement restriction, self-recipient links, range/resistance modifiers and charge-defence grant; selected unit tooltip describes digging into position. Only this exact base ability is reviewed; upgraded variants are not silently included. |
| Blackpowder Discipline | Pinned 10-second preparation, self-effects and movement restriction; [CA's Elspeth introduction](https://community.creative-assembly.com/total-war/total-war-warhammer/blogs/14) corroborates stationary accuracy/reload benefits. The +10 stat_reloading is reload skill, not a percentage reduction in reload time. |
| Feast of the Maggot Lord | Pinned tamurkhan_death behavior, nearby-commander restriction and separate self-healing/protection versus enemy-damage phases; [CA's Tamurkhan introduction](https://community.creative-assembly.com/total-war/total-war-warhammer/blogs/13) explicitly describes a death-triggered last chance and second wind. Do not infer target priority, phase overlap or a universal execution-health threshold. |
| Disengage! | Pinned summon_unbinding behavior, 150-second support phase and 5-second self-damage phase; selected tooltip and [ability reference](https://totalwarwarhammer.fandom.com/wiki/Disengage%21) identify departure to resupply. Self-damage is removal machinery, not outward damage; campaign upgrade behavior is not evaluated. |
| Survival Instinct | Pinned broken-morale restriction, teleport_leave_battle behavior, -100 leadership and rebirth stance; [Dread Maw reference](https://totalwarwarhammer.fandom.com/wiki/Dread_Maw) explicitly says it does not return after fleeing. Interpret the stance in that context, not as resurrection. |
| Redirecting Aura | Pinned missile_mirror behavior, enemy-recipient phase, non-missile exclusion and effect_range 55; [ability reference](https://totalwarwarhammer.fandom.com/wiki/Redirecting_Aura) corroborates nearby-shooter redirection. Projectile exceptions and close-range behavior remain unresolved. |
| Judgement of the Uxmac; Mistwalkers' Barrage | Pinned melee recharge, casting timers and bombardment links; [Judgement reference](https://totalwarwarhammer.fandom.com/wiki/Judgement_of_the_Uxmac) and [Barrage reference](https://totalwarwarhammer.fandom.com/wiki/Mistwalkers%27_Barrage) corroborate melee-associated strikes. Payload values remain pinned, not copied from older balance discussions. |
| Warp Discharge; Searing/Spurting Bile-Blood | Pinned melee recharge and vortex links; [Warp Discharge](https://totalwarwarhammer.fandom.com/wiki/Warp_Discharge), [Searing Bile-Blood](https://totalwarwarhammer.fandom.com/wiki/Searing_Bile-Blood) and [Spurting Bile-Blood](https://totalwarwarhammer.fandom.com/wiki/Spurting_Bile-Blood) corroborate the damage mechanisms. No per-incoming-hit retaliation is established. |
| Tides of Transformation; Hellraiser | Pinned melee recharge, separate vortex links and non-numerical self-phases; Hellraiser also has an outside-melee deactivation. Source records support the explanation; external listings add no proof of exact scheduling or phase/vortex synchronization. |
| Giant Explodin' Spores | Pinned outside-melee recharge and outside-melee deactivation describe recharge and release separately; [historical WH2 unit description](https://www.honga.net/totalwar/warhammer2/unit.php?f=wh_main_grn_greenskins_mp_custom_battles_only&l=en&u=wh2_dlc15_grn_veh_snotling_pump_wagon_ror_0&v=warhammer2) describes charge explosions and regrowth out of combat. Charge-versus-contact timing is qualified; no self-destruction is inferred. |
| Rubble & Ruin I–III bombardment records | Pinned one-use, above-75/50/25% exclusions and shared bombardment. Three event routes survive deduplication of one payload definition. Exact equality and skipped-threshold scheduling remain unknown. |
| Foreboding Ignition | Pinned one-use, above-10% exclusion, effect-enabling qualification and expanding vortex link. Describe a low-health release, not a death event. No external runtime guarantee is added. |
| Wrath of Khorne; Locus of Power | Pinned enemy-targeting, 100-metre interception range, winding-up target restriction and separate vortex damage; [Wrath reference](https://totalwarwarhammer.fandom.com/wiki/Wrath_of_Khorne) and [Locus reference](https://totalwarwarhammer.fandom.com/wiki/Locus_of_Power) support spellcasting retaliation. Whether non-spell abilities qualify, simultaneous-caster arbitration and exact timing remain unknown. Damage does not imply spell cancellation. |

Additional UI-effect junctions in the pinned upstream source independently label
several of these behaviors (healing timer, melee bombardment/vortex, instant
shatter, projectile redirection and Locus miscast). They were inspected as research
evidence but are not newly imported tables or fabricated stored provenance rows.

No packet schema change is needed: summaries, existing condition objects, phase
reasons and bounded calculation payloads carry the explanations. Empty preparation
phases retain their unresolved effect kind and timing qualifications; improved
explanations do not certify engine execution. Existing diagnostics stay separately
retrievable. Default unit and passive results contain no research-document prose.
For an explicit documentation link, use:

```sh
python scripts/query_snapshot.py passive --db work/units.sqlite --include-documentation wh3_twa08_unit_passive_redirecting_aura
```

The optional `explanation_documentation` object links here and distinguishes the
reviewed interpretation from pinned source facts. The inspection site exposes the
same documentation through a collapsed panel. The two excluded records receive
neither a revised explanation nor that documentation attachment.
