# Copyright (c) 2026, Anjaa and contributors
# License: GNU General Public License v3. See license.txt

"""E-Barimt (Mongolian electronic receipt, PosAPI 3.0) integration.

A receipt is registered with the PosAPI service when a Sales Invoice or POS Invoice
is submitted. The returned receipt id (ДДТД), QR data and lottery number are stored
on the invoice. Cancelling the invoice voids the receipt; a return voids it or,
for a partial return, replaces it with a receipt for what the customer kept.
"""

from collections import defaultdict

import frappe
import requests
from frappe import _
from frappe.utils import cint, flt, get_datetime, now_datetime

from mongolia_compliance.e_barimt.doctype.e_barimt_settings.e_barimt_settings import get_ebarimt_settings

INVOICE_DOCTYPES = ("Sales Invoice", "POS Invoice")
RETURN_LINK_FIELD = {"Sales Invoice": "sales_invoice_item", "POS Invoice": "pos_invoice_item"}

STATUS_SENT = "Sent"
STATUS_FAILED = "Failed"
STATUS_CANCELLED = "Cancelled"
STATUS_RETURN = "Return Processed"


class EBarimtError(Exception):
	pass


class PosAPIClient:
	def __init__(self, settings):
		self.settings = settings
		self.base_url = settings.posapi_url.rstrip("/")
		self.timeout = cint(settings.timeout) or 20

	def _request(self, method, path, payload=None):
		try:
			response = requests.request(
				method,
				f"{self.base_url}{path}",
				json=payload,
				timeout=self.timeout,
			)
		except requests.RequestException as e:
			raise EBarimtError(_("Could not connect to PosAPI at {0}: {1}").format(self.base_url, e)) from e

		try:
			data = response.json() if response.content else {}
		except ValueError:
			data = {"message": response.text}

		if response.status_code >= 400:
			raise EBarimtError(
				_("PosAPI returned HTTP {0}: {1}").format(response.status_code, data.get("message") or data)
			)

		return data

	def get_info(self):
		return self._request("GET", "/rest/info")

	def send_data(self):
		return self._request("GET", "/rest/sendData")

	def create_receipt(self, payload):
		data = self._request("POST", "/rest/receipt", payload)
		if data.get("status") != "SUCCESS" or not data.get("id"):
			raise EBarimtError(data.get("message") or _("PosAPI did not return a receipt id"))
		return data

	def delete_receipt(self, receipt_id, receipt_date):
		data = self._request(
			"DELETE",
			"/rest/receipt",
			{"id": receipt_id, "date": get_datetime(receipt_date).strftime("%Y-%m-%d %H:%M:%S")},
		)
		if isinstance(data, dict) and data.get("status") == "ERROR":
			raise EBarimtError(
				data.get("message") or _("PosAPI could not void receipt {0}").format(receipt_id)
			)
		return data


# ---------------------------------------------------------------------------
# Document events
# ---------------------------------------------------------------------------


def on_submit(doc, method=None):
	settings = _get_settings(doc)
	if not settings:
		return

	if doc.is_return:
		if doc.return_against:
			_run(doc, settings, lambda: resync_receipt(doc.doctype, doc.return_against, settings, doc))
		return

	_run(doc, settings, lambda: issue_receipt(doc, settings))


def on_cancel(doc, method=None):
	settings = _get_settings(doc)
	if not settings:
		return

	if doc.is_return:
		if doc.return_against:
			# the return is already cancelled in the database, so the original's
			# receipt is rebuilt without it
			_run(doc, settings, lambda: resync_receipt(doc.doctype, doc.return_against, settings, doc))
		return

	if doc.get("ebarimt_id") and doc.get("ebarimt_status") == STATUS_SENT:
		# cancelling must not silently leave a live receipt behind
		PosAPIClient(settings).delete_receipt(doc.ebarimt_id, doc.ebarimt_date)
		doc.db_set("ebarimt_status", STATUS_CANCELLED)


def _get_settings(doc):
	if doc.doctype not in INVOICE_DOCTYPES or doc.get("is_opening") == "Yes":
		return None

	# POS Invoices are registered on their own; the consolidated Sales Invoice must not repeat them
	if doc.doctype == "Sales Invoice" and doc.get("is_consolidated"):
		return None

	if frappe.get_cached_value("Company", doc.company, "country") != "Mongolia":
		return None

	return get_ebarimt_settings(doc.company)


