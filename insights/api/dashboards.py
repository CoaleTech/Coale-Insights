import frappe
from frappe.query_builder.functions import Count

from insights.decorators import insights_whitelist, validate_type


# v3 API


@insights_whitelist()
def get_dashboards(search_term=None, limit=50):
    dashboards = frappe.get_list(
        "Insights Dashboard v3",
        or_filters={
            "name": ["like", f"%{search_term}%" if search_term else "%"],
            "title": ["like", f"%{search_term}%" if search_term else "%"],
        },
        fields=[
            "name",
            "title",
            "workbook",
            "creation",
            "modified",
            "preview_image",
            "items",
        ],
        order_by="creation desc",
        limit=limit,
    )

    if not dashboards:
        return dashboards

    dashboard_names = [d.name for d in dashboards]

    # Batch fetch view counts — single query instead of N queries
    view_counts = {}
    if dashboard_names:
        ViewLog = frappe.qb.DocType("View Log")
        view_count_rows = (
            frappe.qb.from_(ViewLog)
            .select(ViewLog.reference_name, Count("*").as_("cnt"))
            .where(ViewLog.reference_doctype == "Insights Dashboard v3")
            .where(ViewLog.reference_name.isin(dashboard_names))
            .groupby(ViewLog.reference_name)
            .run(as_dict=True)
        )
        for row in view_count_rows:
            view_counts[row.reference_name] = row.cnt

    for dashboard in dashboards:
        items = frappe.parse_json(dashboard["items"])
        charts = [item for item in items if item["type"] == "chart"]
        dashboard["charts"] = len(charts)
        dashboard["views"] = view_counts.get(dashboard.name, 0)
        del dashboard["items"]

    return dashboards


@insights_whitelist()
@validate_type
def update_dashboard_preview(dashboard_name: str):
    dashboard = frappe.get_doc("Insights Dashboard v3", dashboard_name)
    file_url = dashboard.generate_dashboard_preview()
    if not file_url:
        frappe.msgprint("Preview generation is not configured. Dashboards will work without previews.", indicator="orange")
    return file_url
