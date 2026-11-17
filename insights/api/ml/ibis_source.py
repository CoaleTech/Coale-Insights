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
import functools

import frappe
import frappe.defaults
from frappe.utils import cstr, get_table_name

from insights.api.ml.permissions import permitted

if TYPE_CHECKING:
    import ibis
    import ibis.expr.types as ir


def use_pyarrow_materialization() -> None:
    """Make every ``expr.execute()`` route through PyArrow instead of ibis's
    pandas cursor converter.

    This exists for one reason: on aarch64 Python 3.14, a mismatched set of
    pandas/numpy wheels segfaults inside ``pandas/_libs/pandas_datetime.so``
    whenever ibis converts a date/timestamp column to a pandas ``datetime64``
    array (``ibis/formats/pandas.py:convert_column``). PyArrow reads the
    cursor into Arrow arrays and hands pandas plain Python ``date``/``datetime``
    objects, so the crashing C path is never entered.

    Enabling this changes the dtype of date columns from ``datetime64`` to
    ``object``; any code that uses the pandas ``.dt`` accessor on those
    columns must be adjusted. It is therefore opt-in via the environment
    variable ``INSIGHTS_ML_PYARROW_EXECUTE=1`` and is intended as an escape
    hatch while a bench's wheels are repaired, not the default path.
    """
    import ibis.expr.types as ir

    if getattr(ir.Table.execute, "_insights_patched", False):
        return
    _original_execute = ir.Table.execute

    def _execute(self, *args, **kwargs):
        if kwargs.pop("_unsafe", False):
            return _original_execute(self, *args, **kwargs)
        # The same expression (a cash balance, a row count) is asked for by
        # several analyses in one compute. Ibis compile + round trip is ~0.5 s
        # each, so run it once per request; `.copy()` because callers mutate.
        memo = getattr(frappe.local, "insights_ml_executed", None)
        if memo is None:
            memo = frappe.local.insights_ml_executed = {}
        key = (self.op(), args, tuple(sorted(kwargs.items())))
        if key in memo:
            return memo[key].copy()
        df = self.to_pyarrow().to_pandas(timestamp_as_object=True)
        # An aggregate with no rows (SUM/COUNT(where=) over an empty window) is
        # one row of NULLs. Arrow hands a NULL number to pandas as float NaN,
        # which is truthy: ``int(v or 0)`` then raises and ``float(v or 0)``
        # leaks NaN into the payload. The cursor path returned None, which is
        # what every caller is written for.
        if len(df) == 1:
            for col in df.columns[df.isna().iloc[0] & df.dtypes.map(lambda d: d.kind in "fiu")]:
                df[col] = df[col].astype(object).where(df[col].notna(), None)
        memo[key] = df.copy()
        return df

    _execute._insights_patched = True
    ir.Table.execute = _execute
    _cache_compiled_sql()


_COMPILED_MAX = 2048
_COMPILED_TTL = 3 * 24 * 3600


def _cache_compiled_sql() -> None:
    """Memoise ``SQLBackend.compile``: in this process, then in Redis.

    Compiling an ibis expression is pure Python and the largest single cost of
    a dashboard compute (~0.2-0.5 s per query, 25-50 queries each). The same
    expressions come back -- the hourly refresh, the Refresh button, another
    user, another worker -- and ibis ops compare by value (also across fresh
    connections), so the SQL string is reusable. Redis keeps it across
    processes keyed by a digest of the printed expression (``str(expr)`` is
    ~4x cheaper than compiling it and carries every literal, so a changed
    filter or date is a different key). Parameterised and ``pretty`` compiles
    go through untouched.
    """
    import hashlib

    import ibis
    import sqlglot
    from ibis.backends.sql import SQLBackend

    if getattr(SQLBackend.compile, "_insights_patched", False):
        return
    original = SQLBackend.compile
    compiled: dict = {}
    versions = f"{ibis.__version__}/{sqlglot.__version__}"

    def compile(self, expr, /, *, limit=None, params=None, pretty=False):
        if params or pretty:
            return original(self, expr, limit=limit, params=params, pretty=pretty)
        key = (expr.op(), limit, type(self.compiler), self.dialect)
        sql = compiled.get(key)
        if sql is None:
            # Redis only for this app's own connection: an external Data
            # Source's SQL carries its own database, which the printed
            # expression does not.
            redis_key = None
            if type(self.compiler) is type(_plain_equality_compiler()):
                digest = hashlib.sha1(f"{versions}|{limit}|{expr}".encode()).hexdigest()
                redis_key = f"insights_sql:{digest}"
                sql = frappe.cache.get_value(redis_key)
            if sql is None:
                sql = original(self, expr, limit=limit)
                if redis_key:
                    frappe.cache.set_value(redis_key, sql, expires_in_sec=_COMPILED_TTL)
            if len(compiled) >= _COMPILED_MAX:
                compiled.pop(next(iter(compiled)))
            compiled[key] = sql
        return sql

    compile._insights_patched = True
    SQLBackend.compile = compile


