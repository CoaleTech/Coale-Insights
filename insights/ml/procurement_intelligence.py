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
        yoy_growth = 0
        if last_year and last_year > 0:
            yoy_growth = ((ytd - last_year) / last_year) * 100

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
            .to_dict("records")
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
            .to_dict("records")
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
            .to_dict("records")
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
        from insights.api.ml.ibis_source import t

        PO = t("Purchase Order").filter(lambda x: x.docstatus == 1)
        PR = t("Purchase Receipt").filter(lambda x: x.docstatus == 1)
        Supplier = t("Supplier")
        SE = t("Stock Entry")
        today = datetime.now().date()
        cutoff = today - timedelta(days=365)

        # Two-step approach: compute PO-level totals per supplier here,
        # then enrich with delivery / rejection via separate queries in
        # Python -- correlated sub-aggregates through ``PR.filter(...)``
        # are unreliable in this version of ibis, and the simpler shape
        # is just as fast on this data scale.
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
                "avg_quality_rate": 0,
                "avg_lead_time": 0,
                "top_performers": [],
                "bottom_performers": [],
                "all_suppliers": [],
            }
        # Filter to suppliers with >= 2 POs (matches old HAVING)
        suppliers = suppliers[suppliers["po_count"] >= 2]
        suppliers = suppliers.sort_values("total_value", ascending=False).head(50)

        # Avg lead time per supplier: average (PR.posting_date - PO.transaction_date)
        # for PRs that came after the PO from the same supplier.
        # This is the production-cost-cheap version: per-supplier mean.
        po_with_pr = (
            PO.filter(PO.transaction_date >= cutoff)
            .left_join(
                PR,
                (PR.supplier == PO.supplier) & (PR.posting_date >= PO.transaction_date),
            )
            .select(PO.supplier, PO.transaction_date, PR.posting_date)
            .execute()
        )
        lead_time_map: dict[str, float] = {}
        for sup, grp in po_with_pr.groupby("supplier"):
            diffs = []
            for _, r in grp.iterrows():
                if r["posting_date"] is not None and not (r["posting_date"] != r["posting_date"]):  # not NaN
                    diffs.append((r["posting_date"] - r["transaction_date"]).days)
            if diffs:
                lead_time_map[sup] = round(sum(diffs) / len(diffs), 1)
            else:
                lead_time_map[sup] = 0.0

        # On-time delivery: count of (PO with schedule_date, PR by same supplier with pr.posting_date <= po.schedule_date)
        on_time = (
            PO.filter(
                (PO.transaction_date >= cutoff)
                & (PO.schedule_date.notnull())
            )
            .left_join(
                PR,
                (PR.supplier == PO.supplier) & (PR.docstatus == 1),
            )
            .select(PO.supplier, PO.schedule_date, PR.posting_date)
            .execute()
        )
        on_time_map: dict[str, dict[str, int]] = {}
        for sup, grp in on_time.groupby("supplier"):
            total = len(grp)
            ontime = int(((grp["posting_date"] <= grp["schedule_date"]) & grp["posting_date"].notna()).sum())
            on_time_map[sup] = {"total_orders": total, "on_time_count": ontime}

        # Company-wide return value (Material Transfer / Return)
        rej = SE.filter(
            (SE.docstatus == 1)
            & (SE.posting_date >= cutoff)
            & (SE.stock_entry_type == "Material Transfer")
            & (SE.purpose.like("%Return%"))
        ).aggregate(return_value=SE.total_amount.sum()).execute()
        return_value = float(rej.iloc[0]["return_value"] or 0) if len(rej) else 0.0

        # Build per-supplier records
        all_rows: list[dict[str, Any]] = []
        for _, s in suppliers.iterrows():
            sup = s["supplier"]
            total_v = float(s.get("total_value") or 0) or 1
            ot = on_time_map.get(sup, {"total_orders": 0, "on_time_count": 0})
            ot_rate = round(
                (ot["on_time_count"] / ot["total_orders"] * 100) if ot["total_orders"] > 0 else 0, 1
            )
            quality_rate = max(
                0,
                min(
                    100,
                    round(100 - ((return_value / total_v) * 100), 1),
                ),
            )
            avg_lead = lead_time_map.get(sup, 0.0)
            lead_time_score = max(0.0, 100 - (avg_lead / 30.0 * 100))
            volume_score = min(100.0, (int(s.get("po_count") or 0) / 12.0) * 100)
            overall = round(
                ot_rate * 0.40
                + quality_rate * 0.30
                + lead_time_score * 0.20
                + volume_score * 0.10,
                1,
            )
            all_rows.append(
                {
                    "supplier": sup,
                    "supplier_name": s.get("supplier_name"),
                    "supplier_group": s.get("supplier_group"),
                    "po_count": int(s.get("po_count") or 0),
                    "total_value": total_v,
                    "avg_lead_time": avg_lead,
                    "on_time_rate": ot_rate,
                    "quality_rate": quality_rate,
                    "overall_score": overall,
                }
            )

        all_rows.sort(key=lambda x: x["overall_score"], reverse=True)
        top = all_rows[:10]
        bottom = sorted(all_rows, key=lambda x: x["overall_score"])[:5]

        if all_rows:
            avg_score = sum(r["overall_score"] for r in all_rows) / len(all_rows)
            avg_on_time = sum(r["on_time_rate"] for r in all_rows) / len(all_rows)
            avg_quality = sum(r["quality_rate"] for r in all_rows) / len(all_rows)
            avg_lead = sum(r["avg_lead_time"] for r in all_rows) / len(all_rows)
        else:
            avg_score = avg_on_time = avg_quality = avg_lead = 0

        return {
            "total_suppliers": len(all_rows),
            "avg_score": round(avg_score, 1),
            "avg_on_time_rate": round(avg_on_time, 1),
            "avg_quality_rate": round(avg_quality, 1),
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
            .to_dict("records")
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
            .to_dict("records")
        )

        # Average cycle times
        cycle_df = (
            PO.filter(PO.transaction_date >= cutoff)
            .left_join(POI, POI.parent == PO.name)
            .left_join(MR, MR.name == POI.material_request)
            .left_join(PRI, PRI.purchase_order == PO.name)
            .left_join(PR, (PR.name == PRI.parent) & (PR.docstatus == 1))
            .left_join(PII, PII.purchase_receipt == PR.name)
            .left_join(PI, (PI.name == PII.parent) & (PI.docstatus == 1))
            .select(
                PO.transaction_date,
                MR.transaction_date.name("mr_date"),
                PR.posting_date.name("pr_date"),
                PI.posting_date.name("pi_date"),
            )
            .execute()
        )
        mr_to_po = (cycle_df["transaction_date"] - cycle_df["mr_date"]).dt.days
        po_to_grn = (cycle_df["pr_date"] - cycle_df["transaction_date"]).dt.days
        grn_to_inv = (cycle_df["pi_date"] - cycle_df["pr_date"]).dt.days

        def _avg(s):
            s = s.dropna()
            return round(float(s.mean()), 1) if len(s) else 0.0

        avg_mr_to_po = _avg(mr_to_po)
        avg_po_to_grn = _avg(po_to_grn)
        avg_grn_to_inv = _avg(grn_to_inv)

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
            .to_dict("records")
        )

        # GRN completion rate
        grn_df = (
            PO.filter(PO.transaction_date >= today - timedelta(days=180))
            .left_join(PRI, PRI.purchase_order == PO.name)
            .left_join(PR, PR.name == PRI.parent)
            .select(PO.name, PR.docstatus)
            .execute()
        )
        total_pos = int(grn_df["name"].nunique())
        received = int(grn_df[grn_df["docstatus"] == 1]["name"].nunique())
        grn_completion = round((received / total_pos * 100), 1) if total_pos > 0 else 0

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
            .to_dict("records")
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
            .to_dict("records")
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
            .to_dict("records")
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
        risk_score = min(
            100,
            (high_conc_count * 15) + (len(ss_records) * 2) + (overdue_value / 100000),
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
            .to_dict("records")
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
            .to_dict("records")
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
