# Issue #2 stage-5 local acceptance record

This review starts from adviser main `1c37f902eedc68eed4cfe863a7bb8429b8f4e0db`
(PR #11 merge; tested tree `0c272ccf8589cf5508fa2728ce41b4ab04e47cec`)
and locked CTW-data `595e22764b22e748afdbafafcb0a6258973e2451`.
The source pin, import contract, store, packet assembler and production data are
unchanged by this package increment. Only the local rebuild scripts and
documentation are added. The generated database and reports are ignored under
`work/`, never added to Git.

## Checklist disposition

| Issue #2 acceptance line | Evidence and disposition |
| --- | --- |
| 773: source lock, architecture/import/output contracts and working commands | Existing `source_lock.json`, `schema/import_contract.json`, `schema/evidence_packet.schema.json`, `docs/source-contract.md`, `docs/store-contract.md`, and `docs/lookup-contract.md` remain. `docs/local-rebuild.md` adds Windows/Linux/macOS rebuild, verification and query commands. Windows commands were executed; Linux/macOS are specified but not executed here. In-repo portion is ready for review. |
| 781: attributed enriched explanations, version/evidence qualifications, compact references, optional full documentation and collapsed inspection view | Packet 1.19.0 and `get_passive_detail(..., include_documentation=True)` are present; default packets retain inline refs and defer expanded provenance. The separate `inspection/datasette` branch at `9eee92f2f89f34da9397e4132f6286541bb3616f` contains a collapsed “Supporting source documentation” panel, but its hard-coded banner still says PR #11 is unmerged. The live `/inspect` endpoint was unreachable from this host. Keep live-site parity open until a read-only version/artifact check; do not infer it from code alone. |
| 788: performance and packet-size evidence | Local build/manifest, full query audit, fixed-case packet benchmark, access plans and qualified memory measurement are reproducible below. The accepted Daemon Prince timing exception remains explicit. In-repo measurement evidence is ready for review. |
| 789: issues #3/#5 consume the interface without presenting derived outcomes as imported facts | Downstream consumer integration has not been implemented or proven by stage 5. Keep open for those issues; no combat damage, winner, rout-time or campaign availability calculation is claimed here. |

The checked “Datasette presents each unit once” acceptance line has two parts:
the SQLite profile/alias/availability model is verified locally; the deployed
Datasette view and artifact version were not reachable. Treat that deployed half
as needing revalidation rather than closing it from database tests.

## Reproducible commands and results

Run from this branch root with the pinned sibling source checkout:

```text
python scripts/rebuild_release.py --ctw-root ..\CTW-data-gamma --output work\adviser.sqlite --manifest work\adviser.manifest.json
python scripts/verify_release.py --db work\adviser.sqlite --manifest work\adviser.manifest.json
python scripts/audit_queries.py --db work\adviser.sqlite --ctw-root ..\CTW-data-gamma --output work\stage5-query-audit.json
python scripts/benchmark_packets.py --db work\adviser.sqlite --output work\stage5-packets-idle.json
python work\run_suite_review.py
```

The test runner is an ignored local harness that supplies precreated workspace
temporary directories around a Windows sandbox ACL restriction. A direct
`python -m unittest discover -s tests -v` attempt failed on inaccessible Python
temporary directories; it was not a code assertion failure. The workaround
ran **131 tests, zero failures, zero errors, zero skips**. Source verification
occurs three times in the atomic builder. The exhaustive query audit passed
**2,409 unit keys, 36,678 source locators, zero errors, packet 1.19.0**.

The first rebuild on Windows 11 ARM64 / Python 3.12.10 / SQLite 3.49.1 took
**14.58 s** and produced **67,284,992 bytes** with SHA-256
`ed70b48dddc5a2e550a5e9a28b47e9c639d9007f03dac827d20dd88f346790cc`.
The verifier accepted the matching manifest and rejected a manifest whose SHA
was replaced with zeros. `git` and the ignored manifest record the exact adviser
commit and whether the worktree was dirty. A post-commit rebuild supplies the
distribution identity; its current manifest must accompany the database.

The full audit's measured connection startup was **13.25 ms**; expanded packet
unit median/p95 **21.88/58.02 ms**, repeat Sea Guard/Blue Horrors pair median
**35.16 ms**, expanded packet median **30,800 bytes**, and largest expanded
packet **223,372 bytes** (Daemon Prince). These audit timings were taken while
other checks ran and are not an idle latency acceptance result. Its four
representative query plans and the builder's six access plans all used indexed
`SEARCH` operations. The full JSON reports under `work/` include the plans.

The **idle fixed-case** run used 12 single units and three pairs with 25 warm
query-plus-compact-serialization repetitions per case. Single packet median/max
were **19,113.5/107,637 bytes**; pair median/max were **28,327/31,922 bytes**.
The maximum per-case warm median/p95 were **152.46/159.08 ms**, both for Daemon
Prince; its fresh-connection call took **162.13 ms**. The next-highest warm
median was **42.22 ms**. Daemon Prince still exceeds the provisional 100 ms
warm-median target and remains the explicitly accepted exception, not a pass.
The representative `tracemalloc` Python heap peak for one fresh-connection
Daemon Prince query plus serialization was **3,173,009 bytes**; SQLite native
memory and process RSS were not captured. A previous benchmark that overlapped
the full audit is excluded from latency conclusions. These tests do not prove
that imported game facts or unknown engine scheduling are correct.
