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
from datetime import date, datetime, timedelta
from typing import TYPE_CHECKING, Any, Iterable

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

    Penalizes inventory health problems weighted by severity. Inputs are
    item counts (overstocked SKUs, low-stock SKUs, out-of-stock SKUs)
    plus a reference total_value used only to scale the score against
    the business's overall inventory size (very-small businesses should
    not score 100 just because they only have a handful of items).

    Pre-fix: each problem-count was multiplied by an arbitrary constant
    (1000/1500/2000) and divided by total_value (typically millions) --
    the penalty always collapsed to ~0 and the score saturated at 100
    even when 36 items were out of stock.
    """
    if total_value <= 0:
        return 50.0
    # Use total_value to scale: a business with $10K in stock shouldn't
    # be penalized the same as one with $10M. Reference scale: a
    # $1M baseline; below that, problems hurt more; above, the score
    # spreads out. A penalty-per-item proportional to (1000 / value
    # at the $1M reference) keeps the math in a sensible range.
    value_ref = max(total_value, 100_000)  # floor so very small businesses aren't over-penalized
    scale = 1_000_000 / value_ref          # 1.0 at the $1M reference
    overstock_pen = overstock_count * 1.5 * scale
    low_stock_pen = low_stock_count * 2.5 * scale
    oos_pen = out_of_stock_count * 4.0 * scale
    score = 100 - (overstock_pen + low_stock_pen + oos_pen)
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
        self.start, self.end, self.days = resolve_window(date_filter)
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
        """Compute the full inventory intelligence payload.

        Equivalent to the old ``train()`` -- just no cache to fill.
        """
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
                # Distinct OUT-OF-STOCK ITEMS, not Bin rows: `total_skus` above
                # is `item_code.nunique()` (one item counted once no matter how
                # many warehouses stock it). Summing `ifelse(actual_qty<=0, 1, 0)`
                # counted one Bin ROW per item-warehouse pair, so an item out of
                # stock in 2 warehouses added 2 to the numerator against a
                # denominator that still counted it once -- inflating the
                # stockout rate (measured 60.9% vs the true 56.2% on jkm: 39
                # OOS Bin rows across only 36 distinct OOS items / 64 total).
                out_of_stock_count=Bin.item_code.nunique(where=Bin.actual_qty <= 0),
                warehouse_count=Bin.warehouse.nunique(),
            )
            .execute()
            .iloc[0]
        )

        # Per-item average daily sales over the selected window, so we can
        # compare to current stock for over/low-stock detection in one pass.
        sales_90d = _per_item_avg_daily_sales(self.start, self.end, self.days)

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
        # Filter the parent table BEFORE semi-join: a semi-join returns
        # the LEFT-side columns only, so any predicate on `si.*` after
        # the join references a relation no longer in scope.
        si = t("Sales Invoice").filter(
            lambda x: (x.docstatus == 1) & _between(x.posting_date, self.start, self.end)
        )
        # Ratios are annualised so "turns per year" keeps its meaning for
        # any window; DSI = 365 / annual turnover = days_in_window * stock / COGS.
        annualise = 365 / self.days

        # True COGS in the window comes from Stock Ledger Entry
        # stock_value_difference (the canonical ERPNext cost-of-goods-sold
        # field) summed over outbound vouchers. Cancelled entries are
        # excluded (is_cancelled keeps both the original and reversal rows).
        # Stock Entry vouchers are not COGS (transfers/issues), so excluded.
        SLE = t("Stock Ledger Entry")
        outbound = SLE.filter(
            _between(SLE.posting_date, self.start, self.end)
            & (SLE.is_cancelled == 0)
            & (SLE.stock_value_difference < 0)
            & SLE.voucher_type.isin(["Delivery Note", "Sales Invoice"])
        )
        cogs_df = outbound.aggregate(cogs_12m=(-outbound.stock_value_difference).sum()).execute()
        cogs = float(cogs_df.iloc[0]["cogs_12m"] or 0)
        # Revenue is kept separate from COGS (Sales Invoice Item.amount is
        # selling-price * qty, i.e. revenue, NOT cost).
        rev_expr = (
            sii.join(si, sii.parent == si.name, how="semi")
            .select(sii.amount)
            .aggregate(revenue_12m=sii.amount.sum())
        )
        rev_df = rev_expr.execute()
        revenue_12m = float(rev_df.iloc[0]["revenue_12m"] or 0)

        # Current stock value (positive stock only) -- the turnover denominator.
        inv_expr = Bin.filter(Bin.actual_qty > 0).aggregate(
            current_inventory=(Bin.actual_qty * Bin.valuation_rate).sum()
        )
        inv_df = inv_expr.execute()
        current_inventory = float(inv_df.iloc[0]["current_inventory"] or 0)
        turnover_ratio = cogs / current_inventory * annualise if current_inventory > 0 else 0
        days_sales_inventory = 365 / turnover_ratio if turnover_ratio > 0 else 0
        # Per-item-group COGS: outbound SLE value difference grouped by the
        # Item master's item_group.
        by_group_cogs_df = (
            outbound.left_join(Item, outbound.item_code == Item.name)
            .group_by(Item.item_group)
            .aggregate(cogs_12m=(-outbound.stock_value_difference).sum())
            .mutate(item_group=ibis.coalesce(Item.item_group, ibis.literal("Uncategorized")))
            .execute()
        )
        # Per-item-group revenue from Sales Invoice (Sales Invoice Item
        # .amount is revenue, not cost -- see comment above).
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
        cogs_map = dict(zip(by_group_cogs_df["item_group"], by_group_cogs_df["cogs_12m"]))

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
            cogs_v = float(cogs_map.get(group, 0) or 0)
            # Use real COGS for turnover (the denominator a procurement
            # planner cares about: how fast does cost flow through stock?).
            ratio_basis = cogs_v if cogs_v > 0 else sales
            # No stock on hand -> turnover/DSI are undefined, not 0 / 999.
            if stock_val > 0:
                ratio = round(ratio_basis / stock_val * annualise, 2)
                dsi = round(365 / ratio, 0) if ratio > 0 else None
            else:
                ratio = None
                dsi = None
            by_group.append(
                {
                    "item_group": group,
                    "sales_12m": sales,
                    "cogs_12m": cogs_v,
                    "current_stock_value": stock_val,
                    "turnover_ratio": ratio,
                    "dsi": dsi,
                }
            )

        # Fast-moving items over the selected window (stock-UOM qty)
        fast_moving = (
            sii.join(si, sii.parent == si.name, how="semi")
            .group_by(sii.item_code, sii.item_name)
            .aggregate(
                qty_sold=sii.stock_qty.sum(),
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

        # Slow-moving: positive stock, low sales over the window. Build the
        # base per-item-sales table first, THEN mutate to add a window qty
        # column -- referencing the table inside its own definition is the
        # classic forward-ref bug. (`qty_sold_90d` is the historical key;
        # it now holds the qty sold in the selected window.)
        base_sales = _per_item_avg_daily_sales(self.start, self.end, self.days)
        sales_90d = base_sales.mutate(qty_sold_90d=base_sales.avg_daily_sales * self.days)
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
            "revenue_12m": revenue_12m,
            "gross_margin_pct": round((revenue_12m - cogs) / revenue_12m * 100, 2) if revenue_12m > 0 else 0,
            "current_inventory_value": current_inventory,
            "by_product_group": by_group,
            "fast_moving": fast_moving,
            "slow_moving": slow_moving,
        }

    # --- aging analysis ------------------------------------------------------

    def _aging_analysis(self) -> dict[str, Any]:
        """Stock age per item, by FIFO layer replay.

        Pre-fix this weighted `today - posting_date` by
        `qty_after_transaction` (a running BALANCE snapshot, not a layer
        size) across every positive SLE row ever posted for the item --
        that is a quantity-weighted average of *all-time receipt dates*,
        identical regardless of the item's actual valuation method, and
        not FIFO despite the "Aging (FIFO)" label. `Bin.stock_queue`
        (which `erpnext.stock.valuation.FIFOValuation` maintains) stores
        only `[qty, rate]` per layer, no receipt date, so it can't answer
        "how old is stock still on hand" either. This replays the ledger
        in Python -- same consume-oldest-first algorithm as
        `FIFOValuation.remove_stock` -- tracking dates instead of rates,
        to find which historical receipts the *current* on-hand qty is
        still backed by.
        """
        from insights.api.ml.ibis_source import t

        Bin = t("Bin")
        SLE = t("Stock Ledger Entry")
        Item = t("Item")
        today = datetime.now().date()

        # Bound the replay to items that currently hold stock -- age is a
        # property of on-hand qty, not of every item that ever moved.
        # Current qty/value come from Bin (today's valuation_rate), same
        # source the other tabs use; only `avg_age_days` comes from the
        # FIFO replay below.
        current_stock = (
            Bin.filter(Bin.actual_qty > 0)
            .left_join(Item, Bin.item_code == Item.name)
            .group_by(Bin.item_code, Item.item_name, Item.item_group)
            .aggregate(
                total_qty=Bin.actual_qty.sum(),
                total_value=(Bin.actual_qty * Bin.valuation_rate).sum(),
            )
            .execute()
        )

        if len(current_stock) == 0:
            return {
                "age_buckets": _empty_age_buckets(),
                "by_product_group": [],
                "oldest_items": [],
                "total_items_analyzed": 0,
            }

        # MariaDB SUM() returns Decimal; mixing it with the Python float
        # weighted_age computed below raises TypeError (see
        # `_per_item_avg_daily_sales`/`ABCXYZClassification.train` for the
        # same pattern elsewhere in this file). Cast once, up front.
        current_stock["total_qty"] = current_stock["total_qty"].astype(float)
        current_stock["total_value"] = current_stock["total_value"].astype(float)

        item_codes = current_stock["item_code"].tolist()

        # Full posted ledger history for just those items, in chronological
        # order, to replay each item's FIFO queue.
        # ponytail: one Python loop over every historical SLE row for
        # items currently in stock -- fine at per-tenant table sizes this
        # file already assumes elsewhere (unlimited Bin/SLE joins above);
        # if this becomes the slow path, window the replay per item to a
        # rolling N years or push it into a DB running-balance query.
        history = (
            SLE.filter((SLE.item_code.isin(item_codes)) & (SLE.is_cancelled == 0))
            .select(SLE.item_code, SLE.posting_date, SLE.creation, SLE.actual_qty)
            .execute()
        )
        history = history.sort_values(["item_code", "posting_date", "creation"])

        age_map: dict[str, float] = {}
        for item_code, grp in history.groupby("item_code"):
            avg_age = _fifo_replay_age(
                zip(grp["actual_qty"].tolist(), grp["posting_date"].tolist()), today
            )
            if avg_age is not None:
                age_map[item_code] = avg_age

        current_stock["avg_age_days"] = current_stock["item_code"].map(age_map)
        per_item = current_stock.dropna(subset=["avg_age_days"])

        if len(per_item) == 0:
            return {
                "age_buckets": _empty_age_buckets(),
                "by_product_group": [],
                "oldest_items": [],
                "total_items_analyzed": 0,
            }

        buckets = _empty_age_buckets()
        for _, row in per_item.iterrows():
            age = float(row["avg_age_days"])
            value = float(row["total_value"])
            label = _age_bucket_label(age)
            buckets[label]["count"] += 1
            buckets[label]["value"] += value

        # By item group: qty-weighted average of the per-item FIFO ages.
        per_item = per_item.assign(weighted_age=per_item["avg_age_days"] * per_item["total_qty"])
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

        # Per-warehouse qty for those items (one query, positive-qty bins only).
        if multi:
            dist_rows = (
                Bin.filter(Bin.item_code.isin([m["item_code"] for m in multi]) & (Bin.actual_qty > 0))
                .select(Bin.item_code, Bin.warehouse, Bin.actual_qty)
                .execute()
            )
            per_item: dict[str, list[tuple[float, str]]] = {}
            for code, wh, qty in zip(dist_rows["item_code"], dist_rows["warehouse"], dist_rows["actual_qty"]):
                per_item.setdefault(code, []).append((float(qty), wh))
            for m in multi:
                parts = sorted(per_item.get(m["item_code"], []), key=lambda p: -p[0])
                m["distribution"] = " / ".join(f"{wh}: {_fmt_qty(q)}" for q, wh in parts)

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
        si = t("Sales Invoice").filter(
            lambda x: (x.docstatus == 1) & _between(x.posting_date, self.start, self.end)
        )

        # Per (item, warehouse) demand from the invoice LINE warehouse,
        # falling back to the invoice header's set_warehouse only when the
        # line has none. Narrow both sides first -- joining full doctype
        # tables collides on shared base-Document columns.
        si_slim = si.select(si.name.name("si_name"), si.set_warehouse)
        sii_slim = sii.select(sii.item_code, sii.parent, sii.warehouse, sii.stock_qty)
        joined = sii_slim.join(si_slim, sii_slim.parent == si_slim.si_name, how="inner")
        demand_proj = joined.select(
            item_code=joined.item_code,
            warehouse=ibis.coalesce(joined.warehouse, joined.set_warehouse),
            stock_qty=joined.stock_qty,
        )
        per_wh_demand = (
            demand_proj.group_by(["item_code", "warehouse"])
            .aggregate(qty_window=demand_proj.stock_qty.sum())
            .execute()
        )

        bin_df = (
            Bin.filter(Bin.actual_qty > 0)
            .left_join(Item, Bin.item_code == Item.name)
            .select(Bin.item_code, Item.item_name, Bin.warehouse, Bin.actual_qty)
            .execute()
        )
        if len(bin_df) == 0:
            return []

        demand_map = {
            (r["item_code"], r["warehouse"]): float(r["qty_window"] or 0) / self.days
            for _, r in per_wh_demand.iterrows()
        }

        # Per item, group warehouses and decide transfer
        recommendations: list[dict[str, Any]] = []
        for item_code, group in bin_df.groupby("item_code"):
            warehouses = []
            for _, row in group.iterrows():
                wh = row["warehouse"]
                qty = float(row["actual_qty"] or 0)
                daily = demand_map.get((item_code, wh), 0.0)
                warehouses.append(
                    {
                        "warehouse": wh,
                        "qty": qty,
                        "daily_demand": daily,
                        "days_of_supply": qty / daily if daily > 0 else math.inf,
                    }
                )
            if len(warehouses) < 2:
                continue
            sorted_wh = sorted(warehouses, key=lambda w: w["days_of_supply"])
            # Both sides need a real demand signal: no demand -> no days-of-supply
            # to compare, so no fabricated source/destination.
            low_stock_wh = [w for w in sorted_wh if w["daily_demand"] > 0.01 and w["days_of_supply"] < 14]
            high_stock_wh = [w for w in sorted_wh if w["daily_demand"] > 0.01 and w["days_of_supply"] > 60]
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

    def _dead_stock_rows(self) -> list[dict[str, Any]]:
        """Every positive-stock Bin row whose item has no sale in the last
        180 days (or ever), largest stock value first. The 180-day cutoff is
        the definition of dead stock, so it does not follow `date_filter`."""
        from insights.api.ml.ibis_source import t

        Bin = t("Bin")
        Item = t("Item")
        sii = t("Sales Invoice Item")
        si = t("Sales Invoice").filter(lambda x: x.docstatus == 1)
        today = datetime.now().date()

        # Last sale date per item (any SI, all-time), one aggregate. A
        # semi-join only exposes LEFT-side (sii) columns in the projection,
        # so this needs a real inner join to select `si.posting_date`.
        # Safe: `si.name` is a primary key, so the join can't multiply rows.
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
        # Timestamp, not datetime.date; normalize to plain date.
        last_sale_map = {
            k: (v.date() if hasattr(v, "date") else v)
            for k, v in zip(last_sale["item_code"], last_sale["last_sale_date"])
        }

        # Positive stock (every bin; the 180-day test runs below)
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
        return rows

    def _dead_stock(self) -> dict[str, Any]:
        rows = self._dead_stock_rows()
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

    def _pending_orders(self, limit: int | None = None) -> tuple[int, list[dict[str, Any]]]:
        """(true count, rows) of submitted POs not Completed/Closed/Cancelled,
        oldest first. Current-state backlog, so deliberately NOT windowed.
        Amounts are base currency."""
        from insights.api.ml.ibis_source import t

        PO = t("Purchase Order")
        Supplier = t("Supplier")
        open_po = PO.filter(
            (PO.docstatus == 1) & ~PO.status.isin(["Completed", "Closed", "Cancelled"])
        )
        count = int(open_po.count().execute())
        slim = open_po.select(
            PO.name.name("name"),
            PO.supplier,
            PO.transaction_date,
            PO.base_grand_total.name("grand_total"),
            PO.status,
        )
        supplier_slim = Supplier.select(Supplier.name.name("supplier_key"), Supplier.supplier_name)
        q = (
            slim.left_join(supplier_slim, slim.supplier == supplier_slim.supplier_key)
            .select(
                slim["name"],
                slim.supplier,
                supplier_slim.supplier_name,
                slim.transaction_date,
                slim.grand_total,
                slim.status,
            )
            .order_by("transaction_date")
        )
        if limit:
            q = q.limit(limit)
        today = datetime.now().date()
        rows = q.execute().to_dict("records")
        for r in rows:
            d = r["transaction_date"]
            d = d.date() if hasattr(d, "date") else d
            r["transaction_date"] = str(d)
            r["days_pending"] = (today - d).days
            r["grand_total"] = float(r["grand_total"] or 0)
        return count, rows

    def _reorder_candidates(self) -> list[dict[str, Any]]:
        """Every item with positive demand in the window whose stock is at or
        below max(reorder_level, 14 days of demand), highest demand first."""
        from insights.api.ml.ibis_source import t

        Bin = t("Bin")
        Item = t("Item")
        ItemReorder = t("Item Reorder")

        sales_window = _per_item_avg_daily_sales(self.start, self.end, self.days).execute()
        reorder_levels = (
            ItemReorder.group_by(ItemReorder.parent)
            .aggregate(reorder_level=ItemReorder.warehouse_reorder_level.max())
            .execute()
        )
        rl_map = dict(zip(reorder_levels["parent"], reorder_levels["reorder_level"]))

        stock_per_item = (
            Bin.group_by(Bin.item_code)
            .aggregate(current_stock=Bin.actual_qty.sum())
            .execute()
        )
        si_map = dict(zip(stock_per_item["item_code"], stock_per_item["current_stock"]))

        candidates = []
        for _, r in sales_window.iterrows():
            item = r["item_code"]
            avg_daily = float(r["avg_daily_sales"] or 0)
            if avg_daily <= 0:
                continue
            current = float(si_map.get(item, 0) or 0)
            rl = float(rl_map.get(item, 0) or 0)
            if current <= max(rl, avg_daily * 14):
                candidates.append(
                    {
                        "item_code": item,
                        "current_stock": current,
                        "reorder_level": rl,
                        "avg_daily_demand": avg_daily,
                    }
                )
        candidates.sort(key=lambda x: x["avg_daily_demand"], reverse=True)

        # One Item lookup for the names (no per-row query)
        if candidates:
            names = Item.filter(Item.name.isin([c["item_code"] for c in candidates])).select(
                Item.name, Item.item_name
            ).execute()
            name_map = dict(zip(names["name"], names["item_name"]))
            for c in candidates:
                c["item_name"] = name_map.get(c["item_code"])
        return candidates

    def _procurement_insights(self) -> dict[str, Any]:
        from insights.api.ml.ibis_source import t

        PO = t("Purchase Order").filter(lambda x: x.docstatus == 1)
        Supplier = t("Supplier")
        PR = t("Purchase Receipt").filter(lambda x: x.docstatus == 1)

        # Supplier performance (selected window): count + value + avg lead time.
        # Pre-narrow every side to just the needed (uniquely-named) columns
        # -- joining full doctype tables collides on shared base-Document
        # fields (name, owner, modified, ...) plus overlapping business
        # fields (tax_category, gst_category, ...). Values are base currency.
        po_win = (
            PO.filter(_between(PO.transaction_date, self.start, self.end))
            .select(
                PO.name.name("po_name"),
                PO.supplier,
                PO.transaction_date,
                PO.base_grand_total,
            )
        )
        supplier_slim = Supplier.select(
            Supplier.name.name("supplier_key"), Supplier.supplier_name
        )

        # order_count/total_value: pure PO properties, no receipt join needed.
        supplier_totals = (
            po_win
            .left_join(supplier_slim, po_win.supplier == supplier_slim.supplier_key)
            .group_by(po_win.supplier, supplier_slim.supplier_name)
            .aggregate(
                order_count=po_win.po_name.nunique(),
                total_value=po_win.base_grand_total.sum(),
            )
            .order_by(ibis.desc("total_value"))
            .limit(15)
            .execute()
            .to_dict("records")
        )

        # Lead time via the direct Purchase Receipt Item.purchase_order link
        # back to its originating PO -- NOT a same-supplier/any-later-receipt
        # heuristic, which fans a PO out against every other receipt from the
        # same supplier. Two-stage aggregate: per-PO first (a PO with several
        # lines or partial receipts gets ONE lead-time value, so it isn't
        # overweighted), then averaged per supplier.
        PRI = t("Purchase Receipt Item")
        pri_slim = PRI.select(PRI.purchase_order, PRI.parent)
        pr_slim = PR.select(PR.name.name("pr_name"), PR.posting_date.name("pr_posting_date"))
        po_lead_time = (
            po_win.select(po_win.po_name, po_win.supplier, po_win.transaction_date)
            .inner_join(pri_slim, po_win.po_name == pri_slim.purchase_order)
            .inner_join(pr_slim, pri_slim.parent == pr_slim.pr_name)
            .group_by(po_win.po_name, po_win.supplier)
            .aggregate(
                lead_time=((pr_slim.pr_posting_date - po_win.transaction_date).cast("int32")).mean()
            )
        )
        supplier_lead = (
            po_lead_time
            .group_by(po_lead_time.supplier)
            .aggregate(avg_lead_time=po_lead_time.lead_time.mean())
            .execute()
        )
        lead_time_map = dict(zip(supplier_lead["supplier"], supplier_lead["avg_lead_time"]))

        supplier_perf = supplier_totals
        for row in supplier_perf:
            lt = lead_time_map.get(row["supplier"])
            row["avg_lead_time"] = round(float(lt), 2) if lt is not None and not math.isnan(float(lt)) else None

        pending_count, pending = self._pending_orders(limit=20)
        candidates = self._reorder_candidates()

        return {
            "supplier_performance": supplier_perf,
            "pending_orders": pending,
            "pending_orders_count": pending_count,
            "reorder_needed": candidates[:20],
            "reorder_count": len(candidates),
        }


# ---------------------------------------------------------------------------
# Inventory Classification (ABC/XYZ)
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# ABC/XYZ classification thresholds
#
# Industry-standard cutoffs (Pareto/ABC analysis + coefficient-of-variation
# demand-stability bands), not arbitrary: ABC's 80/95 split is the classic
# "top 80% of value, next 15%, remaining 5%" Pareto rule used across supply-
# chain texts; XYZ's 0.5/1.0 CV bands are the conventional
# stable/variable/erratic demand cutoffs (CV < 0.5 ~ stable, 0.5-1.0 ~
# variable, > 1.0 ~ erratic). Named here so a future change is a one-line
# edit instead of a hunt through inline literals.
# ---------------------------------------------------------------------------
ABC_CLASS_A_CUM_PCT = 80.0  # cumulative value share for Class A (high value)
ABC_CLASS_B_CUM_PCT = 95.0  # cumulative value share for Class B (medium value); remainder is C
XYZ_CLASS_X_MAX_CV = 0.5  # coefficient of variation below which demand is "stable" (X)
XYZ_CLASS_Y_MAX_CV = 1.0  # CV below which demand is "variable" (Y); above is "erratic" (Z)


class ABCXYZClassification:
    """ABC/XYZ classification of stock items, computed in SQL.

    Output keys match the old ``abc_xyz_classification.py`` payload so
    the frontend keeps working without changes.
    """

    def __init__(self, date_filter: str = "12m"):
        self.date_filter = date_filter
        self.start, self.end, _ = resolve_window(date_filter)

    def train(self) -> dict[str, Any]:
        from insights.api.ml.ibis_source import t

        Item = t("Item")
        Bin = t("Bin")
        sii = t("Sales Invoice Item")
        # Filter the parent table BEFORE semi-join; predicates on `si.*`
        # after the join reference a relation no longer in scope.
        si = t("Sales Invoice").filter(
            lambda x: (x.docstatus == 1) & _between(x.posting_date, self.start, self.end)
        )

        # Per-item: total sales value (12 months)
        per_item_sales = (
            sii.join(si, sii.parent == si.name, how="semi")
            .select(sii.item_code, sii.stock_qty, sii.amount)
            .group_by(sii.item_code)
            .aggregate(
                total_qty=sii.stock_qty.sum(),
                total_value=sii.amount.sum(),
            )
            .execute()
        )

        # Per-item: monthly qty, last 12 months. Needs `si.posting_date`,
        # which a semi-join can't expose (LEFT-side only) -- inner join
        # instead; safe since `si.name` is a primary key.
        per_item_monthly_proj = (
            sii.join(si, sii.parent == si.name, how="inner")
            .select(sii.item_code, sii.stock_qty, si.posting_date.name("posting_date"))
        )
        per_item_monthly = (
            per_item_monthly_proj
            .mutate(period=per_item_monthly_proj.posting_date.strftime("%Y-%m"))
            .group_by(["item_code", "period"])
            .aggregate(monthly_qty=sii.stock_qty.sum())
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

        # Item metadata for exactly the items that sold (a disabled item can
        # still have sales; filtering on disabled would leave name/group None).
        sold_codes = per_item_sales["item_code"].tolist()
        if sold_codes:
            items = Item.filter(Item.name.isin(sold_codes)).select(
                Item.name, Item.item_name, Item.item_group
            ).execute()
            item_meta = {r["name"]: r for _, r in items.iterrows()}
        else:
            item_meta = {}

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
            r["abc_class"] = "A" if cum <= ABC_CLASS_A_CUM_PCT else ("B" if cum <= ABC_CLASS_B_CUM_PCT else "C")

        # XYZ by CV thresholds
        for r in rows:
            cv = r["cv"]
            r["xyz_class"] = "X" if cv < XYZ_CLASS_X_MAX_CV else ("Y" if cv < XYZ_CLASS_Y_MAX_CV else "Z")
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


# ---------------------------------------------------------------------------
# Demand forecasting (lightweight, for the inventory dashboard)
# ---------------------------------------------------------------------------


class DemandForecasting:
    """Per-item demand forecast based on monthly quantity buckets.

    The forecast is a weighted recent average of the last 3 *completed*
    months (weights 20/30/50, oldest to newest -- see `_weighted_forecast`).
    The in-progress calendar month is excluded: a partial month would
    understate demand. No statsmodels / Prophet.
    """

    def __init__(self, date_filter: str = "12m"):
        self.date_filter = date_filter
        self.start, self.end, _ = resolve_window(date_filter)

    def train(self) -> dict[str, Any]:
        from insights.api.ml.ibis_source import t

        sii = t("Sales Invoice Item")
        # Filter parent BEFORE semi-join (see inventory_intelligence notes).
        si = t("Sales Invoice").filter(
            lambda x: (x.docstatus == 1) & _between(x.posting_date, self.start, self.end)
        )
        # Per-item monthly stock-UOM qty over the window. Needs
        # `si.posting_date`, which a semi-join can't expose -- inner join
        # instead (safe: `si.name` is a primary key).
        monthly_proj = (
            sii.join(si, sii.parent == si.name, how="inner")
            .select(sii.item_code, sii.stock_qty, si.posting_date.name("posting_date"))
        )
        monthly = (
            monthly_proj
            .mutate(period=monthly_proj.posting_date.strftime("%Y-%m"))
            .group_by(["item_code", "period"])
            .aggregate(qty=sii.stock_qty.sum())
            .order_by(["item_code", "period"])
            .execute()
        )
        # MariaDB SUM() returns Decimal; mixing it with a Python float
        # weight below raises TypeError. Cast once, up front.
        if len(monthly):
            monthly["qty"] = monthly["qty"].astype(float)
            monthly = monthly[monthly["period"] != datetime.now().strftime("%Y-%m")]

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
            forecast = _weighted_forecast(list(group["qty"]))
            stock = float(stock_map.get(item_code, 0) or 0)
            # No forecast demand -> cover is undefined (null), not a sentinel.
            months_cover = stock / forecast if forecast > 0 else None
            if months_cover is None:
                status = "adequate"
            elif months_cover < 1.5:
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
                    "months_cover": round(months_cover, 1) if months_cover is not None else None,
                    "status": status,
                }
            )

        # Counts are over the full population; the list is the 20 most urgent
        # (null cover = no demand, least urgent, sorted last).
        reorder_alerts.sort(
            key=lambda r: (r["months_cover"] is None, r["months_cover"] or 0, r["item_code"])
        )
        return {
            "status": "success",
            "forecast_date": datetime.now().isoformat(),
            "total_items_analyzed": len(reorder_alerts),
            "reorder_alerts": reorder_alerts[:20],
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


def resolve_window(date_filter: str) -> tuple[date | None, date, int]:
    """(start, end, days) for a `date_filter`. `start` is None for "all";
    `days` (>= 1) is then measured from the first posted sale, so per-day
    rates stay meaningful."""
    from frappe.query_builder import functions as fn

    from insights.api.ml.utils import parse_date_filter

    start_dt, end_dt = parse_date_filter(date_filter)
    end = (end_dt or datetime.now()).date()
    start = start_dt.date() if start_dt else None
    first = start
    if first is None:
        SI = frappe.qb.DocType("Sales Invoice")
        row = frappe.qb.from_(SI).select(fn.Min(SI.posting_date)).where(SI.docstatus == 1).run()
        first = row[0][0] if row and row[0][0] else end - timedelta(days=365)
    return start, end, max((end - first).days, 1)


def _between(col, start, end):
    """`col <= end`, and `col >= start` when the window has a start."""
    cond = col <= end
    return (cond & (col >= start)) if start else cond


def _fmt_qty(q: float) -> str:
    return str(int(q)) if q == int(q) else str(round(q, 2))


_FORECAST_WEIGHTS = (0.2, 0.3, 0.5)  # oldest -> newest


def _weighted_forecast(monthly_qty: list[float]) -> float:
    """Weighted mean of the last (up to) 3 chronologically-ascending monthly
    quantities; the most recent month always carries the highest weight."""
    last = monthly_qty[-3:]
    if not last:
        return 0.0
    weights = _FORECAST_WEIGHTS[-len(last):]
    return sum(v * w for v, w in zip(last, weights)) / sum(weights)


def _per_item_avg_daily_sales(start: date | None, end: date, days: int):
    """Return an Ibis table expression (item_code, avg_daily_sales) of
    stock-UOM qty per day over the window from posted sales invoices."""
    sii = _t("Sales Invoice Item")
    # Filter the parent table first so the date predicate references the
    # relation we're filtering -- semi_join returns the LEFT side, so
    # filtering the joined result on a SI column would error out.
    si = _t("Sales Invoice").filter(
        lambda x: (x.docstatus == 1) & _between(x.posting_date, start, end)
    )
    return (
        sii.join(si, sii.parent == si.name, how="semi")
        .select(sii.item_code, sii.stock_qty)
        .group_by(sii.item_code)
        .aggregate(qty_window=sii.stock_qty.sum())
        .mutate(avg_daily_sales=lambda t: t.qty_window / days)
        .select("item_code", "avg_daily_sales")
    )


def _fifo_replay_age(ledger: Iterable[tuple[float, Any]], today) -> float | None:
    """Qty-weighted age (days) of stock still on hand, replaying the ledger
    FIFO (oldest layer consumed first) -- the same consume-oldest-first
    algorithm as ``erpnext.stock.valuation.FIFOValuation.remove_stock``,
    tracking receipt dates instead of rates.

    ``ledger`` is ``(actual_qty, posting_date)`` pairs for one item, already
    in chronological order. Returns ``None`` when there is no remaining
    positive layer (ledger doesn't back any on-hand qty for this item --
    excluded rather than guessed).
    """
    queue: list[list] = []  # [[remaining_qty, posting_date], ...] oldest first
    for actual_qty, posting_date in ledger:
        qty = float(actual_qty or 0)
        if qty > 0:
            queue.append([qty, posting_date])
        elif qty < 0:
            remaining = -qty
            while remaining > 1e-6 and queue:
                layer_qty, _layer_date = queue[0]
                take = min(layer_qty, remaining)
                queue[0][0] -= take
                remaining -= take
                if queue[0][0] <= 1e-6:
                    queue.pop(0)

    layer_qty_total = sum(layer[0] for layer in queue)
    if layer_qty_total <= 0:
        return None
    weighted_days = sum(
        qty * (today - (d.date() if hasattr(d, "date") else d)).days for qty, d in queue
    )
    return round(weighted_days / layer_qty_total, 0)


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


def run_abc_xyz_classification(date_filter: str = "12m") -> dict[str, Any]:
    return ABCXYZClassification(date_filter=date_filter).train()
