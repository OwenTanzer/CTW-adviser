"""Indexed, read-only retrieval. No scenario evaluation or combat arithmetic."""
from __future__ import annotations

import base64
import hashlib
import json
import re
from pathlib import Path

from .store import open_snapshot, quote

PACKET_VERSION = '1.9.0'
MURDEROUS_INDICATOR = 'wh2_main_faction_abilities_murderous_prowess_indicator'
MURDEROUS_BUFFS = {'wh2_main_faction_abilities_murderous_prowess',
                   'wh2_main_faction_abilities_murderous_mastery'}
PASSIVE_RESEARCH_DOCUMENTATION = 'https://github.com/OwenTanzer/CTW-adviser/blob/issue-2-query-packets/docs/lookup-contract.md#focused-passive-research'

# Reviewed families share payload handling, not necessarily phase sequences.
SURVIVAL_PASSIVES = {
    'wh2_main_unit_passive_too_horrible_to_die',
    'wh2_dlc15_unit_passive_fiery_rebirth',
    'wh2_main_unit_passive_rebirth',
    'wh2_pro08_character_passive_heroic_fortitude',
    'wh3_main_daemon_body_passive_restore_the_blighted',
}
DEATH_PAYLOAD_PASSIVES = {
    'wh3_dlc24_unit_passive_sour_discharge': 'The Sourguts',
    'wh3_dlc25_unit_passive_abandon_ship': 'the Land Ship',
    'wh3_dlc26_unit_abilities_force_of_total_destruction': 'the Mangler Squigs',
    'wh3_dlc26_unit_passive_bloodstorm': 'the Bloodwake Berserkers',
    'wh3_dlc27_unit_passive_split_up': 'the Sea Elemental',
    'wh3_dlc29_unit_passive_curse_of_the_fallen': 'the Khemric Titan',
    'wh3_dlc29_unit_passive_pestilent_perfection': 'the Pusbags',
}
# Individually reviewed interpretations; supporting sources and their limits are
# optional documentation in docs/lookup-contract.md#focused-passive-research.
# Murderous Prowess Indicator is consolidated separately at the unit boundary.
RESEARCHED_PASSIVES = {
    'wh3_dlc29_passive_spell_lightning_strike':
        'The Celestial Hurricanum automatically targets enemies within a 40-metre interception range and launches a lightning bombardment from above the selected target. '
        'Each bombardment specifies one projectile, with spread radius setting 1. The magical projectile deals 0 base and 18 armour-piercing damage; '
        'its separate magical explosion deals 0 base and 18 armour-piercing damage with radius 8. Both can damage allies. '
        'Initial recharge is 0, recharge setting 10 seconds, active time 4 seconds and shared-recharge setting 5 seconds; these do not establish an exact repeating attack interval. '
        'Target priority, behavior without an eligible target and shared-recharge interactions remain unverified. '
        'Damage parameters are separate from ordinary weapon attacks and from the separately activated Lightning Strike ability.',
    'wh2_dlc16_lord_passive_conjoined_destiny':
        'Low-health healing for the Sisters of Twilight, disabled above 20% health. '
        'A 30-second preparation phase precedes a self-healing phase with amount setting 0.25, interval setting 1 and duration setting 1.1. '
        'The published ability description identifies this as a 25% heal. Countdown interruption, repeatability and effective healing caps remain unverified.',
    'wh3_dlc23_hero_passive_lucky_git':
        'One-use low-health healing for Gorduz Backstabber, disabled above 25% health. '
        'Prepares for 5 seconds, then heals himself during a 30-second phase. Healing amount setting 0.006 and interval setting 1.5 are retained separately; '
        'the published 0.60% healing-rate description does not establish tick arithmetic or total healing. Interruption behavior remains unverified.',
    'wh3_dlc26_character_passive_bloodborn':
        'One-use low-health healing for Skarr Bloodwrath, disabled above 25% health. '
        'A 1-second buffer precedes a 1-second self-healing phase with amount setting 0.2 and interval setting 1. '
        'This is healing of the living host, with resurrection disabled. Effective healing amount and caps remain unverified.',
    'wh3_cp1_unit_passive_implacable_spirit':
        'After 25 seconds stationary, the Gate Master gains missile range x1.4, armour-piercing missile damage x1.25 and +15 percentage points missile resistance. '
        'These effects target the Gate Master himself, not nearby allies. Movement disables the ability; requires effect enabling. '
        'The additional climbing/equipment/platform restriction is retained below; its exact combination rule remains unverified.',
    'wh3_dlc23_unit_passive_dig_in':
        'After 25 seconds stationary, the host gains missile range x1.4, +15 percentage points missile resistance and Expert Charge Defence. '
        'These are self-targeted benefits; movement disables the ability. '
        'The additional climbing/equipment/platform restriction is retained below; its exact combination rule remains unverified.',
    'wh3_dlc25_unit_passive_blackpowder_discipline':
        'After 10 seconds stationary, the host gains +40 accuracy and +10 reload skill until movement disables the ability. '
        'Reload skill is a stat bonus, not a 10% reduction in reload time. '
        'The additional climbing/equipment/platform restriction is retained below; its exact combination rule remains unverified.',
    'wh3_dlc25_lord_passive_feast_of_the_maggot_lord':
        'One-use last chance at death for Tamurkhan, requiring an enemy lord or hero within the 30-metre interception range. '
        'His self-targeted phase grants Cannot Die and healing (amount setting 0.03, interval setting 1, duration 7); '
        'a separate enemy-targeted phase deals damage (amount 424, interval setting 1, duration 7, maximum one affected entity). '
        'This is a survival response, not an unconditional death explosion. Exact target priority, phase overlap and success requirements remain unverified.',
    'wh3_dlc25_unit_passive_unbinding_spirit_of_grungni':
        'The Spirit of Grungni provides support for 150 seconds, then enters a 5-second disengagement phase and leaves the battlefield to resupply. '
        'The removal phase damages the airship itself (amount 16000, interval setting 1); it does not damage nearby enemies. '
        'This describes the base summoned-airship ability; campaign upgrades and exact removal scheduling are not evaluated.',
    'wh3_dlc27_unit_passive_burrowing_instinct':
        'When the Dread Maw breaks, it shatters and leaves the battle rather than rallying. '
        'The self-targeted leadership penalty is -100 and the behavior requests battlefield departure. '
        'The internal stance named rebirth belongs to this departure sequence, not resurrection. Exact departure timing remains unverified.',
    'wh3_twa08_unit_passive_redirecting_aura':
        'Enemy missile units within 55 metres of the Green Guardian have their projectiles redirected toward the firing unit. '
        'Eligibility concerns nearby enemy shooters, not merely projectiles aimed at the Guardian. '
        'Projectile exceptions and close-range behavior remain unverified; no flat damage-reflection percentage is established.',
    'wh2_dlc12_unit_passive_thunderous_one':
        'The Thunderous One automatically releases lightning bombardments associated with melee combat. '
        'It has 10 uses and recharges while engaged in melee. Bombardment, projectile and explosion parameters are separate from ordinary melee damage. '
        'Exact strike placement and interrupted recharge remain unverified.',
    'wh2_dlc15_lord_passive_mistwalkers_barrage':
        'Eltharion automatically releases a bombardment associated with melee combat; recharge progresses while engaged in melee. '
        'Requires effect enabling. Projectile and explosion parameters are retained separately from his ordinary attacks. '
        'Exact strike placement and interrupted recharge remain unverified.',
    'wh2_dlc16_unit_passive_warp_discharge':
        'Morskittar\'s Hellion releases a damaging magical vortex associated with melee combat; recharge progresses while engaged in melee. '
        'The vortex is a separate damage payload, not a modifier to each melee hit. Exact launch scheduling remains unverified.',
    'wh2_dlc17_unit_passive_searing_bile_blood':
        'The Vorbergland Broodmother releases a damaging bile vortex associated with melee combat; recharge progresses while engaged in melee. '
        'The linked vortex supplies the armour-piercing damage parameters. The records do not establish retaliation on every incoming hit; exact launch scheduling remains unverified.',
    'wh2_dlc17_unit_passive_spurting_bile_blood':
        'The Jabberslythe releases a damaging bile vortex associated with melee combat; recharge progresses while engaged in melee. '
        'The records do not establish retaliation on every incoming hit. Vortex damage is separate from ordinary melee damage; exact launch scheduling remains unverified.',
    'wh3_dlc24_unit_passive_tides_of_transformation':
        'The Mutalith Vortex Beast releases the linked transformation vortex, with recharge progressing while engaged in melee. '
        'Its 32-second self-targeted phase has no numerical modifier; the damaging effect belongs to the separate vortex payload. '
        'Exact launch timing and phase-to-vortex synchronization remain unverified.',
    'wh3_dlc26_unit_passive_hellraiser':
        'The Hellforged Bellowers release the linked damaging vortex in melee; recharge progresses in melee and the ability deactivates outside melee. '
        'Its 6-second self-targeted phase has no numerical modifier; outward damage belongs to the separate vortex payload. '
        'Exact launch scheduling remains unverified.',
    'wh2_dlc15_unit_passive_giant_explodin_spores':
        'Logey Bogey\'s Spore Splodaz release explosive spores on entering melee; the published description associates this with the charge. '
        'Spores recharge outside melee, with initial recharge 0 and subsequent recharge 60. '
        'The bombardment and its explosion are separate from normal attacks; no self-destruction effect is established. '
        'Exact charge-versus-contact timing and interrupted recharge remain unverified.',
    **{f'wh2_dlc15_unit_passive_rubble_and_ruin_tier_{tier}_bombardment':
        f'One-use debris bombardment for this Rubble & Ruin tier, disabled above {health}% host health. '
        'Each health threshold has its own bombardment trigger; all three use the same damage parameters. '
        'How skipped health thresholds are scheduled remains unverified.'
        for tier, health in ((1, 75), (2, 50), (3, 25))},
    'wh3_main_daemon_body_passive_foreboding_ignition':
        'One-use low-health release of an expanding damaging vortex, disabled above 10% host health. '
        'Requires effect enabling. This is a low-health response, not an established death trigger. '
        'Vortex parameters remain separate from ordinary attacks; release timing remains unverified.',
    'wh3_main_lord_passive_wrath_of_khorne':
        'Punishes enemy spellcasting within the 100-metre interception range with a separate damaging vortex; recharge setting 15. '
        'Requires effect enabling. The target restriction checks for an ability winding up; spellcasting is the reviewed interpretation of the published description. '
        'The treatment of non-spell abilities, simultaneous casters, target priority and exact firing timing remain unverified. This does not establish spell cancellation.',
    'wh_dlc06_lord_passive_locus_of_power':
        'Causes a damaging miscast-like explosion when an enemy casts within the 100-metre interception range of the Anvil of Doom; recharge setting 6. '
        'Damage is supplied by the linked vortex rather than added to ordinary attacks. The target restriction checks for an ability winding up. '
        'The treatment of non-spell abilities, simultaneous casters, target priority and exact firing timing remain unverified. This does not establish spell cancellation.',
}

EXPLAINED_PHASE_ROLES = {
    'wh2_dlc16_lord_passive_conjoined_destiny_countdown': '30-second preparation before self-healing; countdown interruption and repeatability remain unverified.',
    'wh3_dlc23_hero_passive_lucky_git_i': '5-second preparation before the 30-second self-healing phase; interruption behavior remains unverified.',
    'wh3_cp1_unit_passive_implacable_spirit_i': '25-second stationary preparation before self-targeted missile benefits.',
    'wh3_dlc23_unit_passive_dig_in_i': '25-second stationary preparation before self-targeted defensive and range benefits.',
    'wh3_dlc25_unit_passive_blackpowder_discipline_i': '10-second stationary preparation before accuracy and reload-skill benefits.',
    'wh3_dlc25_unit_passive_unbinding_spirit_of_grungni': '150-second support period before the self-targeted disengagement/removal phase.',
    'wh3_twa08_unit_passive_redirecting_aura': 'Enemy-targeted projectile redirection phase; the missile-mirror behavior supplies the effect rather than a numerical modifier. Projectile exceptions remain unverified.',
}

