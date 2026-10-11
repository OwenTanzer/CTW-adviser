# Independent requirements review — CTW-adviser PR #31

Review target: issue #28, fetched from GitHub during this review on 2026-10-11.
Remote PR head confirmed: `443e67440b18c09b9274fb2066aa095e8a705951`.
Tree verified from its local Git object: `152ee2b32303d1741e27b6b764e01576be88b803`.
The isolated review worktree `/tmp/ctw-review31` uses local commit `33d5c18ca04555c6ca66748a359f47f0c4fff9b8`, whose tree is identical. No drift found.
Read AGENTS.md, source_lock.json, schema/import_contract.json and docs/source-contract.md. Reviewed the code and current issue requirements independently of the implementation narrative.

## Verdict

No blocking correctness or security finding identified within this bounded review. Implementation meets the locally testable unit-search requirements. This is **not** issue closure, deployment approval or merge approval. Real connector discovery/search/conversation and installed skill synchronization remain outstanding release acceptance.

PR preserves main's #29 revert: store 3 / contract 2, unchanged CTW-data pin `595e22764b22e748afdbafafcb0a6258973e2451`; no source/import/calculation changes in the diff against main. It does not restore #21 effects. Source limitations and unsupported legendary/special classification are explicitly disclosed.

## Severity-ranked observations

No P0/P1/P2 findings.

1. **P3, documentation consistency:** `docs/hosted-mcp.md:3` still says this checkout exposes six read-only tools, whereas `src/ctw_adviser/mcp.py` exposes eight (six existing plus discover/search). This is inherited main documentation now made stale by the new tools. Update the checkout count while keeping the distinct production-tool inventory explicit. Reproduction: inspect `len(TOOLS)` and compare that opening paragraph. Does not affect query behavior.
2. **P3, source label limitation:** discovery describes `source_unit_name` as an original localized label (`src/ctw_adviser/unit_search.py:35`), but 104 of the 2,379 pinned profiles contain untranslated `{{tr:...}}` tokens in unit_name, including Caradryan/Mist Mage examples observed by the parent. These are inherited source values, not invented or lost by search. Consider explicitly mentioning missing localization in limitations/documentation; do not guess replacement labels or change the source pin in this PR. Reproduction SQL: `SELECT count(*) FROM unit_profiles WHERE unit_name LIKE '%{{tr:%'` => 104. This does not invalidate identity completeness or numeric results.

## Acceptance matrix

| Issue requirement | Implementation / local evidence | Actual connector status |
|---|---|---|
| Field meanings, types, units, operators, capabilities, category discovery | Implemented. Reviewed explicit allowlist; independently paginated all categorical fields with limit 3 and compared raw distinct source values (computed is_mounted reviewed separately). | Pending deployment/metadata refresh. |
| Complete High Elf lords/heroes with mount grouping and supported special classifications | Local focused tests pass exact SQL sets and independent mount traversal: 126 profiles / 35 families. Unsupported legendary/special designation disclosed; native hero/lord classifications retained. | Pending new search tools. |
| Hero attack >, >=, <, <= 60 plus real boundary checks | Local focused tests compare SQL sets at 60 and nonempty threshold 40; all pass. | Parent separately checked existing live profile facts, not live search. |
| Infantry armour/speed AND and OR | Focused exact-set SQL checks pass; native run_speed units explicit; nonempty 3.5 boundary supplements requested 35 example. | Pending new search tools. |
| Cost <= 1000 sorted by AP damage | Focused exact ordered identity checks pass; cost and primary melee weapon scopes explicit. | Pending new search tools. |
| Mounted lords, defence > attack | Field comparison implemented; focused independent SQL passes. | Pending new search tools. |
| Independent identities and values | New reviewer script verifies all 2,379 profiles and every exposed numeric field against direct SQL, including two-field sort and identity tie-break. Every returned key resolves. All aliases and subculture arrays verified directly. | Existing-profile spot checks are useful but cannot establish snapshot parity. |
| Pagination/grouped counts, no duplicate or omitted identities | Reviewer full-roster numeric scans: 24 pages each. Maximum-column family scan: 26 pages, 1,658 families / 2,379 unique variants, exact complete identity set. Byte-driven continuation exercised. | Pending new search tools. |
| Null/zero, precedence, incompatibility, multivalue and bounds | 11 focused tests pass; reviewed SQL three-valued semantics, existential relation negatives, source weapon scopes. Additional malformed-type/grammar dispatch probes return controlled diagnostics without uncaught exceptions. Existing focused tests cover stale cursor binding and execution-budget cleanup. | Pending new search tools. |
| Connected discover → search → combat-profile conversation | Local adapter covered by focused tests and prior SDK receipt; reviewer independently resolves every search key. | NOT complete. Production currently lacks new tools (parent observation). |
| Examples, coverage, baseline and measured size/latency | Implemented in docs/unit-search.md and measurement JSON, with two nonblocking documentation observations above. | Hosted latency/new-tool response size pending. |
| Existing tool compatibility / workflow | Shared Queries path and additive adapter reviewed; no source/schema/combat modifications. Canonical ChatGPT workflow updated. | Installed skill synchronization pending; production currently differs in store version. |

