import frappe


def execute():
    """Remove all V2 DocTypes that have been superseded by V3 equivalents.

    V3 uses the workbook architecture. V2 DocTypes are no longer needed.
    This patch deletes the DocType definitions and drops their database tables.
    """
    # Child tables and related DocTypes first (before parents)
    v2_doctypes = [
        # Child tables
        "Insights Query Chart",
        "Insights Query Column",
        "Insights Query Table",
        "Insights Query Transform",
        # NOTE: "Insights Query Variable" is kept - still used by Insights Query v3
        # NOTE: "Insights Query Execution Log" is kept - still used by V3 ibis_utils
        "Insights Query Result",
        "Insights Table Column",
        "Insights Table Import Log",
        "Insights Dashboard Item",
        # Related DocTypes
        "Insights Table Import",
        "Insights Notebook Page",
        # Primary V2 DocTypes
        "Insights Query",
        "Insights Chart",
        "Insights Dashboard",
        "Insights Data Source",
        "Insights Table",
        "Insights Table Link",
    ]

    for dt in v2_doctypes:
        try:
            if frappe.db.exists("DocType", dt):
                count = frappe.db.count(dt)
                if count:
                    frappe.log_error(
                        title="V2 DocType Removal",
                        message=f"Deleting {dt}: {count} records"
                    )
                frappe.delete_doc("DocType", dt, force=True, ignore_missing=True)
                frappe.db.commit()
        except Exception as e:
            # If the table is already gone, just delete the DocType record
            try:
                frappe.db.delete("DocType", {"name": dt})
                frappe.db.delete("DocField", {"parent": dt})
                frappe.db.delete("DocPerm", {"parent": dt})
                frappe.db.commit()
            except Exception:
                pass
