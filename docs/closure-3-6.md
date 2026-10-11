# MCP and ChatGPT workflow acceptance — 11 October 2026

## Scope and versions

Issues #3 and #6 close the shared tool interface and usable tactical workflow.
Issue #5 remains open for actual-battle comparison of recorded predictions;
issue #4 retains Claude setup, tester onboarding and real Claude acceptance.
No combat/backend or production configuration changed for this closure.

Local reviewed base: `38affa2992696f284baf3ed6946d11a699163f43` (main, PR #22).
Source: `595e22764b22e748afdbafafcb0a6258973e2451`, unchanged.
Contract: `fefc71d116c658fa453f9786c67c9ff3b5eb23e40ec8882332914261cad246a1`.
Store 4, packet 1.20.0, adapter 0.1.0, calculator combat-0.1.4.
Base units: patch 9.0/build 25507028, ultra, rank 0, unmodified custom battle.
Scoped supplemental owner: 9.0.1/build 25546563, partial runtime coverage.

The local artifact rebuilt successfully and passed its release manifest check:
[evidence](evidence/closure-20261011/release-verify.json),
[manifest](evidence/closure-20261011/adviser.manifest.json).
Database SHA-256: `e0f18a10b3ef2cc7f290928a6026f0b31225b783d983e3dd263fd63f9b86b524`.
Machine-specific scratch paths in receipts identify execution location only;
the documented rebuild commands recreate the artifact elsewhere.

## Issue #3 acceptance

Live endpoint: `https://ctw-adviser-mcp-production.up.railway.app/mcp`.
Public unauthenticated read-only policy retained. Railway's service/domain reads
confirmed production service `ec9aff14-4f04-4386-a62b-d83657a0c927` and deployment
`5961fed3-5475-4ae9-8e06-59cf424f1004` SUCCESS, created 2026-10-11 13:27:12 UTC.
The redeploy listing does not give a commit SHA; no inferred deployment SHA is
claimed. [Health response](evidence/closure-20261011/health.json) and successful
live protocol calls separately establish current response behavior.

| Requirement | Evidence |
| --- | --- |
| Local startup, schemas, concise descriptions | 22 passing targeted HTTP, MCP-combat and consumer tests; stdio process and HTTP startup exercised against rebuilt artifact |
| Three fixtures and extra pair, preserved components/payloads | Live SDK pair probes and four connected conversations; artillery advice explicitly separates engine/crew and direct/explosion records |
| Missing, ambiguous, stale/incompatible states | SDK checks Feral Manticore ambiguity, missing Bloodletters shorthand, nonexistent profile, bad arguments; local disposable-store tests reject wrong source, snapshot identity and schema/contract mismatches |
| Protocol client plus ChatGPT Work connector | Official TypeScript SDK 1.32.1 live acceptance passes; independent Work agent calls recorded below; Owen separately reported all three fixtures plus an extra pair successful |
| Standard client-neutral tool surface | SDK initializes protocol 2025-06-18, discovers eight schemas/read-only annotations, calls tools and reconnects; no vendor-specific dispatch |
| Fixed fixtures and bounded results | SDK checks pagination, detail/provenance and four pairs; retained exact conversation inputs/results provide cross-client fixtures |
| Evaluation delegates to shared calculator | Ten successful connector evaluation data objects exactly equal independent CLI results; no client formulas added |
| Run/deploy/refresh documentation | Updated README, hosted-mcp.md, historical consumer note and chatgpt-workflow.md |

[Test log](evidence/closure-20261011/closure-tests.log) command:

```sh
CTW_ADVISER_DB=work/adviser.sqlite PYTHONPATH=src python -m unittest \
  tests.test_mcp_http tests.test_mcp_combat tests.test_consumers -v
```

[Successful SDK record](evidence/closure-20261011/remote-sdk.json) command:

```sh
npm install --prefix work/mcp-client @modelcontextprotocol/sdk@1.32.1
node scripts/accept_mcp_http.mjs https://ctw-adviser-mcp-production.up.railway.app/mcp
```

The first SDK attempt overlapped concurrent connector tests and returned HTTP
429; its [error receipt](evidence/closure-20261011/remote-sdk-first-attempt.err)
is retained. Connector tests also retained their 429 responses and successful
retries. After contention ended, the unchanged SDK suite passed. The existing
60-request global per-process minute budget was not changed. Honor Retry-After.

Eight server tools include two activated-effect tools outside this workflow.
This session's exposed CTW Advisor connector supplies all six unit/evaluation
tools required here; do not claim this proves the effect tools are installed in
that connector. The separate SDK did discover and exercise them.

## Issue #6 acceptance

Canonical [skill](../skills/ctw-matchup/SKILL.md), workflow 1.0.0, has linked
interpretation guidance and user-facing metadata. It was validated and saved
in the personal Skills workspace at commit `01618e6`; installation is separate
from merely placing repository instructions. [Setup/activation](chatgpt-workflow.md)
explains the connected endpoint and shared-version boundaries.

Four fresh Work agent conversations consumed the skill with task-local prompts,
called the actual CTW Advisor connector, and completed evidence-to-advice flows.
They were not given expected answers. These are delegated acceptance
conversations, not four human game sessions or proof of battle accuracy.
No synthetic user clarification replies were invented. Each prompt selected
exact variants and included its desired controlled variation.

| Conversation | Controlled cases | CLI matches | Useful outcome |
| --- | --- | ---: | --- |
| [Reiksguard / Doom Diver](evidence/closure-20261011/conversations/reiksguard/transcript.md) | 200 vs 100 m; immediate vs 22.5 s delayed arrival at both distances | 4 | Earlier contact but still one firing event; engine/crew distinction preserved |
| [Shielded Sea Guard / Blue Horrors](evidence/closure-20261011/conversations/sea_guard/task.json) | Front vs rear defensive facing, 100 m, Sea Guard hold | 2 | Nominal advantage flips; advice flags fragile frontal result and unmodeled turning/arcs |
| [Bloodletters / Kroxigor](evidence/closure-20261011/conversations/bloodletters/task.md) | Eight contacts each vs four Kroxigor contacts, 20 m | 2 | Restricting contacts improves Bloodletter survival without reversing nominal advantage |
| [Queen Bess / Reiksguard](evidence/closure-20261011/conversations/queen_bess/task.md) | 200 vs 300 m, artillery holds | 2 | One vs two launches; support advice remains qualitative, crew/engine distinct |

Full advice:
[Reiksguard](evidence/closure-20261011/conversations/reiksguard/advice.md),
[Sea Guard](evidence/closure-20261011/conversations/sea_guard/final-advice.md),
[Bloodletters](evidence/closure-20261011/conversations/bloodletters/final-advice.md),
[Queen Bess](evidence/closure-20261011/conversations/queen_bess/final_advice.md).
Each folder retains call arguments, raw structured/text results, CLI outputs and
comparison records. Advice reports defaults, both damage ledgers, timings,
conditional verdict/sensitivity, stopping distinctions and relevant omissions.

A separate [ambiguity conversation](evidence/closure-20261011/conversations/ambiguity/)
requested Feral Manticore versus Reiksguard. The skill presented four source
candidates and requested selection, making no evaluation call. Missing and
incompatible cases are tested at the protocol/store layer above, rather than
misrepresented as fabricated human conversation turns.

Root independently replayed all ten successful recorded evaluations through
the CLI: [replay report](evidence/closure-20261011/replay.json). Reproduce with:

```sh
python scripts/check_workflow_receipts.py --db work/adviser.sqlite
```

Equality means decoded JSON value equality across the entire evaluator `data`:
identities, provenance, facts, assumptions, timing, damage, stopping fields,
verdict and limitations. Object-key order and integral-float formatting are not
semantic differences; raw text-payload comparisons are additionally retained
where the transport normalized integral floats. No tolerance or numeric field
exclusion masks discrepancies.

For #4, reuse exact prompts/arguments and source/model pins. Narrative wording
and rounding may vary; identities, numeric/evidence fields, unresolved inputs,
conditionality and stopping semantics may not. The same skill is canonical for
adaptation; no Claude-specific backend or equations are required.

## Remaining battle validation (#5)

For Reiksguard/Doom Diver, Sea Guard/Blue Horrors and Bloodletters/Kroxigor:
record predictions before play at the intended build/scale/rank and exact
scenario. Record actual contact/shot timing, damage, casualties, component
losses and morale; compare observed minus predicted, repeat a controlled
variation, and document model error. The acceptance projections above can be
inputs only if the played scenarios actually match. Do not relabel them as
observed battles. Empirical calibration remains null.