def _run(doc, settings, action):
	try:
		action()
	except EBarimtError as e:
		if settings.block_submit_on_error or doc.docstatus == 2:
			frappe.throw(str(e), title=_("E-Barimt Error"))

		doc.db_set({"ebarimt_status": STATUS_FAILED, "ebarimt_error": str(e)})
		frappe.msgprint(
			_("E-Barimt receipt could not be registered and will be retried: {0}").format(e),
			indicator="orange",
			alert=True,
		)


# ---------------------------------------------------------------------------
# Issue / replace / void
# ---------------------------------------------------------------------------


def issue_receipt(doc, settings, inactive_id=None, qty_factor=None):
	payload = build_payload(doc, settings, inactive_id=inactive_id, qty_factor=qty_factor)
	result = PosAPIClient(settings).create_receipt(payload)
	values = {
		"ebarimt_status": STATUS_SENT,
		"ebarimt_id": result.get("id"),
		"ebarimt_qr_data": result.get("qrData"),
		"ebarimt_lottery": result.get("lottery"),
		"ebarimt_date": get_datetime(result.get("date")) if result.get("date") else now_datetime(),
		"ebarimt_error": None,
	}
	if inactive_id:
		values["ebarimt_previous_id"] = inactive_id

	doc.db_set(values)
	return result


def resync_receipt(doctype, original_name, settings, return_doc=None):
	"""Bring the original invoice's receipt in line with its submitted returns.

	Nothing returned: keep/issue the full receipt. Everything returned: void it.
	Partly returned: replace it with a receipt for the quantities kept.
	"""
	original = frappe.get_doc(doctype, original_name)
	qty_factor = get_remaining_qty_factor(original)
	has_live_receipt = original.ebarimt_id and original.ebarimt_status == STATUS_SENT
	client = PosAPIClient(settings)

	if not any(qty_factor.values()):
		if has_live_receipt:
			client.delete_receipt(original.ebarimt_id, original.ebarimt_date)
			original.db_set("ebarimt_status", STATUS_CANCELLED)
	else:
		issue_receipt(
			original,
			settings,
			inactive_id=original.ebarimt_id if has_live_receipt else None,
			qty_factor=qty_factor,
		)

	if return_doc and return_doc.docstatus == 1:
		return_doc.db_set(
			{
				"ebarimt_status": STATUS_RETURN,
				"ebarimt_previous_id": original.ebarimt_previous_id or original.ebarimt_id,
				"ebarimt_error": None,
			}
		)


def get_remaining_qty_factor(original):
	"""Share of each original item row's quantity not yet returned, keyed by row name."""
	link_field = RETURN_LINK_FIELD[original.doctype]
	returned = defaultdict(float)
	return_items = frappe.get_all(
		original.doctype + " Item",
		filters={
			"parenttype": original.doctype,
			"docstatus": 1,
			link_field: ("in", [row.name for row in original.items]),
		},
		fields=[link_field, "qty", "parent"],
	)
	return_names = {
		d.name
		for d in frappe.get_all(
			original.doctype,
			filters={"return_against": original.name, "is_return": 1, "docstatus": 1},
		)
	}
	for row in return_items:
		if row.parent in return_names:
			returned[row.get(link_field)] += abs(flt(row.qty))

	factor = {}
	for row in original.items:
		qty = flt(row.qty)
		factor[row.name] = max(qty - returned[row.name], 0) / qty if qty else 0
	return factor


# ---------------------------------------------------------------------------
# Payload
# ---------------------------------------------------------------------------


