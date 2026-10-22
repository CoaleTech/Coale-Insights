# Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""Direct-SQL demo data for the Kenya Tax Intelligence dashboard (KRA).

Same scenario and numbers as `tax_demo_data.py` (it shares that module's masters and
`plan_*` functions), but invoices, their GL postings, salary slips and landed cost vouchers are
written with plain INSERTs instead of the document controllers: no naming series, hooks,
eTIMS queueing or payroll validation run, so it is fast and the figures land exactly as planned.
Accounts, parties, employees and Journal Entries still go through the ORM because the account
tree (lft/rgt) and the GL must stay consistent.

Run it explicitly on a throw-away site; it writes invoices, GL, payroll and journals:

    bench --site <site> execute insights.setup.tax_demo_sql.create_tax_demo_data_sql

It refuses a company that already has non-demo submitted Sales Invoices unless `force=True`.
"""

from datetime import timedelta

import frappe
from erpnext.accounts.utils import get_fiscal_year

from insights.setup import tax_demo_data as demo

_COLS = {}


def _insert(doctype, values):
    """INSERT one row, keeping only columns this site's table has (custom eTIMS fields may be absent)."""
    if doctype not in _COLS:
        _COLS[doctype] = set(frappe.db.get_table_columns(doctype))
    values = {k: v for k, v in values.items() if k in _COLS[doctype]}
    cols = ", ".join(f"`{k}`" for k in values)
    frappe.db.sql(f"INSERT INTO `tab{doctype}` ({cols}) VALUES ({', '.join(['%s'] * len(values))})", tuple(values.values()))


def _gl(ctx, voucher_type, voucher_no, d, lines):
    """Post (account, debit, credit, party_type, party) lines to the GL; the voucher must balance."""
    assert round(sum(x[1] for x in lines), 2) == round(sum(x[2] for x in lines), 2), voucher_no
    stamp = demo._stamp()
    fiscal_year = get_fiscal_year(d, company=ctx.company)[0]
    for account, debit, credit, party_type, party in lines:
        _insert(
            "GL Entry",
            {
                **stamp, "name": frappe.generate_hash(length=10), "docstatus": 1, "posting_date": d, "account": account, "party_type": party_type,
                "party": party, "cost_center": ctx.c.cost_center, "debit": debit, "credit": credit, "account_currency": "KES",
                "debit_in_account_currency": debit, "credit_in_account_currency": credit, "voucher_type": voucher_type, "voucher_no": voucher_no,
                "remarks": demo.DEMO_TAG, "is_opening": "No", "is_advance": "No", "fiscal_year": fiscal_year, "company": ctx.company, "is_cancelled": 0,
            },
        )


