# Copyright (c) 2026, Anjaa and contributors
# License: GNU General Public License v3. See license.txt

"""Mongolian chart of accounts, VAT templates and withholding tax categories.

ERPNext only offers charts shipped inside its own code, so a Mongolian company is
first created on the chart picked in the form and, while it has no transactions,
that chart is replaced with the one in chart_of_accounts/mn_chart_of_accounts.json.
"""

import json
import os

import frappe
from frappe import _
from frappe.utils import getdate, nowdate

MODULE_PATH = os.path.dirname(__file__)

# Company defaults ERPNext looks up by English account name, set from the Mongolian chart
DEFAULT_ACCOUNTS_BY_NUMBER = {
	"write_off_account": "7214",
	"bank_charges_account": "8102",
	"exchange_gain_loss_account": "8103",
	"unrealized_exchange_gain_loss_account": "8103",
	"default_income_account": "5101",
}

# Withholding taxes a Mongolian company deducts from payments to suppliers.
# (category name, rate, account number in the Mongolian chart, account name)
WITHHOLDING_CATEGORIES = [
	("ХХОАТ 10% - Ажил, үйлчилгээ", 10, "3302", "ХХОАТ-ын өглөг"),
	("ХХОАТ 10% - Хөрөнгийн түрээс", 10, "3302", "ХХОАТ-ын өглөг"),
	("ХХОАТ 10% - Эрхийн шимтгэл (роялти)", 10, "3302", "ХХОАТ-ын өглөг"),
	("ААНОАТ 20% - Оршин суугч бус этгээд", 20, "3303", "ААНОАТ-ын өглөг"),
]


def setup_tax_withholding_categories(company):
	year_start = getdate(nowdate()).replace(month=1, day=1)

	for category_name, rate, account_number, account_name in WITHHOLDING_CATEGORIES:
		account = get_withholding_account(company, account_number, account_name)
		if not account:
			continue

		if frappe.db.exists("Tax Withholding Category", category_name):
			doc = frappe.get_doc("Tax Withholding Category", category_name)
			if any(row.company == company for row in doc.accounts):
				continue
			doc.append("accounts", {"company": company, "account": account})
			doc.save(ignore_permissions=True)
			continue

		frappe.get_doc(
			{
				"doctype": "Tax Withholding Category",
				"name": category_name,
				"category_name": category_name,
				"tax_deduction_basis": "Net Total",
				"rates": [
					{
						"tax_withholding_rate": rate,
						"from_date": year_start,
						"to_date": year_start.replace(year=2099, month=12, day=31),
					}
				],
				"accounts": [{"company": company, "account": account}],
			}
		).insert(ignore_permissions=True)


def get_withholding_account(company, account_number, account_name):
	account = frappe.db.get_value(
		"Account", {"company": company, "account_number": account_number, "is_group": 0}
	) or frappe.db.get_value("Account", {"company": company, "account_name": account_name, "is_group": 0})
	if account:
		return account

	from erpnext.setup.setup_wizard.operations.taxes_setup import get_or_create_account

	try:
		return get_or_create_account(company, {"account_name": account_name}).name
	except Exception:
		frappe.log_error(_("Could not create withholding tax account {0}").format(account_name))
		return None


def on_company_update(doc, method=None):
	if (
		doc.country == "Mongolia"
		and doc.get("mn_use_mongolian_chart")
		and not doc.get("mn_chart_installed")
		and not frappe.local.flags.ignore_chart_of_accounts
		and not has_transactions(doc.name)
	):
		install_mongolian_chart(doc.name)


@frappe.whitelist()
def install_mongolian_chart(company: str):
	"""Replace the company's chart of accounts and tax templates with the Mongolian ones."""
	frappe.has_permission("Company", "write", company, throw=True)
	if has_transactions(company):
		frappe.throw(
			_(
				"Transactions against the Company already exist! Chart of Accounts can only be imported for a Company with no transactions."
			)
		)

	from erpnext.accounts.doctype.account.chart_of_accounts.chart_of_accounts import create_charts
	from erpnext.accounts.doctype.chart_of_accounts_importer.chart_of_accounts_importer import (
		unset_existing_data,
	)

	unset_existing_data(company)
	frappe.db.delete("Item Tax Template", {"company": company})

	currency = frappe.get_cached_value("Company", company, "default_currency")
	create_charts(company, custom_chart=load_chart(currency))

	doc = frappe.get_doc("Company", company)
	doc.update_default_account = True
	doc.set_default_accounts()
	for fieldname, account_type in (
		("default_receivable_account", "Receivable"),
		("default_payable_account", "Payable"),
	):
		doc._set_default_account(fieldname, account_type)
	for fieldname, account_number in DEFAULT_ACCOUNTS_BY_NUMBER.items():
		account = frappe.db.get_value("Account", {"company": company, "account_number": account_number})
		if account:
			doc.db_set(fieldname, account)
	doc.reload()
	if doc.default_cash_account:
		doc.set_mode_of_payment_account()

	setup_tax_templates(company)
	setup_tax_withholding_categories(company)
	doc.db_set("mn_chart_installed", 1)


def has_transactions(company):
	return bool(frappe.db.get_all("GL Entry", {"company": company}, "name", limit=1))


def load_chart(currency):
	with open(os.path.join(MODULE_PATH, "chart_of_accounts", "mn_chart_of_accounts.json")) as f:
		tree = json.load(f)["tree"]

	metadata = {"account_number", "account_type", "root_type", "is_group", "tax_rate", "account_category"}

	def set_currency(node):
		for key, child in node.items():
			if key not in metadata and isinstance(child, dict):
				child["account_currency"] = currency
				set_currency(child)

	set_currency(tree)
	return tree


def setup_tax_templates(company):
	from erpnext.setup.setup_wizard.operations.taxes_setup import from_detailed_data

	with open(os.path.join(MODULE_PATH, "tax_templates.json")) as f:
		data = json.load(f)

	# templates keyed by chart name in the file; the company's own chart field
	# still holds the chart it was created with
	templates = data["chart_of_accounts"]["Mongolia - Chart of Accounts with Account Numbers"]
	from_detailed_data(
		company, {"tax_categories": data.get("tax_categories"), "chart_of_accounts": {"*": templates}}
	)