@functools.cache
def _plain_equality_compiler():
    """MySQL compiler whose string ``==`` is a plain ``=``.

    ibis 11 compiles string equality as ``CAST(left AS BINARY) = right``
    (case-sensitive), which stops MariaDB using any index or join key: the
    gross-profit query ran 40 s instead of ~3 s on 12k-row tables. Plain ``=``
    follows the column collation, the same as Frappe's own filters.
    Applied to this app's own connection only -- external Data Sources keep
    ibis's stock compiler.
    """
    import sqlglot.expressions as sge
    from ibis.backends.sql.compilers.mysql import MySQLCompiler

    class _PlainEquality(MySQLCompiler):
        def visit_Equals(self, op, *, left, right):
            if op.left.dtype.is_string():
                return sge.EQ(this=left, expression=right)
            return super().visit_Equals(op, left=left, right=right)

    return _PlainEquality()


# Per internal temp table, not per connection; MariaDB allocates it as it fills.
_TMP_TABLE_BYTES = 256 * 1024 * 1024


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
        conn = ibis.mysql.connect(
            host=conf.get("db_host") or "127.0.0.1",
            port=int(conf.get("db_port") or 3306),
            user=conf.get("db_user") or conf.get("db_name"),
            password=conf.get("db_password"),
            database=conf.get("db_name"),
            charset="utf8mb4",
        )
        conn.compiler = _plain_equality_compiler()
        # MariaDB's "lateral derived" plan re-runs a grouped subquery once per
        # outer row; for ``with_paid_date`` that was 13 s against 0.4 s for a
        # plain materialisation of the same join. Session-scoped, this
        # connection only.
        conn.raw_sql("SET SESSION optimizer_switch='split_materialized=off'").close()
        # The cost-of-goods join materialises the whole Stock Ledger aggregate
        # (169k rows). Held in memory it needs 64-128 MB: at 64 MB and below
        # MariaDB spills it to an on-disk temp table and probes that row by
        # row, and the gross-profit fetch took 39-75 s against 20-23 s in
        # memory (gardatest, 2026-11-17). Session peak ~100 MB; per-session.
        size = _TMP_TABLE_BYTES
        conn.raw_sql(f"SET SESSION tmp_table_size={size}, max_heap_table_size={size}").close()
        conn.get_schema = _cached_get_schema(conn.get_schema, conf.get("db_name"))
        frappe.local.insights_ml_ibis_conn = conn
    return frappe.local.insights_ml_ibis_conn


_SCHEMAS: dict = {}
_SCHEMA_TTL = 300


def _cached_get_schema(get_schema, db_name):
    """``connection().table()`` asks the database to describe the table first
    (~0.4 s each under load, 7-12 DocTypes per dashboard). A schema only
    changes on migrate, so keep it for five minutes across requests."""
    import time

    def cached(name, *, catalog=None, database=None):
        key = (db_name, name, catalog, database)
        hit = _SCHEMAS.get(key)
        if hit and time.monotonic() - hit[0] < _SCHEMA_TTL:
            return hit[1]
        schema = get_schema(name, catalog=catalog, database=database)
        _SCHEMAS[key] = (time.monotonic(), schema)
        return schema

    return cached