EXPLAINED_PASSIVES = {
    **RESEARCHED_PASSIVES,
    'wh2_dlc13_unit_passive_kaboom':
        'One-use death blast for the Steam Tank variant carrying Kaboom!, interpreted from the unit-alive exclusion and explosion definition. '
        'The expanding flaming blast can hit allies and enemies; its contact effect reduces enemy leadership by 8, with duration setting 10. '
        'Blast parameters are separate from ordinary weapon damage. Exact death-event scheduling remains unverified.',
    'wh3_dlc26_unit_abilities_blow_apart':
        'One-use death blast for the Colossal Squig, supported by the unit-alive exclusion and death tooltip. '
        'The expanding blast can hit allies and enemies; its contact effect reduces enemy leadership by 8 and multiplies speed by 0.85, with duration setting 10. '
        'A separate self-targeted damage phase is retained; it is not outward blast damage or proof of a living-unit suicide trigger. '
        'Exact death-event scheduling and self-phase execution remain unverified.',
    'wh2_dlc11_unit_passive_abandon_ship':
        'Necrofex low-health summon: summons a Zombie Pirate Deckhand Mob at the host position, with one use. '
        'Disabled above 50% host health; exact threshold equality and summon timing remain unverified. '
        'A separate self-targeted phase has damage amount 3, interval setting 1, duration setting 1 and maximum one affected entity. '
        'This is distinct from the Land Ship death blast with the same ability name; summoned-unit lifetime remains unverified.',
    'wh3_dlc29_lord_passive_arch_necromancer': None,
    'wh3_dlc29_lord_passive_liche_ascendant': None,
    'wh_dlc05_lord_abilities_spirit_essence_of_chaos': None,
    'wh2_dlc11_unit_passive_gaseous_demise':
        'Melee engagement enables this one-use detonation. A buffer phase precedes a phase that damages the Corpse itself. '
        'The ability also launches an expanding magical blast that can hit allies and enemies. '
        'Self-damage is separate from blast damage. Exact launch timing and interaction with the low-health detonation route remain unverified.',
    'wh2_dlc11_unit_passive_noxious_unstable_mark_ii':
        'Low-health detonation route: a buffer phase precedes damage to the Corpse itself, and the ability uses the same expanding magical blast as Gaseous Demise. '
        'The blast can hit allies and enemies. A shared blast definition does not establish whether both routes can fire; their interaction and exact threshold timing remain unverified.',
    'wh_dlc06_quest_passive_squigs_go_boom':
        'One-use detonation associated with melee engagement. The ability damages the Squig itself and launches a bombardment projectile carrying an explosion. '
        'The projectile has zero direct damage; the magical explosion can also hit allies. '
        'Self-damage and explosion damage are separate. Exact activation, interruption and self-destruction timing remain unverified.',
    'wh2_main_unit_passive_the_rats_emerge': None,
    'wh2_main_unit_passive_too_horrible_to_die': None,
    **dict.fromkeys(SURVIVAL_PASSIVES),
    **dict.fromkeys(DEATH_PAYLOAD_PASSIVES),
    'wh3_dlc27_unit_passive_split_up_hidden':
        'Separate low-health summon route for the Sea Elemental: summons Oceanids at the host position, with one use. '
        'It is disabled above 25% health; exact threshold equality and event timing remain unverified. '
        'Its outward pulse has zero damage but retains a knockback force setting. '
        'The damaging death blast belongs to the other Split Up ability; these are not one death-triggered summon.',
}

TARGET_SUMMON_PASSIVES = {
    'wh3_dlc29_lord_passive_arch_necromancer': 'commander-class',
    'wh3_dlc29_lord_passive_liche_ascendant': 'non-commander',
    'wh_dlc05_lord_abilities_spirit_essence_of_chaos': 'non-commander',
}

SECTIONS = ('components', 'weapons', 'attributes', 'abilities', 'activated_options')
MODES = ('combined', 'melee', 'missile')
CONDITION_TEXT = {
    'engaged_in_melee': 'engaged in melee',
    'engaged_in_melee_anything': 'engaged in melee with any opponent',
    'out_of_melee': 'not engaged in melee',
    'out_of_melee_anything': 'not engaged in melee with any opponent',
    'losing_melee_combat': 'losing melee combat',
    'winning_melee_combat': 'winning melee combat',
    'have_ammo_below_threshold': 'ammunition below the configured threshold (threshold value not established)',
    'morale_is_broken_or_lower': 'morale state is broken or worse',
    'moving': 'moving', 'climbing': 'climbing',
    'manning_equipment': 'manning equipment', 'no_spells_active': 'no spells active',
    'climbing_manning_eq_on_platform': 'climbing/equipment/platform state (combination rule not established)',
    'unit_is_not_pre_murderous_prowess': 'not in the pre-Murderous-Prowess state (state definition not established)',
}
STAT_NAMES = {
    'stat_melee_attack': 'melee_attack', 'stat_melee_defence': 'melee_defence',
    'stat_charge_bonus': 'charge_bonus', 'stat_resistance_physical': 'physical_resistance',
    'stat_melee_damage_ap': 'melee_ap_damage', 'stat_melee_damage_base': 'melee_base_damage',
    'scalar_speed': 'speed',
}
PROTECTION = ('armour', 'shield_block_chance', 'physical_resistance',
              'missile_resistance', 'spell_resistance', 'fire_resistance', 'ward_save')
CASTING_FIELDS = (
    'wind_up_time', 'active_time', 'recharge_time', 'num_uses', 'effect_range', 'target_intercept_range',
    'affect_self', 'always_affect_self', 'only_affect_target', 'num_effected_friendly_units',
    'num_effected_enemy_units', 'update_targets_every_frame', 'initial_recharge',
    'min_range', 'target_self', 'target_friends', 'target_enemies', 'target_ground',
    'only_affect_owned_units', 'update_phase_by_ability_duration', 'shared_recharge_time',
    'intensity_based_activation', 'spawned_unit', 'spawn_type', 'spawn_is_transformation',
    'spawn_is_decoy', 'spawn_shares_health_and_fatigue', 'behaviour', 'formation',
    'activated_projectile', 'bombardment', 'vortex', 'mom_vortex_key',
)
PHASE_FIELDS = (
    'effect_type', 'cant_move', 'freeze_fatigue', 'fatigue_change_ratio',
    'inspiration_aura_range_mod', 'ability_recharge_change', 'mana_regen_mod',
    'mana_max_depletion_mod', 'imbue_magical', 'imbue_ignition', 'imbue_contact',
    'affects_allies', 'affects_enemies', 'replenish_ammo', 'spreading',
    'freeze_recharge', 'remove_magical', 'execute_ratio', 'requested_stance',
)
PHASE_LABELS = {
    'cant_move': 'Cannot move', 'freeze_fatigue': 'Freeze fatigue',
    'fatigue_change_ratio': 'Fatigue change ratio',
    'inspiration_aura_range_mod': 'Inspiration aura range modifier',
    'ability_recharge_change': 'Ability recharge change',
    'mana_regen_mod': 'Mana regeneration modifier',
    'mana_max_depletion_mod': 'Maximum mana depletion modifier',
    'imbue_magical': 'Imbue magical attacks', 'imbue_ignition': 'Imbue ignition',
    'imbue_contact': 'Imbue contact effect', 'replenish_ammo': 'Ammunition replenishment',
    'spreading': 'Spreading reference', 'freeze_recharge': 'Freeze recharge',
    'remove_magical': 'Remove magical attacks', 'execute_ratio': 'Execution ratio',
    'requested_stance': 'Requested stance',
}
PHASE_ACTIONS = {
    'cant_move': 'Prevents movement', 'freeze_fatigue': 'Stops fatigue changes',
    'imbue_magical': 'Enables magical attacks', 'freeze_recharge': 'Stops ability recharge',
    'remove_magical': 'Removes magical attacks',
}
PHASE_QUALIFICATIONS = {
    'fatigue_change_ratio': 'fatigue scale and update interval not verified',
    'inspiration_aura_range_mod': 'range units not verified',
    'ability_recharge_change': 'time units not verified',
    'mana_regen_mod': 'regeneration unit scale and timing not verified',
    'mana_max_depletion_mod': 'unit scale not verified',
    'imbue_ignition': 'ignition encoding not verified',
    'replenish_ammo': 'absolute amount versus ammunition fraction not verified',
    'execute_ratio': 'execution threshold and application rule not verified',
    'requested_stance': 'stance execution behavior not verified',
}
TRAIT_TEXT = {
    'magical': ('ui_unit_bullet_point_enums_tooltip_ward_physical',
                'Magical attacks bypass physical resistance; scoped to this attack.'),
    'flaming': ('ui_unit_bullet_point_enums_tooltip_flaming_attacks',
                'Flaming attacks interact with fire vulnerability and healing suppression.'),
    'bonus_vs_infantry': ('unit_stat_localisations_tooltip_text_stat_bonus_vs_infantry',
                          'Numeric bonus against infantry-sized targets; distinct from the qualitative Anti-Infantry label.'),
    'bonus_vs_large': ('unit_stat_localisations_tooltip_text_stat_bonus_vs_large',
                       'Numeric bonus against large targets; distinct from the qualitative Anti-Large label.'),
}


def compact(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False)


def boolean(value):
    return None if value is None else bool(value)


def clean_text(value):
    """Remove presentation markup; unresolved substitutions remain visible."""
    if value is None:
        return None
    return re.sub(r'\s+', ' ', re.sub(r'\[\[.*?\]\]', '', value)
                  .replace('\\\\n', ' ').replace('\\n', ' ')).strip() or None


class ResolutionError(ValueError):
    def __init__(self, result):
        self.result = result
        super().__init__(result['status'] + ': ' + result['query'])


