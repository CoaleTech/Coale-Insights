from __future__ import annotations

# Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""
Procurement Intelligence — Ibis rewrite.

Same rationale as ``inventory_intelligence.py``: every metric is one or
two SQL aggregates computed inside MariaDB. No pandas / scikit-learn /
statsmodels. The Python process only touches the final handful of
aggregated rows, so there is nothing to vectorise and no fork to crash.

Conventions shared by every section:

* Window: ``date_filter`` (``insights.api.ml.utils.parse_date_filter``),
  resolved once in ``__init__``; ``None`` start means all history. Sections
  that describe *current state* (open POs, overdue invoices, payment
  exposure) and the forecast history (fixed 24 months) ignore it.
* Money is BASE currency (``base_*`` columns; invoice outstanding x
  ``conversion_rate``). Item prices are per stock UOM
  (``base_rate / conversion_factor``, qty ``stock_qty``).
* A figure that cannot be computed is ``None`` (JSON ``null``), never 0.
"""

from datetime import date, datetime, timedelta
from typing import TYPE_CHECKING, Any

import frappe
import ibis

if TYPE_CHECKING:
    import pandas as pd  # noqa: F401


# ---------------------------------------------------------------------------
# Pure-Python helpers (operate on a few dozen scalar rows)
# ---------------------------------------------------------------------------

# Supplier score weights (on-time / quality / lead time / PO volume). A missing
# component (supplier has no data for it) is dropped and the rest renormalised.
_SCORE_WEIGHTS = {"on_time": 0.40, "quality": 0.30, "lead": 0.20, "volume": 0.10}


def _linear_trend(values: list[float]) -> tuple[float, float]:
    n = len(values)
    if n < 2:
        return 0.0, values[0] if values else 0.0
    sx = sum(range(n))
    sy = sum(values)
    sxy = sum(i * v for i, v in enumerate(values))
    sxx = sum(i * i for i in range(n))
    denom = n * sxx - sx * sx
    if denom == 0:
        return 0.0, sy / n
    slope = (n * sxy - sx * sy) / denom
    intercept = (sy - slope * sx) / n
    return slope, intercept


def _to_records(df) -> list[dict[str, Any]]:
    """``execute().pipe(_to_records)`` with every numeric value coerced
    to a native Python int / float. Without this, MariaDB DECIMAL
    aggregates land as ``decimal.Decimal`` in the response, and the JSON
    serializer on the frontend (and Frappe's ``frappe.response``
    wrapper) silently emits a string or raises on Decimal objects
    downstream — every consumer of this engine that does a
    ``JSON.parse(response)`` then has to handle Decimal itself.
    """
    rows = df.to_dict("records")
    for row in rows:
        for k, v in list(row.items()):
            if isinstance(v, float):
                continue
            # Decimal, numpy ints, numpy floats, anything with __float__
            try:
                if hasattr(v, "__float__") and not isinstance(v, (str, bytes, dict, list)):
                    row[k] = float(v)
            except (TypeError, ValueError):
                pass
    return rows


def _num(value) -> float | None:
    """Native float, or ``None`` for NULL / NaN / NA (SUM and AVG of nothing)."""
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return None if f != f else f


def _pct(part: float | None, whole: float | None, digits: int = 1) -> float | None:
    if part is None or not whole or whole <= 0:
        return None
    return round(part / whole * 100, digits)


def _add_months(d: date, n: int) -> date:
    """First day of the calendar month ``n`` months after ``d``'s month."""
    year, month = divmod(d.year * 12 + d.month - 1 + n, 12)
    return date(year, month + 1, 1)


def _period(d: date) -> str:
    return d.strftime("%Y-%m")


def _overall_score(components: dict[str, float | None]) -> float:
    """Weighted mean of the components that exist (weights renormalised)."""
    present = {k: v for k, v in components.items() if v is not None}
    total = sum(_SCORE_WEIGHTS[k] for k in present)
    return round(sum(_SCORE_WEIGHTS[k] * v for k, v in present.items()) / total, 1)


# ---------------------------------------------------------------------------
# Procurement Intelligence
# ---------------------------------------------------------------------------


