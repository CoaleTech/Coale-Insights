# Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""Demo data for the Kenya Tax Intelligence dashboard (KRA).

Seeds one company with ~12 months of fictional Kenyan trading: VAT 16% sales and
purchases, eTIMS transmission status, withholding tax deducted and (partly) remitted,
payroll with PAYE / NSSF / SHIF / Housing Levy slips, CIT instalments, imports with
customs lines and a few tax disputes. It also seeds deliberate exceptions (an untransmitted
sale, a supplier invoice KRA does not hold, a wrong WHT rate, an understated NSSF slip,
an unremitted WHT deduction) so every dashboard tab has something to show.

Run it explicitly on a throw-away site; it posts invoices, payroll and journals:

    bench --site <site> execute insights.setup.tax_demo_data.create_tax_intelligence_demo_data

It refuses to run on a company that already has non-demo submitted Sales Invoices unless
`force=True`. The `plan_*` and `journal_plan` functions are pure (no database) and shared with
`tax_demo_sql.py`, so the numbers are identical and unit-testable.
"""

import random
from datetime import date, datetime, timedelta
from types import SimpleNamespace

import frappe
from frappe.utils import add_months, getdate, today

from insights.ml.kenya_tax_intelligence import rules

DEMO_TAG = "Kenya tax demo"
SEED = 2026
CUSTOMS_DUTY_RATE = 0.10  # demo-only duty rate on imported hardware; not a statutory figure

_VAT_PCT = round(rules.VAT_RATE * 100, 2)
_PROF_PCT = round(rules.wht_rate("management_professional", True) * 100, 2)
_RENT_PCT = round(rules.wht_rate("rent", True) * 100, 2)
_CONTRACT_PCT = round(rules.wht_rate("contractual", True) * 100, 2)
_ROYALTY_NR_PCT = round(rules.wht_rate("royalty", False) * 100, 2)

# (account name, parent candidates, account_type, root_type)
ACCOUNTS = [
    ("Output VAT", ("Duties and Taxes",), "Tax", "Liability"),
    ("PAYE Payable", ("Duties and Taxes",), "Tax", "Liability"),
    ("NSSF Payable", ("Duties and Taxes",), "Tax", "Liability"),
    ("SHIF Payable", ("Duties and Taxes",), "Tax", "Liability"),
    ("Housing Levy Payable", ("Duties and Taxes",), "Tax", "Liability"),
    ("NITA Payable", ("Duties and Taxes",), "Tax", "Liability"),
    ("Withholding Tax Payable", ("Duties and Taxes",), "Tax", "Liability"),
    ("Excise Duty Payable", ("Duties and Taxes",), "Tax", "Liability"),
    ("Corporate Income Tax Payable", ("Duties and Taxes",), "Tax", "Liability"),
    ("Input VAT", ("Tax Assets", "Current Assets"), "Tax", "Asset"),
    ("Instalment Tax Paid", ("Tax Assets", "Current Assets"), "", "Asset"),
    ("Income Tax Expense", ("Indirect Expenses",), "Expense Account", "Expense"),
    ("Staff Salaries", ("Indirect Expenses",), "Expense Account", "Expense"),
    ("Excise Duty Expense", ("Indirect Expenses",), "Expense Account", "Expense"),
    ("Customs Import Duty", ("Indirect Expenses",), "Expense Account", "Expense"),
    ("IDF Fee", ("Indirect Expenses",), "Expense Account", "Expense"),
    ("Railway Development Levy", ("Indirect Expenses",), "Expense Account", "Expense"),
    ("Entertainment Expenses", ("Indirect Expenses",), "Expense Account", "Expense"),
    ("Penalties and Fines", ("Indirect Expenses",), "Expense Account", "Expense"),
]

_SALES_T = "Sales Taxes and Charges Template"
_PURCH_T = "Purchase Taxes and Charges Template"
_IN_VAT = ("Input VAT", f"VAT {_VAT_PCT:g}%", _VAT_PCT, "Add")


def _wht_row(pct):
    return ("Withholding Tax Payable", f"WHT {pct:g}%", pct, "Deduct")


# key -> (template doctype, title, rows of (account, description, rate %, add/deduct))
TEMPLATES = {
    "sales_vat": (_SALES_T, f"Kenya Output VAT {_VAT_PCT:g}%", [("Output VAT", f"VAT {_VAT_PCT:g}%", _VAT_PCT, "Add")]),
    "pi_vat": (_PURCH_T, f"Kenya Input VAT {_VAT_PCT:g}%", [_IN_VAT]),
    **{
        f"pi_vat_wht_{p:g}": (_PURCH_T, f"Kenya Input VAT {_VAT_PCT:g}% + WHT {p:g}%", [_IN_VAT, _wht_row(p)])
        for p in sorted({_PROF_PCT, _RENT_PCT, _CONTRACT_PCT})
    },
    f"pi_wht_{_ROYALTY_NR_PCT:g}": (_PURCH_T, f"Kenya WHT {_ROYALTY_NR_PCT:g}% (non-resident)", [_wht_row(_ROYALTY_NR_PCT)]),
}

# (customer, exports?) -- fictional; PINs are generated, not real
CUSTOMERS = [
    ("Savannah Retail Ltd", False),
    ("Lakeview Hospitality Ltd", False),
    ("Mombasa Logistics Co", False),
    ("Rift Valley Agro Ltd", False),
    ("Kilimani Clinics Ltd", False),
    ("Entebbe Trade Partners Ltd", True),
]
# (supplier, country)
SUPPLIERS = [
    ("Kibera Consulting Partners", "Kenya"),
    ("Westlands Properties Ltd", "Kenya"),
    ("Mwangaza Office Supplies", "Kenya"),
    ("Tana Fuel Distributors", "Kenya"),
    ("Kisumu Contractors Ltd", "Kenya"),
    ("Cloudscale Inc", "United States"),
    ("Shenzhen Tech Exports Co", "China"),
]
SALES_ITEMS = [
    ("Software Implementation Services", 180000),
    ("Support Retainer", 65000),
    ("Training Workshop", 90000),
    ("Hardware Supply", 240000),
]
PURCHASE_ITEMS = [
    "Consulting Fees",
    "Office Rent",
    "Office Supplies",
    "Fuel and Vehicle Costs",
    "Contract Labour",
    "Software Licence Royalty",
    "Imported Server Hardware",
]
# (first, last, gender, monthly gross KES, resident)
EMPLOYEES = [
    ("Amina", "Wanjiru", "Female", 52000, True),
    ("Brian", "Otieno", "Male", 85000, True),
    ("Cynthia", "Mwangi", "Female", 145000, True),
    ("Daniel", "Kiptoo", "Male", 230000, True),
    ("Esther", "Achieng", "Female", 68000, True),  # no KRA PIN on file
    ("Farouk", "Hassan", "Male", 310000, False),  # non-resident, personal relief wrongly applied in the latest slip
    ("Grace", "Njeri", "Female", 120000, True),
    ("Hassan", "Omondi", "Male", 450000, True),
]
NO_PIN, UNDERSTATED_NSSF, RELIEF_ERROR = 4, 2, 5  # EMPLOYEES indexes of the seeded payroll exceptions
EARNINGS = (("Basic Salary", "BS"), ("House Allowance", "HA"))
DEDUCTIONS = (("PAYE", "PAYE"), ("NSSF Employee", "NSSFE"), ("SHIF", "SHIF"), ("Affordable Housing Levy", "AHL"))
QUEUE_ERRORS = [
    ("Failed", "Invalid PIN: customer PIN rejected by KRA"),
    ("Failed", "Item code not registered on eTIMS"),
    ("Failed", "Transmission timeout"),
    ("Queued", None),
]
CASES = [  # (case_ref, tax_type, period, stage, principal, penalty_interest, notice, objection, decision, tribunal, hearing, amnesty)
    ("DEMO-VAT-001", "VAT", "VAT prior year", "Objection lodged", 842000, 210500, -20, -12, None, None, None, 1),
    ("DEMO-PAYE-002", "PAYE", "PAYE prior year", "Assessment received", 365000, 91250, -8, None, None, None, None, 1),
    ("DEMO-CIT-003", "CIT", "CIT prior year", "Appeal to Tribunal", 2150000, 537500, -150, -120, -70, -35, 25, 1),
    ("DEMO-WHT-004", "WHT", "WHT earlier years", "Settled", 98000, 0, -400, -370, -300, None, None, 0),
]


# --------------------------------------------------------------------------- pure planners
def month_starts(on: date, n: int = 12):
    first = on.replace(day=1)
    return [add_months(first, -i) for i in range(n - 1, -1, -1)]


def _on(month: date, day: int, cap: date) -> date:
    return min(month.replace(day=day), cap)


def plan_sales(on: date, rng=None):
    """Sales invoices for the last 12 months. `cu` is the eTIMS control-unit number (None = untransmitted)."""
    rng = rng or random.Random(SEED)
    months = month_starts(on)
    out, cu, bad = [], 0, 0
    for i, m in enumerate(months):
        trend = 0.8 + 0.4 * i / (len(months) - 1)
        for j in range(rng.randint(4, 6)):
            customer, export = CUSTOMERS[(i + j) % len(CUSTOMERS)]
            lines = [
                (item, rng.randint(1, 4), round(rate * trend * rng.uniform(0.9, 1.15), -2))
                for item, rate in rng.sample(SALES_ITEMS, rng.randint(1, 3))
            ]
            net = round(sum(q * r for _, q, r in lines), 2)
            vat = 0.0 if export else round(net * rules.VAT_RATE, 2)
            sent = rng.random() < 0.88
            if sent:
                cu += 1
            queue = None if sent else QUEUE_ERRORS[bad % len(QUEUE_ERRORS)]
            bad += 0 if sent else 1
            out.append(
                {
                    "customer": customer,
                    "date": _on(m, rng.randint(2, 27), on),
                    "lines": lines,
                    "template": None if export else "sales_vat",
                    "net": net,
                    "vat": vat,
                    "total": round(net + vat, 2),
                    "cu": f"{cu:08d}" if sent else None,
                    "queue": queue,
                }
            )
    return out


def _purchase(supplier, item, net, template, wht_pct, d, rng, *, matched=True, kind=None):
    vat = 0.0 if template in (None, f"pi_wht_{_ROYALTY_NR_PCT:g}") else round(net * rules.VAT_RATE, 2)
    wht = round(net * wht_pct / 100, 2)
    roll = rng.random()
    return {
        "supplier": supplier,
        "date": d,
        "bill_date": d - timedelta(days=rng.randint(0, 10)),
        "item": item,
        "net": net,
        "vat": vat,
        "wht": wht,
        "wht_pct": wht_pct,
        "total": round(net + vat - wht, 2),
        "template": template,
        # eTIMS match status KRA holds for the supplier invoice; None = not tracked (non-residents, imports)
        "match": None if not matched else "Matched" if roll < 0.72 else "Mismatched" if roll < 0.78 else "Not in KRA",
        "import": False,
    }


def plan_purchases(on: date, rng=None):
    """Purchase invoices for the last 12 months, with WHT where the payee type attracts it."""
    rng = rng or random.Random(SEED + 1)
    out = []
    for i, m in enumerate(month_starts(on)):
        consult_pct = _CONTRACT_PCT if i == 3 else _PROF_PCT  # month 3: professional fee withheld at the contract rate (exception)
        out.append(_purchase("Kibera Consulting Partners", "Consulting Fees", round(rng.uniform(90, 150), 0) * 1000, f"pi_vat_wht_{consult_pct:g}", consult_pct, _on(m, 8, on), rng))
        out.append(_purchase("Westlands Properties Ltd", "Office Rent", 120000.0, f"pi_vat_wht_{_RENT_PCT:g}", _RENT_PCT, _on(m, 1, on), rng))
        out.append(_purchase("Mwangaza Office Supplies", "Office Supplies", round(rng.uniform(12, 40), 0) * 1000, "pi_vat", 0, _on(m, 12, on), rng))
        out.append(_purchase("Tana Fuel Distributors", "Fuel and Vehicle Costs", round(rng.uniform(25, 60), 0) * 1000, "pi_vat", 0, _on(m, 20, on), rng))
        if i % 2 == 0:
            out.append(_purchase("Kisumu Contractors Ltd", "Contract Labour", round(rng.uniform(60, 110), 0) * 1000, f"pi_vat_wht_{_CONTRACT_PCT:g}", _CONTRACT_PCT, _on(m, 15, on), rng))
        out.append(_purchase("Cloudscale Inc", "Software Licence Royalty", round(rng.uniform(45, 60), 0) * 1000, f"pi_wht_{_ROYALTY_NR_PCT:g}", _ROYALTY_NR_PCT, _on(m, 5, on), rng, matched=False))
        if i in (2, 5, 8, 10):
            imp = _purchase("Shenzhen Tech Exports Co", "Imported Server Hardware", round(rng.uniform(1.2, 2.8), 1) * 1000000, None, 0, _on(m, 10, on), rng, matched=False)
            imp["import"] = True
            out.append(imp)
    # WHT remittance: 78% remitted, 15% of those late, the rest left open (unremitted exceptions)
    for p in out:
        p["remit"] = None
        if p["wht"] and rng.random() < 0.78:
            when = p["date"] + timedelta(days=12 if rng.random() < 0.15 else 3)
            p["remit"] = when if when <= on else None
    return out


def plan_payroll(on: date):
    """Salary slips for each closed month. Uses `rules`, so expected statutory figures match the dashboard."""
    months = month_starts(on)[:-1]  # the current month is not closed
    out = []
    for k, m in enumerate(months):
        latest = k == len(months) - 1
        slips = []
        for e, (first, last, _g, gross, resident) in enumerate(EMPLOYEES):
            calc = rules.paye(gross, m, resident=resident)
            paye, nssf = calc["paye"], calc["nssf"]
            if latest and e == RELIEF_ERROR:
                paye = rules.paye(gross, m, resident=True)["paye"]
            if latest and e == UNDERSTATED_NSSF:
                nssf = round(rules.nssf_limits(m)[0] * rules.NSSF_RATE, 2)
            basic = round(gross * 0.75, 2)
            slips.append(
                {
                    "emp": e,
                    "name": f"{first} {last}",
                    "gross": float(gross),
                    "earnings": {"Basic Salary": basic, "House Allowance": round(gross - basic, 2)},
                    "deductions": {"PAYE": paye, "NSSF Employee": nssf, "SHIF": calc["shif"], "Affordable Housing Levy": calc["ahl"]},
                    "net": round(gross - paye - nssf - calc["shif"] - calc["ahl"], 2),
                    "nssf_er": calc["nssf"],
                    "ahl_er": calc["ahl"],
                }
            )
        out.append({"month": m, "end": rules.month_end(m), "slips": slips})
    return out


def journal_plan(on: date, purchases, payroll):
    """Journal Entries as {date, remark, lines:[(account short name | 'Bank', debit, credit)]}; always balanced."""

    def je(d, remark, credits, debits=None):
        lines = [(a, 0.0, round(v, 2)) for a, v in credits]
        total = round(sum(v for _, v in credits), 2)
        lines += [(a, round(v, 2), 0.0) for a, v in debits] if debits else []
        return {"date": d, "remark": f"{DEMO_TAG}: {remark}", "lines": lines, "total": total}

    out = []

    def pay(d, remark, debits):  # settle liabilities from the bank
        total = round(sum(v for _, v in debits), 2)
        out.append({"date": d, "remark": f"{DEMO_TAG}: {remark}", "lines": [(a, round(v, 2), 0.0) for a, v in debits] + [("Bank", 0.0, total)]})

    for k, mon in enumerate(payroll):
        s = mon["slips"]
        sums = {c: round(sum(x["deductions"][c] for x in s), 2) for c in ("PAYE", "NSSF Employee", "SHIF", "Affordable Housing Levy")}
        nssf = round(sums["NSSF Employee"] + sum(x["nssf_er"] for x in s), 2)
        ahl = round(sums["Affordable Housing Levy"] + sum(x["ahl_er"] for x in s), 2)
        nita = round(rules.NITA_PER_EMPLOYEE * len(s), 2)
        net = round(sum(x["net"] for x in s), 2)
        credits = [("PAYE Payable", sums["PAYE"]), ("NSSF Payable", nssf), ("SHIF Payable", sums["SHIF"]), ("Housing Levy Payable", ahl), ("NITA Payable", nita), ("Bank", net)]
        total = round(sum(v for _, v in credits), 2)
        out.append(
            {
                "date": mon["end"],
                "remark": f"{DEMO_TAG}: payroll {mon['month']:%b %Y}",
                "lines": [("Staff Salaries", total, 0.0)] + [(a, 0.0, round(v, 2)) for a, v in credits],
            }
        )
        due = rules.monthly_due_dates(mon["end"])
        late = timedelta(days=14) if k == len(payroll) - 2 else timedelta(0)
        if k < len(payroll) - 1:  # latest month is still to be remitted
            if due["paye"] + late <= on:
                pay(due["paye"] + late, f"PAYE, NSSF, SHIF and NITA remittance {mon['month']:%b %Y}", [("PAYE Payable", sums["PAYE"]), ("NSSF Payable", nssf), ("SHIF Payable", sums["SHIF"]), ("NITA Payable", nita)])
            if due["ahl"] + late <= on:
                pay(due["ahl"] + late, f"Housing Levy remittance {mon['month']:%b %Y}", [("Housing Levy Payable", ahl)])

    for p in purchases:
        if p["remit"]:
            pay(p["remit"], f"WHT remittance, {p['supplier']}", [("Withholding Tax Payable", p["wht"])])

    # CIT: prior-year charge, then instalments (the second one short)
    prior = 1800000.0
    out.append(je(date(on.year - 1, 12, 31), "prior-year income tax charge", [("Corporate Income Tax Payable", prior)], [("Income Tax Expense", prior)]))
    amounts = [round(prior * rules.INSTALMENT_PRIOR_FACTOR / 4, 0), 400000.0, round(prior * rules.INSTALMENT_PRIOR_FACTOR / 4, 0), round(prior * rules.INSTALMENT_PRIOR_FACTOR / 4, 0)]
    for d, amt in zip(rules.instalment_dates(date(on.year, 1, 1)), amounts):
        if d <= on:
            out.append({"date": d, "remark": f"{DEMO_TAG}: CIT instalment", "lines": [("Instalment Tax Paid", amt, 0.0), ("Bank", 0.0, amt)]})

    # Excise on the last four months
    for m in month_starts(on)[-5:-1]:
        end = rules.month_end(m)
        out.append(je(end, f"excise duty {m:%b %Y}", [("Excise Duty Payable", 28000.0)], [("Excise Duty Expense", 28000.0)]))
        due = rules.monthly_due_dates(end)["excise"]
        if due <= on:
            pay(due, f"excise remittance {m:%b %Y}", [("Excise Duty Payable", 28000.0)])
    return [j for j in out if j["date"] <= on]


def _stamp():
    ts = datetime.now().replace(microsecond=0)
    return {"owner": "Administrator", "modified_by": "Administrator", "creation": ts, "modified": ts}


def lcv_rows(imports, company, abbr):
    """Landed Cost Voucher rows (voucher, receipt, item, tax lines) for imported goods.

    Duty is a demo rate; IDF and RDL come from `rules.landed_import_taxes`. Import VAT is left
    off the voucher so the dashboard computes it.
    """
    stamp = _stamp()
    rows = []
    for n, imp in enumerate(imports, 1):
        name = f"LCV-DEMO-{n:03d}"
        cif = imp["net"]
        t = rules.landed_import_taxes(cif, round(cif * CUSTOMS_DUTY_RATE, 2))
        lines = [("Import Duty", "Customs Import Duty", t["duty"]), (f"IDF Fee {_pct(rules.IDF_RATE)}", "IDF Fee", t["idf"]), (f"Railway Development Levy {_pct(rules.RDL_RATE)}", "Railway Development Levy", t["rdl"])]
        total = round(sum(a for *_, a in lines), 2)
        child = {**stamp, "parent": name, "parenttype": "Landed Cost Voucher", "docstatus": 1}
        rows.append(("Landed Cost Voucher", {**stamp, "name": name, "company": company, "posting_date": imp["date"], "distribute_charges_based_on": "Amount", "total_taxes_and_charges": total, "docstatus": 1}))
        rows.append(("Landed Cost Purchase Receipt", {**child, "name": f"{name}-r", "parentfield": "purchase_receipts", "idx": 1, "receipt_document_type": "Purchase Invoice", "receipt_document": imp["name"], "supplier": imp["supplier"], "posting_date": imp["date"], "grand_total": cif}))
        rows.append(("Landed Cost Item", {**child, "name": f"{name}-i", "parentfield": "items", "idx": 1, "item_code": "Imported Server Hardware", "description": "Imported Server Hardware", "qty": 1, "rate": cif, "amount": cif, "applicable_charges": total, "receipt_document_type": "Purchase Invoice", "receipt_document": imp["name"]}))
        for i, (desc, acct, amount) in enumerate(lines, 1):
            rows.append(("Landed Cost Taxes and Charges", {**child, "name": f"{name}-t{i}", "parentfield": "taxes", "idx": i, "description": desc, "expense_account": f"{acct} - {abbr}", "amount": amount, "base_amount": amount, "exchange_rate": 1, "account_currency": "KES"}))
    return rows


def _pct(rate: float) -> str:
    return f"{rate * 100:g}%"


def slip_rows(company, payroll, employees):
    """Salary Slip and Salary Detail rows. `employees` maps EMPLOYEES index -> Employee name.

    Inserted directly: the payroll engine would recompute the statutory deductions (and refuse a
    structure it does not know), whereas the dashboard needs these exact figures, exceptions included.
    """
    stamp = _stamp()
    rows = []
    for mon in payroll:
        for s in mon["slips"]:
            name = f"SS-DEMO-{s['emp'] + 1:02d}-{mon['month']:%Y%m}"
            rows.append(
                (
                    "Salary Slip",
                    {
                        **stamp, "name": name, "employee": employees[s["emp"]], "employee_name": s["name"], "company": company,
                        "posting_date": mon["end"], "start_date": mon["month"], "end_date": mon["end"],
                        "salary_structure": "Kenya Demo Structure", "total_working_days": 22, "payment_days": 22,
                        "currency": "KES", "exchange_rate": 1, "gross_pay": s["gross"], "base_gross_pay": s["gross"],
                        "net_pay": s["net"], "base_net_pay": s["net"], "docstatus": 1, "status": "Submitted",
                    },
                )
            )
            for field, items, abbrs in (("earnings", s["earnings"], dict(EARNINGS)), ("deductions", s["deductions"], dict(DEDUCTIONS))):
                for i, (comp, amount) in enumerate(items.items(), 1):
                    rows.append(
                        (
                            "Salary Detail",
                            {
                                **stamp, "name": f"{name}-{field[0]}{i}", "parent": name, "parenttype": "Salary Slip", "parentfield": field,
                                "idx": i, "salary_component": comp, "abbr": abbrs[comp], "amount": amount, "default_amount": amount,
                                "statistical_component": 0, "docstatus": 1,
                            },
                        )
                    )
    return rows


# --------------------------------------------------------------------------- site setup
def make_context(company=None, force=False):
    """Resolve the company and its defaults; refuse a company that has real submitted invoices."""
    company = company or frappe.defaults.get_global_default("company")
    if not company or not frappe.db.exists("Company", company):
        frappe.throw(f"Company {company!r} not found")
    c = frappe.db.get_value(
        "Company",
        company,
        ["abbr", "default_currency", "cost_center", "default_bank_account", "default_cash_account", "default_receivable_account", "default_payable_account", "default_income_account", "default_expense_account"],
        as_dict=True,
    )
    if c.default_currency != "KES":
        frappe.throw(f"{company} reports in {c.default_currency}; the Kenya demo needs a KES company")
    real = frappe.db.count("Sales Invoice", {"company": company, "docstatus": 1, "remarks": ["not like", f"{DEMO_TAG}%"]})
    if real and not force:
        frappe.throw(f"{company} has {real} real submitted Sales Invoices; pass force=True to seed demo data anyway")
    return SimpleNamespace(company=company, abbr=c.abbr, c=c, bank=c.default_bank_account or c.default_cash_account, today=getdate(today()), tpl={})


def acct(ctx, short):
    return ctx.bank if short == "Bank" else f"{short} - {ctx.abbr}"


def _first(doctype, *preferred):
    for p in preferred:
        if frappe.db.exists(doctype, p):
            return p
    return frappe.db.get_value(doctype, {"is_group": 0}, "name")


def ensure_accounts(ctx):
    for name, parents, account_type, root_type in ACCOUNTS:
        full = f"{name} - {ctx.abbr}"
        if frappe.db.exists("Account", full):
            continue
        parent = next((f"{p} - {ctx.abbr}" for p in parents if frappe.db.exists("Account", f"{p} - {ctx.abbr}")), None) or frappe.db.get_value(
            "Account", {"company": ctx.company, "root_type": root_type, "is_group": 1, "parent_account": ["is", "not set"]}, "name"
        )
        try:
            frappe.get_doc({"doctype": "Account", "account_name": name, "parent_account": parent, "account_type": account_type, "root_type": root_type, "company": ctx.company}).insert(ignore_permissions=True)
            print(f"Created account: {full}")
        except Exception as e:
            print(f"Could not create {full}: {e}")


def ensure_templates(ctx):
    for key, (doctype, title, rows) in TEMPLATES.items():
        name = f"{title} - {ctx.abbr}"
        ctx.tpl[key] = name
        if frappe.db.exists(doctype, name):
            continue
        doc = frappe.get_doc({"doctype": doctype, "title": title, "company": ctx.company})
        for account, desc, rate, add_deduct in rows:
            row = {"charge_type": "On Net Total", "account_head": acct(ctx, account), "description": desc, "rate": rate}
            doc.append("taxes", {**row, "category": "Total", "add_deduct_tax": add_deduct} if doctype == _PURCH_T else row)
        doc.insert(ignore_permissions=True)
        print(f"Created {doctype}: {name}")


def ensure_parties_and_items(ctx):
    group, territory = _first("Customer Group", "Commercial"), _first("Territory", "Kenya")
    for i, (name, _export) in enumerate(CUSTOMERS, 1):
        if not frappe.db.exists("Customer", name):
            frappe.get_doc({"doctype": "Customer", "customer_name": name, "customer_type": "Company", "customer_group": group, "territory": territory, "tax_id": f"P0510{i:05d}Z"}).insert(ignore_permissions=True)
    sgroup = _first("Supplier Group", "Services")
    for i, (name, country) in enumerate(SUPPLIERS, 1):
        if not frappe.db.exists("Supplier", name):
            frappe.get_doc({"doctype": "Supplier", "supplier_name": name, "supplier_type": "Company", "supplier_group": sgroup, "country": country, "tax_id": f"P0520{i:05d}Y" if country == "Kenya" else None}).insert(ignore_permissions=True)
    igroup = _first("Item Group", "Services")
    for item in [i for i, _ in SALES_ITEMS] + PURCHASE_ITEMS:
        if not frappe.db.exists("Item", item):
            frappe.get_doc({"doctype": "Item", "item_code": item, "item_name": item, "item_group": igroup, "stock_uom": "Nos", "is_stock_item": 0}).insert(ignore_permissions=True)


def ensure_payroll_masters(ctx):
    """Salary components, Employee PIN/residency fields and the employees; returns EMPLOYEES index -> Employee name."""
    for comp, abbr in EARNINGS + DEDUCTIONS:
        if not frappe.db.exists("Salary Component", comp):
            frappe.get_doc({"doctype": "Salary Component", "salary_component": comp, "salary_component_abbr": abbr, "type": "Earning" if (comp, abbr) in EARNINGS else "Deduction"}).insert(ignore_permissions=True)
    for fieldname, label, fieldtype, options in (("custom_kra_pin", "KRA PIN", "Data", None), ("custom_residency", "Residency", "Select", "Resident\nNon-Resident")):
        if not frappe.db.exists("Custom Field", f"Employee-{fieldname}"):
            frappe.get_doc({"doctype": "Custom Field", "dt": "Employee", "fieldname": fieldname, "label": label, "fieldtype": fieldtype, "options": options, "insert_after": "employee_name"}).insert(ignore_permissions=True)
    names = {}
    for e, (first, last, gender, _gross, resident) in enumerate(EMPLOYEES):
        full = f"{first} {last}"
        found = frappe.db.get_value("Employee", {"employee_name": full, "company": ctx.company})
        if not found:
            doc = frappe.get_doc(
                {
                    "doctype": "Employee", "first_name": first, "last_name": last, "gender": gender, "company": ctx.company, "status": "Active",
                    "date_of_birth": date(1985 + e % 10, 3, 14), "date_of_joining": date(2022, 1, 3),
                    "custom_kra_pin": None if e == NO_PIN else f"A{9000000 + e * 137:09d}Z",
                    "custom_residency": "Resident" if resident else "Non-Resident",
                }
            ).insert(ignore_permissions=True)
            found = doc.name
        names[e] = found
    return names


def post_journals(ctx, journals):
    for j in journals:
        try:
            doc = frappe.get_doc({"doctype": "Journal Entry", "company": ctx.company, "posting_date": j["date"], "voucher_type": "Journal Entry", "user_remark": j["remark"]})
            for account, debit, credit in j["lines"]:
                doc.append("accounts", {"account": acct(ctx, account), "debit_in_account_currency": debit, "credit_in_account_currency": credit, "cost_center": ctx.c.cost_center})
            doc.insert(ignore_permissions=True)
            doc.submit()
        except Exception as e:
            print(f"Journal {j['remark']} {j['date']} failed: {e}")


def seed_tax_cases(ctx):
    if not frappe.db.exists("DocType", "Insights Tax Case"):
        print("Insights Tax Case doctype missing; skipping disputes")
        return
    day = lambda n: None if n is None else ctx.today + timedelta(days=n)  # noqa: E731
    for ref, tax, period, stage, principal, penalty, notice, objection, decision, tribunal, hearing, amnesty in CASES:
        if not frappe.db.exists("Insights Tax Case", ref):
            frappe.get_doc(
                {
                    "doctype": "Insights Tax Case", "case_ref": ref, "tax_type": tax, "period_label": period, "company": ctx.company, "stage": stage,
                    "principal": principal, "penalty_interest": penalty, "notice_date": day(notice), "objection_date": day(objection),
                    "decision_date": day(decision), "tribunal_date": day(tribunal), "hearing_date": day(hearing), "amnesty_eligible": amnesty,
                    "notes": DEMO_TAG,
                }
            ).insert(ignore_permissions=True)


def set_cols(doctype, name, values):
    """Set only the columns this site has (the eTIMS custom fields come from a separate app)."""
    values = {k: v for k, v in values.items() if frappe.db.has_column(doctype, k)}
    if values:
        frappe.db.set_value(doctype, name, values, update_modified=False)


def mark_sale(name, p):
    if p["cu"]:
        set_cols("Sales Invoice", name, {"custom_current_receipt_number": p["cu"], "custom_total_receipt_number": p["cu"]})
    elif p["queue"] and frappe.db.exists("DocType", "eTIMS Invoice Queue"):
        status, error = p["queue"]
        queued = p["date"]
        try:
            frappe.get_doc(
                {
                    "doctype": "eTIMS Invoice Queue", "reference_doctype": "Sales Invoice", "reference_name": name, "status": status,
                    "api_endpoint": "saveTrnsSalesOsdc", "queued_at": f"{queued} 09:00:00", "retry_count": 3 if status == "Failed" else 0, "last_error": error,
                }
            ).insert(ignore_permissions=True)
        except Exception as e:
            print(f"eTIMS queue row for {name} failed: {e}")


def mark_purchase(name, p):
    if p["match"]:
        set_cols("Purchase Invoice", name, {"custom_kra_match_status": p["match"], "custom_kra_variance_amount": round(p["vat"] * 0.04, 2) if p["match"] == "Mismatched" else 0})


def _append_taxes(doc, ctx, key, purchase):
    if not key:
        return
    for account, desc, rate, add_deduct in TEMPLATES[key][2]:
        row = {"charge_type": "On Net Total", "account_head": acct(ctx, account), "description": desc, "rate": rate}
        doc.append("taxes", {**row, "category": "Total", "add_deduct_tax": add_deduct} if purchase else row)
    doc.taxes_and_charges = ctx.tpl[key]


def create_sales_invoices(ctx, plan):
    for n, p in enumerate(plan, 1):
        try:
            si = frappe.get_doc({"doctype": "Sales Invoice", "company": ctx.company, "customer": p["customer"], "posting_date": p["date"], "set_posting_time": 1, "due_date": p["date"] + timedelta(days=30), "currency": "KES", "remarks": DEMO_TAG, "update_stock": 0})
            for item, qty, rate in p["lines"]:
                si.append("items", {"item_code": item, "item_name": item, "description": item, "qty": qty, "rate": rate, "income_account": ctx.c.default_income_account, "cost_center": ctx.c.cost_center})
            _append_taxes(si, ctx, p["template"], False)
            si.insert(ignore_permissions=True)
            si.submit()
            mark_sale(si.name, p)
        except Exception as e:
            print(f"Sales invoice {n} ({p['customer']} {p['date']}) failed: {e}")
    print(f"Sales invoices processed: {len(plan)}")


def create_purchase_invoices(ctx, plan):
    imports = []
    for n, p in enumerate(plan, 1):
        try:
            pi = frappe.get_doc({"doctype": "Purchase Invoice", "company": ctx.company, "supplier": p["supplier"], "posting_date": p["date"], "set_posting_time": 1, "bill_no": f"INV-{n:04d}", "bill_date": p["bill_date"], "due_date": p["date"] + timedelta(days=30), "currency": "KES", "remarks": DEMO_TAG, "update_stock": 0})
            pi.append("items", {"item_code": p["item"], "item_name": p["item"], "description": p["item"], "qty": 1, "rate": p["net"], "expense_account": ctx.c.default_expense_account, "cost_center": ctx.c.cost_center})
            _append_taxes(pi, ctx, p["template"], True)
            pi.insert(ignore_permissions=True)
            pi.submit()
            mark_purchase(pi.name, p)
            if p["import"]:
                imports.append({"name": pi.name, "supplier": p["supplier"], "net": p["net"], "date": p["date"]})
        except Exception as e:
            print(f"Purchase invoice {n} ({p['supplier']} {p['date']}) failed: {e}")
    print(f"Purchase invoices processed: {len(plan)}")
    return imports


def insert_rows(rows):
    """Insert prepared (doctype, values) rows without running controllers or payroll validation."""
    for doctype, values in rows:
        try:
            frappe.get_doc({"doctype": doctype, **values}).db_insert()
        except Exception as e:
            print(f"{doctype} {values.get('name')} failed: {e}")


def create_tax_intelligence_demo_data(company=None, force=False):
    """Create demo data for the Kenya Tax Intelligence dashboard."""
    frappe.db.commit()
    ctx = make_context(company, force)
    sales, purchases, payroll = plan_sales(ctx.today), plan_purchases(ctx.today), plan_payroll(ctx.today)

    ensure_accounts(ctx)
    ensure_templates(ctx)
    ensure_parties_and_items(ctx)
    employees = ensure_payroll_masters(ctx)

    create_sales_invoices(ctx, sales)
    imports = create_purchase_invoices(ctx, purchases)
    insert_rows(lcv_rows(imports, ctx.company, ctx.abbr))
    insert_rows(slip_rows(ctx.company, payroll, employees))
    post_journals(ctx, journal_plan(ctx.today, purchases, payroll))
    seed_tax_cases(ctx)

    frappe.db.commit()
    print("Kenya Tax Intelligence demo data created.")
