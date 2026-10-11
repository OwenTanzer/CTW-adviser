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
The HTML should show the locked source commit and packet 1.19.0, with
“Supporting source documentation” closed by default. The JSON view should
have `provenance_mode: deferred` and empty `sources`/`provenance`; requesting
`provenance=1` should expand those dictionaries. Check ambiguous and unknown
names as well as a source-evidence detail link.

## Railway synchronization

The existing target is project **CTW Datasette**, production environment,
service **ctw-datasette**, at
`https://ctw-datasette-production.up.railway.app`. Its currently connected
source is the historical `inspection/datasette` branch. After this candidate
has been independently reviewed and merged, connect **that reviewed commit**
of `OwenTanzer/CTW-adviser` to the same service. The root `Dockerfile` and
`railway.toml` provide the builder, health check, and launch command. Do not
create another service or database. Record the new deployment ID and require
Railway `SUCCESS` plus live packet/source/version checks before calling the
site synchronized.

For rollback, redeploy the last known successful deployment of this same
service and environment, then repeat the live checks. Reconnect the intended
source branch or commit deliberately before allowing automatic future deploys.
