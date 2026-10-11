"""Read-only MCP stdio adapter over the pinned SQLite query library.

Run ``python -m ctw_adviser.mcp --db PATH``. Stdout contains JSON-RPC only.
"""

from __future__ import annotations

import argparse
import json
import math
import sqlite3
import sys

from .queries import Queries, ResolutionError
from .unit_search import SearchError, UnitSearch

PROTOCOL_VERSION = "2025-06-18"
SERVER_VERSION = "0.1.0"


def _tool(name, description, properties, required=()):
    return {"name": name, "description": description,
            "annotations": {"readOnlyHint": True, "destructiveHint": False,
                            "openWorldHint": False},
            "inputSchema": {"type": "object", "properties": properties,
                            "required": list(required), "additionalProperties": False},
            "outputSchema": {"type": "object", "properties": {
                "status": {"type": "string"}, "snapshot": {"type": "object"},
                "adapter_version": {"type": "string"},
                "model_version": {"type": ["string", "null"]},
                "data": {"type": "object"}},
                "required": ["status", "adapter_version", "model_version", "snapshot", "data"]}}


STRING = {"type": "string", "minLength": 1}
LIMIT = {"type": "integer", "minimum": 1, "maximum": 256, "default": 32}
MAX_SCENARIO_NUMBER = 1_000_000_000
SIDE_SETTINGS = {"type": "object", "properties": {
    "order": {"type": "string", "enum": ["approach", "hold", "retreat"]},
    "fire": {"type": "boolean"}, "fight": {"type": "boolean"},
    "facing": {"type": "string", "enum": ["front", "side", "rear"]},
    "ranged_attack_id": STRING,
    "collision_probability": {"type": "number", "minimum": 0, "maximum": 1},
    "firing_entities": {"type": "number", "minimum": 0, "maximum": MAX_SCENARIO_NUMBER},
    "cycle_seconds": {"type": "number", "minimum": 0.25, "maximum": MAX_SCENARIO_NUMBER},
    "first_shot_delay_seconds": {"type": "number", "minimum": 0, "maximum": MAX_SCENARIO_NUMBER},
    "projectiles_per_cycle": {"type": "number", "exclusiveMinimum": 0, "maximum": MAX_SCENARIO_NUMBER,
                              "description": "Explicit scenario interpretation of sourced projectile, volley and burst counts; compare labeled cases when counts are nontrivial, without assuming their exact engine composition."},
    "flight_seconds": {"type": "number", "minimum": 0, "maximum": MAX_SCENARIO_NUMBER,
                       "description": "Optional measured or assumed flight duration. Without it, missing/nonpositive source velocity uses an immediate-arrival firing-opportunity approximation."},
    "explosion_entities_per_collision": {"type": "number", "minimum": 0, "maximum": MAX_SCENARIO_NUMBER},
    "active_contacts": {"type": "number", "minimum": 0, "maximum": MAX_SCENARIO_NUMBER},
    "charge_duration_seconds": {"type": "number", "minimum": 0, "maximum": MAX_SCENARIO_NUMBER},
    "target_component_role": STRING,
    "assume_targetable": {"type": "boolean"},
    "assume_unit_protection_for_component": {"type": "boolean"},
    "combat_effective_fraction": {"type": "number", "minimum": 0, "maximum": 1},
}, "additionalProperties": False}
SCENARIO = {"type": "object", "description": "Conditional custom-battle assumptions; see docs/matchup-model.md. Duration is capped at 300 seconds for hosted calls.",
            "properties": {"mode": {"type": "string", "enum": ["custom_battle"]},
                           "baseline": {"type": "string", "enum": ["unmodified_ultra_rank_0"]},
                           "separation_metres": {"type": "number", "minimum": 0, "maximum": 10000},
                           "duration_seconds": {"type": "number", "exclusiveMinimum": 0, "maximum": 300},
                           "metres_per_second_per_speed_point": {"type": "number", "exclusiveMinimum": 0, "maximum": MAX_SCENARIO_NUMBER},
                           "path_length_factor": {"type": "number", "exclusiveMinimum": 0, "maximum": MAX_SCENARIO_NUMBER},
                           "terrain_speed_factor": {"type": "number", "exclusiveMinimum": 0, "maximum": MAX_SCENARIO_NUMBER},
                           "line_of_sight": {"type": "boolean"},
                           "historical_relations_apply_to_patch_9": {"type": "boolean"},
                           "barrier_damage_order": {"type": "string", "enum": ["barrier_first", "entity_cap_first"]},
                           "sides": {"type": "object", "properties": {"a": SIDE_SETTINGS,
                                                                      "b": SIDE_SETTINGS},
                                     "additionalProperties": False}}, "additionalProperties": False}
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
    _tool("resolve_effect", "Resolve a spell/activated-ability key or exact label; shared labels (normal, bound, overcast) return candidates. Optional unit restricts to linked effects.",
          {"name_or_key": STRING, "unit_key": STRING, "subculture": STRING}, ("name_or_key",)),
    _tool("get_effect", "Retrieve one spell or activated ability: costs/timing, distinct distance settings, recipients, phases, payload chains, failure branches, summons, variants and qualified unit access. Source parameters only; no damage totals, buff application or availability claim.",
          {"name_or_key": STRING, "unit_key": STRING, "subculture": STRING, "culture": STRING,
           "cursor": STRING, "limit": LIMIT, "include_provenance": {"type": "boolean"}}, ("name_or_key",)),
    _tool("get_detail", "Expand an exact packet detail reference with bounded pagination.",
          {"ref": STRING, "cursor": STRING, "limit": LIMIT}, ("ref",)),
    _tool("get_provenance", "Expand exact source record IDs returned in a packet (maximum 64 per call).",
          {"record_ids": {"type": "array", "items": STRING, "minItems": 1, "maxItems": 64}}, ("record_ids",)),
    _tool("discover_unit_fields", "Describe the unit search: row and count definitions, searchable fields with types, units, operators, null counts and scope, ambiguous terms, unsupported classifications, grammar and examples. With field, page that field's categorical values (subcultures, castes, attributes...). Call before search_units; never guess field names or category values.",
          {"field": STRING, "cursor": STRING, "limit": {"type": "integer", "minimum": 1, "maximum": 256, "default": 64}}),
    _tool("search_units", "Enumerate or filter units from the pinned snapshot: rosters by subculture, lords/heroes by caste, stat thresholds, AND/OR groups, field-to-field comparisons, sorting and mount-family grouping. Returns qualified unit keys, requested baseline values, totals with their count unit, and a cursor. Values are unmodified base stats; follow results with get_unit_combat_profile. Complete within the snapshot, not proof of complete game coverage.",
          {"where": {"type": "object", "description": "Condition {field, op, value|other_field} or group {all: [...]} / {any: [...]}; see discover_unit_fields."},
           "fields": {"type": "array", "items": STRING, "maxItems": 24, "description": "Output field ids (default caste, unit_type, mount_relation)."},
           "sort": {"type": "array", "maxItems": 3, "items": {"type": "object", "properties": {
               "field": STRING, "direction": {"type": "string", "enum": ["asc", "desc"]}},
               "required": ["field"], "additionalProperties": False}},
           "group_by": {"type": "string", "enum": ["variant", "mount_family"]},
           "limit": {"type": "integer", "minimum": 1, "maximum": 100, "default": 25},
           "cursor": STRING}),
    _tool("evaluate_single_unit_matchup", "Conditional two-unit combat projection, not a battle winner prediction. Resolve ambiguous names first; inspect assumptions, sensitivity and limitations. Missing/nonpositive source velocity uses a labeled immediate-arrival approximation. If its damage is material, rerun with flight_seconds equal to that side's returned cycle_seconds as an illustrative delayed case; report both outcomes. bounds_cross does not cover flight timing. Build labeled projectiles_per_cycle cases from nontrivial source projectile, volley and burst counts; compare multiple factors individually rather than multiplying them or claiming exact engine cadence.",
          {"unit_a": STRING, "unit_b": STRING, "subculture_a": STRING, "subculture_b": STRING,
           "scenario": SCENARIO}, ("unit_a", "unit_b")),
]
BY_NAME = {tool["name"]: tool for tool in TOOLS}