def _invoice(ctx, doctype, name, party_field, p, price_list, purchase):
    """Header, item, tax rows and GL for one Sales or Purchase Invoice built from a plan row."""
    stamp, d = demo._stamp(), p["date"]
    child = {**stamp, "parent": name, "parenttype": doctype, "docstatus": 1}
    party = p[party_field]
    lines = p["lines"] if not purchase else [(p["item"], 1, p["net"])]
    taxed = demo.TEMPLATES[p["template"]][2] if p["template"] else []
    money = {"total": p["net"], "net_total": p["net"], "total_taxes_and_charges": round(p["total"] - p["net"], 2), "grand_total": p["total"], "rounded_total": p["total"], "outstanding_amount": p["total"]}
    money = {**money, **{f"base_{k}": v for k, v in money.items()}}
    header = {
        **stamp, "name": name, "docstatus": 1, "company": ctx.company, "posting_date": d, "set_posting_time": 1, "due_date": d + timedelta(days=30),
        "currency": "KES", "conversion_rate": 1, "price_list_currency": "KES", "plc_conversion_rate": 1, "update_stock": 0, "remarks": demo.DEMO_TAG,
        "status": "Unpaid", "taxes_and_charges": ctx.tpl.get(p["template"]), **money,
    }
    if purchase:
        header.update({"supplier": party, "supplier_name": party, "credit_to": ctx.c.default_payable_account, "bill_no": f"INV-{name[-4:]}", "bill_date": p["bill_date"], "buying_price_list": price_list})
        if p["match"]:
            header.update({"custom_kra_match_status": p["match"], "custom_kra_variance_amount": round(p["vat"] * 0.04, 2) if p["match"] == "Mismatched" else 0})
    else:
        header.update({"customer": party, "customer_name": party, "debit_to": ctx.c.default_receivable_account, "selling_price_list": price_list})
        if p["cu"]:
            header.update({"custom_current_receipt_number": p["cu"], "custom_total_receipt_number": p["cu"]})
    _insert(doctype, header)

    for i, (item, qty, rate) in enumerate(lines, 1):
        amount = round(qty * rate, 2)
        _insert(
            f"{doctype} Item",
            {
                **child, "name": f"{name}-i{i}", "parentfield": "items", "idx": i, "item_code": item, "item_name": item, "description": item, "qty": qty, "uom": "Nos",
                "stock_uom": "Nos", "conversion_factor": 1, "rate": rate, "base_rate": rate, "net_rate": rate, "base_net_rate": rate, "amount": amount,
                "base_amount": amount, "net_amount": amount, "base_net_amount": amount, "cost_center": ctx.c.cost_center,
                "expense_account" if purchase else "income_account": ctx.c.default_expense_account if purchase else ctx.c.default_income_account,
            },
        )
    running, gl_tax = p["net"], []
    for i, (account, desc, rate, add_deduct) in enumerate(taxed, 1):
        amount = round(p["net"] * rate / 100, 2)
        running += -amount if add_deduct == "Deduct" else amount
        _insert(
            f"{'Purchase' if purchase else 'Sales'} Taxes and Charges",
            {
                **child, "name": f"{name}-t{i}", "parentfield": "taxes", "idx": i, "charge_type": "On Net Total", "account_head": demo.acct(ctx, account), "description": desc,
                "rate": rate, "tax_amount": amount, "base_tax_amount": amount, "tax_amount_after_discount_amount": amount, "base_tax_amount_after_discount_amount": amount,
                "total": round(running, 2), "base_total": round(running, 2), "category": "Total", "add_deduct_tax": add_deduct,
            },
        )
        gl_tax.append((demo.acct(ctx, account), amount, add_deduct))

    if purchase:
        gl = [(ctx.c.default_expense_account, p["net"], 0.0, None, None)]
        gl += [(a, amt if ad == "Add" else 0.0, amt if ad == "Deduct" else 0.0, None, None) for a, amt, ad in gl_tax]
        gl.append((ctx.c.default_payable_account, 0.0, p["total"], "Supplier", party))
    else:
        gl = [(ctx.c.default_receivable_account, p["total"], 0.0, "Customer", party), (ctx.c.default_income_account, 0.0, p["net"], None, None)]
        gl += [(a, 0.0, amt, None, None) for a, amt, _ in gl_tax]
    _gl(ctx, doctype, name, d, gl)


def create_tax_demo_data_sql(company=None, force=False):
    """Create demo data for the Kenya Tax Intelligence dashboard using direct SQL inserts."""
    frappe.db.commit()
    ctx = demo.make_context(company, force)
    sales, purchases, payroll = demo.plan_sales(ctx.today), demo.plan_purchases(ctx.today), demo.plan_payroll(ctx.today)

    demo.ensure_accounts(ctx)
    demo.ensure_templates(ctx)
    demo.ensure_parties_and_items(ctx)
    employees = demo.ensure_payroll_masters(ctx)

    selling = frappe.db.get_value("Price List", {"selling": 1, "enabled": 1}, "name")
    buying = frappe.db.get_value("Price List", {"buying": 1, "enabled": 1}, "name")
    imports = []
    for n, p in enumerate(sales, 1):
        if not frappe.db.exists("Sales Invoice", f"SINV-DEMO-{n:04d}"):
            _invoice(ctx, "Sales Invoice", f"SINV-DEMO-{n:04d}", "customer", p, selling, False)
    for n, p in enumerate(purchases, 1):
        name = f"PINV-DEMO-{n:04d}"
        if not frappe.db.exists("Purchase Invoice", name):
            _invoice(ctx, "Purchase Invoice", name, "supplier", p, buying, True)
        if p["import"]:
            imports.append({"name": name, "supplier": p["supplier"], "net": p["net"], "date": p["date"]})
    print(f"Invoices written: {len(sales)} sales, {len(purchases)} purchase")

    for doctype, values in demo.lcv_rows(imports, ctx.company, ctx.abbr) + demo.slip_rows(ctx.company, payroll, employees):
        if not frappe.db.exists(doctype, values["name"]):
            _insert(doctype, values)

    # eTIMS queue rows for untransmitted sales: ORM insert so the queue controller sets its own defaults
    for n, p in enumerate(sales, 1):
        if p["queue"]:
            demo.mark_sale(f"SINV-DEMO-{n:04d}", p)

    demo.post_journals(ctx, demo.journal_plan(ctx.today, purchases, payroll))
    demo.seed_tax_cases(ctx)

    frappe.db.commit()
    print("Kenya Tax Intelligence demo data created via SQL.")
