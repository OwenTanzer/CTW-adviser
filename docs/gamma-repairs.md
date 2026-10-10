# Gamma G1/G2 repair evidence

Local repair candidate based on adviser `c92467c169edd2f6ef9ff7d7125b26ddf1a6d8cb`
and the unchanged CTW-data pin `595e22764b22e748afdbafafcb0a6258973e2451`.
Packet version remains 1.18.0. This record supports independent review; it
does not claim a merge, deployment, selected equipment, or engine runtime timing.

## G1: source-defined replacement

The ordinary packet and passive detail now resolve the retained replacement set
for four reviewed core passives. Grim Discipline supersedes Martial Mastery and
Martial Prowess; Grand Arcane Conduit supersedes Arcane Conduit; upgraded For the
Slaughter! supersedes its base; upgraded Unending Feast supersedes the base
ability localized as Blighted Feast. These are five source set-element edges.
The Grand Arcane Conduit **set key** is
`wh2_dlc17_character_passive_grand_arcane_conduit`, distinct from its owning
ability key `wh2_main_character_passive_grand_arcane_conduit`.

The wording states required effect enabling where retained and says the packet
does not identify the selected configuration or support adding superseded
bonuses. Raw effects, replacement links and detail references remain available.
No other supersession set receives this reviewed prose.

## G2: interception conditions

The 24 Gamma inventory entries now place their positive retained
`target_intercept_range` beside the intercept condition without changing its
predicate or role. The same source-backed formatting also clarifies three
intercept conditions whose surrounding summaries already mentioned a distance.
Absent, zero and native negative settings are not rendered as distances.

For Spawn-Kin (Kroxigors), the condition says no Skink allies in the 35-metre
interception range. Battle Songs keeps its friendly-effect radius at 55 metres
and separately states a 100-metre enemy interception range under **Deactivates
when**. Neither condition is promoted into an activation trigger.

## Reproduction

Using a source checkout at the pin above:

```text
python scripts/verify_sources.py --ctw-root ../CTW-data-gamma
python scripts/build_snapshot.py build --ctw-root ../CTW-data-gamma --output work/gamma.sqlite
CTW_DATA_ROOT=../CTW-data-gamma python -m unittest discover -s tests -v
python scripts/validate_packets.py --ctw-root ../CTW-data-gamma
python scripts/audit_queries.py --db work/gamma.sqlite --ctw-root ../CTW-data-gamma --output work/gamma-query-audit.json
python scripts/audit_chej_findings.py --db work/gamma.sqlite --output work/gamma-chej1-audit.json
python scripts/audit_chej_findings2.py --db work/gamma.sqlite --output work/gamma-chej2-audit.json
python scripts/audit_chej_findings3.py --db work/gamma.sqlite --output work/gamma-chej3-audit.json
```

On the Windows review host, unittest discovery required precreated workspace
temporary directories; an ignored local runner applied that environment-only
workaround. **125 tests passed, no failures/errors/skips.** Source verification
passed for 144 files, 76 datasets, 3,181 roster rows and 2,409 unit keys.
The 10 checked-in fixtures passed; regenerated fixtures in a disposable archive
copy passed 17 checks (12 source-backed). Query audit checked 2,409 keys and
36,678 locators with zero errors. The first findings audit found zero health,
movement or ammunition-pool discrepancies; the second found 14 visible child
explosion instances; the third checked all 7 retained casting-flag uses.

Two new tests compare all five replacement edges and all 24 interception
distances against pinned source rows, then verify ordinary/detail agreement,
source references and negative controls. Tests preserve Battle Songs' 55/100
distinction and a passive with no replacement.

## Provisional efficiency check

The Gamma report's fixed set of 12 singles and three pairs was remeasured on a
local Windows ARM64 host (Python 3.12.10 / SQLite 3.49.1), 25 warm query-plus-
compact-serialization repetitions per case, after tests and audits completed.
This is **not** service, connector, model, or production latency; a fresh SQLite
connection did not clear the operating-system disk cache.

The repaired code had a single-packet median of 19,113.5 bytes and maximum
107,637 bytes; pair median 26,204 and maximum 29,553. The median of case
medians was 23.11 ms, maximum case p95 197.54 ms, and maximum fresh-connection
lookup 196.96 ms. Size, p95 and fresh-connection provisional budgets passed.
The Daemon Prince's warm median was 185.8 ms, exceeding the report's 100 ms
provisional per-case budget. The unchanged `c92467c` code measured 189.25 ms
on the **same machine and same snapshot** (107,155 bytes versus 107,637), so
this observation does not show a Gamma repair regression. Brian's earlier
Linux x86_64 local timing and this Windows ARM64 timing are not interchangeable.

Passing structural tests and local timings do not prove source mechanics are
combat-engine truth. Gamma criterion 9 remains bounded by the provisional
benchmark and its platform-dependent warm-median exception. Optional behaviour-
link prose cleanup (G3) was outside this patch.
