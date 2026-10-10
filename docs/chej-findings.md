# Chej's unit findings — packet 1.16

This increment follows recovered PR #11 head 440a8b2. The source remains
CTW-data 3b5d13d94c5ed3eb4b9c6ce61cc75854b4426196. Import contract 2 adds
four existing, hash-verified native exports; it does not alter upstream data.

## Reviewed source-contract extension

The native `land_units`, `battle_entities`, `unit_missile_weapon_junctions`
and `battle_entity_stats` tables are selected through existing roster,
component and weapon roots. No campaign or activated-ability roots are added.
Every native column is retained for detail retrieval. Unprojected columns
remain exact TEXT rather than receiving inferred numerical semantics.
Explicit projected mappings are:

| Source | Typed fields | Identity / selection |
| --- | --- | --- |
| land_units | reload, primary_ammo, secondary_ammo: INTEGER; infinite_secondary_ammo: BOOLEAN | normalized source_land_unit_key → key |
| battle_entities | run_speed, fly_speed, fire_arc_close: REAL | normalized source_battle_entity_key and component battle_entity_key → key |
| unit_missile_weapon_junctions | exact TEXT | source main-unit key; preserve every matching junction id |
| battle_entity_stats | exact TEXT | junction battle_entity_stats_override → key |

Rows, headers, composite relations, file bytes, SHA-256 and Git blob identities
are checked. The source commit and normalized facts are unchanged. Nullable
relationships use the existing recorded-gap policy. Junction retrieval uses
an index on `unit`, not a table scan. These additions require a rebuilt snapshot.

## Packet behavior and acceptance

1. Weapon `firing_policy` preserves precursor true/false/null. Its explanation
   comes from the retained precursor tooltip: Fire-at-Will off requires an
   ordered charge target; on selects the closest enemy. Stalker variants,
   Blessed Stalkers, Sneaky Gits and Khorne Soul Grinder are regression cases.
2. `ammunition_supply` separates native primary/secondary capacities,
   native weapon pool selection, infinite-secondary status and normalized
   assignment. Existing `ammunition_pool` and `ammunition` remain normalized
   source facts for compatibility. **When sources disagree, effective_pool is
   null and an inline qualification states the conflict.** No count of 50
   establishes finite secondary supply for the Thunderbarge family. The
   multiplayer Spirit identity gains no invented secondary attachment.
3. Ordinary explosions now carry their own complete mechanical native
   projection and a detail reference, preserving text-valued fuse settings.
   Contact and shrapnel graphs remain separate. Root values do not establish
   total hit count, damage, or measured timing.
4. Movement retains the existing `speed` compatibility field, explicitly
   identified as primary-body run speed, and separate ground/flight settings
   with the exact body key. Native values are not measured travel times or
   converted unit-card values. Mounted configurations use the normalized
   source-selected body, not a guessed entity from the unit name.
5. Each matching weapon override retains its junction id, exact stat key,
   base melee/missile keys, provenance and resolvable detail. This does not
   invent a component count, targetability or simultaneous firing.
6. `reload` distinguishes projectile base interval from unit reload skill.
   Existing `reload_time` remains a compatibility alias for the base interval.
   Storm Riders / Sea Guard preserve 18 / 0 alongside their common interval 11.
   Effective cadence and damage per second remain downstream calculation work.
7. `health_aggregation` reproduces the upstream builder's native-category
   distinction, not a heuristic based on displayed tactical category.
   `health_contribution` is additive only for primary bodies and separately
   included crew of native artillery. Queen Bess: 2600 + 4700 = 7300;
   Wolf Chariots: 6240 + 0 = 6240, retaining the secondary known total 192.
   Primary artillery health already includes a crew slot. Components omitted
   by projection or pagination must not be summed as a complete total.
8. `body.firing_arc` preserves the primary body's native fire_arc_close and
   identity separately from Fire Whilst Moving. Pistoliers / Outriders retain
   360 / 70. Native field units and weapon applicability remain unestablished;
   the packet does not assert rearward fire or a measured coverage angle.

## Open evidence decisions

The 255 ammunition disagreements across 152 source unit keys are a screening
inventory, not 255 verified bugs. Native flag versus attachment-role priority
requires engine evidence before correcting normalization. The new packet
makes the discrepancy actionable without silently choosing either source.
`effective_pool` means agreement of the retained sources, not an in-game test.
Firing-arc units/application likewise require runtime or authoritative engine
schema evidence before gameplay wording can go beyond the native setting.
These two interpretation gates must remain unchecked in Notion. Preservation
and retrieval can be completed without pretending those gates were solved.

Full provenance remains opt-in; default packets retain small source references.
No passive modifier is applied to base stats. No merge or deployment is implied.

## Verification, 10 October 2026

- Full suite: 103 tests passed; final supplement checks: 6 passed, including
  mounted Crone's Manticore identity and finite-ammunition control.
- Fresh source-verified snapshot: 2,409 unit keys, 3,181 roster rows.
- Full packet/schema/provenance audit: 2,409 keys and 36,643 source locators,
  zero errors. Expanded packet timings: median 2.75 ms, p95 5.05 ms.
- Supplement audit: all 2,409 unit health totals reconcile; no missing
  ground/flight records; 14 override attack rows retained.
- Ammunition disagreement classification: 253 additional-weapon rows and
  2 engine rows across 152 unit keys. All remain explicitly unresolved for
  engine precedence; no raw-flag-driven numerical overrides were applied.
- Sea Guard default packet: 13,505 serialized UTF-8 bytes, compared with
  recovered 1.15's 11,670. New mechanical facts account for the increase;
  full source dictionaries remain deferred.

Reproduce with:

```sh
python scripts/build_snapshot.py build --ctw-root ../CTW-data --output work/chej.sqlite
CTW_DATA_ROOT=../CTW-data python -m unittest discover -s tests
python scripts/audit_queries.py --db work/chej.sqlite --ctw-root ../CTW-data --output work/query-audit.json
python scripts/audit_chej_findings.py --db work/chej.sqlite --output work/chej-findings-audit.json
```

External documentation searches did not establish Warhammer III engine
precedence or firing-arc application. The twwstats exporter's own README
(https://github.com/twwstats/twwstats-dataexporter) documents the historical
`use_secondary_ammo_pool` schema-name correction, but does not establish
attachment precedence. It is not used to override the pinned facts.
