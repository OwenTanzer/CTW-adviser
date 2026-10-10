"""Strict native table construction and offline read-only access."""
from __future__ import annotations

import json
from contextlib import closing
from pathlib import Path
import sqlite3

# Store schema 3 spans more than one import contract. Query packet 1.16 needs
# the native unit supplements selected by contract 2; an older schema-3 store
# cannot satisfy those lookups even when it uses the same CTW-data source pin.
SUPPORTED_CONTRACT_SHA256 = 'fd689183d941d88f021e5a750fd9eaa78ba14c35e93481001d251582d8823802'


def quote(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def convert(value: str, kind: str):
    if value == '':
        return None
    if kind == 'BOOLEAN':
        if value not in ('true', 'false'):
            raise ValueError(f'invalid boolean: {value}')
        return int(value == 'true')
    if kind == 'INTEGER':
        return int(value)
    if kind == 'REAL':
        return float(value)
    return value


def create_native_table(db, name, columns, keys, *, constraints=()):
    declarations = ['record_id TEXT PRIMARY KEY REFERENCES record_provenance(id)']
    for col in columns:
        field = quote(col['name'])
        kind = 'INTEGER' if col['type'] == 'BOOLEAN' else col['type']
        definition = f'{field} {kind}'
        if not col['nullable']:
            definition += ' NOT NULL'
        if col['type'] == 'BOOLEAN':
            definition += f' CHECK({field} IN (0,1))'
        declarations.append(definition)
    db.execute(f'CREATE TABLE {quote(name)} ({",".join([*declarations, *constraints])}) STRICT')
    # NULL remains NULL in the table; tagged JSON key serialization provides
    # source-identity uniqueness even for native blank key components.
    present = {c['name'] for c in columns}
    for key in dict.fromkeys([*keys, 'unit_key', 'base_unit_key', 'mounted_unit_key',
                              'unit_name', 'special_ability', 'phase', 'unit']):
        if key in present:
            suffix = '_nocase' if key == 'unit_name' else ''
            collate = ' COLLATE NOCASE' if key == 'unit_name' else ''
            db.execute(f'CREATE INDEX {quote(name+"_"+key+suffix)} '
                       f'ON {quote(name)} ({quote(key)}{collate})')


def open_snapshot(path: Path) -> sqlite3.Connection:
    db = sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True)
    try:
        db.execute('PRAGMA foreign_keys=ON')
        db.execute('PRAGMA query_only=ON')
        if db.execute('SELECT schema_version FROM snapshot').fetchone() != (3,):
            raise ValueError('unsupported snapshot schema or import contract; rebuild from pinned sources')
        if db.execute('SELECT contract_sha256 FROM snapshot').fetchone() != (SUPPORTED_CONTRACT_SHA256,):
            raise ValueError('unsupported snapshot schema or import contract; rebuild from pinned sources')
    except (sqlite3.Error, ValueError) as exc:
        db.close()
        if isinstance(exc, sqlite3.Error):
            raise ValueError('unsupported snapshot schema or import contract; rebuild from pinned sources') from exc
        raise
    db.row_factory = sqlite3.Row
    return db


def native_table(db, source_path):
    row = db.execute('SELECT table_name FROM dataset_tables WHERE source_file=?',
                     (source_path,)).fetchone()
    if row is None:
        raise KeyError(source_path)
    return row[0]


def inspect_snapshot(path: Path) -> dict:
    with closing(open_snapshot(path)) as db:
        return {
            'snapshot': dict(db.execute('SELECT * FROM snapshot').fetchone()),
            'roster_rows': db.execute('SELECT count(*) FROM unit_availability').fetchone()[0],
            'unit_profiles': db.execute('SELECT count(*) FROM unit_profiles').fetchone()[0],
            'source_unit_keys': db.execute('SELECT count(*) FROM unit_aliases').fetchone()[0],
            'unit_identities': dict(db.execute(
                'SELECT namespace,count(*) FROM unit_identity GROUP BY namespace').fetchall()),
            'classifications': dict(db.execute(
                'SELECT classification,count(*) FROM ability_option_metadata GROUP BY classification').fetchall()),
            'integrity': db.execute('PRAGMA integrity_check').fetchone()[0],
            'foreign_key_errors': [tuple(r) for r in db.execute('PRAGMA foreign_key_check')],
            'sources': [dict(r) for r in db.execute(
                'SELECT path,input_rows,retained_rows,selection_policy FROM source_files ORDER BY path')],
        }
