"""Collect invoice payments through Mongolian payment gateways (QPay first).

Flow: a user clicks "QPay-ээр төлүүлэх" on a submitted Sales Invoice (or Sales Order) -> a gateway invoice
is created and its QR / bank-app links are shown -> the customer pays -> QPay calls our callback (and a
scheduler polls as a fallback) -> the payment is confirmed through the QPay API -> a Payment Entry is
created against the invoice.
"""

import frappe
from frappe import _
from frappe.rate_limiter import rate_limit
from frappe.utils import convert_utc_to_system_timezone, flt, get_url, getdate, now_datetime, nowdate

from mongolia_compliance.mongolia_banking.gateways import get_client
from mongolia_compliance.mongolia_banking.gateways.base import GatewayError, InvoiceRequest
from mongolia_compliance.mongolia_banking.gateways.qpay import PRODUCTION_URL, SANDBOX_URL, QPayClient

GATEWAY_INVOICE = "Mongolia Gateway Invoice"
SUPPORTED_DOCTYPES = ("Sales Invoice", "Sales Order")
POLL_DAYS = 3


class FrappeTokenCache:
	def get(self, key):
		return frappe.cache.get_value(key)

	def set(self, key, value, expires_in_sec=None):
		frappe.cache.set_value(key, value, expires_in_sec=expires_in_sec)

	def delete(self, key):
		frappe.cache.delete_value(key)


def get_qpay_settings(company: str):
	if not frappe.db.exists("QPay Settings", company):
		frappe.throw(_("{0} компанид QPay Settings тохируулаагүй байна").format(company))
	settings = frappe.get_cached_doc("QPay Settings", company)
	if not settings.enabled:
		frappe.throw(_("{0} компанийн QPay идэвхгүй байна").format(company))
	return settings


def get_qpay_client(company: str) -> QPayClient:
	settings = get_qpay_settings(company)
	return QPayClient(
		username=settings.client_id,
		password=settings.get_password("client_secret"),
		invoice_code=settings.invoice_code,
		branch_code=settings.branch_code or "",
		base_url=SANDBOX_URL if settings.sandbox else PRODUCTION_URL,
		cache=FrappeTokenCache(),
	)


def get_gateway_accounting(gateway: str, company: str) -> frappe._dict:
	"""Account, mode of payment and auto-submit flag for Payment Entries of this gateway.

	Clients registered by other apps expose the same values as attributes."""
	if gateway == "QPay":
		settings = get_qpay_settings(company)
		return frappe._dict(
			account=settings.payment_account,
			mode_of_payment=settings.mode_of_payment,
			auto_submit=settings.auto_submit_payment_entry,
		)
	client = get_client(gateway, company)
	return frappe._dict(
		account=getattr(client, "payment_account", None),
		mode_of_payment=getattr(client, "mode_of_payment", None),
		auto_submit=getattr(client, "auto_submit_payment_entry", 1),
	)


# --- create -----------------------------------------------------------------------------------


def _amount_due(doc) -> float:
	if doc.doctype == "Sales Invoice":
		return flt(doc.outstanding_amount)
	return flt(doc.rounded_total or doc.grand_total) - flt(doc.advance_paid)


@frappe.whitelist(methods=["POST"])
def create_gateway_invoice(reference_doctype: str, reference_name: str, gateway: str = "QPay") -> dict:
	if reference_doctype not in SUPPORTED_DOCTYPES:
		frappe.throw(_("{0}-оос төлбөрийн нэхэмжлэх үүсгэх боломжгүй").format(_(reference_doctype)))

	doc = frappe.get_doc(reference_doctype, reference_name)
	doc.check_permission("read")
	frappe.has_permission("Payment Entry", "create", throw=True)

	if doc.docstatus != 1:
		frappe.throw(_("Баримтыг эхлээд батална уу"))
	if doc.currency != "MNT":
		frappe.throw(_("Зөвхөн төгрөгийн (MNT) баримтаар QPay нэхэмжлэх үүсгэнэ"))

	amount = _amount_due(doc)
	if amount <= 0:
		frappe.throw(_("Төлөх үлдэгдэл байхгүй байна"))

	existing = frappe.get_all(
		GATEWAY_INVOICE,
		filters={
			"reference_doctype": reference_doctype,
			"reference_name": reference_name,
			"gateway": gateway,
			"status": "Unpaid",
		},
		fields=["name", "amount"],
	)
	for row in existing:
		if abs(flt(row.amount) - amount) < 0.01:
			return get_invoice_details(row.name)
		# amount changed (partial payment, credit note): replace the old QR
		_cancel(frappe.get_doc(GATEWAY_INVOICE, row.name))

	count = frappe.db.count(GATEWAY_INVOICE, {"reference_name": reference_name})
	token = frappe.generate_hash(length=32)
	gateway_invoice = frappe.get_doc(
		{
			"doctype": GATEWAY_INVOICE,
			"gateway": gateway,
			"company": doc.company,
			"reference_doctype": reference_doctype,
			"reference_name": reference_name,
			"customer": doc.customer,
			"amount": amount,
			"currency": doc.currency,
			"sender_invoice_no": f"{reference_name}-{count + 1}",
			"callback_token": token,
		}
	)

	request = InvoiceRequest(
		reference=gateway_invoice.sender_invoice_no,
		amount=amount,
		description=f"{doc.company}: {reference_name}",
		callback_url=callback_url(doc.company, token),
		receiver_code=_receiver_code(doc),
		currency=doc.currency,
	)
	try:
		result = get_client(gateway, doc.company).create_invoice(request)
	except GatewayError as e:
		frappe.log_error(f"{gateway} invoice {reference_name}", str(e.response or e))
		frappe.throw(str(e), title=_("{0} нэхэмжлэх үүсгэж чадсангүй").format(gateway))

	gateway_invoice.update(
		{
			"gateway_invoice_id": result.invoice_id,
			"qr_text": result.qr_text,
			"qr_image": result.qr_image,
			"short_url": result.short_url,
			"deeplinks": frappe.as_json(result.deeplinks),
		}
	)
	gateway_invoice.insert(ignore_permissions=True)
	return get_invoice_details(gateway_invoice.name)


