---
name: ctw-matchup
description: Compare Total War Warhammer III units and answer tactical matchup and roster questions using the connected CTW Advisor tools. Use for listing rosters, lords and heroes, filtering units by stats, unit-versus-unit advice, approach under fire, ranged exchanges, melee contacts, scenario changes, and interpreting conditional combat calculations. Resolve identities and use the shared evaluator; never invent combat numbers.
---

# CTW matchup

Workflow version 1.1.0. Use the installed CTW Advisor connector. Discover its actual callable schemas; tool-name prefixes may vary. If tools are unavailable, report the missing connector and stop numerical advice. Do not substitute remembered unit stats or build another backend.

## Find units without guessing names

For roster, list or stat-threshold questions ("all High Elf heroes", "infantry with armour below 40"), or when the user has not named exact units, call `discover_unit_fields` first. Use its field ids, units and category values (subculture keys are labeled with faction names); never guess fields, categories or names, and never consult external roster lists. Then call `search_units` with explicit `all`/`any` groups. Choose one field when a term is ambiguous (cost, AP damage) and say which one you used. Page with `next_cursor` until `complete` is true before calling a list exhaustive. Report `total` with its `count_unit`, and the coverage boundary: complete within the imported snapshot, not proof of full game coverage. Use `group_by: mount_family` to present characters with their mounts; each variant keeps its own values. Search values are unmodified base stats, and null is not zero. Unsupported classifications, such as legendary versus generic lords, are reported as unsupported, not inferred from names. Follow a result into evidence or evaluation with its `unit_key` and `subculture`.

## Resolve the question

1. Identify both intended units and the tactical decision. Call `resolve_unit` for each name or key. Display qualified names/variants. If ambiguous, present candidates and obtain selection before evaluation. If a colloquial family name could mean shielded/unshielded, mounted/unmounted, or elite variants, clarify that choice even if the plain label resolves. Never silently choose a candidate. Not-found is not proof the unit is absent: request an exact name/key or retrieve a source-backed candidate.
2. Clarify only material scenario choices. For a baseline, state assumptions and proceed: unmodified custom battle, ultra, rank 0; flat unobstructed ground, front facing, separation 200 m, horizon 120 s, both approach, fire/fight enabled. These are illustrative settings, not observations. Respect supplied orders, distance, contact assumptions and duration. Hosted duration is at most 300 s.
3. Call `get_matchup_evidence` with resolved identities. Inspect components, weapon/projectile/explosion relationships, attributes, relevant abilities and coverage. Use section pagination, `get_detail`, and `get_provenance` for consequential omitted evidence. A truncated or unrequested section is not absent mechanics. Keep artillery crew and engine separate. Do not apply listed passives/activated abilities to base stats yourself.

## Calculate and test the decision

4. Call `evaluate_single_unit_matchup` with the same identities and explicit scenario. The shared calculator owns numeric combat predictions. Read snapshot, model version, source facts, assumptions, empirical calibration, timing, both ledgers, verdict, sensitivity, unresolved inputs and limitations. Preserve nulls and scoped patch differences. On incompatible/unavailable data, give the exact diagnostic and what must be restored; never mix snapshots or fill gaps with memory.
5. Read [calculation interpretation](references/calculation.md) for defaults, ranged scheduling, projectile-count ambiguity and stopping semantics. Disclose consequential uncalibrated assumptions. Do not ask the user for technical source fields obtainable from tools.
6. Run a decision-relevant controlled variation, keeping other inputs fixed: separation/orders for approach, facing for shields, contacts for melee, or a defensible uncertain firing input. Report actual changed results. For material immediate-arrival ranged damage, rerun with the shooter's returned cycle as an illustrative flight delay. For unresolved projectile counts, inspect factors and compare explicit interpretations per the reference. Never select an interpretation merely because it produces a preferred outcome.

## Give tactical advice

Lead with the action the evidence supports and its conditions. Explain relevant identity and source/model version; baseline assumptions; time to range/contact; both sides' modeled damage (direct, explosion, melee and barrier absorption where relevant); distinct stopping criteria; conditional verdict and decisive sensitivity. Round prose numbers sensibly, retaining raw outputs for audits. Report an indeterminate verdict as indeterminate, even if its fallback point ordering names a side. Sensitivity corners are not confidence intervals.

Separate calculated changes from qualitative advice about obstruction, flanking, support, fatigue, abilities or terrain physics the model does not simulate. Never turn health depletion into routing, crew loss into established engine disablement, or projected health advantage into a guaranteed battle winner. Explain consequential gaps without burying useful results in every possible caveat.

For battle tests, save exact scenario and prediction before play, then compare measured outcomes separately. Connector/CLI agreement establishes reproducibility, not game accuracy. Calibration stays distinct from source facts.

## Access and versions

Public read-only endpoint: `https://ctw-adviser-mcp-production.up.railway.app/mcp`; authentication None. Prefer the installed CTW Advisor plugin. Datasette is not the MCP endpoint. Refresh connector metadata after deployed tool changes. On HTTP 429, honor the returned retry delay and pace calls; the request budget is shared across clients. Tool responses determine current versions. Verified 2026-10-11: source `595e22764b22e748afdbafafcb0a6258973e2451`, base patch 9.0/build 25507028, scoped supplemental 9.0.1/build 25546563, store 4, packet 1.20.0, model combat-0.1.4. Report changed versions and check compatibility rather than assuming these persist.

Canonical source: `OwenTanzer/CTW-adviser`, `skills/ctw-matchup/`. Keep installed instructions synchronized; Claude adaptation consumes this same workflow and shared server.
