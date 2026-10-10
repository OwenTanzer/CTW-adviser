# Final 33-case follow-up — local review evidence

Scope: four presentation findings (01A, 01C, 06C, 08C) from the final ledger, plus a bounded Daemon Prince lookup profile. This branch starts at adviser PR #11 head `d2ea52ae085d1d85fd83d40774362faab1949f59` and retains CTW-data source pin `595e22764b22e748afdbafafcb0a6258973e2451`. No CTW-data files, source lock, import scope, merge or deployment changed.

## Source-backed changes

- **01A/01C:** The ordinary ranged attack's `parameter_explanations.payload_chain` now follows retained shrapnel edges to child projectiles, child explosions and linked vortices. It reports each source stage's values and relationship, with child-hit count and total damage explicitly unestablished. This adds no damage to the base profile and leaves `payload_graph`, detail references and provenance available. The source inventory in `fixtures/design/chej2-chains.json` has 14 unit-chain instances; all 14 now have a direct explanation. Ushabti RoR, with eight child projectiles but no child explosion, remains a negative control.
- Thunderbarge fire bomb: root projectile `wh3_dlc25_unit_abilities_thunderbarge_fire_bomb`, root explosion `...stage_1` (0 base / 0 AP; radius 1 metre), shrapnel set `...fire_bomb_shrapnel` (4 children), child projectile and `...stage_2` explosion (30 base / 15 AP; radius 5 metres), plus native vortex `...fire_bomb` (0 base / 8 AP; start and goal radius 8 metres; duration 6 seconds). The exact pinned records are projectile 475, explosions 203 and 204, shrapnel 23, vortex 149. A child count is a source relationship, not a guaranteed per-target hit count.
- **06C:** Friendly-slot uncertainty now appears only when the casting record has a positive friendly recipient cap. Enemy-only Dominate keeps a narrow target-choice qualification and does not mention a friendly slot. Packmaster's positive friendly cap retains that uncertainty.
- **08C:** Complete, combined paired lookups add four aligned and cited dimensions: range, ammunition capacity and pool, scoped melee/ranged attack types, and returned passive conditions. They preserve the original `units[]` profiles, order, null/known-none states, variants and evidence. A partial ability or weapon page is identified as partial. This is an additive packet **1.19.0** field; the schema continues to accept earlier reviewed fixtures. It neither applies passives nor computes DPS or a winner. Projected and mode-restricted pair calls omit `comparison`.

## Bounded performance check

Five warm Daemon Prince calls under `cProfile` before the small source-file memoization made **9,155** SQLite `execute` calls and spent **0.807 s** cumulatively; the same five-call profile after the change made **7,335** calls and spent **0.651 s** cumulatively. The memoization uses the existing per-packet source ID, so each source-file row is read once per packet; the new regression test checks that property. These profile totals are indicative and are not a production latency comparison.

The idle fixed 12-single/3-pair local benchmark used 25 warm repetitions per case, compact UTF-8 JSON, and query-plus-serialization timing on Windows 11 ARM64 / Python 3.12.10 / SQLite 3.49.1. Single median/max were **19,113.5 / 107,637 bytes**; pair median/max were **28,327 / 31,786 bytes**. Daemon Prince warm median was **152.43 ms**, p95 **209.59 ms**, and fresh-connection lookup **169.40 ms**. The provisional **100 ms per-case warm-median limit still fails**. A fresh connection does not clear disk cache. Independent prior same-snapshot runs measured candidate 146.79/155.11 ms and baseline 141.94/144.23 ms; these measurements do not prove equal performance or impossibility of further optimization. No option, source fact or evidence was dropped to chase this budget.

## Verification

- `python scripts/verify_sources.py --ctw-root ..\CTW-data-gamma`: passed, 144 files, 76 datasets, 3,181 roster rows, 2,409 keys.
- `python scripts/define_packet_schema.py`; disposable-copy `python scripts/build_packet_fixtures.py --ctw-root <pinned-source>` and `python scripts/validate_packets.py --ctw-root <pinned-source> --generated-examples`: passed, 17 fixtures, 12 source-backed. The disposable copy used byte-identical current schema and validator files; tracked fixtures were not rewritten.
- `python scripts/audit_queries.py --db work\gamma.sqlite --ctw-root ..\CTW-data-gamma --output work\final-query-audit.json`: passed, 2,409 keys, 36,678 locators, zero errors, packet 1.19.0.
- `python scripts/audit_chej_findings.py --db work\gamma.sqlite --output work\final-chej1-audit.json`: passed; zero health, movement or pool disagreements, 14 scoped overrides.
- `python scripts/audit_chej_findings2.py --db work\gamma.sqlite --output work\final-chej2-audit.json`: passed; all 14 child-explosion instances still visible.
- `python scripts/audit_chej_findings3.py --db work\gamma.sqlite --output work\final-chej3-audit.json`: passed; 7/7 classified retained casting-flag uses.
- Focused regressions cover the two Thunderbarge variants, all 14 child chains, Ushabti no-explosion control, Dominate/Packmaster scope, paired ordering/provenance/projection and per-packet source-file memoization.
- `python work/run_suite_review.py` with fresh workspace-created temporary slots: **130 tests passed, zero failures/errors/skips**. The runner works around this Windows sandbox's inaccessible Python-created temporary directories and is ignored local harness code.

The final diff check is recorded in the review handoff. Passing structural tests and pinned-source lookups do not certify engine runtime semantics.
