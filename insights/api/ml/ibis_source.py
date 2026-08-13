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

from insights.api.ml.permissions import permitted

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
    """Ibis table expression for a DocType, restricted to what the caller may read.

    Example: ``t("Sales Invoice")`` -> the ``tabSales Invoice`` table, lazy
    (no query runs until you call ``.execute()`` on the final expression),
    already carrying the current user's row and column permissions.

    The restriction lives here because this is the only way the 43 modules
    under `insights/api/ml/` and `insights/analytics/` reach the database. A
    caller that genuinely needs the unfiltered table can reach for
    `connection().table()`, which says so in the diff.

    Memoised per request on ``frappe.local``, the same way
    `insights.api.ml.permissions._rules` caches its permission lookups.
    `connection().table()` is not free: it issues an ``information_schema``
    round trip for the column list and rebuilds the ibis table node from it.
    One dashboard asks for the same handful of DocTypes over and over --
    `financial_intelligence` alone calls this 34 times for 8 distinct
    DocTypes -- and measured cold that repetition was 9.2s of a 38.4s
    compute. The expressions are immutable, so handing every caller the same
    node is safe: `.filter()` / `.select()` return new nodes and reusing one
    parent also lets ibis share its compiled sub-plans.
    """
    cache = getattr(frappe.local, "insights_ml_tables", None)
    if cache is None:
        cache = frappe.local.insights_ml_tables = {}

    key = (frappe.session.user, doctype)
    if key not in cache:
        cache[key] = permitted(connection().table(get_table_name(doctype)), doctype)
    return cache[key]


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
