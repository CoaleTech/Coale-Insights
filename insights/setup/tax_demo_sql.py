# Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""Direct SQL Demo Data for Tax Intelligence Dashboard (India GST)"""

import frappe
from frappe.utils import today, add_days, getdate, now_datetime
import random
from datetime import datetime


def create_tax_demo_data_sql():
    """Create demo data using direct SQL inserts for guaranteed persistence."""
    company = "JKM"
    abbr = "J"
    fy_start = "2026-01-01"
    fy_end = "2026-12-31"

    # Update company
    frappe.db.sql("""
        UPDATE `tabCompany`
        SET gst_category = 'Registered Regular',
            gstin = '27AAPFU0939F1ZV',
            default_gst_rate = 18.0
        WHERE name = %s
    """, (company,))

    # Create accounts
    create_accounts_sql(company, abbr)

    # Create items
    create_items_sql(company, abbr)

    # Create customers
    create_customers_sql(company)

    # Create suppliers
    create_suppliers_sql(company)

    # Create sales invoices with GST
    create_sales_invoices_sql(company, abbr, fy_start, fy_end)

    # Create purchase invoices with GST
    create_purchase_invoices_sql(company, abbr, fy_start, fy_end)

    # Create GL entries
    create_gl_entries_sql(company, abbr, fy_start, fy_end)

    # Create GSTR logs
    create_gstr_logs_sql(company)

    # Create GST Inward Supply
    create_gst_inward_supply_sql(company)

    frappe.db.commit()
    print("Tax Intelligence demo data created successfully via SQL!")


def create_accounts_sql(company, abbr):
    """Create GST accounts via SQL."""
    accounts = [
        ("Output CGST", "Duties and Taxes", "Tax", "Liability"),
        ("Output SGST", "Duties and Taxes", "Tax", "Liability"),
        ("Output IGST", "Duties and Taxes", "Tax", "Liability"),
        ("Input CGST", "Tax Assets", "Tax", "Asset"),
        ("Input SGST", "Tax Assets", "Tax", "Asset"),
        ("Input IGST", "Tax Assets", "Tax", "Asset"),
        ("TDS Payable", "Duties and Taxes", "Payable", "Liability"),
        ("WHT Receivable", "Tax Assets", "Receivable", "Asset"),
        ("Entertainment Expenses", "Indirect Expenses", "Expense Account", "Expense"),
        ("Donations", "Indirect Expenses", "Expense Account", "Expense"),
        ("Penalties and Fines", "Indirect Expenses", "Expense Account", "Expense"),
    ]

    # Ensure Tax Assets parent exists
    tax_assets = f"Tax Assets - {abbr}"
    if not frappe.db.exists("Account", tax_assets):
        frappe.db.sql("""
            INSERT INTO `tabAccount` (name, account_name, parent_account, company, root_type, account_type, is_group, lft, rgt, docstatus, creation, modified)
            VALUES (%s, 'Tax Assets', %s, %s, 'Asset', '', 1, 1, 2, 0, NOW(), NOW())
        """, (tax_assets, f"Current Assets - {abbr}", company))

    for acc_name, parent, acc_type, root_type in accounts:
        full_name = f"{acc_name} - {abbr}"
        parent_name = f"{parent} - {abbr}"
        if not frappe.db.exists("Account", full_name):
            frappe.db.sql("""
                INSERT INTO `tabAccount` (name, account_name, parent_account, company, root_type, account_type, is_group, lft, rgt, docstatus, creation, modified)
                VALUES (%s, %s, %s, %s, %s, %s, 0, 1, 2, 0, NOW(), NOW())
            """, (full_name, acc_name, parent_name, company, root_type, acc_type))
            print(f"Created account: {full_name}")
        else:
            print(f"Account exists: {full_name}")


