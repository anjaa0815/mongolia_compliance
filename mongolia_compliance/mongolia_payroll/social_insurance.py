"""Shared data for the НД-7 and НД-8 reports, plus the Excel download endpoint."""

import json

import frappe
from frappe import _
from frappe.utils import cint, flt, get_first_day, get_last_day, getdate

from .calculator import ACCIDENT, BENEFIT, HEALTH, PENSION, UNEMPLOYMENT
from .formula import SETTINGS, get_accident_rate, get_rules

MONTHS = [str(m) for m in range(1, 13)]


def get_period(filters) -> tuple:
	year, month = cint(filters.get("year")), cint(filters.get("month"))
	if not year or not month:
		frappe.throw(_("Please select year and month"))
	start = getdate(f"{year}-{month:02d}-01")
	return get_first_day(start), get_last_day(start)


def component_abbrs() -> dict:
	s = frappe.get_cached_doc(SETTINGS)
	return {
		"ndsh": s.ndsh_employee_abbr or "NDSH",
		"ndsh_er": s.ndsh_employer_abbr or "NDSH_ER",
		"pit": s.pit_abbr or "PIT",
	}


def get_employee_rows(filters) -> list[dict]:
	"""One row per employee for the month, with the НДШ split by fund."""
	from_date, to_date = get_period(filters)
	company = filters.get("company")
	abbrs = component_abbrs()

	slips = frappe.get_all(
		"Salary Slip",
		filters={"docstatus": 1, "company": company, "start_date": ["between", [from_date, to_date]]},
		fields=["name", "employee", "employee_name", "gross_pay"],
		order_by="employee_name asc",
	)
	if not slips:
		return []

	amounts = {}
	for d in frappe.get_all(
		"Salary Detail",
		filters={"parent": ["in", [s.name for s in slips]], "parenttype": "Salary Slip"},
		fields=["parent", "abbr", "amount"],
	):
		key = (d.parent, d.abbr)
		amounts[key] = amounts.get(key, 0) + flt(d.amount)

	rules = get_rules()
	employee_rate = rules.employee_total_rate
	employer_rates = rules.employer_rates_for(get_accident_rate(company))

	by_employee = {}
	for slip in slips:
		row = by_employee.setdefault(
			slip.employee, frappe._dict(employee=slip.employee, gross=0, ndsh=0, ndsh_er=0, pit=0)
		)
		row.gross += flt(slip.gross_pay)
		for key in ("ndsh", "ndsh_er", "pit"):
			row[key] += amounts.get((slip.name, abbrs[key]), 0)

	employees = {
		e.name: e
		for e in frappe.get_all(
			"Employee",
			filters={"name": ["in", list(by_employee)]},
			fields=[
				"name",
				"first_name",
				"last_name",
				"mn_register_no",
				"mn_insured_type",
				"mn_occupation_code",
				"designation",
			],
		)
	}

	rows = []
	for idx, row in enumerate(by_employee.values(), start=1):
		emp = employees.get(row.employee) or frappe._dict()
		# Шимтгэл ногдуулах орлогыг бодитоор суутгасан НДШ-ээс сэргээнэ (томьёонд хасалт хийсэн ч зөрөхгүй).
		base = flt(row.ndsh * 100 / employee_rate, 2) if employee_rate else 0
		ee = rules.contribution_breakdown(base, rules.employee_rates)
		er = rules.contribution_breakdown(base, employer_rates)
		rows.append(
			{
				"idx": idx,
				"employee": row.employee,
				"last_name": emp.last_name,
				"first_name": emp.first_name,
				"register_no": emp.mn_register_no,
				"insured_type": emp.mn_insured_type or "01",
				"occupation_code": emp.mn_occupation_code,
				"designation": emp.designation,
				"gross": row.gross,
				"base": base,
				"ee_pension": ee[PENSION],
				"ee_benefit": ee[BENEFIT],
				"ee_unemployment": ee[UNEMPLOYMENT],
				"ee_health": ee[HEALTH],
				"ee_total": row.ndsh,
				"er_pension": er[PENSION],
				"er_benefit": er[BENEFIT],
				"er_accident": er[ACCIDENT],
				"er_unemployment": er[UNEMPLOYMENT],
				"er_health": er[HEALTH],
				# Хуучин HRMS-д ажил олгогчийн НДШ статистик мөр тул хуудсанд хадгалагддаггүй: задаргаанаас бодно.
				"er_total": row.ndsh_er or sum(er.values()),
				"total": flt(row.ndsh) + flt(row.ndsh_er or sum(er.values())),
				"pit": row.pit,
			}
		)
	return rows


def total_row(rows: list[dict], columns: list[dict], label_field: str) -> dict:
	total = {label_field: _("Нийт"), "bold": 1}
	for col in columns:
		if col.get("fieldtype") in ("Currency", "Float") and col["fieldname"] not in total:
			total[col["fieldname"]] = sum(flt(r.get(col["fieldname"])) for r in rows)
	return total


def header_lines(filters) -> list[tuple[str, str]]:
	company = frappe.get_cached_doc("Company", filters.get("company"))
	from_date, _to_date = get_period(filters)
	return [
		(_("Ажил олгогч"), company.company_name),
		(_("Регистрийн дугаар"), company.tax_id or ""),
		(_("НД-ын дугаар"), company.get("mn_ndsh_employer_no") or ""),
		(_("Тайлант үе"), f"{from_date.year} оны {from_date.month}-р сар"),
	]


REPORTS = {
	"ND-7": f"{__package__}.report.nd_7.nd_7",
	"ND-8": f"{__package__}.report.nd_8.nd_8",
}


@frappe.whitelist()
def download_excel(report: str, filters: str | dict):
	if report not in REPORTS:
		frappe.throw(_("Unknown report {0}").format(report))
	frappe.has_permission("Salary Slip", "read", throw=True)

	from .excel import build_workbook

	filters = frappe._dict(json.loads(filters) if isinstance(filters, str) else filters)
	module = frappe.get_module(REPORTS[report])
	columns, data = module.execute(filters)

	content = build_workbook(module.TITLE, header_lines(filters), columns, data)
	frappe.response["filename"] = f"{report}_{filters.company}_{filters.year}-{cint(filters.month):02d}.xlsx"
	frappe.response["filecontent"] = content
	frappe.response["type"] = "binary"
