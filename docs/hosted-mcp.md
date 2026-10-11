# Hosted MCP service (issue #3)

This checkout serves six read-only tools over stdio and `/mcp` using MCP
Streamable HTTP protocol `2025-06-18`. The separately deployed live endpoint
still exposes eight tools from the earlier release. Its URL is
`https://ctw-adviser-mcp-production.up.railway.app/mcp`, with public,
unauthenticated read-only access. ChatGPT CTW Advisor connector calls were
verified on 2026-10-11; see [acceptance evidence](closure-3-6.md). The Railway
Datasette URL remains human inspection only.

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
pairs, ambiguity, paging, detail, provenance and four calculation
checks then run remotely. The hosted adapter delegates to the same combat library as the CLI.
Keep live release verification separate from local test results.

## Wire and lifecycle

Each JSON-RPC message is one UTF-8 POST with `Content-Type: application/json`
and `Accept: application/json, text/event-stream`. `initialize` negotiates
`2025-06-18`; `notifications/initialized` gets HTTP 202. Discovery and tool
responses are JSON (including `structuredContent` and an equivalent text
block). The server is stateless: it issues no `Mcp-Session-Id`, does not retain
conversations, and does not produce unsolicited messages. GET `/mcp` and DELETE
`/mcp` return 405 because there is no SSE stream or session to close. The MCP
server sends `Connection: close` after each response, releasing its worker slot.
The SDK reconnects by initializing again; a disconnected request does not mutate
the source or leave a session behind. Stdio remains available with
`PYTHONPATH=src python -m ctw_adviser.mcp --db work/adviser.sqlite`.

The server opens an already built SQLite artifact through `Queries` in
`mode=ro` with `query_only=ON` and rejects unsupported schema, contract, source
commit or snapshot ID at startup. The hosted source commit must be
`595e22764b22e748afdbafafcb0a6258973e2451`, and the ID must match that
commit, the supported contract hash and `store3`. This identity check does not
replace the build manifest's file-integrity verification. Ordinary calls never
fetch, rebuild or write source data. Request
bodies are limited to 64 KiB, responses to 1 MiB, concurrent connections to
16, inactive sockets to 15 seconds and complete body upload to 10 seconds.
Handled HTTP requests, including `/healthz`, are also capped at 60 per rolling
minute per server process; excess requests receive HTTP 429 with `Retry-After`.
The limit is global because reverse proxy
addresses and forwarded IP headers are not reliable user identities. If the
service is scaled beyond one replica, each replica has its own limit. Tool
schemas retain 1-256 item paging
limits and 64 IDs per provenance call. Oversize responses return an actionable
JSON-RPC error asking for a smaller limit or section. Origin headers are checked
against exact `--allowed-origin` values or comma-separated
`CTW_ALLOWED_ORIGINS`; requests without an Origin are
accepted for server-side clients. Local binding defaults to `127.0.0.1`;
non-loopback binding requires explicit `--allow-public`. Never put a token or
user input in the URL. The app writes no request bodies or conversation logs.

Every tool response carries adapter version, source snapshot and a separate
model version field (null for evidence tools, the combat library's reported
version for the evaluator).
`evaluate_single_unit_matchup` delegates unchanged scenario arguments to
`combat.evaluate_matchup` and wraps its source facts, assumptions, two ledgers,
conditional verdict, sensitivity and limitations as structured content. Names
with multiple matches return candidates; the adapter never chooses a variant.
The hosted adapter caps scenario duration at 300 seconds, separation at 10,000
metres, an explicitly set firing cycle at a minimum of 0.25 seconds, and
previously unbounded numeric scenario settings at 1,000,000,000. Nonfinite
numbers are rejected as invalid arguments. The combat library validates the
other scenario fields. Check direct library, CLI
and MCP results against the same scenario JSON before release. ChatGPT
workflow instructions should refer to these tool names and schemas, not copy
data or equations.

## Deployment decision and update path

