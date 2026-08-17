# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""Row- and column-level permissions for the intelligence endpoints.

`ibis_source.t()` hands every ML endpoint a bare table. Until this module, the
43 files that import it aggregated with no permission filter of any kind:
`ml_engine.get_dashboard("financial", ...)` returned a company P&L to any
authenticated user, roles or not. The only scoping was an optional `company`
filter fed by `Global Defaults.default_company` -- a site-wide setting, not a
permission boundary.

The shape is upstream Insights' `insights_table_v3.apply_user_permissions`,
with three deliberate differences.

**No settings switch.** Upstream returns the table unfiltered unless
`Insights Settings.apply_user_permissions` is on, and that field ships as `0`.
There the switch is defensible: it governs the query builder, where an admin
points Insights at a data source they chose to expose. These endpoints have no
such story -- they read the site's own ledger, on behalf of whoever is logged
in. So the filter is unconditional. A fix that ships behind a checkbox set to
off is not a fix.

**The row filter stays lazy.** This fork's own copy
(`insights_table_v3.py:136-145`) resolves permissions by calling
`frappe.get_list(pluck="name")` and testing `t.name.isin(that_list)`: every
permitted primary key crosses into Python and back out as a literal in the SQL
text. On a table with a million permitted rows that is a million literals, per
table, per request. Here `t.name.isin(...)` takes the *unexecuted* permission
query's own `name` column, not a Python list -- one subquery, no key ever
crosses into Python. That also matters for *which* subquery shape: MariaDB
only builds an indexed temp table (its "materialization" strategy) for
`name IN (SELECT ...)`; the equivalent correlated `EXISTS`, which is what
`semi_join` compiles to, gets re-scanned per outer row instead. For a child
table permitted through a UNION ALL of every parent doctype it could belong
to, that difference is the gap between an index lookup and a multi-second
scan at dashboard scale.

**Undecidable means filter.** Upstream skips the row filter when it cannot find
a `WHERE` in the permission query, and treats a parse failure as "no WHERE" --
so a query it cannot read is a query it does not enforce. Here the burden runs
the other way: the filter is skipped only when sqlglot parses the query *and*
proves there is nothing to enforce.

Administrator is not special-cased. `frappe.get_list` already emits an
unfiltered query for a user who may read everything, so the general path is a
no-op for them -- and a bypass would mean the tests, which run as
Administrator, exercised nothing.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import frappe
import frappe.defaults
import ibis
import sqlglot as sg
from frappe.utils import cstr
from sqlglot import expressions as sg_exp

if TYPE_CHECKING:
    import ibis.expr.types as ir


def permitted(t: ir.Table, doctype: str, extra_columns: tuple[str, ...] = ()) -> ir.Table:
    """Restrict `t` to the rows and columns the current user may read.

    Fails closed: a doctype the user cannot read yields zero rows, never the
    unfiltered table.

    `extra_columns` widens the column projection below with specific
    physical columns even when the DocType's current meta does not declare
    them as fields. Frappe never drops a database column when a field is
    removed from a DocType, so a column can outlive the field that used to
    gate it -- e.g. `Lead.source` and `Quotation.source`, dropped from both
    doctypes' meta in favour of `utm_source`, but still the only place the
    real historical channel data lives on sites that never adopted UTM
    tracking. This does not weaken row-level security: the row filter below
    already ran, so `extra_columns` can only add back columns of rows the
    caller was already permitted to read.
    """
    columns, query = _resolve(doctype)

    if columns is None or query is None:
        return _empty(t)

    # Rows first: the row filter narrows on `name`, and the column projection
    # below can only remove columns. Filtering first means the two can never
    # interact.
    if not _provably_unrestricted(query):
        if "name" not in t.columns:
            frappe.throw(f"Cannot apply user permissions to `{doctype}`: it has no `name` column.")
        # `isin` against the subquery's own column (never a materialised
        # Python list -- see module docstring) reads identically to
        # `semi_join` but compiles to `name IN (SELECT ...)` instead of a
        # correlated `EXISTS`. That distinction is not cosmetic: for a child
        # table, `query` is a UNION ALL across every parent doctype it could
        # belong to (`_permission_query`), and MariaDB will only build an
        # indexed temp table for that union -- its "materialization"
        # strategy -- for the `IN` shape. The `EXISTS` shape it plans as a
        # correlated re-scan of the full union per outer row; on a
        # multi-parent child joined at dashboard scale that is millions of
        # comparisons for what should be an index lookup (measured: a single
        # tax-intelligence bucket over ~1,200 permitted Purchase Invoices
        # joined to Purchase Taxes and Charges went from a multi-second
        # correlated scan to an indexed `eq_ref`).
        t = t.filter(t["name"].isin(t.sql(query)["name"]))

    # `columns` carries fieldnames, including virtual fields that have no
    # column at all; intersecting against the real columns drops those too.
    keep = [c for c in t.columns if c in columns or c in extra_columns]
    if not keep:
        return _empty(t)
    return t.select(keep) if len(keep) != len(t.columns) else t


