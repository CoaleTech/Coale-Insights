"""Tab briefs for the Inventory dashboard (Rule 7: server-built sentences)."""

from . import action, brief, detail, money, plural

STALE_PO_DAYS = 90
REORDER_WARN, PENDING_WARN = 5, 10  # same cut-points as the Overview badges in the Vue


def _f(v) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _num(v) -> str:
    return f"{round(v, 1):,g}"


def _turnover(p: dict):
    t = p.get("turnover_analysis") or {}
    overall = t.get("overall_turnover_ratio")
    groups = [g for g in t.get("by_product_group") or [] if _f(g.get("sales_12m")) > 0 and g.get("turnover_ratio") is not None]
    if overall is None or not groups:
        return None
    slow = min(groups, key=lambda g: g["turnover_ratio"])
    text = (
        f"{slow['item_group']} turns at {_num(slow['turnover_ratio'])}× against {_num(overall)}× overall, "
        f"holding {money(slow.get('current_stock_value'), p.get('base_currency'))} of stock"
    )
    if slow.get("dsi") is not None:
        text += f" for {plural(int(slow['dsi']), 'day')} of sales"
    sev = "medium" if slow["turnover_ratio"] < overall else "low"
    cur = p.get("base_currency")
    details = []
    if t.get("current_inventory_value") is not None and t.get("cogs_12m") is not None:
        details.append(detail(
            "Stock against sales",
            f"Inventory is {money(t['current_inventory_value'], cur)} against {money(t['cogs_12m'], cur)} of 12-month cost of goods sold"
            + (f", {t['days_sales_inventory']:g} days of sales." if t.get("days_sales_inventory") is not None else "."),
        ))
    actions = []
    if slow["turnover_ratio"] < overall:
        actions.append(action(
            f"Review stock levels in {slow['item_group']}",
            f"It turns at {_num(slow['turnover_ratio'])}× against {_num(overall)}× overall.",
            impact=money(slow.get("current_stock_value"), cur),
        ))
    return brief(sev, text + ".", details, actions)


def _abc_xyz(p: dict):
    a = p.get("abc_xyz") or {}
    summary = {r["class"]: r for r in a.get("abc_summary") or []}
    total = sum(_f(r.get("total_value")) for r in summary.values())
    if "A" not in summary or total <= 0:
        return None
    ac = summary["A"]
    text = (
        f"{plural(ac['item_count'], 'A-class item')} of {a.get('total_items')} classified carry "
        f"{_f(ac['total_value']) * 100 / total:.1f}% of {money(total, p.get('base_currency'))} sales value"
    )
    az = next((m for m in a.get("matrix") or [] if m.get("class") == "AZ"), None)
    if az and az.get("item_count"):
        text += f"; {plural(az['item_count'], 'AZ item')} combine high value with erratic demand"
    cur = p.get("base_currency")
    details = [detail(
        "Value by class",
        ", ".join(
            f"{k} {_f(summary[k]['total_value']) * 100 / total:.1f}% ({plural(summary[k]['item_count'], 'item')})"
            for k in ("A", "B", "C") if k in summary
        ) + ".",
    )]
    actions = [action(
        "Plan A-class items first",
        f"{plural(ac['item_count'], 'A-class item')} carry {_f(ac['total_value']) * 100 / total:.1f}% of sales value: review their stock levels and reorder points before the rest.",
    )]
    return brief("none", text + ".", details, actions)


def _aging(p: dict):
    a = p.get("aging_analysis") or {}
    buckets = a.get("age_buckets") or {}
    old = [buckets.get(k) or {} for k in ("181-365 days", "365+ days")]
    count, value = sum(b.get("count") or 0 for b in old), sum(_f(b.get("value")) for b in old)
    if not buckets:
        return None
    cur = p.get("base_currency")
    if not count:
        return brief("low", "No stock is older than 180 days.")
    text = f"{plural(count, 'item')} older than 180 days hold {money(value, cur)} at write-off risk"
    items = a.get("oldest_items") or []
    if items and items[0].get("avg_age_days") is not None:
        o, age = items[0], int(items[0]["avg_age_days"])
        left = 365 - age
        when = f"reaches 365 days in {plural(left, 'day')}" if left > 0 else "is past 365 days"
        text += f"; {o['item_name']} is {age} days old and {when}"
    details = [detail(
        "Age buckets",
        "; ".join(f"{k}: {plural(v.get('count') or 0, 'item')} ({money(v.get('value'), cur)})" for k, v in buckets.items()) + ".",
    )]
    dead = p.get("dead_stock") or {}
    if dead.get("total_items") is not None:
        details.append(detail("Dead stock", f"{plural(dead['total_items'], 'item')} flagged dead stock ({money(dead.get('total_value'), cur)})."))
    actions = [action(
        "Sell or write down stock older than 180 days",
        f"{plural(count, 'item')} in the 181 day and older buckets.",
        impact=money(value, cur),
    )]
    return brief("high" if (old[1].get("count") or 0) else "medium", text + ".", details, actions)


