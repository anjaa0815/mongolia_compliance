"""Import costs on Landed Cost Voucher for Mongolian companies.

Customs duty, customs fees, freight, insurance and handling are capitalised into item cost
(IAS 2.11). VAT paid at customs is recoverable, so it belongs on the VAT receivable account
and must never be distributed into item cost.
"""

import re

import frappe
from frappe import _

# charge type -> (account number, account name) in the Mongolian chart, all under group "6"
IMPORT_CHARGES = {
	"Customs Duty": ("6105", "Гаалийн албан татвар"),
	"Customs Fee": ("6106", "Гаалийн хураамж"),
	"International Freight": ("6107", "Олон улсын тээврийн зардал"),
	"Local Freight": ("6108", "Дотоод тээврийн зардал"),
	"Insurance": ("6109", "Импортын даатгал"),
	"Handling": ("6110", "Ачиж буулгах зардал"),
}

VAT_PATTERN = re.compile(r"\b(нөат|vat)", re.IGNORECASE)


def before_validate(doc, method=None):
	if not is_mongolian(doc.company):
		return

	for row in doc.taxes:
		charge = row.get("mn_import_charge")
		if not charge or charge not in IMPORT_CHARGES:
			continue
		if not row.expense_account:
			row.expense_account = find_import_charge_account(doc.company, charge)
		if not row.description:
			row.description = _(charge)


def validate(doc, method=None):
	if not is_mongolian(doc.company):
		return

	for row in doc.taxes:
		if is_vat_charge(row):
			frappe.throw(
				_(
					"Row {0}: VAT paid at customs is recoverable and cannot be added to item cost. Book it to the VAT receivable account {1} with a Purchase Invoice or Journal Entry instead."
				).format(row.idx, frappe.bold(get_account_by_number(doc.company, "1211") or "1211")),
				title=_("Customs VAT"),
			)


@frappe.whitelist()
def get_import_charge_account(company: str, charge: str):
	frappe.has_permission("Company", "read", company, throw=True)
	return find_import_charge_account(company, charge)


def find_import_charge_account(company, charge):
	if charge not in IMPORT_CHARGES:
		return None
	return get_account_by_number(company, IMPORT_CHARGES[charge][0]) or get_account_by_number(company, "6102")


def get_account_by_number(company, account_number):
	return frappe.db.get_value(
		"Account", {"company": company, "account_number": account_number, "is_group": 0}
	)


def is_vat_charge(row):
	if (
		row.expense_account
		and frappe.get_cached_value("Account", row.expense_account, "account_type") == "Tax"
	):
		return True
	return bool(VAT_PATTERN.search(row.description or ""))


def is_mongolian(company):
	return frappe.get_cached_value("Company", company, "country") == "Mongolia"


def create_import_charge_accounts(company):
	"""Add the import cost accounts to a company that already has the Mongolian chart."""
	parent = frappe.db.get_value("Account", {"company": company, "account_number": "6", "is_group": 1})
	if not parent:
		return

	for account_number, account_name in IMPORT_CHARGES.values():
		if get_account_by_number(company, account_number):
			continue
		frappe.get_doc(
			{
				"doctype": "Account",
				"company": company,
				"parent_account": parent,
				"account_name": account_name,
				"account_number": account_number,
				"account_type": "Expenses Included In Valuation",
				"account_category": "Other Direct Costs",
			}
		).insert(ignore_permissions=True)
