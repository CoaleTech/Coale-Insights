# Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""Demo Data Setup for Tax Intelligence Dashboard (India GST)"""

import frappe
from frappe.utils import today, add_days, getdate, nowdate, random_string
import random
from datetime import datetime, timedelta


def create_tax_intelligence_demo_data():
    """Create comprehensive demo data for testing the Tax Intelligence Dashboard."""
    frappe.db.commit()

    company = "JKM"
    abbr = "J"

    # Step 1: Setup Company GST
    setup_company_gst(company)

    # Step 2: Create GST Accounts
    create_gst_accounts(company, abbr)

    # Step 3: Create Tax Templates
    create_tax_templates(company, abbr)

    # Step 4: Create Items with HSN
    create_demo_items(company, abbr)

    # Step 5: Create Customers/Suppliers with GSTIN
    create_demo_parties(company)

    # Step 6: Create Sales Invoices with GST
    create_demo_sales_invoices(company, abbr)

    # Step 7: Create Purchase Invoices with GST
    create_demo_purchase_invoices(company, abbr)

    # Step 8: Create GL Entries for TDS/ITC health
    create_gl_entries_for_tax_accounts(company, abbr)

    # Step 9: Create GSTR Logs (if india_compliance tables exist)
    create_gstr_logs(company)

    # Step 10: Create GST Inward Supply for reconciliation
    create_gst_inward_supply(company)

    frappe.db.commit()
    print("Tax Intelligence demo data created successfully!")


def setup_company_gst(company):
    """Update company with GST details."""
    if not frappe.db.exists("Company", company):
        print(f"Company {company} not found!")
        return

    # Use db_set to bypass india_compliance GSTIN validation for demo
    frappe.db.set_value("Company", company, "gst_category", "Registered Regular")
    frappe.db.set_value("Company", company, "gstin", "27AAPFU0939F1ZV")
    frappe.db.set_value("Company", company, "default_gst_rate", 18.0)
    print(f"Updated company {company} with GST details")


def create_gst_accounts(company, abbr):
    """Create GST-related accounts if missing."""
    gst_accounts = [
        {"account_name": "Output CGST", "parent_account": f"Duties and Taxes - {abbr}", "account_type": "Tax", "root_type": "Liability"},
        {"account_name": "Output SGST", "parent_account": f"Duties and Taxes - {abbr}", "account_type": "Tax", "root_type": "Liability"},
        {"account_name": "Output IGST", "parent_account": f"Duties and Taxes - {abbr}", "account_type": "Tax", "root_type": "Liability"},
        {"account_name": "Input CGST", "parent_account": f"Tax Assets - {abbr}", "account_type": "Tax", "root_type": "Asset"},
        {"account_name": "Input SGST", "parent_account": f"Tax Assets - {abbr}", "account_type": "Tax", "root_type": "Asset"},
        {"account_name": "Input IGST", "parent_account": f"Tax Assets - {abbr}", "account_type": "Tax", "root_type": "Asset"},
        {"account_name": "TDS Payable", "parent_account": f"Duties and Taxes - {abbr}", "account_type": "Payable", "root_type": "Liability"},
        {"account_name": "WHT Receivable", "parent_account": f"Tax Assets - {abbr}", "account_type": "Receivable", "root_type": "Asset"},
        {"account_name": "Entertainment Expenses", "parent_account": f"Indirect Expenses - {abbr}", "account_type": "Expense Account", "root_type": "Expense"},
        {"account_name": "Donations", "parent_account": f"Indirect Expenses - {abbr}", "account_type": "Expense Account", "root_type": "Expense"},
        {"account_name": "Penalties and Fines", "parent_account": f"Indirect Expenses - {abbr}", "account_type": "Expense Account", "root_type": "Expense"},
    ]

    # Ensure Tax Assets parent exists
    if not frappe.db.exists("Account", f"Tax Assets - {abbr}"):
        tax_assets = frappe.new_doc("Account")
        tax_assets.account_name = "Tax Assets"
        tax_assets.parent_account = f"Current Assets - {abbr}"
        tax_assets.account_type = ""
        tax_assets.root_type = "Asset"
        tax_assets.company = company
        tax_assets.is_group = 1
        tax_assets.insert()

    for acc in gst_accounts:
        acc_name = f"{acc['account_name']} - {abbr}"
        if not frappe.db.exists("Account", acc_name):
            try:
                doc = frappe.new_doc("Account")
                doc.account_name = acc["account_name"]
                doc.parent_account = acc["parent_account"]
                doc.account_type = acc["account_type"]
                doc.root_type = acc["root_type"]
                doc.company = company
                doc.insert()
                print(f"Created account: {acc_name}")
            except Exception as e:
                print(f"Could not create {acc_name}: {e}")
        else:
            print(f"Account exists: {acc_name}")