class Queries:
    """One reusable connection; per-response evidence dictionaries are isolated."""
    def __init__(self, path: Path | str):
        self.db = open_snapshot(Path(path))
        self.snapshot = dict(self.db.execute('SELECT * FROM snapshot').fetchone())
        self.tables = {r['source_file']: (r['table_name'], json.loads(r['columns_json']))
                       for r in self.db.execute('SELECT * FROM dataset_tables')}
        self.types = {name: {c['name']: c['type'] for c in cols}
                      for name, cols in self.tables.values()}

    def close(self):
        self.db.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def rows(self, table, field, value, order='record_id'):
        return [dict(r) for r in self.db.execute(
            f'SELECT * FROM {quote(table)} WHERE {quote(field)}=? ORDER BY {order}', (value,))]

    def one(self, table, field, value):
        rows = [dict(r) for r in self.db.execute(
            f'SELECT * FROM {quote(table)} WHERE {quote(field)}=? LIMIT 2', (value,))]
        if len(rows) > 1:
            raise ValueError(f'nonunique evidence: {table}.{field}={value}')
        return rows[0] if rows else None

    def resolve_unit(self, query, subculture=None):
        if not isinstance(query, str) or not query.strip():
            raise ValueError('unit query must be a nonempty string')
        query = query.strip()
        alias = self.one('unit_aliases', 'unit_key', query)
        if alias:
            profiles = [self.one('unit_profiles', 'unit_key', alias['profile_unit_key'])]
        else:
            # Separate indexed searches keep SQLite away from an OR table scan.
            found = {}
            for col in ('unit_name', 'source_unit_name'):
                for row in self.db.execute(
                        f'SELECT * FROM unit_profiles WHERE {col}=? COLLATE NOCASE', (query,)):
                    found[row['unit_key']] = dict(row)
            profiles = sorted(found.values(), key=lambda p: p['unit_key'])
        candidates = []
        for profile in profiles:
            source_keys = [query] if alias else json.loads(profile['unit_keys'])
            contexts = []
            for key in source_keys:
                contexts.extend(self.rows('unit_availability', 'unit_key', key))
            if subculture is not None:
                contexts = [r for r in contexts if r['subculture_key'] == subculture]
                if not contexts:
                    continue
            keys = sorted({r['unit_key'] for r in contexts})
            selected = query if alias else (profile['unit_key'] if profile['unit_key'] in keys else keys[0])
            subcultures = sorted({r['subculture_key'] for r in contexts})
            candidates.append({'unit_key': selected, 'profile_unit_key': profile['unit_key'],
                               'subculture_key': subculture if subculture is not None else subcultures[0] if len(subcultures) == 1 else None, 'name': profile['unit_name'],
                               'source_unit_keys': keys,
                               'subcultures': subcultures})
        status = 'resolved' if len(candidates) == 1 else 'ambiguous' if candidates else 'not_found'
        return {'status': status, 'query': query, 'candidates': candidates,
                'resolved': candidates[0] if status == 'resolved' else None}

    def resolved(self, value, subculture=None):
        # Re-resolve caller-supplied dictionaries, so identities cannot be forged.
        if isinstance(value, dict):
            key = value['unit_key']
            base = self.resolve_unit(key)
            if base['status'] != 'resolved':
                raise ResolutionError(base)
            profile_key = base['resolved']['profile_unit_key']
            keys = value.get('source_unit_keys', [key])
            if not isinstance(keys, list) or not keys or key not in keys or len(keys) != len(set(keys)):
                raise ValueError('invalid resolved source identity set')
            contexts = []
            for candidate in keys:
                alias = self.one('unit_aliases', 'unit_key', candidate)
                if not alias or alias['profile_unit_key'] != profile_key:
                    raise ValueError('resolved source identities do not share this profile')
                contexts.extend(self.rows('unit_availability', 'unit_key', candidate))
            selected_context = subculture if subculture is not None else value.get('subculture_key')
            if selected_context is not None:
                contexts = [row for row in contexts if row['subculture_key'] == selected_context]
                if not contexts:
                    raise ResolutionError({'status': 'not_found', 'query': key, 'candidates': [], 'resolved': None})
            valid_keys = sorted({row['unit_key'] for row in contexts})
            selected_key = key if key in valid_keys else valid_keys[0]
            result = self.resolve_unit(selected_key, selected_context)['resolved']
            # Discovery through equivalent keys can leave context unselected.
            # Revalidation of the representative key must not narrow that scope.
            result['subculture_key'] = selected_context
            result['source_unit_keys'] = valid_keys
            result['subcultures'] = sorted({row['subculture_key'] for row in contexts})
            return result
        result = self.resolve_unit(value, subculture)
        if result['status'] != 'resolved':
            raise ResolutionError(result)
        return result['resolved']

    def get_unit_profile(self, resolved_id, **kwargs):
        return self.get_matchup_evidence(resolved_id, **kwargs)

    def get_combat_relations(self, resolved_id, section=None, cursor=None, **kwargs):
        return self.get_matchup_evidence(resolved_id, section=section, cursor=cursor, **kwargs)

    def get_matchup_evidence(self, unit_a, unit_b=None, mode='combined', scenario=None,
                            *, subculture=None, subculture_b=None, section=None,
                            cursor=None, limit=32, include_diagnostics=False):
        if mode not in MODES or (section is not None and section not in SECTIONS):
            raise ValueError('unsupported mode or section')
        if type(limit) is not int or not 1 <= limit <= 256:
            raise ValueError('limit must be an integer between 1 and 256')
        if scenario is not None and not isinstance(scenario, dict):
            raise ValueError('scenario must be an object; it is echoed, never applied')
        if cursor and unit_b is not None:
            raise ValueError('expand one unit section per cursor')
        units = [self.resolved(unit_a, subculture)]
        if unit_b is not None:
            units.append(self.resolved(unit_b, subculture_b))
            if units[0]['unit_key'] == units[1]['unit_key'] and units[0]['subculture_key'] == units[1]['subculture_key']:
                raise ValueError('duplicate qualified unit; retrieve it once')
        context = Packet(self)
        packet = context.packet
        packet['mode'] = mode
        if scenario is not None:
            # JSON roundtrip rejects non-JSON input and isolates caller objects.
            packet['scenario'] = json.loads(json.dumps(scenario, allow_nan=False))
        for unit in units:
            offsets = {}
            if cursor:
                decoded = self.decode_cursor(cursor, unit, mode, section, limit)
                section = decoded['section']
                offsets[section] = decoded['offset']
            packet['units'].append(context.unit(unit, mode, section, offsets, limit))
        for unit in packet['units']:
            coverage = unit['coverage']
            coverage['diagnostic_count'] = len(coverage['gaps'])
            if not include_diagnostics:
                del coverage['gaps']
        context.prune()
        return packet

    def get_coverage_notes(self, unit_a, unit_b=None, **kwargs):
        """Explicit inspection of development caveats, separate from combat facts."""
        kwargs.pop('include_diagnostics', None)
        packet = self.get_matchup_evidence(unit_a, unit_b, include_diagnostics=True, **kwargs)
        units = [{'identity': u['identity'], 'coverage': u['coverage']} for u in packet['units']]
        refs = sorted({ref for u in units for gap in u['coverage']['gaps'] for ref in gap['provenance_refs']})
        evidence = {'sources': {}, 'provenance': {}}
        for offset in range(0, len(refs), 256):
            chunk = self.get_provenance(refs[offset:offset + 256])
            for field in evidence:
                evidence[field].update(chunk[field])
        return {'schema_version': PACKET_VERSION, 'snapshot': packet['snapshot'],
                'mode': packet['mode'], 'units': units,
                'sources': evidence['sources'], 'provenance': evidence['provenance']}

    def cursor(self, unit, mode, section, offset, limit):
        data = {'snapshot': self.snapshot['id'], 'version': PACKET_VERSION,
                'unit': unit['unit_key'], 'subculture': unit['subculture_key'],
                'mode': mode, 'section': section, 'offset': offset, 'limit': limit}
        raw = compact(data).encode()
        return base64.urlsafe_b64encode(raw).decode().rstrip('=') + '.' + hashlib.sha256(raw).hexdigest()[:16]

    def decode_cursor(self, token, unit, mode, section, limit):
        try:
            if len(token) > 2048:
                raise ValueError()
            encoded, digest = token.split('.')
            raw = base64.b64decode(encoded + '=' * (-len(encoded) % 4), altchars=b'-_', validate=True)
            data = json.loads(raw)
            if digest != hashlib.sha256(raw).hexdigest()[:16]:
                raise ValueError()
            expected = {'snapshot': self.snapshot['id'], 'version': PACKET_VERSION,
                        'unit': unit['unit_key'], 'subculture': unit['subculture_key'],
                        'mode': mode, 'limit': limit}
            if any(data.get(k) != v for k, v in expected.items()):
                raise ValueError()
            if data.get('section') not in SECTIONS or (section and data['section'] != section):
                raise ValueError()
            if type(data.get('offset')) is not int or data['offset'] < 1:
                raise ValueError()
            return data
        except (ValueError, TypeError, KeyError, UnicodeError) as exc:
            raise ValueError('invalid, stale or incompatible cursor') from exc

    def record(self, rid):
        p = self.one('record_provenance', 'id', rid)
        if p is None:
            raise KeyError(rid)
        table, columns = self.tables[p['source_file']]
        if p['retention'] == 'localization':
            table = 'localization'
        elif p['retention'] == 'option_metadata':
            table += '_metadata'
        row = self.one(table, 'record_id', rid)
        if row is None:
            raise ValueError('missing retained record: ' + rid)
        return table, row

    def get_provenance(self, record_ids):
        if not isinstance(record_ids, (list, tuple)) or not 1 <= len(record_ids) <= 256:
            raise ValueError('request 1–256 provenance records')
        c = Packet(self)
        records = []
        for rid in sorted(set(record_ids)):
            c.evidence(rid)
            p = self.one('record_provenance', 'id', rid)
            records.append(p)
            for row in self.rows('record_lineage', 'record_id', rid):
                c.evidence(row['lineage_record'])
        return {'schema_version': PACKET_VERSION, 'snapshot': c.packet['snapshot'],
                'records': records, 'sources': c.packet['sources'],
                'provenance': c.packet['provenance']}

    def get_passive_detail(self, key, *, culture='*', limit=128, cursor=None, include_diagnostics=False,
                           include_documentation=False, include_graph=False):
        option = self.one('ability_option_metadata', 'ability_key', key)
        if not option or option['classification'] != 'core_passive':
            raise ValueError('passive detail requires a classified core passive')
        links = [row for row in self.rows('unit_abilities', 'ability_key', key, 'culture_key,unit_key,record_id')
                 if row['culture_key'] == culture]
        if not links:
            raise ValueError('passive detail culture requires a matching source-qualified unit link')
        c = Packet(self)
        mechanic = c.mechanic(links[0], option, c.detail_gaps)
        if cursor is not None and not include_graph:
            raise ValueError('passive graph cursor requires include_graph=True')
        result = {'schema_version': PACKET_VERSION, 'snapshot': c.packet['snapshot'], 'mechanic': mechanic,
                'sources': c.packet['sources'], 'provenance': c.packet['provenance'],
                'detail_refs': c.packet['detail_refs'], 'diagnostic_count': len(c.detail_gaps), 'payload_graph': c.packet['payload_graph']}
        if include_graph:
            result['graph'] = self.get_detail('record:' + option['definition_record'], limit=limit, cursor=cursor)
        if include_diagnostics:
            result['gaps'] = c.detail_gaps
        if include_documentation and key in RESEARCHED_PASSIVES:
            result['explanation_documentation'] = {
                'url': PASSIVE_RESEARCH_DOCUMENTATION,
                'basis': 'Reviewed interpretation of pinned source records with separately attributed external corroboration; numerical records retain their pinned patch scope.',
            }
        return result

    def get_detail(self, ref, *, limit=128, cursor=None):
        """Cycle-safe bounded graph with explicit continuation and every edge."""
        if type(limit) is not int or not 1 <= limit <= 256:
            raise ValueError('detail limit must be between 1 and 256')
        kind, sep, key = ref.partition(':')
        if not sep:
            raise ValueError('invalid detail reference')
        if kind == 'option':
            row = self.one('ability_option_metadata', 'ability_key', key)
            if row is None:
                raise KeyError(key)
            c = Packet(self)
            for field in ('definition_record', 'casting_record'):
                if row[field]:
                    c.evidence(row[field])
            return {'schema_version': PACKET_VERSION, 'snapshot': c.packet['snapshot'], 'status': 'deferred', 'option': row,
                    'sources': c.packet['sources'], 'provenance': c.packet['provenance'],
                    'reason': 'Activated and unresolved effect payloads are outside this interface.'}
        if kind == 'availability':
            unit = self.resolved(key)
            c = Packet(self)
            rows = self.rows('unit_availability', 'unit_key', unit['unit_key'])
            permissions = self.rows('unit_rosters', 'unit_key', unit['unit_key'])
            for row in rows + permissions:
                c.evidence(row['record_id'])
            return {'schema_version': PACKET_VERSION, 'snapshot': c.packet['snapshot'], 'availability': rows,
                    'permissions': permissions, 'sources': c.packet['sources'], 'provenance': c.packet['provenance']}
        if kind != 'record':
            raise ValueError('unsupported detail kind')
        self.record(key)
        binding = {'unit_key': ref, 'subculture_key': None}
        offset = 0
        if cursor:
            offset = self.decode_cursor(cursor, binding, 'combined', 'abilities', limit)['offset']
        # Only these inbound attachments belong to the referenced owner.
        inbound = ('special_ability_to_special_ability_phase_junctions_tables.special_ability',
                   'unit_special_abilities_tables.key',
                   'special_ability_phase_stat_effects_tables.phase',
                   'special_ability_phase_attribute_effects_tables.phase',
                   'special_ability_to_auto_deactivate_flags_tables.special_ability',
                   'special_ability_to_invalid_target_flags_tables.special_ability',
                   'special_ability_to_invalid_usage_flags_tables.special_ability',
                   'special_ability_to_recharge_contexts_tables.special_ability',
                   'special_ability_intensity_settings_tables.ability',
                   'special_ability_behaviour_groups_to_types_tables.group',
                   'unit_ability_superseded_abilities_set_elements_tables.set_key')
        # Bounded traversal: the continuation rebuilds only the visited prefix,
        # never scans source tables or recursively expands activated roots.
        queue = [key]; seen = set(); nodes = []; edges = []; boundary = []
        c = Packet(self)
        while queue and len(nodes) < offset + limit:
            rid = queue.pop(0)
            if rid in seen:
                continue
            seen.add(rid)
            table, row = self.record(rid)
            c.evidence(rid)
            nodes.append({'id': rid, 'kind': table, 'key': json.loads(self.one('record_provenance', 'id', rid)['native_key_json']),
                          'native_parameters': c.native(table, row), 'provenance_refs': [rid]})
            if table.endswith('_metadata'):
                continue
            selected = self.rows('relation_edges', 'source_record', rid, 'relation,target_key_json,edge_ordinal')
            placeholders = ','.join('?' for _ in inbound)
            selected += [dict(r) for r in self.db.execute(
                f'SELECT * FROM relation_edges WHERE target_record=? AND relation IN ({placeholders}) ORDER BY source_record,relation,edge_ordinal',
                (rid, *inbound))]
            for edge in selected:
                identity = (edge['source_record'], edge['relation'], edge['target_key_json'], edge['edge_ordinal'])
                if identity not in {tuple(e[k] for k in ('source_record', 'relation', 'target_key_json', 'edge_ordinal')) for e in edges}:
                    edges.append(edge)
                target = edge['source_record'] if edge['target_record'] == rid else edge['target_record']
                if target and target not in seen and target not in queue:
                    queue.append(target)
        if offset >= len(nodes) and offset:
            raise ValueError('cursor offset outside detail graph')
        returned = nodes[offset:]
        ids = {n['id'] for n in returned}
        page_edges = [e for e in edges if e['source_record'] in ids or e['target_record'] in ids]
        boundary = sorted({r for e in page_edges for r in (e['source_record'], e['target_record']) if r and r not in ids})
        for rid in boundary:
            c.evidence(rid)
        next_cursor = self.cursor(binding, 'combined', 'abilities', len(nodes), limit) if queue else None
        return {'schema_version': PACKET_VERSION, 'snapshot': c.packet['snapshot'], 'nodes': returned,
                'edges': page_edges, 'boundary_refs': ['record:' + r for r in boundary],
                'state': 'partial' if queue else 'complete', 'cursor': next_cursor,
                'sources': c.packet['sources'], 'provenance': c.packet['provenance']}