def t(doctype: str, extra_columns: tuple[str, ...] = ()) -> ir.Table:
    """Ibis table expression for a DocType, restricted to what the caller may read.

    Example: ``t("Sales Invoice")`` -> the ``tabSales Invoice`` table, lazy
    (no query runs until you call ``.execute()`` on the final expression),
    already carrying the current user's row and column permissions.

    The restriction lives here because this is the only way the 43 modules
    under `insights/api/ml/` and `insights/analytics/` reach the database. A
    caller that genuinely needs the unfiltered table can reach for
    `connection().table()`, which says so in the diff.

    ``extra_columns`` restores specific physical columns the DocType's
    current meta no longer declares as fields -- see `permissions.permitted`
    for why that column can still exist and still be worth reading.

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

    key = (frappe.session.user, doctype, extra_columns)
    if key not in cache:
        cache[key] = permitted(
            connection().table(get_table_name(doctype)), doctype, extra_columns=extra_columns
        )
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


def dn_cost() -> ir.Table:
    """Delivery Note Item projected to just its key + valuation rate.

    Projected (not the raw table) so it can be left-joined onto a Sales
    Invoice Item expression without ibis name collisions -- the two DocTypes
    share ~15 column names (``name``, ``modified``, ``cost_center`` ...).
    Join on ``sii.dn_detail == dn_cost().dn_name`` and pass ``.dn_rate`` to
    :func:`line_cogs`.
    """
    dni = t("Delivery Note Item")
    return dni.select(dn_name=dni.name, dn_rate=dni.incoming_rate)


def sle_cost() -> ir.Table:
    """Actual booked COGS per sold line, from the Stock Ledger Entry.

    ``stock_value_difference`` is the change in inventory value each stock
    movement posts to the GL -- negative for an outgoing sale, so its
    negation is the real cost of goods sold, exactly what ERPNext's Gross
    Profit report reads (``get_buying_amount`` -> SLE ``stock_value``). This
    is the ledger truth, unlike the (repost-lagged) ``incoming_rate`` stored
    on the item row. Keyed by ``voucher_detail_no`` -- the Delivery Note Item
    row for a delivery-driven sale, else the Sales Invoice Item row -- so
    callers join on ``coalesce(sii.dn_detail, sii.name)``. Summed per line to
    net any repost corrections. A line with no stock movement (non-stock /
    drop-ship item) has no SLE; :func:`line_cogs` falls back to the stored
    rate for those (ERPNext instead estimates them via an item average rate,
    the one place the two figures can still diverge).
    """
    sle = t("Stock Ledger Entry")
    return (
        sle.filter(sle.is_cancelled == 0)
        .group_by(sle.voucher_detail_no)
        .aggregate(svd=sle.stock_value_difference.sum())
        .select(vd_name=lambda x: x.voucher_detail_no, svd=lambda x: x.svd)
    )


_LEDGER_COLUMNS = ("account", "posting_date", "debit", "credit", "company")
_LEDGER_ACCOUNT_COLUMNS = ("account_name", "account_type", "root_type", "parent_account")


def gl_ledger(company: str | None) -> ir.Table:
    """Live GL Entry rows joined to their Account, as a narrow temporary table.

    A dashboard asks the ledger twenty-odd aggregate questions, and each one
    re-scanned the 534-byte-wide GL Entry rows (0.5-1.4 s apiece under load).
    Built once per compute from the permissioned ``t()`` expressions, so the
    row filter still applies, then every question reads the ~100-byte copy.
    Period Closing Vouchers and cancelled rows are left out, as every caller
    already did. The temp table lives on this connection only; a compute that
    needs more columns (voucher_no, remarks) reads ``t("GL Entry")`` instead.
    """
    import hashlib

    cache = getattr(frappe.local, "insights_gl_ledger", None)
    if cache is None:
        cache = frappe.local.insights_gl_ledger = {}
    key = (frappe.session.user, company or "")
    if key in cache:
        return cache[key]

    gle, acc = t("GL Entry"), t("Account")
    joined = company_filter(gle.join(acc, gle["account"] == acc["name"]), company)
    joined = joined.filter(
        (joined["is_cancelled"] == 0) & (joined["voucher_type"] != "Period Closing Voucher")
    )
    narrow = joined.select(*[joined[c] for c in (*_LEDGER_COLUMNS, *_LEDGER_ACCOUNT_COLUMNS)])
    conn = connection()
    name = "_insights_gl_" + hashlib.sha1(repr(key).encode()).hexdigest()[:10]
    conn.raw_sql(f"DROP TEMPORARY TABLE IF EXISTS `{name}`").close()
    conn.raw_sql(f"CREATE TEMPORARY TABLE `{name}` AS {conn.compile(narrow)}").close()
    cache[key] = conn.table(name)
    return cache[key]


def with_paid_date(si: ir.Table) -> ir.Table:
    """Sales Invoice expression plus ``paid_date``: the posting date of its
    last submitted Payment Entry, i.e. when it was actually settled. An invoice
    closed some other way (credit note, journal) falls back to ``modified``,
    which is only an approximation -- it moves on any later edit and ran about
    9 days after the real payment on this site's closed invoices.
    """
    import ibis

    per, pe = t("Payment Entry Reference"), t("Payment Entry")
    refs = per.filter(per.reference_doctype == "Sales Invoice").select(invoice=per.reference_name, pe_name=per.parent)
    pes = pe.filter(pe.docstatus == 1).select(pe_name=pe.name, pay_date=pe.posting_date)
    paid = refs.join(pes, "pe_name").group_by("invoice").aggregate(paid_on=lambda x: x.pay_date.max())
    joined = si.left_join(paid, si.name == paid.invoice)
    return joined.mutate(paid_date=ibis.coalesce(joined.paid_on.cast("date"), joined.modified.cast("date")))


def line_cogs(sii: ir.Table, dn_rate: ir.Column, sle_svd: ir.Column | None = None) -> ir.Column:
    """Effective per-line cost of goods sold for a Sales Invoice Item.

    When ``sle_svd`` (the summed Stock Ledger ``stock_value_difference`` from
    :func:`sle_cost`, left-joined by the caller) is supplied, the actual
    booked cost ``-sle_svd`` is used -- the ledger truth ERPNext's Gross
    Profit report reports on. Lines with no stock movement (no SLE) fall back
    to the stored rate below.

    The stored-rate fallback: ERPNext books COGS on whichever document runs
    ``update_stock``. A Sales Invoice raised against a Delivery Note is forced
    to ``update_stock = 0`` (``sales_invoice.py``: "stock cannot be updated
    again"), so the invoice books only receivable + income and the Sales
    Invoice Item's ``incoming_rate`` stays 0 until Repost Item Valuation
    back-writes it -- the real cost is booked on the Delivery Note. Prefer the
    (possibly reposted) SII rate; fall back to the linked Delivery Note Item
    rate (``sii.dn_detail`` -> DN Item ``name``). Callers left-join
    :func:`dn_cost` and pass its ``dn_rate`` column here.
    """
    import ibis

    # incoming_rate / DN rate are per STOCK uom: multiply by stock_qty, not the
    # selling-uom qty (a line sold as 88 Tonnes at 5.5/kg cost 484, not 484,000).
    stored = sii.stock_qty * ibis.coalesce(sii.incoming_rate.nullif(0), dn_rate, 0)
    if sle_svd is None:
        return stored
    return ibis.coalesce(-sle_svd, stored)


def cached_gp_lines(
    start,  # date | datetime | None  — same window as the calling compute
    end,    # date | datetime | None
    company: str | None,
    include_returns: bool = False,
) -> "pd.DataFrame":
    """Per-Sales-Invoice-Item row with revenue, cost, and period columns.

    Materialises the ``Sales Invoice × Sales Invoice Item × Delivery Note
    Item × Stock Ledger Entry`` join exactly ONCE per (user, company) per
    request -- over the whole history -- and slices the window in pandas. A
    dashboard asks for many windows (every month of a trend, each fiscal
    year); one query per window cost ~2 s each in ibis compile alone.

    The cache lives only on ``frappe.local`` -- it resets automatically at the
    end of every request and never leaks across users or concurrent sessions.

    ``include_returns=True`` nets Sales Return credit notes (negative revenue
    and cost) like ERPNext's Gross Profit report; callers that join the frame
    to non-return invoice revenue keep the default False.

    ponytail: whole-history fetch; if one company's invoice lines reach
    millions, push the window back into SQL.
    """
    def _day(v):
        return v.date() if hasattr(v, "date") and callable(v.date) else v

    df = _gp_lines_all(company)
    if not include_returns:
        df = df[df["is_return"] == 0]
    if start is not None:
        df = df[df["posting_date"] >= _day(start)]
    if end is not None:
        df = df[df["posting_date"] <= _day(end)]
    return df.copy()


def _gp_lines_all(company: str | None) -> "pd.DataFrame":
    import pandas as pd

    company = company or default_company()
    key = (frappe.session.user, company or "")
    cache = getattr(frappe.local, "insights_gp_line_cache", None)
    if cache is None:
        cache = frappe.local.insights_gp_line_cache = {}
    if key in cache:
        return cache[key]

    import ibis as _ibis

    _si = company_filter(t("Sales Invoice"), company).filter(
        t("Sales Invoice").docstatus == 1
    )

    _sii = t("Sales Invoice Item")
    _dn = dn_cost()
    _sle = sle_cost()
    _svd_key = _ibis.coalesce(_sii.dn_detail.nullif(""), _sii.name)

    df: pd.DataFrame = (
        _si.inner_join(_sii, _sii.parent == _si.name)
        .left_join(_dn, _sii.dn_detail == _dn.dn_name)
        .left_join(_sle, _svd_key == _sle.vd_name)
        .select(
            parent=_si.name,
            posting_date=_si.posting_date,
            is_return=_si.is_return,
            customer=_si.customer,
            territory=_si.territory,
            base_net_total=_si.base_net_total.cast("float64"),
            item_code=_sii.item_code,
            item_name=_sii.item_name,
            item_group=_sii.item_group,
            base_net_amount=_sii.base_net_amount.cast("float64"),
            qty=_sii.qty.cast("float64"),
            stock_qty=_sii.stock_qty.cast("float64"),
            incoming_rate=_sii.incoming_rate.cast("float64"),
            dn_rate=_dn.dn_rate.cast("float64"),
            svd=_sle.svd.cast("float64"),
        )
        .execute()
    )

    # Numeric coercion (MariaDB DECIMAL → float; nulls stay as NaN for cost logic).
    for _col in ("base_net_amount", "qty", "stock_qty", "incoming_rate", "base_net_total"):
        df[_col] = df[_col].astype(float)
    df["dn_rate"] = pd.to_numeric(df["dn_rate"], errors="coerce")
    df["svd"] = pd.to_numeric(df["svd"], errors="coerce")

    # Normalise posting_date to plain Python date (PyArrow path returns date,
    # normal path returns datetime64 -- comparisons to date objects must agree).
    # `.astype(object)`: on an empty frame apply() keeps datetime64, which then
    # refuses `>= date` (an empty window, e.g. this month before any invoice).
    df["posting_date"] = df["posting_date"].apply(
        lambda d: d.date() if hasattr(d, "date") and callable(d.date) else d
    ).astype(object)

    # line_cogs: -svd when the stock ledger booked it, else stock_qty * coalesce(rate, 0).
    # Mirrors ibis_source.line_cogs() exactly.
    _rate = df["incoming_rate"].where(df["incoming_rate"] != 0, df["dn_rate"]).fillna(0)
    _stored = df["stock_qty"] * _rate
    df["line_cogs"] = (-df["svd"]).where(df["svd"].notna(), _stored)
    df["gross_profit"] = df["base_net_amount"] - df["line_cogs"]

    # Period columns for GROUP-BY callers.
    df["period"] = df["posting_date"].apply(
        lambda d: d.strftime("%Y-%m") if hasattr(d, "strftime") else str(d)[:7]
    )
    df["year_week"] = df["posting_date"].apply(
        lambda d: (
            f"{d.isocalendar()[0]}-W{d.isocalendar()[1]:02d}"
            if hasattr(d, "isocalendar") else ""
        )
    )

    # Item group: normalise blank to "Uncategorized" for consistent grouping.
    df["item_group"] = df["item_group"].fillna("").replace("", "Uncategorized")

    cache[key] = df
    return df
