# Copyright (c) 2026, Anjaa and contributors
# For license information, please see license.txt
"""НД-7: Ажил олгогчийн нийгмийн даатгалын шимтгэл төлөлтийн тайлан (сангаар нэгтгэсэн)."""

from frappe import _
from frappe.utils import flt

from ...social_insurance import get_employee_rows

TITLE = "НД-7 Нийгмийн даатгалын шимтгэл төлөлтийн тайлан"

FUNDS = [
	("pension", _("Тэтгэврийн даатгал")),
	("benefit", _("Тэтгэмжийн даатгал")),
	("accident", _("Үйлдвэрлэлийн осол, мэргэжлээс шалтгаалсан өвчний даатгал")),
	("unemployment", _("Ажилгүйдлийн даатгал")),
	("health", _("Эрүүл мэндийн даатгал")),
]


def execute(filters=None):
	return get_columns(), get_data(filters or {})


def get_columns():
	return [
		{"fieldname": "idx", "label": _("№"), "fieldtype": "Data", "width": 50},
		{"fieldname": "label", "label": _("Үзүүлэлт"), "fieldtype": "Data", "width": 380},
		{"fieldname": "employer", "label": _("Ажил олгогч"), "fieldtype": "Currency", "width": 150},
		{"fieldname": "employee", "label": _("Даатгуулагч"), "fieldtype": "Currency", "width": 150},
		{"fieldname": "total", "label": _("Нийт"), "fieldtype": "Currency", "width": 150},
	]


def get_data(filters):
	rows = get_employee_rows(filters)
	if not rows:
		return []

	def sum_of(field):
		return sum(flt(r.get(field)) for r in rows)

	data = [
		{"idx": "1", "label": _("Даатгуулагчийн тоо: {0}").format(len(rows))},
		{"idx": "2", "label": _("Хөдөлмөрийн хөлсний сан"), "total": sum_of("gross")},
		{"idx": "3", "label": _("Шимтгэл ногдуулах орлого"), "total": sum_of("base")},
	]
	for i, (fund, label) in enumerate(FUNDS, start=1):
		employer, employee = sum_of(f"er_{fund}"), sum_of(f"ee_{fund}")
		data.append(
			{
				"idx": f"4.{i}",
				"label": label,
				"employer": employer,
				"employee": employee,
				"total": employer + employee,
			}
		)

	employer, employee = sum_of("er_total"), sum_of("ee_total")
	data.append(
		{
			"idx": "4",
			"label": _("Нийт шимтгэл"),
			"employer": employer,
			"employee": employee,
			"total": employer + employee,
			"bold": 1,
		}
	)
	return data
