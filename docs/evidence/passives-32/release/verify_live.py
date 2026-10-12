import json, urllib.request
from pathlib import Path
root=Path(__file__).resolve().parents[2]
out=Path(__file__).parent
url="https://ctw-adviser-mcp-production.up.railway.app"
def rpc(method,params):
    req=urllib.request.Request(url+"/mcp",data=json.dumps({"jsonrpc":"2.0","id":1,"method":method,"params":params}).encode(),headers={"Content-Type":"application/json","Accept":"application/json, text/event-stream"})
    with urllib.request.urlopen(req,timeout=120) as r:return json.load(r)
schema=rpc("tools/list",{})
(out/"live-schema.json").write_text(json.dumps(schema,indent=2))
evaluator=next(t for t in schema["result"]["tools"] if t["name"]=="evaluate_single_unit_matchup")
assert "passives" in evaluator["inputSchema"]["properties"]["scenario"]["properties"]["sides"]["properties"]["a"]["properties"]
receipt=json.loads((root/"docs/evidence/passives-32/receipt.json").read_text())
results={}
for case in ("enabled","disabled"):
    args={"unit_a":receipt["requests"]["unit_a"],"unit_b":receipt["requests"]["unit_b"],"scenario":receipt["requests"][case]}
    response=rpc("tools/call",{"name":"evaluate_single_unit_matchup","arguments":args})
    (out/(case+"-remote.json")).write_text(json.dumps(response,indent=2))
    data=response["result"]["structuredContent"]
    assert data["model_version"]=="combat-0.2.0",data["model_version"]
    assert data["data"]==receipt[case],case+" full result mismatch"
    results[case]={"exact_equal_to_library_cli":True,"goblin_damage":data["data"]["derived"]["ledgers"][0]["incoming_damage"]["melee"]}
print(json.dumps({"status":"passed","model":"combat-0.2.0","cases":results}))
