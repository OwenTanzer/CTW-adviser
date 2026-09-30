# CTW-adviser

General single-unit matchup adviser. CTW-data owns game facts; this repository
owns rebuildable serving artifacts and, in later increments, matchup calculations.

Current implementation: issue #2, phases 1–2 — pinned contracts and fixtures,
plus an offline STRICT SQLite snapshot builder with indexed relations and
provenance. The query/packet interface and combat evaluator are later work.
Each base unit appears once, with list-valued faction names and linked,
source-qualified availability records.

With Python 3.11+ and SQLite 3.37+:

```sh
python scripts/verify_sources.py --ctw-root ../CTW-data
python scripts/validate_packets.py --ctw-root ../CTW-data
python scripts/build_snapshot.py build --ctw-root ../CTW-data --output work/units.sqlite
python scripts/build_snapshot.py inspect work/units.sqlite
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
