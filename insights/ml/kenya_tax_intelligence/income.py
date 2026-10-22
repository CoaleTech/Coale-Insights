# Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""Income tax tab: provisional CIT, instalments, loss ledger, TOT monitor, key dates, CGT.

All figures come from the General Ledger and ERPNext documents; ERPNext holds no tax computation, so
every estimate here is labelled in `notes`. Heuristics (each a known ceiling):
- Profit before tax = credit - debit over Income and Expense accounts for the income year to date
  (Period Closing Vouchers and income-tax expense accounts excluded). Year to date, not annualised.
- Provisional CIT = CIT_RATE x (profit + add-backs - loss relief). Add-backs: expense accounts named
  entertainment / fines / penalties, and Purchase Invoices without a KRA eTIMS match (upper bound:
  includes stock and capital purchases). Capital allowances are not modelled; book depreciation stays deducted.
- Prior-year tax = debit - credit on income-tax *expense* accounts in the prior fiscal year (None if there
  is no such account). Instalment payments = Payment/Journal Entry debits on non-expense income-tax
  accounts, attributed by date to the window ending on each instalment date, so a prior-year balance paid
  on 30 Apr falls into the second window.
- Tax losses are the accounting loss of each prior fiscal year (a proxy for the tax loss), absorbed
  oldest first by later profits and usable through 31 Dec of year + 5 (`rules.loss_lapse_date`).
- CGT: sold Assets whose category looks like land / buildings, gain = sale invoice net amount - purchase cost.
- WHT credits: balance recorded on WHT receivable (asset) accounts; certificate matching is not tracked, so
  `unmatched` is None.