def callback_url(company: str, token: str) -> str:
	base = ""
	if frappe.db.exists("QPay Settings", company):
		base = frappe.db.get_value("QPay Settings", company, "callback_base_url") or ""
	base = (base or get_url()).rstrip("/")
	return f"{base}/api/method/mongolia_compliance.mongolia_banking.payments.qpay_callback?token={token}"


def _receiver_code(doc) -> str:
	if doc.doctype in SUPPORTED_DOCTYPES and frappe.db.exists("QPay Settings", doc.company):
		if frappe.db.get_value("QPay Settings", doc.company, "use_customer_tax_id"):
			tax_id = doc.get("tax_id") or frappe.db.get_value("Customer", doc.customer, "tax_id")
			if tax_id:
				return tax_id
	return "terminal"


def get_invoice_details(name: str) -> dict:
	doc = frappe.get_doc(GATEWAY_INVOICE, name)
	return {
		"name": doc.name,
		"gateway": doc.gateway,
		"status": doc.status,
		"amount": doc.amount,
		"paid_amount": doc.paid_amount,
		"currency": doc.currency,
		"qr_text": doc.qr_text,
		"qr_image": doc.qr_image,
		"short_url": doc.short_url,
		"deeplinks": frappe.parse_json(doc.deeplinks or "[]"),
		"payment_entry": doc.payment_entry,
	}


# --- confirm ----------------------------------------------------------------------------------


@frappe.whitelist(allow_guest=True, methods=["GET", "POST"])
@rate_limit(limit=120, seconds=60)
def qpay_callback(token: str | None = None, **kwargs):
	"""QPay hits this URL after a payment. Its body is not trusted: the payment is re-checked via the API."""
	name = token and frappe.db.get_value(GATEWAY_INVOICE, {"callback_token": token, "gateway": "QPay"})
	if not name:
		return {"status": "unknown"}

	user = frappe.session.user
	try:
		frappe.set_user("Administrator")
		status = sync_gateway_invoice(name)
		frappe.db.commit()
	except Exception:
		frappe.db.rollback()
		frappe.log_error("QPay callback", reference_doctype=GATEWAY_INVOICE, reference_name=name)
		status = "error"
	finally:
		frappe.set_user(user)
	return {"status": status}


@frappe.whitelist()
def check_gateway_invoice(name: str) -> dict:
	"""Called by the QR dialog every few seconds."""
	reference_doctype, reference_name = frappe.db.get_value(
		GATEWAY_INVOICE, name, ["reference_doctype", "reference_name"]
	)
	frappe.get_doc(reference_doctype, reference_name).check_permission("read")
	frappe.has_permission("Payment Entry", "create", throw=True)
	sync_gateway_invoice(name)
	return get_invoice_details(name)