def _empty(t: ir.Table) -> ir.Table:
    """The table, guaranteed to yield no rows."""
    # A literal predicate is a valid filter at runtime and is the shape upstream
    # Insights uses; pyright types `ibis.literal(False)` as a bare Scalar.
    return t.filter(ibis.literal(False))  # type: ignore[reportArgumentType]


def _resolve(doctype: str) -> tuple[set[str] | None, str | None]:
    """Permitted columns and the row-permission SQL, memoised per request.

    A dashboard touches the same handful of doctypes repeatedly, and each
    resolution costs a `get_meta` plus a permission walk.
    """
    cache = getattr(frappe.local, "insights_ml_permissions", None)
    if cache is None:
        cache = frappe.local.insights_ml_permissions = {}

    key = (frappe.session.user, doctype)
    if key not in cache:
        cache[key] = (_permitted_columns(doctype), _permission_query(doctype))
    return cache[key]


def _permitted_columns(doctype: str) -> set[str] | None:
    """Columns the caller may read, or None when the doctype is off-limits.

    `get_permitted_fields` already folds in `default_fields` (so `name` always
    survives) and the permlevel rules; `optional_fields` are added back because
    they are real columns (`_assign`, `_comments`, ...) that it drops.
    """
    from frappe.model import get_permitted_fields, optional_fields

    readers = _permitted_readers(doctype)
    if readers is None:
        return None

    allowed: set[str] = set()
    for parenttype in readers:
        allowed |= {*get_permitted_fields(doctype=doctype, parenttype=parenttype), *optional_fields}
    return allowed


def _permission_query(doctype: str) -> str | None:
    """`SELECT name FROM ...` carrying the caller's row permissions, unexecuted."""
    readers = _permitted_readers(doctype)
    if readers is None:
        return None

    queries = [
        str(
            frappe.get_list(
                doctype,
                fields=["name"],
                order_by=None,
                parent_doctype=parenttype,
                run=False,
            )
        )
        for parenttype in readers
    ]
    return " UNION ALL ".join(queries)


def _permitted_readers(doctype: str) -> list[str | None] | None:
    """The parenttypes to resolve permissions through, or None if there are none.

    A normal doctype answers for itself, as `[None]`. A child table has no
    permissions of its own -- its rows belong to whichever parent owns them --
    so it answers once per parent doctype the caller can read, and the results
    union. No readable parent means no readable rows.
    """
    # `istable` is a real Meta field; pyright resolves Meta's columns dynamically.
    if not frappe.get_meta(doctype).istable:  # type: ignore[reportAttributeAccessIssue]
        return [None] if frappe.has_permission(doctype, "read") else None

    parents: list[str | None] = [p for p in _parents(doctype) if frappe.has_permission(p, "read")]
    return parents or None


def _parents(child_doctype: str) -> list[str]:
    """Doctypes carrying `child_doctype` in a Table field, standard or custom."""
    standard = frappe.get_all(
        "DocField",
        filters={
            "parenttype": "DocType",
            "fieldtype": ["in", ["Table", "Table MultiSelect"]],
            "options": child_doctype,
        },
        pluck="parent",
        distinct=True,
    )
    custom = frappe.get_all(
        "Custom Field",
        filters={
            "fieldtype": ["in", ["Table", "Table MultiSelect"]],
            "options": child_doctype,
        },
        pluck="dt",
        distinct=True,
    )
    return list(set(standard + custom))


