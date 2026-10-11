# Spells and activated abilities — issue #19, increment 1

This is the data/retrieval half of ONT-120, first increment. Calculations and
scenario application belong to #20. CTW-data stays authoritative; the pin is
unchanged (`595e227`). Contract 3 widens the reviewed import scope from passive
and weapon roots to every source-classified activated root. It adds no input
files; the lock changes only its contract fingerprint.

```sh
python scripts/build_snapshot.py build --ctw-root ../CTW-data --output work/units.sqlite
python scripts/query_snapshot.py resolve-effect --db work/units.sqlite "Fiery Convocation"
python scripts/query_snapshot.py effect --db work/units.sqlite "Bound Fiery Convocation" --unit wh2_main_hef_cha_teclis_0
python scripts/query_snapshot.py effect --db work/units.sqlite wh_main_spell_heavens_comet_of_casandora_upgraded
python scripts/query_snapshot.py unit-effects --db work/units.sqlite wh2_main_hef_cha_teclis_0
python scripts/query_snapshot.py detail --db work/units.sqlite effect:wh2_main_lord_abilities_potion_of_charoi
python -m unittest tests.test_effects -v
```

## Storage: distinct linked tables

Store schema 4 keeps unit rows unchanged and adds three specialized tables
inside the same SQLite snapshot:

| Table | Holds | Never holds |
| --- | --- | --- |
| `effect_abilities` | One row per activated definition (`casting.passive=false`): stable key, `effect_kind`, source type, localized name, definition/casting record IDs, concise derived `keywords_json` | Payload values or unit stats |
| `effect_variants` | `overcast_option` (`overpower_option`) and `supersedes` relations; `status` is `resolved`, `not_activated` or `missing` | Inferred name-based variants |
| `effect_access` | Unit ↔ effect junction from source unit ability links: unit key, culture, `requires_effect_enabling`, route, qualification, link record | Claims of acquisition or active effects |

Detailed mechanics use the canonical shared native tables
(`native_ability_casting`, phase links/phases, stat/attribute effects, conditions,
intensity, bombardments, projectiles, explosions, vortices, shrapnel, spreading)
and the existing `relation_edges` graph. Before contract 3, activated definitions
were narrow `_metadata` rows. They now keep full casting rows and every
dependency edge. Only `unresolved` classifications remain metadata-only.
Passive selection, values and packets are unchanged.

`effect_kind` is `spell` when `definition.source_type` is `spell` or `bound`,
otherwise `activated_ability`. It is a source label, not proof of Winds funding
or obtainability. Keywords name retained fields only: `spell`, `bound`,
`has_overcast`, `overcast`, payload kinds (`bombardment`, `projectile`,
`vortex`, `summon`, `miscast`), target flags, `phase_damage`, `healing`,
`stat_modifier` and `attribute_effect`.

The build reconciles every activated option with an effect row and full
records. It reconciles each qualified access row and variant relation against
its source record, including culture, enabling and provenance. Effect lookups by key, name, unit, ability
and reverse variant use indexed SEARCH plans.

## Retrieval

`Queries.resolve_effect(query, unit=None)` takes an exact key or a
case-insensitive label. Shared labels (normal, bound, quest and overcast
versions) return candidates. `unit` restricts candidates to effects linked to that
unit's source keys.

`Queries.get_effect(...)` returns `effect`:

The complete response is validated by `schema/effect_packet.schema.json` and
`scripts/validate_packets.py`; omission differs from an explicit source null in
each supported mechanic kind.

- `identity`: key, name, kind, basis, source/ability type, keywords.
- `variants`: outgoing and incoming overcast/supersession links with `effect:` refs.
- `activation`: cost, uses, initial/subsequent/shared recharge, wind-up, active
  time, miscast settings. Negative values are listed in `native_sentinels`.
- `distances`: `target_intercept_range`, `effect_range` and `min_range`, each
  with a neutral native label. Projectile range and payload radii stay on
  payload nodes.
- `targeting`: self/friends/enemies/ground flags, recipient caps and ownership flags.
- `mechanic`: the existing conditions/phases/effects envelope, with explicit
  recipients per phase link and no new overarching schema.
- `payload`: readable root-to-leaf paths over the bounded `payload_graph`.
  Phase stat/attribute effects are listed on their phase. A zero-direct-damage
  node with a delivering child is marked as a transport. Miscast explosions are
  separate `conditional_failure` branches carrying `miscast_chance`.
- `summons`: spawned land-unit keys mapped to roster profiles by exact
  `source_land_unit_key` only; anything else stays `unmapped_land_unit`.
- `access`: paged qualified unit links with resolvable unit keys, plus the
  routes not yet imported.
- `summary`: one readable paragraph built from the sections above.

Provenance is deferred by default (`include_provenance=True` expands it).
Diagnostics are opt-in. Unit packets 1.20.0 keep `activated_options`
reference-only, adding `effect_kind`, `keywords` and an `effect:<key>`
`detail_ref`. `get_detail('effect:<key>')` and `get_unit_effects(unit)`
complete the round trip. The MCP adapter adds `resolve_effect` and `get_effect`.
The Datasette detail page shows the summary and payload paths.

## Verified pinned build

See [verification evidence](activated-effects-verification.json). There are
1,884 activated effects (610 spells, 1,274 non-spell abilities); 578 of them
have a unit ability link (2,039 access records). All 210 overcast links and
97 supersession links resolve. Every effect passes through the same lookup
with no failures: median 2 ms, p95 under 4 ms, packets at median 8 KB and
maximum 27 KB, with no payload path overflow. There are 60 effects with
zero-direct-damage transports and 217 with a failure branch. Of 151 summoned
land units, 37 map to roster profiles. The 12 casting `mom_vortex_key` tokens
without a vortex row stay explicit `unresolved_reference` gaps.

All 503 retained passive/culture combinations (mechanics, payload graphs,
diagnostics, detail refs) and all 2,409 unit packets match the previous `main`
build exactly, apart from the intended `activated_options` additions.

## Not in this increment

- Character skill/rank routes (`CTW-data/data/magic` characters, access and
  indexes) need contract 4 and a reviewed lock expansion. 1,306 effects
  currently have no unit link. They are retrievable, but this snapshot does not
  establish who can cast them.
- Item, trait, mount, form and script grants.
- Damage estimates, buff application, stacking, scheduling, combat verdicts (#20).
- `scripts/audit_alpha4_recovery.py` fails on `main` as well: its pinned
  baseline predates the `spreadings` field. This increment does not change that
  audit.
