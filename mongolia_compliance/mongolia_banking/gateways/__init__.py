"""Registry of payment gateway clients.

Built in: QPay. SocialPay (Голомт), Khan Bank and Golomt corporate gateways are planned as follow-ups;
another app can register its own client with the `mongolia_payment_gateways` hook:

	mongolia_payment_gateways = {"SocialPay": "my_app.socialpay.get_client"}

The value is a dotted path to a function `get_client(company: str) -> PaymentGatewayClient`.
"""

BUILTIN_GATEWAYS = {
	"QPay": "mongolia_compliance.mongolia_banking.payments.get_qpay_client",
}


def get_gateway_factories() -> dict[str, str]:
	import frappe

	factories = dict(BUILTIN_GATEWAYS)
	# dict hooks come back from frappe as {key: [value, ...]}; the last installed app wins
	for gateway, paths in (frappe.get_hooks("mongolia_payment_gateways") or {}).items():
		factories[gateway] = paths[-1] if isinstance(paths, list) else paths
	return factories


def get_client(gateway: str, company: str):
	import frappe
	from frappe import _

	factory = get_gateway_factories().get(gateway)
	if not factory:
		frappe.throw(_("Төлбөрийн гарц '{0}' бүртгэгдээгүй байна").format(gateway))
	return frappe.get_attr(factory)(company)
