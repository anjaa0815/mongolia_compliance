# Copyright (c) 2026, Anjaa and contributors
# For license information, please see license.txt

import frappe
from erpnext import get_region
from frappe import _
from frappe.model.document import Document


class EBarimtSettings(Document):
	def validate(self):
		if self.company and get_region(self.company) != "Mongolia":
			frappe.throw(_("Company {0} is not in Mongolia.").format(frappe.bold(self.company)))

		self.posapi_url = (self.posapi_url or "").strip().rstrip("/")
		self.info_api_url = (self.info_api_url or "").strip().rstrip("/")

		for fieldname in ("vat_account", "city_tax_account"):
			account = self.get(fieldname)
			if account and frappe.db.get_value("Account", account, "company") != self.company:
				frappe.throw(
					_("Account {0} does not belong to Company {1}").format(
						frappe.bold(account), frappe.bold(self.company)
					)
				)

	@frappe.whitelist()
	def test_connection(self):
		from mongolia_compliance.e_barimt.ebarimt import PosAPIClient

		return PosAPIClient(self).get_info()


def get_ebarimt_settings(company: str):
	"""Return the enabled E-Barimt Settings for a company, or None."""
	if not frappe.db.exists("E-Barimt Settings", {"company": company, "enabled": 1}):
		return None

	return frappe.get_cached_doc("E-Barimt Settings", company)
