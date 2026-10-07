"""Functions available inside Salary Component formulas.

HRMS evaluates component formulas with a fixed set of globals
(`hrms.payroll.utils.COMPONENT_EVAL_GLOBALS`). `register()` adds the `mn_*` helpers
below to that dict, so the same formula works in the Salary Structure Assignment
(CTC preview) and in the Salary Slip. It is idempotent and runs on every request
and background job through the `before_request` / `before_job` hooks.

Example formulas (see install.py for the full structure):
    НДШ (ажилтан):      mn_ndsh_employee(gross_pay)
    ХХОАТ:              mn_pit(gross_pay, NDSH)
    НДШ (ажил олгогч):  mn_ndsh_employer(gross_pay, company)
"""

import frappe
from frappe.utils import add_months, flt, get_first_day, get_last_day, getdate

from .calculator import ACCIDENT, PayrollRules, Slab, average_daily_wage, norm_working_days

SETTINGS = "Mongolia Payroll Settings"
RISK_CLASS = "Mongolia NDSH Risk Class"


def get_rules() -> PayrollRules:
	rules = PayrollRules()
	if not frappe.db.exists("DocType", SETTINGS):
		return rules

	s = frappe.get_cached_doc(SETTINGS)
	if flt(s.minimum_wage):
		rules.minimum_wage = flt(s.minimum_wage)
	if flt(s.ceiling_multiplier):
		rules.ceiling_multiplier = flt(s.ceiling_multiplier)

	rules.employee_rates = {
		"pension": flt(s.employee_pension_rate),
		"benefit": flt(s.employee_benefit_rate),
		"accident": 0.0,
		"unemployment": flt(s.employee_unemployment_rate),
		"health": flt(s.employee_health_rate),
	}
	rules.employer_rates = {
		"pension": flt(s.employer_pension_rate),
		"benefit": flt(s.employer_benefit_rate),
		"accident": rules.employer_rates[ACCIDENT],
		"unemployment": flt(s.employer_unemployment_rate),
		"health": flt(s.employer_health_rate),
	}
	if s.pit_slabs:
		rules.pit_slabs = [Slab(flt(r.from_amount), flt(r.to_amount), flt(r.rate)) for r in s.pit_slabs]
	if s.pit_credit_slabs:
		rules.pit_credit_slabs = [
			Slab(flt(r.from_amount), flt(r.to_amount), flt(r.credit_amount)) for r in s.pit_credit_slabs
		]
	rules.daily_hours = flt(s.daily_hours) or rules.daily_hours
	rules.overtime_multiplier = flt(s.overtime_multiplier) or rules.overtime_multiplier
	rules.holiday_multiplier = flt(s.holiday_multiplier) or rules.holiday_multiplier
	return rules


def get_accident_rate(company: str | None) -> float | None:
	"""ҮОМШӨ-ийн ажил олгогчийн хувь: компанийн эрсдэлийн зэрэг, эсвэл тохиргооны үндсэн зэрэг."""
	risk_class = company and frappe.get_cached_value("Company", company, "mn_ndsh_risk_class")
	if not risk_class and frappe.db.exists("DocType", SETTINGS):
		risk_class = frappe.db.get_single_value(SETTINGS, "default_risk_class")
	if risk_class:
		return flt(frappe.get_cached_value(RISK_CLASS, risk_class, "accident_rate"))
	return None


def _norm_days(start_date, employee=None, company=None) -> int:
	start_date = getdate(start_date)
	holiday_list = None
	if employee:
		holiday_list = frappe.get_cached_value("Employee", employee, "holiday_list")
	if not holiday_list and company:
		holiday_list = frappe.get_cached_value("Company", company, "default_holiday_list")

	if holiday_list:
		dates = frappe.get_all(
			"Holiday",
			filters={
				"parent": holiday_list,
				"holiday_date": ["between", [get_first_day(start_date), get_last_day(start_date)]],
			},
			pluck="holiday_date",
		)
		return norm_working_days(start_date, [getdate(d) for d in dates])
	return norm_working_days(start_date)


