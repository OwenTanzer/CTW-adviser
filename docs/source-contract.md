# Pinned source contract — issue #2, step 1

The source is CTW-data commit `3b5d13d94c5ed3eb4b9c6ce61cc75854b4426196`.
`source_lock.json` pins every selected input by SHA-256 and byte count, also
recording its Git blob identity. `schema/import_contract.json` supplies explicit
headers, types, keys, expected counts, field mappings, owner gates and joins.
The lock also fingerprints the contract so mapping edits require an explicit
lock update. The verifier performs no extraction, network request or database write.

## Scope and authority

The inputs cover all 25 normalized rosters, all ten unit lookup tables, selected
shared definition tables and their canonical raw sources, melee/missile weapon
supplements, five localization files, native stat definitions and audit metadata.
Shared tables are a bounded input inventory: the future importer must select
classification metadata and dependencies reachable from passive or weapon roots.
This does not authorize expansion from activated-ability roots or wholesale import
of campaign, skill, magic-access or presentation data.

The base owner is patch 9.0/build 25507028, ultra, rank zero, unmodified custom
battle. Shared abilities, stat definitions and additive payload evidence retain
the scoped 9.0.1/build 25546563 owner. The source registry, extraction manifest,
input lock and published payload validation provide compatibility evidence;
the whole store must not be relabeled 9.0.1.

Published unit and shared-owner structural audits pass. Shared semantic/runtime
coverage remains partial. This step verifies pinned bytes, headers, types, keys,
counts and selected joins; it does not rerun the complete upstream extraction
validators, certify runtime mechanics, or establish complete passive payload closure.

## Types, meaning and identity

The pinned import contract describes original source roster identities, not
the serving layout. Store schema 3 deduplicates base profiles with a lossless alias map and
retains source-qualified roster records through linked availability and a
lossless reconstruction view; this does not change the source contract or lock.

Normalized types come from the upstream validator's explicit numeric/boolean
lists and the builder's field expressions. Numeric unit fields use REAL as a
lossless-for-this-source numeric serving input type; IDs and version tokens stay
TEXT. Shared native types and keys come from owner schema definitions. A derived
colour-hex projection is text, with its builder cited separately. No types are
inferred from the first data row.

Builder passthrough extension fields without an established numeric conversion
stay exact TEXT. They require a reviewed native schema mapping before numerical
use; the lock does not pretend their representation proves engine semantics.
All normalized columns are retained, including detail-only fields. Output groups
are mappings for step 2, not a completed response schema. Weapon-linked payloads
will be authoritative attack records; inline default-projectile fields must not
be emitted as a second attack.

Blank, zero and negative sentinel are different. Blank becomes NULL during the
future import; the verifier preserves source strings. When the source does not
distinguish unavailable from inapplicable, neither will we. Native operation
tokens, units, culture wildcards and access conditions are retained unchanged.

Roster identity is snapshot/game/patch/scale/subculture/unit. There are 3,181
roster rows and 2,409 distinct main-unit keys in this pin. Shared combat relations
join main-unit identities, not arbitrary race rows. Race inclusion, aliasing and
mount links cannot transfer permissions. Ability identity includes culture;
phase-link keys preserve order and all recipient flags. Native main-unit and
land-unit namespaces remain distinct.

Core passives require supported effects, conditions and concise source-grounded
explanations. Attributes and material attack traits also need explanations.
Activated options retain identity and qualified access only. Missing or
contradictory classification evidence remains unresolved. No effect is applied
to base stats at this stage.

## Verification and provenance

Run from the adviser repository on Windows, Linux or macOS:

```sh
python scripts/verify_sources.py --ctw-root ../CTW-data
python -m unittest discover -s tests -v
```

A checkout or exported directory is accepted. The verifier checks the exact
locked files, independently of its directory name or local branch. Git blob
hashes were checked when assembling this lock. Selected raw inputs also match
their upstream manifest/registry fingerprints. For historical newline differences,
both byte count and hash must match an LF or CRLF representation; spaces, BOMs,
values and other content are never normalized away. Bare carriage returns fail.

Changed/corrupt/missing files fail before any metadata is interpreted. A changed
contract, failed audit, owner mismatch, header drift, invalid type, duplicate key,
row-count mismatch or required unresolved weapon join also fails. Optional native
references use explicit `record_gap` reporting. This is source validation, not
a claim that all future serving foreign keys have already been implemented.

The future importer must attach original file fingerprints and logical CSV record
locators. Preserve upstream `source_path`, `source_line` and `source_patch`
separately: physical source lines and logical CSV records are not interchangeable.
Source paths present in records may point outside the selected input set; they
remain upstream provenance, never invented local foreign keys.

## Deliberate updates

Changing the pin is a reviewed data migration. First read the new owner contracts,
audit/compatibility reports and builder changes. Update selected paths, field
types, keys, row counts and owner gates explicitly. Obtain each included file at
that exact commit, compare its Git blob hash, compute SHA-256/size, and reconcile
upstream fingerprints. Recompute the contract fingerprint using sorted-key compact
UTF-8 JSON. Commit the contract, lock and fresh verification evidence together.
Do not refresh expected hashes just to make a failed check pass.

The packet schema, example fixtures, importer, SQLite store and query interface
are later steps. Issue #2 stays open.
