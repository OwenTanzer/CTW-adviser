"""Offline verification of the explicit CTW-data serving input contract."""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
from pathlib import Path
import re
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[1]


def fingerprint(data: bytes) -> dict:
    return {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def text_variants(data: bytes) -> list[bytes]:
    text = data.decode("utf-8", errors="strict")
    if re.search(r"\r(?!\n)", text):
        raise ValueError("bare CR is not an approved newline representation")
    lf = text.replace("\r\n", "\n")
    return list(dict.fromkeys([data, lf.encode(), lf.replace("\n", "\r\n").encode()]))


def matches(data: bytes, expected: dict) -> bool:
    return any(fingerprint(b) == {"bytes": expected["bytes"], "sha256": expected["sha256"]}
               for b in text_variants(data))


def safe_path(root: Path, relative: str) -> Path:
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError(f"path escapes source directory: {relative}")
    return path


def read_rows(path: Path, spec: dict) -> list[dict]:
    with path.open(encoding="utf-8", newline="") as stream:
        reader = csv.reader(stream, delimiter=spec.get("delimiter", ","), strict=True)
        header = next(reader)
        if header != [c["name"] for c in spec["columns"]]:
            raise ValueError(f"{path.name}: header drift")
        rows = []
        seen = set()
        for logical_row, row in enumerate(reader, 2):
            if spec.get("rpfm_metadata") and row and row[0].startswith("#"):
                continue
            if len(row) != len(header):
                raise ValueError(f"{path.name}:{logical_row}: row width")
            record = dict(zip(header, row))
            for col, value in zip(spec["columns"], row):
                if value == "":
                    if not col["nullable"]:
                        raise ValueError(f"{path.name}:{logical_row}: blank {col['name']}")
                    continue
                kind = col["type"]
                if kind == "BOOLEAN" and value not in ("true", "false"):
                    raise ValueError(f"{path.name}:{logical_row}: invalid boolean {col['name']}")
                if kind == "INTEGER" and not re.fullmatch(r"[+-]?\d+", value):
                    raise ValueError(f"{path.name}:{logical_row}: invalid integer {col['name']}")
                if kind == "REAL" and not math.isfinite(float(value)):
                    raise ValueError(f"{path.name}:{logical_row}: nonfinite {col['name']}")
            if spec.get("keys"):
                # Blank native key components remain part of the identity; no coalescing.
                key = tuple(record[k] for k in spec["keys"])
                if key in seen:
                    raise ValueError(f"{path.name}:{logical_row}: duplicate key {key}")
                seen.add(key)
            rows.append(record)
    if len(rows) != spec["expected_rows"]:
        raise ValueError(f"{path.name}: expected {spec['expected_rows']} rows, found {len(rows)}")
    return rows


def verify(root: Path, lock: dict, contract: dict) -> dict:
    errors = []
    if sys.version_info < (3, 11) or sqlite3.sqlite_version_info < (3, 37):
        errors.append("Python 3.11+ and SQLite 3.37+ required")
    if lock["contract_sha256"] != hashlib.sha256(
            json.dumps(contract, sort_keys=True, separators=(",", ":")).encode()).hexdigest():
        errors.append("import contract differs from locked contract")
    for entry in lock["files"]:
        try:
            data = safe_path(root, entry["path"]).read_bytes()
            if not matches(data, entry):
                raise ValueError("locked fingerprint mismatch")
            for upstream in entry.get("upstream_fingerprints", []):
                if not matches(data, upstream):
                    raise ValueError(f"upstream fingerprint mismatch: {upstream['authority']}")
        except (OSError, ValueError) as exc:
            errors.append(f"{entry['path']}: {exc}")
    # Fail closed before interpreting any changed metadata or data.
    if errors:
        return {"status": "failed", "errors": errors}
    for gate in contract["metadata_gates"]:
        try:
            value = json.loads(safe_path(root, gate["path"]).read_text())
            for key in gate["keys"]:
                value = value[key]
            if value != gate["equals"]:
                errors.append(f"metadata gate failed: {gate}")
        except (KeyError, TypeError, ValueError) as exc:
            errors.append(f"metadata gate unreadable: {gate['path']}: {exc}")
    tables = {}
    for spec in contract["datasets"]:
        try:
            resolved = dict(spec)
            if "columns_ref" in spec:
                resolved["columns"] = contract["column_schemas"][spec["columns_ref"]]
            tables[spec["path"]] = read_rows(safe_path(root, spec["path"]), resolved)
        except (ValueError, OSError, StopIteration, csv.Error) as exc:
            errors.append(f"{spec['path']}: {exc}")
    relation_reports = []
    for edge in contract["joins"]:
        if edge["source"] not in tables or edge["target"] not in tables:
            continue
        target = {tuple(r[c] for c in edge["target_columns"])
                  for r in tables[edge["target"]]}
        missing = sorted({tuple(r[c] for c in edge["source_columns"])
                          for r in tables[edge["source"]]
                          if all(r[c] != "" for c in edge["source_columns"])
                          and tuple(r[c] for c in edge["source_columns"]) not in target})
        relation_reports.append({"name": edge["name"], "unresolved_count": len(missing),
                                 "policy": edge["unresolved_policy"], "unresolved_keys": missing})
        if missing and edge["unresolved_policy"] == "reject":
            errors.append(f"unresolved required join: {edge['name']}")
    roster_specs = [s for s in contract["datasets"] if s["role"] == "roster"]
    roster_rows = sum(len(tables.get(s["path"], [])) for s in roster_specs)
    unique_units = {r["unit_key"] for s in roster_specs for r in tables.get(s["path"], [])}
    for spec in contract["datasets"]:
        if spec["role"] == "unit_relation":
            external = {r["unit_key"] for r in tables.get(spec["path"], [])} - unique_units
            if external:
                errors.append(f"{spec['path']}: non-roster unit relations {sorted(external)}")
    return {"status": "failed" if errors else "passed", "errors": errors,
            "source_commit": lock["source_commit"], "files_verified": len(lock["files"]),
            "datasets_verified": len(tables), "roster_files": len(roster_specs),
            "roster_rows": roster_rows, "distinct_unit_keys": len(unique_units),
            "relations": relation_reports,
            "coverage_boundary": contract["coverage_boundary"]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ctw-root", required=True, type=Path)
    args = parser.parse_args()
    try:
        lock = json.loads((ROOT / "source_lock.json").read_text())
        contract = json.loads((ROOT / "schema/import_contract.json").read_text())
        result = verify(args.ctw_root, lock, contract)
    except (OSError, ValueError, KeyError) as exc:
        result = {"status": "failed", "errors": [str(exc)]}
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