def create_tax_templates(company, abbr):
    """Create Sales and Purchase GST tax templates."""
    # Sales Tax Template - GST 18%
    if not frappe.db.exists("Sales Taxes and Charges Template", f"GST 18% - {company}"):
        st = frappe.new_doc("Sales Taxes and Charges Template")
        st.title = f"GST 18%"
        st.company = company
        st.is_default = 1
        st.append("taxes", {
            "charge_type": "On Net Total",
            "account_head": f"Output CGST - {abbr}",
            "description": "Output CGST @ 9%",
            "rate": 9,
            "cost_center": f"Main - {abbr}",
        })
        st.append("taxes", {
            "charge_type": "On Net Total",
            "account_head": f"Output SGST - {abbr}",
            "description": "Output SGST @ 9%",
            "rate": 9,
            "cost_center": f"Main - {abbr}",
        })
        st.insert()
        print(f"Created Sales Tax Template: GST 18%")

    # Purchase Tax Template - GST 18%
    if not frappe.db.exists("Purchase Taxes and Charges Template", f"GST 18% - {company}"):
        pt = frappe.new_doc("Purchase Taxes and Charges Template")
        pt.title = f"GST 18%"
        pt.company = company
        pt.is_default = 1
        pt.append("taxes", {
            "charge_type": "On Net Total",
            "account_head": f"Input CGST - {abbr}",
            "description": "Input CGST @ 9%",
            "rate": 9,
            "cost_center": f"Main - {abbr}",
            "add_deduct_tax": "Add",
        })
        pt.append("taxes", {
            "charge_type": "On Net Total",
            "account_head": f"Input SGST - {abbr}",
            "description": "Input SGST @ 9%",
            "rate": 9,
            "cost_center": f"Main - {abbr}",
            "add_deduct_tax": "Add",
        })
        pt.insert()
        print(f"Created Purchase Tax Template: GST 18%")

    # Purchase Tax Template with TDS
    if not frappe.db.exists("Purchase Taxes and Charges Template", f"GST 18% + TDS - {company}"):
        ptt = frappe.new_doc("Purchase Taxes and Charges Template")
        ptt.title = f"GST 18% + TDS"
        ptt.company = company
        ptt.append("taxes", {
            "charge_type": "On Net Total",
            "account_head": f"Input CGST - {abbr}",
            "description": "Input CGST @ 9%",
            "rate": 9,
            "cost_center": f"Main - {abbr}",
            "add_deduct_tax": "Add",
        })
        ptt.append("taxes", {
            "charge_type": "On Net Total",
            "account_head": f"Input SGST - {abbr}",
            "description": "Input SGST @ 9%",
            "rate": 9,
            "cost_center": f"Main - {abbr}",
            "add_deduct_tax": "Add",
        })
        ptt.append("taxes", {
            "charge_type": "On Net Total",
            "account_head": f"TDS Payable - {abbr}",
            "description": "TDS @ 2%",
            "rate": 2,
            "cost_center": f"Main - {abbr}",
            "add_deduct_tax": "Deduct",
        })
        ptt.insert()
        print(f"Created Purchase Tax Template: GST 18% + TDS")