def build_payload(doc, settings, inactive_id=None, qty_factor=None):
	item_taxes = get_item_taxes(doc, settings)
	item_meta = get_item_meta([row.item_code for row in doc.items if row.item_code])

	receipts = {}
	for row in doc.items:
		factor = 1 if qty_factor is None else qty_factor.get(row.name, 0)
		if not factor:
			continue

		taxes = item_taxes.get(row.name, {})
		vat = flt(taxes.get("vat")) * factor
		city_tax = flt(taxes.get("city_tax")) * factor
		total = (flt(row.base_net_amount) + flt(taxes.get("total"))) * factor
		qty = flt(row.qty) * factor
		meta = item_meta.get(row.item_code, {})

		tax_type = "VAT_ABLE" if vat else (meta.get("ebarimt_tax_type") or settings.non_vat_tax_type)
		receipt = receipts.setdefault(
			tax_type,
			{
				"taxType": tax_type,
				"merchantTin": settings.merchant_tin,
				"totalAmount": 0.0,
				"totalVAT": 0.0,
				"totalCityTax": 0.0,
				"items": [],
			},
		)

		item = {
			"name": row.item_name,
			"barCode": row.get("barcode") or None,
			"barCodeType": "GS1" if row.get("barcode") else "UNDEFINED",
			"classificationCode": meta.get("ebarimt_classification_code")
			or settings.default_classification_code,
			"measureUnit": row.uom,
			"qty": round(qty, 4),
			"unitPrice": round(total / qty, 2) if qty else 0,
			"totalAmount": round(total, 2),
			"totalVAT": round(vat, 2),
			"totalCityTax": round(city_tax, 2),
		}
		if tax_type in ("VAT_FREE", "VAT_ZERO"):
			item["taxProductCode"] = meta.get("ebarimt_tax_product_code")
			if not item["taxProductCode"]:
				raise EBarimtError(
					_("Item {0} needs an E-Barimt Tax Product Code for tax type {1}").format(
						row.item_code, tax_type
					)
				)

		receipt["items"].append(item)
		receipt["totalAmount"] += item["totalAmount"]
		receipt["totalVAT"] += item["totalVAT"]
		receipt["totalCityTax"] += item["totalCityTax"]

	if not receipts:
		raise EBarimtError(_("Nothing to register: the invoice has no items left"))

	for receipt in receipts.values():
		for key in ("totalAmount", "totalVAT", "totalCityTax"):
			receipt[key] = round(receipt[key], 2)

	total_amount = round(sum(r["totalAmount"] for r in receipts.values()), 2)
	customer_tin = get_customer_tin(doc, settings)
	receipt_type = get_receipt_type(doc, customer_tin)

	payload = {
		"branchNo": settings.branch_no,
		"posNo": settings.pos_no,
		"merchantTin": settings.merchant_tin,
		"districtCode": settings.district_code,
		"type": receipt_type,
		"totalAmount": total_amount,
		"totalVAT": round(sum(r["totalVAT"] for r in receipts.values()), 2),
		"totalCityTax": round(sum(r["totalCityTax"] for r in receipts.values()), 2),
		"receipts": list(receipts.values()),
		"payments": get_payments(doc, receipt_type, total_amount),
	}
	if customer_tin:
		payload["customerTin"] = customer_tin
	elif doc.get("ebarimt_consumer_no"):
		payload["consumerNo"] = doc.ebarimt_consumer_no
	if inactive_id:
		payload["inactiveId"] = inactive_id

	return payload


def get_item_taxes(doc, settings):
	"""Per item row: VAT, city tax and total tax amounts in company currency."""
	tax_accounts = {row.name: row.account_head for row in doc.get("taxes") or []}
	out = defaultdict(lambda: defaultdict(float))

	# amounts in Item Wise Tax Detail are in company currency
	for detail in doc.get("item_wise_tax_details") or []:
		account = tax_accounts.get(detail.tax_row)
		amount = flt(detail.amount)
		taxes = out[detail.item_row]
		taxes["total"] += amount
		if account == settings.vat_account:
			taxes["vat"] += amount
		elif settings.city_tax_account and account == settings.city_tax_account:
			taxes["city_tax"] += amount

	return out


def get_item_meta(item_codes):
	if not item_codes:
		return {}

	return {
		d.name: d
		for d in frappe.get_all(
			"Item",
			filters={"name": ("in", list(set(item_codes)))},
			fields=[
				"name",
				"ebarimt_classification_code",
				"ebarimt_tax_product_code",
				"ebarimt_tax_type",
			],
		)
	}


def get_customer_tin(doc, settings):
	if doc.get("ebarimt_customer_tin"):
		return doc.ebarimt_customer_tin

	if not doc.customer:
		return None

	customer_type, tin = frappe.db.get_value("Customer", doc.customer, ["customer_type", "ebarimt_tin"])
	if customer_type == "Individual":
		return None

	if not tin and doc.get("tax_id"):
		tin = lookup_tin(doc.tax_id, settings)

	return tin


def get_receipt_type(doc, customer_tin):
	if doc.get("ebarimt_type"):
		return doc.ebarimt_type

	party = "B2B" if customer_tin else "B2C"
	paid = doc.is_pos or flt(doc.outstanding_amount) <= 0
	return f"{party}_{'RECEIPT' if paid else 'INVOICE'}"


def get_payments(doc, receipt_type, total_amount):
	if receipt_type.endswith("_INVOICE"):
		return []

	payments = []
	for row in doc.get("payments") or []:
		if not flt(row.base_amount):
			continue
		mode_type = frappe.get_cached_value("Mode of Payment", row.mode_of_payment, "type")
		payments.append(
			{
				"code": "CASH" if mode_type == "Cash" else "PAYMENT_CARD",
				"status": "PAID",
				"paidAmount": flt(row.base_amount),
			}
		)

	if not payments:
		return [{"code": "CASH", "status": "PAID", "paidAmount": total_amount}]

	# change given back and partial returns: payments must add up to the receipt total
	paid = sum(p["paidAmount"] for p in payments)
	for p in payments:
		p["paidAmount"] = round(p["paidAmount"] * total_amount / paid, 2)
	payments[-1]["paidAmount"] = round(total_amount - sum(p["paidAmount"] for p in payments[:-1]), 2)

	return payments


