# Single-cast spell/ability damage — issue #20, increment A

`ctw_adviser.effect_calc.evaluate_effect_damage(queries, effect, target, *,
scenario=None, caster=None, subculture=None, target_subculture=None)` returns the
expected damage of one cast of one exact spell or activated-ability variant against
one resolved unit. It consumes the #19 `get_effect` packet and the canonical
target unit packet, and reuses the #5 damage relation (`combat._damage_per_hit`)
and health pools (`combat._pool`). It adds no source facts or second formula
set. Model version: `effect-damage-0.1.0`.

```sh
PYTHONPATH=src python -m ctw_adviser.cli effect-damage --db work/adviser.sqlite \
  wh_main_spell_heavens_comet_of_casandora_upgraded "Lothern Sea Guard"
PYTHONPATH=src python -m ctw_adviser.cli effect-damage --db work/adviser.sqlite \
  "Bound Fiery Convocation" "Lothern Sea Guard" --caster wh2_main_hef_cha_teclis_0 \
  --scenario '{"vortex_entities_per_application":10,"vortex_applications":3}'
```

The MCP adapter exposes the same function as `evaluate_effect_damage`. Library,
CLI and MCP return identical structures for identical inputs, which is tested.

## What is calculated

The calculator walks the effect's payload graph from each casting root, per
route. Multiplicity comes only from source counts: bombardment
`num_projectiles`, shrapnel `amount` and `num_vortexes`.
Dangling graph references fail with `dangling_payload_reference`; a missing
linked node never silently lowers the total. Explicitly mapped external
references for supersession, behavior and formation resolve through
`detail_refs`, remain visible as unsupported components and are not treated as
damage-graph roots. Every result citation must exist in the same-snapshot
source packets' provenance maps before the result is returned.

| Component | Per entity | Count | Totals |
| --- | --- | --- | --- |
| Direct projectile | shared relation, missile kind (armour, AP, ward/physical/missile/fire/spell resistance, front shield) | launched × `projectile_hit_probability` × (1 − shield block); one entity per hit | calculated |
| Explosion | shared relation, explosion kind | launched × `entities_per_explosion` | calculated |
| Vortex | shared relation per application | `num_vortexes` × `vortex_entities_per_application` × `vortex_applications` | only when both counts are supplied; otherwise the per-application value is shown and the total is unresolved |
| Damaging contact phase | raw `damage_amount` (protection application unresolved) | affected entities × ticks, capped by `max_damaged_entities` | source-implied `floor(duration / hp_change_frequency)` ticks when positive; scenario override; partial |
| Outward enemy phase (for example Spirit Leech) | raw `damage_amount` (protection and intensity unresolved) | affected entities × applications, always capped by positive `max_damaged_entities` | source-implied `floor(duration / hp_change_frequency)` applications when positive; scenario override; partial |

The spell-resistance flag comes from each payload's `is_spell` field. Magic and
fire flags come from `is_magical` and `ignition_amount`. Totals apply the
target barrier first (`barrier_first`), cap per-entity damage at entity health,
and report overkill. Casualties are reported as a pooled expectation with whole-entity
bounds that bracket it. They are not an individual hit allocation. Contact and
outward phase components contribute to `attempted_damage` as raw estimates,
but are separated in `raw_unresolved_attempted_damage`; only
`modeled_delivery_attempted_damage` is used for barrier, health and casualty
results. Phase protection, actual tick timing and intensity scaling still need
live validation. Source intensity settings and their references are preserved
under `source_facts.intensity_settings`.

## What is not added to target damage

- **Failure branches.** Miscast explosions are listed in `conditional_branches`
  with `miscast_chance`; their recipients are unverified.
- **Shared definitions.** A definition reached by several routes within one
  cast (for example, a projectile and its explosion both naming one shrapnel
  record) is counted once. `totals.upper_all_routes_attempted_damage` adds every
  route, and `shared_definition_multiplicity` makes the status `partial`.
- **External mechanics.** Supersession, behavior and formation detail links
  remain in `unsupported_components` with their exact relationship and detail
  reference; they do not imply a damage event.
