import frappe
from datetime import datetime
from insights.ml.base import sanitize_for_json


def success(data=None, message=None):
    result = {"status": "success"}
    if data is not None:
        result["data"] = sanitize_for_json(data)
    if message:
        result["message"] = message
    return result


def error(message, exc=None):
    if exc:
        frappe.log_error(str(exc), "Insights API Error")
    return {
        "status": "error",
        "message": message,
        "timestamp": datetime.now().isoformat()
    }
