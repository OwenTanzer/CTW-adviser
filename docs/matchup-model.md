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

The `scenario` object supports `mode=custom_battle`,
`baseline=unmodified_ultra_rank_0`, `separation_metres` (default 200),
`duration_seconds` (120), `metres_per_second_per_speed_point` (1),
`path_length_factor` (1), `terrain_speed_factor` (1), `line_of_sight` (true),
and `historical_relations_apply_to_patch_9` (true). The last flag explicitly
accepts the working 8.1.1 combat equations for this 9.0 projection; false
suppresses damage and yields an indeterminate verdict. Terrain and speed factors
are caller assumptions, not observed coordinate conversion.

`sides.a` and `sides.b` each accept `order` (approach, hold, retreat), `fire`,
`fight`, `facing` (front, side, rear), `collision_probability` (default 0.5),
`firing_entities` (attached component count), `cycle_seconds` (illustrative
default: listed projectile reload times 1.25), `first_shot_delay_seconds` (1),
`projectiles_per_cycle` (1 only when the source projectile, volley and burst
counts are all one), `explosion_entities_per_collision` (1), `active_contacts`
(default min(8, living primary bodies)), `charge_duration_seconds` (0),
`target_component_role` (primary), and `combat_effective_fraction` (0.5).
Unknown fields or incompatible baselines fail visibly. The 0.5 collision
probability, cycle multiplier, firing/contact counts and speed conversion are
uncalibrated model inputs. Card accuracy is never used as collision probability;
listed reload is never treated as the complete firing cycle.

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

## Calculation boundary

Straight-line approach uses relative speed and declared path/terrain factors.
Shots are discrete and limited by the selected attack's ammunition pool; their
flight time uses distance/listed velocity. The model selects a single default
ranged attack and primary melee attack. Nontrivial projectile, volley and burst
nesting requires `projectiles_per_cycle`; otherwise that attack is omitted with
a gap. Damage first resolves armour, AP, applicable ordinary resistances and
front-facing shield probability for a direct projectile. Separate explosion
events use an assumed affected-entity count. Barriers absorb expected damage
before health. The historical melee relation supplies hit probability, facing
defence factor, size bonus and charge decay. Active contacts and living primary
bodies limit melee volume. Expected per-hit damage is capped by health per
entity, with overkill reported. Casualties are estimated from pooled health;
they do not reconstruct individual hit allocation or animation schedules.

Health depletion, component casualties, combat-effectiveness threshold,
firing cessation, contact and routing remain separate. Contact ends this
model's firing schedule. Engine disablement and crew-based firing cessation are
unknown without a validated rule, even if a component reaches zero health.
Daemonic source attributes distinguish rout inapplicability from unknown
instability/death behavior. Other morale and special death effects are not
projected. Passives, activated effects, fatigue, collision attacks, splash
selection/distribution, penetration, shrapnel, spell-specific resistance,
terrain physics and actual projectile dispersion remain in `limitations` or
source coverage. The native 9.0.1 ability payload extension remains evidence;
it is not silently applied to 9.0 base profiles.

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
