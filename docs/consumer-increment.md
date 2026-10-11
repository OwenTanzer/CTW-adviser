# First query consumers for issues #3 and #5

This increment closes the database dependency boundary in issue #2. It does not
claim completion of the hosted MCP service or the full combat model.

## Local MCP query path

Build or obtain the verified SQLite artifact using the existing release workflow,
then run from the repository root:

```sh
PYTHONPATH=src python -m ctw_adviser.mcp --db work/adviser.sqlite
```

On Windows PowerShell, set `$env:PYTHONPATH='src'` first. A client launches this
process and sends newline-delimited UTF-8 JSON-RPC 2.0 over stdio. The server
negotiates MCP protocol `2025-06-18`; `initialize`,
`notifications/initialized`, `tools/list` and `tools/call` are implemented.
The five read-only tools are `resolve_unit`, `get_unit_combat_profile`,
`get_matchup_evidence`, `get_detail` and `get_provenance`. The last two expand
packet references; ordinary packets retain bounded sections and cursors.
Discovery includes input/output JSON Schemas. Tool calls return both structured
content and a JSON text block. Ambiguity and missing names remain explicit.

The local server opens a prebuilt artifact through `Queries`, which checks the
supported store schema and import-contract fingerprint. It does not build,
refresh, fetch or edit a snapshot. Its response envelope includes the source
commit and snapshot metadata; packet data retains baseline, owner patches,
coverage, detail references and provenance. Authentication and public HTTPS
transport belong to issue #3; this process has no network listener or credentials.

## Movement-phase calculation

```sh
PYTHONPATH=src python -m ctw_adviser.cli movement-phase --db work/adviser.sqlite \
  --separation-metres 200 "Lothern Sea Guard" "Blue Horrors of Tzeentch"
```

`movement_phase` retrieves the pair through `Queries` at the maximum supported
single-page limit. It reads each primary body's native run speed and all returned
missile range variants. It reports sourced identities, values, section coverage
and provenance references separately from model assumptions and derived timing.
The distance and ranges use metres. The conversion from one native speed point
to metres per second is an **illustrative model assumption**, defaulting to 1 and
overridable with `--metres-per-second-per-speed-point`; it is not an imported
engine rule or live calibration. Both units have explicit approach, hold or
retreat orders. Under constant speeds along one unobstructed line, their directed
velocities determine closing speed. Contact occurs at zero separation; a ranged
attack enters listed range when separation reaches that attack's range. Already
reached and nonclosing cases have explicit states. Unknown speed/range produces
unknown timing; partial weapon sections are marked partial rather than complete.

Range entry is not a shot. The model makes no claim about line of sight, firing
arcs, flight, reload, acceleration, charge, terrain, fatigue, passive effects,
damage, casualties, artillery disablement, leadership, routing, winner, or
campaign availability. Those remain work for issue #5 and the adviser workflow.
The model reports no verdict. It uses no unit-specific branch or copied roster
constant. The existing offline `matchup` query continues to return source
evidence and echo caller context; `movement-phase` is the calculation path.

## Verification

`tests/test_consumers.py` exercises a protocol conversation, five tool schemas,
the three parent fixture pairs plus Queen Bess/Reiksguard, explicit ambiguous and
missing identity handling, weapon pagination, detail/provenance expansion,
CLI/library equality, movement edge cases and monotonicity. Its disposable copy
of the SQLite artifact changes a retrieved speed and missile range and confirms
the calculated output changes. Set `CTW_ADVISER_DB` to a built pinned snapshot
when it is not at `work/adviser.sqlite`.
