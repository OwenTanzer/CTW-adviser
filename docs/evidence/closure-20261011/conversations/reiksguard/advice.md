Approach promptly along the shortest unobstructed route and keep the Reiksguard committed to contact. At 100 m the same order makes contact about 12.8 seconds earlier. These calculations support closing the distance, but do not establish that starting at 100 m prevents the first shot or reduces total damage.

The resolved units are Empire Reiksguard (`wh_main_emp_cav_reiksguard`, `wh_main_sc_emp_empire`) and Greenskins Doom Diver Catapults (`wh_main_grn_art_doom_diver_catapult`, `wh_main_sc_grn_greenskins`). Source commit 595e22764b22e748afdbafafcb0a6258973e2451, store 4, packet 1.20.0, model combat-0.1.4, adapter 0.1.0. Unit baseline is patch 9.0/build 25507028; scoped supplemental projectile/ability records carry patch 9.0.1/build 25546563. This is not a claim that all unit stats are from 9.0.1.

The baseline uses 120 seconds, unmodified custom battle, ultra, rank 0, flat unobstructed ground, front facing, Reiksguard approaching and Catapults holding, fire/fight enabled, path and terrain factors 1. No user clarification replies were invented. The evaluator assumes 7.8 m/s movement from source run speed, no acceleration; collision probability 0.5; first shot at 1 second; a 22.5-second complete firing cycle (18-second reload × 1.25); one projectile per firing cycle and one explosion victim per collision; eight Reiksguard and four artillery primary-body melee contacts; zero charge duration, so the sourced charge bonus 62 is not applied. Empirical calibration is null.

| Returned measure | 200 m | 100 m |
|---|---:|---:|
| Catapults already in range | 0 s | 0 s |
| Contact and modeled firing cessation | 25.641 s | 12.821 s |
| Catapult shots per shooter / firing events | 1 / 1 | 1 / 1 |
| Reiksguard incoming direct damage | 151.200 | 151.200 |
| Reiksguard incoming explosion damage | 40.667 | 40.667 |
| Reiksguard incoming melee damage | 25.198 | 25.251 |
| Reiksguard health at 120 s | 6262.936 / 6480 | 6262.882 / 6480 |
| Catapult incoming melee damage | 1912 | 1912 |
| Catapult incoming direct/explosion damage | 0 / 0 | 0 / 0 |
| Catapult health at 120 s | 2120 / 4032 | 2120 / 4032 |
| Catapult modeled combat-ineffective time | 52 s | 40 s |
| Conditional nominal favored side | Reiksguard | Reiksguard |

Neither side has a barrier; absorption is zero. The remaining-health comparison is approximately 96.65% versus 52.58%. The evaluator estimates 58 surviving cavalry bodies by pooled health; this is not a measured casualty count. Reiksguard have no ranged attack.

Why there is only one firing event even at 200 m: Catapults have range 400 m and minimum range 20 m. With the assumed movement, the cavalry enter the minimum-range zone at (200−20)/7.8 = 23.077 seconds. The second scheduled launch would be 23.5 seconds (1 + 22.5), when separation is only 16.7 m, so it is invalid. At 100 m minimum range is reached at 10.256 seconds and contact at 12.821 seconds; again the first launch remains allowed and the second is prevented. Four engines firing once does not mean four guaranteed hits. Starting closer suppresses firing earlier but does not save a volley under this particular cadence.

The projectile source reports velocity −1, not a usable physical flight speed. I therefore reran both distances with flight_seconds=22.5 (the returned complete cycle), changing nothing else. This is an illustrative delay, not measured flight time or an upper bound. In both delayed cases the first impact is at 23.5 seconds; at 100 m this is after contact, but previously launched shots can still land. Both distances retain identical health and damage results to their immediate-arrival baselines, apart from insignificant floating-point rounding in the 100 m attempted-damage accumulator. The immediate/delayed cases therefore give the same modeled 191.867 ranged health damage. Actual flight, homing, penetration and splash distribution are not reconstructed.

Keep artillery components separate: there are four engines with 1912 total HP and 40 separate crew with 2120 total HP. The default target is the primary engine pool. All 1912 applied cavalry damage is to that pool; crew HP remains untouched because crew targetability is unknown, not because the crew are proven invulnerable. Total-health depletion is null for both units. The 52/40-second combat-ineffective marker uses the assumed 50% primary-body effectiveness threshold, not total-health depletion, routing or a verified engine-disable rule. Firing cessation at contact is a model policy. Engine disablement and crew-based firing cessation remain explicitly unknown. Do not interpret the 2120 remaining crew HP as a resolved cleanup fight.

The verdict is conditional, not indeterminate, with no material unresolved inputs in the chosen primary-target scenario. All collision-probability corners (0 to 1) favor Reiksguard, with roughly 93.69–99.61% Reiksguard health remaining against 52.58%; those corners are not confidence intervals. The returned bounds_cross is nevertheless true because contact sensitivity finds a one-at-a-time flip near 0.381 active Reiksguard contacts at 200 m or 0.348 at 100 m versus the default eight. These fractional thresholds are sensitivity parameters, not literal formations. They reinforce that reaching and maintaining useful contact is the important modeled condition; they do not prove a guaranteed battle winner.

Qualitatively, avoid detours or pauses that prolong exposure, and avoid enemy interception that prevents contact. Cover or a flank can matter in a real battle, but this flat unobstructed scenario does not quantify them. The source has homing parameters, so do not treat zigzagging as a guaranteed dodge. Front-facing shield blocking is simplified in the model (30% applied to direct damage, none to explosion); actual projectile shield eligibility is unverified. Fatigue, real charge impact, collision attacks, passive/activated modifiers, morale and detailed terrain physics are omitted; historical 8.1.1 combat relations are assumed applicable to patch 9.0.

Source evidence was complete for returned components, weapons, attributes, abilities and activated options (no truncated relevant sections): Reiksguard speed is from record 7b179242cbee121c7c14:1177; engine/crew components from 23de8daf4e757f0860fb:1111 and :1112; Doom Diver weapon/projectile from 5e78e24b332add8fcb5e:1358 and f4787b4b05a6cee9d93c:723; explosion from b90c197e7231bba870ce:305; homing from 02c68eb6531d2db41c68:3. Full source paths, checksums, lineage and raw records are retained in calls.json.

All four evaluations were independently run through PYTHONPATH=src python -m ctw_adviser.cli evaluate --db work/adviser.sqlite with exactly the same unit identities and scenario JSON. Connector content.data and CLI output match exactly after canonical JSON key ordering, including numeric types, nulls, all assumptions, source facts, ledgers and verdicts. The structured transport normalizes some integer-valued floats to integers; these representation-only differences are recorded separately. This establishes reproducibility, not in-game accuracy.

