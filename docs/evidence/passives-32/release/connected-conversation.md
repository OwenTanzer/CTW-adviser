# Final connected-conversation acceptance

MSI Chrome: used Settings > CTW Advisor > Refresh tools, then Try in chat. Fresh conversation URL: https://chatgpt.com/c/6acc69ba-7e9c-83e8-b157-fe0195cb4b11 . Read back its completed response through Windows accessibility and Copy response on 2026-10-11 Pacific. This is actual connected-chat evidence, separate from earlier direct HTTP acceptance. The original long-running chat may retain its old schema.

Below is the copied completed response. Its 'matched exactly' statement refers to the expected Goblin damage receipt; a reported Clanrat damage difference of about 1e-11 from the earlier platform receipt is within declared absolute1e-7 tolerance. No bitwise full-response equality claim is made for cross-platform floating-point outputs. Prior full direct-server/library/CLI equality evidence is retained separately. All requested effective inputs and phases agree.

**CTW issue #32’s requested connector acceptance passes.** The current callable schema exposes `scenario.sides.a.passives`, including `initial_active`, `equality`, and `reactivation`. No Refresh tools action was exposed to me; verification used the schema currently available in this conversation.

Both actual connected evaluator calls returned `status: "ok"` and matched the expected receipt exactly.

| Actual damage dealt over 120 seconds | Enabled | Disabled |
|---|---:|---:|
| Goblins → Clanrats | **868.3043478260697** | **1199.0869565217347** |
| Clanrats → Goblins | 1095.3488372093102 | 1095.3488372093102 |

All damage was melee; direct, explosion, and barrier absorption were zero.

The actual tool was `mcp__codex_apps__ctw_advisor_evaluate_single_unit_matchup`. First request:

```json
{
  "unit_a": "wh2_main_skv_inf_clanrat_spearmen_0",
  "unit_b": "wh_main_grn_inf_goblin_spearmen",
  "scenario": {
    "duration_seconds": 120,
    "separation_metres": 0,
    "baseline": "unmodified_ultra_rank_0",
    "mode": "custom_battle",
    "line_of_sight": true,
    "terrain_speed_factor": 1,
    "sides": {
      "a": {
        "order": "hold",
        "facing": "front",
        "fight": true,
        "fire": false,
        "active_contacts": 8,
        "charge_duration_seconds": 0,
        "passives": [{
          "key": "wh2_main_unit_passive_strength_in_numbers",
          "initial_active": true,
          "equality": "active",
          "reactivation": "unresolved"
        }]
      },
      "b": {
        "order": "hold",
        "facing": "front",
        "fight": true,
        "fire": false,
        "active_contacts": 8,
        "charge_duration_seconds": 0
      }
    }
  }
}
```

The second request was identical, changing only `scenario.sides.a.passives[0].initial_active` to `false`.

Returned immutable `source_facts` were identical across both calls:

| Unit / stat | Immutable base | Enabled effective | Disabled effective |
|---|---:|---:|---:|
| Clanrats melee defence | 24 | 32 | 24 |
| Clanrats leadership | 45 | 51 | 45 |
| Clanrats speed and ground speed | 4.2 | 3.7800000000000002 | 4.2 |
| Goblins melee defence | 28 | 28 | 28 |
| Goblins leadership | 50 | 50 | 50 |
| Goblins speed and ground speed | 3.3 | 3.3 | 3.3 |

Each side returned one phase spanning **0–120 seconds**, with transition cause `explicit_initial_state`. Enabled Clanrats had Strength in Numbers active throughout: speed ×0.9, defence +8, leadership +6. Disabled Clanrats and Goblins had empty active keys and modifiers. Both calls returned empty passive diagnostics.

The evaluator defaulted both units to full initial health. Clanrats ended at health fractions `0.9095516304348621` enabled and `0.875095108695632`, disabled, so neither run crossed 50%. Equality was explicitly assumed active; reactivation remained unresolved. These runs therefore verify initial-phase application, not threshold crossing or recovery behavior. Health conditions use component health divided by immutable base health, excluding barriers, with a 0.1-second transition window.

Strength in Numbers returned `conditional_scenario` coverage with no unsupported effects. Its modifier provenance references were `5513bd8dbb859f88e746:792` (speed), `:793` (defence), and `:794` (leadership); the below-50% deactivation reference was `32babbd7b0ea3ed79a68:149`. Engine activation, equality, refresh, and reactivation remain unverified scenario assumptions. **Scurry Away! was omitted**, and leadership does not drive routing because there is no morale model.

Both responses reported:

| Version field | Actual value |
|---|---|
| Adapter | `0.1.0` |
| Combat model | `combat-0.2.0` |
| Source packet | `1.19.0` |
| Store schema | `3` |
| Source commit | `595e22764b22e748afdbafafcb0a6258973e2451` |
| Unit source | Patch `9.0`, build `25507028`, schema `4` |
| Ability/effect source | Patch `9.0.1`, build `25546563`, schema `1` |
| Serving contract SHA-256 | `81e4d944387f0dc77a8e527c424261e8816fa49451c6dae3cd82d8220d0fae16` |

No HTTP substitution or manual combat formulas were used. No winner is claimed, and no issue was closed.