def _validate_scenario(value, rule, path):
    kind = rule["type"]
    if kind == "object":
        if not isinstance(value, dict):
            raise ValueError(f"{path} must be an object")
        properties = rule["properties"]
        if set(value) - set(properties):
            raise ValueError(f"unsupported {path} field")
        for key, item in value.items():
            _validate_scenario(item, properties[key], f"{path}.{key}")
    elif kind == "number":
        if type(value) not in (int, float) or (type(value) is float and not math.isfinite(value)):
            raise ValueError(f"{path} must be a finite number")
        if (("minimum" in rule and value < rule["minimum"]) or
                ("exclusiveMinimum" in rule and value <= rule["exclusiveMinimum"]) or
                ("maximum" in rule and value > rule["maximum"])):
            raise ValueError(f"{path} is outside the hosted range")
    elif kind == "boolean" and type(value) is not bool:
        raise ValueError(f"{path} must be boolean")
    elif kind == "string" and (not isinstance(value, str) or not value.strip()):
        raise ValueError(f"{path} must be a nonempty string")
    if "enum" in rule and value not in rule["enum"]:
        raise ValueError(f"unsupported {path}")


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
        if kind == "array" and rule["items"].get("type") == "string" and (
                not isinstance(value, list) or not rule.get("minItems", 0) <= len(value) <= rule["maxItems"]
                or any(not isinstance(item, str) or not item.strip() for item in value)):
            raise ValueError(f"{key} must contain {rule.get('minItems', 0)} to {rule['maxItems']} nonempty strings")
        if kind == "array" and not isinstance(value, list):
            raise ValueError(f"{key} must be an array")
        if kind == "object" and not isinstance(value, dict):
            raise ValueError(f"{key} must be an object")
        if "enum" in rule and value not in rule["enum"]:
            raise ValueError(f"unsupported {key}")
    if tool["name"] == "evaluate_single_unit_matchup":
        _validate_scenario(args.get("scenario", {}), SCENARIO, "scenario")