def _provably_unrestricted(sql: str) -> bool:
    """True only when the permission query demonstrably filters nothing.

    Skipping the row filter is the one decision here that can leak, so it needs
    a proof rather than the absence of a counter-example: anything sqlglot
    cannot parse is treated as restrictive and enforced.
    """
    try:
        return sg.parse_one(sql, read="mysql").find(sg_exp.Where) is None
    except Exception:
        return False


# Every doctype each dashboard reads, derived from the collectors in
# `insights.analytics.collectors` -- `t("X")`, `frappe.get_all("X")` and any
# `tabX` in raw SQL. `test_permissions.py` re-derives this from source and
# fails if a collector starts reading something this map does not list, so a
# new data source cannot slip past the gate unnoticed.
DASHBOARD_DOCTYPES: dict[str, tuple[str, ...]] = {
    "financial": ("Account", "GL Entry", "Payment Entry", "Purchase Invoice", "Sales Invoice"),
    "sales": ("Quotation", "Sales Invoice", "Sales Invoice Item"),
    "procurement": (
        "Purchase Invoice",
        "Purchase Invoice Item",
        "Purchase Order",
        "Purchase Receipt",
        "Purchase Receipt Item",
    ),
    "inventory": (
        "Bin",
        "Delivery Note",
        "Delivery Note Item",
        "Item",
        "Item Reorder",
        "Stock Ledger Entry",
    ),
    "production": ("Job Card", "Work Order"),
    "customer": ("Customer", "Lead", "Sales Invoice"),
    "hr": (
        "Appraisal",
        "Attendance",
        "Employee",
        "Employee Checkin",
        "Job Applicant",
        "Leave Application",
        "Salary Slip",
    ),
}


def authorize_dashboard(dashboard_type: str) -> None:
    """Refuse a caller who cannot read everything the dashboard is built from.

    All, not any. A dashboard is read as one artefact: a P&L missing the half
    its reader lacks permission for still renders a Net Profit, and a number
    that is wrong for a reason invisible on screen is worse than no number.
    Reading *some* of it is also not evidence of entitlement to the rest.

    This costs access for users who could see these dashboards yesterday. They
    were seeing figures they had no permission for -- that was the defect, not
    this. The message names what is missing so it can be granted deliberately.

    Readability is asked through `_permitted_readers`, not `has_permission`
    directly, because five of these are child tables. A child table carries no
    permission rules of its own, so `has_permission("Sales Invoice Item")` is
    False for everyone but Administrator -- asking it directly denied the sales
    dashboard to a user who could read all 3,704 of the invoices behind it.
    """
    doctypes = DASHBOARD_DOCTYPES.get(dashboard_type)
    if doctypes is None:
        raise frappe.ValidationError(f"Unknown dashboard type: {dashboard_type}")

    missing = [d for d in doctypes if _permitted_readers(d) is None]
    if missing:
        raise frappe.PermissionError(
            f"Not permitted to read {', '.join(missing)}, which the {dashboard_type} dashboard is built from."
        )


def permitted_company(filters: dict | None) -> str | None:
    """The company to report on, chosen from the ones the caller may see.

    The company used to arrive as client-supplied JSON and was passed straight
    into the query; when absent it fell back to `Global Defaults`, which is a
    site-wide value and tells you nothing about who is asking. Both paths now
    end at `frappe.get_list("Company")`, which applies User Permissions.

    None means "every company this user may see" -- correct for a
    multi-company reader, and safe because the rows are filtered anyway.
    """
    allowed: list[str] = frappe.get_list("Company", pluck="name")

    requested = (filters or {}).get("company")
    if requested:
        if requested not in allowed:
            raise frappe.PermissionError(f"Not permitted to report on company {requested}.")
        return requested

    default = cstr(frappe.defaults.get_user_default("Company")) or None
    if default in allowed:
        return default
    return allowed[0] if len(allowed) == 1 else None