class ProcurementIntelligence:
    def __init__(self, date_filter: str = "12m"):
        from insights.api.ml.utils import parse_date_filter

        self.date_filter = date_filter
        start, end = parse_date_filter(date_filter)
        self.start: date | None = start.date() if start else None
        self.end: date = (end or datetime.now()).date()
        self.company = frappe.defaults.get_user_default("Company") or frappe.db.get_single_value(
            "Global Defaults", "default_company"
        )
        self.base_currency = (
            (self.company and frappe.db.get_value("Company", self.company, "default_currency"))
            or frappe.db.get_single_value("Global Defaults", "default_currency")
            or "USD"
        )

    # --- public entry points -------------------------------------------------

    def train(self) -> dict[str, Any]:
        try:
            return {
                "status": "success",
                "generated_at": datetime.now().isoformat(),
                "company": self.company,
                "base_currency": self.base_currency,
                "date_filter": self.date_filter,
                "period": {
                    "start": self.start.isoformat() if self.start else None,
                    "end": self.end.isoformat(),
                },
                "spend_overview": self._spend_overview(),
                "supplier_performance": self._supplier_performance(),
                "purchase_analytics": self._purchase_cycles(),
                "price_intelligence": self._price_intelligence(),
                "risk_analysis": self._procurement_risks(),
                "forecasts": self._forecast(),
            }
        except Exception as e:
            frappe.log_error(frappe.get_traceback(), "Procurement Intelligence failed")
            return {"status": "error", "message": str(e)}

    def predict(self, allow_train: bool = True) -> dict[str, Any]:
        # Backwards-compatible shim; there is no cache to read.
        return self.train()

    # --- window helpers ------------------------------------------------------

    @staticmethod
    def _between(col, start: date | None, end: date):
        cond = col <= end
        return (cond & (col >= start)) if start else cond

    def _win(self, col):
        """Boolean expression: ``col`` lies inside the selected window."""
        return self._between(col, self.start, self.end)

    def _prior_window(self) -> tuple[date, date] | None:
        """The window immediately preceding this one, same length. ``None``
        for an all-time window (no preceding period exists)."""
        if self.start is None:
            return None
        days = (self.end - self.start).days + 1
        prior_end = self.start - timedelta(days=1)
        return prior_end - timedelta(days=days - 1), prior_end

    def _month_series(self, rows: list[dict[str, Any]], zero: dict[str, Any]) -> list[dict[str, Any]]:
        """Whole calendar months from the window start's month through the
        window end's month (the current month for presets), gaps filled with
        ``zero``. The first month is ``partial`` when the window starts
        mid-month; the last when it is still in progress (or the window ends
        before month end)."""
        by_period = {r["period"]: r for r in rows}
        if self.start:
            first = self.start.replace(day=1)
        elif by_period:
            first = date.fromisoformat(min(by_period) + "-01")  # all-time: first month with data
        else:
            return []
        last = self.end.replace(day=1)
        this_month = date.today().replace(day=1)
        series: list[dict[str, Any]] = []
        month = first
        while month <= last:
            row = {**zero, **by_period.get(_period(month), {}), "period": _period(month)}
            month_end = _add_months(month, 1) - timedelta(days=1)
            row["partial"] = bool(
                (month == first and self.start is not None and self.start.day > 1)
                or (month == last and (month == this_month or self.end < month_end))
            )
            series.append(row)
            month = _add_months(month, 1)
        return series

    # --- spend overview ------------------------------------------------------

    def _spend_overview(self) -> dict[str, Any]:
        from insights.api.ml.ibis_source import t

        PI = t("Purchase Invoice").filter(lambda x: x.docstatus == 1)
        PII = t("Purchase Invoice Item")
        Supplier = t("Supplier")
        Item = t("Item")

        pi_win = PI.filter(self._win(PI.posting_date))

        summary = (
            pi_win.aggregate(
                invoice_count=pi_win.name.nunique(),
                supplier_count=pi_win.supplier.nunique(),
                total_spend=pi_win.base_grand_total.sum(),
            )
            .execute()
            .iloc[0]
        )
        total_spend = _num(summary.get("total_spend"))

        # Growth vs the immediately preceding window of equal length.
        prior_period_growth = None
        prior = self._prior_window()
        if prior and total_spend is not None:
            pi_prior = PI.filter(self._between(PI.posting_date, *prior))
            prior_spend = _num(
                pi_prior.aggregate(spend=pi_prior.base_grand_total.sum()).execute().iloc[0]["spend"]
            )
            if prior_spend and prior_spend > 0:
                prior_period_growth = round((total_spend - prior_spend) / prior_spend * 100, 1)

        monthly_rows = (
            pi_win.group_by(pi_win.posting_date.strftime("%Y-%m").name("period"))
            .aggregate(
                invoice_count=pi_win.name.nunique(),
                supplier_count=pi_win.supplier.nunique(),
                spend=pi_win.base_grand_total.sum(),
            )
            .order_by("period")
            .execute()
            .pipe(_to_records)
        )
        monthly = self._month_series(monthly_rows, {"invoice_count": 0, "supplier_count": 0, "spend": 0.0})

        # By category (item group). Filter the parent PI BEFORE the
        # semi-join: after a semi-join the right-side relation is no
        # longer in scope, so a `.filter(PI.posting_date >= ...)` here
        # would raise "they belong to another relation". Every category is
        # fetched (a few dozen rows) so pct_of_total divides by the
        # whole-window item total, not the top-15 sum.
        categories = (
            PII.join(pi_win, PII.parent == pi_win.name, how="semi")
            .select(PII.item_code, PII.base_amount, PII.parent)
            .left_join(Item, PII.item_code == Item.name)
            .group_by(Item.item_group)
            .aggregate(spend=PII.base_amount.sum(), invoice_count=PII.parent.nunique())
            .order_by(ibis.desc("spend"))
            .execute()
            .pipe(_to_records)
        )
        total_cat = sum(float(c.get("spend") or 0) for c in categories)
        by_category = [
            {
                "category": c.get("item_group") or "Uncategorized",
                "spend": c.get("spend"),
                "invoice_count": c.get("invoice_count"),
                "pct_of_total": _pct(c.get("spend"), total_cat),
            }
            for c in categories[:15]
        ]

        top_suppliers = (
            pi_win.left_join(Supplier, pi_win.supplier == Supplier.name)
            .group_by(pi_win.supplier, Supplier.supplier_name)
            .aggregate(invoice_count=pi_win.name.nunique(), spend=pi_win.base_grand_total.sum())
            .order_by(ibis.desc("spend"))
            .limit(10)
            .execute()
            .pipe(_to_records)
        )
        for s in top_suppliers:
            s["pct_of_total"] = _pct(s.get("spend"), total_spend)

        return {
            "total_spend": total_spend,
            "prior_period_growth": prior_period_growth,
            "invoice_count": int(summary.get("invoice_count") or 0),
            "supplier_count": int(summary.get("supplier_count") or 0),
            "monthly_trend": monthly,
            "by_category": by_category,
            "top_suppliers": top_suppliers,
        }

    # --- supplier performance ------------------------------------------------

    def _po_pr_pairs(self, PO, PR, PRI):
        """Distinct (PO, PR) fulfilment pairs for POs in the window, linked
        through ``PRI.purchase_order`` (each PR belongs to exactly one PO;
        a multi-item PR has several item rows for the same PO, hence
        ``distinct``). Single source for ``supplier_performance`` lead times
        and ``purchase_analytics.avg_po_to_grn_days`` so both share a basis.
        The explicit ``select`` before ``distinct`` is required: chained
        joins raise IntegrityError on unresolved name collisions (every
        Frappe doctype table shares name/owner/creation/...)."""
        return (
            PO.filter(self._win(PO.transaction_date))
            .inner_join(PRI, PRI.purchase_order == PO.name)
            .inner_join(PR, (PRI.parent == PR.name) & (PR.docstatus == 1))
            .select(po=PO.name, pr=PR.name, po_date=PO.transaction_date, pr_date=PR.posting_date)
            .distinct()
        )

    def _supplier_performance(self) -> dict[str, Any]:
        from statistics import median as _median

        import pandas as _pd
        from insights.api.ml.ibis_source import t

        PO = t("Purchase Order").filter(lambda x: x.docstatus == 1)
        PR = t("Purchase Receipt").filter(lambda x: x.docstatus == 1)
        PRI = t("Purchase Receipt Item")
        Supplier = t("Supplier")
        today = datetime.now().date()

        empty = {
            "total_suppliers": 0,
            "avg_score": None,
            "avg_on_time_rate": None,
            "avg_quality_rate": None,
            "quality_status": "not_implemented",
            "avg_lead_time": None,
            "top_performers": [],
            "bottom_performers": [],
            "all_suppliers": [],
        }

        # --- PO totals per supplier ----------------------------------------
        po_win = PO.filter(self._win(PO.transaction_date)).select(
            PO.name.name("po_name"), PO.supplier, PO.base_grand_total
        )
        supplier_slim = Supplier.select(
            Supplier.name.name("supplier_key"), Supplier.supplier_name, Supplier.supplier_group
        )
        suppliers = (
            po_win.left_join(supplier_slim, po_win.supplier == supplier_slim.supplier_key)
            .group_by(po_win.supplier, supplier_slim.supplier_name, supplier_slim.supplier_group)
            .aggregate(
                po_count=po_win.po_name.nunique(),
                total_value=po_win.base_grand_total.sum(),
            )
            .execute()
        )
        # Filter to suppliers with >= 2 POs (matches old HAVING).
        suppliers = suppliers[suppliers["po_count"] >= 2]
        if len(suppliers) == 0:
            return empty
        suppliers = suppliers.sort_values("total_value", ascending=False).head(50)

        # Supplier-per-PO lookup, used below to map (PO, PR) rows to
        # their supplier.
        po_win_df = po_win.execute()
        po_supplier_map: dict[str, str] = dict(
            zip(po_win_df["po_name"].astype(str), po_win_df["supplier"].astype(str))
        )

        # --- Lead time per supplier -----------------------------------------
        # Mean of (PR.posting_date - PO.transaction_date) over each distinct
        # (PO, PR) pair (see `_po_pr_pairs`). A PO fulfilled by N partial PRs
        # contributes N rows: each delivery counts.
        lead_pairs = self._po_pr_pairs(PO, PR, PRI).execute()
        lead_time_map: dict[str, float] = {}
        all_leads: list[float] = []
        if len(lead_pairs):
            # Under the PyArrow materialization path (`use_pyarrow_materialization`,
            # applied by every real compute -- see `insights.api.ml.utils._compute`)
            # date columns come back as object-dtype `datetime.date`, not
            # `datetime64[ns]`. Subtracting two such columns still works
            # elementwise (produces `datetime.timedelta` objects, dtype=object),
            # but `.dt.days` requires a proper datetime64/timedelta64 dtype and
            # raises `AttributeError: Can only use .dt accessor with datetimelike
            # values` on the object-dtype result -- this crashed every real
            # request to this endpoint. `pd.to_datetime` normalizes both
            # columns first; it is a no-op when they are already datetime64.
            po_dt = _pd.to_datetime(lead_pairs["po_date"])
            pr_dt = _pd.to_datetime(lead_pairs["pr_date"])
            lead_pairs["delta_days"] = (pr_dt - po_dt).dt.days
            lead_pairs = lead_pairs[lead_pairs["delta_days"] >= 0]
            lead_pairs = lead_pairs.assign(supplier=lead_pairs["po"].map(po_supplier_map)).dropna(
                subset=["supplier"]
            )
            for sup, mean_days in lead_pairs.groupby("supplier")["delta_days"].mean().items():
                lead_time_map[str(sup)] = round(float(mean_days), 1)
            all_leads = [float(d) for d in lead_pairs["delta_days"]]

        # --- On-time delivery per supplier ----------------------------------
        # Per-PO: a PO is "on time" iff it has at least one PR whose
        # posting_date <= schedule_date. Linked through ``PRI.purchase_order``
        # so each PR belongs to exactly one PO. Denominator: POs that have a
        # receipt OR whose schedule_date has already passed -- an open PO
        # that is not yet due is neither on time nor late, so it is excluded.
        sched_pos = (
            PO.filter(self._win(PO.transaction_date) & PO.schedule_date.notnull())
            .select(po=PO.name, schedule=PO.schedule_date)
            .execute()
        )
        receipts = (
            PO.filter(self._win(PO.transaction_date) & PO.schedule_date.notnull())
            .inner_join(PRI, PRI.purchase_order == PO.name)
            .inner_join(PR, (PRI.parent == PR.name) & (PR.docstatus == 1))
            .select(po=PO.name, schedule=PO.schedule_date, pr_date=PR.posting_date)
            .distinct()
            .execute()
        )
        received_pos: set[str] = set()
        on_time_pos: set[str] = set()
        if len(receipts):
            received_pos = set(receipts["po"])
            early = _pd.to_datetime(receipts["pr_date"]) <= _pd.to_datetime(receipts["schedule"])
            on_time_pos = set(receipts.loc[early, "po"])
        on_time_map: dict[str, dict[str, int]] = {}
        for po, schedule in zip(sched_pos["po"], sched_pos["schedule"]):
            sup = po_supplier_map.get(str(po))
            if sup is None or not (po in received_pos or _pd.Timestamp(schedule).date() < today):
                continue
            counts = on_time_map.setdefault(sup, {"total_orders": 0, "on_time_count": 0})
            counts["total_orders"] += 1
            counts["on_time_count"] += int(po in on_time_pos)

        # --- Quality rate per supplier --------------------------------------
        # Per-supplier quality signals in ERPNext:
        #   1. Purchase Receipt Item.rejected_qty (goods rejected at receipt)
        #   2. Purchase Receipt Item.returned_qty (goods returned after receipt)
        #   3. Purchase Invoice with is_return=1 (credit-note returns)
        # Per-supplier rejected+returned share of received qty; if neither
        # signal is populated anywhere on the site, expose
        # ``quality_status: "not_implemented"`` and drop the metric from
        # the composite overall_score so the displayed score reflects only
        # signals that actually exist.
        po_for_quality = PO.filter(self._win(PO.transaction_date)).select(
            PO.name.name("po_name_q"), PO.supplier
        )
        qual = (
            PRI.join(PR, (PRI.parent == PR.name) & (PR.docstatus == 1), how="inner")
            .join(po_for_quality, PRI.purchase_order == po_for_quality.po_name_q, how="inner")
            .select(
                supplier=po_for_quality.supplier,
                received_qty=PRI.received_qty,
                rejected_qty=PRI.rejected_qty,
                returned_qty=PRI.returned_qty,
            )
        )
        qual_rows = (
            qual.group_by(qual.supplier)
            .aggregate(
                received=qual.received_qty.sum(),
                rejected=qual.rejected_qty.sum(),
                returned=qual.returned_qty.sum(),
            )
            .execute()
            .pipe(_to_records)
        )
        total_bad = sum(max(0.0, r["rejected"] or 0.0) + max(0.0, r["returned"] or 0.0) for r in qual_rows)
        quality_status = "success" if total_bad > 0 else "not_implemented"
        quality_map: dict[str, float] = {}
        if quality_status == "success":
            for r in qual_rows:
                received = r["received"] or 0.0
                if received > 0:  # no received qty = no quality data for that supplier
                    bad = max(0.0, (r["rejected"] or 0.0) + (r["returned"] or 0.0))
                    quality_map[str(r["supplier"])] = round(min(100.0, max(0.0, (received - bad) / received * 100)), 1)

        # --- Per-supplier composite score -----------------------------------
        # Site-relative lead-time anchor: a supplier at the site median
        # gets 50, at 2x the site median gets 0. A hardcoded 30-day anchor
        # clamps every supplier to 0 on sites whose median is longer.
        lead_anchor = max(1.0, 2.0 * float(_median(all_leads) if all_leads else 0.0))
        all_rows: list[dict[str, Any]] = []
        for _, s in suppliers.iterrows():
            sup = s["supplier"]
            ot = on_time_map.get(sup)
            ot_rate = round(ot["on_time_count"] / ot["total_orders"] * 100, 1) if ot else None
            avg_lead = lead_time_map.get(sup)
            q_rate = quality_map.get(sup)
            po_count = int(s.get("po_count") or 0)
            overall = _overall_score(
                {
                    "on_time": ot_rate,
                    "quality": q_rate,
                    "lead": None if avg_lead is None else max(0.0, 100.0 * (1.0 - avg_lead / lead_anchor)),
                    "volume": min(100.0, po_count / 12.0 * 100),
                }
            )
            all_rows.append(
                {
                    "supplier": sup,
                    "supplier_name": s.get("supplier_name"),
                    "supplier_group": s.get("supplier_group"),
                    "po_count": po_count,
                    "total_value": float(s.get("total_value") or 0),
                    "avg_lead_time": avg_lead,
                    "on_time_rate": ot_rate,
                    "quality_rate": q_rate,
                    "overall_score": overall,
                }
            )

        all_rows.sort(key=lambda x: x["overall_score"], reverse=True)

        def _avg(key: str) -> float | None:
            vals = [r[key] for r in all_rows if r[key] is not None]
            return round(sum(vals) / len(vals), 1) if vals else None

        return {
            "total_suppliers": len(all_rows),
            "avg_score": _avg("overall_score"),
            "avg_on_time_rate": _avg("on_time_rate"),
            "avg_quality_rate": _avg("quality_rate"),
            "quality_status": quality_status,
            # Every (PO, PR) pair, same basis as purchase_analytics.avg_po_to_grn_days.
            "avg_lead_time": round(sum(all_leads) / len(all_leads), 1) if all_leads else None,
            "top_performers": all_rows[:10],
            "bottom_performers": sorted(all_rows, key=lambda x: x["overall_score"])[:5],
            "all_suppliers": all_rows[:50],
        }

    # --- purchase cycle analytics --------------------------------------------

    def _purchase_cycles(self) -> dict[str, Any]:
        from insights.api.ml.ibis_source import t

        PO = t("Purchase Order").filter(lambda x: x.docstatus == 1)
        POI = t("Purchase Order Item")
        MR = t("Material Request")
        PR = t("Purchase Receipt").filter(lambda x: x.docstatus == 1)
        PRI = t("Purchase Receipt Item")
        PI = t("Purchase Invoice").filter(lambda x: x.docstatus == 1)
        PII = t("Purchase Invoice Item")
        today = datetime.now().date()

        # PO status summary (windowed)
        po_status = (
            PO.filter(self._win(PO.transaction_date))
            .group_by(PO.status)
            .aggregate(count=PO.name.count(), value=PO.base_grand_total.sum())
            .execute()
            .pipe(_to_records)
        )

        # Pending POs: current open-order state, not windowed. ``pending`` below
        # is capped to the 20 oldest for display; pending_count/pending_value
        # come from a separate full aggregate over the same filter.
        pending_filtered = PO.filter(~PO.status.isin(["Completed", "Closed", "Cancelled"]))
        pending_agg = pending_filtered.aggregate(
            pending_count=pending_filtered.name.count(),
            pending_value=pending_filtered.base_grand_total.sum(),
        ).execute()
        pending_count = int(pending_agg["pending_count"].iloc[0]) if len(pending_agg) else 0
        pending_value = _num(pending_agg["pending_value"].iloc[0]) if len(pending_agg) else None

        pending = (
            pending_filtered
            .select(
                PO.name, PO.supplier, PO.transaction_date, PO.base_grand_total.name("grand_total"), PO.status
            )
            .mutate(
                days_pending=(today - PO.transaction_date).cast("int32")
            )
            .order_by(ibis.desc("days_pending"))
            .limit(20)
            .execute()
            .pipe(_to_records)
        )

        # Average cycle times: three independently-scoped SQL AVGs over
        # DISTINCT (earlier doc, later doc) pairs, so a multi-item PO or PR
        # counts once per pair instead of once per item row. Negative gaps
        # (back-dated documents) are dropped, as in supplier_performance.
        # NULL when a stage has no pairs (never 0).
        def _mean_days(pairs, later_col: str, earlier_col: str) -> float | None:
            days = pairs.mutate(days=(pairs[later_col] - pairs[earlier_col]).cast("int32"))
            days = days.filter(days.days >= 0)
            value = _num(days.aggregate(avg_days=days.days.mean()).execute()["avg_days"].iloc[0])
            return None if value is None else round(value, 1)

        # Each join chains two hops (e.g. PO -> POI -> MR), so an explicit
        # ``select()`` is required before aggregating (see `_po_pr_pairs`).
        mr_to_po = (
            PO.filter(self._win(PO.transaction_date))
            .inner_join(POI, POI.parent == PO.name)
            .inner_join(MR, POI.material_request == MR.name)
            .select(
                po=PO.name,
                mr=MR.name,
                later=PO.transaction_date,
                earlier=MR.transaction_date,
            )
            .distinct()
        )
        avg_mr_to_po = _mean_days(mr_to_po, "later", "earlier")

        avg_po_to_grn = _mean_days(self._po_pr_pairs(PO, PR, PRI), "pr_date", "po_date")

        grn_to_inv = (
            PR.filter(self._win(PR.posting_date))
            .inner_join(PII, PII.purchase_receipt == PR.name)
            .inner_join(PI, (PII.parent == PI.name) & (PI.docstatus == 1))
            .select(
                pr=PR.name,
                pi=PI.name,
                later=PI.posting_date,
                earlier=PR.posting_date,
            )
            .distinct()
        )
        avg_grn_to_inv = _mean_days(grn_to_inv, "later", "earlier")

        # Monthly PO trend (windowed)
        monthly_rows = (
            PO.filter(self._win(PO.transaction_date))
            .group_by(PO.transaction_date.strftime("%Y-%m").name("period"))
            .aggregate(
                po_count=PO.name.count(),
                po_value=PO.base_grand_total.sum(),
                avg_po_value=PO.base_grand_total.mean(),
            )
            .order_by("period")
            .execute()
            .pipe(_to_records)
        )
        monthly = self._month_series(monthly_rows, {"po_count": 0, "po_value": 0.0, "avg_po_value": None})

        # total_po_count is windowed; overdue_po_count is current state. Overdue
        # mirrors get_procurement_detail's overdue_pos drill-down filter
        # (docstatus=1, schedule_date < today, status not terminal) so the KPI
        # card agrees with its own drill-down panel.
        po_volume_agg = PO.aggregate(
            total_po_count=PO.name.count(where=self._win(PO.transaction_date)),
            overdue_po_count=PO.name.count(
                where=(PO.schedule_date < today)
                & (~PO.status.isin(["Completed", "Cancelled", "Closed"]))
            ),
        ).execute()
        total_po_count = int(po_volume_agg["total_po_count"].iloc[0]) if len(po_volume_agg) else 0
        overdue_po_count = int(po_volume_agg["overdue_po_count"].iloc[0]) if len(po_volume_agg) else 0

        return {
            "po_status_summary": po_status,
            "pending_pos": pending,
            "pending_count": pending_count,
            "pending_value": pending_value,
            "avg_mr_to_po_days": avg_mr_to_po,
            "avg_po_to_grn_days": avg_po_to_grn,
            "avg_grn_to_invoice_days": avg_grn_to_inv,
            "monthly_trend": monthly,
            "total_po_count": total_po_count,
            "overdue_po_count": overdue_po_count,
        }

    # --- price intelligence --------------------------------------------------

    def _price_intelligence(self) -> dict[str, Any]:
        from insights.api.ml.ibis_source import t

        PII = t("Purchase Invoice Item")
        PI = t("Purchase Invoice").filter(lambda x: x.docstatus == 1)
        Item = t("Item")

        # Stock items only (service/non-stock lines have no comparable unit),
        # purchase invoices only (returns carry negative qty). Filter the parent
        # PI BEFORE joining and `select` before the next join: after a join
        # the right-hand relation is out of scope and name collisions raise.
        pi_win = PI.filter(self._win(PI.posting_date) & (PI.is_return == 0))
        lines = PII.inner_join(pi_win, PII.parent == pi_win.name).select(
            item_code=PII.item_code,
            parent=PII.parent,
            posting_date=pi_win.posting_date,
            # base currency per stock UOM
            unit=PII.base_rate / ibis.ifelse(PII.conversion_factor > 0, PII.conversion_factor, 1),
            qty=PII.stock_qty,
        )
        stock_items = Item.filter(Item.is_stock_item == 1).select(Item.name)
        base = lines.join(stock_items, lines.item_code == stock_items.name, how="semi")

        per_item = (
            base.group_by(base.item_code)
            .aggregate(
                purchase_count=base.parent.nunique(),
                avg_rate=base.unit.mean(),
                min_rate=base.unit.min(),
                max_rate=base.unit.max(),
                total_cost=(base.unit * base.qty).sum(),
                total_qty=base.qty.sum(),
            )
            .filter(lambda x: x.purchase_count >= 3)
        )
        # Last price: per item, the line of the latest invoice (window
        # function, one row per item -- no row-level fetch into pandas).
        newest_first = ibis.window(
            group_by=base.item_code, order_by=[ibis.desc(base.posting_date), ibis.desc(base.parent)]
        )
        ranked = base.mutate(rn=ibis.row_number().over(newest_first))
        last = ranked.filter(ranked.rn == 0).select(last_item=ranked.item_code, last_rate=ranked.unit)
        rows = (
            per_item.left_join(last, per_item.item_code == last.last_item)
            .select(
                per_item.item_code,
                per_item.purchase_count,
                per_item.avg_rate,
                per_item.min_rate,
                per_item.max_rate,
                per_item.total_cost,
                per_item.total_qty,
                last.last_rate,
            )
            .execute()
            .pipe(_to_records)
        )

        item_meta: dict[str, dict[str, Any]] = {}
        if rows:
            meta = (
                Item.filter(Item.name.isin([r["item_code"] for r in rows]))
                .select(Item.name, Item.item_name, Item.item_group)
                .execute()
            )
            item_meta = {r["name"]: r for _, r in meta.iterrows()}

        records = []
        for r in rows:
            avg, mn, mx = _num(r["avg_rate"]), _num(r["min_rate"]), _num(r["max_rate"])
            last_rate = _num(r["last_rate"])
            meta = item_meta.get(r["item_code"], {})
            records.append(
                {
                    "item_code": r["item_code"],
                    "item_name": meta.get("item_name"),
                    "item_group": meta.get("item_group"),
                    "purchase_count": int(r["purchase_count"] or 0),
                    "avg_rate": avg,
                    "min_rate": mn,
                    "max_rate": mx,
                    "last_rate": last_rate,
                    "price_variance_pct": _pct(last_rate - avg, avg) if avg and last_rate is not None else None,
                    "price_range_pct": _pct(mx - mn, avg) if avg and mx is not None and mn is not None else None,
                    # sum((unit_price_i - min_unit_price) * stock_qty_i)
                    "potential_savings": round((_num(r["total_cost"]) or 0.0) - (mn or 0.0) * (_num(r["total_qty"]) or 0.0), 2),
                }
            )

        records.sort(key=lambda x: x["purchase_count"], reverse=True)
        increases = sorted(
            [r for r in records if (r["price_variance_pct"] or 0) > 5],
            key=lambda x: x["price_variance_pct"],
            reverse=True,
        )
        volatile = sorted(
            [r for r in records if (r["price_range_pct"] or 0) > 20],
            key=lambda x: x["price_range_pct"],
            reverse=True,
        )

        return {
            "price_variance_items": records[:20],
            "price_increases": increases[:10],
            "price_increases_count": len(increases),
            "volatile_items": volatile[:10],
            "total_potential_savings": round(sum(r["potential_savings"] for r in records), 2),
            "items_analyzed": len(records),
        }

    # --- risk assessment -----------------------------------------------------

    def _procurement_risks(self) -> dict[str, Any]:
        from insights.api.ml.ibis_source import t

        PI = t("Purchase Invoice").filter(lambda x: x.docstatus == 1)
        PII = t("Purchase Invoice Item")
        Supplier = t("Supplier")
        Item = t("Item")
        today = datetime.now().date()

        pi_win = PI.filter(self._win(PI.posting_date))
        total_spend = _num(
            pi_win.aggregate(total=pi_win.base_grand_total.sum()).execute().iloc[0]["total"]
        )

        # Supplier concentration (share of whole-window spend)
        supplier_conc = (
            pi_win.left_join(Supplier, pi_win.supplier == Supplier.name)
            .group_by(pi_win.supplier, Supplier.supplier_name)
            .aggregate(spend=pi_win.base_grand_total.sum())
            .order_by(ibis.desc("spend"))
            .limit(10)
            .execute()
            .pipe(_to_records)
        )
        for s in supplier_conc:
            pct = _pct(s.get("spend"), total_spend)
            s["concentration_pct"] = pct
            s["total_spend"] = total_spend
            s["risk_level"] = None if pct is None else "High" if pct > 30 else ("Medium" if pct > 15 else "Low")
        high_conc_count = sum(1 for s in supplier_conc if (s["concentration_pct"] or 0) > 30)

        # Single-source items: one supplier in the window and item spend at
        # least 0.05% of window spend. Needs `pi_win.supplier`, which a
        # semi-join can't expose -- inner join instead (safe: `pi_win.name`
        # is a primary key, so no row multiplication). With one supplier,
        # `max()` IS that supplier.
        single_source_all = (
            PII.join(pi_win, PII.parent == pi_win.name, how="inner")
            .group_by(PII.item_code)
            .aggregate(
                supplier_count=pi_win.supplier.nunique(),
                total_spend=PII.base_amount.sum(),
                only_supplier=pi_win.supplier.max(),
            )
            .filter(lambda x: (x.supplier_count == 1) & (x.total_spend >= (total_spend or 0) * 0.0005))
        )
        # single_source_count/value reflect every matching item, not just
        # the top-20 kept for the drill-down list below.
        ss_totals = single_source_all.aggregate(
            single_source_count=single_source_all.item_code.nunique(),
            single_source_value=single_source_all.total_spend.sum(),
        ).execute()
        single_source_count = int(ss_totals["single_source_count"].iloc[0]) if len(ss_totals) else 0
        single_source_value = _num(ss_totals["single_source_value"].iloc[0]) or 0.0 if len(ss_totals) else 0.0

        single_source = single_source_all.order_by(ibis.desc("total_spend")).limit(20).execute()
        ss_records = []
        if len(single_source):
            items_meta = (
                Item.filter(Item.name.isin(list(single_source["item_code"])))
                .select(Item.name, Item.item_name, Item.item_group)
                .execute()
            )
            item_meta_map = {r["name"]: r for _, r in items_meta.iterrows()}
            for _, r in single_source.iterrows():
                meta = item_meta_map.get(r["item_code"], {})
                ss_records.append(
                    {
                        "item_code": r["item_code"],
                        "item_name": meta.get("item_name"),
                        "item_group": meta.get("item_group"),
                        "supplier_count": 1,
                        "total_spend": float(r["total_spend"] or 0),
                        "only_supplier": r["only_supplier"],
                    }
                )

        # Payment exposure: current state (not windowed), base currency.
        open_pi = PI.filter(PI.outstanding_amount > 0)
        payment_exposure = (
            open_pi.left_join(Supplier, open_pi.supplier == Supplier.name)
            .group_by(open_pi.supplier, Supplier.supplier_name)
            .aggregate(
                outstanding=(open_pi.outstanding_amount * open_pi.conversion_rate).sum(),
                invoice_count=open_pi.name.count(),
                earliest_due=open_pi.due_date.min(),
            )
            .order_by(ibis.desc("outstanding"))
            .limit(15)
            .execute()
            .pipe(_to_records)
        )
        total_outstanding = _num(
            open_pi.aggregate(total=(open_pi.outstanding_amount * open_pi.conversion_rate).sum())
            .execute()
            .iloc[0]["total"]
        ) or 0.0

        # Overdue invoices: current state, base currency.
        overdue_pi = PI.filter((PI.outstanding_amount > 0) & (PI.due_date < today))
        overdue_invoices = (
            overdue_pi.select(
                overdue_pi.name,
                overdue_pi.supplier,
                overdue_pi.posting_date,
                overdue_pi.due_date,
                overdue_pi.base_grand_total.name("grand_total"),
                (overdue_pi.outstanding_amount * overdue_pi.conversion_rate).name("outstanding_amount"),
            )
            .mutate(days_overdue=(today - overdue_pi.due_date).cast("int32"))
            .order_by(ibis.desc("days_overdue"))
            .limit(20)
            .execute()
            .pipe(_to_records)
        )
        overdue_totals = overdue_pi.aggregate(
            count=overdue_pi.name.count(),
            value=(overdue_pi.outstanding_amount * overdue_pi.conversion_rate).sum(),
        ).execute().iloc[0]
        overdue_count = int(overdue_totals.get("count") or 0)
        overdue_value = _num(overdue_totals.get("value")) or 0.0

        # Risk score, 0-100 = sum of three bounded components (weights
        # 35 / 35 / 30), so no single factor can saturate the score:
        #   concentration: 15 per supplier above 30% of window spend, max 35
        #   single_source: single-source item spend / window spend x 35
        #   overdue:       overdue base value / window spend x 30
        # No spend in the window => no denominator => null score.
        if total_spend and total_spend > 0:
            risk_components = {
                "concentration": min(35.0, 15.0 * high_conc_count),
                "single_source": min(35.0, 35.0 * single_source_value / total_spend),
                "overdue": min(30.0, 30.0 * overdue_value / total_spend),
            }
            risk_components = {k: round(v, 1) for k, v in risk_components.items()}
            risk_score = round(sum(risk_components.values()), 1)
        else:
            risk_components = dict.fromkeys(("concentration", "single_source", "overdue"))
            risk_score = None

        return {
            "risk_score": risk_score,
            "risk_components": risk_components,
            "supplier_concentration": supplier_conc,
            "single_source_items": ss_records,
            "single_source_count": single_source_count,
            "single_source_value": single_source_value,
            "payment_exposure": payment_exposure,
            "total_outstanding": total_outstanding,
            "overdue_invoices": overdue_invoices,
            "overdue_count": overdue_count,
        }

    # --- forecasting ---------------------------------------------------------

    def _forecast(self) -> dict[str, Any]:
        from insights.api.ml.ibis_source import t

        PI = t("Purchase Invoice").filter(lambda x: x.docstatus == 1)
        PII = t("Purchase Invoice Item")
        Item = t("Item")
        today = datetime.now().date()
        this_month = today.replace(day=1)

        # History is fixed (last 24 whole calendar months + the in-progress
        # month), independent of date_filter.
        history_start = _add_months(this_month, -24)
        pi_hist = PI.filter(self._between(PI.posting_date, history_start, today))
        spend_by_period = {
            r["period"]: float(r["spend"] or 0)
            for r in pi_hist.group_by(pi_hist.posting_date.strftime("%Y-%m").name("period"))
            .aggregate(spend=pi_hist.base_grand_total.sum())
            .execute()
            .pipe(_to_records)
        }

        # Contiguous complete months from the first month with spend (leading
        # empty months would drag the fit), gaps inside zero-filled. The
        # in-progress month is shown flagged `partial` but never fitted.
        months = [_add_months(this_month, k) for k in range(-24, 0)]
        values = [spend_by_period.get(_period(m), 0.0) for m in months]
        lead = next((i for i, v in enumerate(values) if v), len(values))
        months, values = months[lead:], values[lead:]
        historical = [{"period": _period(m), "spend": v, "partial": False} for m, v in zip(months, values)]
        historical.append(
            {"period": _period(this_month), "spend": spend_by_period.get(_period(this_month), 0.0), "partial": True}
        )

        if len(values) < 6:
            return {
                "status": "insufficient_data",
                "message": "Need at least 6 months of data for forecasting",
                "historical": historical,
            }

        # Linear-trend projection: complete months are index 0..n-1, the
        # in-progress month is n, the next three calendar months n+1..n+3.
        slope, intercept = _linear_trend(values)
        n = len(values)
        forecasts = [
            {
                "period": _period(_add_months(this_month, i)),
                "predicted_spend": round(max(0.0, intercept + slope * (n + i)), 2),
            }
            for i in range(1, 4)
        ]

        # Category run-rate: trailing-12-month item amount / 12, held flat for
        # 3 months. Filter parent PI BEFORE the semi-join.
        pi_12m = PI.filter(self._between(PI.posting_date, today - timedelta(days=365), today))
        category = (
            PII.join(pi_12m, PII.parent == pi_12m.name, how="semi")
            .left_join(Item, PII.item_code == Item.name)
            .group_by(Item.item_group)
            .aggregate(total_12m=PII.base_amount.sum())
            .order_by(ibis.desc("total_12m"))
            .limit(10)
            .execute()
            .pipe(_to_records)
        )
        category_forecast = [
            {
                "category": c.get("item_group") or "Uncategorized",
                "avg_monthly_spend": round(float(c["total_12m"] or 0) / 12, 2),
                "forecast_3m": round(float(c["total_12m"] or 0) / 12 * 3, 2),
            }
            for c in category
        ]

        return {
            "status": "success",
            "historical": historical,
            "forecasts": forecasts,
            "avg_monthly_spend": round(sum(values[-6:]) / 6.0, 2),
            "trend_direction": "up" if slope > 0 else "down",
            "trend_amount": round(abs(slope), 2),
            "category_forecast": category_forecast,
        }


# ---------------------------------------------------------------------------
# Module-level wrappers
# ---------------------------------------------------------------------------


def run_procurement_intelligence(refresh: bool = False, date_filter: str = "12m") -> dict[str, Any]:
    """Run procurement intelligence analysis."""
    return ProcurementIntelligence(date_filter=date_filter).train()
