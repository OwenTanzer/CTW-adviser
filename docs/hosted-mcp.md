# Hosted MCP transport candidate (issue #3)

The same six read-only tools served over stdio are available at `/mcp` using
MCP Streamable HTTP protocol `2025-06-18`. This is a deployable candidate, not a
live endpoint or a completed ChatGPT Work connection. The existing Railway
Datasette URL is only for human inspection.

## Local build and acceptance

From this repository, using Python 3.11+ and a CTW-data checkout at commit
`595e22764b22e748afdbafafcb0a6258973e2451`:

```sh
python scripts/verify_sources.py --ctw-root ../CTW-data
python scripts/rebuild_release.py --ctw-root ../CTW-data --output work/adviser.sqlite --manifest work/adviser.manifest.json
python scripts/verify_release.py --db work/adviser.sqlite --manifest work/adviser.manifest.json
PYTHONPATH=src python -m ctw_adviser.mcp_http --db work/adviser.sqlite --port 8080
```

In a second shell:

```sh
PYTHONPATH=src python -m unittest tests.test_mcp_http tests.test_consumers -v
npm install --prefix work/mcp-client @modelcontextprotocol/sdk@1.32.1
node scripts/accept_mcp_http.mjs http://127.0.0.1:8080/mcp
curl -i http://127.0.0.1:8080/healthz
```

On PowerShell use `$env:PYTHONPATH='src'` instead of `PYTHONPATH=src`.
The Node SDK is a development-only test dependency in ignored `work/`; the server
uses Python's standard library. For a reviewed deployment replace the URL in
`accept_mcp_http.mjs` with the final `https://.../mcp` endpoint. The same four
pairs, ambiguity, paging, detail, provenance and four conditional calculation
checks then run remotely. This integration branch requires the independently
reviewed combat implementation from PR #16 before deployment.

## Wire and lifecycle

Each JSON-RPC message is one UTF-8 POST with `Content-Type: application/json`
and `Accept: application/json, text/event-stream`. `initialize` negotiates
`2025-06-18`; `notifications/initialized` gets HTTP 202. Discovery and tool
responses are JSON (including `structuredContent` and an equivalent text
block). The server is stateless: it issues no `Mcp-Session-Id`, does not retain
conversations, and does not produce unsolicited messages. GET `/mcp` and DELETE
`/mcp` return 405 because there is no SSE stream or session to close. The MCP
SDK reconnects by initializing again; a disconnected request does not mutate
the source or leave a session behind. Stdio remains available with
`PYTHONPATH=src python -m ctw_adviser.mcp --db work/adviser.sqlite`.

The server opens an already built SQLite artifact through `Queries` in
`mode=ro` with `query_only=ON` and rejects unsupported schema/contract at
startup. Ordinary calls never fetch, rebuild or write source data. Request
bodies are limited to 64 KiB, responses to 1 MiB, concurrent connections to
16 and inactive sockets to 15 seconds. Tool schemas retain 1–256 item paging
limits and 64 IDs per provenance call. Oversize responses return an actionable
JSON-RPC error asking for a smaller limit or section. Origin headers are checked
against exact `--allowed-origin` values or comma-separated
`CTW_ALLOWED_ORIGINS`; requests without an Origin are
accepted for server-side clients. Local binding defaults to `127.0.0.1`;
non-loopback binding requires explicit `--allow-public`. Never put a token or
user input in the URL. The app writes no request bodies or conversation logs.

Every tool response carries adapter version, source snapshot and a separate
model version field (null for evidence tools, `combat-0.1.0` for the evaluator).
`evaluate_single_unit_matchup` delegates unchanged scenario arguments to
`combat.evaluate_matchup` and wraps its source facts, assumptions, two ledgers,
conditional verdict, sensitivity and limitations as structured content. Names
with multiple matches return candidates; the adapter never chooses a variant.
The hosted adapter caps scenario duration at 300 seconds, separation at 10,000
metres and an explicitly set firing cycle at a minimum of 0.25 seconds. The
combat library validates the other scenario fields. Check direct library, CLI
and MCP results against the same scenario JSON before release. ChatGPT
workflow instructions should refer to these tool names and schemas, not copy
data or equations.

## Deployment decision and update path

The inspected Railway project is **CTW Datasette**
(`c9508545-a42a-4f74-84bf-092de49ab94a`), environment **production**
(`79823054-462e-4d00-b962-94ad526c4b4f`). Its one service,
**ctw-datasette** (`892527d7-a069-4df0-835a-0d71b792f3f7`), is a successful
inspection deployment at `https://ctw-datasette-production.up.railway.app`.
It must stay an inspection app; that URL is not an MCP endpoint. The observed
source is `OwenTanzer/CTW-adviser` branch `main`, with Railway config pointing
to commit `f3dab8b346a348c0fb22d79e18bc7328b12f094c` at inspection time.

The preferred hosted target is a **separate** `ctw-adviser-mcp` service in the
same project and production environment, with its own Railway HTTPS domain.
Set `RAILWAY_DOCKERFILE_PATH=Dockerfile.mcp` on that service, and set its
health-check path to `/healthz` with a 120-second timeout in service settings.
Railway's legacy `railway.toml` config path is unavailable to new services;
the repository root file continues to belong to Datasette. This target needs an explicit decision
because another Railway service may incur cost. An alternative is a separately
approved host with HTTPS termination that runs this same image and `/mcp`
path. Do not repurpose the Datasette service or point a client at it. No
service/domain/variable has been created by this candidate.

The current candidate uses **public, unauthenticated read-only access** to
public game data. This avoids a shared secret and supports standard MCP clients,
but anyone with the URL can call it and individual revocation is unavailable.
Before production, approve this public policy with platform rate limiting, or
choose individual OAuth with revocation at a gateway. The latter needs a
separate security design and configuration; no credential or permission
expansion is included here. TLS must terminate at the platform HTTPS domain.

For each reviewed release: build the image at a reviewed adviser commit;
download exactly the files in `source_lock.json` from the pinned CTW-data
commit during image build; verify hashes and contract; build the SQLite file;
inspect integrity; then publish the image. Redeploy only after review, record
deployment ID and require Railway `SUCCESS`, `/healthz`, and the remote SDK
acceptance command above. Record returned source commit, base patch/build
`9.0/25507028`, unit scale `ultra`, owner-specific supplemental patch/build,
store schema 3, packet 1.19.0 and model version. On mismatch, stop rollout and
restore the previous successful deployment. A source refresh changes the lock,
contract and verification evidence through its separate reviewed process.

For ChatGPT Work, once HTTPS, access policy and service are approved and live,
go to ChatGPT Plugins, select **+ → Add custom MCP server**, enter a name and
description, and supply the final `https://<domain>/mcp` URL under Connection.
Choose the approved authentication mode, review the risk warning, create the
plugin, and inspect the five discovered tools. Install it, start a new chat,
select the plugin with `@`, and run the exact-name, ambiguity and pair probes.
Workspace policy can restrict custom servers. If tool metadata changes, refresh
the connection and start a new chat before retesting. These steps follow the
[OpenAI plugin connection guide](https://developers.openai.com/plugins/deploy/connect-chatgpt).
Client organization permissions and first conversation acceptance remain to be
verified; no live ChatGPT connection is claimed here.