# --- formula helpers ---------------------------------------------------------


def mn_ndsh_base(wage):
	"""Шимтгэл ногдуулах орлого (дээд хязгаартай)."""
	return get_rules().ndsh_base(wage)


def mn_ndsh_employee(wage):
	"""Ажилтнаас суутгах НДШ (11.5%, дээд хязгаартай)."""
	return get_rules().ndsh_employee(wage)


def mn_ndsh_employer(wage, company=None):
	"""Ажил олгогчийн НДШ (12.5%-14.5%, компанийн эрсдэлийн зэргээс хамаарна)."""
	return get_rules().ndsh_employer(wage, get_accident_rate(company))


def mn_pit(wage, ndsh_employee=0):
	"""ХХОАТ: шатласан хувь, сар бүрийн хөнгөлөлтийг хассан."""
	return get_rules().pit(wage, ndsh_employee)


def mn_pit_credit(wage):
	return get_rules().pit_credit(wage)


def mn_norm_days(start_date, employee=None, company=None):
	return _norm_days(start_date, employee, company)


def mn_overtime_pay(monthly_salary, start_date, hours, employee=None, company=None):
	"""Илүү цагийн хөлс = цагийн цалин x цаг x 1.5."""
	if not flt(hours):
		return 0
	return get_rules().overtime_pay(monthly_salary, _norm_days(start_date, employee, company), hours)


def mn_holiday_pay(monthly_salary, start_date, hours, employee=None, company=None):
	"""Нийтээр амрах баярын өдөр ажилласан цагийн хөлс = цагийн цалин x цаг x 2.0."""
	if not flt(hours):
		return 0
	return get_rules().holiday_pay(monthly_salary, _norm_days(start_date, employee, company), hours)


def mn_vacation_pay(employee, days, start_date, monthly_salary=0, months=12):
	"""Ээлжийн амралтын олговор = өмнөх 12 сарын дундаж өдрийн цалин x амралтын өдөр.

	Дундажийг батлагдсан цалингийн хуудсуудын gross_pay / payment_days-аас тооцно.
	Түүх байхгүй (шинэ ажилтан) бол тухайн сарын цалинг ажлын өдрийн нормд хуваана.
	"""
	if not flt(days):
		return 0
	start_date = getdate(start_date)
	totals = frappe.db.sql(
		"""
		select sum(gross_pay), sum(payment_days)
		from `tabSalary Slip`
		where employee = %s and docstatus = 1
			and start_date >= %s and end_date < %s
		""",
		(employee, add_months(start_date, -int(months)), start_date),
	)
	total_wage, total_days = (totals[0] if totals else (0, 0)) or (0, 0)
	daily = average_daily_wage(flt(total_wage), flt(total_days))
	if not daily:
		daily = average_daily_wage(flt(monthly_salary), _norm_days(start_date, employee))
	return get_rules().vacation_pay(daily, days)


FORMULA_FUNCTIONS = {
	fn.__name__: fn
	for fn in (
		mn_ndsh_base,
		mn_ndsh_employee,
		mn_ndsh_employer,
		mn_pit,
		mn_pit_credit,
		mn_norm_days,
		mn_overtime_pay,
		mn_holiday_pay,
		mn_vacation_pay,
	)
}


def register(*args, **kwargs):
	try:
		from hrms.payroll.utils import COMPONENT_EVAL_GLOBALS
	except ImportError:
		return
	COMPONENT_EVAL_GLOBALS.update(FORMULA_FUNCTIONS)


def register_on_doc(doc, method=None):
	"""Also covers console / test runs where before_request does not fire."""
	register()
	if isinstance(getattr(doc, "whitelisted_globals", None), dict):
		doc.whitelisted_globals.update(FORMULA_FUNCTIONS)