def _content(payload, is_error=False):
    result = {"content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=False, allow_nan=False)}],
              "structuredContent": payload}
    if is_error:
        result["isError"] = True
    return result


def _unit_search(queries):
    # One search helper per open snapshot keeps category lists cached across calls.
    if getattr(queries, "_unit_search", None) is None:
        queries._unit_search = UnitSearch(queries)
    return queries._unit_search


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
        elif name == "resolve_effect":
            data = queries.resolve_effect(args["name_or_key"], args.get("unit_key"), args.get("subculture"))
        elif name == "get_effect":
            data = queries.get_effect(args["name_or_key"], unit=args.get("unit_key"), subculture=args.get("subculture"),
                                      culture=args.get("culture"), cursor=args.get("cursor"), limit=args.get("limit", 32),
                                      include_provenance=args.get("include_provenance", False))
        elif name == "get_detail":
            data = queries.get_detail(args["ref"], cursor=args.get("cursor"), limit=args.get("limit", 32))
        elif name == "discover_unit_fields":
            data = _unit_search(queries).discover(args.get("field"), cursor=args.get("cursor"),
                                                limit=args.get("limit", 64))
        elif name == "search_units":
            data = _unit_search(queries).search(args.get("where"), fields=args.get("fields"), sort=args.get("sort"),
                                              group_by=args.get("group_by", "variant"),
                                              limit=args.get("limit", 25), cursor=args.get("cursor"))
        elif name == "evaluate_single_unit_matchup":
            from .combat import evaluate_matchup
            data = evaluate_matchup(queries, args["unit_a"], args["unit_b"], scenario=args.get("scenario"),
                                    subculture_a=args.get("subculture_a"), subculture_b=args.get("subculture_b"))
        else:
            data = queries.get_provenance(args["record_ids"])
        return _content({"status": "ok", "adapter_version": SERVER_VERSION,
                         "model_version": data["model_version"] if name == "evaluate_single_unit_matchup" else None,
                         "snapshot": queries.snapshot, "data": data})
    except SearchError as exc:
        return _content({"status": "invalid_query", "adapter_version": SERVER_VERSION,
                         "model_version": None, "snapshot": queries.snapshot, "data": exc.detail}, True)
    except ResolutionError as exc:
        return _content({"status": exc.result["status"], "adapter_version": SERVER_VERSION,
                         "model_version": None, "snapshot": queries.snapshot, "data": exc.result}, True)
    except (ValueError, OverflowError, KeyError, sqlite3.Error) as exc:
        return _content({"status": "error", "adapter_version": SERVER_VERSION,
                         "model_version": None, "snapshot": queries.snapshot,
                         "data": {"message": str(exc)}}, True)


def _response(message_id, *, result=None, error=None):
    response = {"jsonrpc": "2.0", "id": message_id}
    response["error" if error else "result"] = error or result
    return response


def dispatch_method(queries, method, params, message_id):
    """Shared tool dispatcher for stdio and stateless HTTP transports.

    Future calculation tools belong in TOOLS and call_tool; neither transport
    implements calculations or its own tool routing.
    """
    if method == "ping":
        return _response(message_id, result={})
    if method == "tools/list":
        return _response(message_id, result={"tools": TOOLS})
    if method == "tools/call":
        if not isinstance(params, dict) or not isinstance(params.get("name"), str) or params["name"] not in BY_NAME:
            return _response(message_id, error={"code": -32602, "message": "unknown tool"})
        try:
            result = call_tool(queries, params["name"], params.get("arguments", {}))
            return _response(message_id, result=result)
        except ValueError as exc:
            return _response(message_id, error={"code": -32602, "message": str(exc)})
    return _response(message_id, error={"code": -32601, "message": "method not found"})


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
                response = dispatch_method(queries, method, request.get("params"), message_id)
            elif not ready:
                response = _response(message_id, error={"code": -32000, "message": "initialize first"})
            else:
                response = dispatch_method(queries, method, request.get("params"), message_id)
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