Drill metrics (filters: `page`, optional `start`/`end`): income_pl, income_addbacks, income_payments.
"""

from __future__ import annotations

import re
from datetime import date, timedelta
from typing import Any, Dict, List, Optional, Tuple

import frappe
from frappe import _

from insights.ml.kenya_tax_intelligence import rules
from insights.ml.kenya_tax_intelligence.common import (
    TaxContext,
    as_date,
    chip,
    doctype_exists,
    drill_page,
    fiscal_year_for,
    gl_debit,
    gl_net,
    has_field,
    kpi,
    money_short,
    pct,
    tax_accounts,
    unavailable,
)

_ADDBACK_RE = re.compile(r"entertain|\bfines?\b|penalt")
_CGT_ASSET_RE = re.compile(r"land|building|propert|plot")
_PAID_OK = 0.99


# --------------------------------------------------------------------------- pure logic
def simulate_losses(history: List[Tuple[int, float]], cur_year: int, cur_profit: Optional[float]) -> Tuple[List[Dict[str, Any]], float]:
    """Loss ledger from yearly results, oldest first.

    `history` = [(income year, profit)] of prior years; a negative year opens a loss usable through
    year + LOSS_CARRY_FORWARD_YEARS; a positive year (and the current one, `cur_profit`) absorbs older
    unlapsed losses first. Returns (ledger rows {year, amount, used, remaining}, loss absorbed by the current year).
    """
    ledger: List[Dict[str, Any]] = []

    def absorb(year: int, profit: float) -> float:
        left = profit
        for loss in ledger:
            if left <= 0:
                break
            if loss["remaining"] > 0 and loss["year"] + rules.LOSS_CARRY_FORWARD_YEARS >= year:
                use = min(loss["remaining"], left)
                loss["used"] += use
                loss["remaining"] -= use
                left -= use
        return profit - left

    for year, profit in sorted(history):
        if profit < 0:
            ledger.append({"year": year, "amount": -profit, "used": 0.0, "remaining": -profit})
        elif profit > 0:
            absorb(year, profit)
    absorbed = absorb(cur_year, cur_profit) if cur_profit and cur_profit > 0 else 0.0
    return ledger, absorbed


def instalment_chip(due: date, today: date, required: Optional[float], paid: Optional[float]) -> Dict[str, str]:
    days = (due - today).days
    if required is None:
        return chip("mut", "No estimate")
    if paid is not None and paid >= required * _PAID_OK:
        return chip("pos", "Paid")
    if days >= 0:
        return chip("acc", f"Due in {days} d")
    if paid is None:
        return chip("mut", "Due date passed, payment not traceable")
    return chip("warn", "Part-paid") if paid > 0 else chip("neg", "Unpaid")


def loss_chip(lapses: date, today: date) -> Dict[str, str]:
    days = (lapses - today).days
    label = f"{lapses:%d %b %Y}"
    return chip("neg" if days <= 180 else "warn" if days <= 548 else "mut", label)


def underpayment(rows: List[Dict[str, Any]], today: date) -> Optional[float]:
    """INSTALMENT_PENALTY x the shortfall on instalments already due; None when any of them cannot be judged."""
    short = 0.0
    for r in rows:
        if r["due_date"] >= today.isoformat():
            continue
        if r["required"] is None or r["paid"] is None:
            return None
        short += max(r["required"] - r["paid"], 0.0)
    return round(short * rules.INSTALMENT_PENALTY, 2)


# --------------------------------------------------------------------------- data
_PL_FROM = """FROM `tabGL Entry` g JOIN `tabAccount` a ON a.name = g.account
    WHERE g.company = %s AND g.is_cancelled = 0 AND g.voucher_type != 'Period Closing Voucher'
      AND a.root_type IN ('Income', 'Expense') AND g.posting_date BETWEEN %s AND %s"""
_EXCL = " AND g.account NOT IN %s"


def _pl(ctx: TaxContext, excl: List[str], start: date, end: date, by: str = "") -> List[Dict[str, Any]]:
    """Profit and loss GL sum (credit - debit) between dates, optionally grouped by `by` ('account' / 'fiscal_year')."""
    params: List[Any] = [ctx.company, start, end]
    sql = _PL_FROM
    if excl:
        sql += _EXCL
        params.append(tuple(excl))
    col = {"": "", "account": "g.account AS k, a.root_type AS root, ", "fiscal_year": "g.fiscal_year AS k, "}[by]
    group = " GROUP BY g.account, a.root_type" if by == "account" else " GROUP BY g.fiscal_year" if by else ""
    return frappe.db.sql(f"SELECT {col}COALESCE(SUM(g.credit - g.debit), 0) AS net, COUNT(*) AS n {sql}{group}", tuple(params), as_dict=True)


def _accounts(ctx: TaxContext) -> Dict[str, List[str]]:
    """Income-tax accounts split into expense (the charge) and other (where payments post), plus add-back and WHT-credit accounts."""
    if "income_accts" not in ctx._cache:
        rows = frappe.get_all("Account", filters={"company": ctx.company, "is_group": 0, "disabled": 0}, fields=["name", "account_name", "root_type"])
        root = {r["name"]: r["root_type"] for r in rows}
        it = tax_accounts(ctx, "income_tax")
        ctx._cache["income_accts"] = {
            "charge": [a for a in it if root.get(a) == "Expense"],
            "pay": [a for a in it if root.get(a) != "Expense"],
            "addback": [r["name"] for r in rows if r["root_type"] == "Expense" and r["name"] not in it and _ADDBACK_RE.search((r["account_name"] or "").lower())],
            "wht_credit": [a for a in tax_accounts(ctx, "wht") if root.get(a) == "Asset"],
        }
    return ctx._cache["income_accts"]


def _history(ctx: TaxContext, excl: List[str]) -> List[Tuple[int, float]]:
    years = {f["name"]: as_date(f["year_end_date"]).year for f in frappe.get_all("Fiscal Year", fields=["name", "year_end_date"])}
    start = rules.add_months(ctx.fy_start, -12 * (rules.LOSS_CARRY_FORWARD_YEARS + 1))
    rows = _pl(ctx, excl, start, ctx.fy_start - timedelta(days=1), "fiscal_year")
    return [(years[r["k"]], float(r["net"])) for r in rows if r["k"] in years]


def _non_etims(ctx: TaxContext, start: date, end: date) -> Optional[float]:
    if not has_field("Purchase Invoice", "custom_kra_match_status"):
        return None
    return float(frappe.db.sql(
        """SELECT COALESCE(SUM(base_net_total), 0) FROM `tabPurchase Invoice`
           WHERE company = %s AND docstatus = 1 AND is_return = 0 AND posting_date BETWEEN %s AND %s
             AND COALESCE(custom_kra_match_status, '') NOT IN ('Matched', 'Mismatched')""",
        (ctx.company, start, end),
    )[0][0] or 0)


def _cgt(ctx: TaxContext) -> List[Dict[str, Any]]:
    if not (doctype_exists("Asset") and has_field("Sales Invoice Item", "asset")):
        return []
    cost_col = next((c for c in ("purchase_amount", "gross_purchase_amount") if has_field("Asset", c)), None)
    if not cost_col:
        return []
    assets = [
        a for a in frappe.get_all(
            "Asset",
            filters={"company": ctx.company, "status": "Sold", "disposal_date": ["between", [ctx.fy_start, ctx.fy_end]]},
            fields=["name", "asset_name", "asset_category", cost_col],
        )
        if _CGT_ASSET_RE.search((a["asset_category"] or "").lower())
    ]
    if not assets:
        return []
    proceeds: Dict[str, float] = {}
    for r in frappe.get_all("Sales Invoice Item", filters={"asset": ["in", [a["name"] for a in assets]], "docstatus": 1}, fields=["asset", "base_net_amount"]):
        proceeds[r["asset"]] = proceeds.get(r["asset"], 0.0) + float(r["base_net_amount"] or 0)
    out = []
    for a in assets:
        if a["name"] not in proceeds:
            continue
        gain = round(proceeds[a["name"]] - float(a[cost_col] or 0), 2)
        out.append({"disposal": a["asset_name"] or a["name"], "gain": gain, "cgt": round(max(gain, 0.0) * rules.CGT_RATE, 2)})
    return out


def _turnover(ctx: TaxContext) -> Optional[float]:
    if not doctype_exists("Sales Invoice"):
        return None
    start = rules.add_months(ctx.today, -12) + timedelta(days=1)
    return float(frappe.db.sql(
        "SELECT COALESCE(SUM(base_net_total), 0) FROM `tabSales Invoice` WHERE company = %s AND docstatus = 1 AND posting_date BETWEEN %s AND %s",
        (ctx.company, start, ctx.today),
    )[0][0] or 0)


# --------------------------------------------------------------------------- compute
def compute(ctx: TaxContext) -> Dict[str, Any]:
    if not ctx.company:
        return unavailable(_("Set a default Company to see income tax"))
    acc = _accounts(ctx)
    start, end = ctx.fy_start, min(ctx.fy_end, ctx.today)
    notes: List[str] = []

    pl = _pl(ctx, acc["charge"], start, end)[0]
    pbt = float(pl["net"]) if pl["n"] else None
    ent = gl_net(ctx, acc["addback"], start, end, credit_positive=False)
    non_etims = _non_etims(ctx, start, end)
    if non_etims is None:
        notes.append(_("eTIMS add-back not derived: Purchase Invoice has no KRA match status field."))
    else:
        notes.append(_("Add-back for expenses without a KRA eTIMS match is an upper bound: it includes stock and capital purchases."))
    pre_loss = None if pbt is None else pbt + (ent or 0.0) + (non_etims or 0.0)

    history = _history(ctx, acc["charge"])
    ledger, absorbed = simulate_losses(history, ctx.fy_end.year, pre_loss)
    notes.append(_("Tax losses are prior-year accounting losses from the ledger, not filed tax computations."))
    notes.append(_("Capital allowances are not modelled; book depreciation stays deducted."))
    adjusted = None if pre_loss is None else pre_loss - absorbed
    cit = None if adjusted is None else round(max(adjusted, 0.0) * rules.CIT_RATE, 2)

    # prior-year tax and instalments
    prior_fy = fiscal_year_for(ctx.company, ctx.fy_start - timedelta(days=1))
    prior = gl_net(ctx, acc["charge"], as_date(prior_fy["year_start_date"]), as_date(prior_fy["year_end_date"]), credit_positive=False)
    if prior is None:
        notes.append(_("Prior-year tax not found: no income-tax expense account in the chart. Instalments use the current estimate only."))
    base = rules.instalment_required(prior, cit)
    required = None if base is None else round(base * 0.25, 2)
    dues = rules.instalment_dates(ctx.fy_start)
    if not acc["pay"]:
        notes.append(_("Instalment payments not traceable: no income-tax payable or prepaid account in the chart."))
    inst, lo = [], ctx.fy_start
    for i, due in enumerate(dues):
        paid = gl_debit(ctx, acc["pay"], lo, min(due, ctx.today)) if acc["pay"] else None
        inst.append({
            "label": f"{due.day} {due:%b}", "due_date": due.isoformat(), "required": required, "paid": paid,
            "chip": instalment_chip(due, ctx.today, required, paid),
            "drill": {"metric": "income_payments", "filters": {"start": lo.isoformat(), "end": due.isoformat()}},
        })
        lo = due + timedelta(days=1)
    paid_total = sum(r["paid"] for r in inst) if acc["pay"] else None
    n_paid = sum(1 for r in inst if r["chip"]["label"] == "Paid")
    nxt = next((r for r in inst if r["due_date"] >= ctx.today.isoformat()), None)
    exposure = underpayment(inst, ctx.today) if required is not None else None
    short_total = None if exposure is None else round(exposure / rules.INSTALMENT_PENALTY, 2)

    # losses
    live = [x for x in ledger if rules.loss_lapse_date(x["year"]) >= ctx.today and x["amount"] > 0 and (x["remaining"] > 0 or x["used"] > 0)]
    losses = [
        {"year": x["year"], "amount": round(x["amount"], 2), "used": round(x["used"], 2), "remaining": round(x["remaining"], 2),
         "lapses_on": rules.loss_lapse_date(x["year"]).isoformat(), "chip": loss_chip(rules.loss_lapse_date(x["year"]), ctx.today)}
        for x in live
    ]
    horizon = ctx.today + timedelta(days=365)
    expiring = [x for x in live if x["remaining"] > 0 and rules.loss_lapse_date(x["year"]) <= horizon]
    exp_sum = round(sum(x["remaining"] for x in expiring), 2)

    # bridge
    bridge: List[Dict[str, Any]] = []
    if pbt is not None:
        bridge.append({"label": "Profit before tax", "amount": round(pbt, 2), "kind": "base", "drill": {"metric": "income_pl", "filters": {}}})
        if non_etims:
            bridge.append({"label": "Add back: non-eTIMS expenses", "amount": round(non_etims, 2), "kind": "add"})
        if ent:
            bridge.append({"label": "Add back: entertainment, fines", "amount": round(ent, 2), "kind": "add", "drill": {"metric": "income_addbacks", "filters": {}}})
        if absorbed:
            bridge.append({"label": "Less: tax losses used", "amount": round(absorbed, 2), "kind": "less"})

    # TOT
    turn = _turnover(ctx)
    tot = {
        "applicable": None if turn is None else rules.TOT_MIN <= turn <= rules.TOT_MAX,
        "trailing_12m_turnover": turn, "ceiling": rules.TOT_MAX, "pct_of_ceiling": pct(turn, rules.TOT_MAX),
        "note": _("TOT {0:g}% of gross sales, due the 20th, for turnover between KES {1:,.0f} and KES {2:,.0f}. Above the ceiling the business moves to income tax; at KES {3:,.0f} or more it must also register for VAT.").format(
            rules.TOT_RATE * 100, rules.TOT_MIN, rules.TOT_MAX, rules.VAT_REG_THRESHOLD),
    }

    late_ref = next((p["penalty"] for p in rules.PENALTY_REFERENCE if p["breach"] == "Late company return"), "")
    wht_credit = gl_net(ctx, acc["wht_credit"], start, end, credit_positive=False)
    if wht_credit is not None:
        notes.append(_("WHT credits are the balance on WHT receivable accounts; certificate matching is not tracked."))

    next_label = None if nxt is None else f"{dues[inst.index(nxt)]:%d %b}"
    return {
        "available": True,
        "kpis": [
            kpi("provisional_cit", f"Provisional CIT, {ctx.fy_name}", cit, "money",
                _("{0:g}% × {1} adjusted profit to date").format(rules.CIT_RATE * 100, money_short(ctx, adjusted)) if adjusted is not None else _("No profit and loss postings in the financial year")),
            kpi("instalments_paid", "Instalments paid", paid_total, "money",
                _("{0} of 4 · {1}% of estimate").format(n_paid, f"{pct(paid_total, required * 4):.0f}" if paid_total is not None and required else "-") if paid_total is not None else _("No income-tax payment account to trace")),
            kpi("next_instalment", "Next instalment", nxt["due_date"] if nxt else None, "date",
                _("{0} · {1} days").format(money_short(ctx, required), (as_date(nxt["due_date"]) - ctx.today).days) if nxt else _("All four instalment dates have passed. Balance due {0:%d %b %Y}").format(rules.cit_balance_due(ctx.fy_end))),
            kpi("underpayment_exposure", "Underpayment exposure", exposure, "money",
                (_("{0:g}% penalty on the {1} shortfall").format(rules.INSTALMENT_PENALTY * 100, money_short(ctx, short_total)) if short_total else _("No shortfall on instalments already due")) if exposure is not None else _("Needs an estimate and a payment account"),
                "bad" if exposure else "neutral"),
            kpi("tax_losses_expiring", "Tax losses expiring", exp_sum if history or ledger else None, "money",
                (_("{0} loss lapses {1:%d %b %Y} · {2}-year limit").format(min(expiring, key=lambda x: x["year"])["year"], rules.loss_lapse_date(min(expiring, key=lambda x: x["year"])["year"]), rules.LOSS_CARRY_FORWARD_YEARS) if expiring else _("No loss lapses in the next 12 months")),
                "warn" if expiring else "neutral"),
            kpi("effective_tax_rate", "Effective tax rate", round(cit / pbt * 100, 2) if cit is not None and pbt and pbt > 0 else None, "pct",
                _("vs {0:g}% statutory · see the profit bridge").format(rules.CIT_RATE * 100)),
        ],
        "instalments": inst,
        "instalment_base": {"prior_year_tax": prior, "current_estimate": cit, "annual_required": base, "next": next_label},
        "bridge": bridge,
        "losses": losses,
        "tot": tot,
        "key_dates": [
            {"date": rules.cit_balance_due(ctx.fy_end).isoformat(), "title": "Balance of CIT", "sub": "Interest from this date"},
            {"date": rules.cit_return_due(ctx.fy_end).isoformat(), "title": "Company return", "sub": f"{late_ref} late"},
        ],
        "wht_credits": {"matched": wht_credit, "unmatched": None},
        "cgt": _cgt(ctx),
        "notes": notes,
    }


# --------------------------------------------------------------------------- drill-down
_METRICS = ("income_pl", "income_addbacks", "income_payments")


def drilldown(ctx: TaxContext, metric: str, filters: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if metric not in _METRICS:
        return None
    frappe.has_permission("GL Entry", throw=True)
    if not ctx.company:
        return drill_page([], [], filters)
    acc = _accounts(ctx)
    start = as_date(filters.get("start")) or ctx.fy_start
    end = as_date(filters.get("end")) or min(ctx.fy_end, ctx.today)
    if metric == "income_payments":
        cols = [
            {"label": "Date", "fieldname": "posting_date", "fieldtype": "Date"},
            {"label": "Voucher", "fieldname": "voucher_no", "fieldtype": "Data"},
            {"label": "Type", "fieldname": "voucher_type", "fieldtype": "Data"},
            {"label": "Account", "fieldname": "account", "fieldtype": "Link", "options": "Account"},
            {"label": "Paid", "fieldname": "amount", "fieldtype": "Currency"},
        ]
        rows = frappe.db.sql(
            """SELECT posting_date, voucher_no, voucher_type, account, debit AS amount FROM `tabGL Entry`
               WHERE company = %s AND is_cancelled = 0 AND account IN %s AND debit > 0 AND voucher_type IN ('Payment Entry', 'Journal Entry')
                 AND posting_date BETWEEN %s AND %s ORDER BY posting_date""",
            (ctx.company, tuple(acc["pay"]), start, end), as_dict=True,
        ) if acc["pay"] else []
        return drill_page(cols, rows, filters)
    cols = [
        {"label": "Account", "fieldname": "account", "fieldtype": "Link", "options": "Account"},
        {"label": "Type", "fieldname": "root", "fieldtype": "Data"},
        {"label": "Net (credit - debit)", "fieldname": "amount", "fieldtype": "Currency"},
    ]
    if metric == "income_addbacks":
        rows = [r for r in _pl(ctx, acc["charge"], start, end, "account") if r["k"] in acc["addback"]]
    else:
        rows = _pl(ctx, acc["charge"], start, end, "account")
    rows = sorted(({"account": r["k"], "root": r["root"], "amount": float(r["net"])} for r in rows), key=lambda r: -abs(r["amount"]))
    return drill_page(cols, rows, filters)
