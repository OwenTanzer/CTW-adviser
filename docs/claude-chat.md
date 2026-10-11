# CTW Advisor in Claude chat

This is the issue #4 handoff derived from the closed issue #6 workflow. It uses the
existing public, read-only MCP endpoint and the same calculator; it adds no account
access, data source, equation, or server. The canonical workflow is
[`skills/ctw-matchup/SKILL.md`](../skills/ctw-matchup/SKILL.md), version 1.0.0.
The Claude ZIP is built from that file and its calculation reference with
`python scripts/build_claude_skill.py`. Download the versioned
[`ctw-matchup-claude-1.0.0.zip`](../dist/ctw-matchup-claude-1.0.0.zip) and verify
its [SHA-256 checksum](../dist/ctw-matchup-claude-1.0.0.sha256) before upload:
`fb6f44a159e1a3a296386fe083a3ffaf405803de7a1a0ac5479af0e6462fdfd6`.

## Connect a Claude **chat** account

1. On Claude Team or Enterprise, an organization owner adds a custom **Web**
   connector in **Organization settings → Connectors → Add custom connector**.
   Name it **CTW Advisor**, set the URL to
   `https://ctw-adviser-mcp-production.up.railway.app/mcp`, and choose
   **No sign in**. Each tester then opens **Customize → Connectors** and connects
   to it. For an individual Pro or Max account, use **Customize → Connectors →
   Add custom connector** with the same URL and no sign-in. Enable the connector
   for each chat from the chat's **+ → Connectors** menu. Ask the account owner
   to verify any organization policy before inviting testers; do not share a
   credential because this endpoint does not require one.
2. An owner permits custom skills and code execution under the organization's
   Claude policy. Each tester downloads the versioned ZIP linked above and uploads it from
   **Customize → Skills → Create skill → Upload a skill**, then enables it.
   A personal upload does not automatically provision coworkers; share the ZIP
   only with consenting testers or provision it by organization policy.
3. Start a fresh Claude chat with both the connector and skill enabled. Ask:
   “Using the CTW matchup skill, call `resolve_unit` for Reiksguard and report
   the resolved key and source snapshot. Do not infer combat numbers yet.”
   Confirm the response is tool-derived and the source commit is
   `595e22764b22e748afdbafafcb0a6258973e2451`. If tool discovery,
   permissions, or snapshot differs, stop fixture testing and record the exact
   response. Do not paste source data as a substitute for a connection.

Claude's [custom connector instructions](https://support.claude.com/en/articles/11175166-get-started-with-custom-connectors-using-remote-mcp),
[skill creation instructions](https://support.claude.com/en/articles/12512198-how-to-create-custom-skills),
and [skill usage instructions](https://support.claude.com/en/articles/12512180-use-skills-in-claude)
describe these account controls. The shared endpoint's request budget is
60/minute across clients; honor HTTP 429 `Retry-After` and space out trials.

## Fixed chat trials

Use a fresh chat per family, with the first prompt followed by its controlled
changes. For Reiksguard, compare case 3 with 4 for distance, case 3 with 5
for flight delay at 200 m, and case 4 with 6 for flight delay at 100 m. Cases 5
and 6 explicitly return to their respective earlier baselines. The exact keys,
calculator arguments, saved JSON result paths,
and source/model pins are in [`claude-fixtures.json`](claude-fixtures.json).
Give Claude the prompt text there verbatim. A family requires two
`resolve_unit` calls, `get_matchup_evidence`, then one
`evaluate_single_unit_matchup` per scenario; follow the skill's evidence
pagination when needed. The ten recorded issue #6 evaluations are the baseline.

| Family | Controlled trial | Expected evaluation count |
| --- | --- | ---: |
| Reiksguard / Doom Diver | 200 m, 100 m, then each with illustrative 22.5 s Doom Diver flight delay | 4 |
| Shielded Lothern Sea Guard / Blue Horrors | front, then rear facing at 100 m | 2 |
| Bloodletters / Kroxigor | eight contacts per side, then four Kroxigor contacts at 20 m | 2 |
| Queen Bess / Reiksguard | 200 m, then 300 m | 2 |

For each response, compare the tool arguments with the manifest and the tool's
structured `data` with the saved JSON. Identity keys, source commit, packet and
model versions, scenario assumptions, timings, both damage ledgers, barrier
absorption where present, verdict, limitations, and explicit nulls are invariant.
Changing one listed scenario field should leave every other supplied field
fixed. Prose wording and sensible rounding may vary. Advice must retain the
conditional verdict and distinguish source facts, calculation, assumptions,
and unmodeled tactics. An indeterminate verdict stays indeterminate. Do not
present projected health advantage as guaranteed routing or battle victory.
The flight delay is illustrative, not an observed projectile time.

The CLI check is `python scripts/check_claude_fixtures.py --db PATH_TO_PINNED_DB`.
The read-only endpoint check is `node scripts/check_claude_mcp.mjs` after
installing `@modelcontextprotocol/sdk@1.32.1` under `work/mcp-client` (or
setting `CTW_MCP_SDK_ROOT` to its `dist/esm` directory). These checks establish
calculator and protocol reproducibility; they do **not** establish Claude's
chat behavior or battle accuracy. The largest recorded result is about 139,000
characters, so record any chat output truncation and consult the tool result
directly. Real Claude chat and Jacob/Jayden's consent-based acceptance remain
unverified until their own trials are recorded.

## Tester feedback, with consent

Ask a willing tester to share only the following, with any personal chat text
removed. Do not collect account tokens, credentials, or unrelated conversations.

```text
Tester (optional label):
Claude plan and date:
Skill ZIP SHA-256 / connector name:
Fixture family and case ID:
Tool names and exact argument JSON (or consented export):
Source commit, packet version, model version:
Did the advice preserve the verdict and caveats? What was useful or confusing?
Discrepancies between the tool result, the saved fixture, and Claude's answer:
Missing source data, model outputs, or explanation that affected the decision:
Suggested next controlled test or battle observation:
Any tool error, 429 delay, missing output, or truncation?
May this anonymized feedback be used in issue #4? yes/no
```
