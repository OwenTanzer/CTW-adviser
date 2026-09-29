# CTW-adviser

General single-unit matchup adviser. CTW-data owns game facts; this repository
owns rebuildable serving artifacts and, in later increments, matchup calculations.

Current implementation: issue #2, step 1 — pinned source verification and import
contract. No serving database, importer or combat evaluator exists yet.

With Python 3.11+ and SQLite 3.37+:

```sh
python scripts/verify_sources.py --ctw-root ../CTW-data
python -m unittest discover -s tests -v
```

The first command accepts a checkout or exported directory containing the locked
files. It works offline, validates file fingerprints and selected structures,
and writes JSON to standard output. Exit status is nonzero on failure. It never
changes CTW-data or an existing serving database.

See [source contract](docs/source-contract.md) and
[verification evidence](docs/step-1-verification.json).
