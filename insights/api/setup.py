# Copyright (c) 2022, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import json

import frappe

from insights.decorators import insights_whitelist
from insights.setup.demo import DemoDataFactory
from insights.api.response import success, error


@insights_whitelist()
def setup_complete():
    return bool(frappe.get_single("Insights Settings").setup_complete)


@insights_whitelist(methods=["POST"])
def update_erpnext_source_title(title):
    frappe.db.set_value("Insights Data Source v3", "Site DB", "title", title)


@insights_whitelist(methods=["POST"])
def setup_sample_data(dataset):
    factory = DemoDataFactory()
    factory.run()


@insights_whitelist(methods=["POST"])
def submit_survey_responses(responses):
    responses = frappe.parse_json(responses)

    try:
        responses = json.dumps(responses, default=str, indent=4)
        frappe.integrations.utils.make_post_request(
            "https://frappeinsights.com/api/method/insights.telemetry.submit_survey_responses",
            data={"response": responses},
        )
    except Exception:
        frappe.log_error(title="Error submitting survey responses")


@insights_whitelist(methods=["POST"])
def complete_setup():
    settings = frappe.get_single("Insights Settings")
    settings.setup_complete = 1
    settings.save()