The inspected Railway project is **CTW Datasette**
(`c9508545-a42a-4f74-84bf-092de49ab94a`), environment **production**
(`79823054-462e-4d00-b962-94ad526c4b4f`). Its existing inspection service,
**ctw-datasette** (`892527d7-a069-4df0-835a-0d71b792f3f7`), is a successful
inspection deployment at `https://ctw-datasette-production.up.railway.app`.
It must stay an inspection app; that URL is not an MCP endpoint. The inspection service has its own release lifecycle; its historical source
commit is not evidence of the MCP service version.

The approved hosted target is a **separate** `ctw-adviser-mcp` service in the
same project and production environment, with its own Railway HTTPS domain.
Service `ec9aff14-4f04-4386-a62b-d83657a0c927` uses `Dockerfile.mcp` and
`/healthz`. On 2026-10-11, Railway reports deployment
`5961fed3-5475-4ae9-8e06-59cf424f1004` SUCCESS (created 13:27:12 UTC),
with HTTPS domain `ctw-adviser-mcp-production.up.railway.app` targeting port 8080.
The deployment listing does not expose a source SHA for this redeploy; record
the live protocol versions and equality evidence rather than inventing one.
Railway's legacy `railway.toml` config path is unavailable to new services;
the repository root file continues to belong to Datasette. Do not repurpose
the Datasette service or point a client at it.

Owen approved up to US$5 per month of additional usage for this service.
Railway's hard spending limit is workspace-wide, has a US$10 minimum, and
shuts down every workload in the workspace when reached; it cannot enforce a
US$5 incremental cap for this service. Track its current and estimated cost
from the workspace Usage page's project/service breakdown after release.
Replica CPU/memory limits and Serverless sleep can reduce usage but do not cap
egress or guarantee a dollar ceiling. Keep one replica, inspect its first-day
usage and projected end-of-cycle cost, and stop or reconfigure it before an
additional US$5 is incurred. No workspace-wide spending limit has changed.

Owen approved **public, unauthenticated read-only access** for the initial
endpoint. Anyone with the URL can call it, and individual revocation is
unavailable. The process-wide rolling limit, connection cap and body/response
limits bound ordinary traffic; production may add platform edge controls after
inspection. TLS must terminate at the platform HTTPS domain. No credential or
permission expansion is included here.

The initial service is deployed. For each subsequent reviewed release: build
the image at a reviewed adviser commit;
download exactly the files in `source_lock.json` from the pinned CTW-data
commit during image build; verify hashes and contract; build the SQLite file;
inspect integrity; then publish the image. Redeploy only after review, record
deployment ID and require Railway `SUCCESS`, `/healthz`, and the remote SDK
acceptance command above. Record returned source commit, base patch/build
`9.0/25507028`, unit scale `ultra`, owner-specific supplemental patch/build,
store schema 3, packet 1.19.0 and model version. On mismatch, stop rollout and
restore the previous successful deployment. A source refresh changes the lock,
contract and verification evidence through its separate reviewed process.

For ChatGPT Work,
go to ChatGPT Plugins, select **+ → Add custom MCP server**, enter a name and
description, and supply `https://ctw-adviser-mcp-production.up.railway.app/mcp` under Connection.
Choose **No authentication**, review the risk warning, create the
plugin, and inspect the eight discovered tools. Install it, start a new chat,
select the plugin with `@`, and run the exact-name, ambiguity and pair probes.
Workspace policy can restrict custom servers. If tool metadata changes, refresh
the connection and start a new chat before retesting. These steps follow the
[OpenAI plugin connection guide](https://developers.openai.com/plugins/deploy/connect-chatgpt).
Owen reported successful connector calls for all three parent fixtures and an
extra pair on 2026-10-11. Independent connector receipts and CLI comparisons
are recorded in [closure evidence](closure-3-6.md). The server exposes eight
tools; this session’s connector exposes the six unit/evaluation tools required
by this workflow. The two effect tools are outside this acceptance scope.
Real Claude conversations and tester onboarding remain issue #4.

For HTTP 429, honor Retry-After and pace calls. The 60-request process-wide
minute budget is shared across clients; simultaneous acceptance suites can
exhaust it without indicating a model or source defect.
