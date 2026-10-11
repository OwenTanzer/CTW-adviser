"""Read-only MCP stdio adapter over the pinned SQLite query library.

Run ``python -m ctw_adviser.mcp --db PATH``. Stdout contains JSON-RPC only.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys

from .queries import Queries, ResolutionError

PROTOCOL_VERSION = "2025-06-18"
SERVER_VERSION = "0.1.0"


def _tool(name, description, properties, required=()):
    return {"name": name, "description": description,
            "inputSchema": {"type": "object", "properties": properties,
                            "required": list(required), "additionalProperties": False},
            "outputSchema": {"type": "object", "properties": {
                "status": {"type": "string"}, "snapshot": {"type": "object"},
                "adapter_version": {"type": "string"},
                "model_version": {"type": "null"},
                "data": {"type": "object"}},
                "required": ["status", "adapter_version", "model_version", "snapshot", "data"]}}


STRING = {"type": "string", "minLength": 1}
LIMIT = {"type": "integer", "minimum": 1, "maximum": 256, "default": 32}
TOOLS = [
    _tool("resolve_unit", "Resolve an exact unit key or name; ambiguous names return candidates. No fuzzy choice or availability inference.",
          {"name_or_key": STRING, "subculture": STRING}, ("name_or_key",)),
    _tool("get_unit_combat_profile", "Retrieve one qualified unit's sourced combat packet. Sections page explicitly; omitted sections are not absent mechanics. No damage or winner prediction.",
          {"unit_key": STRING, "subculture": STRING,
           "mode": {"type": "string", "enum": ["combined", "melee", "missile"]},
           "section": {"type": "string", "enum": ["components", "weapons", "attributes", "abilities", "activated_options"]},
           "cursor": STRING, "limit": LIMIT, "include_provenance": {"type": "boolean"}}, ("unit_key",)),
    _tool("get_matchup_evidence", "Retrieve two units through the same read-only query path. Source facts, variants, coverage and provenance only; no modeled outcome.",
          {"unit_a": STRING, "unit_b": STRING, "subculture_a": STRING, "subculture_b": STRING,
           "mode": {"type": "string", "enum": ["combined", "melee", "missile"]},
           "section": {"type": "string", "enum": ["components", "weapons", "attributes", "abilities", "activated_options"]},
           "limit": LIMIT, "include_provenance": {"type": "boolean"}}, ("unit_a", "unit_b")),
    _tool("get_detail", "Expand an exact packet detail reference with bounded pagination.",
          {"ref": STRING, "cursor": STRING, "limit": LIMIT}, ("ref",)),
    _tool("get_provenance", "Expand exact source record IDs returned in a packet (maximum 64 per call).",
          {"record_ids": {"type": "array", "items": STRING, "minItems": 1, "maxItems": 64}}, ("record_ids",)),
]
BY_NAME = {tool["name"]: tool for tool in TOOLS}


def _validate(tool, args):
    schema = tool["inputSchema"]
    if not isinstance(args, dict):
        raise ValueError("arguments must be an object")
    if set(args) - set(schema["properties"]):
        raise ValueError("unknown argument")
    if set(schema["required"]) - set(args):
        raise ValueError("missing required argument")
    for key, value in args.items():
        rule = schema["properties"][key]
        kind = rule["type"]
        if kind == "string" and (not isinstance(value, str) or not value.strip()):
            raise ValueError(f"{key} must be a nonempty string")
        if kind == "integer" and (type(value) is not int or not rule["minimum"] <= value <= rule["maximum"]):
            raise ValueError(f"{key} must be an integer from {rule['minimum']} to {rule['maximum']}")
        if kind == "boolean" and type(value) is not bool:
            raise ValueError(f"{key} must be boolean")
        if kind == "array" and (not isinstance(value, list) or not rule["minItems"] <= len(value) <= rule["maxItems"]
                                or any(not isinstance(item, str) or not item.strip() for item in value)):
            raise ValueError(f"{key} must contain 1 to 64 nonempty strings")
        if "enum" in rule and value not in rule["enum"]:
            raise ValueError(f"unsupported {key}")


def _content(payload, is_error=False):
    result = {"content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=False, allow_nan=False)}],
              "structuredContent": payload}
    if is_error:
        result["isError"] = True
    return result


def call_tool(queries, name, args):
    tool = BY_NAME.get(name)
    if tool is None:
        raise ValueError(f"unknown tool: {name}")
    _validate(tool, args)
    try:
        if name == "resolve_unit":
            data = queries.resolve_unit(args["name_or_key"], args.get("subculture"))
        elif name == "get_unit_combat_profile":
            data = queries.get_unit_profile(args["unit_key"], subculture=args.get("subculture"),
                                            mode=args.get("mode", "combined"), section=args.get("section"),
                                            cursor=args.get("cursor"), limit=args.get("limit", 32),
                                            include_provenance=args.get("include_provenance", False))
        elif name == "get_matchup_evidence":
            data = queries.get_matchup_evidence(args["unit_a"], args["unit_b"],
                                                subculture=args.get("subculture_a"),
                                                subculture_b=args.get("subculture_b"),
                                                mode=args.get("mode", "combined"), section=args.get("section"),
                                                limit=args.get("limit", 32),
                                                include_provenance=args.get("include_provenance", False))
        elif name == "get_detail":
            data = queries.get_detail(args["ref"], cursor=args.get("cursor"), limit=args.get("limit", 32))
        else:
            data = queries.get_provenance(args["record_ids"])
        return _content({"status": "ok", "adapter_version": SERVER_VERSION,
                         "model_version": None, "snapshot": queries.snapshot, "data": data})
    except ResolutionError as exc:
        return _content({"status": exc.result["status"], "adapter_version": SERVER_VERSION,
                         "model_version": None, "snapshot": queries.snapshot, "data": exc.result}, True)
    except (ValueError, KeyError, sqlite3.Error) as exc:
        return _content({"status": "error", "adapter_version": SERVER_VERSION,
                         "model_version": None, "snapshot": queries.snapshot,
                         "data": {"message": str(exc)}}, True)


def _response(message_id, *, result=None, error=None):
    response = {"jsonrpc": "2.0", "id": message_id}
    response["error" if error else "result"] = error or result
    return response


def serve(queries, input_stream=None, output_stream=None):
    input_stream = input_stream or sys.stdin
    output_stream = output_stream or sys.stdout
    initialized = False
    ready = False
    for line in input_stream:
        try:
            request = json.loads(line)
            if not isinstance(request, dict) or request.get("jsonrpc") != "2.0" or not isinstance(request.get("method"), str):
                raise ValueError("invalid JSON-RPC request")
            method = request["method"]
            message_id = request.get("id")
            if method == "notifications/initialized" and initialized and "id" not in request:
                ready = True
                continue
            if "id" not in request or isinstance(message_id, bool) or not isinstance(message_id, (str, int)):
                continue
            if method == "initialize" and not initialized:
                params = request.get("params", {})
                if not isinstance(params, dict) or not isinstance(params.get("protocolVersion"), str):
                    response = _response(message_id, error={"code": -32602, "message": "invalid initialize params"})
                else:
                    initialized = True
                    response = _response(message_id, result={"protocolVersion": PROTOCOL_VERSION,
                        "capabilities": {"tools": {}},
                        "serverInfo": {"name": "ctw-adviser", "version": SERVER_VERSION}})
            elif method == "ping" and initialized:
                response = _response(message_id, result={})
            elif not ready:
                response = _response(message_id, error={"code": -32000, "message": "initialize first"})
            elif method == "tools/list":
                response = _response(message_id, result={"tools": TOOLS})
            elif method == "tools/call":
                params = request.get("params")
                if not isinstance(params, dict) or not isinstance(params.get("name"), str) or params["name"] not in BY_NAME:
                    response = _response(message_id, error={"code": -32602, "message": "unknown tool"})
                else:
                    try:
                        result = call_tool(queries, params["name"], params.get("arguments", {}))
                        response = _response(message_id, result=result)
                    except ValueError as exc:
                        response = _response(message_id, error={"code": -32602, "message": str(exc)})
            else:
                response = _response(message_id, error={"code": -32601, "message": "method not found"})
        except (ValueError, json.JSONDecodeError):
            response = _response(None, error={"code": -32700, "message": "invalid JSON-RPC message"})
        output_stream.write(json.dumps(response, ensure_ascii=False, allow_nan=False, separators=(",", ":")) + "\n")
        output_stream.flush()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", required=True)
    args = parser.parse_args()
    # MCP stdio is UTF-8 regardless of the Windows console/pipe code page.
    sys.stdin.reconfigure(encoding="utf-8", errors="strict")
    sys.stdout.reconfigure(encoding="utf-8", errors="strict", newline="\n")
    with Queries(args.db) as queries:
        serve(queries)


if __name__ == "__main__":
    main()
