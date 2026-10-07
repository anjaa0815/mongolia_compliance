import frappe

from mongolia_compliance.mongolia_banking.statement.profiles import GENERIC, STATEMENT_FORMATS

BANKS = [
	"Хаан банк",
	"Голомт банк",
	"Худалдаа хөгжлийн банк",
	"Хас банк",
	"Төрийн банк",
	"Капитрон банк",
	"Богд банк",
	"Ариг банк",
	"Транс банк",
	"Үндэсний хөрөнгө оруулалтын банк",
	"Чингис хаан банк",
	"М банк",
]

SETTINGS_DEFAULTS = {
	"set_default_currency": 1,
	"symbol_on_right": 1,
	"whole_number_amounts": 0,
	"number_format": "#,###.##",
	"apply_date_format": 1,
	"match_threshold": 70,
	"date_window_days": 5,
}


def after_install():
	"""Runs once when mongolia_compliance is installed: records plus the MNT / ₮ / yyyy-mm-dd formats."""
	create_records()
	settings = frappe.get_single("Mongolia Banking Settings")
	settings.update(SETTINGS_DEFAULTS)
	settings.flags.ignore_permissions = True
	settings.save()  # applies MNT / ₮ / yyyy-mm-dd through on_update


def after_migrate():
	create_records()


def create_records():
	if not frappe.db.exists("Mode of Payment", "QPay"):
		frappe.get_doc({"doctype": "Mode of Payment", "mode_of_payment": "QPay", "type": "Bank"}).insert(
			ignore_permissions=True
		)

	for bank in BANKS:
		if not frappe.db.exists("Bank", bank):
			frappe.get_doc({"doctype": "Bank", "bank_name": bank}).insert(ignore_permissions=True)

	for profile in STATEMENT_FORMATS:
		if frappe.db.exists("Mongolia Bank Statement Format", profile["format_name"]):
			continue  # never overwrite a format the user has edited
		doc = frappe.new_doc("Mongolia Bank Statement Format")
		doc.format_name = profile["format_name"]
		doc.bank = profile.get("bank")
		doc.enabled = 1
		doc.decimal_separator = "."
		for field in (
			"date_columns",
			"description_columns",
			"deposit_columns",
			"withdrawal_columns",
			"amount_columns",
			"direction_columns",
			"account_columns",
			"party_name_columns",
			"reference_columns",
			"balance_columns",
		):
			# bank-specific names first; the generic aliases stay as a fallback at parse time
			doc.set(field, "\n".join(profile.get(field) or GENERIC[field]))
		doc.date_formats = "\n".join(GENERIC["date_formats"])
		doc.deposit_markers = "\n".join(GENERIC["deposit_markers"])
		doc.insert(ignore_permissions=True)