def _procurement(p: dict):
    pi = p.get("procurement_insights") or {}
    n = pi.get("pending_orders_count")
    if n is None:
        return None
    orders = pi.get("pending_orders") or []
    stale = [o for o in orders if (o.get("days_pending") or 0) > STALE_PO_DAYS]
    text = f"{plural(n, 'purchase order')} open"
    if stale:  # the backend lists the oldest first
        text += (
            f"; {len(stale)} of the {len(orders)} oldest are over {STALE_PO_DAYS} days, worth "
            f"{money(sum(_f(o.get('grand_total')) for o in stale), p.get('base_currency'))}, the oldest {plural(int(stale[0]['days_pending']), 'day')}"
        )
    r = pi.get("reorder_count")
    if r is not None:
        text += f". {plural(r, 'item')} below reorder level"
    sev = "high" if n > PENDING_WARN or (r or 0) > REORDER_WARN else "medium" if n or r else "low"
    cur = p.get("base_currency")
    so, dp = p.get("stock_overview") or {}, (p.get("demand_planning") or {}).get("summary") or {}
    details, actions = [], []
    if so.get("out_of_stock_count") is not None and so.get("total_skus"):
        details.append(detail(
            "Stock-outs",
            f"{so['out_of_stock_count']:,} of {so['total_skus']:,} SKUs are out of stock; {(so.get('low_stock_count') or 0):,} more are low.",
        ))
    if dp.get("reorder_now_count") is not None:
        details.append(detail("Reorder now", f"{plural(dp['reorder_now_count'], 'item')} of {dp.get('total_items', 0):,} planned items are flagged to reorder now."))
    if stale:
        actions.append(action(
            f"Chase purchase orders older than {STALE_PO_DAYS} days",
            f"{len(stale)} of the {len(orders)} oldest open orders, the oldest {plural(int(stale[0]['days_pending']), 'day')} pending.",
            impact=money(sum(_f(o.get("grand_total")) for o in stale), cur),
        ))
    if r:
        actions.append(action("Review items below reorder level", f"{plural(r, 'item')} are below their reorder level."))
    return brief(sev, text + ".", details, actions)


def _warehouses(p: dict):
    wa = p.get("warehouse_analysis") or {}
    whs = wa.get("by_warehouse") or []
    if not whs:
        return None
    cur = p.get("base_currency")
    recs = p.get("transfer_recommendations") or []
    multi = wa.get("multi_warehouse_items") or []
    top = whs[0]
    on_hand, reserved, ordered = (sum(_f(w.get(k)) for w in whs) for k in ("total_qty", "reserved_qty", "ordered_qty"))
    text = (
        f"{money(wa.get('total_stock_value'), cur)} of stock sits across {plural(len(whs), 'warehouse')}; "
        f"{top.get('warehouse')} holds {_num(_f(top.get('pct_of_total')))}% of it"
    )
    if on_hand > 0 and reserved > 0:
        text += f". Reserved demand of {_num(reserved)} units is {_num(reserved / on_hand)}× the {_num(on_hand)} units on hand"
    details = [
        detail(
            str(w.get("warehouse")),
            f"{plural(int(_f(w.get('item_count'))), 'item')}, {_num(_f(w.get('total_qty')))} units on hand worth "
            f"{money(_f(w.get('stock_value')), cur)}; {_num(_f(w.get('reserved_qty')))} reserved, {_num(_f(w.get('ordered_qty')))} on order.",
        )
        for w in whs[:4]
    ]
    if multi:
        details.append(detail("Split stock", f"{plural(len(multi), 'item')} held in more than one warehouse."))
    actions = []
    if recs:
        actions.append(action("Review transfer recommendations", f"{plural(len(recs), 'transfer')} suggested to rebalance stock between warehouses."))
    uncovered = reserved - on_hand - ordered
    if uncovered > 0:
        actions.append(action(
            "Cover reserved demand",
            f"{_num(reserved)} units are reserved against {_num(on_hand)} on hand and {_num(ordered)} on open orders, leaving {_num(uncovered)} uncovered.",
        ))
    return brief("medium" if recs or uncovered > 0 else "low", text + ".", details, actions)


def briefs(p: dict) -> dict:
    out = {
        "turnover": _turnover(p),
        "abc-xyz": _abc_xyz(p),
        "aging": _aging(p),
        "procurement": _procurement(p),
        "warehouses": _warehouses(p),
    }
    return {k: v for k, v in out.items() if v}


def lazy_itemwise_be(r: dict):
    items = r.get("items")
    if items is None:
        return None
    rng = r.get("date_range") or {}
    if not items:
        return brief("none", f"Item break-even returned 0 items for {r.get('period')} ({rng.get('start')} to {rng.get('end')}).")
    text = f"{plural(len(items), 'item')} analyzed for {r.get('period')}"
    if not r.get("total_fixed_costs"):
        return brief("none", text + "; no fixed cost centres are set in Insights Settings, so break-even quantities are zero and coverage cannot be rated.")
    below = [i for i in items if i.get("coverage") is not None and i["coverage"] < 1]
    text += f"; {len(below)} sell below their break-even quantity." if below else "; none sell below their break-even quantity."
    return brief("high" if below else "low", text)
