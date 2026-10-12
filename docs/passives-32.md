# Issue #32 acceptance receipt — 12 October 2026 UTC

Implementation: `combat-0.2.0`, branch `steve/conditional-passives-32`.
This is a reviewable implementation, not a completed production release.
See [machine-readable cases](evidence/passives-32/receipt.json),
[full test log](evidence/passives-32/tests.log), and
[actual connected baseline](evidence/passives-32/connected-control.json).

## Versions and provenance

- Local implementation commit: `5a57ced25d061178cf643befc4eafb862593c5ea`.
- Installed skill save: `a89f6975c4ddf8123ba0654389b6c9226ef530e0`, pushed and remote head verified.
- Base main: `331fbe8cc06cee2ed6019c2c25539ef0fa270b51` (PR #31 already merged).
- Source pin remains `595e22764b22e748afdbafafcb0a6258973e2451`.
- Store 3; import contract 2, SHA-256 `81e4d944387f0dc77a8e527c424261e8816fa49451c6dae3cd82d8220d0fae16`.
- Packet 1.19.0; unit owner 9.0/build 25507028, ultra/rank 0;
  ability/effect owner 9.0.1/build 25546563. No source migration.
- SQLite rebuilt with `scripts/rebuild_release.py` against the pinned checkout;
  source verification and atomic import passed (67,284,992-byte database).
- Shared modifier design inspected at #20 branch commit
  `562cdede29a9543e1a4c301885e51db4ce89d8c1`. New `modifiers.py` is its reusable
  field/operation layer; #20's spell subsystem is not imported or required.
- #5 remains empirical battle tests only; no new calibration claim.

## Gates

Final full pinned-source suite: **208 tests passed, zero skips**, 97.280 s.
Command: `python -m unittest discover -s tests -v`. The receipt generator
additionally verifies full 120-second library/CLI/local-adapter equality.

| #32 gate | Evidence and status |
|---|---|
| Initial-active exact pair | **Local pass**. Defence 24→32, leadership 45→51, native ground speed 4.2→3.78; source facts unchanged. Active phase spans 0–120 s. Goblin melee damage 1199.08695652→868.30434783; Clanrat damage 1095.34883721. No winner assertion. |
| Disabled regression | **Pass**, historical damage and remaining-health values within absolute 1e-7. Omitted-passive legacy path is still 1-second integration; explicit on/off pair shares the .1-second window. |
| Above/at/below 50% | **Pass**, .50001/.5/.49999 with both explicit equality policies. Tolerance 1e-9 of base health. |
| Crossing | **Pass**, initial .5001, health transition closes active phase and removes defence/speed/leadership without accumulation. .1/.05/.025 s integration yields damage spread 0.13782609, below declared fixture tolerance .5. Projectile crossing separately verifies immediate transition and contact recomputation from remaining distance. |
| Recovery/reactivation | **Pass**, synthetic health trace 1→.49→.6; unresolved/never remain inactive, explicit when_eligible reactivates. Unresolved case reports scoped diagnostic. No general healing implementation claimed. |
| Effect channels | **Pass**, defence changes melee hits/damage, separated-start speed changes contact, leadership changes only effective reporting; routing stays unknown. |
| Generalization | **Pass**, source-backed Scurry Away! uses the same resolver/application/lifecycle with explicit low-morale predicate assumption. Enabled/disabled/inapplicable speed 4.62/4.2/4.2; defence and leadership unchanged. |
| Negative/coverage | **Pass**, wrong bearer, snapshot mismatch, dangling phase/source refs, invalid operation, missing/nonfinite material value, duplicate stacking and missing non-health predicate assumptions reject. Unsupported effect kinds stay explicit. |
| Isolation/determinism | **Pass**, repeated requests, toggles and side swaps preserve source packets and produce equal ledgers. |
| Library/CLI/adapter | **Local pass**, complete structured result equality for exact 120-second scenario, not just metadata. **Actual new connected-tool acceptance pending release.** |
| Skill/workflow | **Canonical and installed instructions updated**, validated and pushed. Independent fresh conversation used real connector: correctly reported base-only omission because its schema lacks passives; did not fabricate an enabled result. **New enabled conversation pending release.** |
| Evidence | Exact requests, normalized assumptions, source/model versions, ledgers, provenance, convergence outputs and tolerances retained in JSON. Automated consistency is not battle accuracy. |

## Deployment and remaining limitations

Railway read on 12 October: service `ec9aff14-4f04-4386-a62b-d83657a0c927`,
production deployment `2509101e-4e78-4d79-b359-469ee34b3ef9` SUCCESS,
created 11 October 22:18:46 UTC. Listing exposes no commit SHA; none is inferred.
Actual connected tool returns combat-0.1.4/store3/packet1.19.0 and lacks passive
scenario fields. The original control is independently reproduced through it.
No merge, deployment, source pin, Railway setting or #5 scope change was made.

As required by `docs/hosted-mcp.md`, release follows review. Owner approval and
review must precede merge/deployment. After release, verify the new actual callable
schema, run this exact enabled/disabled pair through CTW Advisor, compare phases,
effective inputs and ledgers to the receipt, then record the real conversation.
Do not close #32 before those two remaining gates pass. Separately released #4
Claude ZIP in PR #27 remains outside this PR; its next build should consume the
updated canonical workflow, not fork passive formulas.

This bounded implementation supports one indefinite self phase per selected
passive, explicit initial activation, sourced health deactivation, and externally
assumed static non-health predicates. Finite duration, enabling, external targets,
intensity, complex activation and overlapping stat stacking are rejected.
Unsupported effect/lifecycle channels are visible and qualify the verdict.
No engine activation, equality, refresh or reactivation semantics are asserted.
Health uses total source base component health, excluding barrier; requested
starting health is separate from that denominator. Melee threshold detection has
one-window latency, with per-scenario convergence checks required when material.
Projectile damage uses effective inputs at arrival. Speed changes before first
launch restart the assumed shot delay from recomputed range entry. These timing
conventions, pooled casualties and leadership without routing are model limits.
