import frappe
from frappe.query_builder import DocType

from insights.decorators import validate_type
from insights.api.response import success, error

public_doctypes = [
    "Insights Dashboard v3",
    "Insights Chart v3",
    "Insights Query v3",
]


def check_public_access(doctype, name):
    if not is_public(doctype, name):
        raise frappe.PermissionError("You don't have permission to access this document")


def is_public(doctype: str, name: str):
    if doctype not in public_doctypes:
        return False
    if get_preview_key():
        return True
    return get_public_root(doctype, name) is not None


def get_public_root(doctype: str, name: str) -> tuple[str, str] | None:
    """The published document that makes `doctype`/`name` reachable without a login.

    Returns the (doctype, name) of the published root so callers can read its
    `permission_user`. Takes the oldest root so the answer is stable.
    """
    if doctype == "Insights Dashboard v3":
        return ("Insights Dashboard v3", name) if is_public_dashboard(name) else None
    if doctype == "Insights Chart v3":
        return _get_chart_root(name)
    if doctype == "Insights Query v3":
        for chart in _get_charts_built_on(name):
            root = _get_chart_root(chart)
            if root:
                return root
    return None


def _get_chart_root(name: str) -> tuple[str, str] | None:
    if frappe.db.get_value("Insights Chart v3", name, "is_public"):
        return ("Insights Chart v3", name)
    dashboard = _get_oldest_public_dashboard_holding(name)
    return ("Insights Dashboard v3", dashboard) if dashboard else None


def _get_oldest_public_dashboard_holding(chart: str) -> str | None:
    """Oldest published dashboard that holds `chart` — stable across calls."""
    Dashboard = DocType("Insights Dashboard v3")
    DashboardChart = DocType("Insights Dashboard Chart v3")
    holders = (
        frappe.qb.from_(DashboardChart)
        .select(DashboardChart.parent)
        .where(DashboardChart.chart == chart)
    )
    rows = (
        frappe.qb.from_(Dashboard)
        .select(Dashboard.name)
        .where((Dashboard.is_public == 1) & Dashboard.name.isin(holders))
        .orderby(Dashboard.creation)
        .limit(1)
        .run(pluck=True)
    )
    return rows[0] if rows else None


def _get_charts_built_on(query: str) -> list[str]:
    return frappe.get_all(
        "Insights Chart v3",
        or_filters=[["query", "=", query], ["data_query", "=", query]],
        order_by="creation asc",
        pluck="name",
    )


def get_public_permission_user(doctype: str, name: str) -> str | None:
    """The user a public execution of `doctype`/`name` filters its rows by.

    A preview runs as the user the key was cut for.  Everything else runs as
    the user the root recorded when it was published.
    """
    key = get_preview_key()
    if key:
        return key.get("user")
    root = get_public_root(doctype, name)
    return frappe.db.get_value(*root, "permission_user") if root else None



@validate_type
def is_public_workbook(name: str):
    public_dashboard_exists = frappe.db.exists(
        "Insights Dashboard v3",
        {
            "workbook": name,
            "is_public": 1,
        },
    )
    if public_dashboard_exists:
        return True

    public_charts = get_public_charts()
    return frappe.db.exists(
        "Insights Chart v3",
        {
            "workbook": name,
            "name": ["in", public_charts],
        },
    )


def get_preview_key():
    """The cached preview-key payload, or None."""
    key = frappe.request and frappe.request.headers.get("X-Insights-Preview-Key")
    if not key:
        return None
    return frappe.cache.get_value(f"insights_preview_key:{key}")


def has_valid_preview_key():
    return bool(get_preview_key())


@validate_type
def is_public_dashboard(name: str):
    return frappe.db.exists(
        "Insights Dashboard v3",
        {
            "name": name,
            "is_public": 1,
        },
    )


def get_public_charts():
    Chart = DocType("Insights Chart v3")
    Dashboard = DocType("Insights Dashboard v3")
    DashboardChart = DocType("Insights Dashboard Chart v3")

    public_dashboards = frappe.qb.from_(Dashboard).select(Dashboard.name).where(Dashboard.is_public == 1)

    charts = (
        frappe.qb.from_(Chart)
        .select(Chart.name)
        .where(
            (Chart.is_public == 1)
            | (
                Chart.name.isin(
                    frappe.qb.from_(DashboardChart)
                    .select(DashboardChart.chart)
                    .where(DashboardChart.parent.isin(public_dashboards))
                )
            )
        )
        .run(pluck=True)
    )

    return list(set(charts))


@validate_type
def is_public_chart(name: str):
    is_public = frappe.db.exists(
        "Insights Chart v3",
        {
            "name": name,
            "is_public": 1,
        },
    )
    if is_public:
        return True

    return name in get_public_charts()


@validate_type
def is_public_query(name: str):
    # find a public chart that is linked with this query
    linked_charts = frappe.get_all(
        "Insights Chart v3",
        or_filters=[
            ["query", "=", name],
            ["data_query", "=", name],
        ],
        pluck="name",
    )
    public_charts = get_public_charts()
    if any(chart in public_charts for chart in linked_charts):
        return True

    return False


@frappe.whitelist(allow_guest=True)
@validate_type
def get_dashboard_name(dashboard_name: str):
    name = dashboard_name
    if not frappe.db.exists("Insights Dashboard v3", name):
        new_name = frappe.db.exists("Insights Dashboard v3", {"old_name": name})
        if new_name:
            name = new_name
    return name


@frappe.whitelist(allow_guest=True)
@validate_type
def get_chart_name(chart_name: str):
    name = chart_name
    if not frappe.db.exists("Insights Chart v3", name):
        new_name = frappe.db.exists("Insights Chart v3", {"old_name": name})
        if new_name:
            name = new_name
    return name
