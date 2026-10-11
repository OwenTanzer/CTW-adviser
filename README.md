# CTW-adviser

General single-unit matchup adviser. CTW-data owns game facts; this repository
owns rebuildable serving artifacts and, in later increments, matchup calculations.

Current implementation: issue #2, phases 1-3 and local phase-5 packaging - pinned contracts and fixtures,
an offline STRICT SQLite snapshot builder, and indexed JSON evidence retrieval
with unit resolution, inline passive explanations, projections and continuation.
The combat evaluator is later work.
The first downstream consumers are a local read-only MCP stdio query adapter and
an explicitly illustrative movement-phase timing command. See
[consumer increment](docs/consumer-increment.md) for commands and limits. The full
matchup evaluator remains issue #5. A deployable Streamable HTTP transport
candidate for issue #3 is described in [hosted MCP](docs/hosted-mcp.md).
Each base unit appears once, with list-valued faction names and linked,
source-qualified availability records.

With Python 3.11+ and SQLite 3.37+:

```sh
python scripts/verify_sources.py --ctw-root ../CTW-data
python scripts/validate_packets.py --ctw-root ../CTW-data
python scripts/build_snapshot.py build --ctw-root ../CTW-data --output work/units.sqlite
python scripts/build_snapshot.py inspect work/units.sqlite
python scripts/query_snapshot.py resolve --db work/units.sqlite Teclis
python scripts/query_snapshot.py unit --db work/units.sqlite "Lothern Sea Guard"
python scripts/query_snapshot.py matchup --db work/units.sqlite "Lothern Sea Guard" "Blue Horrors of Tzeentch"
python scripts/audit_queries.py --db work/units.sqlite --ctw-root ../CTW-data
python scripts/audit_chej_findings.py --db work/units.sqlite --output work/chej-findings-audit.json
python scripts/audit_alpha4_recovery.py --db work/units.sqlite
python -m unittest discover -s tests -v
```

The first command accepts a checkout or exported directory containing the locked
files. It works offline, validates file fingerprints and selected structures,
and writes JSON to standard output. Exit status is nonzero on failure. It never
changes CTW-data or an existing serving database.

See [source contract](docs/source-contract.md) and
[verification evidence](docs/step-1-verification.json), then the
[lookup contract](docs/lookup-contract.md) for packet semantics and fixture rebuilds.
See the [store contract](docs/store-contract.md) for build boundaries, source
accounting, dependency selection and atomic installation.
See [local rebuild and measurements](docs/local-rebuild.md) for the reproducible
SQLite artifact, SHA-256 manifest, verification and packet benchmark.

Query commands require only the built SQLite file. Ambiguous names return
candidates; source aliases and availability remain distinct. Python callers use
`Queries` from `ctw_adviser.queries` as a context manager. See the lookup contract
for sections, modes, continuation, detail/provenance commands and interpretation
boundaries. The existing public Datasette service uses this repository's
[`inspection_plugins` and Docker build](docs/inspection-deployment.md) for
read-only human inspection. Its live source and packet version must be checked
against a reviewed merge before claiming parity.

Packet 1.19.0 includes the Alpha 4 repairs first released in 1.15.0 and the
Chej unit supplements. Default packets keep
inline evidence IDs and defer source/provenance dictionaries; use
`--include-provenance` to expand them or the `provenance` command to resolve IDs.
The recovery audit checks both views across all roster contexts against the
published pre-repair baseline; its review-key inventory is checked in.
