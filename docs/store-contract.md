# SQLite serving snapshot — issue #2, phase 2

Build offline with Python 3.11+ and SQLite 3.37+:

```sh
python scripts/build_snapshot.py build --ctw-root ../CTW-data --output work/units.sqlite
python scripts/build_snapshot.py inspect work/units.sqlite
python -m unittest discover -s tests -v
```

Integration tests use `CTW_DATA_ROOT` or the sibling `CTW-data` directory. They
explicitly skip without pinned inputs. The database, full reports and temporary
cases stay under ignored `work/`; no generated database or extra packets are
committed. Phase 3 supplies queries and approved packet assembly. This phase
does not complete issue #2 or calculate combat results.

## Storage

`schema/store.sql` defines STRICT metadata, identity, provenance, classification,
graph and coverage tables. Native evidence tables are generated from the existing
locked column types and keys, with their mappings recorded in `dataset_tables`.
Schema version 3 stores each distinct base profile once in `unit_profiles`, keyed by
a canonical `unit_key` within the pinned game/patch/scale snapshot. `faction_name` is a sorted,
unique JSON array, including for single-faction units. `unit_availability` retains
each original faction/subculture-qualified roster entry, its restrictions, counts,
notes and provenance locator. Conflicting base fields for a shared unit key reject
the build. The current source has 2,379 profiles representing 2,409 original
unit keys and 3,181 availability records. `unit_aliases` maps every original key
to its canonical profile and retains its original `source_main_unit_key`.
`unit_keys` is a sorted JSON array of all keys represented by a profile.
`unit_roster_records` is a lossless view reconstructing every original normalized
column and source record; roster entries in `dataset_tables` point to this view.
`unit_identity` stores each main-unit key once, scoped to the snapshot. `unit_records`
connects original roster records and unit relations to that identity. A profile's
`record_id` is a deterministic representative; all supporting roster evidence is
available through `unit_availability`. Mount-only identities absent from
the rosters are classified as external. Roster permissions remain separate and
never transfer through shared inclusion or mount links.

For characters with explicit mount links, `unit_name` includes the mount variant
in parentheses; unmounted base versions use `(on foot)`. Bases already carrying
a mount/platform are labeled accordingly. `source_unit_name` preserves the exact
upstream name and the reconstruction view returns that original name. Labels are
presentation derived from pinned mount icons/identifiers, not certified localized
names or combat facts. Missing identifiers produce an explicit unresolved label.
Unit keys, combat statistics, mount links and availability remain unchanged.

Roster-wide consolidation compares every profile field except source record ID,
unit/main-unit keys and aggregated faction labels. It also requires exact equality
of the distinct linked unit-relation records (components, weapon slots/payloads,
qualified abilities, attributes, contacts and other supported unit relations),
excluding only their source record ID and unit key. Mount relationships must also
match. Missing and present evidence remain distinct. Recruitment/roster permissions
are preserved separately per original key. Matching names or base stats alone do
not establish equivalence. No upstream key or dependency edge is discarded.
The pinned snapshot consolidates 29 groups, eliminating 30 repeated profiles.
Canonical selection prefers the shared land-unit key, then shortest/lexical key.
Original keys resolve through the indexed alias map; original names and keys
reconstruct through `unit_roster_records`. Serving clients must resolve aliases
before profile lookup and retain the selected source key for availability queries.

Normalized relation tables retain their stems, e.g. `unit_components`,
`unit_weapon_links`, `unit_attributes`, `projectiles` and `explosions`. Shared
definitions use `native_`, e.g. `native_ability_phases`. Raw weapon supplements
use `melee_weapons` and `missile_weapons`. Supplements do not overwrite profiles;
phase 3 assembles attacks from weapon links rather than duplicating inline
default-projectile values as another attack.

Blank becomes NULL; zero and negative sentinels remain distinct. Source booleans
become checked integer booleans. Types come from the contract, never row inference.
Native operation tokens remain literal. Original key strings, including blanks,
are preserved in provenance JSON and checked for uniqueness independently of SQL
NULL equality. Compound weapon and phase/order/recipient keys survive intact.
No modifiers are applied to base profiles.

## Dependency boundaries

All roster rows and normalized unit relations are roots. Linked ability
definitions plus `casting.passive` establish passive/activated/unresolved
classification, with exact evidence locators. Enabling and culture qualifications
survive. Missing evidence is unresolved; names and button visibility do not
classify mechanics.

