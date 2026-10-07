"""QPay v2 client against a fake HTTP session (no network, no bench)."""

import os
import sys
import time

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from mongolia_compliance.mongolia_banking.gateways.base import GatewayError, InvoiceRequest
from mongolia_compliance.mongolia_banking.gateways.qpay import SANDBOX_URL, QPayClient


class FakeResponse:
	def __init__(self, status_code=200, data=None):
		self.status_code = status_code
		self._data = data if data is not None else {}
		self.text = str(self._data)

	def json(self):
		return self._data


class FakeSession:
	def __init__(self, responses):
		self.responses = list(responses)
		self.calls = []

	def _next(self, method, url, **kwargs):
		self.calls.append((method, url, kwargs))
		return self.responses.pop(0)

	def post(self, url, **kwargs):
		return self._next("POST", url, **kwargs)

	def request(self, method, url, **kwargs):
		return self._next(method, url, **kwargs)


def token(expires_in=None):
	now = int(time.time())
	return FakeResponse(
		200,
		{
			"token_type": "bearer",
			"access_token": "ACCESS",
			"refresh_token": "REFRESH",
			"expires_in": expires_in or now + 86400,
			"refresh_expires_in": now + 2 * 86400,
		},
	)


def client(session):
	return QPayClient("TEST_MERCHANT", "secret", "TEST_INVOICE", base_url=SANDBOX_URL, session=session)


def test_create_invoice_payload_and_parse():
	session = FakeSession(
		[
			token(),
			FakeResponse(
				200,
				{
					"invoice_id": "inv-1",
					"qr_text": "0002010102...",
					"qr_image": "iVBOR",
					"qPay_shortUrl": "https://s.qpay.mn/x",
					"urls": [
						{"name": "Khan bank", "description": "Хаан банк", "logo": "l", "link": "khanbank://q"}
					],
				},
			),
		]
	)
	result = client(session).create_invoice(
		InvoiceRequest(
			reference="SINV-1-1", amount=150000, description="Test", callback_url="https://x/cb?token=t"
		)
	)
	assert result.invoice_id == "inv-1"
	assert result.short_url == "https://s.qpay.mn/x"
	assert result.deeplinks[0]["link"] == "khanbank://q"

	method, url, kwargs = session.calls[0]
	assert url == f"{SANDBOX_URL}/v2/auth/token" and kwargs["auth"] == ("TEST_MERCHANT", "secret")
	method, url, kwargs = session.calls[1]
	assert (method, url) == ("POST", f"{SANDBOX_URL}/v2/invoice")
	assert kwargs["headers"]["Authorization"] == "Bearer ACCESS"
	assert kwargs["json"] == {
		"invoice_code": "TEST_INVOICE",
		"sender_invoice_no": "SINV-1-1",
		"invoice_receiver_code": "terminal",
		"invoice_description": "Test",
		"amount": 150000.0,
		"callback_url": "https://x/cb?token=t",
	}


def test_token_is_cached_between_calls():
	session = FakeSession(
		[token(), FakeResponse(200, {"count": 0, "rows": []}), FakeResponse(200, {"count": 0, "rows": []})]
	)
	c = client(session)
	c.check_payments("inv-1")
	c.check_payments("inv-1")
	assert [call[1].rsplit("/", 2)[-2:] for call in session.calls].count(["auth", "token"]) == 1


def test_expired_access_token_is_refreshed():
	session = FakeSession([token(expires_in=int(time.time()) + 10), token(), FakeResponse(200, {"rows": []})])
	c = client(session)
	c.get_token()  # stores a token that is inside the safety margin
	c.check_payments("inv-1")
	assert session.calls[1][1].endswith("/v2/auth/refresh")
	assert session.calls[1][2]["headers"]["Authorization"] == "Bearer REFRESH"


def test_401_retries_once_with_new_token():
	session = FakeSession([token(), FakeResponse(401, {}), token(), FakeResponse(200, {"rows": []})])
	assert client(session).check_payments("inv-1") == []
	assert len(session.calls) == 4


def test_check_payments_parses_rows():
	session = FakeSession(
		[
			token(),
			FakeResponse(
				200,
				{
					"count": 1,
					"paid_amount": 150000,
					"rows": [
						{
							"payment_id": 593744473409193,
							"payment_status": "PAID",
							"payment_date": "2026-10-07T05:15:01.123Z",
							"payment_fee": "1500.00",
							"payment_amount": "150000.00",
							"payment_currency": "MNT",
							"payment_wallet": "Khan bank",
						}
					],
				},
			),
		]
	)
	(payment,) = client(session).check_payments("inv-1")
	assert payment.is_paid and payment.amount == 150000 and payment.fee == 1500
	assert payment.payment_id == "593744473409193"
	assert payment.paid_at.year == 2026
	body = session.calls[1][2]["json"]
	assert body["object_type"] == "INVOICE" and body["object_id"] == "inv-1"


def test_errors_are_gateway_errors():
	session = FakeSession([FakeResponse(401, {"message": "NO_CREDENDIALS"})])
	with pytest.raises(GatewayError):
		client(session).get_token()

	session = FakeSession([token(), FakeResponse(400, {"message": "INVOICE_CODE_INVALID"})])
	with pytest.raises(GatewayError, match="INVOICE_CODE_INVALID"):
		client(session).create_invoice(InvoiceRequest("R", 100, "d", "https://x"))


def test_rejects_foreign_currency_and_zero():
	c = client(FakeSession([]))
	with pytest.raises(GatewayError):
		c.create_invoice(InvoiceRequest("R", 100, "d", "https://x", currency="USD"))
	with pytest.raises(GatewayError):
		c.create_invoice(InvoiceRequest("R", 0, "d", "https://x"))
