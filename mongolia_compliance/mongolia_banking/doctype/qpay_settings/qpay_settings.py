# Copyright (c) 2026, Anjaa and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class QPaySettings(Document):
	def validate(self):
		if self.payment_account:
			account = frappe.get_cached_value(
				"Account", self.payment_account, ["company", "account_currency", "is_group"], as_dict=True
			)
			if account.company != self.company:
				frappe.throw(
					_("{0} данс {1} компанийнх биш байна").format(self.payment_account, self.company)
				)
			if account.is_group:
				frappe.throw(_("Бүлэг данс сонгох боломжгүй"))
			if account.account_currency and account.account_currency != "MNT":
				frappe.throw(_("QPay-ийн данс төгрөгийн (MNT) данс байх ёстой"))
		if self.callback_base_url and not self.callback_base_url.startswith("https://"):
			frappe.msgprint(
				_("QPay callback-ийг https хаягаар тохируулахыг зөвлөж байна"), indicator="orange", alert=True
			)

	def on_update(self):
		from mongolia_compliance.mongolia_banking.gateways.qpay import PRODUCTION_URL, SANDBOX_URL

		# credentials may have changed: drop the cached token
		for base in (PRODUCTION_URL, SANDBOX_URL):
			frappe.cache.delete_value(f"mongolia_banking:qpay_token:{base}:{self.client_id}")


@frappe.whitelist()
def test_connection(company: str):
	frappe.only_for(("System Manager", "Accounts Manager"))
	from mongolia_compliance.mongolia_banking.payments import get_qpay_client

	client = get_qpay_client(company)
	client.get_token(force=True)
	return _("QPay-д амжилттай холбогдлоо")
