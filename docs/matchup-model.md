# First two-unit combat calculation (issue #5)

`ctw_adviser.combat.evaluate_matchup(queries, unit_a, unit_b, *, scenario=None,
subculture_a=None, subculture_b=None)` is the sole calculation entry point. It
calls the verified `Queries.get_matchup_evidence(..., limit=256,
include_diagnostics=True)` and returns a JSON-safe dictionary. Name resolution,
including ambiguous variants, belongs to `Queries`; callers must present its
candidate list rather than choosing by label. The MCP adapter can call this
function directly and return the result as structured content. No transport
schema or server packaging is defined here.

The equivalent local command is:

```sh
PYTHONPATH=src python -m ctw_adviser.cli evaluate --db work/adviser.sqlite \
  "Lothern Sea Guard (Shields)" "Blue Horrors of Tzeentch" \
  --scenario '{"separation_metres":100,"sides":{"a":{"order":"hold","active_contacts":8},"b":{"order":"approach"}}}'
```

On PowerShell set `$env:PYTHONPATH='src'` and quote the JSON for PowerShell.
The command and the library serialize the same object; the optional full-store
test checks exact equality. `Bloodletters of Khorne` is a resolvable exact name;
`Bloodletters` is not. The shielded Sea Guard variant has exact key
`wh2_main_hef_inf_lothern_sea_guard_1`; the plain name resolves to an unshielded
record.

## Scenario and result contract

Calculator model `combat-0.1.4` uses the immediate-arrival firing-opportunity
convention for missing or nonpositive source velocity. The changed model
version distinguishes these projections from earlier zero-shot results under
the same source packet and data commit.

The `scenario` object supports `mode=custom_battle`,
`baseline=unmodified_ultra_rank_0`, `separation_metres` (default 200),
`duration_seconds` (120), `metres_per_second_per_speed_point` (1),
`path_length_factor` (1), `terrain_speed_factor` (1), `line_of_sight` (true),
`barrier_damage_order` (`barrier_first` or `entity_cap_first`; represented
default `barrier_first`), and `historical_relations_apply_to_patch_9` (true).
The last flag explicitly
accepts the working 8.1.1 combat equations for this 9.0 projection; false
suppresses damage and yields an indeterminate verdict. Terrain and speed factors
are caller assumptions, not observed coordinate conversion.

`sides.a` and `sides.b` each accept `order` (approach, hold, retreat), `fire`,
`fight`, `facing` (front, side, rear), `collision_probability` (default 0.5),
`firing_entities` (attached component count), `cycle_seconds` (illustrative
default: listed projectile reload times 1.25), `first_shot_delay_seconds` (1),
`flight_seconds` (optional measured or explicitly assumed flight duration;
otherwise missing/nonpositive source velocity uses immediate arrival),
`projectiles_per_cycle` (1 only when the source projectile, volley and burst
counts are all one), `explosion_entities_per_collision` (1), `active_contacts`
(default min(8, living primary bodies)), `charge_duration_seconds` (0),
`target_component_role` (primary), and `combat_effective_fraction` (0.5).
For a nonprimary target with unknown targetability, the caller may explicitly
set `assume_targetable=true` and `assume_unit_protection_for_component=true`;
without both assumptions damage to that component is withheld. Known false
targetability cannot be overridden. Component size, including small artillery
crew, selects the size bonus instead of the primary engine size.
Unknown fields or incompatible baselines fail visibly. The 0.5 collision
probability, cycle multiplier, firing/contact counts and speed conversion are
uncalibrated model inputs. Card accuracy is never used as collision probability;
listed reload is never treated as the complete firing cycle.
When listed reload is absent, no firing cycle is derived and shots are withheld
unless the caller supplies `cycle_seconds`; an applicable missing cycle makes
the verdict indeterminate.

