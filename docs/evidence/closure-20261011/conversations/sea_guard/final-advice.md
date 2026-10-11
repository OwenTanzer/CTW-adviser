Keep the Lothern Sea Guard (Shields) facing the Blue Horrors, hold position, and shoot during their approach. Use nearby support to protect the rear and intercept a flank. This model supports preserving the firing window and frontal protection; it does not establish a reliable solo victory. If a rear attack develops, turn toward it before contact if possible or have another unit intercept it. Turning time and multi-unit support are qualitative advice, not simulated effects.

Resolved identities are High Elf Lothern Sea Guard (Shields), wh2_main_hef_inf_lothern_sea_guard_1, and Blue Horrors of Tzeentch, wh3_main_tze_inf_blue_horrors_0, a shared profile across Daemons of Chaos, Tzeentch, and Warriors of Chaos. No variant ambiguity remained.

With your settings—100 m apart, 120 s, flat unobstructed ground, unmodified custom battle, ultra, rank 0—the Sea Guard hold, the Horrors approach, and both fire and fight. Sea Guard have 165 m range versus 90 m. Sea Guard can fire immediately within the model's 1 s initial delay; Horrors enter range at 2.63 s. At assumed 3.8 m/s closing speed, contact occurs at 26.32 s. The model schedules two Sea Guard firing events and three Horror firing events before contact; these are launches, not guaranteed hits. Both stop firing at contact despite ammunition remaining (22 versus 4 initial capacity). Listed projectile velocities, 45 and 35, provide flight timing; there is no missing-velocity immediate-arrival case or nontrivial projectile-count nesting requiring extra interpretations.

| 120-second result | Frontal attack | Rear attack on Sea Guard |
|---|---:|---:|
| Sea Guard incoming direct missile health damage | 1,198.8 | 2,664.0 |
| Sea Guard incoming melee health damage | 497.5 | 1,426.1 |
| Sea Guard remaining health | 4,423.7 / 6,120 (72.28%) | 2,029.9 / 6,120 (33.17%) |
| Horrors incoming direct missile health damage | 0 | 0 |
| Horrors incoming melee health damage | 1,252.2 | 1,193.2 |
| Horrors barrier absorption, all damage types combined | 1,400 | 1,400 |
| Horrors remaining health | 6,427.8 / 7,680 (83.70%) | 6,486.8 / 7,680 (84.46%) |
| Horrors remaining health + barrier / initial health + barrier | 70.79% | 71.44% |
| Conditional nominal advantage | Sea Guard, narrowly | Blue Horrors |
| Sea Guard below assumed 50% health effectiveness threshold | Not reached | 53 s |

Neither attack has an explosion, so explosion damage is zero in every ledger. Both finish with zero barrier. Horror total attempted incoming damage is 2,652.2 front or 2,593.2 rear, including absorbed damage; zero direct missile health damage does not mean Sea Guard arrows had no effect. Their arrows contributed to exhausting the barrier before health damage from melee.

The controlled variation changes only sides.a.facing from front to rear. Frontal shield block probability goes from 55% to zero, while the Horrors' unmodified melee hit probability rises from 15% to 43%. Sea Guard firing remains enabled in both cases: this isolates defensive facing and does not simulate rear firing arcs, turning, or a second simultaneous attacker. The small reduction in damage they inflict in the rear case comes through the model's casualty/firing feedback.

The frontal advantage is fragile: reducing Sea Guard collision probability from 0.5 to about 0.448, increasing Horror collision probability to about 0.536, or reducing Sea Guard active contacts from 8 to about 7.20 flips it in one-at-a-time tests. Sensitivity corners favor both sides, for both facing scenarios; these are not confidence intervals. Barrier-first versus entity-cap-first makes no material difference here. Verdicts are conditional, with no unresolved verdict inputs; do not convert that into certainty.

Use the range advantage before contact and avoid unnecessarily advancing into the Horrors' short range. Their 20% physical resistance reduces the Sea Guard's nonmagical damage; the Horrors' attacks are magical and flaming. Sea Guard's +16 anti-large melee bonus does not help against these infantry. The source also lists an additional +5 anti-infantry bow attachment sharing the primary ammunition pool, but the evaluator selects the ordinary primary bow only; simultaneous firing or switching eligibility is unresolved. Do not add both attacks. Martial Prowess is listed (+2 attack, +12 defence, deactivation below 25% health) but not applied to this projection. Charge Defence vs Large and Charge Reflection are sourced attributes, not numerical bonuses added here; these Horrors are infantry and default charge duration is zero.

These are uncalibrated expected-damage projections: empirical calibration is null, collision probability is 0.5, complete cycles are assumed reload × 1.25 (13.75 s / 10 s), default active contacts are min(8, living bodies), first-shot delay is 1 s, and historical 8.1.1 combat relations are assumed applicable to patch 9.0. Casualties use pooled expected damage. Barrier recharge, fatigue, detailed formation/obstruction, passive/activated effects and morale are not simulated. Neither nominal run reaches health depletion. The 53 s rear threshold is an assumed combat-effectiveness marker, not routing or death; Sea Guard routing is unknown, and daemonic Horrors cannot rout while their instability/death behavior remains unmodeled.

Evidence uses source commit 595e22764b22e748afdbafafcb0a6258973e2451, store 4, packet 1.20.0, model combat-0.1.4, adapter 0.1.0. Unit baseline is patch 9.0/build 25507028; scoped abilities/effect semantics use 9.0.1/build 25546563. All five evidence sections were complete for both units. Exact source references, source paths, facts, graphs, assumptions and raw ledgers are retained in calls.json.

Both successful connected evaluation data objects were independently compared with identical local CLI invocations using work/adviser.sqlite and PYTHONPATH=src: exact parsed JSON equality for front and rear, no differences. This demonstrates reproducibility, not game accuracy. One failed rear call returned HTTP 429 with an 18-second retry hint; the error and successful retry are preserved. No external service was modified and no synthetic user replies were created.