def create_demo_items(company, abbr):
    """Create items with HSN codes."""
    items = [
        {"item_code": "LAPTOP-001", "item_name": "Business Laptop Dell XPS", "item_group": "Products", "gst_hsn_code": "847130", "valuation_rate": 75000, "standard_rate": 95000},
        {"item_code": "SERVER-001", "item_name": "HP ProLiant Server", "item_group": "Products", "gst_hsn_code": "847150", "valuation_rate": 150000, "standard_rate": 185000},
        {"item_code": "DESK-001", "item_name": "Executive Office Desk", "item_group": "Products", "gst_hsn_code": "940330", "valuation_rate": 12000, "standard_rate": 15000},
        {"item_code": "CHAIR-001", "item_name": "Ergonomic Office Chair", "item_group": "Products", "gst_hsn_code": "940310", "valuation_rate": 8000, "standard_rate": 10000},
        {"item_code": "PRINT-001", "item_name": "Laser Printer HP", "item_group": "Products", "gst_hsn_code": "844331", "valuation_rate": 25000, "standard_rate": 30000},
        {"item_code": "PAPER-001", "item_name": "A4 Copier Paper (Ream)", "item_group": "Products", "gst_hsn_code": "480256", "valuation_rate": 250, "standard_rate": 300},
        {"item_code": "INK-001", "item_name": "Printer Ink Cartridge", "item_group": "Products", "gst_hsn_code": "321511", "valuation_rate": 1500, "standard_rate": 1800},
        {"item_code": "CAB-001", "item_name": "Network Cable Cat 6", "item_group": "Products", "gst_hsn_code": "854442", "valuation_rate": 500, "standard_rate": 650},
        {"item_code": "ROUTER-001", "item_name": "WiFi Router TP-Link", "item_group": "Products", "gst_hsn_code": "851762", "valuation_rate": 3500, "standard_rate": 4200},
        {"item_code": "SOFT-001", "item_name": "Software License Annual", "item_group": "Services", "gst_hsn_code": "852349", "valuation_rate": 50000, "standard_rate": 60000},
    ]

    for item in items:
        if not frappe.db.exists("Item", item["item_code"]):
            doc = frappe.new_doc("Item")
            doc.item_code = item["item_code"]
            doc.item_name = item["item_name"]
            doc.item_group = item["item_group"]
            doc.gst_hsn_code = item["gst_hsn_code"]
            doc.valuation_rate = item["valuation_rate"]
            doc.standard_rate = item["standard_rate"]
            doc.is_stock_item = 1
            doc.stock_uom = "Nos"
            doc.append("item_defaults", {
                "company": company,
                "default_warehouse": f"Stores - {abbr}",
                "expense_account": f"Cost of Goods Sold - {abbr}",
                "income_account": f"Sales - {abbr}",
            })
            try:
                doc.insert()
                print(f"Created item: {item['item_code']}")
            except Exception as e:
                print(f"Could not create item {item['item_code']}: {e}")
        else:
            print(f"Item exists: {item['item_code']}")


def create_demo_parties(company):
    """Create customers and suppliers with GSTIN."""
    abbr = frappe.db.get_value("Company", company, "abbr") or "J"

    customers = [
        {"customer_name": "Reliance Retail Ltd", "gstin": "27AABCU9603R1ZN", "territory": "India"},
        {"customer_name": "Tata Motors Dealership", "gstin": "27AADCT2378N1Z5", "territory": "India"},
        {"customer_name": "Infosys Ltd", "gstin": "29AABCU9603R1ZM", "territory": "India"},
        {"customer_name": "Wipro Technologies", "gstin": "29AAACW1234H1Z2", "territory": "India"},
        {"customer_name": "HDFC Bank Branch", "gstin": "27AAACH1234H1Z5", "territory": "India"},
    ]

    for cust in customers:
        if not frappe.db.exists("Customer", cust["customer_name"]):
            doc = frappe.new_doc("Customer")
            doc.customer_name = cust["customer_name"]
            doc.gst_category = "Registered Regular"
            doc.territory = cust["territory"]
            try:
                doc.insert()
                # Set GSTIN after insert to bypass validation hooks
                frappe.db.set_value("Customer", doc.name, "gstin", cust["gstin"])
                print(f"Created customer: {cust['customer_name']}")
            except Exception as e:
                print(f"Could not create customer {cust['customer_name']}: {e}")
        else:
            print(f"Customer exists: {cust['customer_name']}")

    suppliers = [
        {"supplier_name": "Dell India Pvt Ltd", "gstin": "27AAACD1234H1Z5"},
        {"supplier_name": "HP India Sales", "gstin": "27AAACH1234H1Z5"},
        {"supplier_name": "Staples India", "gstin": "29AABCS1234H1Z5"},
        {"supplier_name": "Canon India Pvt Ltd", "gstin": "07AAACC1234H1Z5"},
        {"supplier_name": "Cisco Systems India", "gstin": "29AABCC1234H1Z5"},
    ]

    for sup in suppliers:
        if not frappe.db.exists("Supplier", sup["supplier_name"]):
            doc = frappe.new_doc("Supplier")
            doc.supplier_name = sup["supplier_name"]
            doc.gst_category = "Registered Regular"
            try:
                doc.insert()
                # Set GSTIN after insert to bypass validation hooks
                frappe.db.set_value("Supplier", doc.name, "gstin", sup["gstin"])
                print(f"Created supplier: {sup['supplier_name']}")
            except Exception as e:
                print(f"Could not create supplier {sup['supplier_name']}: {e}")
        else:
            print(f"Supplier exists: {sup['supplier_name']}")


