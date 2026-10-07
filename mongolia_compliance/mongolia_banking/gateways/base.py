"""Common interface every Mongolian payment gateway client implements.

Clients are pure python (they only need `requests`), so they can be tested with a fake session. The
frappe side (payments.py) only talks to this interface: adding SocialPay or a bank's corporate gateway
means writing one client class and registering it, without touching the invoice and payment flow.
"""

import datetime
from dataclasses import dataclass, field


class GatewayError(Exception):
	def __init__(self, message: str, status_code: int | None = None, response: dict | None = None):
		super().__init__(message)
		self.status_code = status_code
		self.response = response or {}


@dataclass
class InvoiceRequest:
	reference: str  # our unique number, e.g. ACC-SINV-2026-00012-1
	amount: float
	description: str
	callback_url: str
	receiver_code: str = "terminal"
	currency: str = "MNT"


@dataclass
class GatewayInvoice:
	invoice_id: str
	qr_text: str = ""
	qr_image: str = ""  # base64 PNG
	short_url: str = ""
	deeplinks: list[dict] = field(default_factory=list)  # [{name, description, logo, link}]
	raw: dict = field(default_factory=dict)


@dataclass
class GatewayPayment:
	payment_id: str
	amount: float
	status: str  # PAID / FAILED / REFUNDED / NEW
	paid_at: datetime.datetime | None = None
	fee: float = 0.0
	wallet: str = ""
	currency: str = "MNT"
	raw: dict = field(default_factory=dict)

	@property
	def is_paid(self) -> bool:
		return self.status.upper() == "PAID"


class PaymentGatewayClient:
	name = ""

	def create_invoice(self, request: InvoiceRequest) -> GatewayInvoice:
		raise NotImplementedError

	def check_payments(self, invoice_id: str) -> list[GatewayPayment]:
		"""All payments made against the gateway invoice."""
		raise NotImplementedError

	def cancel_invoice(self, invoice_id: str) -> None:
		raise NotImplementedError