- **Healing, stat and attribute effects, and summons.** These are listed in
  `unsupported_components`. Buff/debuff engagement comparison is the next #20
  increment.

## Status and blocks

`calculated` means modeled damage components were totalled without unresolved
delivery. `partial` includes raw phase estimates, unknown components and route
ambiguity. Source-implied schedules are estimates, not measured game behavior.
`blocked` means one of:

- `ineligible_recipient`: neither the casting nor an outward phase or payload
  can reach enemies (for example self-only Potion of Charoi).
- `out_of_range` or `inside_min_range`: the supplied `cast_distance_metres` is
  checked against `target_intercept_range` and `min_range`, never projectile
  range or payload radius.
- `no_damage_payload`: there is no outward damaging payload.

A supplied `caster` is checked against qualified source access links and
reported as `linked` or `not_established`. A link is not proof of acquisition.

## Scenario

| Field | Default | Meaning |
| --- | --- | --- |
| `projectile_hit_probability` | 0.5 | uncalibrated, as in #5 |
| `entities_per_explosion` | 1 | radius geometry is not modeled |
| `vortex_entities_per_application`, `vortex_applications` | required | vortex totals |
| `contact_phase_ticks`, `phase_damage_applications` | source-implied schedule when duration and frequency are positive | raw phase totals; overrides do not establish game cadence |
| `phase_damage_entities` | source cap, or living entities if uncapped | always clamped to a positive source cap |
| `facing` | front | |
| `target_component_role` | primary | |
| `cast_distance_metres` | unchecked | range check |
| `historical_relations_apply_to_patch_9` | true | false disables damage, as in #5 |

Unknown fields, out-of-range values and other barrier orders are rejected.

## Verification

`tests/test_effect_calc.py` (17 tests, from source evidence and synthetic corruption probes) covers:

- a spell chain recomputed through the shared relation (Comet)
- a non-spell ability with a contact phase (Pyromaniac), including the source-implied schedule
- Spirit Leech raw phase damage, cap enforcement and unresolved protection/intensity
- a linked Comet explosion removed from a copied packet, which must be rejected
- valid external supersession, behavior and formation links, plus a missing detail link
- an injected nonexistent provenance ID, which must be rejected
- zero-direct-damage transport (Hell Hammer)
- overcast versus normal and the excluded miscast branch
- shared shrapnel counted once with an upper bound (Dreaded Thirteenth)
- vortex count requirement and linear sensitivity
- ineligible-recipient and range blocks
- qualified caster access
- canonical, unchanged base profiles
- input validation
- library/CLI/MCP equality
- resolvable cross-references and provenance

A fresh independent-style sweep on this exact evaluator tree completed all
1,884 pinned effects against Lothern Sea Guard with zero errors: 216
`calculated`, 493 `partial` and 1,175 `blocked`. These regression checks are
not live-battle observations; `empirical_calibration` is null.

# Buff/debuff engagement comparison — issue #20, increment B

`ctw_adviser.effect_engagement.evaluate_effect_engagement(queries, effect,
unit_a, unit_b, *, recipient="a", relation="friendly", phase=None,
scenario=None, caster=None, ...)` runs the same #5 `evaluate_matchup`
engagement twice: without and with one effect phase applied to one side. It
returns the deltas, the changed inputs and both full matchup results. Model
version: `effect-engagement-0.1.0`. CLI: `effect-engagement`. MCP:
`evaluate_effect_engagement`.

```sh
PYTHONPATH=src python -m ctw_adviser.cli effect-engagement --db work/adviser.sqlite \
  wh2_main_spell_plague_wither "Lothern Sea Guard" "Bloodletters of Khorne" \
  --recipient b --relation enemy \
  --scenario '{"separation_metres":40,"sides":{"a":{"order":"hold"},"b":{"order":"approach"}}}'
```

**Shared baseline.** `evaluate_matchup` gained one optional `unit_modifier`
hook. It receives deep copies of the two verified packets; `source_facts` and
`identities` still report the unmodified packets. The unmodified run is
byte-identical to a standalone #5 call with the same scenario, which is tested.
Base profiles never change.