def create_demo_sales_invoices(company, abbr):
    """Create sales invoices with GST across multiple months."""
    items = frappe.get_all("Item", filters={"item_group": ["in", ["Products", "Services"]]}, fields=["name", "standard_rate"], limit=5)
    if not items:
        print("No items found for sales invoices")
        return

    customers = frappe.get_all("Customer", fields=["name"], limit=5)
    if not customers:
        print("No customers found for sales invoices")
        return

    # Create invoices for past 6 months
    base_date = getdate(today())
    months_back = 6

    for month_offset in range(months_back, -1, -1):
        invoice_date = add_days(base_date, -month_offset * 30)
        if invoice_date.month != base_date.month:
            # Ensure we're in a valid fiscal year
            pass

        # Create 3-5 invoices per month
        num_invoices = random.randint(3, 5)
        for i in range(num_invoices):
            customer = random.choice(customers)
            si = frappe.new_doc("Sales Invoice")
            si.customer = customer["name"]
            si.company = company
            si.posting_date = invoice_date
            si.due_date = add_days(invoice_date, 30)
            si.taxes_and_charges = f"GST 18% - {company}"

            # Add 2-4 items
            num_items = random.randint(2, 4)
            total_amount = 0
            for _ in range(num_items):
                item = random.choice(items)
                qty = random.randint(1, 10)
                rate = item["standard_rate"]
                amount = qty * rate
                total_amount += amount
                si.append("items", {
                    "item_code": item["name"],
                    "qty": qty,
                    "rate": rate,
                    "amount": amount,
                    "warehouse": f"Stores - {abbr}",
                })

            try:
                si.set_missing_values()
                si.calculate_taxes_and_totals()
                si.insert()
                si.submit()
                print(f"Created Sales Invoice {si.name} for {invoice_date}")
            except Exception as e:
                print(f"Could not create Sales Invoice: {e}")
                frappe.db.rollback()

    print(f"Created sales invoices for {months_back} months")


def create_demo_purchase_invoices(company, abbr):
    """Create purchase invoices with GST across multiple months."""
    items = frappe.get_all("Item", filters={"item_group": ["in", ["Products", "Services"]]}, fields=["name", "valuation_rate"], limit=5)
    if not items:
        print("No items found for purchase invoices")
        return

    suppliers = frappe.get_all("Supplier", fields=["name"], limit=5)
    if not suppliers:
        print("No suppliers found for purchase invoices")
        return

    base_date = getdate(today())
    months_back = 6

    for month_offset in range(months_back, -1, -1):
        invoice_date = add_days(base_date, -month_offset * 30)
        num_invoices = random.randint(2, 4)

        for i in range(num_invoices):
            supplier = random.choice(suppliers)
            use_tds = random.random() < 0.3  # 30% chance of TDS

            pi = frappe.new_doc("Purchase Invoice")
            pi.supplier = supplier["name"]
            pi.company = company
            pi.posting_date = invoice_date
            pi.due_date = add_days(invoice_date, 30)
            pi.taxes_and_charges = f"GST 18%{' + TDS' if use_tds else ''} - {company}"

            num_items = random.randint(2, 4)
            for _ in range(num_items):
                item = random.choice(items)
                qty = random.randint(5, 20)
                rate = item["valuation_rate"] * random.uniform(0.9, 1.1)
                pi.append("items", {
                    "item_code": item["name"],
                    "qty": qty,
                    "rate": round(rate, 2),
                    "warehouse": f"Stores - {abbr}",
                })

            try:
                pi.set_missing_values()
                pi.calculate_taxes_and_totals()
                pi.insert()
                pi.submit()
                print(f"Created Purchase Invoice {pi.name} for {invoice_date} {'with TDS' if use_tds else ''}")
            except Exception as e:
                print(f"Could not create Purchase Invoice: {e}")
                frappe.db.rollback()

    print(f"Created purchase invoices for {months_back} months")


