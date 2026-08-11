# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""
Ibis connection to the current site's own database.

Every "intelligence" endpoint used to fetch rows with ``frappe.db.sql``, load
them into a pandas DataFrame, and crunch them in-process with numpy /
scikit-learn / statsmodels (and, briefly, Prophet). On Frappe Cloud that
crunching ran inside an RQ work-horse, and the horse's ``os.fork()``
reliably segfaulted ("waitpid returned 139 (signal 11)") -- forking a
multi-threaded process (Python's GC thread, glibc, RQ's heartbeat thread,
OpenBLAS's thread pool) is undefined behaviour per POSIX, not a bug in this
app that could be patched around. No amount of lazy importing, thread-pool
pinning, or NOFORK worker configuration changed that; the only fix is to
never run that code in a forked worker at all.

Ibis is already this app's query engine -- every external Data Source
(``insights.insights.doctype.insights_data_source_v3.connectors.*``) is
queried through it. This module hands the ML endpoints the same tool,
pointed at the site's own database instead of an external one: every
aggregate, window function, and percentile bucket below compiles to one SQL
statement and executes *inside MariaDB*. The Python process only ever
materialises the final, already-aggregated result -- typically a handful of
rows -- so there is nothing left for numpy/sklearn to vectorise and nothing
that needs a background job, a warm cache, or a fork.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import frappe
import frappe.defaults
from frappe.utils import cstr, get_table_name

if TYPE_CHECKING:
    import ibis
    import ibis.expr.types as ir


def connection() -> ibis.BaseBackend:
    """Ibis backend bound to the current site's own MariaDB database.

    Cached on ``frappe.local`` for the life of the request: connecting is a
    real TCP handshake + auth round trip, and a single dashboard request
    typically touches several tables, so paying that cost once per request
    (not once per table) matters.
    """
    if getattr(frappe.local, "insights_ml_ibis_conn", None) is None:
        import ibis

        conf = frappe.conf
        frappe.local.insights_ml_ibis_conn = ibis.mysql.connect(
            host=conf.get("db_host") or "127.0.0.1",
            port=int(conf.get("db_port") or 3306),
            user=conf.get("db_user") or conf.get("db_name"),
            password=conf.get("db_password"),
            database=conf.get("db_name"),
            charset="utf8mb4",
        )
    return frappe.local.insights_ml_ibis_conn


def t(doctype: str) -> ir.Table:
    """Ibis table expression for a DocType, by its real MariaDB table name.

    Example: ``t("Sales Invoice")`` -> the ``tabSales Invoice`` table, lazy
    (no query runs until you call ``.execute()`` on the final expression).
    """
    return connection().table(get_table_name(doctype))


def company_filter(table: ir.Table, company: str | None) -> ir.Table:
    """Apply the standard ``company`` filter used by nearly every domain
    table, skipped when no company is resolved (single-company sites, or a
    caller that intentionally wants every company)."""
    if company and "company" in table.columns:
        # Column equality returns an ibis BooleanValue expression at runtime
        # (verified: compiles to a real SQL WHERE clause) -- pyright can't
        # resolve that through dynamic `Table.__getitem__`, and infers `bool`.
        return table.filter(table["company"] == company)  # type: ignore[reportArgumentType]
    return table


def default_company() -> str | None:
    company = frappe.defaults.get_user_default("Company") or frappe.db.get_single_value(
        "Global Defaults", "default_company"
    )
    return cstr(company) or None
