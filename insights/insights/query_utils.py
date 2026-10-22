# Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import frappe
import sqlglot as sg
from sqlglot.optimizer.scope import build_scope


def table_reference(table_exp: sg.exp.Table) -> str:
	"""A table as a SQL query names it, with its schema when the query gives one."""
	return f"{table_exp.db}.{table_exp.name}" if table_exp.db else table_exp.name


def real_table_refs(parsed: sg.Expression) -> list[sg.exp.Table]:
	"""Every table reference in a statement that names a real table.

	Excludes tables whose name is defined by a CTE in the same scope, except
	when the reference is schema-qualified (a CTE name never has a schema).
	"""
	root = build_scope(parsed)
	if root is None:
		return list(parsed.find_all(sg.exp.Table))

	from sqlglot.optimizer.scope import Scope

	# a CTE name has no schema, so a qualified reference is always a real table
	return [
		table
		for scope in root.traverse()
		for table in scope.tables
		if table.db or not isinstance(scope.sources.get(table.alias_or_name), Scope)
	]


def extract_sql_table_refs(raw_sql: str, dialect: sg.Dialect | None = None) -> list[frappe._dict]:
	"""Every distinct table reference in `raw_sql`, as a list of dicts with keys
	`name`, `db` (schema), `catalog`, `reference`.
	"""
	try:
		parsed = sg.parse_one(raw_sql, dialect=dialect)
	except Exception:
		return []

	seen_refs: set[tuple] = set()
	table_refs = []
	for table_exp in real_table_refs(parsed):
		table_name = table_exp.name
		if not table_name:
			continue
		table_ref = frappe._dict(
			name=table_name,
			db=str(table_exp.db) if table_exp.db else None,
			catalog=str(table_exp.catalog) if table_exp.catalog else None,
			reference=table_reference(table_exp),
		)
		ref_key = (table_ref.name, table_ref.db, table_ref.catalog)
		if ref_key in seen_refs:
			continue
		seen_refs.add(ref_key)
		table_refs.append(table_ref)

	return table_refs