## Verification performed

- `CTW_TEST_DB=/workspace/scratch/df71833d6698/CTW-adviser/work/adviser.sqlite python -m unittest discover -s tests -p test_unit_search.py -v`: **11 passed**, no skips/errors.
- Independent reviewer script `/tmp/ctw-review31-independent.py`: **passed** all 2,379 identities, every exposed numeric output field, full scalar-sort order, aliases, roster arrays, categorical pages, and full family pagination with 16 requested columns.
- Numeric scans: 24 pages each; largest entire data response 62,094 bytes for first 16 numeric fields, 33,936 for remaining fields.
- Family scan: 26 pages; largest entire data response 62,980 bytes. The documented 60,000-byte cap applies to result items, not response metadata; observed envelope sizes are consistent with that distinction and well within existing HTTP response limit.
- Additional `/tmp/ctw-review31-probe.py` dispatch probes covered null/boolean/numeric/string/list/object forms for every top-level new-tool argument, malformed leaf members and invalid Unicode string literals; no uncaught exception.
- Reviewed allowlisted SQL expressions, bound parameters, filter-node/depth/value caps, cursor binding, 10,000-result ceiling, SQLite instruction budget and cleanup, pre-group filtering and connected-mount grouping.

Existing 198-test and SDK receipts are previous implementation evidence; this reviewer did not rerun the full suite or claim those executions as independent new runs. No code changes, publication, deployment or merge performed.

## Live evidence boundary supplied by parent

Parent observed production tools/list still lacks discover_unit_fields/search_units and exposes the earlier effects tools. Production is store 4 while reviewed candidate follows current main at store 3. Same pinned CTW-data commit is not full serving-contract parity. Parent's existing live combat-profile checks for Loremaster (attack 55 / defence 45 / cost 750) and Fire Mage Sun Dragon (50 / 44 / 1750) agree with candidate base facts. These are explicitly supporting profile spot checks, not fulfillment of actual-connector search acceptance.

## Narrow follow-up review — both P3 observations resolved locally

Read back the parent's uncommitted diff after the review. `docs/hosted-mcp.md` now correctly says eight checkout tools and distinguishes those capabilities from the different eight-tool production inventory. `docs/unit-search.md` explicitly records the 104 source-label placeholders. `src/ctw_adviser/unit_search.py` adds an exposed localization limitation and corrects the source_unit_name field description. Both observations are resolved by these edits.

The source-code diff changes only descriptive strings: no SQL, predicates, sorting, grouping, pagination, validation, source scope, types or numeric outputs change. The original independent behavioral review remains applicable. Parent reports the 11 focused tests passed again; this follow-up did not rerun them. This follow-up covers the inspected local diff, not a claim that the amended files have already been published. Live release gates remain pending.