**Applied modifiers.** Only phase stat effects that map to inputs the #5
model reads are applied, using their native `add` or `mult` operation:

- melee attack, defence, base/AP damage and charge bonus
- speed
- armour, physical, missile, magic and flame resistance, and ward (`stat_resistance_all`)
- missile block chance
- missile base/AP damage
- melee bonus versus large or infantry

Changed inputs are listed with before and after values. Morale, reload,
accuracy and other stats, and healing, summons and attributes, are listed as
unsupported. If nothing supported remains, the result is
`blocked: no_supported_modifier`.

**Recipients.** `relation=enemy` requires an enemy-targeting phase link;
self/friendly cast selection can produce an outward aura. Its coverage is
unverified. `friendly` requires a friends or self phase link. A self-only phase
requires a supplied caster and matching resolved recipient identity;
otherwise it is blocked. A supplied `caster` is checked against qualified
access links.

**Timing.** The effect is assumed active from the engagement start; cast timing,
wind-up and refresh are not modeled. For a selected later-order phase, its
source start time is unknown: `window.start_seconds` is null and comparisons
are conditional on that phase being active at the selected window origin.
A phase shorter than the horizon gives two
comparisons:

- `active_window`: both runs truncated at phase expiry. This is the primary comparison.
- `horizon`: the effect held for the whole horizon. This is an upper bound.

A null or sentinel duration reports only the horizon bound, as `partial`.
Intensity-scaled abilities use full listed values and are flagged. Stacking,
replacement, recipient caps and area coverage are not modeled.

Verified with `tests/test_effect_engagement.py` (18 tests, from source evidence):

- Hand of Glory: a friendly spell attack buff lowers only the enemy's survivability
- Wither: an enemy armour debuff, plus the ineligible-relation block
- Aura of Inertia: an enemy phase from a self cast, with reach uncertainty
- Potion of Charoi: a self-only phase cannot modify an unrelated unit
- Crooked Dice phase III: later-stage start remains unresolved
- Shanty Verse: a non-spell defence buff
- Wild Mantle of Ghorok: inverse effects (armour down, attack up) both reflected
- Tomb King Rally: the morale-only block
- active-window expiry, and a shared baseline identical to #5
- a zero modifier giving zero delta
- unchanged base profiles and input validation
- library/CLI/MCP equality

These are regression checks, not live observations.

## Review round: response budget, sensitivity and coverage

- **Compact engagement results by default.** Each run reports its verdict,
  contact and ledgers; full #5 results are opt-in (`include_matchups`). A
  Daemon Prince engagement drops from 1.27 MB, over the hosted 1 MiB cap, to
  21 KB. Compact and full results agree on every comparison.
- **Sensitivity.** Each comparison lists the four #5 collision-probability
  corners with the favored side with and without the effect, and both runs'
  one-parameter flip thresholds.
- **Clamping.** Modifiers that push a field below its domain (armour, damage,
  attack, block chance) are clamped at the bound, marked `clamped` with the
  unclamped value, and flagged `modifier_clamped`. The full-inventory sweep
  found 20 such effects that previously failed.
- **Replacement.** `replacement.supersedes` lists superseded effects. Only the
  selected effect's phase is applied, never stacked with its variants.
- **Eligibility.** A self or friendly-cast ability reaches enemies only through
  enemy-targeting phases or payloads that can damage enemies; this is
  labeled as aura or self-centred.

[Recorded predictions](effect-predictions.json) come from
`scripts/record_effect_predictions.py`. They give exact inputs and key outputs
for seven damage and five engagement cases, plus sweeps of 1,884 damage effects
and 829 stat-phase effects with no errors:

- **Damage:** 216 calculated, 493 partial, 648 ineligible recipients and 527
  without an outward damage payload.
- **Engagement:** 94 calculated, 403 partial, 221 self-only phases blocked
  without a verified caster, 84 without a supported modifier, 25 needing a
  phase choice and 2 ineligible recipients. The sweep intentionally provides
  no caster identity.
- **Latency on this host:** damage median 29 ms; engagement median 2.16 s,
  since it runs up to four full #5 engagements with their sensitivity.

These are model predictions, not live observations.
