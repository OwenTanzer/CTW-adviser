# CTW-adviser

General single-unit matchup adviser. CTW-data owns game facts; this repository
owns rebuildable serving artifacts and, in later increments, matchup calculations.

Current implementation: issue #2, Lock and validate — pinned source verification,
import contract, versioned packet schema and source-backed/synthetic fixtures.
No serving database, importer or combat evaluator exists yet.

With Python 3.11+ and SQLite 3.37+:

```sh
python scripts/verify_sources.py --ctw-root ../CTW-data
python scripts/validate_packets.py --ctw-root ../CTW-data
python -m unittest discover -s tests -v
```

The first command accepts a checkout or exported directory containing the locked
files. It works offline, validates file fingerprints and selected structures,
and writes JSON to standard output. Exit status is nonzero on failure. It never
changes CTW-data or an existing serving database.

See [source contract](docs/source-contract.md) and
[verification evidence](docs/step-1-verification.json), then the
[lookup contract](docs/lookup-contract.md) for packet semantics and fixture rebuilds.
