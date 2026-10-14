# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""String equality on the Insights DB connection must use the column index,
not ibis's default ``CAST(x AS BINARY) = y``."""

import frappe
import ibis
from frappe.tests.utils import FrappeTestCase

from insights.api.ml.ibis_source import connection, t


class TestPlainEquality(FrappeTestCase):
    def test_string_equality_is_not_cast_to_binary(self):
        tbl = ibis.table({"company": "string", "qty": "int64"}, name="x")
        sql = connection().compile(tbl.filter((tbl.company == "A") & (tbl.qty == 1)))
        self.assertNotIn("BINARY", sql.upper())
        self.assertIn("= 'A'", sql)

    def test_other_connections_keep_stock_compiler(self):
        conf = frappe.conf
        other = ibis.mysql.connect(
            host=conf.get("db_host") or "127.0.0.1",
            port=int(conf.get("db_port") or 3306),
            user=conf.get("db_user") or conf.get("db_name"),
            password=conf.get("db_password"),
            database=conf.get("db_name"),
        )
        self.assertIsNot(other.compiler, connection().compiler)
        self.assertIn("BINARY", other.compile(
            ibis.table({"a": "string"}, name="x").filter(lambda r: r.a == "A")).upper())

    def test_count_matches_frappe(self):
        company = frappe.db.get_value("Sales Invoice", {"docstatus": 1}, "company")
        if not company:
            self.skipTest("no submitted Sales Invoice")
        si = t("Sales Invoice")
        got = si.filter((si.company == company) & (si.docstatus == 1)).count().execute()
        self.assertEqual(int(got), frappe.db.count("Sales Invoice", {"company": company, "docstatus": 1}))
