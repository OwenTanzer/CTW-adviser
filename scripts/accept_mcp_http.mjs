// Protocol acceptance with the official MCP TypeScript SDK (development only).
// npm install --prefix work/mcp-client @modelcontextprotocol/sdk@1.32.1
// node scripts/accept_mcp_http.mjs http://127.0.0.1:8080/mcp
import assert from 'node:assert/strict';
import { pathToFileURL } from 'node:url';
import { resolve } from 'node:path';

const sdk = resolve('work/mcp-client/node_modules/@modelcontextprotocol/sdk/dist/esm');
const { Client } = await import(pathToFileURL(resolve(sdk, 'client/index.js')).href);
const { StreamableHTTPClientTransport } = await import(pathToFileURL(resolve(sdk, 'client/streamableHttp.js')).href);
const endpoint = process.argv[2] ?? 'http://127.0.0.1:8080/mcp';
const client = new Client({ name: 'ctw-adviser-acceptance', version: '1.0.0' });
const transport = new StreamableHTTPClientTransport(new URL(endpoint));
let reconnected;

try {
  await client.connect(transport);
  const listed = await client.listTools();
  assert.deepEqual(new Set(listed.tools.map(t => t.name)), new Set([
    'resolve_unit', 'get_unit_combat_profile', 'get_matchup_evidence',
    'get_detail', 'get_provenance', 'evaluate_single_unit_matchup'
  ]));
  for (const tool of listed.tools) {
    assert.ok(tool.inputSchema && tool.outputSchema && tool.description);
    assert.equal(tool.annotations?.readOnlyHint, true);
  }
  const call = async (name, args) => (await client.callTool({ name, arguments: args })).structuredContent;
  const exact = await call('resolve_unit', { name_or_key: 'Lothern Sea Guard' });
  assert.equal(exact.data.status, 'resolved');
  assert.equal(exact.snapshot.source_commit, '595e22764b22e748afdbafafcb0a6258973e2451');
  assert.equal((await call('resolve_unit', { name_or_key: 'Feral Manticore' })).data.status, 'ambiguous');
  assert.equal((await call('resolve_unit', { name_or_key: 'Bloodletters' })).data.status, 'not_found');
  const profile = await call('get_unit_combat_profile', {
    unit_key: 'Lothern Sea Guard', section: 'weapons', limit: 1
  });
  const weapons = profile.data.units[0].coverage.sections.find(s => s.name === 'weapons');
  assert.equal(weapons.state, 'partial');
  const next = await call('get_unit_combat_profile', {
    unit_key: 'Lothern Sea Guard', section: 'weapons', limit: 1, cursor: weapons.cursor
  });
  assert.equal(next.data.units[0].coverage.sections.find(s => s.name === 'weapons').offset, 1);
  const ref = profile.data.units[0].provenance_refs[0];
  assert.ok((await call('get_provenance', { record_ids: [ref] })).data.provenance[ref]);
  assert.equal((await call('get_detail', { ref: `record:${ref}`, limit: 1 })).status, 'ok');
  const missing = await client.callTool({ name: 'get_unit_combat_profile',
    arguments: { unit_key: 'no-such-unit' } });
  assert.equal(missing.isError, true);
  await assert.rejects(() => client.callTool({ name: 'resolve_unit',
    arguments: { name_or_key: 'Teclis', limit: 2 } }));
  for (const [unit_a, unit_b] of [
    ['Reiksguard', 'Doom Diver Catapults'],
    ['Lothern Sea Guard', 'Blue Horrors of Tzeentch'],
    ['Bloodletters of Khorne', 'Kroxigor'],
    ['Queen Bess', 'Reiksguard']
  ]) {
    const pair = await call('get_matchup_evidence', { unit_a, unit_b, limit: 32 });
    assert.equal(pair.data.units.length, 2);
    assert.equal(pair.data.snapshot.commit, exact.snapshot.source_commit);
  }
  for (const [unit_a, unit_b] of [
    ['Reiksguard', 'Doom Diver Catapults'],
    ['Lothern Sea Guard (Shields)', 'Blue Horrors of Tzeentch'],
    ['Bloodletters of Khorne', 'Kroxigor'],
    ['Queen Bess', 'Reiksguard']
  ]) {
    const modeled = await call('evaluate_single_unit_matchup', { unit_a, unit_b });
    assert.equal(modeled.model_version, modeled.data.model_version);
    assert.equal(modeled.data.derived.ledgers.length, 2);
    assert.equal(modeled.data.snapshot.commit, exact.snapshot.source_commit);
    assert.equal(modeled.data.empirical_calibration, null);
    assert.ok(modeled.data.limitations.length > 0);
  }
  await assert.rejects(() => client.callTool({ name: 'evaluate_single_unit_matchup',
    arguments: { unit_a: 'Reiksguard', unit_b: 'Kroxigor', scenario: { baseline: 'campaign' } } }));
  await assert.rejects(() => client.callTool({ name: 'evaluate_single_unit_matchup',
    arguments: { unit_a: 'Reiksguard', unit_b: 'Kroxigor',
      scenario: { sides: { a: { active_contacts: 1e100 } } } } }));
  assert.equal((await call('resolve_unit', { name_or_key: 'Lothern Sea Guard' })).status, 'ok');
  await client.close();
  reconnected = new Client({ name: 'ctw-adviser-reconnect', version: '1.0.0' });
  await reconnected.connect(new StreamableHTTPClientTransport(new URL(endpoint)));
  assert.equal((await reconnected.listTools()).tools.length, 6);
  console.log(JSON.stringify({ status: 'passed', endpoint, protocol: '2025-06-18',
    source_commit: exact.snapshot.source_commit, tools: listed.tools.map(t => t.name), pairs: 4,
    calculations: 4, errors: true, reconnect: true }));
} finally {
  await reconnected?.close();
  await client.close();
}
