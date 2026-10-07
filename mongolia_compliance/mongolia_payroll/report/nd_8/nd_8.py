# Copyright (c) 2026, Anjaa and contributors
# For license information, please see license.txt
"""НД-8: Даатгуулагчийн цалин хөлс, нийгмийн даатгалын шимтгэлийн жагсаалт (ажилтан тус бүрээр)."""

from frappe import _

from ...social_insurance import get_employee_rows, total_row

TITLE = "НД-8 Даатгуулагчийн цалин хөлс, шимтгэлийн жагсаалт"


def execute(filters=None):
	columns = get_columns()
	rows = get_employee_rows(filters or {})
	if rows:
		rows.append(total_row(rows, columns, "last_name"))
	return columns, rows


def get_columns():
	def col(fieldname, label, fieldtype="Currency", width=130, **kw):
		return {"fieldname": fieldname, "label": label, "fieldtype": fieldtype, "width": width, **kw}

	return [
		col("idx", _("№"), "Int", 50),
		col("last_name", _("Овог"), "Data", 130),
		col("first_name", _("Нэр"), "Data", 130),
		col("register_no", _("Регистрийн дугаар"), "Data", 120),
		col("insured_type", _("Даатгуулагчийн төрөл"), "Data", 90),
		col("occupation_code", _("Ажил мэргэжлийн код"), "Data", 100),
		col("employee", _("Employee"), "Link", 120, options="Employee"),
		col("gross", _("Хөдөлмөрийн хөлс")),
		col("base", _("Шимтгэл ногдуулах орлого")),
		col("er_pension", _("Ажил олгогч: Тэтгэвэр")),
		col("er_benefit", _("Ажил олгогч: Тэтгэмж")),
		col("er_accident", _("Ажил олгогч: ҮОМШӨ")),
		col("er_unemployment", _("Ажил олгогч: Ажилгүйдэл")),
		col("er_health", _("Ажил олгогч: ЭМД")),
		col("er_total", _("Ажил олгогчийн шимтгэл")),
		col("ee_pension", _("Даатгуулагч: Тэтгэвэр")),
		col("ee_benefit", _("Даатгуулагч: Тэтгэмж")),
		col("ee_unemployment", _("Даатгуулагч: Ажилгүйдэл")),
		col("ee_health", _("Даатгуулагч: ЭМД")),
		col("ee_total", _("Даатгуулагчийн шимтгэл")),
		col("total", _("Нийт шимтгэл")),
	]
