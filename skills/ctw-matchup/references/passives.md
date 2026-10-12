# Conditional passive scenarios (workflow 1.2.0)

Discover the actual evaluator schema first. Combat model 0.2.0 adds per-side
`passives`, an array of `{key, initial_active, equality, reactivation,
condition_assumptions}`. Keys must come from that unit's sourced attached passive
inventory. The caller supplies activation assumptions, never numeric modifiers.

For full-health Clanrat Spears with Strength in Numbers, use:

```json
{"key":"wh2_main_unit_passive_strength_in_numbers","initial_active":true,"equality":"active","reactivation":"unresolved"}
```

Rerun with only `initial_active:false` changed. Keep all other choices identical.
Read `source_facts` for immutable base stats, `derived.ledgers[*].effect_phases`
for effective defence, speed and leadership, and `passive_coverage` for source
references, recipient side, activation basis and unsupported channels. The
initial `event_mechanics` uses the initial effective inputs; phase ledgers describe
subsequent changes. Leadership does not predict routing.

`initial_health_fraction` defaults to 1. Health predicates use summed component
health divided by source base total, excluding barrier. `equality` is an explicit
scenario choice (`active` default or `inactive`) with a 1e-9 fraction tolerance;
it is not a verified engine rule. Initial ineligible effects are suppressed even
if initially requested. `reactivation` defaults to unresolved (kept inactive after
recovery); `when_eligible` or `never` are explicit assumptions, not source facts.
General healing is not modeled; recovery is tested through controlled state traces.

Melee health transitions occur at bounded integration windows, default 0.1 s
(`passive_step_seconds`, .01–1). Rerun at half the step if a transition materially
affects the decision, compare actual damage/timing, and report sensitivity. This
is not an exact engine event simulator. Projectile arrivals trigger immediate
condition reevaluation; movement/contact are recomputed from remaining distance.
A speed change before the first launch recomputes range entry and restarts the
assumed shot delay. Report this timing approximation when material.

For other supported self passives, inspect conditions. Non-health deactivation
predicates require explicit `condition_assumptions` mapping the exact sourced key
to true (predicate holds, effect inapplicable) or false. For Scurry Away!, an
illustrative low-morale case uses `morale_is_higher_than_wavering:false`; the model
does not derive morale. Do not combine overlapping speed effects: stacking and
refresh are unsupported. Finite duration, external recipients, enabling, intensity
and complex lifecycle cases fail visibly; unsupported effect kinds remain in
coverage. Apply reasonable labeled cases where supported; qualify only the
unsupported dependent calculation.

Never infer a battle winner from a modeled health advantage, silently treat an
unselected passive as applied, or replace a failed modifier input with zero.
