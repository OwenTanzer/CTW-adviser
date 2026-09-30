# Working instructions

Read the current GitHub issue before implementing its next increment.
CTW-data is authoritative and its generated production files must not be edited.
Read source_lock.json, schema/import_contract.json and docs/source-contract.md.
Use Python 3.11+ standard library initially. No database service or ORM.

Keep source facts, interpretation, scenario assumptions and calculated results
separate. Preserve qualified identities, nulls, native sentinels, all relationship
edges and per-owner patch scope. Do not apply passive effects to base profiles.
Use source-backed types and explicit mappings, never first-row type inference.

Changes to the source pin or import scope require a deliberate reviewed update of
the lock, contract and verification evidence. Step 1 is not full issue closure.
Build future candidates under ignored work/ and install only after validation.
