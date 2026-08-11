from __future__ import annotations

# Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""
Inventory Intelligence — Ibis rewrite.

The previous implementation was a pandas/scikit-learn pipeline that loaded
``Stock Ledger Entry`` / ``Sales Invoice Item`` rows into a DataFrame in
process and ran isolation-forest / KMeans-style operations in the web
worker. On Frappe Cloud, that worker forks via RQ, and forking a
multithreaded Python (GC + glibc + RQ heartbeat + OpenBLAS thread pool) is
undefined per POSIX — it segfaulted the entire session with signal 11.

Every metric this domain used to compute is now expressed as one or two
SQL aggregates that the database executes, returning only the final,
already-aggregated rows. There is no model to train, no background job, no
fork, and no in-process ML library import.
"""

import math
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

import frappe
import ibis

if TYPE_CHECKING:
    import pandas as pd  # noqa: F401  (kept for type hints; not imported at runtime)


# ---------------------------------------------------------------------------
# Pure-Python trend / quantile helpers
#
# These run on a handful of aggregated rows (a few dozen at most) -- not
# raw transactional rows. They live here, not in `utils.py`, because no
# other domain needs them and they are not generic SQL helpers.
# ---------------------------------------------------------------------------


def _linear_trend(values: list[float]) -> tuple[float, float]:
    """Return (slope, intercept) of a least-squares line over `values`
    using closed-form sums. 24 datapoints is fine; no numpy needed."""
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


def _projection(values: list[float], periods: int) -> list[float]:
    """Linear-trend projection of `periods` future points."""
    slope, intercept = _linear_trend(values)
    n = len(values)
    return [max(0.0, intercept + slope * (n + i)) for i in range(periods)]


def _health_score(total_value: float, overstock_count: int, low_stock_count: int, out_of_stock_count: int) -> float:
    """0-100 inventory health score. Higher is healthier.

    Same weighting the old code used; this just operates on the four
    already-aggregated counts, not on row-level data.
    """
    if total_value <= 0:
        return 50.0
    overstock_pct = (overstock_count * 1000) / total_value  # rough scaling
    low_stock_pct = (low_stock_count * 1500) / total_value
    oos_pct = (out_of_stock_count * 2000) / total_value
    score = 100 - (overstock_pct * 0.3 + low_stock_pct * 0.5 + oos_pct * 0.7)
    return round(max(0, min(100, score)), 1)


# ---------------------------------------------------------------------------
# Inventory Intelligence
# ---------------------------------------------------------------------------


class InventoryIntelligence:
    """Compute inventory intelligence directly in MariaDB via Ibis.

    The historical class extended ``BaseMLModel`` (which carried the
    cache/warming/lock machinery that has now been removed). The new
    implementation does not need any of that: each method issues one or
    two SQL aggregates and returns the result.
    """

    def __init__(self, date_filter: str = "12m"):
        self.date_filter = date_filter

    # --- public entry points -------------------------------------------------

    def train(self) -> dict[str, Any]:
        """Compute the full inventory intelligence payload.

        Equivalent to the old ``train()`` -- just no cache to fill.
        """
        try:
            return {
                "status": "success",
                "generated_at": datetime.now().isoformat(),
                "date_filter": self.date_filter,
                "stock_overview": self._stock_overview(),
                "turnover_analysis": self._turnover_analysis(),
                "aging_analysis": self._aging_analysis(),
                "warehouse_analysis": self._warehouse_analysis(),
                "procurement_insights": self._procurement_insights(),
                "dead_stock": self._dead_stock(),
                "transfer_recommendations": self._transfer_recommendations(),
            }
        except Exception as e:
            frappe.log_error(frappe.get_traceback(), "Inventory Intelligence failed")
            return {"status": "error", "message": str(e)}

    def predict(self) -> dict[str, Any]:
        """Backward-compatible alias; there is no cached state to read."""
        return self.train()

    # --- stock overview ------------------------------------------------------

    def _stock_overview(self) -> dict[str, Any]:
        from insights.api.ml.ibis_source import t

        Bin = t("Bin")

        # Stock summary
        stock = (
            Bin.filter((Bin.actual_qty != 0) | (Bin.reserved_qty != 0) | (Bin.ordered_qty != 0))
            .aggregate(
                total_skus=Bin.item_code.nunique(),
                total_qty=Bin.actual_qty.sum(),
                total_value=(Bin.actual_qty * Bin.valuation_rate).sum(),
                out_of_stock_count=ibis.ifelse(Bin.actual_qty <= 0, 1, 0).sum(),
                warehouse_count=Bin.warehouse.nunique(),
            )
            .execute()
            .iloc[0]
        )

        # Per-item average daily sales (last 90 days), so we can compare to
        # current stock for over/low-stock detection in one pass.
        sales_90d = _per_item_avg_daily_sales(90)

        # Bring the sales figure back to Bin via a left join
        Bin_with_sales = Bin.left_join(
            sales_90d, Bin.item_code == sales_90d.item_code
        ).select(
            Bin.item_code,
            Bin.warehouse,
            Bin.actual_qty,
            Bin.valuation_rate,
            sales_90d.avg_daily_sales,
        )

        # Overstocked: actual > 90 days of supply, AND we have actual sales
        overstock = (
            Bin_with_sales.filter(
                (Bin_with_sales.actual_qty > 0)
                & (Bin_with_sales.avg_daily_sales.notnull())
                & (Bin_with_sales.avg_daily_sales > 0)
                & (Bin_with_sales.actual_qty > Bin_with_sales.avg_daily_sales * 90)
            )
            .aggregate(overstock_count=Bin_with_sales.item_code.nunique())
            .execute()
            .iloc[0]["overstock_count"]
        )

        # Low stock: actual < 14 days of supply but positive, AND sales
        low_stock = (
            Bin_with_sales.filter(
                (Bin_with_sales.actual_qty > 0)
                & (Bin_with_sales.avg_daily_sales.notnull())
                & (Bin_with_sales.avg_daily_sales > 0)
                & (Bin_with_sales.actual_qty < Bin_with_sales.avg_daily_sales * 14)
            )
            .aggregate(low_stock_count=Bin_with_sales.item_code.nunique())
            .execute()
            .iloc[0]["low_stock_count"]
        )

        # Stock by item group
        Item = t("Item")
        by_group = (
            Bin.filter(Bin.actual_qty > 0)
            .left_join(Item, Bin.item_code == Item.name)
            .group_by(Item.item_group)
            .aggregate(
                item_count=Bin.item_code.nunique(),
                total_qty=Bin.actual_qty.sum(),
                stock_value=(Bin.actual_qty * Bin.valuation_rate).sum(),
            )
            .mutate(item_group=ibis.coalesce(Item.item_group, ibis.literal("Uncategorized")))
            .order_by(ibis.desc("stock_value"))
            .limit(15)
            .execute()
            .to_dict("records")
        )

        total_value = float(stock.get("total_value") or 0)
        total_qty = float(stock.get("total_qty") or 0)
        overstock_count = int(overstock or 0)
        low_stock_count = int(low_stock or 0)
        out_of_stock_count = int(stock.get("out_of_stock_count") or 0)

        return {
            "total_skus": int(stock.get("total_skus") or 0),
            "total_qty": total_qty,
            "total_value": total_value,
            "out_of_stock_count": out_of_stock_count,
            "overstock_count": overstock_count,
            "low_stock_count": low_stock_count,
            "warehouse_count": int(stock.get("warehouse_count") or 0),
            "by_item_group": by_group,
            "health_score": _health_score(
                total_value, overstock_count, low_stock_count, out_of_stock_count
            ),
        }

    # --- turnover analysis ---------------------------------------------------

    def _turnover_analysis(self) -> dict[str, Any]:
        from insights.api.ml.ibis_source import t

        Bin = t("Bin")
        Item = t("Item")
        sii = t("Sales Invoice Item")
        cutoff_12m = (datetime.now() - timedelta(days=365)).date()
        cutoff_90d = (datetime.now() - timedelta(days=90)).date()
        # Filter the parent table BEFORE semi-join: a semi-join returns
        # the LEFT-side columns only, so any predicate on `si.*` after
        # the join references a relation no longer in scope.
        si = t("Sales Invoice").filter(
            lambda x: (x.docstatus == 1) & (x.posting_date >= cutoff_12m)
        )
        si_90 = t("Sales Invoice").filter(
            lambda x: (x.docstatus == 1) & (x.posting_date >= cutoff_90d)
        )

        # COGS last 12 months (sum of sales invoice item amounts)
        cogs_expr = (
            sii.join(si, sii.parent == si.name, how="semi")
            .select(sii.amount)
            .aggregate(cogs_12m=sii.amount.sum())
        )
        # Current stock value (positive stock only)
        inv_expr = Bin.filter(Bin.actual_qty > 0).aggregate(
            avg_inventory=(Bin.actual_qty * Bin.valuation_rate).sum()
        )

        cogs_df = cogs_expr.execute()
        inv_df = inv_expr.execute()
        cogs = float(cogs_df.iloc[0]["cogs_12m"] or 0)
        avg_inventory = float(inv_df.iloc[0]["avg_inventory"] or 1)
        turnover_ratio = cogs / avg_inventory if avg_inventory > 0 else 0
        days_sales_inventory = 365 / turnover_ratio if turnover_ratio > 0 else 0

        # Per-item-group turnover
        by_group_sales = (
            sii.join(si, sii.parent == si.name, how="semi")
            .select(sii.item_code, sii.amount)
            .left_join(Item, sii.item_code == Item.name)
            .group_by(Item.item_group)
            .aggregate(sales_12m=sii.amount.sum())
            .mutate(item_group=ibis.coalesce(Item.item_group, ibis.literal("Uncategorized")))
            .order_by(ibis.desc("sales_12m"))
            .limit(10)
            .execute()
        )

        by_group_stock = (
            Bin.filter(Bin.actual_qty > 0)
            .left_join(Item, Bin.item_code == Item.name)
            .group_by(Item.item_group)
            .aggregate(stock_value=(Bin.actual_qty * Bin.valuation_rate).sum())
            .mutate(item_group=ibis.coalesce(Item.item_group, ibis.literal("Uncategorized")))
            .execute()
        )
        stock_map = dict(zip(by_group_stock["item_group"], by_group_stock["stock_value"]))

        by_group = []
        for _, row in by_group_sales.iterrows():
            group = row["item_group"]
            stock_val = float(stock_map.get(group, 0) or 0)
            sales = float(row["sales_12m"] or 0)
            if stock_val > 0:
                ratio = round(sales / stock_val, 2)
                dsi = round(365 / ratio, 0) if ratio > 0 else 999
            else:
                ratio = 0
                dsi = 999
            by_group.append(
                {
                    "item_group": group,
                    "sales_12m": sales,
                    "current_stock_value": stock_val,
                    "turnover_ratio": ratio,
                    "dsi": dsi,
                }
            )

        # Fast-moving items (last 90 days, using the date-restricted SI)
        fast_moving = (
            sii.join(si_90, sii.parent == si_90.name, how="semi")
            .group_by(sii.item_code, sii.item_name)
            .aggregate(
                qty_sold=sii.qty.sum(),
                sales_value=sii.amount.sum(),
            )
            .order_by(ibis.desc("qty_sold"))
            .limit(10)
            .execute()
            .to_dict("records")
        )
        # Current stock per fast-moving item
        if fast_moving:
            fast_codes = [r["item_code"] for r in fast_moving]
            stock_now = (
                Bin.filter(Bin.item_code.isin(fast_codes))
                .group_by(Bin.item_code)
                .aggregate(current_stock=Bin.actual_qty.sum())
                .execute()
            )
            stock_map_fm = dict(zip(stock_now["item_code"], stock_now["current_stock"]))
            for r in fast_moving:
                r["current_stock"] = float(stock_map_fm.get(r["item_code"], 0) or 0)

        # Slow-moving: positive stock, low sales over 90 days. Build the
        # base per-item-sales table first, THEN mutate to add a 90-day
        # qty column -- referencing the table inside its own definition
        # is the classic forward-ref bug.
        base_sales = _per_item_avg_daily_sales(90)
        sales_90d = base_sales.mutate(qty_sold_90d=base_sales.avg_daily_sales * 90)
        slow_moving = (
            Bin.filter(Bin.actual_qty > 0)
            .left_join(Item, Bin.item_code == Item.name)
            .left_join(sales_90d, Bin.item_code == sales_90d.item_code)
            .select(
                Bin.item_code,
                Item.item_name,
                Bin.actual_qty,
                Bin.valuation_rate,
                sales_90d.qty_sold_90d,
            )
            .mutate(stock_value=Bin.actual_qty * Bin.valuation_rate)
            .mutate(qty_sold_90d=ibis.coalesce(sales_90d.qty_sold_90d, 0.0))
            .mutate(current_stock=Bin.actual_qty)
            .order_by("qty_sold_90d", ibis.desc("stock_value"))
            .limit(10)
            .execute()
            .to_dict("records")
        )
        for r in slow_moving:
            r["qty_sold_90d"] = float(r.get("qty_sold_90d") or 0)

        return {
            "overall_turnover_ratio": round(turnover_ratio, 2),
            "days_sales_inventory": round(days_sales_inventory, 0),
            "cogs_12m": cogs,
            "avg_inventory_value": avg_inventory,
            "by_product_group": by_group,
            "fast_moving": fast_moving,
            "slow_moving": slow_moving,
        }

    # --- aging analysis ------------------------------------------------------

    def _aging_analysis(self) -> dict[str, Any]:
        from insights.api.ml.ibis_source import t

        SLE = t("Stock Ledger Entry")
        Item = t("Item")
        today = datetime.now().date()

        # Per-item: weighted average age based on qty_after_transaction.
        # Items may have many positive SLE rows; we aggregate in SQL.
        # age = (today - posting_date); weighted_age = age * qty_after_transaction
        per_item = (
            SLE.filter((SLE.actual_qty > 0) & (SLE.is_cancelled == 0))
            .left_join(Item, SLE.item_code == Item.name)
            .group_by(SLE.item_code, Item.item_name, Item.item_group)
            .aggregate(
                total_qty=SLE.qty_after_transaction.sum(),
                total_value=(SLE.qty_after_transaction * SLE.valuation_rate).sum(),
                weighted_age=((today - SLE.posting_date).cast("int32") * SLE.qty_after_transaction).sum(),
            )
            .execute()
        )

        if len(per_item) == 0:
            return {
                "age_buckets": _empty_age_buckets(),
                "by_product_group": [],
                "oldest_items": [],
                "total_items_analyzed": 0,
            }

        per_item["avg_age_days"] = per_item.apply(
            lambda r: round(r["weighted_age"] / r["total_qty"], 0) if r["total_qty"] > 0 else 0,
            axis=1,
        )
        per_item["weighted_age"] = per_item["avg_age_days"]  # frontend reads weighted_age? keep compat
        per_item["avg_age"] = per_item["avg_age_days"]

        buckets = _empty_age_buckets()
        for _, row in per_item.iterrows():
            age = float(row["avg_age_days"])
            value = float(row["total_value"])
            label = _age_bucket_label(age)
            buckets[label]["count"] += 1
            buckets[label]["value"] += value

        # By item group
        by_group = (
            per_item.groupby("item_group", dropna=False)
            .agg(
                item_count=("item_code", "count"),
                total_value=("total_value", "sum"),
                total_qty=("total_qty", "sum"),
                total_weighted_age=("weighted_age", "sum"),
            )
            .reset_index()
        )
        by_group["item_group"] = by_group["item_group"].fillna("Uncategorized")
        by_group["avg_age_days"] = by_group.apply(
            lambda r: round(r["total_weighted_age"] / r["total_qty"], 0)
            if r["total_qty"] > 0
            else 0,
            axis=1,
        )
        by_group = by_group.sort_values("total_value", ascending=False).head(10)
        by_group_records = by_group.drop(columns=["total_weighted_age"]).to_dict("records")

        # Oldest items (top 10 by avg_age)
        oldest = per_item.sort_values("avg_age_days", ascending=False).head(10)
        oldest_records = oldest[
            ["item_code", "item_name", "item_group", "total_qty", "total_value", "avg_age_days"]
        ].to_dict("records")

        return {
            "age_buckets": buckets,
            "by_product_group": by_group_records,
            "oldest_items": oldest_records,
            "total_items_analyzed": len(per_item),
        }

    # --- warehouse analysis --------------------------------------------------

    def _warehouse_analysis(self) -> dict[str, Any]:
        from insights.api.ml.ibis_source import t

        Bin = t("Bin")
        Item = t("Item")

        by_warehouse = (
            Bin.filter((Bin.actual_qty > 0) | (Bin.reserved_qty > 0) | (Bin.ordered_qty > 0))
            .group_by(Bin.warehouse)
            .aggregate(
                item_count=Bin.item_code.nunique(),
                total_qty=Bin.actual_qty.sum(),
                stock_value=(Bin.actual_qty * Bin.valuation_rate).sum(),
                reserved_qty=Bin.reserved_qty.sum(),
                ordered_qty=Bin.ordered_qty.sum(),
            )
            .order_by(ibis.desc("stock_value"))
            .execute()
            .to_dict("records")
        )

        total_value = sum(float(w.get("stock_value") or 0) for w in by_warehouse)
        for w in by_warehouse:
            sv = float(w.get("stock_value") or 0)
            w["pct_of_total"] = round(sv / total_value * 100, 1) if total_value > 0 else 0

        # Multi-warehouse items (HAVING warehouse_count > 1)
        multi = (
            Bin.filter(Bin.actual_qty > 0)
            .left_join(Item, Bin.item_code == Item.name)
            .group_by(Bin.item_code, Item.item_name)
            .aggregate(
                warehouse_count=Bin.warehouse.nunique(),
                total_qty=Bin.actual_qty.sum(),
            )
            .filter(lambda t: t.warehouse_count > 1)
            .order_by(ibis.desc("total_qty"))
            .limit(20)
            .execute()
            .to_dict("records")
        )

        return {
            "by_warehouse": by_warehouse,
            "total_warehouses": len(by_warehouse),
            "total_stock_value": total_value,
            "multi_warehouse_items": multi,
        }

    # --- transfer recommendations --------------------------------------------

    def _transfer_recommendations(self) -> list[dict[str, Any]]:
        from insights.api.ml.ibis_source import t

        Bin = t("Bin")
        Item = t("Item")
        sii = t("Sales Invoice Item")
        si = t("Sales Invoice").filter(lambda x: x.docstatus == 1)
        today = datetime.now().date()
        cutoff = (today - timedelta(days=90)).isoformat()

        # Per (item, warehouse) demand from Sales Invoice via set_warehouse
        # on the SI header. The original SQL used si.set_warehouse; we
        # honour that here.
        per_wh_demand = (
            si.filter(si.posting_date >= cutoff)
            .select(si.name, si.set_warehouse, si.posting_date)
            .join(sii, sii.parent == si.name, how="inner")
            .select(sii.item_code, si.set_warehouse, sii.qty)
            .group_by("item_code", "set_warehouse")
            .aggregate(qty_90d=sii.qty.sum())
            .mutate(avg_daily_sales=lambda t: t.qty_90d / 90.0)
            .execute()
        )

        # Bring to Bin via left join on (item_code, warehouse == set_warehouse)
        bin_df = (
            Bin.filter(Bin.actual_qty > 0)
            .left_join(Item, Bin.item_code == Item.name)
            .select(Bin.item_code, Item.item_name, Bin.warehouse, Bin.actual_qty)
            .execute()
        )
        if len(bin_df) == 0:
            return []

        demand_map = {
            (r["item_code"], r["set_warehouse"]): float(r["avg_daily_sales"] or 0)
            for _, r in per_wh_demand.iterrows()
        }

        # Per item, group warehouses and decide transfer
        recommendations: list[dict[str, Any]] = []
        for item_code, group in bin_df.groupby("item_code"):
            warehouses = []
            for _, row in group.iterrows():
                wh = row["warehouse"]
                qty = float(row["actual_qty"] or 0)
                daily = demand_map.get((item_code, wh), 0.0) or 0.01
                warehouses.append(
                    {
                        "warehouse": wh,
                        "qty": qty,
                        "daily_demand": daily,
                        "days_of_supply": qty / daily,
                    }
                )
            if len(warehouses) < 2:
                continue
            sorted_wh = sorted(warehouses, key=lambda w: w["days_of_supply"])
            low_stock_wh = [w for w in sorted_wh if w["days_of_supply"] < 14 and w["daily_demand"] > 0.01]
            high_stock_wh = [w for w in sorted_wh if w["days_of_supply"] > 60]
            for low in low_stock_wh:
                for high in high_stock_wh:
                    target_days = 30
                    needed = (target_days * low["daily_demand"]) - low["qty"]
                    available = high["qty"] - (30 * high["daily_demand"])
                    transfer_qty = min(needed, available)
                    if transfer_qty > 0:
                        recommendations.append(
                            {
                                "item_code": item_code,
                                "item_name": group.iloc[0]["item_name"],
                                "from_warehouse": high["warehouse"],
                                "to_warehouse": low["warehouse"],
                                "recommended_qty": round(transfer_qty, 0),
                                "reason": (
                                    f"Low stock ({round(low['days_of_supply'], 0)} days) at "
                                    f"destination, excess ({round(high['days_of_supply'], 0)} "
                                    f"days) at source"
                                ),
                                "priority": "High" if low["days_of_supply"] < 7 else "Medium",
                            }
                        )

        recommendations.sort(
            key=lambda x: (0 if x["priority"] == "High" else 1, -x["recommended_qty"])
        )
        return recommendations[:20]

    # --- dead stock ----------------------------------------------------------

    def _dead_stock(self) -> dict[str, Any]:
        from insights.api.ml.ibis_source import t

        Bin = t("Bin")
        Item = t("Item")
        sii = t("Sales Invoice Item")
        si = t("Sales Invoice").filter(lambda x: x.docstatus == 1)
        today = datetime.now().date()

        # Last sale date per item (any SI, all-time). A semi-join only
        # exposes LEFT-side (sii) columns in the projection -- `si` is
        # gone from scope afterward -- so this needs a real inner join
        # to select `si.posting_date`. Safe: `si.name` is a primary key,
        # so the join can't multiply `sii` rows.
        last_sale_proj = (
            sii.join(si, sii.parent == si.name, how="inner")
            .select(sii.item_code.name("item_code"), si.posting_date.name("posting_date"))
        )
        last_sale = (
            last_sale_proj
            .group_by("item_code")
            .aggregate(last_sale_date=last_sale_proj.posting_date.max())
            .execute()
        )
        # MariaDB DATE columns come back from .execute() as pandas
        # Timestamp, not datetime.date; `today - Timestamp` raises
        # TypeError, so normalize to plain date here.
        last_sale_map = {
            k: (v.date() if hasattr(v, "date") else v)
            for k, v in zip(last_sale["item_code"], last_sale["last_sale_date"])
        }

        # Positive stock
        stock = (
            Bin.filter(Bin.actual_qty > 0)
            .left_join(Item, Bin.item_code == Item.name)
            .select(
                Bin.item_code,
                Item.item_name,
                Item.item_group,
                Bin.warehouse,
                Bin.actual_qty,
                Bin.valuation_rate,
            )
            .mutate(stock_value=Bin.actual_qty * Bin.valuation_rate)
            .order_by(ibis.desc("stock_value"))
            .limit(50)
            .execute()
        )

        rows = []
        for _, r in stock.iterrows():
            last_sale_date = last_sale_map.get(r["item_code"])
            if last_sale_date is None or (today - last_sale_date).days > 180:
                days = (today - last_sale_date).days if last_sale_date else None
                rows.append(
                    {
                        "item_code": r["item_code"],
                        "item_name": r["item_name"],
                        "item_group": r.get("item_group") or "Uncategorized",
                        "warehouse": r["warehouse"],
                        "actual_qty": float(r["actual_qty"] or 0),
                        "stock_value": float(r["stock_value"] or 0),
                        "last_sale_date": str(last_sale_date) if last_sale_date else None,
                        "days_since_last_sale": days,
                    }
                )

        total_value = sum(float(r["stock_value"] or 0) for r in rows)

        # By group
        by_group_map: dict[str, dict[str, Any]] = {}
        for r in rows:
            g = r.get("item_group") or "Uncategorized"
            if g not in by_group_map:
                by_group_map[g] = {"item_group": g, "count": 0, "value": 0.0}
            by_group_map[g]["count"] += 1
            by_group_map[g]["value"] += r["stock_value"]
        by_group = sorted(by_group_map.values(), key=lambda x: x["value"], reverse=True)

        return {
            "total_items": len(rows),
            "total_value": total_value,
            "items": rows[:20],
            "by_product_group": by_group,
        }

    # --- procurement insights (for inventory dashboard) ----------------------

    def _procurement_insights(self) -> dict[str, Any]:
        from insights.api.ml.ibis_source import t

        PO = t("Purchase Order").filter(lambda x: x.docstatus == 1)
        Supplier = t("Supplier")
        PR = t("Purchase Receipt").filter(lambda x: x.docstatus == 1)
        Bin = t("Bin")
        ItemReorder = t("Item Reorder")

        # Supplier performance (last 12 months): count + value + avg lead time
        # via join on PO/Supplier + PR (any receipt from same supplier).
        # Pre-narrow every side to just the needed (uniquely-named) columns
        # -- joining full doctype tables collides on shared base-Document
        # fields (name, owner, modified, ...) plus overlapping business
        # fields (tax_category, gst_category, ...).
        po_365 = (
            PO.filter(PO.transaction_date >= (datetime.now() - timedelta(days=365)).date())
            .select(
                PO.name.name("po_name"),
                PO.supplier,
                PO.transaction_date,
                PO.grand_total,
            )
        )
        supplier_slim = Supplier.select(
            Supplier.name.name("supplier_key"), Supplier.supplier_name
        )
        pr_slim = PR.select(
            PR.supplier.name("pr_supplier"), PR.posting_date.name("pr_posting_date")
        )
        supplier_perf = (
            po_365
            .left_join(supplier_slim, po_365.supplier == supplier_slim.supplier_key)
            .left_join(
                pr_slim,
                (pr_slim.pr_supplier == po_365.supplier)
                & (pr_slim.pr_posting_date >= po_365.transaction_date),
            )
            .group_by(po_365.supplier, supplier_slim.supplier_name)
            .aggregate(
                order_count=po_365.po_name.nunique(),
                total_value=po_365.grand_total.sum(),
                avg_lead_time=(
                    (pr_slim.pr_posting_date - po_365.transaction_date).cast("int32")
                ).mean(),
            )
            .order_by(ibis.desc("total_value"))
            .limit(15)
            .execute()
            .to_dict("records")
        )

        # Pending POs
        pending = (
            PO.filter(
                ~PO.status.isin(["Completed", "Closed", "Cancelled"])
            )
            .select(PO.name, PO.supplier, PO.transaction_date, PO.grand_total, PO.status)
            .mutate(
                days_pending=(datetime.now().date() - PO.transaction_date).cast("int32")
            )
            .order_by(ibis.desc("days_pending"))
            .limit(20)
            .execute()
            .to_dict("records")
        )

        # Reorder-needed items: positive daily demand, current stock below
        # the larger of (reorder_level, 14 days of demand).
        # Step 1: per-item demand from Sales Invoice (last 90 days)
        sales_90d = _per_item_avg_daily_sales(90).execute()
        # Step 2: max reorder level per item (Item Reorder child)
        reorder_levels = (
            ItemReorder.group_by(ItemReorder.parent)
            .aggregate(reorder_level=ItemReorder.warehouse_reorder_level.max())
            .execute()
        )
        rl_map = dict(zip(reorder_levels["parent"], reorder_levels["reorder_level"]))

        # Step 3: per-item current stock
        stock_per_item = (
            Bin.group_by(Bin.item_code)
            .aggregate(current_stock=Bin.actual_qty.sum())
            .execute()
        )
        si_map = dict(zip(stock_per_item["item_code"], stock_per_item["current_stock"]))

        # Step 4: candidates
        candidates = []
        for _, r in sales_90d.iterrows():
            item = r["item_code"]
            avg_daily = float(r["avg_daily_sales"] or 0)
            if avg_daily <= 0:
                continue
            current = float(si_map.get(item, 0) or 0)
            rl = float(rl_map.get(item, 0) or 0)
            threshold = max(rl, avg_daily * 14)
            if current <= threshold:
                candidates.append(
                    {
                        "item_code": item,
                        "current_stock": current,
                        "reorder_level": rl,
                        "avg_daily_demand": avg_daily,
                    }
                )
        candidates.sort(key=lambda x: x["avg_daily_demand"], reverse=True)
        reorder_needed = candidates[:20]

        return {
            "supplier_performance": supplier_perf,
            "pending_orders": pending,
            "pending_orders_count": len(pending),
            "reorder_needed": reorder_needed,
            "reorder_count": len(candidates),
        }


# ---------------------------------------------------------------------------
# Inventory Classification (ABC/XYZ)
# ---------------------------------------------------------------------------


class ABCXYZClassification:
    """ABC/XYZ classification of stock items, computed in SQL.

    Output keys match the old ``abc_xyz_classification.py`` payload so
    the frontend keeps working without changes.
    """

    def __init__(self):
        pass

    def train(self) -> dict[str, Any]:
        from insights.api.ml.ibis_source import t

        Item = t("Item")
        Bin = t("Bin")
        sii = t("Sales Invoice Item")
        cutoff_12m = (datetime.now() - timedelta(days=365)).date()
        # Filter the parent table BEFORE semi-join; predicates on `si.*`
        # after the join reference a relation no longer in scope.
        si = t("Sales Invoice").filter(
            lambda x: (x.docstatus == 1) & (x.posting_date >= cutoff_12m)
        )

        # Per-item: total sales value (12 months)
        per_item_sales = (
            sii.join(si, sii.parent == si.name, how="semi")
            .select(sii.item_code, sii.qty, sii.amount)
            .group_by(sii.item_code)
            .aggregate(
                total_qty=sii.qty.sum(),
                total_value=sii.amount.sum(),
            )
            .execute()
        )

        # Per-item: monthly qty, last 12 months. Needs `si.posting_date`,
        # which a semi-join can't expose (LEFT-side only) -- inner join
        # instead; safe since `si.name` is a primary key.
        per_item_monthly_proj = (
            sii.join(si, sii.parent == si.name, how="inner")
            .select(sii.item_code, sii.qty, si.posting_date.name("posting_date"))
        )
        per_item_monthly = (
            per_item_monthly_proj
            .mutate(period=per_item_monthly_proj.posting_date.strftime("%Y-%m"))
            .group_by(["item_code", "period"])
            .aggregate(monthly_qty=sii.qty.sum())
            .execute()
        )
        # MariaDB SUM() returns Decimal; pandas .std()/.mean() on an
        # object-dtype Decimal column raises TypeError when mixed with
        # float internals. Cast once, up front.
        per_item_monthly["monthly_qty"] = per_item_monthly["monthly_qty"].astype(float)

        # Per-item: current stock value from Bin
        per_item_stock = (
            Bin.group_by(Bin.item_code)
            .aggregate(
                stock_qty=Bin.actual_qty.sum(),
                stock_value=(Bin.actual_qty * Bin.valuation_rate).sum(),
            )
            .execute()
        )
        stock_map = {
            r["item_code"]: {"stock_qty": float(r["stock_qty"] or 0), "stock_value": float(r["stock_value"] or 0)}
            for _, r in per_item_stock.iterrows()
        }

        # Item metadata
        items = Item.filter(Item.disabled == 0).select(
            Item.name, Item.item_name, Item.item_group
        ).execute()
        item_meta = {r["name"]: r for _, r in items.iterrows()}

        # Build rows
        rows: list[dict[str, Any]] = []
        for _, r in per_item_sales.iterrows():
            item_code = r["item_code"]
            monthly = per_item_monthly[per_item_monthly["item_code"] == item_code]
            if len(monthly) >= 2:
                mean_q = monthly["monthly_qty"].mean()
                std_q = monthly["monthly_qty"].std(ddof=0)
                cv = float(std_q / mean_q) if mean_q > 0 else math.inf
            else:
                cv = 999.0  # insufficient data → treat as Z

            sm = stock_map.get(item_code, {"stock_qty": 0, "stock_value": 0})
            meta = item_meta.get(item_code, {})
            rows.append(
                {
                    "item_code": item_code,
                    "item_name": meta.get("item_name"),
                    "item_group": meta.get("item_group"),
                    "total_value": float(r["total_value"] or 0),
                    "total_qty": float(r["total_qty"] or 0),
                    "avg_monthly_qty": float(monthly["monthly_qty"].mean()) if len(monthly) else 0,
                    "stock_qty": sm["stock_qty"],
                    "stock_value": sm["stock_value"],
                    "cv": cv if math.isfinite(cv) else 999.0,
                }
            )

        # ABC: rank by total_value desc, cumulative pct → A: 0-80, B: 80-95, C: 95-100
        rows.sort(key=lambda x: x["total_value"], reverse=True)
        total_v = sum(r["total_value"] for r in rows) or 1
        cum = 0.0
        for r in rows:
            cum += r["total_value"] / total_v * 100
            r["abc_class"] = "A" if cum <= 80 else ("B" if cum <= 95 else "C")

        # XYZ by CV thresholds
        for r in rows:
            cv = r["cv"]
            r["xyz_class"] = "X" if cv < 0.5 else ("Y" if cv < 1.0 else "Z")
            r["abc_xyz_class"] = r["abc_class"] + r["xyz_class"]
            r["strategy"] = _strategy_for(r["abc_xyz_class"])
            r["cv"] = float(cv) if math.isfinite(cv) else 999.0

        # Summary
        abc_summary_map: dict[str, dict[str, Any]] = {}
        xyz_summary_map: dict[str, dict[str, Any]] = {}
        combined_map: dict[str, dict[str, Any]] = {}
        for r in rows:
            abc_summary_map.setdefault(
                r["abc_class"], {"class": r["abc_class"], "item_count": 0, "total_value": 0.0}
            )
            abc_summary_map[r["abc_class"]]["item_count"] += 1
            abc_summary_map[r["abc_class"]]["total_value"] += r["total_value"]

            xyz_summary_map.setdefault(
                r["xyz_class"], {"class": r["xyz_class"], "item_count": 0}
            )
            xyz_summary_map[r["xyz_class"]]["item_count"] += 1

            combined_map.setdefault(
                r["abc_xyz_class"],
                {"class": r["abc_xyz_class"], "item_count": 0, "total_value": 0.0, "stock_value": 0.0},
            )
            combined_map[r["abc_xyz_class"]]["item_count"] += 1
            combined_map[r["abc_xyz_class"]]["total_value"] += r["total_value"]
            combined_map[r["abc_xyz_class"]]["stock_value"] += r["stock_value"]

        # Top items (cv sanitised, JSON-safe)
        top_items = []
        for r in rows[:50]:
            top_items.append({**r, "cv": 999 if (r["cv"] is None or math.isinf(r["cv"]) or math.isnan(r["cv"])) else round(r["cv"], 4)})

        return {
            "status": "success",
            "analysis_date": datetime.now().isoformat(),
            "total_items": len(rows),
            "items": [
                {
                    "item_code": r["item_code"],
                    "item_name": r["item_name"],
                    "item_group": r["item_group"],
                    "total_value": r["total_value"],
                    "total_qty": r["total_qty"],
                    "abc_class": r["abc_class"],
                    "xyz_class": r["xyz_class"],
                    "abc_xyz_class": r["abc_xyz_class"],
                    "cv": 999 if (r["cv"] is None or math.isinf(r["cv"]) or math.isnan(r["cv"])) else round(r["cv"], 4),
                    "avg_monthly_qty": r["avg_monthly_qty"],
                    "stock_qty": r["stock_qty"],
                    "stock_value": r["stock_value"],
                    "strategy": r["strategy"],
                }
                for r in rows
            ],
            "abc_summary": sorted(abc_summary_map.values(), key=lambda x: x["class"]),
            "xyz_summary": sorted(xyz_summary_map.values(), key=lambda x: x["class"]),
            "combined_summary": sorted(combined_map.values(), key=lambda x: x["class"]),
            "summary": {
                "a_count": abc_summary_map.get("A", {}).get("item_count", 0),
                "b_count": abc_summary_map.get("B", {}).get("item_count", 0),
                "c_count": abc_summary_map.get("C", {}).get("item_count", 0),
                "x_count": xyz_summary_map.get("X", {}).get("item_count", 0),
                "y_count": xyz_summary_map.get("Y", {}).get("item_count", 0),
                "z_count": xyz_summary_map.get("Z", {}).get("item_count", 0),
            },
            "top_items": top_items,
        }

    def predict(self, item_code: str | None = None) -> dict[str, Any]:
        return self.train()

    def get_reorder_recommendations(self) -> dict[str, list[dict[str, Any]]]:
        data = self.train()
        items = data.get("items", [])
        Bin = _t("Bin")
        # monthly demand -> stock months
        per_item_monthly_demand = {
            r["item_code"]: r.get("avg_monthly_qty", 0) or 0 for r in items
        }
        stock_now = (
            Bin.group_by(Bin.item_code)
            .aggregate(stock_qty=Bin.actual_qty.sum())
            .execute()
        )
        stock_map = dict(zip(stock_now["item_code"], stock_now["stock_qty"]))

        critical, review, discontinue = [], [], []
        for r in items:
            item = r["item_code"]
            monthly = per_item_monthly_demand.get(item, 0) or 0
            stock = float(stock_map.get(item, 0) or 0)
            stock_months = stock / monthly if monthly > 0 else 0
            if r["abc_class"] == "A" and stock_months < 2:
                critical.append({**r, "stock_months": round(stock_months, 1)})
            elif r["abc_class"] == "B" and stock_months < 1:
                review.append({**r, "stock_months": round(stock_months, 1)})
            elif r.get("abc_xyz_class") == "CZ":
                discontinue.append(r)
        return {
            "critical_reorder": critical,
            "review_needed": review,
            "consider_discontinue": discontinue,
        }


# ---------------------------------------------------------------------------
# Demand forecasting (lightweight, for the inventory dashboard)
# ---------------------------------------------------------------------------


class DemandForecasting:
    """Per-item demand forecast based on monthly quantity buckets.

    The forecast is a weighted recent average (last 3 months, weighted
    50/30/20) with a linear trend extrapolated 3 months forward -- the
    same pattern the Sales domain uses. No statsmodels / Prophet.
    """
    def train(self) -> dict[str, Any]:
        from insights.api.ml.ibis_source import t

        sii = t("Sales Invoice Item")
        cutoff_24m = (datetime.now() - timedelta(days=730)).date()
        # Filter parent BEFORE semi-join (see inventory_intelligence notes).
        si = t("Sales Invoice").filter(
            lambda x: (x.docstatus == 1) & (x.posting_date >= cutoff_24m)
        )
        # Per-item monthly qty, last 24 months. Needs `si.posting_date`,
        # which a semi-join can't expose -- inner join instead (safe:
        # `si.name` is a primary key, so no row multiplication).
        monthly_proj = (
            sii.join(si, sii.parent == si.name, how="inner")
            .select(sii.item_code, sii.qty, si.posting_date.name("posting_date"))
        )
        monthly = (
            monthly_proj
            .mutate(period=monthly_proj.posting_date.strftime("%Y-%m"))
            .group_by(["item_code", "period"])
            .aggregate(qty=sii.qty.sum())
            .order_by(["item_code", "period"])
            .execute()
        )
        # MariaDB SUM() returns Decimal; mixing it with a Python float
        # weight below (`v * w`) raises TypeError. Cast once, up front.
        if len(monthly):
            monthly["qty"] = monthly["qty"].astype(float)

        if len(monthly) == 0:
            return {
                "status": "insufficient_data",
                "forecast_date": datetime.now().isoformat(),
                "total_items_analyzed": 0,
                "reorder_alerts": [],
                "reorder_now_count": 0,
                "monitor_count": 0,
                "adequate_count": 0,
            }

        # Stock now
        Bin = t("Bin")
        stock_now = (
            Bin.group_by(Bin.item_code)
            .aggregate(stock_qty=Bin.actual_qty.sum())
            .execute()
        )
        stock_map = dict(zip(stock_now["item_code"], stock_now["stock_qty"]))

        reorder_alerts: list[dict[str, Any]] = []
        for item_code, group in monthly.groupby("item_code"):
            qty = list(group["qty"])
            last_3 = qty[-3:] if len(qty) >= 3 else qty
            weights = [0.5, 0.3, 0.2][: len(last_3)]
            if sum(weights) > 0:
                forecast = sum(v * w for v, w in zip(last_3, weights)) / sum(weights)
            else:
                forecast = 0
            stock = float(stock_map.get(item_code, 0) or 0)
            months_cover = stock / forecast if forecast > 0 else 999
            if months_cover < 1.5:
                status = "reorder_now"
            elif months_cover < 3:
                status = "monitor"
            else:
                status = "adequate"
            reorder_alerts.append(
                {
                    "item_code": item_code,
                    "monthly_forecast": round(forecast, 1),
                    "current_stock": stock,
                    "months_cover": round(months_cover, 1),
                    "status": status,
                }
            )

        return {
            "status": "success",
            "forecast_date": datetime.now().isoformat(),
            "total_items_analyzed": len(reorder_alerts),
            "reorder_alerts": reorder_alerts[:10],
            "reorder_now_count": sum(1 for r in reorder_alerts if r["status"] == "reorder_now"),
            "monitor_count": sum(1 for r in reorder_alerts if r["status"] == "monitor"),
            "adequate_count": sum(1 for r in reorder_alerts if r["status"] == "adequate"),
        }

    def predict(self) -> dict[str, Any]:
        return self.train()


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _conn():
    from insights.api.ml.ibis_source import connection

    return connection()


def _t(doctype: str):
    from insights.api.ml.ibis_source import t

    return t(doctype)


def _per_item_avg_daily_sales(days: int):
    """Return an Ibis table expression (item_code, avg_daily_sales) for
    the given lookback window from posted sales invoices."""
    sii = _t("Sales Invoice Item")
    cutoff = (datetime.now() - timedelta(days=days)).date()
    # Filter the parent table first so the date predicate references the
    # relation we're filtering -- semi_join returns the LEFT side, so
    # filtering the joined result on a SI column would error out.
    si = _t("Sales Invoice").filter(
        lambda x: (x.docstatus == 1) & (x.posting_date >= cutoff)
    )
    return (
        sii.join(si, sii.parent == si.name, how="semi")
        .select(sii.item_code, sii.qty)
        .group_by(sii.item_code)
        .aggregate(qty_90d=sii.qty.sum())
        .mutate(avg_daily_sales=lambda t: t.qty_90d / days)
        .select("item_code", "avg_daily_sales")
    )


def _empty_age_buckets() -> dict[str, dict[str, int | float]]:
    return {
        "0-30 days": {"count": 0, "value": 0.0},
        "31-60 days": {"count": 0, "value": 0.0},
        "61-90 days": {"count": 0, "value": 0.0},
        "91-180 days": {"count": 0, "value": 0.0},
        "181-365 days": {"count": 0, "value": 0.0},
        "365+ days": {"count": 0, "value": 0.0},
    }


def _age_bucket_label(age_days: float) -> str:
    if age_days <= 30:
        return "0-30 days"
    if age_days <= 60:
        return "31-60 days"
    if age_days <= 90:
        return "61-90 days"
    if age_days <= 180:
        return "91-180 days"
    if age_days <= 365:
        return "181-365 days"
    return "365+ days"


def _strategy_for(abc_xyz: str) -> str:
    """Inventory policy recommendation for each ABC/XYZ cell.

    The old code had this mapping duplicated in a few places; this single
    table is the source of truth.
    """
    strategies = {
        "AX": "Tight control: high-value, stable. Tight safety stock, frequent review.",
        "AY": "Moderate attention: high-value, variable. Frequent review, buffer stock.",
        "AZ": "Critical review: high-value, erratic. Special attention, drop-ship option.",
        "BX": "Standard control: medium-value, stable. Standard reorder policy.",
        "BY": "Moderate control: medium-value, variable. Periodic review.",
        "BZ": "Loose control: medium-value, erratic. Periodic review, larger buffers.",
        "CX": "Simple control: low-value, stable. Bulk reorder, infrequent review.",
        "CY": "Simple control: low-value, variable. Bulk reorder, periodic review.",
        "CZ": "Consider discontinue: low-value, erratic. Re-evaluate carrying cost.",
    }
    return strategies.get(abc_xyz, "Standard policy")


# ---------------------------------------------------------------------------
# Module-level wrappers
# ---------------------------------------------------------------------------


def run_inventory_intelligence(refresh: bool = False, date_filter: str = "12m") -> dict[str, Any]:
    """Run inventory intelligence analysis."""
    return InventoryIntelligence(date_filter=date_filter).train()


def run_abc_xyz_classification() -> dict[str, Any]:
    return ABCXYZClassification().train()
