"""QPay Merchant API v2 client.

Endpoints (https://developer.qpay.mn):
  POST   /v2/auth/token          Basic auth (client id / secret) -> access + refresh token
  POST   /v2/auth/refresh        Bearer refresh token
  POST   /v2/invoice             create invoice -> invoice_id, qr_text, qr_image, urls
  DELETE /v2/invoice/{id}        cancel invoice
  POST   /v2/payment/check       payments made against an invoice

QPay calls the invoice's callback_url when it is paid. The callback carries no signature, so the
caller must always confirm the payment with check_payments() before trusting it.
"""

import datetime
import time

from mongolia_compliance.mongolia_banking.gateways.base import (
	GatewayError,
	GatewayInvoice,
	GatewayPayment,
	InvoiceRequest,
	PaymentGatewayClient,
)

PRODUCTION_URL = "https://merchant.qpay.mn"
SANDBOX_URL = "https://merchant-sandbox.qpay.mn"
TIMEOUT = 30
TOKEN_SAFETY_SECONDS = 60


class DictTokenCache:
	"""Minimal cache used outside frappe (tests). payments.py passes a frappe.cache adapter."""

	def __init__(self):
		self.store = {}

	def get(self, key):
		return self.store.get(key)

	def set(self, key, value, expires_in_sec=None):
		self.store[key] = value

	def delete(self, key):
		self.store.pop(key, None)


def _expiry(value, now: float) -> float:
	"""QPay returns expires_in as an epoch timestamp; other deployments return seconds."""
	value = float(value or 0)
	if value > 1_000_000_000:
		return value
	return now + (value or 300)


def _parse_datetime(value) -> datetime.datetime | None:
	if not value:
		return None
	text = str(value).replace("Z", "+00:00")
	try:
		return datetime.datetime.fromisoformat(text)
	except ValueError:
		return None


class QPayClient(PaymentGatewayClient):
	name = "QPay"

	def __init__(
		self,
		username: str,
		password: str,
		invoice_code: str,
		base_url: str = PRODUCTION_URL,
		session=None,
		cache=None,
		branch_code: str = "",
	):
		if session is None:
			import requests

			session = requests.Session()
		self.username = username
		self.password = password
		self.invoice_code = invoice_code
		self.branch_code = branch_code
		self.base_url = (base_url or PRODUCTION_URL).rstrip("/")
		self.session = session
		self.cache = cache or DictTokenCache()

	# --- auth ----------------------------------------------------------------------------

	@property
	def cache_key(self) -> str:
		return f"mongolia_banking:qpay_token:{self.base_url}:{self.username}"

	def _store_token(self, data: dict) -> str:
		now = time.time()
		token = {
			"access_token": data.get("access_token"),
			"refresh_token": data.get("refresh_token"),
			"expires_at": _expiry(data.get("expires_in"), now),
			"refresh_expires_at": _expiry(data.get("refresh_expires_in"), now),
		}
		if not token["access_token"]:
			raise GatewayError("QPay токен буцаасангүй", response=data)
		ttl = max(int(token["refresh_expires_at"] - now), 60)
		self.cache.set(self.cache_key, token, expires_in_sec=ttl)
		return token["access_token"]

	def get_token(self, force: bool = False) -> str:
		now = time.time()
		token = None if force else self.cache.get(self.cache_key)
		if token and token.get("expires_at", 0) - TOKEN_SAFETY_SECONDS > now:
			return token["access_token"]

		if (
			token
			and token.get("refresh_token")
			and token.get("refresh_expires_at", 0) - TOKEN_SAFETY_SECONDS > now
		):
			response = self.session.post(
				f"{self.base_url}/v2/auth/refresh",
				headers={"Authorization": f"Bearer {token['refresh_token']}"},
				timeout=TIMEOUT,
			)
			if response.status_code < 400:
				return self._store_token(response.json())

		response = self.session.post(
			f"{self.base_url}/v2/auth/token",
			auth=(self.username, self.password),
			timeout=TIMEOUT,
		)
		if response.status_code >= 400:
			raise GatewayError(
				"QPay нэвтрэлт амжилтгүй. Client ID / нууц үгээ шалгана уу.",
				status_code=response.status_code,
				response=_json(response),
			)
		return self._store_token(response.json())

	def _request(self, method: str, path: str, payload: dict | None = None, retry: bool = True) -> dict:
		response = self.session.request(
			method,
			f"{self.base_url}{path}",
			json=payload,
			headers={"Authorization": f"Bearer {self.get_token()}"},
			timeout=TIMEOUT,
		)
		if response.status_code == 401 and retry:
			self.cache.delete(self.cache_key)
			return self._request(method, path, payload, retry=False)
		data = _json(response)
		if response.status_code >= 400:
			message = data.get("message") or data.get("error") or response.text
			raise GatewayError(f"QPay алдаа ({response.status_code}): {message}", response.status_code, data)
		return data

	# --- invoice -------------------------------------------------------------------------

	def build_invoice_payload(self, request: InvoiceRequest) -> dict:
		payload = {
			"invoice_code": self.invoice_code,
			"sender_invoice_no": request.reference,
			"invoice_receiver_code": request.receiver_code or "terminal",
			"invoice_description": (request.description or request.reference)[:255],
			"amount": round(float(request.amount), 2),
			"callback_url": request.callback_url,
		}
		if self.branch_code:
			payload["sender_branch_code"] = self.branch_code
		return payload

	def create_invoice(self, request: InvoiceRequest) -> GatewayInvoice:
		if request.currency and request.currency != "MNT":
			raise GatewayError("QPay зөвхөн төгрөгөөр (MNT) нэхэмжлэх үүсгэнэ")
		if float(request.amount) <= 0:
			raise GatewayError("Нэхэмжлэх дүн 0-ээс их байх ёстой")

		data = self._request("POST", "/v2/invoice", self.build_invoice_payload(request))
		if not data.get("invoice_id"):
			raise GatewayError("QPay invoice_id буцаасангүй", response=data)
		return GatewayInvoice(
			invoice_id=data["invoice_id"],
			qr_text=data.get("qr_text") or "",
			qr_image=data.get("qr_image") or "",
			short_url=data.get("qPay_shortUrl") or data.get("qpay_shorturl") or "",
			deeplinks=data.get("urls") or [],
			raw=data,
		)

	def cancel_invoice(self, invoice_id: str) -> None:
		self._request("DELETE", f"/v2/invoice/{invoice_id}")

	def check_payments(self, invoice_id: str) -> list[GatewayPayment]:
		payments, page = [], 1
		while True:
			data = self._request(
				"POST",
				"/v2/payment/check",
				{
					"object_type": "INVOICE",
					"object_id": invoice_id,
					"offset": {"page_number": page, "page_limit": 100},
				},
			)
			rows = data.get("rows") or []
			for row in rows:
				payments.append(
					GatewayPayment(
						payment_id=str(row.get("payment_id")),
						amount=float(row.get("payment_amount") or 0),
						status=str(row.get("payment_status") or ""),
						paid_at=_parse_datetime(row.get("payment_date")),
						fee=float(row.get("payment_fee") or 0),
						wallet=row.get("payment_wallet") or "",
						currency=row.get("payment_currency") or "MNT",
						raw=row,
					)
				)
			if len(rows) < 100 or len(payments) >= int(data.get("count") or 0):
				break
			page += 1
		return payments


def _json(response) -> dict:
	try:
		data = response.json()
	except ValueError:
		return {}
	return data if isinstance(data, dict) else {"data": data}
