# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""Every raw SQL query in the ML layer must still match the live schema.

The ML layer runs ~250 hand-written aggregate queries against ERPNext tables
instead of `frappe.qb`. That is a defensible choice -- these are multi-join
aggregates the ORM cannot express -- but it forfeits the one thing the query
builder gives you for free: a column that gets renamed or dropped upstream
fails at *runtime*, inside a background job, as a zero on a dashboard rather
than an error anyone sees.

This test closes that gap without rewriting a single query. It hands each
query to the database's own parser via `PREPARE`, which resolves every table
and column but executes nothing. An ERPNext upgrade that moves a column now
fails here, loudly, naming the file and line.

It found `Work Order.qty_completed` (correct name: `produced_qty`) and
`Work Order.qty_to_manufacture` (correct name: `qty`) on its first run.
"""

import ast
import os
import re
import unittest

import frappe

APP_ROOT = frappe.get_app_path("insights")
SCANNED_SUBDIRS = ("ml", "api/ml")


def _sql_literals():
	"""Yield (relative_path, lineno, query_text) for every `frappe.db.sql` call."""
	for sub in SCANNED_SUBDIRS:
		for root, _dirs, files in os.walk(os.path.join(APP_ROOT, sub)):
			if "__pycache__" in root:
				continue
			for filename in sorted(files):
				if not filename.endswith(".py"):
					continue
				path = os.path.join(root, filename)
				try:
					tree = ast.parse(open(path, encoding="utf8", errors="replace").read())
				except SyntaxError:
					continue
				for node in ast.walk(tree):
					if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
						continue
					if node.func.attr not in ("sql", "sql_list") or not node.args:
						continue
					text = _query_text(node.args[0])
					if text and "tab" in text:
						yield os.path.relpath(path, APP_ROOT), node.lineno, text


def _query_text(arg):
	"""The literal SQL, with interpolated fragments reduced to a marker."""
	if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
		return arg.value
	if isinstance(arg, ast.JoinedStr):
		return "".join(
			str(v.value) if isinstance(v, ast.Constant) else "{H}" for v in arg.values
		)
	return None


def _normalize(query: str) -> str:
	"""Make a query parseable while preserving every table and column reference.

	An interpolated fragment stands in for SQL we cannot see, so it is replaced
	by the simplest construct that is valid *in that position* -- which differs
	between an IN list, a parenthesised predicate, a select-list expression and
	a trailing WHERE clause.
	"""
	query = re.sub(r"%\((\w+)\)s", "%s", query)
	query = query.replace("%%", "\x00")  # protect an escaped literal percent
	query = re.sub(r"(?i)\bIN\s*\(\s*\{H\}\s*\)", "IN (%s)", query)
	query = re.sub(r"\(\s*\{H\}\s*\)", "(1=1)", query)
	query = re.sub(r"(?i)(SELECT|,)\s*\{H\}", r"\1 NULL", query)
	query = re.sub(r"(?i)\bWHERE\s*\{H\}", "WHERE 1=1", query)
	query = re.sub(r"\{H\}", " IS NOT NULL ", query)
	query = re.sub(r"(?i)\bIN\s*%s", "IN (%s)", query)
	return query.replace("%s", "?").replace("\x00", "%").strip().rstrip(";")


class TestSqlSchemaContract(unittest.TestCase):
	def test_every_ml_query_matches_the_live_schema(self):
		checked = 0
		failures = []

		for rel_path, lineno, raw in _sql_literals():
			query = _normalize(raw)
			if not query.lower().lstrip().startswith(("select", "with")):
				continue
			checked += 1
			try:
				frappe.db.sql("PREPARE _schema_guard FROM %s", (query,))
				frappe.db.sql("DEALLOCATE PREPARE _schema_guard")
			except Exception as e:
				failures.append(f"{rel_path}:{lineno}\n    {str(e).splitlines()[0][:200]}")

		self.assertGreater(checked, 200, "query discovery broke -- expected 200+ SELECTs")
		self.assertEqual(
			failures,
			[],
			f"{len(failures)} of {checked} ML queries no longer match the schema:\n\n"
			+ "\n\n".join(failures),
		)
