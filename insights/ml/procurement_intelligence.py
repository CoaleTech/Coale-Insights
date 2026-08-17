from __future__ import annotations

# Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""
Procurement Intelligence — Ibis rewrite.

Same rationale as ``inventory_intelligence.py``: every metric is one or
two SQL aggregates computed inside MariaDB. No pandas / scikit-learn /
statsmodels. The Python process only touches the final handful of
aggregated rows, so there is nothing to vectorise and no fork to crash.
"""

from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

import frappe
import ibis

if TYPE_CHECKING:
    import pandas as pd  # noqa: F401


# ---------------------------------------------------------------------------
# Pure-Python trend helpers (operate on a few dozen scalar rows)
# ---------------------------------------------------------------------------


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
    aggregates land as ``decimal.Decimal`` in the response, and the
    JSON serializer on the frontend (and Frappe's ``frappe.response``
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


# ---------------------------------------------------------------------------
# Procurement Intelligence
# ---------------------------------------------------------------------------


class ProcurementIntelligence:
    def __init__(self):
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

    # --- spend overview ------------------------------------------------------

    def _spend_overview(self) -> dict[str, Any]:
        from insights.api.ml.ibis_source import t

        PI = t("Purchase Invoice").filter(lambda x: x.docstatus == 1)
        PII = t("Purchase Invoice Item")
        Supplier = t("Supplier")
        Item = t("Item")
        today = datetime.now().date()

        # Headline numbers
        summary = PI.filter(PI.posting_date >= today - timedelta(days=365)).aggregate(
            invoice_count=PI.name.nunique(),
            supplier_count=PI.supplier.nunique(),
            total_spend=PI.grand_total.sum(),
            avg_invoice_value=PI.grand_total.mean(),
        ).execute().iloc[0]

        # YTD
        ytd = PI.filter(PI.posting_date.strftime("%Y") == today.strftime("%Y")).aggregate(
            ytd_spend=PI.grand_total.sum()
        ).execute().iloc[0]["ytd_spend"] or 0

        # Last year same period (up to today's day-of-year)
        last_year = (
            PI.filter(
                (PI.posting_date.strftime("%Y") == str(today.year - 1))
                & (PI.posting_date.strftime("%j").cast("int") <= int(today.strftime("%j")))
            )
            .aggregate(last_year_spend=PI.grand_total.sum())
            .execute()
            .iloc[0]["last_year_spend"]
            or 0
        )
        yoy_growth = 0.0
        if last_year and float(last_year) > 0:
            # Cast to float explicitly: ibis/MariaDB DECIMAL aggregates
            # land as decimal.Decimal in the response, and the JSON
            # serializer on the frontend chokes on Decimal. Force a
            # Python float here so the dashboard's "Total Spend" tile
            # can display YoY without needing a Decimal->Number fallback
            # in every consumer.
            yoy_growth = (float(ytd) - float(last_year)) / float(last_year) * 100

        # Monthly trend
        monthly = (
            PI.filter(PI.posting_date >= today - timedelta(days=365))
            .group_by(PI.posting_date.strftime("%Y-%m").name("period"))
            .aggregate(
                invoice_count=PI.name.nunique(),
                supplier_count=PI.supplier.nunique(),
                spend=PI.grand_total.sum(),
            )
            .order_by("period")
            .execute()
            .pipe(_to_records)
        )

        # By category (item group). Filter the parent PI BEFORE the
        # semi-join: after a semi-join the right-side relation is no
        # longer in scope, so a `.filter(PI.posting_date >= ...)` here
        # would raise "they belong to another relation".
        pi_365 = PI.filter(PI.posting_date >= today - timedelta(days=365))
        by_category = (
            PII.join(pi_365, PII.parent == pi_365.name, how="semi")
            .select(PII.item_code, PII.amount, PII.parent)
            .left_join(Item, PII.item_code == Item.name)
            .group_by(Item.item_group)
            .aggregate(spend=PII.amount.sum(), invoice_count=PII.parent.nunique())
            .mutate(category=ibis.coalesce(Item.item_group, ibis.literal("Uncategorized")))
            .order_by(ibis.desc("spend"))
            .limit(15)
            .execute()
            .pipe(_to_records)
        )
        total_cat = sum(float(c.get("spend") or 0) for c in by_category) or 1
        for c in by_category:
            c["pct_of_total"] = round(float(c.get("spend") or 0) / total_cat * 100, 1)

        # Top suppliers
        top_suppliers = (
            PI.filter(PI.posting_date >= today - timedelta(days=365))
            .left_join(Supplier, PI.supplier == Supplier.name)
            .group_by(PI.supplier, Supplier.supplier_name)
            .aggregate(
                invoice_count=PI.name.nunique(),
                spend=PI.grand_total.sum(),
            )
            .order_by(ibis.desc("spend"))
            .limit(10)
            .execute()
            .pipe(_to_records)
        )
        total_sup = sum(float(s.get("spend") or 0) for s in top_suppliers) or 1
        for s in top_suppliers:
            s["pct_of_total"] = round(float(s.get("spend") or 0) / total_sup * 100, 1)

        return {
            "total_spend_12m": float(summary.get("total_spend") or 0),
            "ytd_spend": float(ytd or 0),
            "yoy_growth": round(yoy_growth, 1),
            "invoice_count": int(summary.get("invoice_count") or 0),
            "supplier_count": int(summary.get("supplier_count") or 0),
            "avg_invoice_value": float(summary.get("avg_invoice_value") or 0),
            "monthly_trend": monthly,
            "by_category": by_category,
            "top_suppliers": top_suppliers,
        }

    # --- supplier performance ------------------------------------------------

    def _supplier_performance(self) -> dict[str, Any]:
        from statistics import median as _median

        import pandas as _pd
        from insights.api.ml.ibis_source import t

        PO = t("Purchase Order").filter(lambda x: x.docstatus == 1)
        PR = t("Purchase Receipt").filter(lambda x: x.docstatus == 1)
        PRI = t("Purchase Receipt Item")
        Supplier = t("Supplier")
        today = datetime.now().date()
        cutoff = today - timedelta(days=365)

        # --- PO totals per supplier (unchanged shape) ----------------------
        po_365 = (
            PO.filter(PO.transaction_date >= cutoff)
            .select(PO.name.name("po_name"), PO.supplier, PO.grand_total)
        )
        supplier_slim = Supplier.select(
            Supplier.name.name("supplier_key"), Supplier.supplier_name, Supplier.supplier_group
        )
        suppliers = (
            po_365
            .left_join(supplier_slim, po_365.supplier == supplier_slim.supplier_key)
            .group_by(po_365.supplier, supplier_slim.supplier_name, supplier_slim.supplier_group)
            .aggregate(
                po_count=po_365.po_name.nunique(),
                total_value=po_365.grand_total.sum(),
            )
            .execute()
        )
        if len(suppliers) == 0:
            return {
                "total_suppliers": 0,
                "avg_score": 0,
                "avg_on_time_rate": 0,
                "avg_quality_rate": None,
                "quality_status": "not_implemented",
                "avg_lead_time": 0,
                "top_performers": [],
                "bottom_performers": [],
                "all_suppliers": [],
            }
        # Filter to suppliers with >= 2 POs (matches old HAVING).
        suppliers = suppliers[suppliers["po_count"] >= 2]
        suppliers = suppliers.sort_values("total_value", ascending=False).head(50)

        # Supplier-per-PO lookup, used below to map (PO, PR) rows to
        # their supplier. ``suppliers`` was aggregated; build a separate
        # one-row-per-PO map from the pre-aggregated ``po_365`` so we
        # can resolve a supplier for any PO that surfaces in the lead
        # time or on-time joins.
        po_365_df = po_365.execute()
        po_supplier_map: dict[str, str] = dict(
            zip(po_365_df["po_name"].astype(str), po_365_df["supplier"].astype(str))
        )

        # --- Lead time per supplier -----------------------------------------
        # Mean of (PR.posting_date - PO.transaction_date) over each (PO, PR)
        # pair, where the pair is defined by the Purchase Receipt Item
        # linking back to the PO (``PRI.purchase_order == PO.name``). The
        # previous shape joined PR directly to PO on ``PR.supplier ==
        # PO.supplier`` only, producing a Cartesian product (every PR of a
        # supplier paired with every PO of the same supplier); the
        # 2026-08-04 fix preserved the same bad join. Use PRI.purchase_order
        # so each PR belongs to exactly one PO, and dedup by (PO, PR) since
        # a multi-item PR can have several item rows that all link to the
        # same PO.
        lead_pairs_expr = (
            PO.filter(PO.transaction_date >= cutoff)
            .inner_join(PRI, PRI.purchase_order == PO.name)
            .inner_join(PR, (PRI.parent == PR.name) & (PR.docstatus == 1))
            .select(po=PO.name, pr=PR.name, po_date=PO.transaction_date, pr_date=PR.posting_date)
        )
        lead_pairs = lead_pairs_expr.execute()
        lead_pairs = lead_pairs.drop_duplicates(subset=["po", "pr"])
        lead_time_map: dict[str, float] = {}
        all_leads_for_score: list[float] = []
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
            if len(lead_pairs):
                lead_pairs = lead_pairs.assign(supplier=lead_pairs["po"].map(po_supplier_map))
                lead_pairs = lead_pairs.dropna(subset=["supplier"])
                # Per-(PO, PR) one row, then average within supplier. A PO
                # fulfilled by N partial PRs would have N rows in the mean,
                # but each (PO, PR) is a distinct fulfilment event so this
                # is the right weighting (each delivery counts).
                agg = (
                    lead_pairs.groupby("supplier")["delta_days"].mean().reset_index()
                )
                for _, r in agg.iterrows():
                    lead_time_map[str(r["supplier"])] = round(float(r["delta_days"]), 1)
                all_leads_for_score = list(lead_pairs["delta_days"].astype(float))

        # --- On-time delivery per supplier ----------------------------------
        # Per-PO: a PO is "on time" iff it has at least one PR whose
        # posting_date <= schedule_date. The previous query's ``LEFT JOIN
        # Purchase Receipt ON pr.supplier = po.supplier`` paired every PO
        # with every PR of the same supplier (Cartesian product), so the
        # rate degenerated to the supplier's overall PR on-time rate,
        # independent of which POs they actually fulfilled. Re-link
        # through ``PRI.purchase_order`` so each PR belongs to exactly one
        # PO; aggregate per-PO first, then per-supplier.
        on_time_pairs_expr = (
            PO.filter((PO.transaction_date >= cutoff) & (PO.schedule_date.notnull()))
            .inner_join(PRI, PRI.purchase_order == PO.name)
            .inner_join(PR, (PRI.parent == PR.name) & (PR.docstatus == 1))
            .select(
                po=PO.name,
                pr=PR.name,
                po_schedule=PO.schedule_date,
                pr_date=PR.posting_date,
            )
        )
        on_time_pairs = on_time_pairs_expr.execute()
        on_time_pairs = on_time_pairs.drop_duplicates(subset=["po", "pr"])
        # Need every PO with a schedule_date as the denominator, not just
        # those that already have a PR.
        all_sched_pos = (
            PO.filter((PO.transaction_date >= cutoff) & (PO.schedule_date.notnull()))
            .select(po=PO.name)
            .execute()
        )
        if len(all_sched_pos):
            all_sched_pos = all_sched_pos.assign(
                supplier=all_sched_pos["po"].map(po_supplier_map)
            )
            if len(on_time_pairs):
                on_time_pairs["on_time"] = (
                    on_time_pairs["pr_date"] <= on_time_pairs["po_schedule"]
                )
                po_flags = on_time_pairs.groupby("po")["on_time"].any()
            else:
                po_flags = _pd.Series(dtype=bool)
            all_sched_pos = all_sched_pos.assign(
                on_time=all_sched_pos["po"].map(lambda p: bool(po_flags.get(p, False)))
            )
            all_sched_pos = all_sched_pos.dropna(subset=["supplier"])
            supplier_on_time = (
                all_sched_pos.groupby("supplier")
                .agg(total_orders=("po", "count"), on_time_count=("on_time", "sum"))
                .reset_index()
            )
        else:
            supplier_on_time = _pd.DataFrame(
                columns=["supplier", "total_orders", "on_time_count"]
            )
        on_time_map: dict[str, dict[str, int]] = {
            str(row["supplier"]): {
                "total_orders": int(row["total_orders"]),
                "on_time_count": int(row["on_time_count"] or 0),
            }
            for _, row in supplier_on_time.iterrows()
        }

        # --- Quality rate per supplier --------------------------------------
        # Per-supplier quality signals in ERPNext:
        #   1. Purchase Receipt Item.rejected_qty (goods rejected at receipt)
        #   2. Purchase Receipt Item.returned_qty (goods returned after receipt)
        #   3. Purchase Invoice with is_return=1 (credit-note returns)
        # The previous "quality_rate" used a single global Stock Entry total
        # against per-supplier PO value: on sites with no return Stock
        # Entries (this site has 0), every supplier got 100%, and on any
        # site the result was a per-supplier constant (all suppliers got
        # the same number, scaled by global return_value / own PO value).
        # Replace with per-supplier rejected+returned share of received
        # qty; if neither signal is populated anywhere on the site, expose
        # ``quality_status: "not_implemented"`` and drop the metric from
        # the composite overall_score so the displayed score reflects only
        # signals that actually exist.
        po_for_quality = PO.filter(PO.transaction_date >= cutoff).select(
            PO.name.name("po_name_q"), PO.supplier
        )
        qual_pairs_expr = (
            PRI.join(PR, (PRI.parent == PR.name) & (PR.docstatus == 1), how="inner")
            .join(po_for_quality, PRI.purchase_order == po_for_quality.po_name_q, how="inner")
            .select(
                supplier=po_for_quality.supplier,
                pr=PR.name,
                received_qty=PRI.received_qty,
                rejected_qty=PRI.rejected_qty,
                returned_qty=PRI.returned_qty,
            )
        )
        qual_pairs = qual_pairs_expr.execute()
        if len(qual_pairs):
            qual_pairs = qual_pairs.fillna(0)
            for c in ("received_qty", "rejected_qty", "returned_qty"):
                qual_pairs[c] = qual_pairs[c].astype(float)
            agg_q = (
                qual_pairs.groupby("supplier")
                .agg(
                    received=("received_qty", "sum"),
                    rejected=("rejected_qty", "sum"),
                    returned=("returned_qty", "sum"),
                )
                .reset_index()
            )
        else:
            agg_q = _pd.DataFrame(
                columns=["supplier", "received", "rejected", "returned"]
            )
        quality_map: dict[str, float] = {}
        if len(agg_q):
            total_rejected = float(agg_q["rejected"].sum())
            total_returned = float(agg_q["returned"].sum())
            if total_rejected <= 0 and total_returned <= 0:
                quality_status = "not_implemented"
            else:
                quality_status = "success"
                bad = (agg_q["rejected"] + agg_q["returned"]).clip(lower=0.0)
                denom = agg_q["received"].replace(0, float("nan"))
                good_rate = ((agg_q["received"] - bad) / denom) * 100
                good_rate = good_rate.fillna(100.0).clip(lower=0.0, upper=100.0)
                for i, r in agg_q.reset_index(drop=True).iterrows():
                    quality_map[str(r["supplier"])] = round(float(good_rate.iloc[i]), 1)
        else:
            quality_status = "not_implemented"

        # --- Per-supplier composite score -----------------------------------
        all_rows: list[dict[str, Any]] = []
        site_median_lead = (
            _median(all_leads_for_score) if all_leads_for_score else 0.0
        )
        # Site-relative lead-time anchor: a supplier at the site median
        # gets 50, at 2x the site median gets 0. The previous hardcoded
        # 30-day anchor was below this site's median (~85 days) and
        # therefore clamped every supplier's lead-time contribution to 0.
        lead_anchor = max(1.0, 2.0 * float(site_median_lead))
        for _, s in suppliers.iterrows():
            sup = s["supplier"]
            ot = on_time_map.get(sup, {"total_orders": 0, "on_time_count": 0})
            ot_rate = round(
                (ot["on_time_count"] / ot["total_orders"] * 100)
                if ot["total_orders"] > 0
                else 0,
                1,
            )
            avg_lead = lead_time_map.get(sup, 0.0)
            lead_time_score = max(0.0, 100.0 * (1.0 - avg_lead / lead_anchor))
            volume_score = min(100.0, (int(s.get("po_count") or 0) / 12.0) * 100)
            if quality_status == "success":
                # Original 40/30/20/10 split (on-time / quality / lead / volume).
                q_rate = quality_map.get(sup, 0.0)
                overall = round(
                    ot_rate * 0.40
                    + q_rate * 0.30
                    + lead_time_score * 0.20
                    + volume_score * 0.10,
                    1,
                )
            else:
                # Re-weight the remaining three components to sum to 100.
                # Quality_rate is not exposed (set to None) so the
                # frontend's "On-time | Quality" line shows "N/A" for
                # quality and the score no longer carries a constant
                # 30-point phantom contribution.
                q_rate = None
                overall = round(
                    ot_rate * 0.55
                    + lead_time_score * 0.30
                    + volume_score * 0.15,
                    1,
                )
            all_rows.append(
                {
                    "supplier": sup,
                    "supplier_name": s.get("supplier_name"),
                    "supplier_group": s.get("supplier_group"),
                    "po_count": int(s.get("po_count") or 0),
                    "total_value": float(s.get("total_value") or 0),
                    "avg_lead_time": avg_lead,
                    "on_time_rate": ot_rate,
                    "quality_rate": q_rate,
                    "overall_score": overall,
                }
            )

        all_rows.sort(key=lambda x: x["overall_score"], reverse=True)
        top = all_rows[:10]
        bottom = sorted(all_rows, key=lambda x: x["overall_score"])[:5]

        if all_rows:
            avg_score = sum(r["overall_score"] for r in all_rows) / len(all_rows)
            avg_on_time = sum(r["on_time_rate"] for r in all_rows) / len(all_rows)
            q_vals = [r["quality_rate"] for r in all_rows if r["quality_rate"] is not None]
            avg_quality = (
                round(sum(q_vals) / len(q_vals), 1) if q_vals else None
            )
            avg_lead = sum(r["avg_lead_time"] for r in all_rows) / len(all_rows)
        else:
            avg_score = avg_on_time = avg_lead = 0
            avg_quality = None

        return {
            "total_suppliers": len(all_rows),
            "avg_score": round(avg_score, 1),
            "avg_on_time_rate": round(avg_on_time, 1),
            "avg_quality_rate": avg_quality,
            "quality_status": quality_status,
            "avg_lead_time": round(avg_lead, 1),
            "top_performers": top,
            "bottom_performers": bottom,
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
        cutoff = today - timedelta(days=365)

        # PO status summary
        po_status = (
            PO.filter(PO.transaction_date >= cutoff)
            .group_by(PO.status)
            .aggregate(count=PO.name.count(), value=PO.grand_total.sum())
            .execute()
            .pipe(_to_records)
        )

        # Pending POs
        pending = (
            PO.filter(~PO.status.isin(["Completed", "Closed", "Cancelled"]))
            .select(PO.name, PO.supplier, PO.transaction_date, PO.grand_total, PO.status)
            .mutate(
                days_pending=(today - PO.transaction_date).cast("int32")
            )
            .order_by(ibis.desc("days_pending"))
            .limit(20)
            .execute()
            .pipe(_to_records)
        )

        # Average cycle times — three independently-scoped aggregates, each
        # a single SQL AVG. The pre-fix version chained POI -> MR -> PRI
        # -> PR -> PII -> PI into one join and fetched every combinatorial
        # row into pandas (a PO with 5 items and 3 partial receipts produced
        # 15+ duplicate rows before any averaging happened), which was both
        # the dominant cost of this endpoint (~60% of a 37s total) and
        # biased (multi-item/multi-receipt POs were over-weighted vs.
        # single-line POs). The 2026-08-04 incident fix preserved speed
        # (single SQL AVG) but kept the bias, and surfaced ``NaN`` for
        # sites with no matching pairs in a stage (e.g. no PO->MR link
        # at all on this site made ``avg_mr_to_po_days`` render as
        # ``NaN``). Fix: keep the SQL AVG (cheap), wrap the int32 cast
        # in COALESCE so an empty result is 0 rather than NaN, and live
        # with the per-PR dedup bias (small on most sites — at the jkm
        # bench, 1469/1521 = 96.6% of PO->PR pairs have exactly one PR,
        # so the bias is < 4%). The dedup trade-off isn't worth 6x
        # slower execution; revisit if a site shows wider over-weighting.
        def _mean_days(expr, later_col: str, earlier_col: str) -> float:
            days_expr = (expr[later_col] - expr[earlier_col]).cast("int32")
            # ``.mean()`` returns NULL on empty input; the prior code's
            # round-trip through ``cast("int32")`` produced NaN, which
            # the dashboard rendered literally as "NaN days". Detect
            # NULL/NaN here and return 0.0 instead.
            agg = expr.aggregate(avg_days=days_expr.mean()).execute()
            value = agg["avg_days"].iloc[0] if len(agg) else None
            if value is None or (isinstance(value, float) and value != value):
                return 0.0
            return round(float(value), 1)

        # Each join chains two hops (e.g. PO -> POI -> MR), so an explicit
        # ``select()`` is required before aggregating: ibis's join "finish"
        # step raises IntegrityError on unresolved name collisions (every
        # Frappe doctype table shares name/owner/creation/modified/docstatus/
        # etc.) once a second join is chained on top of the first.
        mr_to_po_expr = (
            PO.filter(PO.transaction_date >= cutoff)
            .inner_join(POI, POI.parent == PO.name)
            .inner_join(MR, POI.material_request == MR.name)
            .select(
                po=PO.name,
                mr=MR.name,
                later=PO.transaction_date,
                earlier=MR.transaction_date,
            )
        )
        avg_mr_to_po = _mean_days(mr_to_po_expr, "later", "earlier")

        po_to_grn_expr = (
            PO.filter(PO.transaction_date >= cutoff)
            .inner_join(PRI, PRI.purchase_order == PO.name)
            .inner_join(PR, (PRI.parent == PR.name) & (PR.docstatus == 1))
            .select(
                po=PO.name,
                pr=PR.name,
                later=PR.posting_date,
                earlier=PO.transaction_date,
            )
        )
        avg_po_to_grn = _mean_days(po_to_grn_expr, "later", "earlier")

        grn_to_inv_expr = (
            PR.filter(PR.posting_date >= cutoff)
            .inner_join(PII, PII.purchase_receipt == PR.name)
            .inner_join(PI, (PII.parent == PI.name) & (PI.docstatus == 1))
            .select(
                pr=PR.name,
                pi=PI.name,
                later=PI.posting_date,
                earlier=PR.posting_date,
            )
        )
        avg_grn_to_inv = _mean_days(grn_to_inv_expr, "later", "earlier")

        # Monthly PO trend
        monthly = (
            PO.filter(PO.transaction_date >= cutoff)
            .group_by(PO.transaction_date.strftime("%Y-%m").name("period"))
            .aggregate(
                po_count=PO.name.count(),
                po_value=PO.grand_total.sum(),
                avg_po_value=PO.grand_total.mean(),
            )
            .order_by("period")
            .execute()
            .pipe(_to_records)
        )

        # GRN completion rate — single SQL aggregate (COUNT(DISTINCT ...)),
        # no row-level fetch (previously pulled every PO x PRI x PR row into
        # pandas just to call nunique() on two columns). ``received_pos`` must
        # count distinct PO names with >=1 submitted receipt, not distinct PR
        # names -- a PO received across several partial receipts would
        # otherwise inflate the numerator past ``total_pos``.
        grn_selected = (
            PO.filter(PO.transaction_date >= today - timedelta(days=180))
            .left_join(PRI, PRI.purchase_order == PO.name)
            .left_join(PR, (PRI.parent == PR.name) & (PR.docstatus == 1))
            .select(po_name=PO.name, pr_name=PR.name)
        )
        grn_agg = grn_selected.aggregate(
            total_pos=grn_selected.po_name.nunique(),
            received_pos=grn_selected.po_name.nunique(where=grn_selected.pr_name.notnull()),
        ).execute()
        total_pos = int(grn_agg["total_pos"].iloc[0]) if len(grn_agg) else 0
        received = int(grn_agg["received_pos"].iloc[0]) if len(grn_agg) else 0
        grn_completion = round((received / total_pos * 100), 1) if total_pos > 0 else 0

        # Total & overdue PO counts. Mirrors get_procurement_detail's
        # total_pos / overdue_pos drill-down filters exactly (docstatus=1,
        # all-time for the total; docstatus=1 + schedule_date < today +
        # status not terminal for overdue) so these KPI cards agree with
        # what their own drill-down panel lists.
        po_volume_agg = PO.aggregate(
            total_po_count=PO.name.count(),
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
            "pending_count": len(pending),
            "pending_value": sum(float(p.get("grand_total") or 0) for p in pending),
            "avg_mr_to_po_days": avg_mr_to_po,
            "avg_po_to_grn_days": avg_po_to_grn,
            "avg_grn_to_invoice_days": avg_grn_to_inv,
            "monthly_trend": monthly,
            "grn_completion_rate": grn_completion,
            "total_po_count": total_po_count,
            "overdue_po_count": overdue_po_count,
        }

    # --- price intelligence --------------------------------------------------

    def _price_intelligence(self) -> dict[str, Any]:
        from insights.api.ml.ibis_source import t

        PII = t("Purchase Invoice Item")
        PI = t("Purchase Invoice").filter(lambda x: x.docstatus == 1)
        Item = t("Item")
        Supplier = t("Supplier")
        today = datetime.now().date()
        cutoff = today - timedelta(days=365)

        # Per-item rate stats + last rate. Filter parent PI BEFORE the
        # semi-join (the right-side relation is gone afterwards).
        pi_cutoff = PI.filter(PI.posting_date >= cutoff)

        # Step 1: per-item rate aggregates
        per_item = (
            PII.join(pi_cutoff, PII.parent == pi_cutoff.name, how="semi")
            .group_by(PII.item_code)
            .aggregate(
                purchase_count=PII.parent.nunique(),
                avg_rate=PII.rate.mean(),
                min_rate=PII.rate.min(),
                max_rate=PII.rate.max(),
            )
            .filter(lambda x: x.purchase_count >= 3)
            .execute()
        )
        # Last rate: per-item, row with max posting_date. Needs
        # `pi_cutoff.posting_date`, which a semi-join can't expose --
        # inner join instead (safe: `pi_cutoff.name` is a primary key).
        last_df_proj = (
            PII.join(pi_cutoff, PII.parent == pi_cutoff.name, how="inner")
            .select(PII.item_code, PII.rate, pi_cutoff.posting_date)
        )
        last_df = (
            last_df_proj
            .order_by(PII.item_code, ibis.desc("posting_date"))
            .execute()
        )
        last_rate_map: dict[str, float] = {}
        for item_code, grp in last_df.groupby("item_code", sort=False):
            last_rate_map[item_code] = float(grp.iloc[0]["rate"] or 0)

        # Item metadata
        items = Item.filter(Item.disabled == 0).select(Item.name, Item.item_name, Item.item_group).execute()
        item_meta = {r["name"]: r for _, r in items.iterrows()}

        # Build variance records
        records = []
        for _, r in per_item.iterrows():
            item = r["item_code"]
            avg = float(r.get("avg_rate") or 0) or 1
            last = float(last_rate_map.get(item, avg) or avg)
            mn = float(r.get("min_rate") or avg)
            mx = float(r.get("max_rate") or avg)
            records.append(
                {
                    "item_code": item,
                    "item_name": item_meta.get(item, {}).get("item_name") if item in item_meta else None,
                    "item_group": item_meta.get(item, {}).get("item_group") if item in item_meta else None,
                    "purchase_count": int(r.get("purchase_count") or 0),
                    "avg_rate": avg,
                    "min_rate": mn,
                    "max_rate": mx,
                    "last_rate": last,
                    "price_variance_pct": round(((last - avg) / avg) * 100, 1) if avg > 0 else 0,
                    "price_range_pct": round(((mx - mn) / avg) * 100, 1) if avg > 0 else 0,
                    "potential_savings": round((last - mn) * int(r.get("purchase_count") or 0), 2),
                }
            )

        records.sort(key=lambda x: x["purchase_count"], reverse=True)
        price_increases = sorted(
            [r for r in records if r["price_variance_pct"] > 5],
            key=lambda x: x["price_variance_pct"],
            reverse=True,
        )
        volatile = sorted(
            [r for r in records if r["price_range_pct"] > 20],
            key=lambda x: x["price_range_pct"],
            reverse=True,
        )

        # Best supplier per item (cheapest min rate). Needs
        # `pi_cutoff.supplier`, which a semi-join can't expose -- inner
        # join instead (safe: `pi_cutoff.name` is a primary key).
        best_df = (
            PII.join(pi_cutoff, PII.parent == pi_cutoff.name, how="inner")
            .group_by([PII.item_code, pi_cutoff.supplier])
            .aggregate(best_rate=PII.rate.min(), purchase_count=PII.parent.nunique())
            .order_by(["item_code", "best_rate"])
            .execute()
        )
        best_suppliers: list[dict[str, Any]] = []
        if len(best_df):
            sup_names = Supplier.select(Supplier.name, Supplier.supplier_name).execute()
            sup_name_map = dict(zip(sup_names["name"], sup_names["supplier_name"]))
            seen = set()
            for _, r in best_df.iterrows():
                item = r["item_code"]
                if item in seen:
                    continue
                seen.add(item)
                sup = r["supplier"]
                best_suppliers.append(
                    {
                        "item_code": item,
                        "item_name": item_meta.get(item, {}).get("item_name"),
                        "supplier": sup,
                        "supplier_name": sup_name_map.get(sup),
                        "best_rate": float(r["best_rate"] or 0),
                        "purchase_count": int(r["purchase_count"] or 0),
                    }
                )
                if len(best_suppliers) >= 20:
                    break

        total_potential_savings = round(
            sum(float(r.get("potential_savings") or 0) for r in records), 2
        )

        return {
            "price_variance_items": records[:20],
            "price_increases": price_increases[:10],
            "volatile_items": volatile[:10],
            "best_price_suppliers": best_suppliers,
            "total_potential_savings": total_potential_savings,
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
        cutoff = today - timedelta(days=365)

        # Supplier concentration
        total_spend_expr = PI.filter(PI.posting_date >= cutoff).aggregate(
            total=PI.grand_total.sum()
        )
        total_spend = float(total_spend_expr.execute().iloc[0]["total"] or 0) or 1

        supplier_conc = (
            PI.filter(PI.posting_date >= cutoff)
            .left_join(Supplier, PI.supplier == Supplier.name)
            .group_by(PI.supplier, Supplier.supplier_name)
            .aggregate(spend=PI.grand_total.sum())
            .order_by(ibis.desc("spend"))
            .limit(10)
            .execute()
            .pipe(_to_records)
        )
        for s in supplier_conc:
            spend = float(s.get("spend") or 0)
            pct = round(spend / total_spend * 100, 1) if total_spend > 0 else 0
            s["concentration_pct"] = pct
            s["total_spend"] = total_spend
            s["risk_level"] = "High" if pct > 30 else ("Medium" if pct > 15 else "Low")

        # Single-source items. Needs `pi_365.supplier`, which a semi-join
        # can't expose -- inner join instead (safe: `pi_365.name` is a
        # primary key, so no row multiplication).
        pi_365 = PI.filter(PI.posting_date >= cutoff)
        single_source = (
            PII.join(pi_365, PII.parent == pi_365.name, how="inner")
            .group_by(PII.item_code)
            .aggregate(
                supplier_count=pi_365.supplier.nunique(),
                total_spend=PII.amount.sum(),
            )
            .filter(lambda x: (x.supplier_count == 1) & (x.total_spend > 10000))
            .order_by(ibis.desc("total_spend"))
            .limit(20)
            .execute()
        )
        # Add item + supplier details
        if len(single_source):
            items_meta = Item.filter(Item.name.isin(list(single_source["item_code"]))).select(
                Item.name, Item.item_name, Item.item_group
            ).execute()
            item_meta_map = {r["name"]: r for _, r in items_meta.iterrows()}
            # Find the only supplier per item (re-use the pre-filtered pi_365)
            only_sup = (
                PII.join(pi_365, PII.parent == pi_365.name, how="inner")
                .group_by(PII.item_code)
                .aggregate(only_supplier=pi_365.supplier.max())
                .filter(lambda x: x.item_code.isin(list(single_source["item_code"])))
                .execute()
            )
            only_sup_map = dict(zip(only_sup["item_code"], only_sup["only_supplier"]))
            ss_records = []
            for _, r in single_source.iterrows():
                meta = item_meta_map.get(r["item_code"], {})
                ss_records.append(
                    {
                        "item_code": r["item_code"],
                        "item_name": meta.get("item_name"),
                        "item_group": meta.get("item_group"),
                        "supplier_count": 1,
                        "total_spend": float(r["total_spend"] or 0),
                        "only_supplier": only_sup_map.get(r["item_code"]),
                    }
                )
        else:
            ss_records = []

        # Payment exposure
        payment_exposure = (
            PI.filter(PI.outstanding_amount > 0)
            .left_join(Supplier, PI.supplier == Supplier.name)
            .group_by(PI.supplier, Supplier.supplier_name)
            .aggregate(
                outstanding=PI.outstanding_amount.sum(),
                invoice_count=PI.name.count(),
                earliest_due=PI.due_date.min(),
            )
            .order_by(ibis.desc("outstanding"))
            .limit(15)
            .execute()
            .pipe(_to_records)
        )

        total_outstanding = float(
            PI.filter(PI.outstanding_amount > 0)
            .aggregate(total=PI.outstanding_amount.sum())
            .execute()
            .iloc[0]["total"]
            or 0
        )

        # Overdue invoices
        overdue_invoices = (
            PI.filter(
                (PI.outstanding_amount > 0) & (PI.due_date < today)
            )
            .select(
                PI.name,
                PI.supplier,
                PI.posting_date,
                PI.due_date,
                PI.grand_total,
                PI.outstanding_amount,
            )
            .mutate(days_overdue=(today - PI.due_date).cast("int32"))
            .order_by(ibis.desc("days_overdue"))
            .limit(20)
            .execute()
            .pipe(_to_records)
        )

        overdue_totals = (
            PI.filter((PI.outstanding_amount > 0) & (PI.due_date < today))
            .aggregate(count=PI.name.count(), value=PI.outstanding_amount.sum())
            .execute()
            .iloc[0]
        )
        overdue_count = int(overdue_totals.get("count") or 0)
        overdue_value = float(overdue_totals.get("value") or 0)

        high_conc_count = sum(1 for s in supplier_conc if s.get("concentration_pct", 0) > 30)
        single_source_value = sum(float(r.get("total_spend") or 0) for r in ss_records)
        # Risk score on a 0-100 scale, bounded properly. The previous
        # formula ``high_conc_count*15 + single_source_count*2 +
        # overdue_value/100000`` saturated at 100 on this site from
        # overdue_value/100000 alone (10.88M / 100k = 108.8, capped to
        # 100) — every site with > $8M in overdue invoices got a 100/100
        # risk score regardless of concentration or single-source
        # exposure. Replace the un-bounded /100000 term with a
        # normalized share: overdue as a fraction of total annual spend,
        # capped to 1.0 (which contributes 40 to the score).
        overdue_share = (
            (overdue_value / total_spend) if total_spend > 0 else 0.0
        )
        overdue_component = min(40.0, overdue_share * 100.0 * 0.4)
        risk_score = min(
            100.0,
            (high_conc_count * 15.0)
            + (len(ss_records) * 2.0)
            + overdue_component,
        )

        return {
            "risk_score": round(risk_score, 1),
            "supplier_concentration": supplier_conc,
            "high_concentration_count": high_conc_count,
            "single_source_items": ss_records,
            "single_source_count": len(ss_records),
            "single_source_value": single_source_value,
            "payment_exposure": payment_exposure,
            "total_outstanding": total_outstanding,
            "overdue_invoices": overdue_invoices,
            "overdue_count": overdue_count,
            "overdue_value": overdue_value,
        }

    # --- forecasting ---------------------------------------------------------

    def _forecast(self) -> dict[str, Any]:
        from insights.api.ml.ibis_source import t

        PI = t("Purchase Invoice").filter(lambda x: x.docstatus == 1)
        PII = t("Purchase Invoice Item")
        Item = t("Item")
        today = datetime.now().date()
        cutoff = today - timedelta(days=730)

        # Monthly spend (24 months)
        monthly = (
            PI.filter(PI.posting_date >= cutoff)
            .group_by(PI.posting_date.strftime("%Y-%m").name("period"))
            .aggregate(spend=PI.grand_total.sum())
            .order_by("period")
            .execute()
            .pipe(_to_records)
        )

        if len(monthly) < 6:
            return {
                "status": "insufficient_data",
                "message": "Need at least 6 months of data for forecasting",
                "historical": monthly,
            }

        # Linear-trend projection (3 months)
        values = [float(m["spend"] or 0) for m in monthly]
        slope, intercept = _linear_trend(values)
        n = len(values)
        forecasts: list[dict[str, Any]] = []
        for i in range(1, 4):
            future = today + timedelta(days=30 * i)
            predicted = max(0.0, intercept + slope * (n + i - 1))
            forecasts.append(
                {
                    "period": future.strftime("%Y-%m"),
                    "predicted_spend": round(predicted, 2),
                    "confidence": "Medium" if i <= 2 else "Low",
                }
            )

        avg_spend = round(sum(values[-6:]) / 6.0, 2)
        trend = "up" if slope > 0 else "down"
        trend_amount = round(abs(slope), 2)

        # Seasonal pattern: by month-of-year
        seasonal_df = (
            PI.filter(PI.posting_date >= cutoff)
            .group_by(PI.posting_date.strftime("%m").name("month"))
            .aggregate(spend=PI.grand_total.sum())
            .execute()
        )
        seasonal = {
            str(int(r["month"])): round(float(r["spend"] or 0) / 2.0, 2)  # avg over 2 years
            for _, r in seasonal_df.iterrows()
        }

        # Category-level forecast (top 10, 2% growth assumption).
        # Filter parent PI BEFORE the semi-join.
        pi_12m = PI.filter(PI.posting_date >= today - timedelta(days=365))
        category = (
            PII.join(pi_12m, PII.parent == pi_12m.name, how="semi")
            .left_join(Item, PII.item_code == Item.name)
            .group_by(Item.item_group)
            .aggregate(
                avg_monthly_spend=PII.amount.mean(),
                total_12m=PII.amount.sum(),
            )
            .mutate(category=ibis.coalesce(Item.item_group, ibis.literal("Uncategorized")))
            .order_by(ibis.desc("total_12m"))
            .limit(10)
            .execute()
            .pipe(_to_records)
        )
        for c in category:
            c["forecast_3m"] = round(float(c.get("avg_monthly_spend") or 0) * 3 * 1.02, 2)

        return {
            "status": "success",
            "historical": monthly,
            "forecasts": forecasts,
            "avg_monthly_spend": avg_spend,
            "trend_direction": trend,
            "trend_amount": trend_amount,
            "seasonal_pattern": seasonal,
            "category_forecast": category,
        }


# ---------------------------------------------------------------------------
# Module-level wrappers
# ---------------------------------------------------------------------------


def run_procurement_intelligence(refresh: bool = False) -> dict[str, Any]:
    """Run procurement intelligence analysis."""
    return ProcurementIntelligence().train()