The response separates `snapshot` (including the serving contract hash),
`source_fingerprints`, `source_provenance`, `source_payload_graph` and `source_facts` from
`scenario_assumptions`, `empirical_calibration` (currently null), `derived`,
`verdict`, `limitations` and `tactical_contingencies`. `derived.phase_timing`
shows closing speed, range entry, minimum range, listed velocity and contact.
`derived.ledgers` has two records in A/B order, each with direct projectile,
explosion, melee, barrier absorption and overkill, component health and estimated
living entities, firing events and separate stopping fields. The verdict uses
remaining health plus barrier fraction at the chosen horizon; it is conditional
on assumptions and is never a morale or battle winner. Collision probabilities
are tested at the four extreme corners; sampled one-parameter thresholds show
changes that can flip the nominal ordering. These are sensitivity calculations,
not confidence intervals. A crossing or major unresolved mechanic should be
explained alongside the nominal side.
`verdict.unresolved_inputs` contains structured records with `side`,
`source_path`, `code` and affected `calculation`. An applicable null source
value, unresolved supply or attack status, or required scenario assumption
makes the verdict indeterminate. Missing/nonpositive velocity alone does not
withhold a verdict; its immediate-arrival approximation appears in limitations.
`represented_point_ordering` and any partial ledgers then show only the
calculation under the omitted-input fallback; they are not a favored verdict.
If component health or count needed to construct a health pool is unknown,
the projection is withheld and `derived.phase_timing`, `event_mechanics` and
`ledgers` are null. Numeric zero remains known zero. Fields on disabled attack
channels and movement speed for a holding unit do not create missing-input
records. The source packet retains the original nulls.
`verdict.barrier_damage_order_sensitivity` reports both orderings when a barrier
is present. If their health, barrier or overkill ledgers differ, the default
projection is indeterminate until the caller explicitly selects an order.
Explicit selection makes the result conditional; neither order is established
as observed game behavior.

## Calculation boundary

Straight-line approach uses relative speed and declared path/terrain factors.
Shots are discrete and limited by the selected attack's ammunition pool. Range,
minimum range and living shooters are checked at the exact scheduled shot time;
arriving impacts are processed before later firing opportunities. Flight time
uses shot-time distance/listed velocity only when the source velocity is positive.
Missing, zero or negative native velocity is preserved as source evidence and
uses an immediate-arrival approximation at each valid firing opportunity.
An explicit `flight_seconds` overrides either flight-time path. Collision
probability remains an independent expected-hit assumption; a volley is a
launch event, not a guaranteed hit. Firing stops at contact, while already
launched projectiles may arrive afterward within the projection horizon.
Null range, minimum range, damage, ammunition supply or reload fields on an
enabled attack do not silently establish zero damage or zero shots. Source
armour, ward, resistance, shield, melee defence, spell tags and movement speed
are checked when their calculation paths are enabled.
The model selects a single default
ranged attack and primary melee attack. Nontrivial projectile, volley and burst
nesting requires `projectiles_per_cycle`; otherwise that attack is omitted with
a gap. Damage first resolves armour, AP, applicable ordinary resistances and
front-facing shield probability for a direct projectile. Separate explosion
events use an assumed affected-entity count. A sourced explosion `is_spell=true`
adds target spell resistance under the declared historical damage relation.
Barriers absorb expected damage before health. `barrier_first` absorbs attempted
damage before the per-entity health cap; `entity_cap_first` caps each expected
hit before barrier absorption. Their different barrier use and overkill are
reported. The historical melee relation supplies hit probability, facing
defence factor, size bonus and charge decay. The integration splits at the end
of a charge window, including windows shorter than one second. Active contacts
and living primary bodies limit melee volume. Expected per-hit damage after
the selected barrier order is capped by health per entity, with overkill
reported. Casualties are estimated from pooled health;
they do not reconstruct individual hit allocation or animation schedules.

Health depletion, component casualties, combat-effectiveness threshold,
firing cessation, contact and routing remain separate. Contact ends this
model's firing schedule. Engine disablement and crew-based firing cessation are
unknown without a validated rule, even if a component reaches zero health.
`bounds_cross` includes tested contact-count switches as well as collision
probability corners; `one_parameter_flip_thresholds` identifies the sampled
change. An unresolved targetability or component protection that
could change the outcome prevents a favored verdict.
Daemonic source attributes distinguish rout inapplicability from unknown
instability/death behavior. Other morale and special death effects are not
projected. Passives, activated effects, fatigue, collision attacks, splash
selection/distribution, penetration, shrapnel, other spell-specific behavior,
terrain physics and actual projectile dispersion remain in `limitations` or
source coverage. The native 9.0.1 ability payload extension remains evidence;
it is not silently applied to 9.0 base profiles.

## Standard calculator workflow

