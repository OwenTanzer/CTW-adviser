# Stage-5 release-verifier repair for draft PR #12

Brian's independent acceptance report found that the first release verifier
accepted a rehashed SQLite copy with unsupported snapshot schema or import
contract, and accepted several false manifest identities. A JSON list produced
an uncaught traceback. The report also identified two Windows test-connection
cleanup errors. This local follow-up keeps CTW-data and the source lock pinned
at `595e22764b22e748afdbafafcb0a6258973e2451`.

The Windows test cleanup is integrated as a separate commit carrying Brian's
authorship and the exact two-file patch from local commit
`b9af0bd620a09b33dfbd06cca5d21f8e03ec2989`; it does not change production
query code. The release-verifier changes are separate for independent review.

`verify_release.py` now checks the version-1 manifest's required fields and
types, clean-build declaration, supported Python/SQLite build versions, source
repository/tree/commit and import-contract fingerprint against this checkout's
locked contract, and adviser commit against this checkout's HEAD by default.
`--expected-adviser-commit` permits a separately known revision. It opens the
database through the ordinary reader's store-schema/import-contract gate,
requires one snapshot identity, checks SQLite integrity and foreign keys, then
compares actual snapshot metadata and aggregate counts with the manifest. The
database size and SHA-256 are checked before and after inspection to detect a
change during verification. Invalid JSON objects and malformed metadata return
a structured JSON error and nonzero exit.

The new regression cases use a small synthetic SQLite store with real store
schema and pinned identity metadata. They create disposable copies with
recomputed hashes and invalid schema, contract, foreign key, duplicate
snapshot, metadata and count states. A separately rebuilt real pinned artifact
is checked with its known adviser commit. The synthetic fixture tests the
verifier's contract; it is not evidence that an empty store is a useful game
database.

The manifest is still **not a signature**. Its adviser revision can be compared
with an independently known SHA, but the verifier cannot establish who built
the file or whether a malicious actor replaced both database and manifest.
Build duration, machine description and historical query-plan text are checked
for shape and plausible types, not independently reconstructed. Game-engine
semantics and live inspection-site parity remain separate acceptance questions.

## Local checks

With `CTW_DATA_ROOT` set to the pinned sibling source and TEMP pointed within
this workspace, ordinary `python -m unittest discover -s tests -v` passed
**138 tests in 178.723 seconds**, zero failures, errors or skips, with no
test monkeypatch. The eighth verifier regression added during that run was
then included in a separate focused `python -m unittest discover -s tests -p
test_release.py -v` run: **8 passed in 2.331 seconds**. The full suite should
be rerun on the final committed tree as a review gate. The earlier real Windows
artifact at adviser commit `fc317a7394b527a3d38fba09ce6d8470aae17fa5`
passed `verify_release.py --expected-adviser-commit fc317a7...`; its rehashed
schema-999 disposable copy failed with “unsupported snapshot schema or import
contract.” The new focused tests cover the corresponding contract and foreign-key
mutations. `python scripts/verify_sources.py --ctw-root ..\CTW-data-gamma`
passed 144 files, 76 datasets and 2,409 distinct unit keys;
`python scripts/validate_packets.py --ctw-root ..\CTW-data-gamma` passed
10 committed fixtures, five source-backed. `python scripts/audit_queries.py
--db work\adviser.sqlite --ctw-root ..\CTW-data-gamma --output
work\d1-query-audit.json` passed all 2,409 keys and 36,678 source locators,
with zero errors and packet 1.19.0. The real SQLite snapshot inspection and
Sea Guard CLI query also succeeded. These are source and structural checks,
not proof of game-engine runtime truth.
