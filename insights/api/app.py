# Copyright (c) 2022, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""
App-level API endpoints
Version info, user session, and team contact endpoints.
"""

import frappe
from frappe.defaults import get_user_default, set_user_default
from frappe.integrations.utils import make_post_request
from frappe.rate_limiter import rate_limit

from insights.decorators import insights_whitelist
from insights.api.response import success


@insights_whitelist()
def get_app_version():
    return frappe.get_attr("insights" + ".__version__")


@insights_whitelist()
def get_user_info():
    is_admin = frappe.db.exists(
        "Has Role",
        {
            "parenttype": "User",
            "parent": frappe.session.user,
            "role": ["in", ("Insights Admin")],
        },
    )
    is_user = frappe.db.exists(
        "Has Role",
        {
            "parenttype": "User",
            "parent": frappe.session.user,
            "role": ["in", ("Insights User")],
        },
    )

    user = frappe.db.get_value(
        "User", frappe.session.user, ["first_name", "last_name", "user_type"], as_dict=1
    )

    return success({
        "email": frappe.session.user,
        "first_name": user.get("first_name"),
        "last_name": user.get("last_name"),
        "is_admin": is_admin or frappe.session.user == "Administrator",
        "is_user": is_user or frappe.session.user == "Administrator",
        "country": frappe.db.get_single_value("System Settings", "country"),
        "locale": frappe.db.get_single_value("System Settings", "language"),
        "is_v2_instance": False,
        "default_version": get_user_default("insights_default_version", frappe.session.user),
        "has_desk_access": user.get("user_type") == "System User",
    })


@insights_whitelist(methods=["POST"])
def update_default_version(version):
    if get_user_default("insights_has_visited_v3", frappe.session.user) != "1":
        set_user_default("insights_has_visited_v3", "1", frappe.session.user)

    set_user_default("insights_default_version", version, frappe.session.user)


@frappe.whitelist(methods=["POST"])
@rate_limit(limit=10, seconds=60 * 60)
def contact_team(message_type, message_content, is_critical=False):
    if not message_type or not message_content:
        frappe.throw("Message Type and Content are required")

    message_title = {
        "Feedback": "Feedback from Insights User",
        "Bug": "Bug Report from Insights User",
        "Question": "Question from Insights User",
    }.get(message_type)

    if not message_title:
        frappe.throw("Invalid Message Type")

    try:
        make_post_request(
            "https://frappeinsights.com/api/method/contact-team",
            data={
                "message_title": message_title,
                "message_content": message_content,
            },
        )
    except Exception as e:
        frappe.log_error(e)
        frappe.throw("Something went wrong. Please try again later.")
