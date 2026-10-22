# Copyright (c) 2022, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""
Document method proxy API
Allows public (guest-accessible) doc reads and method execution.
"""

import frappe
from frappe.handler import is_valid_http_method, is_whitelisted
from frappe.monitor import add_data_to_monitor

from insights.api.shared import get_public_permission_user, is_public
from insights.decorators import validate_type


# A public execution runs what the publisher published. The surface is the set
# of parameter names the published document's methods accept from a viewer,
# not the builder's own parameters (active_operation_idx, force, …).
PUBLIC_METHOD_ARGS: dict[tuple[str, str], set[str]] = {
    ("Insights Query v3", "execute"): {"adhoc_filters"},
    ("Insights Query v3", "download_results"): {"format", "adhoc_filters"},
    ("Insights Dashboard v3", "get_distinct_column_values"): {
        "query",
        "column_name",
        "search_term",
        "adhoc_filters",
    },
    ("Insights Dashboard v3", "track_view"): set(),
}


def is_public_method(doctype: str, method: str) -> bool:
    return (doctype, method) in PUBLIC_METHOD_ARGS


def public_method_args(doctype: str, method: str, args: dict | str | None) -> dict:
    """The caller's args, stripped of anything the public contract does not name.

    Dropped rather than refused so the published document still renders.
    """
    allowed = PUBLIC_METHOD_ARGS.get((doctype, method), set())
    args = frappe.parse_json(args) or {}
    return {k: v for k, v in args.items() if k in allowed}



def _execute_doc_method(doc, method: str, args: dict | None = None, ignore_permissions=False):
    args = frappe.parse_json(args)
    method_obj = getattr(doc, method)
    fn = getattr(method_obj, "__func__", method_obj)

    if not ignore_permissions:
        doc.check_permission("read")
        is_whitelisted(fn)
        is_valid_http_method(fn)

    new_kwargs = frappe.get_newargs(fn, args)
    response = doc.run_method(method, **new_kwargs)
    frappe.response.docs.append(doc)
    frappe.response["message"] = response
    add_data_to_monitor(methodname=method)
    return response


@frappe.whitelist(allow_guest=True)  # nosemgrep - falls back to is_public() only after the
# framework has already refused the caller
@validate_type
def get_doc(doctype: str, name: str | int):
    """Fetch a document. Falls back to public access for shared docs."""
    try:
        from frappe.client import get as _get_doc

        return _get_doc(doctype, name)
    except frappe.PermissionError:
        if not is_public(doctype, name):
            raise
        doc = frappe.get_doc(doctype, name)
        doc.apply_fieldlevel_read_permissions()
        return doc.as_dict()


@frappe.whitelist(allow_guest=True)  # nosemgrep - guests reach only public documents,
# and only the methods and arguments PUBLIC_METHOD_ARGS names
def run_doc_method(method: str, docs: dict | str, args: dict | None = None):
    """Execute a document method. Guest callers are restricted to PUBLIC_METHOD_ARGS."""
    doc = frappe.parse_json(docs)
    doctype = doc.get("doctype")
    name = doc.get("name")

    if not doctype or not name:
        raise frappe.ValidationError("Invalid document")

    try:
        doc = frappe.get_doc(frappe.parse_json(docs))
        return _execute_doc_method(doc, method, args)

    except frappe.PermissionError:
        if not is_public(doctype, name):
            raise frappe.PermissionError("You don't have permission to access this document")
        if not is_public_method(doctype, method):
            raise frappe.PermissionError("You don't have permission to access this method")

        from insights.permission_user import permission_user

        doc = frappe.get_doc(doctype, name)
        filtered_args = public_method_args(doctype, method, args)
        with permission_user(get_public_permission_user(doctype, name)):
            return _execute_doc_method(doc, method, filtered_args, ignore_permissions=True)