def sync_gateway_invoice(name: str) -> str:
	# lock the row so the callback and the poller never create two Payment Entries
	frappe.db.get_value(GATEWAY_INVOICE, name, "name", for_update=True)
	doc = frappe.get_doc(GATEWAY_INVOICE, name)
	# "Failed" (expired by us) is still checked: a late callback must not lose a real payment
	if doc.status not in ("Unpaid", "Failed") or doc.payment_entry:
		return doc.status

	payments = get_client(doc.gateway, doc.company).check_payments(doc.gateway_invoice_id)
	paid = [p for p in payments if p.is_paid]
	if not paid:
		return doc.status

	paid_amount = sum(flt(p.amount) for p in paid)
	paid_at = max((p.paid_at for p in paid if p.paid_at), default=None)
	doc.paid_amount = paid_amount
	if paid_at and paid_at.tzinfo:
		# QPay sends UTC ("...Z"); Datetime fields hold the site's time zone
		paid_at = convert_utc_to_system_timezone(paid_at.replace(tzinfo=None)).replace(tzinfo=None)
	doc.paid_at = paid_at or now_datetime()
	doc.payment_ids = "\n".join(p.payment_id for p in paid)

	if paid_amount + 0.01 >= flt(doc.amount):
		doc.status = "Paid"
		try:
			doc.payment_entry = make_payment_entry(doc, paid_amount, [p.payment_id for p in paid])
			doc.error = None
		except Exception as e:
			# keep the payment recorded on the gateway invoice; an accountant can post it by hand
			doc.error = str(e)[:1000]
			frappe.log_error("QPay Payment Entry", reference_doctype=GATEWAY_INVOICE, reference_name=name)
	doc.save(ignore_permissions=True)
	return doc.status


def make_payment_entry(doc, paid_amount: float, payment_ids: list[str]) -> str:
	from erpnext.accounts.doctype.payment_entry.payment_entry import get_payment_entry

	accounting = get_gateway_accounting(doc.gateway, doc.company)
	account = accounting.account
	reference = frappe.get_doc(doc.reference_doctype, doc.reference_name)
	amount = min(paid_amount, _amount_due(reference))
	if amount <= 0:
		frappe.throw(_("{0} аль хэдийн төлөгдсөн байна").format(doc.reference_name))

	pe = get_payment_entry(
		doc.reference_doctype, doc.reference_name, party_amount=amount, bank_account=account
	)
	pe.posting_date = getdate(doc.paid_at) if doc.paid_at else nowdate()
	pe.reference_date = pe.posting_date
	pe.reference_no = ", ".join(payment_ids)[:140]
	pe.remarks = _("{0} төлбөр, нэхэмжлэх {1}").format(doc.gateway, doc.sender_invoice_no)
	pe.bank_account = frappe.db.get_value(
		"Bank Account", {"account": account, "is_company_account": 1, "company": doc.company}, "name"
	)
	if accounting.mode_of_payment and frappe.db.exists("Mode of Payment", accounting.mode_of_payment):
		pe.mode_of_payment = accounting.mode_of_payment
	pe.flags.ignore_permissions = True
	pe.insert()
	if accounting.auto_submit:
		pe.submit()
	return pe.name


# --- cancel / poll ----------------------------------------------------------------------------


@frappe.whitelist(methods=["POST"])
def cancel_gateway_invoice(name: str):
	doc = frappe.get_doc(GATEWAY_INVOICE, name)
	frappe.get_doc(doc.reference_doctype, doc.reference_name).check_permission("write")
	_cancel(doc)


def _cancel(doc):
	if doc.status != "Unpaid":
		return
	try:
		get_client(doc.gateway, doc.company).cancel_invoice(doc.gateway_invoice_id)
	except GatewayError as e:
		# already paid or expired on the gateway side: leave it for the poller
		doc.error = str(e)[:1000]
	doc.status = "Cancelled"
	doc.save(ignore_permissions=True)


def cancel_for_reference(doc, method=None):
	"""Sales Invoice / Sales Order on_cancel: drop QR codes that can no longer be paid."""
	for name in frappe.get_all(
		GATEWAY_INVOICE,
		filters={"reference_doctype": doc.doctype, "reference_name": doc.name, "status": "Unpaid"},
		pluck="name",
	):
		_cancel(frappe.get_doc(GATEWAY_INVOICE, name))


def poll_unpaid_invoices():
	"""Scheduler fallback when a callback never arrives (site not reachable from the internet)."""
	since = frappe.utils.add_days(now_datetime(), -POLL_DAYS)
	for name in frappe.get_all(
		GATEWAY_INVOICE,
		filters={"status": "Unpaid", "creation": (">=", since)},
		pluck="name",
		order_by="creation desc",
	):
		try:
			sync_gateway_invoice(name)
			frappe.db.commit()
		except Exception:
			frappe.db.rollback()
			frappe.log_error("QPay poll", reference_doctype=GATEWAY_INVOICE, reference_name=name)


def expire_old_invoices():
	"""Daily: invoices nobody paid within the polling window are marked Failed (QR no longer shown)."""
	since = frappe.utils.add_days(now_datetime(), -POLL_DAYS)
	for name in frappe.get_all(
		GATEWAY_INVOICE, filters={"status": "Unpaid", "creation": ("<", since)}, pluck="name"
	):
		frappe.db.set_value(GATEWAY_INVOICE, name, "status", "Failed")
