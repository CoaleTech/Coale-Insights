# Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""HR Data Collector - Headcount, attrition, payroll, attendance, recruitment"""

import frappe
from frappe.utils import flt, cint
from typing import Dict, Any, List

from . import BaseCollector


class HRDataCollector(BaseCollector):
    """Collect HR and workforce data from HRMS module"""

    def collect(self) -> Dict[str, Any]:
        return {
            "headcount": self._get_headcount_analytics(),
            "attrition": self._get_attrition_analytics(),
            "payroll": self._get_payroll_analytics(),
            "attendance": self._get_attendance_analytics(),
            "leave": self._get_leave_analytics(),
            "recruitment": self._get_recruitment_analytics(),
            "performance": self._get_performance_analytics(),
            "workforce_planning": self._get_workforce_planning()
        }

    def _get_headcount_analytics(self) -> Dict[str, Any]:
        """Get headcount analytics"""
        try:
            # Current active employees
            current_employees = frappe.db.count("Employee",
                filters={"status": "Active", "company": self.company})

            # New hires in period
            new_hires = frappe.db.count("Employee",
                filters={
                    "date_of_joining": ["between", [self.from_date, self.to_date]],
                    "status": "Active",
                    "company": self.company
                })

            # Exits in period
            exits = frappe.db.count("Employee",
                filters={
                    "relieving_date": ["between", [self.from_date, self.to_date]],
                    "company": self.company
                })

            # Department breakdown
            dept_breakdown = frappe.db.sql("""
                SELECT department, COUNT(*) as count
                FROM `tabEmployee`
                WHERE status = 'Active' AND company = %s
                AND department IS NOT NULL AND department != ''
                GROUP BY department
                ORDER BY count DESC
            """, (self.company,), as_dict=True)

            # Employment type breakdown
            emp_type_breakdown = frappe.db.sql("""
                SELECT employment_type, COUNT(*) as count
                FROM `tabEmployee`
                WHERE status = 'Active' AND company = %s
                AND employment_type IS NOT NULL AND employment_type != ''
                GROUP BY employment_type
            """, (self.company,), as_dict=True)

            return {
                "total_active": current_employees,
                "new_hires": new_hires,
                "exits": exits,
                "net_change": new_hires - exits,
                "department_breakdown": dept_breakdown,
                "employment_type_breakdown": emp_type_breakdown
            }

        except Exception as e:
            frappe.log_error(f"Error in HR headcount analytics: {e}")
            return {"error": str(e)}

    def _get_attrition_analytics(self) -> Dict[str, Any]:
        """Get attrition and retention metrics"""
        try:
            # Calculate attrition rate for the period
            total_employees = frappe.db.count("Employee",
                filters={"company": self.company})

            exits = frappe.db.count("Employee",
                filters={
                    "relieving_date": ["between", [self.from_date, self.to_date]],
                    "company": self.company
                })

            attrition_rate = (exits / total_employees * 100) if total_employees else 0

            # Voluntary vs involuntary exits
            voluntary_exits = frappe.db.sql("""
                SELECT COUNT(*) as count FROM `tabEmployee`
                WHERE relieving_date BETWEEN %s AND %s
                AND company = %s
                AND (resignation_letter_date IS NOT NULL OR resignation_letter_date != '')
            """, (self.from_date, self.to_date, self.company), as_dict=True)

            voluntary_count = voluntary_exits[0]["count"] if voluntary_exits else 0
            involuntary_count = exits - voluntary_count

            # Exit reasons breakdown
            exit_reasons = frappe.db.sql("""
                SELECT
                    COALESCE(reason_for_leaving, 'Unknown') as reason,
                    COUNT(*) as count
                FROM `tabEmployee`
                WHERE relieving_date BETWEEN %s AND %s
                AND company = %s
                GROUP BY reason_for_leaving
                ORDER BY count DESC
            """, (self.from_date, self.to_date, self.company), as_dict=True)

            return {
                "attrition_rate": round(attrition_rate, 2),
                "total_exits": exits,
                "voluntary_exits": voluntary_count,
                "involuntary_exits": involuntary_count,
                "exit_reasons": exit_reasons
            }

        except Exception as e:
            frappe.log_error(f"Error in HR attrition analytics: {e}")
            return {"error": str(e)}

    def _get_payroll_analytics(self) -> Dict[str, Any]:
        """Get payroll cost analytics"""
        try:
            # Get payroll data from Salary Slip
            payroll_data = frappe.db.sql("""
                SELECT
                    SUM(gross_pay) as total_gross_pay,
                    SUM(total_deduction) as total_deductions,
                    SUM(net_pay) as total_net_pay,
                    AVG(gross_pay) as avg_gross_pay,
                    COUNT(DISTINCT employee) as employees_paid
                FROM `tabSalary Slip`
                WHERE start_date <= %s AND end_date >= %s
                AND company = %s
                AND docstatus = 1
            """, (self.to_date, self.from_date, self.company), as_dict=True)

            data = payroll_data[0] if payroll_data else {}

            # Department-wise payroll cost
            dept_payroll = frappe.db.sql("""
                SELECT
                    e.department,
                    SUM(ss.gross_pay) as total_cost,
                    AVG(ss.gross_pay) as avg_cost,
                    COUNT(DISTINCT ss.employee) as employee_count
                FROM `tabSalary Slip` ss
                JOIN `tabEmployee` e ON ss.employee = e.name
                WHERE ss.start_date <= %s AND ss.end_date >= %s
                AND ss.company = %s AND ss.docstatus = 1
                AND e.department IS NOT NULL AND e.department != ''
                GROUP BY e.department
                ORDER BY total_cost DESC
            """, (self.to_date, self.from_date, self.company), as_dict=True)

            return {
                "total_gross_pay": flt(data.get("total_gross_pay", 0)),
                "total_deductions": flt(data.get("total_deductions", 0)),
                "total_net_pay": flt(data.get("total_net_pay", 0)),
                "average_gross_pay": flt(data.get("avg_gross_pay", 0)),
                "employees_paid": cint(data.get("employees_paid", 0)),
                "department_breakdown": dept_payroll
            }

        except Exception as e:
            frappe.log_error(f"Error in HR payroll analytics: {e}")
            return {"error": str(e)}

    def _get_attendance_analytics(self) -> Dict[str, Any]:
        """Get attendance patterns and metrics"""
        try:
            # Overall attendance statistics
            total_attendance = frappe.db.count("Attendance",
                filters={
                    "attendance_date": ["between", [self.from_date, self.to_date]],
                    "company": self.company,
                    "docstatus": 1
                })

            present_count = frappe.db.count("Attendance",
                filters={
                    "attendance_date": ["between", [self.from_date, self.to_date]],
                    "company": self.company,
                    "status": "Present",
                    "docstatus": 1
                })

            absent_count = frappe.db.count("Attendance",
                filters={
                    "attendance_date": ["between", [self.from_date, self.to_date]],
                    "company": self.company,
                    "status": "Absent",
                    "docstatus": 1
                })

            attendance_rate = (present_count / total_attendance * 100) if total_attendance else 0

            # Late arrivals from Employee Checkin
            late_arrivals = frappe.db.sql("""
                SELECT COUNT(*) as count
                FROM `tabEmployee Checkin` ec
                INNER JOIN `tabEmployee` e ON e.name = ec.employee
                WHERE ec.time >= %s AND ec.time <= %s
                AND e.company = %s
                AND ec.log_type = 'IN'
                AND TIME(ec.time) > '09:30:00'
            """, (self.from_date, self.to_date, self.company), as_dict=True)

            late_count = late_arrivals[0]["count"] if late_arrivals else 0

            return {
                "total_attendance_records": total_attendance,
                "present_days": present_count,
                "absent_days": absent_count,
                "attendance_rate": round(attendance_rate, 2),
                "late_arrivals": late_count
            }

        except Exception as e:
            frappe.log_error(f"Error in HR attendance analytics: {e}")
            return {"error": str(e)}

    def _get_leave_analytics(self) -> Dict[str, Any]:
        """Get leave utilization and patterns"""
        try:
            # Leave applications summary
            total_leaves = frappe.db.sql("""
                SELECT
                    COUNT(*) as total_applications,
                    SUM(total_leave_days) as total_days,
                    AVG(total_leave_days) as avg_days_per_application
                FROM `tabLeave Application`
                WHERE from_date >= %s AND to_date <= %s
                AND company = %s
                AND status = 'Approved'
            """, (self.from_date, self.to_date, self.company), as_dict=True)

            leave_data = total_leaves[0] if total_leaves else {}

            # Leave type breakdown
            leave_types = frappe.db.sql("""
                SELECT
                    leave_type,
                    COUNT(*) as applications,
                    SUM(total_leave_days) as total_days
                FROM `tabLeave Application`
                WHERE from_date >= %s AND to_date <= %s
                AND company = %s
                AND status = 'Approved'
                GROUP BY leave_type
                ORDER BY total_days DESC
            """, (self.from_date, self.to_date, self.company), as_dict=True)

            return {
                "total_applications": cint(leave_data.get("total_applications", 0)),
                "total_leave_days": flt(leave_data.get("total_days", 0)),
                "avg_days_per_application": flt(leave_data.get("avg_days_per_application", 0)),
                "leave_type_breakdown": leave_types
            }

        except Exception as e:
            frappe.log_error(f"Error in HR leave analytics: {e}")
            return {"error": str(e)}

    def _get_recruitment_analytics(self) -> Dict[str, Any]:
        """Get recruitment pipeline and metrics"""
        try:
            # Job openings and applications (if Job Applicant doctype exists)
            if frappe.db.exists("DocType", "Job Applicant"):
                applications = frappe.db.sql("""
                    SELECT
                        COUNT(*) as total_applications,
                        SUM(CASE WHEN status = 'Accepted' THEN 1 ELSE 0 END) as accepted,
                        SUM(CASE WHEN status = 'Rejected' THEN 1 ELSE 0 END) as rejected,
                        SUM(CASE WHEN status = 'Open' THEN 1 ELSE 0 END) as pending
                    FROM `tabJob Applicant`
                    WHERE creation BETWEEN %s AND %s
                """, (self.from_date, self.to_date), as_dict=True)

                app_data = applications[0] if applications else {}

                return {
                    "total_applications": cint(app_data.get("total_applications", 0)),
                    "accepted": cint(app_data.get("accepted", 0)),
                    "rejected": cint(app_data.get("rejected", 0)),
                    "pending": cint(app_data.get("pending", 0)),
                    "success_rate": round((app_data.get("accepted", 0) / app_data.get("total_applications", 1) * 100), 2) if app_data.get("total_applications") else 0
                }
            else:
                return {"message": "Job Applicant module not available"}

        except Exception as e:
            frappe.log_error(f"Error in HR recruitment analytics: {e}")
            return {"error": str(e)}

    def _get_performance_analytics(self) -> Dict[str, Any]:
        """Get performance appraisal data"""
        try:
            # Performance appraisal summary (if Appraisal doctype exists)
            if frappe.db.exists("DocType", "Appraisal"):
                appraisals = frappe.db.sql("""
                    SELECT
                        COUNT(*) as total_appraisals,
                        AVG(total_score) as avg_score
                    FROM `tabAppraisal`
                    WHERE start_date >= %s AND end_date <= %s
                    AND company = %s
                    AND docstatus = 1
                """, (self.from_date, self.to_date, self.company), as_dict=True)

                appraisal_data = appraisals[0] if appraisals else {}

                return {
                    "total_appraisals": cint(appraisal_data.get("total_appraisals", 0)),
                    "average_score": flt(appraisal_data.get("avg_score", 0))
                }
            else:
                return {"message": "Appraisal module not available"}

        except Exception as e:
            frappe.log_error(f"Error in HR performance analytics: {e}")
            return {"error": str(e)}

    def _get_workforce_planning(self) -> Dict[str, Any]:
        """Get workforce planning metrics"""
        try:
            # Current vs planned headcount (basic analysis)
            current_headcount = frappe.db.count("Employee",
                filters={"status": "Active", "company": self.company})

            # Department capacity analysis
            dept_analysis = frappe.db.sql("""
                SELECT
                    department,
                    COUNT(*) as current_count,
                    ROUND(AVG(CASE
                        WHEN DATEDIFF(CURDATE(), date_of_joining) < 1095 THEN 1 -- Less than 3 years
                        ELSE 0
                    END) * 100, 2) as junior_percentage
                FROM `tabEmployee`
                WHERE status = 'Active' AND company = %s
                AND department IS NOT NULL AND department != ''
                GROUP BY department
                ORDER BY current_count DESC
            """, (self.company,), as_dict=True)

            return {
                "current_headcount": current_headcount,
                "department_analysis": dept_analysis,
                "workforce_diversity": self._get_diversity_metrics()
            }

        except Exception as e:
            frappe.log_error(f"Error in HR workforce planning: {e}")
            return {"error": str(e)}

    def _get_diversity_metrics(self) -> Dict[str, Any]:
        """Get workforce diversity metrics"""
        try:
            # Gender distribution
            gender_dist = frappe.db.sql("""
                SELECT
                    gender,
                    COUNT(*) as count
                FROM `tabEmployee`
                WHERE status = 'Active' AND company = %s
                AND gender IS NOT NULL AND gender != ''
                GROUP BY gender
            """, (self.company,), as_dict=True)

            return {
                "gender_distribution": gender_dist
            }

        except Exception as e:
            frappe.log_error(f"Error in HR diversity metrics: {e}")
            return {"error": str(e)}
