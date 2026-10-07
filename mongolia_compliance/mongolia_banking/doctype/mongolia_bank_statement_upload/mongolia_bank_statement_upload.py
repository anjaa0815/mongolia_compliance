# Copyright (c) 2026, Anjaa and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document

from mongolia_compliance.mongolia_banking.statement.importer import (
	BACKGROUND_THRESHOLD,
	import_statement,
	read_statement,
)


class MongoliaBankStatementUpload(Document):
	def validate(self):
		if not frappe.db.get_value("Bank Account", self.bank_account, "is_company_account"):
			frappe.throw(_("Байгууллагын өөрийн банкны дансыг сонгоно уу"))
		if not frappe.db.get_value("Bank Account", self.bank_account, "account"):
			frappe.throw(_("{0} банкны дансанд НББ-ийн данс холбоогүй байна").format(self.bank_account))
		if not self.statement_format:
			self.statement_format = default_format(self.bank_account)

	@frappe.whitelist()
	def preview(self) -> list[dict]:
		self.check_permission("read")
		lines = read_statement(self)
		return [
			{
				"row": line.row_no,
				"date": line.date,
				"description": line.description,
				"deposit": line.deposit,
				"withdrawal": line.withdrawal,
				"party_account": line.party_account,
				"reference": line.reference,
			}
			for line in lines[:20]
		] + ([{"more": len(lines) - 20}] if len(lines) > 20 else [])

	@frappe.whitelist()
	def start_import(self):
		self.check_permission("write")
		frappe.has_permission("Bank Transaction", "create", throw=True)
		if self.status == "Queued":
			frappe.throw(_("Импорт аль хэдийн явагдаж байна"))

		lines = len(read_statement(self))
		if lines > BACKGROUND_THRESHOLD:
			self.db_set("status", "Queued")
			frappe.enqueue(
				import_statement,
				queue="long",
				upload_name=self.name,
				enqueue_after_commit=True,
				job_id=f"mn_statement::{self.name}",
				deduplicate=True,
			)
			return _("{0} мөрийг цаана импортолж байна").format(lines)
		import_statement(self.name)
		return None


def default_format(bank_account: str) -> str | None:
	bank = frappe.db.get_value("Bank Account", bank_account, "bank")
	return frappe.db.get_value("Mongolia Bank Statement Format", {"bank": bank, "enabled": 1}) or (
		frappe.db.get_value("Mongolia Bank Statement Format", {"bank": ("is", "not set"), "enabled": 1})
	)


@frappe.whitelist()
def get_default_format(bank_account: str) -> str | None:
	frappe.has_permission("Bank Account", "read", doc=bank_account, throw=True)
	return default_format(bank_account)
