# Copyright (c) 2026, Anjaa and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt


class MongoliaPayrollSettings(Document):
	def validate(self):
		self.ndsh_ceiling = flt(self.minimum_wage) * flt(self.ceiling_multiplier)
		self.validate_slabs("pit_slabs")
		self.validate_slabs("pit_credit_slabs")

	def validate_slabs(self, table):
		for row in self.get(table):
			if flt(row.to_amount) and flt(row.to_amount) <= flt(row.from_amount):
				frappe.throw(
					_("Row {0}: upper amount must be greater than the lower amount").format(row.idx),
					title=self.meta.get_label(table),
				)

	def on_update(self):
		frappe.clear_document_cache(self.doctype, self.name)


@frappe.whitelist()
def create_salary_structure(company: str):
	"""Тухайн компанид Монгол стандарт цалингийн бүтцийн ноорог үүсгэнэ."""
	frappe.only_for(("HR Manager", "System Manager"))
	from ...install import make_salary_structure

	return make_salary_structure(company)
