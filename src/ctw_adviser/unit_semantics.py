"""Source-backed unit supplements; never apply modifiers or resolve source conflicts by fiat."""

def supplement(context, unit, profile, components):
    q = context.q
    land = q.one('land_units', 'key', profile['source_land_unit_key'])
    entity = q.one('battle_entities', 'key', profile['source_battle_entity_key'])
    movement = unit['movement']
    movement.update(speed_basis='primary_body_run_speed',
                    primary_body_key=profile['source_battle_entity_key'],
                    ground_speed=(entity or {}).get('run_speed'),
                    flight_speed=(entity or {}).get('fly_speed'),
                    provenance_refs=context.refs(entity) if entity else [])
    unit['body']['firing_arc'] = {
        'primary_body_key': profile['source_battle_entity_key'],
        'native_fire_arc_close': (entity or {}).get('fire_arc_close'),
        'interpretation': 'Native primary-body setting; weapon coverage and angular units are not established.',
        'provenance_refs': context.refs(entity) if entity else []}
    crewed = profile['primary_component_role'] == 'engine' and (land or {}).get('category') == 'artillery'
    unit['body']['health_aggregation'] = {
        'rule': 'primary_and_separate_crew' if crewed else 'primary_body_only',
        'summary': ('Unit health includes primary artillery bodies and separate crew. Each primary body already includes one crew slot.' if crewed else
                    'Unit health uses the primary bodies; secondary component totals are not additional health.'),
        'provenance_refs': context.refs(land) if land else []}
    by_id = {'component:' + c['record_id']: c for c in components}
    for component in unit['body']['components']:
        source = by_id[component['id']]
        included = bool(source['is_primary_health_pool']) or (crewed and source['component_role'] == 'crew_or_rider')
        component['health_contribution'] = source['known_hp_total'] if included else 0
    ranged = unit['ranged']
    if not ranged or ranged.get('status') != 'present':
        return
    junctions = q.rows('unit_missile_weapon_junctions', 'unit', unit['identity']['unit_key'])
    for attack in [ranged, *ranged['variants']]:
        weapon = q.one('missile_weapons', 'key', attack['weapon_key'])
        precursor = None if not weapon or weapon['precursor'] is None else bool(weapon['precursor'])
        _, tooltip_refs = context.loc('ui_unit_bullet_point_enums_tooltip_precursor_missile') if precursor else (None, [])
        attack['firing_policy'] = {
            'precursor': precursor,
            'summary': ('With Fire-at-Will off, fires only at the ordered charge target; with Fire-at-Will on, fires at the closest enemy.' if precursor else None),
            'provenance_refs': (context.refs(weapon) if weapon else []) + tooltip_refs}
        attack['reload'] = {
            'projectile_base_interval': attack['reload_time'],
            'unit_reload_skill': (land or {}).get('reload'),
            'provenance_refs': context.refs(land) if land else []}
        flag = (weapon or {}).get('use_secondary_ammo_pool')
        native_pool = None if flag is None else ('secondary' if flag else 'primary')
        disagreement = native_pool is not None and native_pool != attack['ammunition_pool']
        infinite = None if not land or land['infinite_secondary_ammo'] is None else bool(land['infinite_secondary_ammo'])
        effective_pool = None if disagreement else native_pool
        attack['ammunition_supply'] = {
            'native_weapon_pool': native_pool,
            'native_primary_capacity': (land or {}).get('primary_ammo'),
            'native_secondary_capacity': (land or {}).get('secondary_ammo'),
            'infinite_secondary': infinite,
            'assignment_status': 'source_disagreement' if disagreement else ('sources_agree' if native_pool else 'unresolved'),
            'effective_pool': effective_pool,
            'capacity': (land or {}).get(effective_pool + '_ammo') if effective_pool else None,
            'unlimited': (infinite if effective_pool == 'secondary' else False) if effective_pool else None,
            'qualification': ('Normalized attachment pool and native weapon flag disagree; effective supply is unresolved.' if disagreement else None),
            'provenance_refs': context.refs(land, weapon)}
        attack['entity_stat_overrides'] = []
        for junction in junctions:
            if junction['missile_weapon'] != attack['weapon_key'] or not junction['battle_entity_stats_override']:
                continue
            override = q.one('battle_entity_stats', 'key', junction['battle_entity_stats_override'])
            attack['entity_stat_overrides'].append({
                'junction_id': junction['id'], 'key': junction['battle_entity_stats_override'],
                'base_melee_weapon': (override or {}).get('primary_melee_weapon'),
                'base_missile_weapon': (override or {}).get('primary_missile_weapon'),
                'detail_ref': context.detail('record', (override or junction)['record_id']),
                'provenance_refs': context.refs(junction, override)})
        explosion = attack['explosion']
        if explosion:
            raw = q.one('explosions', 'explosion_key', explosion['key'])
            fields = [k for k in q.types['explosions'] if not k.startswith('source_') and
                      not any(t in k for t in ('audio','particle','camera','display','icon','video','composite_scene','vfx'))]
            explosion['native_parameters'] = context.native('explosions', raw, fields)
            explosion['detail_ref'] = context.detail('record', raw['record_id'])
