// Compare the shared read-only MCP endpoint with the ten frozen #6 receipts.
// npm install --prefix work/mcp-client @modelcontextprotocol/sdk@1.32.1
// CTW_MCP_SDK_ROOT may point to an existing SDK dist/esm directory.
import assert from 'node:assert/strict';
import { readFileSync, writeFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { pathToFileURL } from 'node:url';

const root = resolve(import.meta.dirname, '..');
const sdk = process.env.CTW_MCP_SDK_ROOT ?? resolve(root, 'work/mcp-client/node_modules/@modelcontextprotocol/sdk/dist/esm');
const { Client } = await import(pathToFileURL(resolve(sdk, 'client/index.js')).href);
const { StreamableHTTPClientTransport } = await import(pathToFileURL(resolve(sdk, 'client/streamableHttp.js')).href);
const endpoint = process.argv[2] ?? 'https://ctw-adviser-mcp-production.up.railway.app/mcp';
const output = process.argv[3];
const manifest = JSON.parse(readFileSync(resolve(root, 'docs/claude-fixtures.json'), 'utf8'));
const client = new Client({ name: 'ctw-claude-fixture-check', version: '1.0.0' });
const checks = [];

try {
  await client.connect(new StreamableHTTPClientTransport(new URL(endpoint)));
  const listed = await client.listTools();
  assert.deepEqual(new Set(listed.tools.map(tool => tool.name)), new Set([
    'resolve_unit', 'get_unit_combat_profile', 'get_matchup_evidence',
    'resolve_effect', 'get_effect', 'get_detail', 'get_provenance',
    'evaluate_single_unit_matchup',
  ]));
  assert.ok(listed.tools.every(tool => tool.annotations?.readOnlyHint === true));
  const call = async (name, args) => {
    const response = await client.callTool({ name, arguments: args });
    assert.notEqual(response.isError, true, `${name} returned isError`);
    assert.equal(response.structuredContent?.status, 'ok', `${name} status`);
    return response.structuredContent;
  };
  const pairs = new Set();
  for (const item of manifest.cases) {
    const { unit_a, unit_b } = item.arguments;
    const pair = `${unit_a}|${unit_b}`;
    if (pairs.has(pair)) continue;
    pairs.add(pair);
    for (const key of [unit_a, unit_b]) {
      const result = await call('resolve_unit', { name_or_key: key });
      assert.equal(result.data.status, 'resolved', `resolve ${key}`);
      assert.equal(result.snapshot.source_commit, item.expected_source_commit);
    }
    const evidence = await call('get_matchup_evidence', { unit_a, unit_b, limit: 1 });
    assert.equal(evidence.data.snapshot.commit, item.expected_source_commit);
    assert.equal(evidence.data.units.length, 2);
  }
  for (const item of manifest.cases) {
    const expected = JSON.parse(readFileSync(resolve(root, item.expected_result), 'utf8'));
    const response = await call('evaluate_single_unit_matchup', item.arguments);
    assert.deepEqual(response.data, expected, item.id);
    assert.equal(response.data.snapshot.commit, item.expected_source_commit);
    assert.equal(response.data.model_version, item.expected_model_version);
    checks.push({ id: item.id, equal: true });
  }
  const report = { status: 'passed', endpoint, source_commit: manifest.cases[0].expected_source_commit,
    pairs: pairs.size, evaluations: checks.length, checks };
  if (output) writeFileSync(output, JSON.stringify(report, null, 2) + '\n', 'utf8');
  console.log(JSON.stringify(report));
} finally {
  await client.close();
}
