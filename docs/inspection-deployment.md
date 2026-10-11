# Existing Datasette inspection service

The inspection app is a read-only view over the same `Queries` packet interface
used by the offline CLI. Its Docker build downloads only files in
`source_lock.json` from the locked CTW-data commit, verifies their bytes and
source contract, then builds `ctw.sqlite`. The database is an image artifact;
CTW-data is never modified. The human page expands provenance in a collapsed
panel. JSON keeps provenance deferred unless `provenance=1` is requested.

## Local check

After installing `datasette==0.65.5` in an isolated environment and rebuilding
the snapshot from the locked CTW-data checkout:

```sh
python scripts/verify_sources.py --ctw-root ../CTW-data
python scripts/build_snapshot.py build --ctw-root ../CTW-data --output work/ctw.sqlite
datasette serve -i work/ctw.sqlite --metadata datasette-metadata.json \
  --plugins-dir inspection_plugins --host 127.0.0.1 --port 8765
```

Check `/ctw.json`, `/inspect?q=Teclis`, and a Celestial Hurricanum unit view.
The HTML should show the locked source commit and packet 1.21.0, with
“Supporting source documentation” closed by default. The JSON view should
have `provenance_mode: deferred` and empty `sources`/`provenance`; requesting
`provenance=1` should expand those dictionaries. Check ambiguous and unknown
names as well as a source-evidence detail link.

## PR #23 inspection preview

The existing target is project **CTW Datasette**, production environment,
service **ctw-datasette**, at
`https://ctw-datasette-production.up.railway.app`. Its currently connected
source is the historical `inspection/datasette` branch. For a pre-merge review,
build this same service from an exact **unmerged PR #23 commit**. Do not change
the separate MCP service. The root `Dockerfile` and `railway.toml` provide the
builder, health check, and launch command; do not create another service or
database.

The `/inspect` and detail pages must display **PR #23 preview — unmerged** and
the full adviser commit SHA. A GitHub-triggered build on
`issue-19/character-access` uses Railway's `RAILWAY_GIT_BRANCH` and
`RAILWAY_GIT_COMMIT_SHA`; a manually pinned build must set `CTW_PREVIEW_PR=23`
and `CTW_ADVISER_COMMIT` to the exact 40-character commit SHA. A preview with a
missing, invalid or conflicting SHA fails startup. Match the visible adviser
SHA to the deployment source commit. The CTW-data source SHA and packet version
are separate identities and must also match the reviewed candidate.

Record the deployment ID and require Railway `SUCCESS`, `/ctw.json`, the
visible preview label and SHA, packet 1.21.0, store schema 4, and representative
character/effect and provenance checks before inviting hands-on inspection.
After review and merge, make a separate decision about the site's final source.

For rollback, redeploy the last known successful deployment of this same
service and environment, then repeat the live checks. Reconnect the intended
source branch or commit deliberately before allowing automatic future deploys.
