# Copyright (c) 2026, Anjaa and contributors
# License: GNU General Public License v3. See license.txt

"""Jinja helpers for the AA primary document print formats.

num2words, which Frappe's money_in_words relies on, has no Mongolian, so amounts are
spelled out here.
"""

import frappe
from frappe.utils import cint, flt, getdate

# Mongolian numerals in the attributive form used before a following word ("таван зуун төгрөг")
UNITS = ["", "нэг", "хоёр", "гурван", "дөрвөн", "таван", "зургаан", "долоон", "найман", "есөн"]
TENS = ["", "арван", "хорин", "гучин", "дөчин", "тавин", "жаран", "далан", "наян", "ерэн"]
# (attributive, followed by further numerals) for each power of a thousand
SCALES = [("", ""), ("мянган", "мянга"), ("сая", "сая"), ("тэрбум", "тэрбум"), ("их наяд", "их наяд")]


def number_in_words(number: int) -> str:
	"""Spell out a non-negative integer in Mongolian, ready to be followed by a unit word."""
	number = int(number)
	if number == 0:
		return "тэг"

	groups = []
	while number:
		number, group = divmod(number, 1000)
		groups.append(group)
	if len(groups) > len(SCALES):
		raise ValueError("Number too large to spell out")

	words = []
	for scale, group in reversed(list(enumerate(groups))):
		if not group:
			continue
		hundreds, rest = divmod(group, 100)
		tens, units = divmod(rest, 10)
		if hundreds:
			words += [UNITS[hundreds], "зуун"]
		if tens:
			words.append(TENS[tens])
		if units:
			words.append(UNITS[units])
		if scale:
			is_last = not any(groups[:scale])
			words.append(SCALES[scale][0 if is_last else 1])

	return " ".join(words)


def mn_money_in_words(amount, currency: str | None = None) -> str:
	"""Amount in words as written on Mongolian primary documents, e.g. "Хоёр мянга таван зуун төгрөг 50 мөнгө"."""
	currency = currency or frappe.db.get_default("currency")
	if currency and currency != "MNT":
		return frappe.utils.money_in_words(amount, currency)

	amount = flt(amount, 2)
	sign = "Хасах " if amount < 0 else ""
	amount = abs(amount)
	tugrik = int(amount)
	mongo = cint(round((amount - tugrik) * 100))

	words = f"{number_in_words(tugrik)} төгрөг"
	if mongo:
		words += f" {mongo:02d} мөнгө"

	words = sign + words
	return words[0].upper() + words[1:]


def mn_date(date) -> str:
	"""Date written the Mongolian way: "2026 оны 10 сарын 07"."""
	if not date:
		return ""
	date = getdate(date)
	return f"{date.year} оны {date.month:02d} сарын {date.day:02d}"


def get_party_details(doctype: str, name: str) -> dict:
	"""Registration number and phone of a customer or supplier for the form header."""
	if not name:
		return frappe._dict()
	return frappe._dict(frappe.db.get_value(doctype, name, ["tax_id", "mobile_no"], as_dict=True) or {})


def get_full_name(user: str) -> str:
	return frappe.db.get_value("User", user, "full_name") or user or ""