def create_items_sql(company, abbr):
    """Create items with HSN codes via SQL."""
    items = [
        ("LAPTOP-001", "Business Laptop Dell XPS", "Products", "847130", 75000, 95000),
        ("DESK-001", "Executive Office Desk", "Products", "940330", 12000, 15000),
        ("CHAIR-001", "Ergonomic Office Chair", "Products", "940310", 8000, 10000),
        ("PAPER-001", "A4 Copier Paper (Ream)", "Products", "480256", 250, 300),
        ("INK-001", "Printer Ink Cartridge", "Products", "321511", 1500, 1800),
        ("CAB-001", "Network Cable Cat 6", "Products", "854442", 500, 650),
        ("ROUTER-001", "WiFi Router TP-Link", "Products", "851762", 3500, 4200),
        ("SOFT-001", "Software License Annual", "Services", "852349", 50000, 60000),
    ]

    for item_code, item_name, item_group, hsn, valuation_rate, standard_rate in items:
        if not frappe.db.exists("Item", item_code):
            frappe.db.sql("""
                INSERT INTO `tabItem` (name, item_code, item_name, item_group, gst_hsn_code, valuation_rate, standard_rate, is_stock_item, stock_uom, docstatus, creation, modified, owner)
                VALUES (%s, %s, %s, %s, %s, %s, %s, 1, 'Nos', 0, NOW(), NOW(), 'Administrator')
            """, (item_code, item_code, item_name, item_group, hsn, valuation_rate, standard_rate))
            print(f"Created item: {item_code}")
        else:
            print(f"Item exists: {item_code}")


def create_customers_sql(company):
    """Create customers with GSTIN via SQL."""
    customers = [
        ("Reliance Retail Ltd", "27AABCU9603R1ZV"),
        ("Tata Motors Dealership", "27AADCT2378N1Z5"),
        ("Infosys Ltd", "29AABCU9603R1ZM"),
        ("Wipro Technologies", "29AAACW1234H1Z2"),
        ("HDFC Bank Branch", "27AAACH1234H1Z5"),
    ]

    for cust_name, gstin in customers:
        if not frappe.db.exists("Customer", cust_name):
            frappe.db.sql("""
                INSERT INTO `tabCustomer` (name, customer_name, gst_category, territory, docstatus, creation, modified, owner)
                VALUES (%s, %s, 'Registered Regular', 'India', 0, NOW(), NOW(), 'Administrator')
            """, (cust_name, cust_name))
            frappe.db.sql("UPDATE `tabCustomer` SET gstin = %s WHERE name = %s", (gstin, cust_name))
            print(f"Created customer: {cust_name}")
        else:
            print(f"Customer exists: {cust_name}")


def create_suppliers_sql(company):
    """Create suppliers with GSTIN via SQL."""
    suppliers = [
        ("Dell India Pvt Ltd", "27AAACD1234H1Z5"),
        ("HP India Sales", "27AAACH1234H1Z5"),
        ("Staples India", "29AABCS1234H1Z5"),
        ("Canon India Pvt Ltd", "07AAACC1234H1Z5"),
        ("Cisco Systems India", "29AABCC1234H1Z5"),
    ]

    for sup_name, gstin in suppliers:
        if not frappe.db.exists("Supplier", sup_name):
            frappe.db.sql("""
                INSERT INTO `tabSupplier` (name, supplier_name, supplier_type, gst_category, docstatus, creation, modified, owner)
                VALUES (%s, %s, 'Company', 'Registered Regular', 0, NOW(), NOW(), 'Administrator')
            """, (sup_name, sup_name))
            frappe.db.sql("UPDATE `tabSupplier` SET gstin = %s WHERE name = %s", (gstin, sup_name))
            print(f"Created supplier: {sup_name}")
        else:
            print(f"Supplier exists: {sup_name}")


