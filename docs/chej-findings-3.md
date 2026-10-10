# Chej findings 3 — repair and acceptance

The baseline is adviser `08e9f20406978f3e52ed52dffad140296250702e` and source
`2b5965e78c85dc795451dad188756a173b247be5`. These changes implement the six
follow-up findings. Packet shape remains 1.18.0; the source pin, import-contract
fingerprint and snapshot compatibility gate migrate deliberately to source
`595e22764b22e748afdbafafcb0a6258973e2451`.

| Finding | Repair and evidence |
| --- | --- |
| 1. Running with the Pack | Explicitly maps unit_is_moulder_monster to the source invalid state: target is **not** a Clan Moulder Monster. Both eligibility and invalid-state localization records remain in provenance. Ordinary Packmaster and passive detail agree; 3-friendly-unit / 35-metre settings and effects are preserved. Locus of Azyr’s correctly worded exclusion is a control. No global inversion is introduced. |
| 2. Granted Flaming | Reuses the innate-Flaming explanation for a phase’s recipients while active: fire-vulnerability interaction, half-rate healing while on fire, +50% building modifier. Tests cover ordinary/detail Balefire and Blaze, innate Flaming, and a non-Flaming control. The Corpse Cart’s base melee attack remains non-Flaming. Raw ignition and damage values are untouched. |
| 3. Stat scope | Shared labels are Spell Resistance, Incoming Healing Modifier and Melee Damage Reflection. Explanations distinguish spell damage from all magical attacks, healing/regeneration received, and damage returned on a melee hit. Blood Shield +20, Blood Thirst ×1.5, Acid Ichor +6 and Blazing Body +25 retain signs and operations. Label/tooltip evidence is included with the effects. |
| 4. Casting predicate | The explanation preserves the conflict: the invalid-state UI says casting is absent, while the key refers to post-wind-up activation. Exact predicate and timing remain unresolved. This is a deactivation condition, not an invented activation trigger. The committed inventory records all 56 native deactivation links and the flag definition; seven links are retained in the current passive projection. The semantic audit checks all seven, including the five requested Daemon Flies / Children of Nurgle / Kamau cases. |
| 5. Compatibility | Source PR #42 now has an exact reviewed ammunition migration instead of resetting the historical baseline. The five stale output fingerprints and generated baseline comparison are regenerated together. Downstream additionally locks the migration, unchanged historical baseline, validation code and owner compatibility artifacts. Source rows and imported columns do not change. Old snapshots require a rebuild. |
| 6. Regiment-of-renown example | Corrected source documentation to secondary/560 for the RoR engine, with its mortar primary/15; ordinary non-RoR engine remains secondary/40. The regression also checks all 772 served missile links for pool/capacity agreement. Configured capacity is not a per-volley or endurance calculation. |

## Upstream protection and validation

The unchanged historical payload baseline remains commit
`13b4ff93736d82a06d7be56f55046425c4cc0259`. The migration records each of the 255
before/after weapon fingerprints and the six default roster ammunition changes.
Every migrated row must match the reviewed full fingerprint. Only the two allowed
ammunition fields are restored in memory before comparing with the original
baseline. Unrelated projectile, explosion and weapon changes, missing migrated
rows and duplicates still fail. Negative regressions cover altered ammunition,
weapon projectile identity, projectile damage and explosion damage.

The candidate magic validator passed, as did all 14 magic tests. The ordinary
local `npm run validate` attempt stopped in the high-memory skills validator;
a bounded-heap diagnostic reproduced a heap exhaustion. This local limitation
is not substituted for the required GitHub full validation result.

## Downstream verification

On 10 October 2026, the ordinary unittest discovery run passed **123 tests**
without skips. Source verification passed **144 locked files / 76 datasets**,
3,181 roster rows / 2,409 unit keys. All **17 fixtures** passed (12 source-backed,
5 synthetic). The full query audit passes all 2,409 keys / 36,673 source locators. The first
review audit reports zero ammunition disagreements and no health/movement
failures; the second retains all 14 named child-explosion instances. The new
casting audit passes all seven retained uses against the rebuilt snapshot. The named regressions use default retrieval
limits for ordinary ability output, plus a full 772-link ammunition sweep.

```sh
python scripts/build_snapshot.py build --ctw-root ../CTW-data --output work/chej3.sqlite
CTW_DATA_ROOT=../CTW-data python -m unittest discover -s tests
python scripts/verify_sources.py --ctw-root ../CTW-data
python scripts/validate_packets.py --ctw-root ../CTW-data --generated-examples
python scripts/audit_queries.py --db work/chej3.sqlite --ctw-root ../CTW-data --output work/chej3-query-audit.json
python scripts/audit_chej_findings.py --db work/chej3.sqlite --output work/chej3-first-audit.json
python scripts/audit_chej_findings2.py --db work/chej3.sqlite --output work/chej3-second-audit.json
python scripts/audit_chej_findings3.py --db work/chej3.sqlite --output work/chej3-semantic-audit.json
```

No merge, deployment, measured firing experiment, exact casting event timing,
reflection damage-resolution formula or siege multiplier stacking is claimed.

The full upstream `npm run validate` step **passed** at source
`595e22764b22e748afdbafafcb0a6258973e2451` in
[GitHub run 38063265468](https://github.com/OwenTanzer/CTW-data/actions/runs/38063265468/job/114245663157).
That workflow also runs architecture, snapshot, newline, technology, effect,
campaign-start and magic regressions. The linked job is the durable upstream
acceptance record; local memory-limited execution is not presented as a full pass.
