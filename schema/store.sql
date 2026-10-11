PRAGMA foreign_keys = ON;
CREATE TABLE snapshot (
  id TEXT PRIMARY KEY, schema_version INTEGER NOT NULL CHECK(schema_version=4),
  source_commit TEXT NOT NULL, contract_sha256 TEXT NOT NULL,
  baseline_json TEXT NOT NULL CHECK(json_valid(baseline_json)),
  owners_json TEXT NOT NULL CHECK(json_valid(owners_json)),
  coverage_json TEXT NOT NULL CHECK(json_valid(coverage_json))
) STRICT;
CREATE TABLE source_files (
  path TEXT PRIMARY KEY, snapshot_id TEXT NOT NULL REFERENCES snapshot(id),
  sha256 TEXT NOT NULL, locked_sha256 TEXT NOT NULL, byte_count INTEGER NOT NULL,
  owner TEXT NOT NULL, input_rows INTEGER, retained_rows INTEGER,
  selection_policy TEXT NOT NULL
) STRICT;
CREATE TABLE record_provenance (
  id TEXT PRIMARY KEY, source_file TEXT NOT NULL REFERENCES source_files(path),
  logical_record INTEGER NOT NULL CHECK(logical_record>=2),
  native_key_json TEXT NOT NULL CHECK(json_valid(native_key_json)),
  source_path TEXT, source_line INTEGER, source_patch TEXT,
  retention TEXT NOT NULL CHECK(retention IN ('full','option_metadata','localization')),
  UNIQUE(source_file,logical_record)
) STRICT;
CREATE TABLE dataset_tables (
  source_file TEXT PRIMARY KEY REFERENCES source_files(path),
  table_name TEXT NOT NULL, columns_json TEXT NOT NULL CHECK(json_valid(columns_json))
) STRICT;
CREATE TABLE unit_identity (
  unit_key TEXT PRIMARY KEY, snapshot_id TEXT NOT NULL REFERENCES snapshot(id),
  namespace TEXT NOT NULL CHECK(namespace IN ('roster','external'))
) STRICT;
CREATE TABLE unit_records (
  record_id TEXT PRIMARY KEY REFERENCES record_provenance(id),
  unit_key TEXT NOT NULL REFERENCES unit_identity(unit_key)
) STRICT;
CREATE INDEX unit_records_key ON unit_records(unit_key, record_id);
CREATE TABLE ability_option_metadata (
  ability_key TEXT PRIMARY KEY,
  classification TEXT NOT NULL CHECK(classification IN ('core_passive','activated_option','unresolved')),
  requires_effect_enabling INTEGER CHECK(requires_effect_enabling IN (0,1)),
  definition_record TEXT REFERENCES record_provenance(id),
  casting_record TEXT REFERENCES record_provenance(id),
  evidence_json TEXT NOT NULL CHECK(json_valid(evidence_json))
) STRICT;
CREATE TABLE relation_edges (
  source_record TEXT NOT NULL REFERENCES record_provenance(id),
  relation TEXT NOT NULL, target_key_json TEXT NOT NULL CHECK(json_valid(target_key_json)),
  target_record TEXT REFERENCES record_provenance(id),
  status TEXT NOT NULL CHECK(status IN ('resolved','unresolved','deferred')),
  edge_ordinal INTEGER NOT NULL CHECK(edge_ordinal>=0),
  PRIMARY KEY(source_record,relation,target_key_json,edge_ordinal),
  CHECK((status='resolved' AND target_record IS NOT NULL) OR
        (status!='resolved' AND target_record IS NULL))
) STRICT;
CREATE INDEX relation_edges_reverse ON relation_edges(target_record,relation,source_record);
CREATE TABLE coverage_gaps (
  id INTEGER PRIMARY KEY, record_id TEXT REFERENCES record_provenance(id),
  kind TEXT NOT NULL, detail TEXT NOT NULL,
  UNIQUE(record_id,kind,detail)
) STRICT;
CREATE INDEX coverage_gaps_record ON coverage_gaps(record_id);
CREATE TABLE localization (
  record_id TEXT PRIMARY KEY REFERENCES record_provenance(id),
  key TEXT NOT NULL, text TEXT NOT NULL, tooltip INTEGER CHECK(tooltip IN (0,1))
) STRICT;
CREATE INDEX localization_key ON localization(key);
CREATE TABLE record_lineage (
  record_id TEXT NOT NULL REFERENCES record_provenance(id),
  lineage_record TEXT NOT NULL REFERENCES record_provenance(id),
  PRIMARY KEY(record_id,lineage_record)
) STRICT;
-- Issue #19: spells and activated abilities. Distinct linked tables; detailed
-- payloads stay in the shared native ability/payload tables, never unit rows.
CREATE TABLE effect_abilities (
  ability_key TEXT PRIMARY KEY, snapshot_id TEXT NOT NULL REFERENCES snapshot(id),
  effect_kind TEXT NOT NULL CHECK(effect_kind IN ('spell','activated_ability')),
  kind_basis TEXT NOT NULL, source_type TEXT, ability_type TEXT, name TEXT,
  definition_record TEXT NOT NULL REFERENCES record_provenance(id),
  casting_record TEXT NOT NULL REFERENCES record_provenance(id),
  keywords_json TEXT NOT NULL CHECK(json_valid(keywords_json) AND json_type(keywords_json)='array')
) STRICT;
CREATE INDEX effect_abilities_name_nocase ON effect_abilities(name COLLATE NOCASE);
CREATE TABLE effect_variants (
  ability_key TEXT NOT NULL REFERENCES effect_abilities(ability_key),
  relation TEXT NOT NULL CHECK(relation IN ('overcast_option','supersedes')),
  variant_key TEXT NOT NULL, variant_ability TEXT REFERENCES effect_abilities(ability_key),
  status TEXT NOT NULL CHECK(status IN ('resolved','not_activated','missing')),
  source_record TEXT NOT NULL REFERENCES record_provenance(id),
  PRIMARY KEY(ability_key,relation,variant_key),
  CHECK((status='resolved') = (variant_ability IS NOT NULL))
) STRICT;
CREATE INDEX effect_variants_reverse ON effect_variants(variant_key,relation,ability_key);
CREATE TABLE effect_access (
  link_record TEXT PRIMARY KEY REFERENCES record_provenance(id),
  unit_key TEXT NOT NULL REFERENCES unit_identity(unit_key),
  ability_key TEXT NOT NULL REFERENCES effect_abilities(ability_key),
  culture_key TEXT, route TEXT NOT NULL CHECK(route IN ('unit_ability_link')),
  requires_effect_enabling INTEGER CHECK(requires_effect_enabling IN (0,1)),
  qualification TEXT NOT NULL
) STRICT;
CREATE INDEX effect_access_unit ON effect_access(unit_key,ability_key);
CREATE INDEX effect_access_ability ON effect_access(ability_key,unit_key);
-- Issue #19 increment 2 (contract 4): character forms and skill access.
CREATE TABLE character_unit_forms (
  record_id TEXT PRIMARY KEY REFERENCES record_provenance(id),
  agent_subtype_key TEXT NOT NULL, form_ordinal INTEGER NOT NULL CHECK(form_ordinal>=0),
  main_unit_key TEXT NOT NULL, land_unit_key TEXT,
  via_kind TEXT NOT NULL CHECK(via_kind IN ('associated_unit_override','mount_variant')),
  unit_key TEXT REFERENCES unit_identity(unit_key),
  mapping TEXT NOT NULL CHECK(mapping IN ('roster_unit','unmapped')),
  CHECK((mapping='roster_unit') = (unit_key IS NOT NULL)),
  UNIQUE(agent_subtype_key,form_ordinal)
) STRICT;
CREATE INDEX character_unit_forms_unit ON character_unit_forms(unit_key,agent_subtype_key);
CREATE TABLE effect_character_access (
  binding_record TEXT PRIMARY KEY REFERENCES record_provenance(id),
  agent_subtype_key TEXT NOT NULL, ability_key TEXT NOT NULL,
  effect_ability TEXT REFERENCES effect_abilities(ability_key),
  role TEXT NOT NULL CHECK(role IN ('enables','enables_overcast','disables','modifies')),
  bonus_value_id TEXT NOT NULL, skill_key TEXT NOT NULL, skill_level INTEGER NOT NULL, node_set_key TEXT NOT NULL,
  status TEXT NOT NULL CHECK(status IN ('activated_effect','not_activated','missing_definition')),
  CHECK((status='activated_effect') = (effect_ability IS NOT NULL))
) STRICT;
CREATE INDEX effect_character_access_ability ON effect_character_access(ability_key,agent_subtype_key,role);
CREATE INDEX effect_character_access_character ON effect_character_access(agent_subtype_key,ability_key);