def create_sales_invoices_sql(company, abbr, fy_start, fy_end):
    """Create sales invoices with GST via SQL."""
    items = frappe.get_all("Item", fields=["name", "standard_rate"], limit=5)
    customers = frappe.get_all("Customer", fields=["name"], limit=5)

    if not items or not customers:
        print("Missing items or customers for sales invoices")
        return

    base_date = getdate(today())
    months_back = 6
    invoice_counter = 1

    for month_offset in range(months_back, -1, -1):
        invoice_date = add_days(base_date, -month_offset * 30)
        num_invoices = random.randint(3, 5)

        for _ in range(num_invoices):
            customer = random.choice(customers)
            inv_name = f"SINV-DEMO-{invoice_counter:04d}"
            invoice_counter += 1

            # Calculate totals
            num_items = random.randint(2, 4)
            total_net = 0
            for _ in range(num_items):
                item = random.choice(items)
                qty = random.randint(1, 10)
                rate = item["standard_rate"]
                total_net += qty * rate

            cgst = round(total_net * 0.09, 2)
            sgst = round(total_net * 0.09, 2)
            grand_total = round(total_net + cgst + sgst, 2)

            # Insert Sales Invoice
            frappe.db.sql("""
                INSERT INTO `tabSales Invoice`
                (name, customer, company, posting_date, due_date, base_net_total, base_grand_total, grand_total, docstatus,
                 status, is_return, is_debit_note, currency, conversion_rate, creation, modified, owner, naming_series)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 1, 'Submitted', 0, 0, 'INR', 1, NOW(), NOW(), 'Administrator', 'SINV-.YYYY.-.#####')
            """, (inv_name, customer["name"], company, invoice_date, add_days(invoice_date, 30),
                  total_net, grand_total, grand_total))

            # Insert Sales Taxes and Charges
            tax_row1 = frappe.generate_hash(length=10)
            tax_row2 = frappe.generate_hash(length=10)
            frappe.db.sql("""
                INSERT INTO `tabSales Taxes and Charges`
                (name, parent, parenttype, parentfield, charge_type, account_head, description, rate, tax_amount, base_tax_amount, idx)
                VALUES (%s, %s, 'Sales Invoice', 'taxes', 'On Net Total', %s, 'Output CGST @ 9%%', 9, %s, %s, 1)
            """, (tax_row1, inv_name, f"Output CGST - {abbr}", cgst, cgst))

            frappe.db.sql("""
                INSERT INTO `tabSales Taxes and Charges`
                (name, parent, parenttype, parentfield, charge_type, account_head, description, rate, tax_amount, base_tax_amount, idx)
                VALUES (%s, %s, 'Sales Invoice', 'taxes', 'On Net Total', %s, 'Output SGST @ 9%%', 9, %s, %s, 2)
            """, (tax_row2, inv_name, f"Output SGST - {abbr}", sgst, sgst))

            # Insert Sales Invoice Items
            for idx in range(1, num_items + 1):
                item = random.choice(items)
                qty = random.randint(1, 10)
                rate = item["standard_rate"]
                amount = qty * rate
                hsn = frappe.db.get_value("Item", item["name"], "gst_hsn_code") or ""
                item_row = frappe.generate_hash(length=10)
                frappe.db.sql("""
                    INSERT INTO `tabSales Invoice Item`
                    (name, parent, parenttype, parentfield, item_code, item_name, qty, rate, amount, base_rate, base_amount, gst_hsn_code, idx, warehouse)
                    VALUES (%s, %s, 'Sales Invoice', 'items', %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (item_row, inv_name, item["name"], item["name"], qty, rate, amount, rate, amount, hsn, idx, f"Stores - {abbr}"))

            print(f"Created Sales Invoice: {inv_name} for {invoice_date} (Total: {grand_total})")

    print(f"Created {invoice_counter - 1} sales invoices")


def create_purchase_invoices_sql(company, abbr, fy_start, fy_end):
    """Create purchase invoices with GST via SQL."""
    items = frappe.get_all("Item", fields=["name", "valuation_rate"], limit=5)
    suppliers = frappe.get_all("Supplier", fields=["name"], limit=5)

    if not items or not suppliers:
        print("Missing items or suppliers for purchase invoices")
        return

    base_date = getdate(today())
    months_back = 6
    invoice_counter = 1

    for month_offset in range(months_back, -1, -1):
        invoice_date = add_days(base_date, -month_offset * 30)
        num_invoices = random.randint(2, 4)

        for _ in range(num_invoices):
            supplier = random.choice(suppliers)
            inv_name = f"PINV-DEMO-{invoice_counter:04d}"
            invoice_counter += 1
            use_tds = random.random() < 0.3

            num_items = random.randint(2, 4)
            total_net = 0
            for _ in range(num_items):
                item = random.choice(items)
                qty = random.randint(5, 20)
                rate = item["valuation_rate"] * random.uniform(0.9, 1.1)
                total_net += qty * rate

            cgst = round(total_net * 0.09, 2)
            sgst = round(total_net * 0.09, 2)
            tds_amount = round(total_net * 0.02, 2) if use_tds else 0
            grand_total = round(total_net + cgst + sgst - tds_amount, 2)

            frappe.db.sql("""
                INSERT INTO `tabPurchase Invoice`
                (name, supplier, company, posting_date, due_date, base_net_total, base_grand_total, grand_total, docstatus,
                 status, is_return, currency, conversion_rate, creation, modified, owner, naming_series)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 1, 'Submitted', 0, 'INR', 1, NOW(), NOW(), 'Administrator', 'PINV-.YYYY.-.#####')
            """, (inv_name, supplier["name"], company, invoice_date, add_days(invoice_date, 30),
                  total_net, grand_total, grand_total))

            # Insert Purchase Taxes and Charges
            pt_row1 = frappe.generate_hash(length=10)
            pt_row2 = frappe.generate_hash(length=10)
            frappe.db.sql("""
                INSERT INTO `tabPurchase Taxes and Charges`
                (name, parent, parenttype, parentfield, charge_type, account_head, description, rate, tax_amount, base_tax_amount, add_deduct_tax, idx)
                VALUES (%s, %s, 'Purchase Invoice', 'taxes', 'On Net Total', %s, 'Input CGST @ 9%%', 9, %s, %s, 'Add', 1)
            """, (pt_row1, inv_name, f"Input CGST - {abbr}", cgst, cgst))

            frappe.db.sql("""
                INSERT INTO `tabPurchase Taxes and Charges`
                (name, parent, parenttype, parentfield, charge_type, account_head, description, rate, tax_amount, base_tax_amount, add_deduct_tax, idx)
                VALUES (%s, %s, 'Purchase Invoice', 'taxes', 'On Net Total', %s, 'Input SGST @ 9%%', 9, %s, %s, 'Add', 2)
            """, (pt_row2, inv_name, f"Input SGST - {abbr}", sgst, sgst))

            if use_tds:
                pt_row3 = frappe.generate_hash(length=10)
                frappe.db.sql("""
                    INSERT INTO `tabPurchase Taxes and Charges`
                    (name, parent, parenttype, parentfield, charge_type, account_head, description, rate, tax_amount, base_tax_amount, add_deduct_tax, idx)
                    VALUES (%s, %s, 'Purchase Invoice', 'taxes', 'On Net Total', %s, 'TDS @ 2%%', 2, %s, %s, 'Deduct', 3)
                """, (pt_row3, inv_name, f"TDS Payable - {abbr}", tds_amount, tds_amount))

            # Insert Purchase Invoice Items
            for idx in range(1, num_items + 1):
                item = random.choice(items)
                qty = random.randint(5, 20)
                rate = item["valuation_rate"] * random.uniform(0.9, 1.1)
                amount = qty * rate
                item_row = frappe.generate_hash(length=10)
                frappe.db.sql("""
                    INSERT INTO `tabPurchase Invoice Item`
                    (name, parent, parenttype, parentfield, item_code, item_name, qty, rate, amount, base_rate, base_amount, idx, warehouse)
                    VALUES (%s, %s, 'Purchase Invoice', 'items', %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (item_row, inv_name, item["name"], item["name"], qty, round(rate, 2), round(amount, 2), round(rate, 2), round(amount, 2), idx, f"Stores - {abbr}"))

            print(f"Created Purchase Invoice: {inv_name} for {invoice_date} {'with TDS' if use_tds else ''} (Total: {grand_total})")

    print(f"Created {invoice_counter - 1} purchase invoices")


