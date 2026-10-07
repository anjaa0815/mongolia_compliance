"""Mongolian currency, number and date formats.

Frappe already ships MNT with the ₮ symbol and yyyy-mm-dd for Mongolia (frappe/geo/country_info.json),
but only applies them when the setup wizard runs with country Mongolia. This module (re)applies them on
an existing site and adds the "whole tugrik" option:

- MNT number format becomes "#,###" and System Settings "use number format from currency" is switched on,
  so MNT amounts have 0 decimals while USD, CNY etc. keep 2 (frappe.model.meta.get_precision_from_currency_format).
- MNT smallest currency fraction becomes 1, so Rounded Total rounds to a whole tugrik.
- A global System Settings currency precision overrides per-currency formats, so it is cleared.
"""

import frappe
from frappe import _

MNT = "MNT"
WHOLE_FORMATS = {"#,###.##": "#,###", "#.###,##": "#.###"}


def apply_formats(settings=None):
	settings = settings or frappe.get_single("Mongolia Banking Settings")
	number_format = settings.number_format or "#,###.##"
	messages = []

	ensure_mnt(settings, number_format)

	system = frappe.get_single("System Settings")
	system.number_format = number_format
	if settings.apply_date_format:
		system.date_format = "yyyy-mm-dd"
	if settings.whole_number_amounts:
		system.use_number_format_from_currency = 1
		if system.currency_precision not in (None, ""):
			messages.append(
				_(
					"Системийн 'Currency Precision' ({0})-ийг хоосолсон: валют бүр өөрийн форматаар нарийвчлалаа авна"
				).format(system.currency_precision)
			)
			system.currency_precision = ""
	system.flags.ignore_permissions = True
	system.save()

	if settings.set_default_currency:
		defaults = frappe.get_single("Global Defaults")
		if defaults.default_currency != MNT:
			defaults.default_currency = MNT
			defaults.flags.ignore_permissions = True
			defaults.save()

	frappe.clear_cache()
	if messages:
		frappe.msgprint("<br>".join(messages), alert=True)


def ensure_mnt(settings, number_format: str):
	if frappe.db.exists("Currency", MNT):
		currency = frappe.get_doc("Currency", MNT)
	else:
		currency = frappe.get_doc(
			{
				"doctype": "Currency",
				"currency_name": MNT,
				"fraction": "Мөнгө",
				"fraction_units": 100,
			}
		)
	whole = bool(settings.whole_number_amounts)
	currency.update(
		{
			"enabled": 1,
			"symbol": "₮",
			"symbol_on_right": 1 if settings.symbol_on_right else 0,
			"number_format": WHOLE_FORMATS.get(number_format, "#,###") if whole else number_format,
			"smallest_currency_fraction_value": 1 if whole else 0,
		}
	)
	currency.flags.ignore_permissions = True
	currency.save()
