"""Stock valuation rules for Mongolian companies.

IAS 2 (adopted in Mongolia) allows FIFO and weighted average cost; LIFO is not permitted.
Inventory is kept on the perpetual system so every stock movement posts to the ledger.
"""

import frappe
from frappe import _

NOT_ALLOWED_METHOD = "LIFO"


def has_mongolian_company():
	return bool(frappe.db.exists("Company", {"country": "Mongolia"}))


def validate_company(doc, method=None):
	if doc.country != "Mongolia":
		return

	if doc.is_new() and not doc.valuation_method:
		doc.valuation_method = "FIFO"
	if doc.valuation_method == NOT_ALLOWED_METHOD:
		throw_lifo_not_allowed()

	if doc.is_new():
		doc.enable_perpetual_inventory = 1
	elif doc.has_value_changed("enable_perpetual_inventory") and not doc.enable_perpetual_inventory:
		frappe.throw(
			_("Perpetual inventory is required for companies in Mongolia."),
			title=_("Not Allowed"),
		)


def validate_stock_settings(doc, method=None):
	if doc.valuation_method == NOT_ALLOWED_METHOD and has_mongolian_company():
		throw_lifo_not_allowed()


def validate_item(doc, method=None):
	if doc.valuation_method == NOT_ALLOWED_METHOD and has_mongolian_company():
		throw_lifo_not_allowed()


def throw_lifo_not_allowed():
	frappe.throw(
		_("LIFO valuation is not allowed under IAS 2. Use FIFO or Moving Average."),
		title=_("Not Allowed"),
	)
