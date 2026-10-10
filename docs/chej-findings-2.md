# Chej’s findings 2 — acceptance record

This implements the eight-part second review on the Schema refinements Notion
page, against adviser baseline `f82e57525450c370dc8170ae43d23c50ef965256`.
Runtime packets are **1.18.0**. This is author verification, not independent review,
a merge, deployment or an in-game combat test.

| Finding | Repair and acceptance cases |
| --- | --- |
| 1. Child explosions | Ordinary weapon graphs traverse descendants and omit only the root explosion already represented as its own attack. All 12 recorded chains, across 13 unit keys / 14 unit-chain instances, expose their child explosion. Zero were visible in the reproduced baseline; all 14 are visible after repair. Base/AP, radius and ally-hit settings match retained records, and root explosions are not duplicated. The inventory includes both Poison-Wind Mortar projectiles and both Thunderbarge variants. |
| 2. Combat target class | `body.size` stays the native enum. A separate `target_classification` uses an explicitly reviewed mapping: very_small/small → infantry; medium/large/very_large → large; unknown → unresolved. Reiksguard, Pistoliers, Outriders and Demigryph Knights retain medium and return large combat class, with infantry and Star Dragon controls. This does not consume the existing normalized `is_large` boolean. |
| 3. Trajectory | Every returned root/alternative projectile retains trajectory_sight, fixed_elevation and max_elevation. Handgunners low, Sea Guard dual_low_fixed and Mortar fixed are named regressions. Elevations retain the source contract’s TEXT type. The explanation does not claim angular units, line-of-sight simulation or obstacle clearance. |
| 4. Buildings | Every melee weapon/projectile retains its building_damage_multiplier, including sub-unit values. Tests cover Miners 3, Warp Grinders 2.5, Empire sword 0.75 / spear 0.5, Queen Bess 2, and Little Grom 2 / 4. Sea Guard preserves can_damage_buildings=false alongside 0.25. No effective siege-damage formula is introduced. |
| 5. Flaming | Shared attack-scoped wording gives half-rate healing while on fire, fire-vulnerability interaction and the +50% building modifier. Melee, ranged and explosion scopes plus a non-Flaming control are checked. No burn duration or damage-over-time effect is invented. |
| 6. Recipient caps | Positive finite native friendly/enemy limits appear beside their group and range. Dominate 1 enemy, Running with the Pack 3 friendly, Blood Oath 2 friendly, Legion Commander 4 friendly and Locus of Azyr 3 friendly are verified in ordinary and detail output. Dominate’s 25-entity damage limit remains separate. Missing, zero and negative values do not acquire an invented finite count. Casting/phase self flags remain separate; target choice and bearer slot accounting remain qualified. |
| 7. Spreading | Ordinary mechanics expose linked phase identity, native radius, linked-phase explanation, provenance IDs and detail references. Tears 35, Daemon Flies 40, and Little Plague I/II 40 are verified. II correctly links to v1, rather than copying v2. Propagation timing, recipient selection and repeat stacking remain qualified. |
| 8. Same-order phases | Same-order distinct phase keys receive recipient-branch labels instead of invented sequential stages. All six recorded cases are checked: Giver of Arcane Glory, Befouled Charge, Living Darkness, Dual Personality/Defiler, Arcane Leech, Humiliation of the Gods. Defensive Stance remains a genuinely staged control. Matching order is not described as proof of exact simultaneity. |

## Target-class interpretation evidence

The upstream builder’s existing `is_large` expression literally recognizes only
`large` and `very_large` (both profile and component rows). It is therefore not
used as a combat eligibility flag. This change does not silently reinterpret or
overwrite that stored boolean.

The reviewed mapping is corroborated by the author-maintained
[RPFM WH3 schema at 57a23a849fcaa805ccf3afe743bf46fd14a1a43c](https://github.com/Frodo45127/rpfm-schemas/blob/57a23a849fcaa805ccf3afe743bf46fd14a1a43c/schema_wh3.ron):
`projectiles_tables`, version 53, documents the infantry bonus for small/very-small
entities and the large bonus for medium-or-larger entities; `battle_entities.size`
is documented as a collision/combat size field. The pinned game’s anti-large UI
describes horse-sized targets and its charge-reflector tooltip explicitly names
cavalry and monsters. The ordinary packet cites the native entity and those two
retained localizations; this document records the interpretation source.

This is a reviewed semantic mapping, distinct from direct runtime observation.
No new unit modifier is applied and no charge-defence bracing/frontage calculation
is made. The adviser’s target-class change requires no CTW-data schema correction;
upstream’s narrower historical boolean remains retained for provenance only.

## Separate earlier ammunition item

A separately committed correction also closes ammunition item 2 from the *first*
Chej review. [CTW-data PR #42](https://github.com/OwenTanzer/CTW-data/pull/42)
fixes a builder heuristic that selected supply from attachment role instead of
`missile_weapons.use_secondary_ammo_pool`. The native flag selects the land-unit
primary/secondary capacity; attachment identity remains unchanged. The verified
source is `2b5965e78c85dc795451dad188756a173b247be5`, tree
`17cf1c66f9507d9694b6026a944aa49ac79379d0`.

The regenerated source changes 255 weapon-link rows (253 additional / 2 engine)
and six default roster ammunition values, without unrelated CSV changes.
Sea Guard’s alternate bow is primary/22; the Iron Daemon train cannonade is
secondary/40 while its Dreadquake is primary/15. Capacity and unlimited supply
are separate per-weapon fields. Thunderbarge’s secondary weapons inherit the
infinite-secondary flag; primary weapons do not. Synthetic disagreement still
returns unresolved pool/capacity/unlimited fields.

The deliberate lock migration also incorporates source main’s documentation
merge, updates hashes for the generated files and imports the builder’s new helper
as a locked authority input. Raw source records and roster counts are unchanged.
The import contract fingerprint and snapshot compatibility gate are updated;
old snapshots require a rebuild. Existing source-backed fixtures were regenerated
with their reviewed old packet shape and the new pin; earlier packet versions
remain schema-valid. PR #42 remains unmerged, so PR #11 currently depends on its
reviewed source branch commit rather than source main.

## Reproduction

```sh
python scripts/build_snapshot.py build --ctw-root ../CTW-data --output work/ammo.sqlite
CTW_DATA_ROOT=../CTW-data python -m unittest discover -s tests
python scripts/validate_packets.py --ctw-root ../CTW-data --generated-examples
python scripts/audit_queries.py --db work/ammo.sqlite --ctw-root ../CTW-data --output work/chej2-query-audit.json
python scripts/audit_chej_findings.py --db work/ammo.sqlite --output work/chej2-first-findings.json
python scripts/audit_chej_findings2.py --db work/ammo.sqlite --output work/chej2-after.json
```

The bounded audit also accepts `--code-root` and a matching historical database.
A separate worktree at f82e575, built from its original source pin 3b5d13d,
reproduced the before state; the audit compared 17 named unit packets and 16
passive explanations (including the staged control). Each passive’s ordinary
summary is checked against its detail response. Full audit reports and databases
remain reproducible under ignored `work/`; the 12-chain inventory and named tests
are checked in.

Verification on 10 October 2026: 118 tests passed, followed by all 9 second-review
checks after the final spreading-provenance refinement. All 17 fixture checks
passed (12 source-backed plus 5 synthetic). The full query audit passed 2,409 unit
keys and 36,665 source locators. The first-review audit retains all 14 override
junctions, finds no health/movement failures, and reports zero ammunition-pool
disagreements. Upstream unit validation and 17 unit tests passed, as did the
architecture validator and 26 architecture tests.
