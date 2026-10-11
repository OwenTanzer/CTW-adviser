Protect Queen Bess with an interception screen and a nearby reserve that can stop cavalry reaching the gun. Deploy farther back while preserving a clear firing lane. The extra 100 metres helps, but does not make an unsupported gun safe in this projection. Use suitable anti-large troops or a durable blocker to catch the Reiksguard before they enter the artillery position; keep support on its flanks as well as in front. This support advice is qualitative: the two-unit calculation does not simulate a third unit, bracing, path obstruction or a formation screen.

The resolved units are Queen Bess (`wh2_dlc11_cst_art_queen_bess`, shared profile listed for Vampire Coast and Undead Legions) and Empire Reiksguard (`wh_main_emp_cav_reiksguard`). Queen Bess has a 450 m listed range and 50 m minimum range. It is a one-engine artillery unit, with 2,600 engine HP and a separate 4,700 HP across 47 crew; those pools must not be treated as interchangeable. Reiksguard has 60 mounted entities and 6,480 HP.

These are conditional results for 120 seconds, custom battle, ultra, rank 0, unobstructed sight, flat terrain, front facing, Queen Bess holding and firing and Reiksguard approaching. Only starting separation changes between cases.

| Returned projection | 200 m | 300 m |
|---|---:|---:|
| Already in maximum range | Yes, at 0 s | Yes, at 0 s |
| Contact / firing cessation | 25.64 s | 38.46 s |
| Queen Bess shots launched | 1 | 2 |
| Reiksguard incoming direct damage | 37.8 | 75.6 |
| Reiksguard incoming explosion damage | 38.5 | 77.0 |
| Reiksguard incoming melee damage | 34.25 | 33.90 |
| Reiksguard remaining health | 6,369.45 (98.29%) | 6,293.50 (97.12%) |
| Queen Bess incoming melee damage | 2,600.00 | 2,586.21 |
| Queen Bess remaining engine health | 0 | 13.79 |
| Queen Bess remaining crew health | 4,700 | 4,700 |
| Queen Bess total remaining health | 4,700 (64.38%) | 4,713.79 (64.57%) |
| Returned combat-ineffective time for Queen Bess | 108 s | null: not reached in horizon |

Reiksguard has no ranged weapon here, so Queen Bess receives zero direct/explosion damage; both sides absorb zero barrier damage. The model conditionally favors Reiksguard in both cases by remaining health-plus-barrier fraction, not by a simulated battle victory. Neither unit's entire health pool depletes within the horizon. At 200 m, the engine pool depletes while crew remains; engine disablement and the crew threshold needed to keep firing are explicitly unknown. Routing is unknown. At 300 m, the tiny engine remainder and null combat-ineffective time are horizon effects, not evidence of safety.

Why the extra distance matters: it grants about 12.82 seconds before contact and permits the second firing opportunity at 23.5 seconds. At 200 m that opportunity is already inside the 50 m minimum range, so it cannot launch. Shot scheduling uses a 1 s initial delay and an illustrative 22.5 s full cycle (18 s listed reload times 1.25). Launches are not guaranteed hits. Flight uses the sourced positive velocity of 120; no immediate-arrival or unresolved projectile-count branch applies (projectile/volley/burst factors are each 1).

The decisive tactical issue is contact. Keep the enemy away from the engine and intercept early enough that Queen Bess retains firing opportunities. Retarget or stop firing when the melee becomes intermingled: source projectile/explosion fields say they can damage allies, though friendly-fire geometry is not simulated here. Extra distance is useful time for your screen to act, rather than a substitute for one.

Important model conditions: collision probability is an uncalibrated 0.5; splash assumes one affected entity per collision despite the sourced 12 m radius; melee defaults to one Queen Bess primary contact and eight Reiksguard contacts; charge duration defaults to zero, so the cavalry charge bonus is not applied. Historical 8.1.1 damage relations are assumed applicable to patch 9.0. Empirical calibration is null. Health-capped direct damage is smaller than raw projectile damage; do not infer live casualty allocation from these pooled estimates.

Both verdicts return `bounds_cross: true`, although their listed collision-only corners all favor Reiksguard. The reported one-at-a-time active-contact flip thresholds for Reiksguard are approximately 0.348 at 200 m and 0.650 at 300 m, versus the default 8. They are sensitivity results, not practical fractional troop counts or confidence intervals. They reinforce how much the result depends on keeping cavalry off the gun.

Source evidence includes Black Powder Aplenty (listed missile/explosion damage multipliers of 1.3 with an ammunition-threshold condition), Crumbling and Disintegrating. The projectile/explosion also links a 10-second contact phase with 0.4 multipliers to speed and charge speed. These sourced effects could materially affect a real approach, but runtime activation/execution is unverified and the evaluator does not apply them. I have not manually added their bonuses or slowdown. Crew targetability is unknown in the source; this baseline targets the known targetable primary engine and does not claim to simulate cavalry attacking crew. Fatigue, detailed splash/penetration, morale, and terrain physics are also outside the projection.

Evidence/model: source commit `595e22764b22e748afdbafafcb0a6258973e2451`; source packet 1.20.0; store schema 4; model combat-0.1.4; adapter 0.1.0. Base unit data is patch 9.0/build 25507028, with scoped shared-ability and native-stat-definition supplements from patch 9.0.1/build 25546563; this is not a claim that all unit data is patch 9.0.1.

Both complete connector evaluation data objects exactly equal the corresponding local CLI JSON outputs; there are no differences. This establishes reproducibility, not in-game accuracy. Exact arguments, full results, scenarios, commands and comparisons are retained alongside this advice.
