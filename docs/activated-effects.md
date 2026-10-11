# Spells and activated abilities — issue #19

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

- Character skill/rank routes: delivered in increment 2 below.
- Item, trait, mount, form and script grants.
- Damage estimates, buff application, stacking, scheduling, combat verdicts (#20).
- `scripts/audit_alpha4_recovery.py` fails on `main` as well: its pinned
  baseline predates the `spreadings` field. This increment does not change that
  audit.

## Increment 2: character skill/rank access (contract 4)

Contract 4 keeps the pin `595e227`, as Owen confirmed. It locks 1,086
additional CTW-data files:

- `data/magic/character_index.csv`
- the 534 per-character skill-binding CSVs
- the 550 `data/magic/access/*.json` unit-form files
- `abilities/tables/ability_group_members.csv`

`scripts/contract4_magic_access.py` performs the migration. It checks each file
against its Git blob at the pin and against CTW-data's own
`data/magic/output_manifest.json`, and aborts on any mismatch rather than
refreshing a hash. The existing lock entries, joins and dataset specs are unchanged.

New linked tables (still store schema 4):

| Table | Holds |
| --- | --- |
| `magic_characters` | 550 indexed characters (agent subtype, name, class, caster flag) |
| `magic_skill_bindings` | All 50,934 skill → effect → binding rows with exact skill, rank, node set, bonus value and source lines |
| `character_unit_forms` | 1,370 character → main/land unit forms (associated unit override or mount variant). 1,367 map to snapshot unit keys by exact key; 3 stay `unmapped` with a coverage gap |
| `effect_character_access` | The 29,146 ability-targeted bindings with role `enables`, `enables_overcast` (native `enable_overchage`), `disables` or `modifies`, and status `activated_effect`, `not_activated` (for example skill-granted passives) or `missing_definition` (none) |
| `native_ability_group_members` | Exact lore/group membership |

Group, phase, unit-set, army, pre-battle and context bindings stay in
`magic_skill_bindings`. They never create per-spell access rows. Group
modifiers are shown on effect packets as modifiers of a group the effect
belongs to, never as grants. Ranks are separate records and are never summed,
and no build solver chooses skills.

Retrieval additions:

```sh
python scripts/query_snapshot.py resolve-character --db work/units.sqlite "Tomb King"
python scripts/query_snapshot.py character --db work/units.sqlite Teclis
python scripts/query_snapshot.py character --db work/units.sqlite Teclis --skill wh2_main_skill_magic_dark_flock_of_doom_teclis:1
python scripts/query_snapshot.py detail --db work/units.sqlite effect-characters:wh_main_spell_heavens_comet_of_casandora
```

- `get_effect` → `access.characters`: the first 8 characters, each with
  compact unit forms and bindings grouped by exact skill/rank/role. The
  `effect-characters:<key>` detail ref pages through all characters with full
  forms and node sets. `access.group_modifiers` lists the effect's groups and
  their modifiers.
- `get_character_effects(character, skills=None, limit=32, cursor=None)` pages
  exact source bindings (1–256 per page). `binding_page` reports the total,
  offset, returned count, limit, continuation cursor and `character:<key>`
  detail reference. `get_detail` accepts that reference with the same limit and
  cursor. An ability may span pages; collect all pages before interpreting its
  full set of skill/rank/role bindings. The cursor retains supplied
  `SKILL_KEY:RANK` pairs, so detail continuation keeps the same selection.
  Unknown pairs are reported, and non-ability binding summaries are filtered
  to supplied pairs when present. Group modifiers never grant a spell.
- `get_unit_effects` → `character_skill_effects`: unit → indexed character
  forms → effects their skill bindings can enable.
- The MCP adds `get_character_effects`. Packet version 1.21.0 leaves unit
  packets unchanged.

Snapshots now open with a read-only `mmap_size` of 256 MiB. On the
165 MB schema-4 file this brought warm effect-lookup p95 from about 57 ms to
about 10 ms.

Verified with contract 4 (see the evidence file): 1,084 of 1,884 effects have
an access route (578 through unit links, 849 through character skill
bindings). Effect lookups run at median 2.6 ms and p95 10 ms, with a maximum
packet of 35 KB. Character lookups over all 550 characters run at median 4 ms
and maximum 36 ms. All 503 passive outputs and all 2,409 unit packets are
identical to increment 1. The remaining 800 effects (mostly army, quest, item
and upgrade abilities) have no route established by these indexes; that is not
evidence that they are unavailable.

Still not established: item, trait and ancillary grants, mount unlocks,
scripted forms, campaign legality and calculations (#20). Completing #19 does
not close ONT-120.