def create_gl_entries_sql(company, abbr, fy_start, fy_end):
    """Create GL entries for tax accounts."""
    je_name = f"JE-TAX-DEMO-001"

    if frappe.db.exists("Journal Entry", je_name):
        print(f"Journal Entry {je_name} exists")
        return

    posting_date = add_days(today(), -15)

    # Create Journal Entry header
    frappe.db.sql("""
        INSERT INTO `tabJournal Entry`
        (name, company, posting_date, voucher_type, remark, total_debit, total_credit, docstatus, creation, modified, owner)
        VALUES (%s, %s, %s, 'Journal Entry', 'Tax adjustment entry for demo', 97000, 97000, 1, NOW(), NOW(), 'Administrator')
    """, (je_name, company, posting_date))

    # Insert GL Entries
    gl_entries = [
        (f"Input CGST - {abbr}", 45000, 0),
        (f"Input SGST - {abbr}", 45000, 0),
        (f"Output CGST - {abbr}", 0, 52000),
        (f"Output SGST - {abbr}", 0, 52000),
        (f"TDS Payable - {abbr}", 0, 15000),
        (f"Cash - {abbr}", 37000, 0),
    ]

    for account, debit, credit in gl_entries:
        frappe.db.sql("""
            INSERT INTO `tabGL Entry`
            (name, posting_date, account, company, debit, credit, debit_in_account_currency, credit_in_account_currency,
             voucher_type, voucher_no, against_voucher_type, against_voucher, is_cancelled, creation, modified, owner)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'Journal Entry', %s, '', '', 0, NOW(), NOW(), 'Administrator')
        """, (frappe.generate_hash(), posting_date, account, company, debit, credit, debit, credit, je_name))

    print(f"Created Journal Entry {je_name} with GL entries")