def create_gl_entries_for_tax_accounts(company, abbr):
    """Create GL entries for tax liability and asset accounts."""
    # This creates additional GL entries for ITC health and TDS tracking
    # Some will come from the invoices above, but we add more for variety

    accounts = [
        {"account": f"Input CGST - {abbr}", "debit": 45000, "credit": 0},
        {"account": f"Input SGST - {abbr}", "debit": 45000, "credit": 0},
        {"account": f"Output CGST - {abbr}", "debit": 0, "credit": 52000},
        {"account": f"Output SGST - {abbr}", "debit": 0, "credit": 52000},
        {"account": f"TDS Payable - {abbr}", "debit": 0, "credit": 15000},
    ]

    # Create a journal entry
    je = frappe.new_doc("Journal Entry")
    je.company = company
    je.posting_date = add_days(today(), -15)
    je.voucher_type = "Journal Entry"
    je.remark = "Tax adjustment entry for demo"

    for acc in accounts:
        je.append("accounts", {
            "account": acc["account"],
            "debit_in_account_currency": acc["debit"],
            "credit_in_account_currency": acc["credit"],
        })

    # Balance with a suspense account
    total_debit = sum(a["debit"] for a in accounts)
    total_credit = sum(a["credit"] for a in accounts)
    diff = total_credit - total_debit
    if diff != 0:
        je.append("accounts", {
            "account": f"Cash - {abbr}",
            "debit_in_account_currency": max(0, diff),
            "credit_in_account_currency": max(0, -diff),
        })

    try:
        je.insert()
        je.submit()
        print(f"Created Journal Entry {je.name} for tax GL entries")
    except Exception as e:
        print(f"Could not create Journal Entry: {e}")


def create_gstr_logs(company):
    """Create GSTR-1 and GSTR-3B log entries if tables exist."""
    # Check if india_compliance tables exist
    try:
        if frappe.db.sql("""SELECT 1 FROM information_schema.tables WHERE table_name = 'tabGSTR-1 Log'"""):
            months = ["2026-01", "2026-02", "2026-03", "2026-04"]
            for month in months:
                if not frappe.db.exists("GSTR-1 Log", {"company": company, "return_period": month}):
                    doc = frappe.new_doc("GSTR-1 Log")
                    doc.company = company
                    doc.return_period = month
                    doc.status = random.choice(["Filed", "Filed", "Pending"])
                    doc.insert()
                    print(f"Created GSTR-1 Log for {month}")
    except Exception as e:
        print(f"GSTR-1 Log setup skipped: {e}")

    try:
        if frappe.db.sql("""SELECT 1 FROM information_schema.tables WHERE table_name = 'tabGSTR-3B Entry'"""):
            months = ["2026-01", "2026-02", "2026-03", "2026-04"]
            for month in months:
                if not frappe.db.exists("GSTR-3B Entry", {"company": company, "return_period": month}):
                    doc = frappe.new_doc("GSTR-3B Entry")
                    doc.company = company
                    doc.return_period = month
                    doc.status = random.choice(["Filed", "Filed", "Pending"])
                    doc.insert()
                    print(f"Created GSTR-3B Entry for {month}")
    except Exception as e:
        print(f"GSTR-3B Entry setup skipped: {e}")


def create_gst_inward_supply(company):
    """Create GST Inward Supply records for reconciliation."""
    try:
        if not frappe.db.sql("""SELECT 1 FROM information_schema.tables WHERE table_name = 'tabGST Inward Supply'"""):
            print("GST Inward Supply table not found")
            return

        suppliers = frappe.get_all("Supplier", fields=["name", "supplier_name", "gstin"], limit=3)

        for i in range(10):
            supplier = random.choice(suppliers) if suppliers else {"name": "Unknown", "supplier_name": "Unknown", "gstin": ""}
            statuses = ["Matched", "Matched", "Matched", "Unmatched", "Mismatch"]

            doc = frappe.new_doc("GST Inward Supply")
            doc.company = company
            doc.supplier_name = supplier["supplier_name"]
            doc.supplier_gstin = supplier.get("gstin", "")
            doc.bill_no = f"SUPP-INV-{i+1:04d}"
            doc.bill_date = add_days(today(), -random.randint(1, 90))
            doc.taxable_value = random.randint(10000, 100000)
            doc.cgst = doc.taxable_value * 0.09
            doc.sgst = doc.taxable_value * 0.09
            doc.igst = 0
            doc.cess = 0
            doc.match_status = random.choice(statuses)
            try:
                doc.insert()
                print(f"Created GST Inward Supply {doc.name}")
            except Exception as e:
                print(f"Could not create GST Inward Supply: {e}")
    except Exception as e:
        print(f"GST Inward Supply setup skipped: {e}")


if __name__ == "__main__":
    create_tax_intelligence_demo_data()
