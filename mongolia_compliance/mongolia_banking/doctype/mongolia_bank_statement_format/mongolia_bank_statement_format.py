# Copyright (c) 2026, Anjaa and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document

from mongolia_compliance.mongolia_banking.statement.profiles import PROFILE_FIELDS, build_profile


def split_lines(value: str | None) -> list[str]:
	return [line.strip() for line in (value or "").splitlines() if line.strip()]


class MongoliaBankStatementFormat(Document):
	def validate(self):
		if not (self.deposit_columns and self.withdrawal_columns) and not self.amount_columns:
			frappe.throw(_("Орлого ба Зарлага баганууд, эсвэл Дүн баганыг заавал бөглөнө"))

	def as_profile(self) -> dict:
		overrides = {field: split_lines(self.get(field)) for field in PROFILE_FIELDS}
		overrides["decimal_separator"] = self.decimal_separator or "."
		return build_profile(overrides)