Resolve both units, call `evaluate_single_unit_matchup` with the intended
separation, orders and horizon, then inspect `source_facts`,
`scenario_assumptions`, `derived.phase_timing`, `derived.ledgers`,
`verdict.unresolved_inputs` and `limitations`. The caller need not know
projectile speed. Positive source velocity schedules shot-time flight;
missing or nonpositive velocity automatically uses the labeled
firing-opportunity immediate-arrival approximation. Supply `flight_seconds`
only when a measured or deliberately assumed duration is available. State
which flight basis applied and distinguish `shots_fired_per_shooter` and
`discrete_firing_events` from collision-weighted expected damage. Check range
entry, minimum range, first-shot delay, cycle, ammunition, firing entities,
targetability and contact cessation before interpreting a zero ledger.
If immediate-arrival damage is material, rerun with `flight_seconds` set to
that side's `scenario_assumptions.sides.<side>.cycle_seconds`. This value comes
from the source reload and declared cycle multiplier when available, or from
an existing explicit cycle assumption; it is an illustrative delayed-arrival
case, not a measured flight time or physical upper bound. Keep all other
scenario inputs fixed. Report the nominal estimate and the conditional range
of modeled damage and ordering across the two cases. `bounds_cross` covers
collision/contact sensitivity, not flight timing, and cannot replace this
rerun. No projectile-speed measurement is required from the user.
When source projectile, volley or burst counts differ from one, inspect all
three counts and run explicit `projectiles_per_cycle` cases informed by them.
For one nontrivial count, compare one projectile per cycle with that sourced
count. For multiple nontrivial counts, compare one with each sourced factor
individually; do not multiply them without a reviewed composition rule.
Label each case as a scenario interpretation, not proven engine cadence;
materially different volley or burst timing remains unsupported. If no
defensible case captures a consequential nesting, leave the ranged schedule
unresolved and say why. Do not ask the user for technical source fields or
infer a count from card accuracy.
Use the verdict and sensitivity as conditional projections, and report other
unresolved inputs rather than filling them from projectile speed.

### Spells and activated abilities (#20)

Use the same resolve → retrieve → evaluate → explain flow:

1. **Resolve.** Resolve the units with `resolve_unit` and the effect with
   `resolve_effect`. A shared label returns normal, bound, quest and overcast
   candidates; present them rather than choosing. Passing a `unit_key` limits
   effect candidates to that unit's links. Start either from a unit's
   `activated_options[*].detail_ref` (`effect:<key>`) or from a named spell;
   both reach the same evidence.
2. **Retrieve.** Read `get_effect` before calculating: costs, timing, distinct
   distance settings, recipients, phases, payload paths, failure branches and
   qualified access. A link is qualified access, not proof of acquisition.
3. **Evaluate damage** with `evaluate_effect_damage` (effect, target, optional
   caster and `cast_distance_metres`). Report `status`, `unresolved_inputs`, the
   components, totals and casualty bounds.
   - Vortex and contact-phase totals need explicit application counts.
   - Phase-linked damage defaults to the source-implied duration ÷ interval schedule.
   - Shared definitions are counted once, with an all-routes upper bound.
   - `self_effects` and `conditional_branches` are never target damage.
4. **Evaluate a buff or debuff** with `evaluate_effect_engagement`: the effect,
   the two units, the receiving side, the relation (`friendly` or `enemy`) and
   the same scenario you would pass to `evaluate_single_unit_matchup`.
   - Report the `active_window` comparison first and the `horizon` upper bound second.
   - List changed inputs (including `clamped` ones) and unsupported effects, and
     report whether `sensitivity.effect_changes_favored_at` is non-empty.
   - The default result is compact; request `include_matchups` only when the
     full #5 ledgers are needed.
5. **Explain.** Separate source facts, scenario assumptions and calculated
   values. Say which components were blocked or need assumptions, and never
   present a `partial` total as complete. These are uncalibrated projections.

## Verification and adding cases

`python -m unittest discover -s tests -p test_combat.py -v` runs arithmetic,
source-packet, controlled mutation, mixed/melee/ranged, shield, explosion and
conditional-result tests. Set `CTW_ADVISER_DB` to a verified pinned SQLite
artifact to run the four optional real-`Queries` pairs and CLI equality test.
The checked-in source-backed packets are design projections with unresolved
weapon/passive coverage. They test mechanics, not roster-wide completeness or
live-battle accuracy. Add a pair by supplying resolved identities and a scenario
to `evaluate_matchup`; do not add a unit-name branch. The held-out pair is Queen
Bess/Reiksguard in the optional store test; Queen Bess/Wargor exercises shield
and explosion arithmetic in the source-backed tests.

Live validation remains open. For each named fixture, record the exact resolved
keys, scenario JSON and model result before a battle; then measure contact,
first shot, subsequent cycles, projectile collisions, damage, casualties,
component losses and morale state on the pinned game build. Repeat a controlled
separation, facing, contact or order mutation. Report observed minus predicted
times and health and keep any empirical calibration separate from source facts.
No such observations are claimed by this increment.
