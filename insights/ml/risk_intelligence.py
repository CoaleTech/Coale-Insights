from __future__ import annotations
# Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""
Risk Intelligence & Analytics -- Ibis-native rewrite.

Was a Frankenstein's monster: a 1000-line ``BaseMLModel`` subclass that
combined pandas, numpy, scikit-learn, statsmodels, ``india_tax_intelligence``,
and an embedded Prophet forecast for cash flow. It cached every output
to Redis and shipped a "warming" placeholder when the cache was cold,
which crashed in the RQ work-horse on Frappe Cloud.

The whole thing now compiles to a dozen Ibis aggregates -- per-customer
credit metrics, aging buckets, GL-derived cash/working-capital, top-N
risk lists, a few hand-rolled forecasts computed in Python on ~24-row
monthly series -- and assembles a single JSON dict that the Vue dashboard
consumes. The compliance sub-section still calls into
``insights.ml.india_tax_intelligence`` for GSTR-1/GSTR-3B filing status
(unchanged), because the ``india_compliance`` app's GST Return Log is the
only honest source of that data on this site.

The response shape is byte-compatible with the previous one: every key
the Vue dashboard reads is preserved. Internal ``*_score`` weights are
documented inline so a finance team can audit the numbers.
"""

from datetime import datetime, timedelta

import frappe
import ibis
from frappe import _

from insights.api.ml.ibis_source import company_filter, default_company, t

# Risk-score thresholds (0-100). Same as the original class.
RISK_THRESHOLDS = {
    "low": (0, 25),
    "medium": (26, 50),
    "high": (51, 75),
    "critical": (76, 100),
}

# Weighting for the aggregate risk score. Same as the original.
WEIGHTS = {"credit": 0.30, "cashflow": 0.30, "operational": 0.25, "compliance": 0.15}

# Time window for the analysis (months back). 12 = "last year" of data.
HISTORY_MONTHS = 12


def _risk_category(score: float) -> str:
    if score <= 25:
        return "Low"
    if score <= 50:
        return "Medium"
    if score <= 75:
        return "High"
    return "Critical"


def _risk_color(category: str) -> str:
    return {"Low": "green", "Medium": "yellow", "High": "orange", "Critical": "red"}.get(
        category, "gray"
    )


def _months_ago(months: int):
    return (datetime.now() - timedelta(days=months * 30)).date()


# ── Public API ──────────────────────────────────────────────────────────────


def run_risk_intelligence(refresh: bool = False) -> dict:
    """Main entry point for the Risk Intelligence dashboard.

    ``refresh`` is accepted for API back-compat; every call recomputes
    from live SQL (the cache + background-job machinery is gone) so the
    flag is a no-op. Returns the same shape as the previous sklearn
    implementation, computed via Ibis aggregates.
    """
    try:
        company = default_company()
        base_currency = _base_currency(company)

        overview = _overview(company)
        credit_risk = _analyze_credit_risk(company)
        payables_risk = _analyze_payables_risk(company)
        cashflow_risk = _analyze_cashflow_risk(company)
        operational_risk = _analyze_operational_risk(company)
        compliance_risk = _analyze_compliance_risk(company)
        predictive_analytics = _generate_predictive_analytics(company)

        return {
            "status": "success",
            "generated_at": datetime.now().isoformat(),
            "company": company,
            "base_currency": base_currency,
            "overview": overview,
            "credit_risk": credit_risk,
            "payables_risk": payables_risk,
            "cashflow_risk": cashflow_risk,
            "operational_risk": operational_risk,
            "compliance_risk": compliance_risk,
            "predictive_analytics": predictive_analytics,
        }
    except Exception as e:
        frappe.log_error(f"Risk Intelligence failed: {e}", "ML Risk")
        return {"status": "error", "message": str(e)}


# ── Helpers ─────────────────────────────────────────────────────────────────


def _base_currency(company: str | None) -> str:
    if company:
        cur = frappe.db.get_value("Company", company, "default_currency")
        if cur:
            return cur
    return (
        frappe.db.get_single_value("Global Defaults", "default_currency") or "USD"
    )


def _days_diff_sql(date_col):
    """MariaDB DATEDIFF(CURDATE(), <col>) as an integer expression."""
    today = datetime.now().date()
    return ibis.ifelse(
        date_col.isnull(),
        ibis.null(),
        date_col.cast("date").delta(today, unit="day"),
    )


# ── Overview ────────────────────────────────────────────────────────────────


def _overview(company: str | None) -> dict:
    total_customers = _scalar_count("Customer")
    total_suppliers = _scalar_count("Supplier")
    total_items = _scalar_count("Item", filters={"is_stock_item": 1})

    credit_score = _aggregate_credit_risk(company)
    cashflow_score = _aggregate_cashflow_risk(company)
    operational_score = _aggregate_operational_risk()
    compliance_score = _aggregate_compliance_risk(company)

    aggregate_score = (
        credit_score * WEIGHTS["credit"]
        + cashflow_score * WEIGHTS["cashflow"]
        + operational_score * WEIGHTS["operational"]
        + compliance_score * WEIGHTS["compliance"]
    )

    alerts = _top_alerts(company)
    risk_matrix = _risk_matrix(credit_score, cashflow_score, operational_score, compliance_score)

    return {
        "aggregate_risk_score": round(float(aggregate_score), 1),
        "aggregate_risk_category": _risk_category(aggregate_score),
        "risk_components": {
            "credit_risk": {"score": credit_score, "category": _risk_category(credit_score)},
            "cashflow_risk": {"score": cashflow_score, "category": _risk_category(cashflow_score)},
            "operational_risk": {"score": operational_score, "category": _risk_category(operational_score)},
            "compliance_risk": {"score": compliance_score, "category": _risk_category(compliance_score)},
        },
        "alerts": alerts[:10],
        "risk_matrix": risk_matrix,
        "total_customers": int(total_customers),
        "total_suppliers": int(total_suppliers),
        "total_items": int(total_items),
    }


def _scalar_count(doctype: str, filters: dict | None = None) -> int:
    if filters:
        return int(frappe.db.count(doctype, filters=filters))
    return int(frappe.db.count(doctype))


def _top_alerts(company: str | None) -> list[dict]:
    alerts: list[dict] = []

    si = t("Sales Invoice")
    q = si.filter(si.docstatus == 1, si.outstanding_amount > 0)
    q = company_filter(q, company)
    overdue_threshold = (datetime.now() - timedelta(days=60)).date()
    q = q.filter(si.due_date < overdue_threshold)
    by_customer = (
        q.group_by(si.customer)
        .aggregate(outstanding=si.outstanding_amount.sum())
        .order_by(ibis.desc("outstanding"))
        .limit(5)
        .execute()
    )
    for r in by_customer.to_dict(orient="records"):
        cust = r.get("customer")
        if not cust:
            continue
        out = float(r.get("outstanding") or 0)
        alerts.append(
            {
                "type": "credit_risk",
                "severity": "high",
                "title": f"Overdue Customer: {cust}",
                "description": f"Outstanding: {frappe.format_value(out, {'fieldtype': 'Currency'})}",
                "action": "Review credit limit and payment terms",
            }
        )

    cash = _current_cash_position(company)
    if cash < 1_000_000:
        alerts.append(
            {
                "type": "cashflow_risk",
                "severity": "critical" if cash < 500_000 else "high",
                "title": "Low Cash Position",
                "description": f"Current cash: {frappe.format_value(cash, {'fieldtype': 'Currency'})}",
                "action": "Monitor cash flow and accelerate collections",
            }
        )

    stockouts = _stockout_count()
    if stockouts > 50:
        alerts.append(
            {
                "type": "operational_risk",
                "severity": "medium",
                "title": f"Stock Outs: {stockouts} Items",
                "description": "Multiple items out of stock",
                "action": "Review inventory reorder levels",
            }
        )

    return alerts


def _risk_matrix(
    credit_score: float, cashflow_score: float, operational_score: float, compliance_score: float
) -> list[dict]:
    """Risk register for the heatmap.

    ``probability`` is this business's real, currently-computed risk score
    for that category (the same 0-100 aggregates behind ``risk_components``)
    -- not a generic constant. ``impact`` is a static severity weight (how
    bad the event would be *if* it happened); that axis is legitimately a
    domain judgment call independent of this period's transactions, the same
    way a GRC risk register assigns severity by category. Before 2026-08-16
    both axes were hardcoded per-row constants with no query behind them;
    the two categories with no real ERPNext-derived signal for either axis
    (currency fluctuation, security breach) were dropped rather than left
    fabricated -- see TODOS.md.
    """
    total_items = _scalar_count("Item", filters={"is_stock_item": 1})
    stockout_ratio = (_stockout_count() / total_items * 100.0) if total_items else 0.0
    supplier_share = _top_supplier_share()

    risks = [
        {"name": "Major Customer Default", "probability": credit_score, "impact": 90, "category": "Credit"},
        {"name": "Cash Flow Shortage", "probability": cashflow_score, "impact": 70, "category": "Financial"},
        {"name": "Key Supplier Failure", "probability": round(supplier_share, 1), "impact": 80, "category": "Operational"},
        {"name": "GST Compliance Issue", "probability": compliance_score, "impact": 60, "category": "Compliance"},
        {"name": "Inventory Stockout", "probability": round(stockout_ratio, 1), "impact": 40, "category": "Operational"},
        {"name": "Payment Delays", "probability": credit_score, "impact": 60, "category": "Credit"},
    ]
    for r in risks:
        r["risk_score"] = round((r["probability"] * r["impact"]) / 100.0, 1)
        r["risk_category"] = _risk_category(r["risk_score"])
    return sorted(risks, key=lambda x: x["risk_score"], reverse=True)


# ── Component aggregates ─────────────────────────────────────────────────────


def _aggregate_credit_risk(company: str | None) -> float:
    si = t("Sales Invoice")
    cutoff = _months_ago(HISTORY_MONTHS)
    today = datetime.now().date()

    total_sales = si.filter(si.docstatus == 1, si.posting_date >= cutoff)
    total_sales = company_filter(total_sales, company)
    total_sales = total_sales.aggregate(v=si.grand_total.sum()).execute().iloc[0]["v"] or 0

    outstanding = si.filter(si.docstatus == 1, si.outstanding_amount > 0)
    outstanding = company_filter(outstanding, company)
    total_outstanding = outstanding.aggregate(v=si.outstanding_amount.sum()).execute().iloc[0]["v"] or 0

    overdue = outstanding.filter(si.due_date < today)
    overdue_total = overdue.aggregate(v=si.outstanding_amount.sum()).execute().iloc[0]["v"] or 0

    outstanding_ratio = (float(total_outstanding) / float(total_sales) * 100.0) if total_sales else 0.0
    overdue_ratio = (float(overdue_total) / float(total_outstanding) * 100.0) if total_outstanding else 0.0
    return round(min(100.0, outstanding_ratio * 0.6 + overdue_ratio * 0.4), 1)


def _aggregate_cashflow_risk(company: str | None) -> float:
    current_cash = _current_cash_position(company)

    pi = t("Purchase Invoice")
    cutoff_6m = _months_ago(6)
    q = pi.filter(pi.docstatus == 1, pi.posting_date >= cutoff_6m)
    q = company_filter(q, company)
    monthly = q.mutate(month=q.posting_date.truncate("M")).group_by("month").aggregate(
        monthly_expenses=pi.grand_total.sum()
    )
    df = monthly.execute()
    if df.empty:
        monthly_expenses = 0.0
    else:
        monthly_expenses = float(df["monthly_expenses"].mean())

    cash_runway = (current_cash / monthly_expenses) if monthly_expenses > 0 else 12.0

    si = t("Sales Invoice")
    si = company_filter(si.filter(si.docstatus == 1, si.outstanding_amount > 0), company)
    avg_receivables = si.aggregate(v=si.outstanding_amount.mean()).execute().iloc[0]["v"] or 0

    # Daily sales: average of daily grand_total over the last 3 months.
    # A single mean-of-mean is close enough for the DSO component.
    cutoff_90 = _months_ago(3)
    si2 = company_filter(
        t("Sales Invoice").filter(
            t("Sales Invoice").docstatus == 1, t("Sales Invoice").posting_date >= cutoff_90
        ),
        company,
    )
    avg_daily_sales = float(si2.aggregate(v=si2.grand_total.mean()).execute().iloc[0]["v"] or 0)
    dso = (float(avg_receivables) / avg_daily_sales) if avg_daily_sales else 30.0

    runway_risk = max(0.0, 100.0 - (cash_runway * 10.0))
    dso_risk = min(100.0, dso * 1.5)
    return round(runway_risk * 0.7 + dso_risk * 0.3, 1)


def _aggregate_operational_risk() -> float:
    total_items = _scalar_count("Item", filters={"is_stock_item": 1})
    if not total_items:
        return 0.0
    stockout_items = _stockout_count()
    stockout_ratio = stockout_items / total_items * 100.0

    # Supplier concentration: top supplier's share of last-12-month spend.
    top_share = _top_supplier_share()
    error_rate = _invoice_error_rate()

    return round(min(100.0, stockout_ratio * 0.4 + top_share * 0.4 + error_rate * 0.2), 1)


def _aggregate_compliance_risk(company: str | None) -> float:
    risk_factors: list[float] = []

    si = t("Sales Invoice")
    si_q = si.filter(
        si.docstatus == 1,
        (si.customer_name.isnull()) | (si.customer_name == ""),
    )
    si_q = company_filter(si_q, company)
    incomplete = int(si_q.count().execute())

    si_total_q = company_filter(
        si.filter(si.docstatus == 1), company
    )
    total_sales = int(si_total_q.count().execute())
    if total_sales:
        incomplete_ratio = incomplete / total_sales * 100.0
        risk_factors.append(incomplete_ratio)

    # GST filing: delegate to the india_tax_intelligence module's
    # data, the same way the original class did. A status the underlying
    # log does not record (no india_compliance app, or filing_status
    # never populated on this site, or the current FY has no logged
    # returns yet) is reported as moderate/unknown rather than
    # fabricated as compliant -- the previous code added nothing to
    # `risk_factors` whenever the status was "No Data" / "Not Tracked",
    # which silently scored 0 for any site whose current FY started
    # recently and had no return rows yet, contradicting the documented
    # intent. (See TODOS.md, 2026-08-17 risk_intelligence audit, bug 2.)
    try:
        from insights.ml.india_tax_intelligence.model import IndiaTaxIntelligence
        import insights.ml.india_tax_intelligence.data as india_tax_data

        tax_intel = IndiaTaxIntelligence(period="fy")
        if tax_intel.india_compliance_installed:
            fy_start = str(tax_intel.fiscal_year["year_start_date"])
            today = datetime.now().strftime("%Y-%m-%d")
            filing = india_tax_data.get_filing_compliance(tax_intel, fy_start, today)
            statuses = [filing.get("gstr1", {}).get("status"), filing.get("gstr3b", {}).get("status")]
            unknown_count = statuses.count("No Data") + statuses.count("Not Tracked")
            pending_count = statuses.count("Pending")
            # "Unknown" (no logged returns, or filing_status not populated)
            # is itself a compliance risk signal -- a finance team cannot
            # claim "compliant" when the data is absent. 25 per occurrence
            # is the same "moderate/unknown" budget the comment above
            # advertised and the `not india_compliance_installed` branch
            # already uses (30); 25 is slightly more conservative because
            # at least one half of the picture (india_compliance itself
            # being present) is known here.
            risk_factors.append(pending_count * 40.0 + unknown_count * 25.0)
        else:
            risk_factors.append(30.0)
    except Exception:
        risk_factors.append(30.0)

    if not risk_factors:
        return 0.0
    return round(sum(risk_factors) / len(risk_factors), 1)


# ── Credit risk ─────────────────────────────────────────────────────────────


def _analyze_credit_risk(company: str | None) -> dict:
    si = t("Sales Invoice")
    cutoff = _months_ago(HISTORY_MONTHS)
    today = datetime.now().date()

    # Per-customer credit scores. Computed via Ibis; bucketing and
    # categorization done in Python on the (at most 50-row) result.
    base = si.filter(si.docstatus == 1, si.posting_date >= cutoff)
    base = company_filter(base, company)
    # `today_d` is an Ibis date literal (Python `datetime.date` is opaque
    # to Ibis; wrapping in `ibis.literal().cast("date")` gives us an
    # expression the .delta() operator can be called on).
    today_d = ibis.literal(today).cast("date")
    per_customer = (
        base.group_by(si.customer)
        .aggregate(
            total_invoices=base.count(),
            total_sales=si.grand_total.sum(),
            outstanding=si.outstanding_amount.sum(),
            # In Ibis, `a.delta(b, unit="day")` returns a - b, so to get
            # "days overdue" (positive when the invoice is past due, i.e.
            # today > due_date) the order must be `today - due_date`.
            # Earlier code wrote `due_date.delta(today)` and shipped a
            # negative sign for late invoices, which the consumer code
            # then clamped to zero via `max(0.0, ...)`, silently
            # zeroing every customer's overdue component of risk_score
            # and labelling real late payers as Low risk. (See TODOS.md,
            # 2026-08-17 risk_intelligence audit, bug 1.)
            avg_overdue_days=ibis.ifelse(
                si.due_date.isnull(),
                ibis.null(),
                today_d.delta(si.due_date.cast("date"), unit="day"),
            ).mean(),
            max_overdue_days=ibis.ifelse(
                si.due_date.isnull(),
                ibis.null(),
                today_d.delta(si.due_date.cast("date"), unit="day"),
            ).max(),
        )
        .order_by(ibis.desc("outstanding"))
        .limit(50)
        .execute()
    )

    # Join to Customer for the customer_name field. Done in Python on
    # the small (<=50 row) result; the customer master is cached.
    customer_names = {
        c.name: c.customer_name
        for c in frappe.get_all(
            "Customer",
            fields=["name", "customer_name"],
            filters={"name": ["in", per_customer["customer"].dropna().tolist()]}
            if not per_customer.empty
            else {},
        )
    }

    customer_scores: list[dict] = []
    for r in per_customer.to_dict(orient="records"):
        cust = r.get("customer")
        if not cust:
            continue
        total_sales = float(r.get("total_sales") or 0)
        outstanding = float(r.get("outstanding") or 0)
        avg_overdue = float(r.get("avg_overdue_days") or 0)
        outstanding_ratio = (outstanding / total_sales) if total_sales else 0.0
        overdue_factor = max(0.0, avg_overdue) / 90.0
        risk_score = min(100.0, outstanding_ratio * 60.0 + overdue_factor * 40.0)
        customer_scores.append(
            {
                "customer": cust,
                "customer_name": customer_names.get(cust, cust),
                "total_invoices": int(r.get("total_invoices") or 0),
                "total_sales": total_sales,
                "outstanding": outstanding,
                "avg_overdue_days": round(avg_overdue, 1),
                "max_overdue_days": int(r.get("max_overdue_days") or 0),
                "risk_score": round(risk_score, 1),
                "risk_category": _risk_category(risk_score),
                "risk_color": _risk_color(_risk_category(risk_score)),
            }
        )

    # Monthly payment patterns.
    monthly_base = base.mutate(month=si.posting_date.truncate("M"))
    monthly = (
        monthly_base
        .group_by("month")
        .aggregate(
            total_invoices=monthly_base.count(),
            total_amount=si.grand_total.sum(),
            outstanding_amount=si.outstanding_amount.sum(),
            # Same sign-inversion fix as the per-customer aggregate above:
            # `today - due_date` so positive means days past due.
            avg_days_overdue=ibis.ifelse(
                si.due_date.isnull(),
                ibis.null(),
                today_d.delta(si.due_date.cast("date"), unit="day"),
            ).mean(),
        )
        .order_by("month")
        .execute()
    )
    payment_patterns: list[dict] = []
    avg_days_overdue_values: list[float] = []
    for r in monthly.to_dict(orient="records"):
        m = r.get("month")
        ado = r.get("avg_days_overdue")
        if ado is not None:
            avg_days_overdue_values.append(float(ado))
        payment_patterns.append(
            {
                "period": str(m)[:7] if m else None,
                "total_invoices": int(r.get("total_invoices") or 0),
                "total_amount": float(r.get("total_amount") or 0),
                "outstanding_amount": float(r.get("outstanding_amount") or 0),
                "avg_days_overdue": round(float(ado), 1) if ado is not None else None,
            }
        )

    # Aging analysis: bucket all open invoices by days overdue.
    aging = _aging_buckets(company)

    return {
        "customer_risk_scores": customer_scores,
        "payment_patterns": payment_patterns,
        "aging_analysis": aging,
        "total_outstanding": sum(c["outstanding"] for c in customer_scores),
        "high_risk_customers": sum(1 for c in customer_scores if c["risk_score"] > 70),
        "avg_days_overdue": round(
            sum(avg_days_overdue_values) / max(1, len(avg_days_overdue_values)), 1
        ),
    }


def _aging_buckets(company: str | None) -> list[dict]:
    """5 aging buckets, computed by Ibis. Bucketing in SQL keeps the
    result to a handful of rows; the ordering is done in Python so the
    chart reads 'Current -> 90+ Days' left-to-right."""
    si = t("Sales Invoice")
    today = datetime.now().date()
    q = si.filter(si.docstatus == 1, si.outstanding_amount > 0)
    q = company_filter(q, company)
    # `today_d`: see _analyze_credit_risk above for why `.delta()` needs an
    # Ibis date literal (not a raw Python date) and why the operand order
    # must be `today - due_date`, not `due_date - today`, to get a
    # positive "days overdue". This sibling helper had the reversed
    # order: every genuinely overdue invoice produced a *negative* delta
    # that `ibis.greatest(..., 0)` clamped to zero, landing it in the
    # "Current" bucket, while not-yet-due invoices (due_date > today,
    # legitimately positive under the old order) wrongly aged into the
    # 30/60/90+ buckets instead. Live-verified against SI25261036 (354
    # days overdue, KES 23,361 outstanding): before this fix it bucketed
    # as "Current"; after, "90+ Days". Fixed 2026-08-17.
    today_d = ibis.literal(today).cast("date")
    days_overdue = ibis.ifelse(
        si.due_date.isnull(),
        ibis.literal(0),
        ibis.greatest(today_d.delta(si.due_date.cast("date"), unit="day"), 0),
    )
    bucket = (
        ibis.cases(
            (days_overdue <= 0, "Current"),
            (days_overdue <= 30, "1-30 Days"),
            (days_overdue <= 60, "31-60 Days"),
            (days_overdue <= 90, "61-90 Days"),
            else_="90+ Days",
        )
    )
    bucketed = q.mutate(b=bucket)
    df = bucketed.group_by("b").aggregate(
        invoice_count=bucketed.count(), outstanding_amount=si.outstanding_amount.sum()
    ).execute()
    by_bucket = {r["b"]: r for r in df.to_dict(orient="records")}
    order = ["Current", "1-30 Days", "31-60 Days", "61-90 Days", "90+ Days"]
    out = []
    for name in order:
        r = by_bucket.get(name, {})
        out.append(
            {
                "aging_bucket": name,
                "invoice_count": int(r.get("invoice_count") or 0),
                "outstanding_amount": float(r.get("outstanding_amount") or 0),
            }
        )
    return out


# ── Payables (AP) ───────────────────────────────────────────────────────────


def _analyze_payables_risk(company: str | None) -> dict:
    """Payables-side mirror of `_analyze_credit_risk`: per-supplier risk
    scores, aging buckets, and an aggregate overdue-days figure for
    outstanding Purchase Invoices. Same weighting (`outstanding_ratio *
    60 + overdue_factor * 40`, capped at 100) as the receivables side, so
    the two "Risk Score" numbers stay comparable.
    """
    pi = t("Purchase Invoice")
    cutoff = _months_ago(HISTORY_MONTHS)
    today = datetime.now().date()
    today_d = ibis.literal(today).cast("date")

    base = pi.filter(pi.docstatus == 1, pi.posting_date >= cutoff)
    base = company_filter(base, company)
    per_supplier = (
        base.group_by(pi.supplier)
        .aggregate(
            total_invoices=base.count(),
            total_purchases=pi.grand_total.sum(),
            outstanding=pi.outstanding_amount.sum(),
            avg_overdue_days=ibis.ifelse(
                pi.due_date.isnull(),
                ibis.null(),
                today_d.delta(pi.due_date.cast("date"), unit="day"),
            ).mean(),
            max_overdue_days=ibis.ifelse(
                pi.due_date.isnull(),
                ibis.null(),
                today_d.delta(pi.due_date.cast("date"), unit="day"),
            ).max(),
        )
        .order_by(ibis.desc("outstanding"))
        .limit(50)
        .execute()
    )

    # Join to Supplier for the supplier_name field. Same pattern as the
    # Customer join in _analyze_credit_risk.
    supplier_names = {
        s.name: s.supplier_name
        for s in frappe.get_all(
            "Supplier",
            fields=["name", "supplier_name"],
            filters={"name": ["in", per_supplier["supplier"].dropna().tolist()]}
            if not per_supplier.empty
            else {},
        )
    }

    supplier_scores: list[dict] = []
    for r in per_supplier.to_dict(orient="records"):
        sup = r.get("supplier")
        if not sup:
            continue
        total_purchases = float(r.get("total_purchases") or 0)
        outstanding = float(r.get("outstanding") or 0)
        avg_overdue = float(r.get("avg_overdue_days") or 0)
        outstanding_ratio = (outstanding / total_purchases) if total_purchases else 0.0
        overdue_factor = max(0.0, avg_overdue) / 90.0
        risk_score = min(100.0, outstanding_ratio * 60.0 + overdue_factor * 40.0)
        supplier_scores.append(
            {
                "supplier": sup,
                "supplier_name": supplier_names.get(sup, sup),
                "total_invoices": int(r.get("total_invoices") or 0),
                "total_purchases": total_purchases,
                "outstanding": outstanding,
                "avg_overdue_days": round(avg_overdue, 1),
                "max_overdue_days": int(r.get("max_overdue_days") or 0),
                "risk_score": round(risk_score, 1),
                "risk_category": _risk_category(risk_score),
                "risk_color": _risk_color(_risk_category(risk_score)),
            }
        )

    # Aggregate avg days overdue across *all* outstanding payables (not
    # just the top-50-by-outstanding suppliers above), so a long tail of
    # small overdue bills isn't dropped from the figure.
    outstanding_pi = company_filter(pi.filter(pi.docstatus == 1, pi.outstanding_amount > 0), company)
    overdue_expr = ibis.ifelse(
        pi.due_date.isnull(),
        ibis.null(),
        today_d.delta(pi.due_date.cast("date"), unit="day"),
    )
    avg_overdue_all = outstanding_pi.mutate(days_overdue=overdue_expr).days_overdue.mean().execute()

    aging = _aging_buckets_payables(company)

    return {
        "supplier_risk_scores": supplier_scores,
        "aging_analysis": aging,
        "total_outstanding": sum(s["outstanding"] for s in supplier_scores),
        "high_risk_suppliers": sum(1 for s in supplier_scores if s["risk_score"] > 70),
        "avg_days_overdue": round(float(avg_overdue_all), 1) if avg_overdue_all is not None else 0.0,
    }


def _aging_buckets_payables(company: str | None) -> list[dict]:
    """5 aging buckets for payables (Purchase Invoice) -- mirrors
    `_aging_buckets` (receivables) including its corrected overdue-days
    sign convention (`today - due_date`, not `due_date - today`; see the
    comment on `_aging_buckets` for the bug this avoids)."""
    pi = t("Purchase Invoice")
    today = datetime.now().date()
    q = pi.filter(pi.docstatus == 1, pi.outstanding_amount > 0)
    q = company_filter(q, company)
    today_d = ibis.literal(today).cast("date")
    days_overdue = ibis.ifelse(
        pi.due_date.isnull(),
        ibis.literal(0),
        ibis.greatest(today_d.delta(pi.due_date.cast("date"), unit="day"), 0),
    )
    bucket = (
        ibis.cases(
            (days_overdue <= 0, "Current"),
            (days_overdue <= 30, "1-30 Days"),
            (days_overdue <= 60, "31-60 Days"),
            (days_overdue <= 90, "61-90 Days"),
            else_="90+ Days",
        )
    )
    bucketed = q.mutate(b=bucket)
    df = bucketed.group_by("b").aggregate(
        invoice_count=bucketed.count(), outstanding_amount=pi.outstanding_amount.sum()
    ).execute()
    by_bucket = {r["b"]: r for r in df.to_dict(orient="records")}
    order = ["Current", "1-30 Days", "31-60 Days", "61-90 Days", "90+ Days"]
    out = []
    for name in order:
        r = by_bucket.get(name, {})
        out.append(
            {
                "aging_bucket": name,
                "invoice_count": int(r.get("invoice_count") or 0),
                "outstanding_amount": float(r.get("outstanding_amount") or 0),
            }
        )
    return out


# ── Cash flow ───────────────────────────────────────────────────────────────


def _analyze_cashflow_risk(company: str | None) -> dict:
    overdue_days_trend = _overdue_days_trend(company)

    # Working capital: current_assets - current_liabilities.
    current_assets = _gl_balance_for_account_types(
        ["Receivable", "Cash", "Bank", "Stock"], company
    )
    current_liabilities = _gl_balance_for_account_types(
        ["Payable", "Tax"], company
    )
    working_capital = current_assets - current_liabilities
    wc_ratio = (current_assets / current_liabilities) if current_liabilities else 0.0

    concentration = _customer_concentration(company)
    top_customer_share = concentration[0]["revenue_share"] if concentration else 0.0

    return {
        "overdue_days_trend": overdue_days_trend,
        "current_working_capital": working_capital,
        "working_capital_ratio": round(wc_ratio, 2),
        "current_cash_position": _current_cash_position(company),
        "customer_concentration": concentration,
        "top_customer_share": top_customer_share,
        "cash_forecast": _forecast_cash_flow(company),
    }


def _overdue_days_trend(company: str | None) -> list[dict]:
    si = t("Sales Invoice")
    cutoff = _months_ago(HISTORY_MONTHS)
    today = ibis.literal(datetime.now().date()).cast("date")
    q = company_filter(
        si.filter(si.docstatus == 1, si.posting_date >= cutoff), company
    )
    # Same sign-inversion fix as the credit-risk aggregates above:
    # `today - due_date` so positive means days past due. The downstream
    # trend chart expects positive values for late-paying periods.
    days_overdue = ibis.ifelse(
        si.due_date.isnull(),
        ibis.null(),
        today.delta(si.due_date.cast("date"), unit="day"),
    )
    df = (
        q.mutate(month=si.posting_date.truncate("M"), days=days_overdue)
        .group_by("month")
        .aggregate(
            avg_days_overdue=days_overdue.mean(),
            monthly_sales=si.grand_total.sum(),
            month_end_outstanding=si.outstanding_amount.sum(),
        )
        .order_by("month")
        .execute()
    )
    out: list[dict] = []
    for r in df.to_dict(orient="records"):
        m = r.get("month")
        out.append(
            {
                "period": str(m)[:7] if m else None,
                "avg_days_overdue": round(float(r.get("avg_days_overdue") or 0), 1),
                "monthly_sales": float(r.get("monthly_sales") or 0),
                "month_end_outstanding": float(r.get("month_end_outstanding") or 0),
            }
        )
    return out


def _customer_concentration(company: str | None) -> list[dict]:
    si = t("Sales Invoice")
    cutoff = _months_ago(HISTORY_MONTHS)
    q = company_filter(
        si.filter(si.docstatus == 1, si.posting_date >= cutoff), company
    )
    total = q.aggregate(v=si.grand_total.sum()).execute().iloc[0]["v"] or 0
    by_customer = (
        q.group_by(si.customer, si.customer_name)
        .aggregate(revenue=si.grand_total.sum())
        .order_by(ibis.desc("revenue"))
        .limit(10)
        .execute()
    )
    out: list[dict] = []
    for r in by_customer.to_dict(orient="records"):
        rev = float(r.get("revenue") or 0)
        share = (rev / float(total) * 100.0) if total else 0.0
        out.append(
            {
                "customer": r.get("customer"),
                "customer_name": r.get("customer_name"),
                "revenue": rev,
                "revenue_share": round(share, 2),
            }
        )
    return out


# ── Operational risk ────────────────────────────────────────────────────────


def _analyze_operational_risk(company: str | None) -> dict:
    inventory_risks = _inventory_risks()
    supplier_performance = _supplier_performance(company)
    process_risks = {
        "invoice_error_rate": _invoice_error_rate(),
        "average_approval_time": None,  # Not measured -- workflow state isn't tracked here.
        "system_downtime_incidents": None,  # Not measured -- no system-monitoring integration.
    }

    return {
        "inventory_risks": inventory_risks,
        "supplier_performance": supplier_performance,
        "process_risks": process_risks,
        "top_inventory_risk": inventory_risks[0] if inventory_risks else None,
        "worst_supplier": max(
            supplier_performance,
            key=lambda x: x["reliability_risk_score"],
            default=None,
        ),
    }


def _inventory_risks() -> list[dict]:
    """Per-item-group inventory risk. Ibis join of Item (filtered to
    stock items) and Bin (grouped), bucketed in Python on the small
    (<=20-row) result. ``stock_value`` comes straight off ``Bin`` --
    ERPNext's stock ledger already maintains it per warehouse/item
    (``actual_qty * valuation_rate``), so no extra join is needed.
    """
    item = t("Item")
    bin_ = t("Bin")
    items = item.filter(item.is_stock_item == 1).select(item.name, item.item_group)
    bins = bin_.group_by(bin_.item_code).aggregate(
        actual_qty=bin_.actual_qty.sum(),
        stock_value=bin_.stock_value.sum(),
    )
    joined = items.left_join(bins, items.name == bins.item_code).select(
        items.name, items.item_group, bins.actual_qty, bins.stock_value
    )
    mutated = joined.mutate(stockout=joined.actual_qty.fill_null(0) <= 0)
    df = (
        mutated.group_by(mutated.item_group)
        .aggregate(
            total_items=mutated.count(),
            stockout_items=mutated.stockout.sum(),
            stock_value=mutated.stock_value.fill_null(0).sum(),
        )
        .execute()
    )
    out: list[dict] = []
    for r in df.to_dict(orient="records"):
        total = int(r.get("total_items") or 0)
        stockouts = int(r.get("stockout_items") or 0)
        ratio = (stockouts / total) if total else 0.0
        score = min(100.0, ratio * 100.0)
        out.append(
            {
                "item_group": r.get("item_group") or "Unknown",
                "total_items": total,
                "stockout_items": stockouts,
                "stock_value": float(r.get("stock_value") or 0),
                "stockout_risk_score": round(score, 1),
                "risk_category": _risk_category(score),
            }
        )
    return sorted(out, key=lambda x: x["stockout_items"], reverse=True)


def _supplier_performance(company: str | None) -> list[dict]:
    pi = t("Purchase Invoice")
    s = t("Supplier")
    cutoff = _months_ago(HISTORY_MONTHS)
    q = company_filter(pi.filter(pi.docstatus == 1, pi.posting_date >= cutoff), company)
    delay = ibis.ifelse(
        pi.due_date.isnull() | pi.posting_date.isnull(),
        ibis.null(),
        pi.posting_date.cast("date").delta(pi.due_date.cast("date"), unit="day"),
    )
    cancelled = (pi.status == "Cancelled").cast("int")
    df = (
        q.group_by(pi.supplier)
        .aggregate(
            total_orders=q.count(),
            total_value=pi.grand_total.sum(),
            avg_delay_days=delay.mean(),
            cancelled_orders=cancelled.sum(),
        )
        .order_by(ibis.desc("total_value"))
        .limit(20)
        .execute()
    )
    # Filter to total_orders > 5 (HAVING-equivalent) in Python on the small result.
    df = df[df["total_orders"] > 5]
    supplier_names = {
        r["name"]: r["supplier_name"]
        for r in frappe.get_all(
            "Supplier",
            fields=["name", "supplier_name"],
            filters={"name": ["in", df["supplier"].dropna().tolist()]}
            if not df.empty
            else {},
        )
    }
    out: list[dict] = []
    for r in df.to_dict(orient="records"):
        supp = r.get("supplier")
        if not supp:
            continue
        delay_avg = float(r.get("avg_delay_days") or 0)
        delay_factor = max(0.0, delay_avg) / 30.0
        cancel_rate = (
            float(r.get("cancelled_orders") or 0) / float(r.get("total_orders") or 1)
        )
        score = min(100.0, delay_factor * 50.0 + cancel_rate * 50.0)
        out.append(
            {
                "supplier": supp,
                "supplier_name": supplier_names.get(supp, supp),
                "total_orders": int(r.get("total_orders") or 0),
                "total_value": float(r.get("total_value") or 0),
                "avg_delay_days": round(delay_avg, 1),
                "cancelled_orders": int(r.get("cancelled_orders") or 0),
                "reliability_risk_score": round(score, 1),
                "risk_category": _risk_category(score),
            }
        )
    return out


# ── Compliance risk ─────────────────────────────────────────────────────────


def _analyze_compliance_risk(company: str | None) -> dict:
    from insights.ml.india_tax_intelligence.model import IndiaTaxIntelligence
    import insights.ml.india_tax_intelligence.data as india_tax_data

    try:
        tax_intel = IndiaTaxIntelligence(period="fy")
        fy_start = str(tax_intel.fiscal_year["year_start_date"])
        today_str = datetime.now().strftime("%Y-%m-%d")

        if tax_intel.india_compliance_installed:
            filing = india_tax_data.get_filing_compliance(tax_intel, fy_start, today_str)
            einvoice = india_tax_data.get_einvoice_status(tax_intel, fy_start, today_str)
        else:
            filing = {"gstr1": {"status": "Not Available"}, "gstr3b": {"status": "Not Available"}}
            einvoice = {"coverage_pct": None, "pending_value": 0}
    except Exception:
        filing = {"gstr1": {"status": "Not Available"}, "gstr3b": {"status": "Not Available"}}
        einvoice = {"coverage_pct": None, "pending_value": 0}

    gst_status = {
        "gstr1_status": filing.get("gstr1", {}).get("status", "No Data"),
        "gstr1_latest_period": filing.get("gstr1", {}).get("latest_period", ""),
        "gstr3b_status": filing.get("gstr3b", {}).get("status", "No Data"),
        "gstr3b_latest_period": filing.get("gstr3b", {}).get("latest_period", ""),
        "einvoice_coverage_pct": einvoice.get("coverage_pct"),
        "einvoice_pending_value": einvoice.get("pending_value", 0),
    }

    # Document completeness audit. Two table reads combined into one
    # Python result so the response shape stays a single array.
    document_audit = _document_audit(company)

    # GST/PAN registration: read from the Company master (not invented).
    gstin, pan = "", ""
    if company:
        try:
            company_doc = frappe.get_cached_doc("Company", company)
            gstin = (company_doc.get("gstin") or "").strip()
            pan = (company_doc.get("pan") or "").strip()
        except Exception:
            pass
    licenses = [
        {
            "license_type": "GST Registration",
            "reference": gstin or "Not on file",
            "status": "Registered" if gstin else "Not Registered",
            "risk_level": "Low" if gstin else "High",
        },
        {
            "license_type": "PAN",
            "reference": pan or "Not on file",
            "status": "Registered" if pan else "Not Registered",
            "risk_level": "Low" if pan else "High",
        },
    ]

    compliance_issues: list[dict] = []
    for audit in document_audit:
        if audit["total_docs"] > 0:
            rate = audit["incomplete_docs"] / audit["total_docs"] * 100.0
            if rate > 5:
                compliance_issues.append(
                    {
                        "issue": f"High incomplete {audit['document_type']} rate",
                        "severity": "Medium" if rate < 20 else "High",
                        "rate": round(rate, 2),
                    }
                )
    if gst_status["gstr1_status"] == "Pending":
        compliance_issues.append(
            {"issue": "GSTR-1 returns pending for this fiscal year", "severity": "High", "rate": None}
        )
    if gst_status["gstr3b_status"] == "Pending":
        compliance_issues.append(
            {"issue": "GSTR-3B returns pending for this fiscal year", "severity": "High", "rate": None}
        )
    if not gstin:
        compliance_issues.append(
            {"issue": "No GSTIN on file for this company", "severity": "High", "rate": None}
        )

    overall_score = min(100, len(compliance_issues) * 15)
    return {
        "gst_status": gst_status,
        "document_audit": document_audit,
        "licenses": licenses,
        "compliance_issues": compliance_issues,
        "overall_compliance_score": overall_score,
        "compliance_category": _risk_category(overall_score),
    }


def _document_audit(company: str | None) -> list[dict]:
    """Incomplete document counts for Sales Invoice and Purchase Invoice."""
    out: list[dict] = []

    si = t("Sales Invoice")
    si_q = company_filter(
        si.filter(si.docstatus == 1), company
    )
    si_total = int(si_q.count().execute())
    si_incomplete = int(
        si_q.filter((si.customer_name.isnull()) | (si.customer_name == ""))
        .count()
        .execute()
    )
    out.append(
        {
            "document_type": "Sales Invoice",
            "total_docs": si_total,
            "incomplete_docs": si_incomplete,
        }
    )

    pi = t("Purchase Invoice")
    pi_q = company_filter(pi.filter(pi.docstatus == 1), company)
    pi_total = int(pi_q.count().execute())
    pi_incomplete = int(
        pi_q.filter((pi.supplier_name.isnull()) | (pi.supplier_name == ""))
        .count()
        .execute()
    )
    out.append(
        {
            "document_type": "Purchase Invoice",
            "total_docs": pi_total,
            "incomplete_docs": pi_incomplete,
        }
    )

    return out


# ── Predictive analytics ───────────────────────────────────────────────────


def _generate_predictive_analytics(company: str | None) -> dict:
    cash_forecast = _forecast_cash_flow(company)
    revenue_forecast = _forecast_revenue(company)
    payment_risk_forecast = _predict_payment_delays(company)
    anomalies = _detect_anomalies(company)
    early_warnings = _early_warnings(cash_forecast)

    return {
        "cash_flow_forecast": cash_forecast,
        "revenue_forecast": revenue_forecast,
        "payment_risk_forecast": payment_risk_forecast,
        "anomalies": anomalies,
        "early_warnings": early_warnings,
        "forecast_confidence": None,  # No model performance tracking exists.
        "last_model_training": datetime.now().isoformat(),
    }


def _forecast_cash_flow(company: str | None) -> dict:
    """Moving-average cash-flow forecast over the next 30 days. Computed
    on the small (one row per day for ~6 months) daily series that
    Ibis pulls; no sklearn / no Prophet."""
    gle = t("GL Entry")
    a = t("Account")
    cutoff = _months_ago(6)
    a_filtered = a.filter(a.account_type.isin(["Cash", "Bank"]))
    q = gle.join(a_filtered, gle.account == a_filtered.name).filter(
        gle.is_cancelled == 0,
        gle.posting_date >= cutoff,
    )
    if company:
        q = q.filter(gle.company == company)
    df = q.select(
        posting_date=gle.posting_date,
        amount=gle.debit.fill_null(0) - gle.credit.fill_null(0),
    ).execute()
    if df.empty or len(df) < 7:
        return {
            "status": "insufficient_data",
            "message": _("Need at least 7 days of cash flow data"),
        }

    df = df.sort_values("posting_date")
    values = df["amount"].astype(float).tolist()
    dates = df["posting_date"].tolist()
    recent_avg = sum(values[-30:]) / min(30, len(values[-30:]))
    weekly_avg = sum(values[-7:]) / min(7, len(values[-7:]))
    trend = (weekly_avg - recent_avg) / recent_avg if recent_avg else 0.0

    forecast = []
    base_date = dates[-1] if dates else datetime.now().date()
    for i in range(1, 31):
        d = base_date + timedelta(days=i)
        predicted = recent_avg * (1 + trend * (i / 30.0))
        forecast.append(
            {
                "ds": d.strftime("%Y-%m-%d"),
                "yhat": round(float(predicted), 2),
                "yhat_lower": round(float(predicted * 0.85), 2),
                "yhat_upper": round(float(predicted * 1.15), 2),
            }
        )
    return {
        "status": "success",
        "forecast": forecast,
        "model_performance": {
            "method": "Moving Average",
            "periods": 30,
            "data_points": len(values),
            "trend": f"{trend * 100:.1f}%",
        },
    }


def _forecast_revenue(company: str | None) -> dict:
    """Moving-average revenue forecast. Same shape as cash forecast."""
    si = t("Sales Invoice")
    cutoff = _months_ago(6)
    q = company_filter(
        si.filter(si.docstatus == 1, si.posting_date >= cutoff), company
    )
    df = q.mutate(amount=si.grand_total.fill_null(0)).execute()
    if df.empty or len(df) < 7:
        return {
            "status": "insufficient_data",
            "message": _("Need at least 7 days of revenue data"),
        }

    df = df.sort_values("posting_date")
    values = df["grand_total"].astype(float).tolist()
    dates = df["posting_date"].tolist()
    recent_avg = sum(values[-30:]) / min(30, len(values[-30:]))
    weekly_avg = sum(values[-7:]) / min(7, len(values[-7:]))
    trend = (weekly_avg - recent_avg) / recent_avg if recent_avg else 0.0

    forecast = []
    total_forecast = 0.0
    base_date = dates[-1] if dates else datetime.now().date()
    for i in range(1, 31):
        d = base_date + timedelta(days=i)
        predicted = recent_avg * (1 + trend * (i / 30.0))
        forecast.append(
            {
                "ds": d.strftime("%Y-%m-%d"),
                "yhat": round(float(predicted), 2),
                "yhat_lower": round(float(predicted * 0.85), 2),
                "yhat_upper": round(float(predicted * 1.15), 2),
            }
        )
        total_forecast += float(predicted)
    return {
        "status": "success",
        "forecast": forecast,
        "total_forecasted_revenue": round(total_forecast, 2),
        "model_performance": {
            "method": "Moving Average",
            "data_points": len(values),
            "trend": f"{trend * 100:.1f}%",
        },
    }


def _predict_payment_delays(company: str | None) -> dict:
    """Customers whose paid invoices have a high average days-to-pay."""
    si = t("Sales Invoice")
    cutoff = _months_ago(HISTORY_MONTHS)
    q = company_filter(
        si.filter(si.docstatus == 1, si.outstanding_amount == 0, si.posting_date >= cutoff),
        company,
    )
    delay = ibis.ifelse(
        si.modified.isnull() | si.due_date.isnull(),
        ibis.null(),
        si.modified.cast("date").delta(si.due_date.cast("date"), unit="day"),
    )
    df = (
        q.group_by(si.customer)
        .aggregate(
            avg_delay=delay.mean(),
            delay_stddev=delay.std(),
            payment_count=q.count(),
        )
        .execute()
    )
    df = df[df["payment_count"] > 5]
    high_risk = []
    market_delays: list[float] = []
    for r in df.to_dict(orient="records"):
        avg_delay = r.get("avg_delay")
        if avg_delay is None:
            continue
        market_delays.append(float(avg_delay))
        if avg_delay > 30:
            score = min(100.0, (avg_delay / 90.0) * 100.0)
            high_risk.append(
                {
                    "customer": r.get("customer"),
                    "avg_delay_days": round(float(avg_delay), 1),
                    "risk_score": round(score, 1),
                    "risk_category": _risk_category(score),
                }
            )
    high_risk.sort(key=lambda x: x["risk_score"], reverse=True)
    return {
        "high_risk_customers": high_risk[:10],
        "average_market_delay": (
            round(sum(market_delays) / len(market_delays), 1) if market_delays else 0.0
        ),
    }


def _detect_anomalies(company: str | None) -> list[dict]:
    """Revenue + expense anomalies via simple 2-sigma z-score on the
    daily aggregate, computed in Python on a ~30-row series."""
    anomalies: list[dict] = []

    # Revenue anomalies
    si = t("Sales Invoice")
    cutoff = _months_ago(1)
    q = company_filter(
        si.filter(si.docstatus == 1, si.posting_date >= cutoff), company
    )
    rev_df = (
        q.mutate(d=si.posting_date)
        .group_by("d")
        .aggregate(daily_revenue=si.grand_total.sum())
        .order_by("d")
        .execute()
    )
    if not rev_df.empty:
        values = rev_df["daily_revenue"].astype(float).tolist()
        if len(values) >= 3:
            mean = sum(values) / len(values)
            std = (sum((v - mean) ** 2 for v in values) / len(values)) ** 0.5
            for d, v in zip(rev_df["d"].tolist()[-7:], values[-7:]):
                if std and abs(v - mean) > 2 * std:
                    pct = (abs(v - mean) / mean * 100.0) if mean else 0.0
                    anomalies.append(
                        {
                            "type": "revenue_anomaly",
                            "date": str(d),
                            "description": f"Revenue {v:,.0f} is {pct:.1f}% from average",
                            "severity": "medium" if abs(v - mean) < 3 * std else "high",
                        }
                    )

    # Expense anomalies
    pi = t("Purchase Invoice")
    q = company_filter(
        pi.filter(pi.docstatus == 1, pi.posting_date >= cutoff), company
    )
    exp_df = (
        q.mutate(d=pi.posting_date)
        .group_by("d")
        .aggregate(daily_expenses=pi.grand_total.sum())
        .order_by("d")
        .execute()
    )
    if not exp_df.empty:
        values = exp_df["daily_expenses"].astype(float).tolist()
        if len(values) >= 3:
            mean = sum(values) / len(values)
            std = (sum((v - mean) ** 2 for v in values) / len(values)) ** 0.5
            for d, v in zip(exp_df["d"].tolist()[-7:], values[-7:]):
                if std and abs(v - mean) > 2 * std:
                    pct = (abs(v - mean) / mean * 100.0) if mean else 0.0
                    anomalies.append(
                        {
                            "type": "expense_anomaly",
                            "date": str(d),
                            "description": f"Expenses {v:,.0f} is {pct:.1f}% from average",
                            "severity": "medium" if abs(v - mean) < 3 * std else "high",
                        }
                    )

    return anomalies[-20:]


def _early_warnings(cash_forecast: dict) -> list[dict]:
    warnings: list[dict] = []
    if cash_forecast and cash_forecast.get("status") == "success":
        forecast_list = cash_forecast.get("forecast", [])
        if forecast_list:
            future = forecast_list[-1].get("yhat", 0)
            if future < 500_000:
                warnings.append(
                    {
                        "type": "cash_flow",
                        "severity": "critical",
                        "title": "Cash Flow Warning",
                        "description": f"Forecasted cash position: {frappe.format_value(future, {'fieldtype': 'Currency'})}",
                        "timeframe": "Next 30 days",
                    }
                )
    if datetime.now().month in (12, 1, 2):
        warnings.append(
            {
                "type": "seasonal",
                "severity": "medium",
                "title": "Seasonal Risk Period",
                "description": "Holiday season may affect cash flow and collections",
                "timeframe": "Next 60 days",
            }
        )
    return warnings


# ── GL-derived balances ─────────────────────────────────────────────────────


def _gl_balance_for_account_types(account_types: list[str], company: str | None) -> float:
    """Sum of (debit - credit) for leaf accounts of the given types."""
    gle = t("GL Entry")
    a = t("Account")
    a_filtered = a.filter(a.account_type.isin(account_types), a.is_group == 0)
    q = (
        gle.join(a_filtered, gle.account == a_filtered.name)
        .filter(gle.is_cancelled == 0)
    )
    if company:
        q = q.filter(gle.company == company)
    net = gle.debit.fill_null(0) - gle.credit.fill_null(0)
    if account_types == ["Payable", "Tax"]:
        net = gle.credit.fill_null(0) - gle.debit.fill_null(0)
    val = q.aggregate(v=net.sum()).execute().iloc[0]["v"] or 0
    return float(val)


def _current_cash_position(company: str | None) -> float:
    return _gl_balance_for_account_types(["Cash", "Bank"], company)


def _stockout_count() -> int:
    """Count of stock items whose total quantity across every warehouse
    is <= 0.

    Previously an inner join of raw ``Bin`` rows to ``Item``, counting
    matched rows with ``actual_qty <= 0`` directly -- an item with empty
    stock in 3 warehouses was counted 3 times (over-count), while an item
    with no ``Bin`` row at all (never stocked) was never counted at all
    (under-count), since the inner join drops it. Bin is pre-aggregated
    per item first, then left-joined, so every stock item is counted at
    most once -- consistent with ``_inventory_risks``.
    """
    item = t("Item")
    bin_ = t("Bin")
    bins = bin_.group_by(bin_.item_code).aggregate(actual_qty=bin_.actual_qty.sum())
    joined = item.filter(item.is_stock_item == 1).left_join(bins, item.name == bins.item_code)
    count_result = joined.filter(joined.actual_qty.fill_null(0) <= 0).count().execute()
    return int(count_result)


def _top_supplier_share() -> float:
    """Top supplier's share of total purchase spend over the trailing
    ``HISTORY_MONTHS`` window, as a 0-100 percentage.

    Previously returned the raw top-supplier total with no denominator --
    a multi-hundred-thousand-currency-unit number consumed everywhere
    (``_aggregate_operational_risk``, the risk matrix) as if it were
    already a 0-100 percentage. That silently saturated operational risk
    to 100/Critical for any business with real purchase volume.
    """
    pi = t("Purchase Invoice")
    cutoff = _months_ago(HISTORY_MONTHS)
    q = pi.filter(pi.docstatus == 1, pi.posting_date >= cutoff)
    total = q.aggregate(v=pi.grand_total.sum()).execute().iloc[0]["v"] or 0
    if not total:
        return 0.0
    df = (
        q.group_by(pi.supplier)
        .aggregate(v=pi.grand_total.sum())
        .order_by(ibis.desc("v"))
        .limit(1)
        .execute()
    )
    if df.empty:
        return 0.0
    top = float(df.iloc[0]["v"] or 0)
    return round(min(100.0, top / float(total) * 100.0), 1)


def _invoice_error_rate() -> float:
    total = _scalar_count("Sales Invoice")
    cancelled = _scalar_count("Sales Invoice", filters={"docstatus": 2})
    if not total:
        return 0.0
    return cancelled / total * 100.0