class Packet:
    def __init__(self, queries):
        self.q = queries
        self.detail_gaps = []
        owners = json.loads(queries.snapshot['owners_json'])
        self.packet = {'schema_version': PACKET_VERSION, 'mode': 'combined',
                       'snapshot': {'commit': queries.snapshot['source_commit'],
                                    'owners': {k: {'patch': v.get('extraction_patch', v.get('patch')),
                                                   'build': v['build'], 'schema': v['schema']} for k, v in owners.items()},
                                    'baseline': {k: v for k, v in json.loads(queries.snapshot['baseline_json']).items()
                                                 if k in ('game', 'unit_scale', 'rank', 'context')},
                                    'coverage': {k: v for k, v in json.loads(queries.snapshot['coverage_json']).items() if k != 'packet_interface'}},
                       'units': [], 'trait_descriptions': {}, 'sources': {}, 'provenance': {},
                       'detail_refs': {}, 'payload_graph': {'nodes': [], 'edges': []}}

    def native(self, table, row, fields=None):
        types = self.q.types.get(table, {})
        return {k: boolean(v) if types.get(k) == 'BOOLEAN' else v
                for k, v in row.items() if k != 'record_id' and (fields is None or k in fields)}

    def evidence(self, rid):
        if rid in self.packet['provenance']:
            return rid
        p = self.q.one('record_provenance', 'id', rid)
        if p is None:
            raise ValueError('missing provenance: ' + rid)
        path = p['source_file']
        sid = 's_' + hashlib.sha256(path.encode()).hexdigest()[:12]
        source = self.q.one('source_files', 'path', path)
        self.packet['sources'][sid] = {'path': path, 'sha256': source['sha256'], 'owner': source['owner']}
        self.packet['provenance'][rid] = {'source_id': sid, 'logical_record': p['logical_record'],
                                         'key': {k: '' if v is None else str(v) for k, v in json.loads(p['native_key_json']).items()},
                                         'source_line': p['source_line'], 'source_patch': p['source_patch'],
                                         'source_path': p['source_path']}
        lineage = self.q.rows('record_lineage', 'record_id', rid, 'lineage_record')
        if lineage:
            self.packet['provenance'][rid]['lineage_refs'] = [self.evidence(r['lineage_record']) for r in lineage]
        return rid

    def refs(self, *rows):
        return list(dict.fromkeys(self.evidence(r['record_id']) for r in rows if r is not None))

    def detail(self, kind, key):
        ref = kind + ':' + key
        self.packet['detail_refs'][ref] = {'kind': kind, 'key': key}
        return ref

    def loc(self, key):
        rows = self.q.rows('localization', 'key', key)
        if len({r['text'] for r in rows}) > 1:
            raise ValueError('conflicting localization: ' + key)
        if not rows:
            return None, []
        return clean_text(rows[0]['text']), self.refs(*rows)

    def gap(self, gaps, code, section, summary, refs=()):
        item = {'code': code, 'section': section, 'summary': summary, 'provenance_refs': list(refs)}
        if item not in gaps:
            gaps.append(item)

    def stored_gaps(self, rid, section, gaps):
        for g in self.q.rows('coverage_gaps', 'record_id', rid, 'kind,detail'):
            self.gap(gaps, g['kind'], section, g['detail'], [self.evidence(rid)])

    def attribute(self, row, gaps):
        key = row['attribute_key']
        name, nrefs = self.loc('unit_attributes_onscreen_name_' + key)
        text, trefs = self.loc('unit_attributes_bullet_text_' + key)
        refs = self.refs(row) + nrefs + trefs
        if text is None:
            text = 'Meaning unresolved: selected localization has no mechanical description.'
            self.gap(gaps, 'attribute_meaning_unknown', 'attributes', key + ': missing description.', refs)
        if '{{' in text:
            self.gap(gaps, 'unresolved_localization', 'attributes', key + ': unresolved text substitution.', refs)
        return {'key': key, 'name': name, 'summary': text, 'provenance_refs': refs}

    def condition(self, row, key, kind, gaps):
        text, refs = self.loc('special_ability_invalid_usage_flags_alt_description_' + key)
        if text is None:
            text, refs = self.loc('special_ability_invalid_usage_flags_description_' + key)
        # Shared UI wording often states eligibility, opposite to the flag.
        # Explain the encoded predicate; preserve localization through evidence.
        meaning = 'the host unit is alive' if key == 'unit_alive' else CONDITION_TEXT.get(key)
        health = re.fullmatch(r'health_(above|below)_(\d+)%(_base)?', key)
        if health:
            meaning = 'health ' + health[1] + ' ' + health[2] + '%' + (' of base health' if health[3] else '')
        if key == 'have_ammo_below_threshold' and text:
            threshold = re.search(r'Ammunition above (\d+(?:\.\d+)?)%', text)
            if threshold:
                meaning = 'ammunition below ' + threshold[1] + '% (threshold inferred from source UI wording)'
                self.gap(gaps, 'ammo_threshold_from_ui', 'abilities', key + ': threshold comes from selected UI wording rather than a numeric condition field.', self.refs(row) + refs)
        if meaning is None and text is None:
            meaning = key.replace('_', ' ') + ' (exact predicate not established)'
            self.gap(gaps, 'condition_meaning_unknown', 'abilities', key + ': no selected wording.', self.refs(row))
        elif meaning is None:
            meaning = key.replace('_', ' ')
        if key in ('climbing_manning_eq_on_platform', 'unit_is_not_pre_murderous_prowess'):
            self.gap(gaps, 'condition_predicate_detail', 'abilities', key + ': exact state/composition needs verification.', self.refs(row))
        return {'key': key, 'summary': meaning,
                'provenance_refs': self.refs(row) + refs}

    def mechanic(self, link, option, gaps):
        key = link['ability_key']
        definition = self.q.one('native_ability_definitions', 'key', key)
        casting = self.q.one('native_ability_casting', 'key', key)
        name, nrefs = self.loc('unit_abilities_onscreen_name_' + key)
        refs = self.refs(link, definition, casting) + nrefs
        classification = self.refs(definition, casting)
        mechanic = {'key': key, 'name': name, 'culture_key': link['culture_key'],
                    'requires_effect_enabling': boolean(option['requires_effect_enabling']),
                    'classification_evidence': classification, 'summary': '',
                    'native_parameters': self.native('native_ability_casting', casting or {}, CASTING_FIELDS),
                    'conditions': {k: [] for k in ('activates_when', 'deactivates_when', 'recipient_requirements', 'recharges_when', 'unavailable_when', 'invalid_targets', 'unresolved')},
                    'phases': [], 'effects': [], 'provenance_refs': refs,
                    'detail_ref': self.detail('record', definition['record_id'])}
        for table, field, category, wording in (
            ('native_special_ability_to_auto_deactivate_flags', 'deactivate_flag', 'deactivates_when', 'deactivation'),
            ('native_special_ability_to_invalid_usage_flags', 'invalid_usage_flag', 'unavailable_when', 'invalid usage'),
            ('native_special_ability_to_invalid_target_flags', 'invalid_target', 'invalid_targets', 'invalid target'),
            ('native_special_ability_to_recharge_contexts', 'recharge_context', 'recharges_when', 'recharge')):
            for row in self.q.rows(table, 'special_ability', key):
                mechanic['conditions'][category].append(self.condition(row, row[field], wording, gaps))
        if mechanic['conditions']['recharges_when']:
            self.gap(gaps, 'recharge_activation_boundary', 'abilities', key + ': recharge predicates and timer settings do not certify threshold equality, interrupted progress, reactivation or removal of an existing phase.', refs[:3])
        if mechanic['conditions']['deactivates_when']:
            self.gap(gaps, 'activation_boundary', 'abilities', key + ': deactivation evidence alone does not establish activation, threshold equality or refresh.', refs[:3])
        for phase_link in self.q.rows('native_ability_phase_links', 'special_ability', key,
                                      '"order",target_self,target_friends,target_enemies,phase,record_id'):
            phase = self.q.one('native_ability_phases', 'id', phase_link['phase'])
            if phase is None:
                self.gap(gaps, 'phase_missing', 'abilities', key + ': unresolved phase ' + phase_link['phase'], self.refs(phase_link))
                continue
            phrefs = self.refs(phase_link, phase)
            mechanic['phases'].append({'key': phase['id'], 'order': phase_link['order'],
                                      **{k: boolean(phase_link[k]) for k in ('target_self', 'target_friends', 'target_enemies')},
                                      'duration': phase['duration'], 'lifecycle': self.native('native_ability_phases', phase, PHASE_FIELDS),
                                      'provenance_refs': phrefs})
            # A phase shared by several recipient edges has one effect inventory.
            if any(e['phase_ref'] == phase['id'] for e in mechanic['effects']):
                continue
            mechanic['effects'].extend(self.phase_effects(phase, gaps))
            self.stored_gaps(phase['record_id'], 'abilities', gaps)
        for row in self.q.rows('native_special_ability_intensity_settings', 'ability', key):
            mechanic['effects'].append({'kind': 'unresolved', 'phase_ref': None,
                                         'native_kind': 'intensity_settings', 'native_parameters': self.native('native_special_ability_intensity_settings', row),
                                         'reason': 'Native intensity evidence; effective intensity and stacking require interpretation.', 'provenance_refs': self.refs(row)})
            self.gap(gaps, 'intensity_semantics', 'abilities', key + ': intensity is not applied to effects.', self.refs(row))
        # Payload/replacement/behavior dependencies retain typed lazy references.
        for source in (definition, casting):
            if source:
                self.stored_gaps(source['record_id'], 'abilities', gaps)
                for edge in self.q.rows('relation_edges', 'source_record', source['record_id'], 'relation,target_key_json,edge_ordinal'):
                    if edge['relation'] in ('unit_special_abilities_tables.key', 'unit_abilities_tables.type', 'unit_abilities_tables.source_type'):
                        continue
                    if edge['target_record']:
                        mechanic['effects'].append({'kind': 'payload_reference', 'phase_ref': None,
                                                     'node_ref': self.detail('record', edge['target_record']),
                                                     'relationship': edge['relation'], 'provenance_refs': self.refs(source)})
        if key in ('wh2_dlc13_unit_passive_kaboom', 'wh3_dlc26_unit_abilities_blow_apart') and casting:
            alive = [c for c in mechanic['conditions']['deactivates_when'] if c['key'] == 'unit_alive']
            if alive and casting['vortex']:
                _, tooltip_refs = self.loc('unit_abilities_tooltip_text_' + key)
                mechanic['conditions']['activates_when'].append({
                    'key': 'on_death',
                    'summary': 'the host dies (reviewed interpretation of this death-blast definition and unit-alive exclusion; exact scheduling unverified)',
                    'provenance_refs': list(dict.fromkeys(self.refs(casting) + tooltip_refs + [r for c in alive for r in c['provenance_refs']]))})
        if key in DEATH_PAYLOAD_PASSIVES and casting:
            for behavior in self.q.rows('native_special_ability_behaviour_groups_to_types', 'group', casting['behaviour']):
                event = {
                    'vortex_on_death': 'the host unit dies, releasing the linked blast',
                    'vortex_on_entity_death': 'an individual entity in the host unit dies, releasing the linked blast',
                }.get(behavior['behaviour'])
                if event:
                    event_refs = self.refs(casting, behavior)
                    mechanic['conditions']['activates_when'].append({
                        'key': behavior['behaviour'], 'summary': event + ' (interpreted from the behavior definition; exact scheduling unverified)',
                        'provenance_refs': event_refs})
                    mechanic['provenance_refs'] += event_refs
        if key in SURVIVAL_PASSIVES and casting and casting['miscast_explosion']:
            explosion = self.q.one('explosions', 'explosion_key', casting['miscast_explosion'])
            if explosion:
                phase = self.q.one('native_ability_phases', 'id', explosion['contact_phase_effect']) if explosion['contact_phase_effect'] else None
                for effect in mechanic['effects']:
                    if effect['kind'] == 'payload_reference' and effect['node_ref'] == 'record:' + explosion['record_id']:
                        effect['failure_context'] = {
                            'miscast_chance': casting['miscast_chance'],
                            'miscast_global_bonus': boolean(casting['miscast_global_bonus']),
                            'explosion_base_damage': explosion['base_damage'],
                            'explosion_ap_damage': explosion['ap_damage'],
                            'explosion_radius': explosion['radius'],
                            'explosion_affects_allies': boolean(explosion['affects_allies']),
                            'contact_phase_key': explosion['contact_phase_effect'],
                        }
                        if phase:
                            effect['failure_context'].update({
                                'contact_' + k: v for k, v in self.native('native_ability_phases', phase,
                                    ('damage_amount', 'hp_change_frequency', 'duration', 'max_damaged_entities', 'affects_allies', 'affects_enemies')).items()})
                        effect['provenance_refs'] = list(dict.fromkeys(effect['provenance_refs'] + self.refs(casting, explosion, phase)))
        if casting and casting['spawned_unit']:
            unit_key = casting['spawned_unit']
            unit_name, unit_refs = self.loc('land_units_onscreen_name_' + unit_key)
            # Reviewed display labels from the pinned tree's land_units localization;
            # that catalog is not imported, so do not invent retained row references.
            if unit_name is None:
                unit_name = {
                    'wh2_main_skv_inf_skavenslave_spearmen_0_summoned': 'Skavenslave Spears',
                    'wh3_dlc25_nur_inf_nurglings_summoned': 'Nurglings',
                    'wh3_dlc27_hef_inf_oceanids_split_up_summoned': 'Oceanids',
                    'wh2_dlc11_cst_inf_zombie_deckhands_mob_necrofex_summoned_0': 'Zombie Pirate Deckhand Mob',
                    'wh_main_vmp_cha_wight_king_0_summoned': 'Wight King',
                    'wh_main_vmp_inf_zombie_summoned': 'Zombies',
                    'wh_dlc03_bst_mon_chaos_spawn_0_summoned': 'Chaos Spawn',
                }.get(unit_key)
            spawn_refs = self.refs(casting) + unit_refs
            # This is a reviewed interpretation of two death-spawn definitions,
            # not a generic inversion of arbitrary deactivation predicates.
            death_spawn = key in ('wh2_main_unit_passive_the_rats_emerge',
                                  'wh3_dlc25_unit_passive_nurgling_emergence') and any(
                c['key'] == 'unit_alive' for c in mechanic['conditions']['deactivates_when'])
            if death_spawn:
                spawn_refs += [r for c in mechanic['conditions']['deactivates_when']
                               if c['key'] == 'unit_alive' for r in c['provenance_refs']]
            mechanic['effects'].append({
                'kind': 'summon', 'phase_ref': None, 'unit_key': unit_key,
                'unit_name': unit_name, 'trigger': 'on_death' if death_spawn else 'unresolved',
                'trigger_basis': 'Reviewed interpretation of passive summon with unit_alive deactivation; exact death-event scheduling unverified.' if death_spawn else 'Activation event not established by summon fields.',
                'spawn_type': casting['spawn_type'], 'num_uses': casting['num_uses'],
                'native_parameters': self.native('native_ability_casting', casting,
                    ('spawn_is_transformation', 'spawn_is_decoy', 'spawn_shares_health_and_fatigue')),
                'provenance_refs': list(dict.fromkeys(spawn_refs))})
            if key == 'wh3_dlc27_unit_passive_split_up_hidden':
                mechanic['effects'][-1]['trigger_basis'] = (
                    'Low-health summon route, disabled above 25% health. Exact threshold equality and event scheduling unverified; not the death-blast route.')
            if key == 'wh2_dlc11_unit_passive_abandon_ship':
                mechanic['effects'][-1]['trigger_basis'] = 'Host low-health summon, disabled above 50% host health; exact threshold equality and scheduling unverified.'
            if key in TARGET_SUMMON_PASSIVES:
                mechanic['effects'][-1]['trigger_basis'] = (
                    'Enemy-targeted damage and summon; target health/class restrictions are not caster conditions. '
                    'Whether summoning requires the target to die, exact timing and caster-versus-target placement anchor remain unverified.')
            if key in TARGET_SUMMON_PASSIVES or key == 'wh2_dlc11_unit_passive_abandon_ship':
                mechanic['effects'][-1]['provenance_refs'] = list(dict.fromkeys(spawn_refs + [
                    r for role in ('invalid_targets', 'deactivates_when') for c in mechanic['conditions'][role] for r in c['provenance_refs']]))
        if not mechanic['effects']:
            mechanic['effects'].append({'kind': 'unresolved', 'phase_ref': None, 'native_kind': 'passive_definition',
                                         'native_parameters': {}, 'reason': 'No mapped effects in the retained definition.', 'provenance_refs': classification})
            self.gap(gaps, 'effect_meaning_unknown', 'abilities', key + ': no mapped effect.', classification)
        if key in EXPLAINED_PASSIVES:
            for effect in mechanic['effects']:
                if effect.get('native_kind') == 'phase' and effect['phase_ref'] == 'wh2_main_unit_passive_rebirth_buffer':
                    effect['reason'] = 'Buffer phase before the healing phase; duration setting 1, with no numerical modifier. Exact transition timing unverified.'
                if key in RESEARCHED_PASSIVES and effect.get('native_kind') == 'phase':
                    role = EXPLAINED_PHASE_ROLES.get(effect['phase_ref'])
                    if role:
                        effect['reason'] = role
                    elif casting and (casting['vortex'] or casting['bombardment']):
                        effect['reason'] = 'Ability phase with no numerical modifier; damage comes from the separately linked vortex or bombardment. Exact phase-to-payload timing remains unverified.'
                if effect.get('native_kind') == 'phase' and (
                        effect['phase_ref'] == 'wh2_main_unit_passive_rebirth_buffer' or
                        (key in RESEARCHED_PASSIVES and (effect['phase_ref'] in EXPLAINED_PHASE_ROLES or
                         (casting and (casting['vortex'] or casting['bombardment']))))):
                    effect['kind'] = 'phase_role'
                    phase_ref = effect['phase_ref']
                    gaps[:] = [gap for gap in gaps if not (
                        gap['code'] == 'phase_effect_unknown' and gap['summary'] == phase_ref + ': no mapped numerical effect.')]
                if key == 'wh3_dlc27_unit_passive_burrowing_instinct' and effect.get('native_kind') == 'phase_behavior':
                    effect['reason'] = 'The rebirth stance is used with battlefield departure when the Dread Maw breaks, not resurrection; exact transition timing remains unverified.'
            if key == 'wh3_dlc25_lord_passive_feast_of_the_maggot_lord' and casting:
                for behavior in self.q.rows('native_special_ability_behaviour_groups_to_types', 'group', casting['behaviour']):
                    if behavior['behaviour'] == 'tamurkhan_death':
                        mechanic['conditions']['activates_when'].append({
                            'key': 'tamurkhan_death',
                            'summary': 'Tamurkhan reaches death with an eligible nearby enemy character (reviewed death-response behavior; exact execution timing unverified)',
                            'provenance_refs': self.refs(casting, behavior)})
            if key in ('wh3_main_lord_passive_wrath_of_khorne', 'wh_dlc06_lord_passive_locus_of_power'):
                for condition in mechanic['conditions']['invalid_targets']:
                    if condition['key'] == 'other_abilities_none_on_wind_up':
                        condition['summary'] = 'the target has no ability winding up (which non-spell abilities qualify remains unverified)'
            self.passive_payloads(mechanic, gaps)
            _, tooltip_refs = self.loc('unit_abilities_tooltip_text_' + key)
            mechanic['provenance_refs'] += tooltip_refs
        mechanic['summary'] = self.summary(mechanic)
        return mechanic

    def phase_effects(self, phase, gaps):
        key = phase['id']; refs = self.refs(phase); effects = []
        for row in self.q.rows('native_phase_stat_effects', 'phase', key, 'stat,record_id'):
            effects.append({'kind': 'stat_modifier', 'phase_ref': key,
                            'stat': STAT_NAMES.get(row['stat'], row['stat']),
                            'operation': {'add': 'add', 'mult': 'multiply'}.get(row['how'], 'native'),
                            'native_operation': row['how'], 'value': row['value'], 'provenance_refs': self.refs(row)})
        for row in self.q.rows('native_phase_attribute_effects', 'phase', key, 'attribute,record_id'):
            # Attribute polarity controls application, not benefit/harm.
            operation = {'positive': 'grant', 'negative': 'remove'}.get(row['attribute_type'], 'native')
            effects.append({'kind': 'attribute_effect', 'phase_ref': key, 'attribute_key': row['attribute'],
                            'operation': operation, 'recipient': None,
                            'native_parameters': {'attribute_type': row['attribute_type']}, 'provenance_refs': self.refs(row)})
            if operation == 'native':
                self.gap(gaps, 'attribute_operation', 'abilities', key + ': attribute application is unknown for ' + str(row['attribute_type']) + '.', self.refs(row))
        if phase['damage_amount'] not in (0, None):
            effects.append({'kind': 'periodic_damage', 'phase_ref': key,
                            'native_parameters': {k: phase[k] for k in ('damage_amount', 'hp_change_frequency', 'max_damaged_entities')},
                            'provenance_refs': refs})
        if any(phase[k] not in (0, None) for k in ('heal_amount', 'barrier_heal_amount', 'resurrect')):
            effects.append({'kind': 'healing', 'phase_ref': key,
                            'native_parameters': {**{k: phase[k] for k in ('heal_amount', 'barrier_heal_amount', 'hp_change_frequency')},
                                                  'resurrect': boolean(phase['resurrect']), 'limits': {}}, 'provenance_refs': refs})
            self.gap(gaps, 'healing_units_limits', 'abilities', key + ': quantities, cadence and resurrection are native; effective healing units/caps are not certified.', refs)
        for edge in self.q.rows('relation_edges', 'source_record', phase['record_id'], 'relation,target_key_json,edge_ordinal'):
            if edge['target_record']:
                effects.append({'kind': 'payload_reference', 'phase_ref': key,
                                'node_ref': self.detail('record', edge['target_record']), 'relationship': edge['relation'], 'provenance_refs': refs})
        other = {k: v for k, v in self.native('native_ability_phases', phase, PHASE_FIELDS).items()
                 if v not in (0, None, False) and k not in ('effect_type', 'affects_allies', 'affects_enemies')}
        if other:
            effects.append({'kind': 'unresolved', 'phase_ref': key, 'native_kind': 'phase_behavior',
                            'native_parameters': other, 'reason': 'Phase settings retained; exact units or engine rules require further verification.', 'provenance_refs': refs})
            self.gap(gaps, 'phase_behavior_semantics', 'abilities', key + ': phase behavior needs interpretation.', refs)
        if key == 'wh2_dlc15_unit_abilities_exploding_unit':
            tooltip, tooltip_refs = self.loc('unit_abilities_tooltip_text_' + key)
            if tooltip and 'persistent banner VFX' in tooltip and 'indicate that a unit explodes' in tooltip:
                effects.append({'kind': 'visual_indicator', 'phase_ref': key,
                                'purpose': 'Persistent banner visual effect indicating that the unit explodes',
                                'provenance_refs': list(dict.fromkeys(refs + tooltip_refs))})
        if not effects:
            effects.append({'kind': 'unresolved', 'phase_ref': key, 'native_kind': 'phase', 'native_parameters': {},
                            'reason': 'Phase has no mapped numerical effect; engine behavior is unresolved.', 'provenance_refs': refs})
            self.gap(gaps, 'phase_effect_unknown', 'abilities', key + ': no mapped numerical effect.', refs)
        return effects

    def summary(self, mechanic):
        """Deterministic templates use only emitted structured evidence."""
        pieces = []
        for effect in mechanic['effects']:
            kind = effect['kind']; ph = effect['phase_ref']
            prefix = (ph + ': ') if len({p['key'] for p in mechanic['phases']}) > 1 and ph else ''
            if kind == 'stat_modifier':
                value = effect['value']; op = effect['operation']
                text = (f'{effect["stat"]} ' + (f'{value:+g}' if value is not None else 'unknown')) if op == 'add' else f'{effect["stat"]} x{value:g}' if op == 'multiply' and value is not None else f'{effect["stat"]}: value {value}; operation {effect["native_operation"]} is not mapped'
            elif kind == 'periodic_damage':
                n = effect['native_parameters']
                text = f'Periodic damage amount: {n["damage_amount"]}; interval setting: {n["hp_change_frequency"]}; maximum affected entities: {n["max_damaged_entities"]} (damage units and effective timing not verified)'
            elif kind == 'healing':
                n = effect['native_parameters']
                text = f'Healing amount: {n["heal_amount"]}; barrier healing amount: {n["barrier_heal_amount"]}; interval setting: {n["hp_change_frequency"]}; resurrection: {"enabled" if n["resurrect"] is True else "disabled" if n["resurrect"] is False else "unknown"} (amount units, effective timing and healing caps not verified)'
            elif kind == 'attribute_effect':
                name, refs = self.loc('unit_attributes_onscreen_name_' + effect['attribute_key'])
                if not name:
                    description, refs = self.loc('unit_attributes_bullet_text_' + effect['attribute_key'])
                    name = description.split('||', 1)[0] if description else None
                name = name if name and '{{' not in name else effect['attribute_key'].replace('_', ' ').title()
                effect['provenance_refs'] = list(dict.fromkeys(effect['provenance_refs'] + refs))
                verb = {'grant': 'Grants ', 'remove': 'Removes '}.get(effect['operation'])
                text = verb + name if verb else name + ': application rule unknown (source token: ' + str(effect['native_parameters']['attribute_type']) + ')'
            elif kind == 'summon':
                text = 'Summons ' + (effect['unit_name'] or effect['unit_key'])
                text += ' upon the host dying' if effect['trigger'] == 'on_death' else ' (activation event unresolved)'
                text += ' at the host position' if effect['spawn_type'] == 'unit_position' else '; spawn placement: ' + str(effect['spawn_type'])
                if effect['num_uses'] is not None and effect['num_uses'] >= 0:
                    text += f'; uses: {effect["num_uses"]:g}'
            elif kind == 'visual_indicator':
                text = effect['purpose']
            elif kind == 'payload_reference':
                text = 'linked ' + effect['relationship']
                if effect.get('failure_context'):
                    f = effect['failure_context']
                    chance = f['miscast_chance']
                    text = (f'Failure chance: {chance:.0%} (interpreted from miscast_chance={chance:g})' if chance is not None else 'Failure chance unknown')
                    text += f'; failure explosion direct damage: {f["explosion_base_damage"]} base / {f["explosion_ap_damage"]} armour-piercing'
                    if 'contact_damage_amount' in f:
                        text += f'; delivers a contact effect with damage amount {f["contact_damage_amount"]}, interval setting {f["contact_hp_change_frequency"]}, duration setting {f["contact_duration"]}, maximum affected entities {f["contact_max_damaged_entities"]}'
                        text += '; contact effect affects allies: ' + str(f['contact_affects_allies']).lower() + ', enemies: ' + str(f['contact_affects_enemies']).lower()
                    text += ' (failure scheduling, effective damage and exact recipients unverified)'

            elif effect.get('native_parameters'):
                parameters = {k: v for k, v in effect['native_parameters'].items()
                              if k not in ('ability', 'source_path', 'source_line', 'source_patch')}
                pieces_for_effect = []
                for k, v in parameters.items():
                    if k in PHASE_ACTIONS and isinstance(v, bool):
                        description = PHASE_ACTIONS[k] if v else PHASE_LABELS[k] + ': disabled'
                    else:
                        description = PHASE_LABELS.get(k, k.replace('_', ' ')) + ': ' + compact(v)
                        if k in PHASE_QUALIFICATIONS:
                            description += ' (' + PHASE_QUALIFICATIONS[k] + ')'
                    pieces_for_effect.append(description)
                text = '; '.join(pieces_for_effect)
                if effect.get('native_kind') == 'intensity_settings':
                    text += ' (effective scaling and stacking unverified)'
            else:
                text = effect['reason']
            text = text.rstrip('.')
            if prefix + text not in pieces:
                pieces.append(prefix + text)
        result = ('Effect: ' if all(e['kind'] in ('summon', 'visual_indicator') for e in mechanic['effects']) else 'While active: ') + '; '.join(pieces) + '.'
        result = self.explained_summary(mechanic) or result
        for category, label in (
            ('activates_when', 'Activation conditions'),
            ('recharges_when', 'Readiness/recharge conditions'),
            ('deactivates_when', 'Deactivates when'),
            ('unavailable_when', 'Unavailable when'),
            ('invalid_targets', 'Excluded target conditions'),
            ('recipient_requirements', 'Recipient requirements'),
            ('unresolved', 'Other conditions'),
        ):
            conditions = mechanic['conditions'].get(category, [])
            if conditions:
                result += ' ' + label + ': ' + '; '.join(c['summary'] for c in conditions) + '.'
        if mechanic['conditions'].get('recharges_when'):
            timers = mechanic['native_parameters']
            settings = []
            for field, label in (('initial_recharge', 'initial recharge'), ('recharge_time', 'subsequent recharge')):
                if timers.get(field) is not None and timers[field] >= 0:
                    settings.append(label + ': ' + str(timers[field]))
            if settings:
                result += ' Recharge timer settings: ' + '; '.join(settings) + '.'
        return result

    def explained_summary(self, mechanic):
        key = mechanic.get('key')
        if key in TARGET_SUMMON_PASSIVES:
            spawn = next(e for e in mechanic['effects'] if e['kind'] == 'summon')
            damage = next(e for e in mechanic['effects'] if e['kind'] == 'periodic_damage')
            n = damage['native_parameters']; c = mechanic['native_parameters']
            duration = next(p['duration'] for p in mechanic['phases'] if p['key'] == damage['phase_ref'])
            result = (f'Damages one eligible enemy {TARGET_SUMMON_PASSIVES[key]} unit and summons {spawn["unit_name"]}. '
                      'Targets above 20% health are excluded; this is a target-health restriction, not a caster-health trigger. '
                      f'Target interception range setting: {c["target_intercept_range"]:g}. '
                      f'Enemy damage phase: amount {n["damage_amount"]:g}, interval setting {n["hp_change_frequency"]:g}, '
                      f'duration setting {duration:g}, maximum affected entities {n["max_damaged_entities"]:g}. '
                      f'Uses: {spawn["num_uses"]:g}; recharge setting: {c["recharge_time"]:g}. ')
            if mechanic['requires_effect_enabling']:
                result += 'Requires effect enabling. '
            return result + ('Summon placement uses the unit-position setting; whether this anchors to the caster or target is unverified. '
                             'Exact threshold equality, target selection, damage timing, whether summoning requires a kill, and summoned-unit lifetime remain unverified.')
        if key in DEATH_PAYLOAD_PASSIVES:
            vortex = self.q.one('native_vortices', 'vortex_key', mechanic['native_parameters']['vortex'])
            if vortex:
                entity_event = any(c['key'] == 'vortex_on_entity_death' for c in mechanic['conditions']['activates_when'])
                subject = DEATH_PAYLOAD_PASSIVES[key]
                result = (f'An individual entity dying in {subject}' if entity_event else f'The death of {subject}')
                result += ' releases an expanding blast'
                result += ' that can hit allies and enemies. ' if boolean(vortex['affects_allies']) else ' that can hit enemies without affecting allies. '
                if key == 'wh3_dlc26_unit_abilities_force_of_total_destruction':
                    result += ('A separate phase damages the Mangler Squigs themselves; its relationship to the death-triggered blast '
                               'and wind-up is not established by the behavior record. ')
                elif key == 'wh3_dlc27_unit_passive_split_up':
                    result += ('This is the damaging death route. The separate hidden Split Up ability summons Oceanids at low health '
                               'and carries a zero-damage pulse; do not count that summon as a death effect. ')
                elif key == 'wh3_dlc25_unit_passive_abandon_ship':
                    result += 'This Land Ship ability is distinct from the Necrofex summon ability with the same name. '
                elif key == 'wh3_dlc29_unit_passive_pestilent_perfection':
                    phase = self.q.one('native_ability_phases', 'id', vortex['contact_effect'])
                    if phase:
                        stats = self.q.rows('native_phase_stat_effects', 'phase', phase['id'])
                        for stat in stats:
                            if stat['stat'] == 'stat_morale' and stat['how'] == 'add':
                                result += f'The blast also delivers a contact effect: leadership {stat["value"]:+g}, duration setting {phase["duration"]:g}. '
                                mechanic['provenance_refs'] += self.refs(vortex, phase, stat)
                result += 'Damage, radius, delay and duration settings are retained separately; exact hit scheduling and overlap remain unverified.'
                return result
        if key in SURVIVAL_PASSIVES and key != 'wh2_main_unit_passive_too_horrible_to_die':
            f = next((e['failure_context'] for e in mechanic['effects'] if 'failure_context' in e), None)
            heal = next((e for e in mechanic['effects'] if e['kind'] == 'healing'), None)
            if f and f['miscast_chance'] is not None and heal:
                has_buffer = any(p['key'] == 'wh2_main_unit_passive_rebirth_buffer' for p in mechanic['phases'])
                result = 'Low-health survival mechanic, disabled above 10% health. '
                result += 'A buffer phase precedes healing. ' if has_buffer else 'The retained sequence has a healing phase and no buffer phase. '
                n = heal['native_parameters']
                duration = next(p['duration'] for p in mechanic['phases'] if p['key'] == heal['phase_ref'])
                result += f'Healing amount setting: {n["heal_amount"]:g}; interval setting: {n["hp_change_frequency"]:g}; duration setting: {duration:g}. '
                result += f'Failure chance: {f["miscast_chance"]:.0%} (interpreted from the casting definition). '
                result += ('Failure uses a zero-direct-damage explosion to deliver a damaging contact effect, '
                           'with allies enabled and enemies excluded; exact contact recipients are unverified. ')
                if key == 'wh2_dlc15_unit_passive_fiery_rebirth':
                    result += ('Fiery Rebirth also has a separate expanding magical, flaming blast that can hit allies and enemies; '
                               'its timing relative to success or failure remains unverified. ')
                if mechanic['native_parameters']['num_uses'] == 1:
                    result += 'One use. '
                else:
                    result += 'Use and recharge settings are -1 sentinels; repeatability is not established. '
                if mechanic.get('requires_effect_enabling'):
                    result += 'Requires effect enabling. '
                return result + 'Threshold equality, failure scheduling, healing units and caps remain unverified.'
        if key == 'wh2_main_unit_passive_the_rats_emerge':
            spawn = next((e for e in mechanic['effects'] if e['kind'] == 'summon' and e['trigger'] == 'on_death'), None)
            if spawn:
                return ('Summons ' + (spawn['unit_name'] or spawn['unit_key']) +
                        ' upon the host dying, at its position. This is a separate death-triggered summon from Too Horrible to Die; '
                        'the two abilities do not establish a single heal-versus-summon coin flip. '
                        'Exact spawn timing and summoned-unit lifetime remain unverified.')
        if key == 'wh2_main_unit_passive_too_horrible_to_die':
            f = next((e['failure_context'] for e in mechanic['effects'] if 'failure_context' in e), None)
            if f and f['miscast_chance'] is not None:
                return ('Low-health survival mechanic with a buffer phase followed by healing. '
                        f'Failure chance: {f["miscast_chance"]:.0%} (interpreted from the casting definition). '
                        'The failure branch uses an explosion to deliver a damaging contact effect; '
                        f'the explosion itself has {f["explosion_base_damage"]:g} base and {f["explosion_ap_damage"]:g} armour-piercing direct damage. '
                        'Failure timing, healing amount interpretation and exact contact recipients remain unverified; '
                        'the death summon is a separate mechanic.')
        return EXPLAINED_PASSIVES.get(key)

    def passive_payloads(self, mechanic, gaps):
        """Reuse the existing graph for the reviewed examples' calculation inputs."""
        graph = self.packet['payload_graph']
        allowed = {'native_vortices', 'native_bombardments', 'projectiles', 'explosions',
                   'native_ability_phases', 'native_phase_stat_effects', 'native_phase_attribute_effects'}
        roots = [e['node_ref'].split(':', 1)[1] for e in mechanic['effects'] if e['kind'] == 'payload_reference']
        queue = [(rid, 0) for rid in roots]; visited = set()
        def add(rid, table, row):
            node_id = self.detail('record', rid)
            if not any(n['id'] == node_id for n in graph['nodes']):
                params = self.native(table, row)
                params = {k: v for k, v in params.items() if not k.startswith('source_') and
                          not any(t in k for t in ('audio', 'particle', 'camera', 'display', 'icon', 'video', 'composite_scene', 'vfx'))}
                graph['nodes'].append({'id': node_id, 'kind': table,
                    'key': compact(json.loads(self.q.one('record_provenance', 'id', rid)['native_key_json'])),
                    'native_parameters': params, 'provenance_refs': self.refs(row)})
            return node_id
        while queue:
            rid, depth = queue.pop(0)
            if rid in visited:
                continue
            if len(visited) >= 64:
                self.gap(gaps, 'payload_detail_required', 'abilities', mechanic['key'] + ': further payload records require detail expansion.', [self.evidence(rid)])
                break
            visited.add(rid)
            table, row = self.q.record(rid)
            if table not in allowed:
                continue
            parent = add(rid, table, row)
            edges = self.q.rows('relation_edges', 'source_record', rid, 'relation,target_key_json,edge_ordinal')
            if table == 'native_ability_phases':
                # Effect rows reference their owning phase; include that reverse
                # ownership link just as weapon contact payloads do.
                for effect_table in ('native_phase_stat_effects', 'native_phase_attribute_effects'):
                    edges += [{'target_record': effect['record_id'], 'relation': 'phase_effect', 'edge_ordinal': None}
                              for effect in self.q.rows(effect_table, 'phase', row['id'], 'record_id')]
            for edge in edges:
                target = edge['target_record']
                if not target:
                    self.gap(gaps, 'payload_dependency_' + edge['status'], 'abilities', edge['relation'] + ': ' + edge['target_key_json'], self.refs(row))
                    continue
                child_table, child = self.q.record(target)
                if child_table not in allowed:
                    continue
                if depth >= 4:
                    self.detail('record', target)
                    self.gap(gaps, 'payload_detail_required', 'abilities', mechanic['key'] + ': further payload records require detail expansion.', self.refs(row))
                    continue
                child_id = add(target, child_table, child)
                item = {'from': parent, 'to': child_id, 'relationship': edge['relation'],
                        'order': edge['edge_ordinal'], 'provenance_refs': self.refs(child if edge['relation'] == 'phase_effect' else row)}
                if item not in graph['edges']:
                    graph['edges'].append(item)
                queue.append((target, depth + 1))

    def traits(self, kind, attack, row, component=None, normalized=False):
        if normalized:
            inf = row['bonus_vs_infantry']; large = row['bonus_vs_large']
            magical = boolean(row['melee_is_magical']); flaming = boolean(row['melee_is_flaming'])
        else:
            inf = row.get('bonus_v_infantry', row.get('bonus_vs_infantry'))
            large = row.get('bonus_v_large', row.get('bonus_vs_large'))
            magical = boolean(row.get('is_magical'))
            ignition = row.get('ignition_amount')
            flaming = None if ignition is None else ignition > 0
        result = {'scope': {'attack_ref': attack['id'], 'component_ref': component},
                  'bonus_vs_infantry': inf, 'bonus_vs_large': large, 'magical': magical,
                  'flaming': flaming, 'provenance_refs': self.refs(row)}
        for tag, (key, explanation) in TRAIT_TEXT.items():
            if result[tag] not in (0, False, None):
                text, refs = self.loc(key)
                self.packet['trait_descriptions'][tag] = {'summary': explanation, 'provenance_refs': refs or self.refs(row)}
        return result

    def weapon_payload(self, source, attack_ref, gaps):
        """Inline immediate mechanical nodes; fuller graphs remain lazy."""
        if source is None:
            return
        root_id = source['record_id']
        # A scope node distinguishes two attacks sharing the same payload.
        scope_id = 'attack_payload:' + attack_ref
        graph = self.packet['payload_graph']
        if not any(n['id'] == scope_id for n in graph['nodes']):
            graph['nodes'].append({'id': scope_id, 'kind': 'attack_payload', 'key': attack_ref,
                                   'native_parameters': {}, 'provenance_refs': self.refs(source)})
        queue = [(root_id, scope_id, 0)]; visited = set()
        while queue:
            rid, parent_node, depth = queue.pop(0)
            if (rid, parent_node) in visited:
                continue
            visited.add((rid, parent_node))
            edges = self.q.rows('relation_edges', 'source_record', rid, 'relation,target_key_json,edge_ordinal')
            for edge in edges:
                target = edge['target_record']
                if not target:
                    self.gap(gaps, 'payload_dependency_' + edge['status'], 'weapons',
                             edge['relation'] + ': ' + edge['target_key_json'], [self.evidence(rid)])
                    continue
                table, row = self.q.record(target)
                # The explosion already has its own scoped attack and damage.
                if table == 'explosions':
                    continue
                node_ref = self.detail('record', target)
                if not any(n['id'] == node_ref for n in graph['nodes']):
                    fields = PHASE_FIELDS + ('duration', 'damage_amount', 'hp_change_frequency', 'max_damaged_entities', 'heal_amount', 'barrier_heal_amount', 'resurrect') if table == 'native_ability_phases' else None
                    native = self.native(table, row, fields)
                    # Exclude lineage and presentation from ordinary graph nodes.
                    native = {k: v for k, v in native.items() if not k.startswith('source_') and not any(t in k for t in ('audio', 'particle', 'camera', 'display', 'icon', 'video'))}
                    graph['nodes'].append({'id': node_ref, 'kind': table, 'key': compact(json.loads(self.q.one('record_provenance', 'id', target)['native_key_json'])),
                                           'native_parameters': native, 'provenance_refs': self.refs(row)})
                graph_edge = {'from': parent_node, 'to': node_ref, 'relationship': edge['relation'],
                              'order': edge['edge_ordinal'], 'provenance_refs': [self.evidence(rid)]}
                if graph_edge not in graph['edges']:
                    graph['edges'].append(graph_edge)
                if depth < 1:
                    queue.append((target, node_ref, depth + 1))
                if table == 'native_ability_phases':
                    for effect_table in ('native_phase_stat_effects', 'native_phase_attribute_effects'):
                        for effect in self.q.rows(effect_table, 'phase', row['id']):
                            effect_ref = self.detail('record', effect['record_id'])
                            if not any(n['id'] == effect_ref for n in graph['nodes']):
                                graph['nodes'].append({'id': effect_ref, 'kind': effect_table, 'key': row['id'],
                                                       'native_parameters': self.native(effect_table, effect, ('stat', 'value', 'how', 'attribute', 'attribute_type')),
                                                       'provenance_refs': self.refs(effect)})
                            item = {'from': node_ref, 'to': effect_ref, 'relationship': 'phase_effect', 'order': None, 'provenance_refs': self.refs(effect)}
                            if item not in graph['edges']:
                                graph['edges'].append(item)
                self.stored_gaps(target, 'weapons', gaps)

    def unit(self, resolved, mode, section, offsets, limit):
        q = self.q; key = resolved['unit_key']
        profile = q.one('unit_profiles', 'unit_key', resolved['profile_unit_key'])
        # Profile values are shared; provenance is selected from the source key.
        availability = q.rows('unit_availability', 'unit_key', key)
        if resolved['subculture_key'] is not None:
            availability = [r for r in availability if r['subculture_key'] == resolved['subculture_key']]
        ev = availability[0]['record_id']; self.evidence(ev)
        gaps = []; coverage = []
        unit = {'identity': {'unit_key': key, 'profile_unit_key': resolved['profile_unit_key'],
                             'unit_keys': json.loads(profile['unit_keys']), 'subculture_key': resolved['subculture_key'],
                             'faction_name': json.loads(profile['faction_name']), 'name': profile['unit_name'],
                             'unit_type': profile['tactical_category']},
                'body': {**{k: profile[k] for k in ('entity_count', 'hp_per_entity', 'total_hp', 'barrier_health')},
                         'size': profile['primary_target_size'], 'components': []},
                'movement': {k: profile[k] for k in ('speed', 'mass')}, 'leadership': profile['leadership'],
                'melee': None, 'ranged': {'status': 'unresolved'},
                'passives': {'protection': {k: profile[k] for k in PROTECTION},
                             'attack_traits': {'melee': None, 'ranged': None, 'explosion': None, 'additional': []},
                             'attributes': [], 'abilities': []},
                'cost': {k: profile[v] for k, v in (('multiplayer', 'multiplayer_cost'), ('campaign_recruitment', 'campaign_recruit_cost'), ('campaign_upkeep', 'campaign_upkeep'))},
                'activated_options': [], 'provenance_refs': [ev], 'coverage': {'melee': 'unresolved', 'ranged': 'unresolved', 'sections': coverage, 'gaps': gaps}}
        self.detail('availability', key)
        self.stored_gaps(ev, 'components', gaps)

        def page(name, records, include=True):
            total = len(records); offset = offsets.get(name, 0)
            if not include:
                self.gap(gaps, 'section_projection', name, name + ' omitted by requested projection.')
                coverage.append({'name': name, 'state': 'omitted', 'returned': 0, 'total': total, 'cursor': None})
                return []
            if offset and offset >= total:
                raise ValueError('cursor offset outside section')
            selected = records[offset:offset + limit]
            more = offset + len(selected) < total
            coverage.append({'name': name, 'state': 'partial' if more else 'complete', 'returned': len(selected), 'offset': offset,
                             'total': total, 'cursor': q.cursor(resolved, mode, name, offset + len(selected), limit) if more else None})
            return selected

        components = q.rows('unit_components', 'unit_key', key, 'component_role,relationship_key,battle_entity_key,record_id')
        # Attacks carry references only to components actually returned.
        component_ids = {}
        for c in page('components', components, section in (None, 'components', 'weapons')):
            cid = 'component:' + c['record_id']
            component_ids.setdefault(c['component_role'], []).append(cid)
            unit['body']['components'].append({'id': cid, 'role': c['component_role'],
                                               'count': c['component_count'], 'hp_per_component': c['base_hp_per_component'],
                                               'bonus_hp_per_component': c['bonus_hp_per_component'], 'known_hp_total': c['known_hp_total'],
                                               'size': c['size_class'], 'targetable': boolean(c['can_be_targeted']),
                                               'primary': boolean(c['is_primary_health_pool']), 'provenance_refs': self.refs(c)})
            self.stored_gaps(c['record_id'], 'components', gaps)
            if c['can_be_targeted'] is None:
                self.gap(gaps, 'targetability_unknown', 'components', c['component_role'] + ': targetability unknown.', self.refs(c))
        weapons = q.rows('unit_weapon_links', 'unit_key', key, "attack_type,slot,is_default_projectile DESC,projectile_key,record_id")
        def weapon_order(w):
            primary = (w['melee_weapon_key'] == profile['source_melee_weapon_key'] and w['slot'] == 'primary') if w['attack_type'] == 'melee' else (
                w['missile_weapon_key'] == profile['source_missile_weapon_key'] and w['projectile_key'] == profile['source_projectile_key'])
            return (w['attack_type'], not primary, w['component_role'], w['slot'], not w['is_default_projectile'], w['projectile_key'] or '', w['record_id'])
        weapons.sort(key=weapon_order)
        weapons = [w for w in weapons if (mode != 'melee' or w['attack_type'] == 'melee') and (mode != 'missile' or w['attack_type'] != 'melee')]
        selected_weapons = page('weapons', weapons, section in (None, 'weapons'))
        melee = []; ranged = []; attack_traits = unit['passives']['attack_traits']
        for w in selected_weapons:
            crefs = component_ids.get(w['component_role'], [])
            component = crefs[0] if len(crefs) == 1 else None
            if component is None and w['component_role'] != 'unit':
                self.gap(gaps, 'component_scope_unresolved', 'weapons', w['record_id'] + ': component attachment is unavailable or ambiguous.', self.refs(w))
            if w['attack_type'] == 'melee':
                raw = q.one('melee_weapons', 'key', w['melee_weapon_key'])
                primary = w['slot'] == 'primary' and w['melee_weapon_key'] == profile['source_melee_weapon_key']
                a = {'id': 'melee:' + w['record_id'], 'weapon_key': w['melee_weapon_key'],
                     'component_ref': component, 'slot': w['slot'], 'attack': profile['melee_attack'],
                     'defence': profile['melee_defence'], 'charge_bonus': profile['charge_bonus'],
                     'base_damage': profile['weapon_base_damage'] if primary else (raw or {}).get('damage'),
                     'ap_damage': profile['weapon_ap_damage'] if primary else (raw or {}).get('ap_damage'),
                     'attack_interval': profile['attack_interval'] if primary else (raw or {}).get('melee_attack_interval'),
                     'max_splash_targets': profile['max_splash_targets'] if primary else (raw or {}).get('splash_attack_max_attacks'),
                     'native_parameters': self.native('melee_weapons', raw or {}, ('weapon_length', 'splash_attack_target_size', 'splash_attack_power_multiplier', 'collision_attack_max_targets', 'collision_attack_max_targets_cooldown', 'contact_phase', 'scaling_damage')),
                     'provenance_refs': self.refs(w, raw) + [ev], 'detail_ref': self.detail('record', (raw or w)['record_id'])}
                if not raw:
                    self.gap(gaps, 'weapon_join_missing', 'weapons', str(w['melee_weapon_key']) + ': native weapon missing.', self.refs(w))
                elif primary:
                    for field, native_field in (('base_damage', 'damage'), ('ap_damage', 'ap_damage'), ('attack_interval', 'melee_attack_interval'), ('max_splash_targets', 'splash_attack_max_attacks')):
                        if a[field] != raw[native_field]:
                            self.gap(gaps, 'normalized_weapon_discrepancy', 'weapons',
                                     w['melee_weapon_key'] + ': normalized ' + field + ' differs from native ' + native_field + '.', a['provenance_refs'])
                melee.append(a)
                self.weapon_payload(raw, a['id'], gaps)
                traits = self.traits('melee', a, dict(profile, record_id=ev) if primary else (raw or w), component, normalized=primary)
                self.attach_traits(attack_traits, 'melee', traits)
            else:
                p = q.one('projectiles', 'projectile_key', w['projectile_key'])
                if p is None:
                    self.gap(gaps, 'projectile_join_missing', 'weapons', str(w['projectile_key']) + ': projectile unresolved.', self.refs(w))
                    # Do not claim a present attack without resolved payload.
                    next(s for s in coverage if s['name'] == 'weapons')['returned'] -= 1
                    continue
                mapping = {'range': 'effective_range', 'minimum_range': 'minimum_range', 'reload_time': 'base_reload_time',
                           'base_damage': 'base_damage', 'ap_damage': 'ap_damage', 'projectiles_per_shot': 'projectile_number',
                           'shots_per_volley': 'shots_per_volley', 'burst_size': 'burst_size', 'burst_shot_delay': 'burst_shot_delay',
                           'velocity': 'muzzle_velocity', 'spread': 'spread', 'marksmanship_bonus': 'marksmanship_bonus',
                           'calibration_distance': 'calibration_distance', 'calibration_area': 'calibration_area'}
                a = {'id': 'ranged:' + w['record_id'], 'weapon_key': w['missile_weapon_key'], 'projectile_key': w['projectile_key'],
                     'component_ref': component, 'slot': w['slot'], 'ammunition_pool': w['ammunition_pool'],
                     'is_default': boolean(w['is_default_projectile']), 'ammunition': w['ammunition'], 'accuracy': profile['accuracy'],
                     **{k: p[v] for k, v in mapping.items()}, 'explosion': None,
                     'native_parameters': self.native('projectiles', p, ('shot_type', 'collision_radius', 'mass', 'gravity', 'can_target_airborne', 'can_damage_allies', 'can_damage_buildings', 'projectile_penetration', 'penetration_entity_size_cap', 'max_penetration', 'expiry_range', 'expire_on_impact', 'can_bounce', 'can_roll', 'homing_params', 'scaling_damage', 'contact_stat_effect', 'overhead_stat_effect', 'shrapnel_key', 'spawned_vortex')),
                     'detail_ref': self.detail('record', p['record_id']), 'provenance_refs': self.refs(w, p)}
                if w['projectile_key'] == profile['source_projectile_key'] and w['missile_weapon_key'] == profile['source_missile_weapon_key']:
                    for out, normalized in (('range', 'range'), ('reload_time', 'reload_time'), ('base_damage', 'missile_base_damage'), ('ap_damage', 'missile_ap_damage'), ('projectiles_per_shot', 'projectiles_per_shot'), ('ammunition', 'ammunition')):
                        if a[out] != profile[normalized]:
                            self.gap(gaps, 'normalized_projectile_discrepancy', 'weapons',
                                     w['projectile_key'] + ': linked ' + out + ' differs from normalized default.', a['provenance_refs'] + [ev])
                x = q.one('explosions', 'explosion_key', p['explosion_key']) if p['explosion_key'] else None
                if x:
                    a['explosion'] = {'id': 'explosion:' + w['record_id'], 'key': x['explosion_key'],
                                      **{k: x[k] for k in ('base_damage', 'ap_damage', 'radius')}, 'provenance_refs': self.refs(x)}
                    self.attach_traits(attack_traits, 'explosion', self.traits('explosion', a['explosion'], x, component))
                    self.weapon_payload(x, a['explosion']['id'], gaps)
                elif p['explosion_key']:
                    self.gap(gaps, 'explosion_join_missing', 'weapons', p['explosion_key'] + ': explosion unresolved.', self.refs(p))
                ranged.append(a)
                self.weapon_payload(p, a['id'], gaps)
                self.attach_traits(attack_traits, 'ranged', self.traits('ranged', a, p, component))
                self.stored_gaps(p['record_id'], 'weapons', gaps)
            self.stored_gaps(w['record_id'], 'weapons', gaps)
        if melee:
            unit['melee'] = dict(melee[0], variants=melee[1:]); unit['coverage']['melee'] = 'present'
        else:
            unit['coverage']['melee'] = 'omitted' if mode == 'missile' or section not in (None, 'weapons') or offsets.get('weapons', 0) else 'unresolved'
            self.gap(gaps, 'melee_projection_or_gap', 'melee', 'Melee attack not returned in this page/projection.' if unit['coverage']['melee'] == 'omitted' else 'Melee attachment not resolved.', [ev])
        if ranged:
            unit['ranged'] = dict(ranged[0], status='present', variants=ranged[1:]); unit['coverage']['ranged'] = 'present'
        elif mode == 'melee' or section not in (None, 'weapons') or offsets.get('weapons', 0) or (
                any(w['attack_type'] != 'melee' for w in weapons) and next(s for s in coverage if s['name'] == 'weapons')['state'] == 'partial'):
            unit['ranged'] = {'status': 'omitted'}; unit['coverage']['ranged'] = 'omitted'
            self.gap(gaps, 'ranged_projection', 'ranged', 'Ranged attack omitted by requested page/projection.')
        elif profile['has_missile_weapon'] == 0:
            unit['ranged'] = None; unit['coverage']['ranged'] = 'known_none'
        else:
            unit['coverage']['ranged'] = 'unresolved'
            self.gap(gaps, 'ranged_unresolved', 'ranged', 'Missile evidence exists or is unknown but no ranged payload was returned.', [ev])
        weapon_coverage = next(s for s in coverage if s['name'] == 'weapons')
        if weapon_coverage['state'] == 'complete' and weapon_coverage['returned'] + weapon_coverage.get('offset', 0) != weapon_coverage['total']:
            weapon_coverage['state'] = 'unresolved'
        if section in (None, 'weapons'):
            for row in q.rows('unit_contact_effects', 'unit_key', key):
                self.detail('record', row['record_id'])
                self.stored_gaps(row['record_id'], 'weapons', gaps)
        for row in page('attributes', q.rows('unit_attributes', 'unit_key', key, 'attribute_key,record_id'), section in (None, 'attributes')):
            unit['passives']['attributes'].append(self.attribute(row, gaps))
        ability_links = q.rows('unit_abilities', 'unit_key', key, 'ability_key,culture_key,record_id')
        classified = [(row, q.one('ability_option_metadata', 'ability_key', row['ability_key'])) for row in ability_links]
        passives = [(r, o) for r, o in classified if o and o['classification'] == 'core_passive']
        options = [(r, o) for r, o in classified if not o or o['classification'] != 'core_passive']
        # Consolidate only a redundant, equally qualified indicator. Filtering
        # precedes pagination; never hide a standalone or ambiguous unit link.
        consolidated = {}
        for indicator, indicator_option in passives:
            if indicator['ability_key'] != MURDEROUS_INDICATOR:
                continue
            matches = [(r, o) for r, o in passives if r['ability_key'] in MURDEROUS_BUFFS
                       and r['culture_key'] == indicator['culture_key']
                       and o['requires_effect_enabling'] == indicator_option['requires_effect_enabling']]
            if len(matches) == 1:
                consolidated[matches[0][0]['record_id']] = (indicator, indicator_option)
        hidden = {r['record_id'] for r, _ in consolidated.values()}
        passives = [(r, o) for r, o in passives if r['record_id'] not in hidden]
        for row, option in page('abilities', passives, section in (None, 'abilities')):
            mechanic = self.mechanic(row, option, gaps)
            if row['record_id'] in consolidated:
                indicator, indicator_option = consolidated[row['record_id']]
                mechanic['provenance_refs'] += self.refs(indicator)
                self.detail('record', indicator_option['definition_record'])
            unit['passives']['abilities'].append(mechanic)
        for row, option in page('activated_options', options, section in (None, 'activated_options')):
            name, refs = self.loc('unit_abilities_onscreen_name_' + row['ability_key'])
            refs = self.refs(row) + refs
            classification = []
            if option:
                for field in ('definition_record', 'casting_record'):
                    if option[field]:
                        classification.append(self.evidence(option[field]))
            else:
                classification = self.refs(row)
            entry = {'key': row['ability_key'], 'name': name, 'culture_key': row['culture_key'],
                     'classification': option['classification'] if option else 'unresolved',
                     'requires_effect_enabling': boolean(option['requires_effect_enabling']) if option else None,
                     'classification_evidence': classification, 'provenance_refs': refs,
                     'detail_ref': self.detail('option', row['ability_key'])}
            unit['activated_options'].append(entry)
            if entry['classification'] == 'unresolved':
                self.gap(gaps, 'classification_unresolved', 'activated_options', row['ability_key'] + ': classification unresolved.', refs)
        gaps.sort(key=lambda g: (g['section'], g['code'], g['summary']))
        return unit

    @staticmethod
    def attach_traits(traits, kind, value):
        if traits[kind] is None:
            traits[kind] = value
        else:
            traits['additional'].append({'kind': kind, 'traits': value})

    def prune(self):
        # Evidence collected during intermediate assembly is kept only if used.
        used = set()
        def walk(value):
            if isinstance(value, dict):
                for key, item in value.items():
                    if key in ('provenance_refs', 'classification_evidence'):
                        used.update(item)
                    else:
                        walk(item)
            elif isinstance(value, list):
                for item in value:
                    walk(item)
        walk(self.packet['units']); walk(self.packet['trait_descriptions']); walk(self.packet['payload_graph'])
        pending = list(used)
        while pending:
            for rid in self.packet['provenance'][pending.pop()].get('lineage_refs', []):
                if rid not in used:
                    used.add(rid); pending.append(rid)
        self.packet['provenance'] = {k: v for k, v in sorted(self.packet['provenance'].items()) if k in used}
        source_ids = {v['source_id'] for v in self.packet['provenance'].values()}
        self.packet['sources'] = {k: v for k, v in sorted(self.packet['sources'].items()) if k in source_ids}
        self.packet['detail_refs'] = dict(sorted(self.packet['detail_refs'].items()))
