import os

import frappe

from insights.insights.doctype.insights_data_source_v3.data_warehouse import (
	get_parquet_filepath,
)
from insights.insights.doctype.insights_table_v3.insights_table_v3 import get_table_name


def execute():
	"""
	Postgres data sources used to qualify every table name with its schema
	("public.tabSales Invoice") even when only one schema was configured. The prefix
	leaked into the UI and broke the table -> doctype mapping for frappe databases, so
	executing any query against a postgres Site DB failed with a DoesNotExistError.

	Table names are now only qualified when the data source spans several schemas. This
	patch strips the redundant prefix from everything that stored it.
	"""
	sources = frappe.get_all(
		"Insights Data Source v3",
		filters={"database_type": "PostgreSQL"},
		fields=["name", "schema"],
	)

	for source in sources:
		schemas = [s.strip() for s in (source.schema or "").split(",") if s.strip()] or ["public"]
		if len(schemas) > 1:
			# names are still qualified for multi-schema sources
			continue

		try:
			unqualify_source(source, f"{schemas[0]}.")
			frappe.db.commit()
		except Exception:
			frappe.db.rollback()
			frappe.log_error(title=f"Failed to strip schema prefix for {source.name}")


def unqualify_source(source, prefix):
	renames = rename_tables(source.name, prefix)
	if not renames:
		return

	update_queries(source.name, renames)
	update_query_references(source.name, renames)
	update_table_links(source.name, renames)


def rename_tables(data_source, prefix) -> dict[str, str]:
	"""Strip `prefix` from the stored `Insights Table v3` records. Returns {old: new}."""
	rows = frappe.get_all(
		"Insights Table v3",
		filters={"data_source": data_source, "table": ["like", f"{prefix}%"]},
		fields=["name", "table", "label", "stored"],
	)

	renames = {}
	for row in rows:
		new_table = row.table[len(prefix):]
		new_name = get_table_name(data_source, new_table)

		if frappe.db.exists("Insights Table v3", new_name):
			# an unqualified record already exists — drop the duplicate
			discard_table(data_source, row)
			renames[row.table] = new_table
			continue

		frappe.db.set_value(
			"Insights Table v3",
			row.name,
			{
				"name": new_name,
				"table": new_table,
				"label": row.label[len(prefix):] if row.label.startswith(prefix) else row.label,
			},
			update_modified=False,
		)
		frappe.db.set_value(
			"Insights Resource Permission",
			{"resource_type": "Insights Table v3", "resource_name": row.name},
			"resource_name",
			new_name,
			update_modified=False,
		)

		if row.stored and not rename_parquet_file(data_source, row.table, new_table):
			# the imported data can no longer be found under the new name — let it re-import
			frappe.db.set_value("Insights Table v3", new_name, "stored", 0, update_modified=False)

		renames[row.table] = new_table

	return renames


def discard_table(data_source, row):
	"""Delete a qualified record whose unqualified counterpart already exists."""
	if row.stored:
		old_path = get_parquet_filepath(data_source, row.table)
		if os.path.exists(old_path):
			try:
				os.remove(old_path)
			except Exception:
				pass

	frappe.db.delete(
		"Insights Resource Permission",
		{"resource_type": "Insights Table v3", "resource_name": row.name},
	)
	frappe.delete_doc("Insights Table v3", row.name, force=True, ignore_permissions=True)


def rename_parquet_file(data_source, old_table, new_table) -> bool:
	"""Rename the parquet file for a warehouse-stored table. Returns True on success."""
	old_path = get_parquet_filepath(data_source, old_table)
	new_path = get_parquet_filepath(data_source, new_table)
	if not os.path.exists(old_path):
		return False
	try:
		os.rename(old_path, new_path)
		return True
	except Exception:
		return False


def update_queries(data_source, renames):
	"""Rewrite the table names referenced by the source/join/union operations of every query."""
	queries = frappe.get_all(
		"Insights Query v3",
		filters={"operations": ["like", "%table_name%"]},
		fields=["name", "operations"],
	)

	for query in queries:
		operations = frappe.parse_json(query.operations)
		if not operations:
			continue

		if not rewrite_table_names(operations, data_source, renames):
			continue

		frappe.db.set_value(
			"Insights Query v3",
			query.name,
			"operations",
			frappe.as_json(operations),
			update_modified=False,
		)


def rewrite_table_names(node, data_source, renames) -> bool:
	"""Recursively rename every {data_source, table_name} reference. Returns True if changed."""
	changed = False

	if isinstance(node, list):
		for item in node:
			changed = rewrite_table_names(item, data_source, renames) or changed
		return changed

	if not isinstance(node, dict):
		return False

	if node.get("data_source") == data_source and node.get("table_name") in renames:
		node["table_name"] = renames[node["table_name"]]
		changed = True

	for value in node.values():
		changed = rewrite_table_names(value, data_source, renames) or changed

	return changed


def update_query_references(data_source, renames):
	for old_table, new_table in renames.items():
		frappe.db.set_value(
			"Insights Query Reference",
			{"data_source": data_source, "table_name": old_table},
			"table_name",
			new_table,
			update_modified=False,
		)


def update_table_links(data_source, renames):
	"""Rename the tables a link points at."""
	for old_table, new_table in renames.items():
		for field in ("left_table", "right_table"):
			frappe.db.set_value(
				"Insights Table Link v3",
				{"data_source": data_source, field: old_table},
				field,
				new_table,
				update_modified=False,
			)
