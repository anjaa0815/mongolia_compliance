# Copyright (c) 2026, Anjaa and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import date_diff, flt, getdate, today


def execute(filters=None):
	filters = frappe._dict(filters or {})
	return get_columns(), get_data(filters)


def get_columns():
	return [
		{
			"label": _("Stock Entry"),
			"fieldname": "stock_entry",
			"fieldtype": "Link",
			"options": "Stock Entry",
			"width": 160,
		},
		{"label": _("Posting Date"), "fieldname": "posting_date", "fieldtype": "Date", "width": 100},
		{"label": _("Item"), "fieldname": "item_code", "fieldtype": "Link", "options": "Item", "width": 140},
		{"label": _("Item Name"), "fieldname": "item_name", "fieldtype": "Data", "width": 160},
		{
			"label": _("Source Warehouse"),
			"fieldname": "s_warehouse",
			"fieldtype": "Link",
			"options": "Warehouse",
			"width": 150,
		},
		{
			"label": _("Transit Warehouse"),
			"fieldname": "t_warehouse",
			"fieldtype": "Link",
			"options": "Warehouse",
			"width": 150,
		},
		{
			"label": _("Destination Warehouse"),
			"fieldname": "destination",
			"fieldtype": "Link",
			"options": "Warehouse",
			"width": 150,
		},
		{"label": _("UOM"), "fieldname": "stock_uom", "fieldtype": "Link", "options": "UOM", "width": 70},
		{"label": _("Sent Qty"), "fieldname": "sent_qty", "fieldtype": "Float", "width": 90},
		{"label": _("Received Qty"), "fieldname": "received_qty", "fieldtype": "Float", "width": 100},
		{"label": _("Qty In Transit"), "fieldname": "pending_qty", "fieldtype": "Float", "width": 100},
		{"label": _("Value In Transit"), "fieldname": "pending_value", "fieldtype": "Currency", "width": 120},
		{"label": _("Days"), "fieldname": "days", "fieldtype": "Int", "width": 60},
		{"label": _("Status"), "fieldname": "status", "fieldtype": "Data", "width": 130},
	]


def get_data(filters):
	se = frappe.qb.DocType("Stock Entry")
	sed = frappe.qb.DocType("Stock Entry Detail")
	query = (
		frappe.qb.from_(se)
		.join(sed)
		.on(sed.parent == se.name)
		.select(
			se.name.as_("stock_entry"),
			se.posting_date,
			sed.item_code,
			sed.item_name,
			sed.s_warehouse,
			sed.t_warehouse,
			sed.mn_final_warehouse.as_("destination"),
			sed.stock_uom,
			sed.transfer_qty.as_("sent_qty"),
			sed.transferred_qty.as_("received_qty"),
			sed.valuation_rate,
		)
		.where(
			(se.docstatus == 1)
			& (se.add_to_transit == 1)
			& (se.purpose == "Material Transfer")
			& (se.company == filters.company)
			& (se.posting_date[getdate(filters.from_date) : getdate(filters.to_date)])
		)
		.orderby(se.posting_date)
		.orderby(se.name)
		.orderby(sed.idx)
	)
	if filters.warehouse:
		query = query.where(sed.mn_final_warehouse == filters.warehouse)

	rows = query.run(as_dict=True)
	received_entries = get_entries_with_receipts({row.stock_entry for row in rows})

	data = []
	for row in rows:
		row.pending_qty = max(flt(row.sent_qty) - flt(row.received_qty), 0)
		row.pending_value = row.pending_qty * flt(row.valuation_rate)
		if not row.pending_qty:
			row.status = "Received"
		elif row.stock_entry in received_entries:
			row.status = "Partially Received"
		else:
			row.status = "In Transit"
		if row.pending_qty:
			row.days = date_diff(today(), row.posting_date)

		if filters.status and row.status != filters.status:
			continue
		data.append(row)

	return data


def get_entries_with_receipts(stock_entries):
	if not stock_entries:
		return set()
	return set(
		frappe.get_all(
			"Stock Entry",
			filters={"outgoing_stock_entry": ("in", list(stock_entries)), "docstatus": 1},
			pluck="outgoing_stock_entry",
		)
	)