Core-passive and weapon roots select their supported dependency records. Explicit
inbound attachment joins bring in phase links, conditions, effects, intensity,
recharge and replacement evidence. Arbitrary reverse traversal is prohibited.
The graph follows contact, overhead, shrapnel, homing, penetration, scaling,
bombardment and vortex references. A visited-record set stops cycles while
retaining every source edge. Contact tokens can identify one phase or a group;
every group member survives without declaring simultaneous application. Optional
behavior junctions do not establish absence when missing.

The locked contract supplies the base joins. Narrow additional payload edges
and inbound attachments follow the selected native schemas and upstream payload
conventions. No source pin or approved packet contract changes in this phase.

Activated/unresolved definitions and casting records use narrow
`native_ability_definitions_metadata` and `native_ability_casting_metadata`
tables. Payload fields are absent rather than misleading NULLs. If a passive
dependency reaches an activated option, its identity survives, expansion stops
and the deferred dependency is recorded as a gap. `ability_option_metadata`
records classification, enabling qualification and source evidence. Ability
links preserve culture; neither classification nor a link proves obtainable access.

`source_files` reconciles input, retained and excluded catalog row counts. Excluded
rows are outside the serving scope, not absent from the game. Global coverage
declares partial semantics and unverified runtime. Record-level gaps preserve
unresolved references, unknown targetability, engine behavior and summons.
Bare native evidence is not certification of a complete engine simulation.

## Provenance and explanation material

Each retained record has file fingerprints, a logical CSV record locator (header
is record 1), and its native key. RPFM metadata rows count in that locator but are
not game records. Native physical `source_line`, `source_path` and `source_patch`
remain separate. Selected projectile/explosion records acquire original lineage
from the locked payload-provenance table, linked through `record_lineage`.
An upstream path outside the selected inputs is retained as a path, never invented
as a local foreign key. Actual bytes and locked fingerprints are both recorded
because the upstream contract permits reviewed LF/CRLF representations.

Relevant localization is retained verbatim: attribute text, ability labels and
tooltips, both condition-description forms, and stat/trait dictionaries. Markup
and placeholders remain evidence for phase-3 reviewed explanations. Phase 3 must
embed supported summaries/effects and disclose unresolved interpretation; this
storage phase does not present raw tooltips as validated numeric mechanics.

## Validation and installation

Source verification rejects missing/corrupt bytes, stale contracts, failed owner
or audit gates, header/type/key/count drift and required join failures. Inputs
are fingerprinted again after reading and before installation. Output inside
CTW-data is rejected.

A uniquely named sibling candidate imports in one transaction. Counts, source
identities, foreign keys and SQLite integrity must reconcile. SQLite statistics
and query plans verify indexed unit key/name and forward/reverse access. The
candidate is closed and flushed before atomic replacement. Failure preserves
the previous artifact and removes the candidate. Windows may reject replacement
while a reader holds the file open; the prior database then remains usable.
Ordinary access uses `mode=ro` and `query_only`, requiring no extraction, network
or source scans.

Identical inputs on the same Python/SQLite runtime produce identical database
bytes; cross-runtime page layout is not promised. Tests independently compare
every retained native field with source, check passive/activated boundaries,
contact groups and lineage, reject writes and exercise failed installation.

## Verified pinned build

On Windows with Python 3.12 and SQLite 3.49.1, the final pinned build retained
3,181 roster rows, 2,409 main-unit identities and 46,257 evidence/lineage/text
records. Its 1,077 reachable ability identities classify as 499 core passives and
578 activated options. All 36,196 stored dependency edges resolve; 312 explicit
coverage gaps concern unsupported runtime behavior or targetability rather than
broken references. These are evidence-coverage counts, not a completeness claim.

The database is 56,279,040 bytes; this run built in 8.912 seconds. All four checked
unit key/name and forward/reverse access plans use indexed SEARCH operations.
All 41 tests pass, including full retained-field source comparison, byte-identical
rebuilds, read-only access, invalid inputs and injected pre-install failure. The
10 approved packet fixtures still pass schema/semantic/source validation. Timing
depends on hardware/runtime; packet size and assembled-query performance belong
to phase 3. Full reports remain reproducible under ignored `work/`.