def create_gstr_logs_sql(company):
    """Create GSTR logs via SQL."""
    try:
        if frappe.db.sql("""SELECT 1 FROM information_schema.tables WHERE table_name = 'tabGSTR-1 Log'"""):
            months = ["2026-01", "2026-02", "2026-03", "2026-04"]
            for month in months:
                log_name = f"GSTR1-DEMO-{month}"
                if not frappe.db.exists("GSTR-1 Log", log_name):
                    frappe.db.sql("""
                        INSERT INTO `tabGSTR-1 Log` (name, company, return_period, status, creation, modified, owner)
                        VALUES (%s, %s, %s, %s, NOW(), NOW(), 'Administrator')
                    """, (log_name, company, month, random.choice(["Filed", "Filed", "Pending"])))
                    print(f"Created GSTR-1 Log for {month}")
    except Exception as e:
        print(f"GSTR-1 Log setup skipped: {e}")

    try:
        if frappe.db.sql("""SELECT 1 FROM information_schema.tables WHERE table_name = 'tabGSTR-3B Entry'"""):
            months = ["2026-01", "2026-02", "2026-03", "2026-04"]
            for month in months:
                entry_name = f"GSTR3B-DEMO-{month}"
                if not frappe.db.exists("GSTR-3B Entry", entry_name):
                    frappe.db.sql("""
                        INSERT INTO `tabGSTR-3B Entry` (name, company, return_period, status, creation, modified, owner)
                        VALUES (%s, %s, %s, %s, NOW(), NOW(), 'Administrator')
                    """, (entry_name, company, month, random.choice(["Filed", "Filed", "Pending"])))
                    print(f"Created GSTR-3B Entry for {month}")
    except Exception as e:
        print(f"GSTR-3B Entry setup skipped: {e}")


def create_gst_inward_supply_sql(company):
    """Create GST Inward Supply records via SQL."""
    try:
        if not frappe.db.sql("""SELECT 1 FROM information_schema.tables WHERE table_name = 'tabGST Inward Supply'"""):
            print("GST Inward Supply table not found")
            return

        suppliers = frappe.get_all("Supplier", fields=["name", "supplier_name", "gstin"], limit=3)
        statuses = ["Exact Match", "Exact Match", "Exact Match", "Suggested Match", "Mismatch", "Unlinked"]

        for i in range(10):
            supplier = random.choice(suppliers) if suppliers else {"name": "Unknown", "supplier_name": "Unknown", "gstin": ""}
            inv_name = f"GIS-DEMO-{i+1:04d}"
            taxable = random.randint(10000, 100000)
            cgst = round(taxable * 0.09, 2)
            sgst = round(taxable * 0.09, 2)

            frappe.db.sql("""
                INSERT INTO `tabGST Inward Supply`
                (name, company, supplier_name, supplier_gstin, bill_no, bill_date, taxable_value, cgst, sgst, igst, cess, match_status, creation, modified, owner)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 0, 0, %s, NOW(), NOW(), 'Administrator')
            """, (inv_name, company, supplier["supplier_name"], supplier.get("gstin", ""), f"SUPP-INV-{i+1:04d}",
                  add_days(today(), -random.randint(1, 90)), taxable, cgst, sgst, random.choice(statuses)))
            print(f"Created GST Inward Supply {inv_name}")
    except Exception as e:
        print(f"GST Inward Supply setup skipped: {e}")


if __name__ == "__main__":
    create_tax_demo_data_sql()
