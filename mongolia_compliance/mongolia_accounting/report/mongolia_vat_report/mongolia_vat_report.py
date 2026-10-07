# Copyright (c) 2026, Anjaa and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.query_builder.functions import Sum
from frappe.utils import flt

# (invoice doctype, tax child doctype, party field)
SOURCES = [
	("Sales Invoice", "Sales Taxes and Charges", "customer"),
	("Purchase Invoice", "Purchase Taxes and Charges", "supplier"),
]


def execute(filters=None):
	filters = frappe._dict(filters or {})
	accounts = get_vat_accounts(filters)

	data = []
	totals = {}
	for doctype, tax_doctype, party_field in SOURCES:
		rows = get_invoices(filters, doctype, tax_doctype, party_field, accounts[doctype])
		data.extend(rows)
		totals[doctype] = (
			sum(flt(r["net_amount"]) for r in rows),
			sum(flt(r["vat_amount"]) for r in rows),
		)

	output_net, output_vat = totals["Sales Invoice"]
	input_net, input_vat = totals["Purchase Invoice"]
	data += [
		{},
		summary_row(_("Output VAT (Sales)"), output_net, output_vat),
		summary_row(_("Input VAT (Purchases)"), input_net, input_vat),
		summary_row(_("VAT Payable / (Refundable)"), None, output_vat - input_vat),
	]

	return get_columns(), data


def summary_row(label, net, vat):
	return {"transaction_type": label, "net_amount": net, "vat_amount": vat, "is_summary": 1}


def get_vat_accounts(filters):
	output_account = filters.output_vat_account or frappe.db.get_value(
		"E-Barimt Settings", {"company": filters.company}, "vat_account"
	)
	input_account = filters.input_vat_account or frappe.db.get_value(
		"Account", {"company": filters.company, "account_number": "1211", "is_group": 0}
	)

	if not output_account or not input_account:
		frappe.throw(_("Set the Output VAT Account and Input VAT Account filters"))

	return {"Sales Invoice": output_account, "Purchase Invoice": input_account}


def get_invoices(filters, doctype, tax_doctype, party_field, vat_account):
	inv = frappe.qb.DocType(doctype)
	tax = frappe.qb.DocType(tax_doctype)

	party_doctype = "Customer" if doctype == "Sales Invoice" else "Supplier"
	party = frappe.qb.DocType(party_doctype)

	receipt_no = inv.ebarimt_id if doctype == "Sales Invoice" else inv.bill_no
	group_by = [inv.name, inv.posting_date, inv[party_field], inv.base_net_total, party.tax_id, receipt_no]
	fields = [
		inv.name.as_("voucher_no"),
		inv.posting_date,
		inv[party_field].as_("party"),
		inv.base_net_total.as_("net_amount"),
		party.tax_id,
		receipt_no.as_("ebarimt_id"),
		Sum(tax.base_tax_amount_after_discount_amount).as_("vat_amount"),
	]

	query = (
		frappe.qb.from_(inv)
		.join(tax)
		.on((tax.parent == inv.name) & (tax.parenttype == doctype))
		.left_join(party)
		.on(party.name == inv[party_field])
		.select(*fields)
		.where(
			(inv.docstatus == 1)
			& (inv.company == filters.company)
			& (inv.posting_date >= filters.from_date)
			& (inv.posting_date <= filters.to_date)
			& (tax.account_head == vat_account)
		)
		.groupby(*group_by)
		.orderby(inv.posting_date)
		.orderby(inv.name)
	)
	if doctype == "Purchase Invoice":
		query = query.where(tax.add_deduct_tax == "Add")

	rows = query.run(as_dict=True)
	for row in rows:
		row.transaction_type = _("Sales") if doctype == "Sales Invoice" else _("Purchases")
		row.voucher_type = doctype
		row.total_amount = flt(row.net_amount) + flt(row.vat_amount)

	return rows


def get_columns():
	return [
		{"fieldname": "transaction_type", "label": _("Type"), "fieldtype": "Data", "width": 170},
		{"fieldname": "posting_date", "label": _("Posting Date"), "fieldtype": "Date", "width": 100},
		{"fieldname": "voucher_type", "label": _("Voucher Type"), "fieldtype": "Data", "hidden": 1},
		{
			"fieldname": "voucher_no",
			"label": _("Voucher No"),
			"fieldtype": "Dynamic Link",
			"options": "voucher_type",
			"width": 170,
		},
		{"fieldname": "party", "label": _("Party"), "fieldtype": "Data", "width": 180},
		{"fieldname": "tax_id", "label": _("Tax ID"), "fieldtype": "Data", "width": 110},
		{"fieldname": "ebarimt_id", "label": _("E-Barimt Receipt ID"), "fieldtype": "Data", "width": 220},
		{"fieldname": "net_amount", "label": _("Net Amount"), "fieldtype": "Currency", "width": 130},
		{"fieldname": "vat_amount", "label": _("VAT Amount"), "fieldtype": "Currency", "width": 120},
		{"fieldname": "total_amount", "label": _("Total Amount"), "fieldtype": "Currency", "width": 130},
	]
