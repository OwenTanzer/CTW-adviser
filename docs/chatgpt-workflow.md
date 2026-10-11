# ChatGPT matchup workflow 1.0.0

## Install and invoke

The canonical instructions are [skills/ctw-matchup/SKILL.md](../skills/ctw-matchup/SKILL.md)
and its linked calculation reference. They contain no second database or combat
formulas. The installed personal skill is named `ctw-matchup` / **CTW Matchup**.
In ChatGPT Work, invoke `$ctw-matchup` with CTW Advisor connected, for example:

> Use $ctw-matchup to compare shielded Lothern Sea Guard holding at 100 m against approaching Blue Horrors for 120 seconds, then compare rear facing.

The personal Work skill is saved through the user's Skills workspace (commit `01618e6`, verified push). A local
Codex installation can copy the complete `skills/ctw-matchup` directory into
`$CODEX_HOME/skills` (or `~/.codex/skills`) and start a new session. Merely placing
an AGENTS.md in the adviser checkout does not connect ChatGPT to the database.

For a missing connector: Plugins → + → Add custom MCP server; name it CTW
Advisor, enter `https://ctw-adviser-mcp-production.up.railway.app/mcp`, choose
No authentication, review the connection notice, create and install the plugin.
Start a new Work chat and select `@CTW Advisor`. Workspace restrictions apply.
These steps follow [OpenAI's connection guide](https://developers.openai.com/plugins/deploy/connect-chatgpt)
(checked 2026-10-11). Refresh connection metadata and start a new conversation
when deployed tool descriptions/schemas change. The endpoint is public and
read-only; no shared secret is distributed.

## Reproduce and compare

Build the pinned artifact per [hosted MCP](hosted-mcp.md). For each saved
`evaluate_single_unit_matchup` call, run:

```sh
PYTHONPATH=src python -m ctw_adviser.cli evaluate --db work/adviser.sqlite \
  '<unit_a>' '<unit_b>' --scenario '<identical scenario JSON>'
```

Pass matching `--subculture-a` / `--subculture-b` when the connector call uses
them. Compare decoded JSON to the connector envelope's `data`, not to the whole
adapter envelope. Snapshot/model/identity, source evidence, assumptions, phase
timing, ledgers, stopping fields, verdict, unresolved inputs and sensitivity
must agree exactly. JSON whitespace and object-key order may differ. Never
normalize away nulls, version differences or substantive numeric differences.

## Conversation evidence and Claude handoff

[Closure evidence](closure-3-6.md) indexes four separate Work agent conversations:
identity and evidence retrieval, evaluation, controlled variations and readable
advice. These are actual connected tool runs, not invented tool transcripts;
the task prompts are acceptance prompts, not transcripts of Owen playing battles.
The prompts, raw results, comparison records and advice are preserved under
`docs/evidence/closure-20261011/` for issue #4.

Claude should use the same canonical workflow and exact scenarios. Permissible
prose differences include ordering, wording and sensible rounding. Numerical
fields, identities, model/source versions, unresolved flags and outcome
conditions are invariants. Indeterminate cannot become a winner; casualty
estimates cannot become measured kills; artillery crew loss cannot silently
establish engine disablement; qualitative tactics cannot be presented as
calculated modifiers. No additional backend or client-specific equations.

The skill's ambiguity boundary requires candidate selection before evaluation.
Plain Sea Guard naming also requires the intended shield variant; exact variant
names in these four prompts are already explicit. Missing/ambiguous/stale-source
protocol checks are separately recorded, not claimed as four user selections.
Actual Claude account setup, tester onboarding and real Claude conversations
remain issue #4. Predictions-versus-battles validation remains issue #5.
