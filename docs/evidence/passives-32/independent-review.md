# Independent review of PR #33

Requested by Owen on 11 October 2026 Pacific. A fresh independent agent inspected
published head `d155b345cc193a712004a8842fc6de20ff776763` in an isolated clean
checkout, without editing the implementation or production. The report is posted
as [GitHub review 5486538295](https://github.com/OwenTanzer/CTW-adviser/pull/33#pullrequestreview-5486538295).
The author connector records the report; it is not a separate GitHub-account approval.

## Original recommendation: request changes

One P2 correctness finding at `src/ctw_adviser/combat.py:419–421`: a speed
transition could make a previously unreachable range reachable, but the scheduler
only recomputed a first shot when the old `next_shot` was non-null.

Source-backed reproduction, without packet mutation:
A `wh2_main_skv_inf_skavenslave_slingers_0`,
B `wh2_dlc10_hef_inf_shadow_warriors_0`.

```json
{"duration_seconds":20,"separation_metres":121,"sides":{"a":{"order":"approach","initial_health_fraction":0.5001,"passives":[{"key":"wh2_main_unit_passive_strength_in_numbers","initial_active":true}],"cycle_seconds":5,"flight_seconds":0,"first_shot_delay_seconds":0},"b":{"order":"retreat","cycle_seconds":100,"flight_seconds":0,"first_shot_delay_seconds":0}}}
```

The t=0 impact removes Strength in Numbers and changes closing speed from -0.22
to +0.2 m/s. A reaches its 120-m range at 5 seconds and should fire at 5/10/15 s.
Reviewed code fired zero shots and dealt zero damage. Changing only initial_active
to false fired three shots and dealt 501.15 damage; both received 880 damage.

Independent verification on the original head: source verifier passed; full
208-test suite passed, zero skips, 93.145 s; receipt generator passed including
complete 120-second library/CLI/local-adapter equality. Independently reproduced
868.3043478260697/1199.0869565217347 Goblin damage and .13782608695663612
crossing convergence spread. No other confirmed findings.

## Repair

Local code commit `5a58fc4462277c76450bdd96dba4dd4275e5e426` recomputes scheduling
from current ranged eligibility instead of the old schedule's existence. Added
`test_speed_transition_starts_previously_unreachable_firing`, preserving the
source-backed reproduction and equality with its disabled control. Independent
recheck completed against this exact commit; outcome recorded below.

Actual new connected-tool parity and the enabled Clanrat/Goblin conversation
remain post-release gates. No merge, deployment or battle calibration is claimed.

## Independent recheck: finding resolved

Reviewer inspected the exact two-file repair at
`5a58fc4462277c76450bdd96dba4dd4275e5e426` in an isolated clean checkout and
recommends accepting the revised code. Reproduction now fires three shots for
501.15 damage, matching the otherwise identical disabled control.

All 11 passive tests passed, zero skips, 9.082 s. Additional independent
assertions passed for disabled firing, range remaining unreachable, explicit
wind-up and delayed impact. With an impact at 1 s and two-second wind-up,
firing begins at 9.1 s: zero shots at horizon 9.05, one at 9.15, three at 20.
No additional finding in the repair. This was a focused recheck, separate from
the original head's full-suite/source verification and from live acceptance.
