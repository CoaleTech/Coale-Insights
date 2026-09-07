# Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""HR Data Collector - Headcount, attrition, payroll, attendance, recruitment"""

import frappe
from frappe.utils import flt, cint
from typing import Dict, Any, List

from pypika.terms import CustomFunction
from frappe.query_builder import Case, DocType
from frappe.query_builder.functions import (
    Avg,
    Coalesce,
    Count,
    CurDate,
    DateDiff,
    Round,
    Sum,
)

from insights.analytics.collectors.base import BaseCollector


# MariaDB/MySQL `TIME()` extractor — used to compare a datetime column to a
# wall-clock time string (late-arrival cutoff). PyPika has no built-in for
# this, so we wire it through `CustomFunction`.
_Time = CustomFunction("TIME", ["value"])


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

            Employee = DocType("Employee")

            # Department breakdown
            dept_breakdown = (
                frappe.qb.from_(Employee)
                .select(Employee.department, Count("*").as_("count"))
                .where(Employee.status == "Active")
                .where(Employee.company == self.company)
                .where(Employee.department.notnull())
                .where(Employee.department != "")
                .groupby(Employee.department)
                .orderby("count", order=frappe.qb.desc)
                .run(as_dict=True)
            )

            # Employment type breakdown
            emp_type_breakdown = (
                frappe.qb.from_(Employee)
                .select(Employee.employment_type, Count("*").as_("count"))
                .where(Employee.status == "Active")
                .where(Employee.company == self.company)
                .where(Employee.employment_type.notnull())
                .where(Employee.employment_type != "")
                .groupby(Employee.employment_type)
                .run(as_dict=True)
            )

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

            Employee = DocType("Employee")

            # Voluntary vs involuntary exits
            voluntary_exits = (
                frappe.qb.from_(Employee)
                .select(Count("*").as_("count"))
                .where(Employee.relieving_date.between(self.from_date, self.to_date))
                .where(Employee.company == self.company)
                # Original SQL uses `IS NOT NULL OR != ''`. `!= ''` already
                # excludes NULL in MySQL/MariaDB, so the same effective
                # predicate collapses to `!= ''`.
                .where(Employee.resignation_letter_date != "")
                .run(as_dict=True)
            )

            voluntary_count = voluntary_exits[0]["count"] if voluntary_exits else 0
            involuntary_count = exits - voluntary_count

            # Exit reasons breakdown
            exit_reasons = (
                frappe.qb.from_(Employee)
                .select(
                    Coalesce(Employee.reason_for_leaving, "Unknown").as_("reason"),
                    Count("*").as_("count"),
                )
                .where(Employee.relieving_date.between(self.from_date, self.to_date))
                .where(Employee.company == self.company)
                .groupby(Employee.reason_for_leaving)
                .orderby("count", order=frappe.qb.desc)
                .run(as_dict=True)
            )

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
            SalarySlip = DocType("Salary Slip")

            # Get payroll data from Salary Slip
            payroll_data = (
                frappe.qb.from_(SalarySlip)
                .select(
                    Coalesce(Sum(SalarySlip.gross_pay), 0).as_("total_gross_pay"),
                    Coalesce(Sum(SalarySlip.total_deduction), 0).as_("total_deductions"),
                    Coalesce(Sum(SalarySlip.net_pay), 0).as_("total_net_pay"),
                    Coalesce(Avg(SalarySlip.gross_pay), 0).as_("avg_gross_pay"),
                    Count(SalarySlip.employee).distinct().as_("employees_paid"),
                )
                .where(SalarySlip.start_date <= self.to_date)
                .where(SalarySlip.end_date >= self.from_date)
                .where(SalarySlip.company == self.company)
                .where(SalarySlip.docstatus == 1)
                .run(as_dict=True)
            )

            data = payroll_data[0] if payroll_data else {}

            Employee = DocType("Employee")

            # Department-wise payroll cost
            dept_payroll = (
                frappe.qb.from_(SalarySlip)
                .join(Employee)
                .on(SalarySlip.employee == Employee.name)
                .select(
                    Employee.department,
                    Coalesce(Sum(SalarySlip.gross_pay), 0).as_("total_cost"),
                    Coalesce(Avg(SalarySlip.gross_pay), 0).as_("avg_cost"),
                    Count(SalarySlip.employee).distinct().as_("employee_count"),
                )
                .where(SalarySlip.start_date <= self.to_date)
                .where(SalarySlip.end_date >= self.from_date)
                .where(SalarySlip.company == self.company)
                .where(SalarySlip.docstatus == 1)
                .where(Employee.department.notnull())
                .where(Employee.department != "")
                .groupby(Employee.department)
                .orderby("total_cost", order=frappe.qb.desc)
                .run(as_dict=True)
            )

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

            EmployeeCheckin = DocType("Employee Checkin")
            Employee = DocType("Employee")

            # Late arrivals from Employee Checkin
            late_arrivals = (
                frappe.qb.from_(EmployeeCheckin)
                .inner_join(Employee)
                .on(Employee.name == EmployeeCheckin.employee)
                .select(Count("*").as_("count"))
                .where(EmployeeCheckin.time >= self.from_date)
                .where(EmployeeCheckin.time <= self.to_date)
                .where(Employee.company == self.company)
                .where(EmployeeCheckin.log_type == "IN")
                .where(_Time(EmployeeCheckin.time) > "09:30:00")
                .run(as_dict=True)
            )

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
            LeaveApplication = DocType("Leave Application")

            # Leave applications summary
            total_leaves = (
                frappe.qb.from_(LeaveApplication)
                .select(
                    Count("*").as_("total_applications"),
                    Coalesce(Sum(LeaveApplication.total_leave_days), 0).as_("total_days"),
                    Coalesce(Avg(LeaveApplication.total_leave_days), 0).as_("avg_days_per_application"),
                )
                .where(LeaveApplication.from_date >= self.from_date)
                .where(LeaveApplication.to_date <= self.to_date)
                .where(LeaveApplication.company == self.company)
                .where(LeaveApplication.status == "Approved")
                .run(as_dict=True)
            )

            leave_data = total_leaves[0] if total_leaves else {}

            # Leave type breakdown
            leave_types = (
                frappe.qb.from_(LeaveApplication)
                .select(
                    LeaveApplication.leave_type,
                    Count("*").as_("applications"),
                    Coalesce(Sum(LeaveApplication.total_leave_days), 0).as_("total_days"),
                )
                .where(LeaveApplication.from_date >= self.from_date)
                .where(LeaveApplication.to_date <= self.to_date)
                .where(LeaveApplication.company == self.company)
                .where(LeaveApplication.status == "Approved")
                .groupby(LeaveApplication.leave_type)
                .orderby("total_days", order=frappe.qb.desc)
                .run(as_dict=True)
            )

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
                JobApplicant = DocType("Job Applicant")

                accepted_expr = Sum(
                    Case().when(JobApplicant.status == "Accepted", 1).else_(0)
                ).as_("accepted")
                rejected_expr = Sum(
                    Case().when(JobApplicant.status == "Rejected", 1).else_(0)
                ).as_("rejected")
                pending_expr = Sum(
                    Case().when(JobApplicant.status == "Open", 1).else_(0)
                ).as_("pending")

                applications = (
                    frappe.qb.from_(JobApplicant)
                    .select(
                        Count("*").as_("total_applications"),
                        accepted_expr,
                        rejected_expr,
                        pending_expr,
                    )
                    .where(JobApplicant.creation.between(self.from_date, self.to_date))
                    .run(as_dict=True)
                )

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
                Appraisal = DocType("Appraisal")

                appraisals = (
                    frappe.qb.from_(Appraisal)
                    .select(
                        Count("*").as_("total_appraisals"),
                        Coalesce(Avg(Appraisal.total_score), 0).as_("avg_score"),
                    )
                    .where(Appraisal.start_date >= self.from_date)
                    .where(Appraisal.end_date <= self.to_date)
                    .where(Appraisal.company == self.company)
                    .where(Appraisal.status == "Completed")
                    .run(as_dict=True)
                )

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

            Employee = DocType("Employee")

            # Department capacity analysis
            junior_flag = Case().when(
                DateDiff(CurDate(), Employee.date_of_joining) < 1095, 1
            ).else_(0)

            dept_analysis = (
                frappe.qb.from_(Employee)
                .select(
                    Employee.department,
                    Count("*").as_("current_count"),
                    Round(Avg(junior_flag) * 100, 2).as_("junior_percentage"),
                )
                .where(Employee.status == "Active")
                .where(Employee.company == self.company)
                .where(Employee.department.notnull())
                .where(Employee.department != "")
                .groupby(Employee.department)
                .orderby("current_count", order=frappe.qb.desc)
                .run(as_dict=True)
            )

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
            Employee = DocType("Employee")

            # Gender distribution
            gender_dist = (
                frappe.qb.from_(Employee)
                .select(Employee.gender, Count("*").as_("count"))
                .where(Employee.status == "Active")
                .where(Employee.company == self.company)
                .where(Employee.gender.notnull())
                .where(Employee.gender != "")
                .groupby(Employee.gender)
                .run(as_dict=True)
            )

            return {
                "gender_distribution": gender_dist
            }

        except Exception as e:
            frappe.log_error(f"Error in HR diversity metrics: {e}")
            return {"error": str(e)}
