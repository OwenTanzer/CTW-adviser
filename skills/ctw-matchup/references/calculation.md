# Calculation interpretation

Workflow 1.0.0; repository `docs/matchup-model.md` defines the full contract.

Read source facts/provenance separately from scenario assumptions, derived values and empirical calibration (currently null). Inspect both ledgers, not just the verdict.

Consequential defaults: collision probability 0.5; complete firing cycle illustratively listed reload × 1.25; first shot delay 1 s; explosion affected entities 1; contacts min(8, living primary bodies); charge duration 0 s; speed-to-metres conversion 1; path/terrain factors 1; combat-effective threshold 50%. Historical 8.1.1 combat relations are assumed applicable to patch 9.0 unless disabled. These are assumptions, not measurements. Card accuracy is not collision probability; reload is not an established complete cycle.

Missing/nonpositive projectile velocity uses labeled immediate arrival at valid firing opportunities in combat-0.1.4. When its damage matters, rerun with `sides.<shooter>.flight_seconds` equal to that side's returned `cycle_seconds`, all else fixed. This is an illustrative delayed-arrival case, not measured flight or a physical upper bound. If cycle is null, obtain a defensible explicit assumption or leave firing unresolved. Report estimates and conditional range across cases; built-in `bounds_cross` does not cover flight uncertainty.

Nontrivial projectile/volley/burst nesting requires explicit `projectiles_per_cycle`. Inspect all factors. If one is nontrivial, compare 1 with that factor. If several are nontrivial, compare 1 with each separately; never multiply without a reviewed composition rule. Label alternatives as interpretations. If none defensibly captures consequential nesting, retain the unresolved schedule. Cadence and dispersion remain unsupported.

Shots are launch events, not guaranteed hits. Check range entry, minimum range, line of sight, first-shot delay, cycle, ammunition, living shooters, targetability and contact cessation before explaining zero damage. Firing stops at contact; launched impacts may arrive later within the horizon. Direct/explosion contributions are separate. Positive velocity uses shot-time distance; explicit flight overrides it.

Health depletion, pooled-health casualty estimates, combat effectiveness, contact, firing cessation, routing and engine disablement are distinct. Unknown artillery crew targetability/protection requires explicit assumptions. Daemonic rout inapplicability does not simulate instability/death behavior.

Missing applicable inputs may withhold calculations or make the verdict indeterminate. `represented_point_ordering` is only fallback ordering, not a favored verdict. Read `verdict.unresolved_inputs`. Barrier-order sensitivity can make the default indeterminate; explicit `barrier_damage_order` is a conditional interpretation, not an observed engine rule. Present both if materially different.

Passives, activated effects, fatigue, collision attacks, detailed splash distribution, terrain physics and universal morale simulation are not automatically applied. Do not manually add them to the shared result. No numerical advice may exceed returned evidence.