# ---------------------------------------------------------------------------
# Taxpayer lookup
# ---------------------------------------------------------------------------


def _info_api_url(settings=None):
	url = settings.info_api_url if settings else None
	if not url:
		url = (
			frappe.db.get_value("E-Barimt Settings", {"enabled": 1}, "info_api_url")
			or "https://api.ebarimt.mn/api/info/check"
		)
	return url.rstrip("/")


def _info_get(path, params, settings=None):
	try:
		response = requests.get(f"{_info_api_url(settings)}/{path}", params=params, timeout=15)
		response.raise_for_status()
		data = response.json()
	except (requests.RequestException, ValueError) as e:
		raise EBarimtError(_("Taxpayer lookup failed: {0}").format(e)) from e

	if cint(data.get("status")) != 200:
		raise EBarimtError(data.get("msg") or _("Taxpayer not found"))
	return data.get("data")


def lookup_tin(reg_no, settings=None):
	reg_no = (reg_no or "").strip().upper()
	if not reg_no:
		return None
	# an 11-14 digit number is already a TIN
	if reg_no.isdigit() and len(reg_no) >= 11:
		return reg_no
	tin = _info_get("getTinInfo", {"regNo": reg_no}, settings)
	return str(tin) if tin else None


@frappe.whitelist()
def get_taxpayer_info(reg_no: str):
	"""Return TIN, name and VAT / city tax payer flags for a registration number."""
	frappe.has_permission("Customer", "read", throw=True)
	try:
		tin = lookup_tin(reg_no)
		if not tin:
			frappe.throw(_("Taxpayer not found"))
		info = _info_get("getInfo", {"tin": tin}) or {}
	except EBarimtError as e:
		frappe.throw(str(e), title=_("E-Barimt Error"))

	return {
		"tin": tin,
		"name": info.get("name"),
		"vat_payer": cint(info.get("vatPayer")),
		"city_payer": cint(info.get("cityPayer")),
		"found": cint(info.get("found", 1)),
	}


# ---------------------------------------------------------------------------
# Manual retry and scheduler
# ---------------------------------------------------------------------------


@frappe.whitelist()
def resend(doctype: str, name: str):
	if doctype not in INVOICE_DOCTYPES:
		frappe.throw(_("Invalid document type"))

	doc = frappe.get_doc(doctype, name)
	doc.check_permission("submit")
	if doc.docstatus != 1:
		frappe.throw(_("Only submitted invoices can be sent to E-Barimt"))

	settings = _get_settings(doc)
	if not settings:
		frappe.throw(_("E-Barimt is not enabled for Company {0}").format(doc.company))

	try:
		if doc.is_return and doc.return_against:
			resync_receipt(doctype, doc.return_against, settings, doc)
		elif doc.ebarimt_status != STATUS_SENT:
			issue_receipt(doc, settings)
	except EBarimtError as e:
		doc.db_set({"ebarimt_status": STATUS_FAILED, "ebarimt_error": str(e)})
		frappe.throw(str(e), title=_("E-Barimt Error"))

	return doc.ebarimt_status


def process_pending():
	"""Hourly: retry failed receipts and push stored receipts to the tax authority."""
	for settings_name in frappe.get_all("E-Barimt Settings", filters={"enabled": 1}, pluck="name"):
		settings = frappe.get_doc("E-Barimt Settings", settings_name)

		for doctype in INVOICE_DOCTYPES:
			for name in frappe.get_all(
				doctype,
				filters={"company": settings.company, "docstatus": 1, "ebarimt_status": STATUS_FAILED},
				pluck="name",
				limit=200,
			):
				try:
					resend(doctype, name)
					frappe.db.commit()
				except Exception:
					frappe.db.rollback()
					frappe.log_error(f"E-Barimt retry failed for {doctype} {name}")

		try:
			PosAPIClient(settings).send_data()
		except EBarimtError:
			frappe.log_error(f"E-Barimt sendData failed for {settings.company}")


def get_qr_code_image(qr_data):
	"""Base64 PNG of the receipt QR code, for print formats."""
	if not qr_data:
		return ""

	from pyqrcode import create as qr_create

	return qr_create(qr_data).png_as_base64_str(scale=3)
