"""Two-step transfers between branches through an in-transit warehouse.

A Material Transfer from one branch's warehouse to another branch's warehouse is sent to the
company's transit warehouse first. The branch then receives it with "End Transit", which brings
the goods from transit into the destination warehouse kept on each row.
"""

import frappe
from frappe import _

TRANSIT_WAREHOUSE_NAME = "Замд яваа бараа"


def before_validate_stock_entry(doc, method=None):
	if doc.purpose != "Material Transfer" or not is_mongolian(doc.company):
		return

	if doc.outgoing_stock_entry:
		set_destination_from_outgoing_entry(doc)
	elif not doc.add_to_transit:
		route_through_transit(doc)


def route_through_transit(doc):
	rows = [
		(row, row.s_warehouse or doc.from_warehouse, row.t_warehouse or doc.to_warehouse) for row in doc.items
	]
	if not any(is_cross_branch(source, target) for _row, source, target in rows):
		return

	transit = get_transit_warehouse(doc.company, doc.from_warehouse or rows[0][1])
	if not transit:
		frappe.throw(
			_("Set a Default In-Transit Warehouse on Company {0} to transfer goods between branches.").format(
				frappe.bold(doc.company)
			),
			title=_("Transit Warehouse Missing"),
		)

	for row, _source, target in rows:
		row.mn_final_warehouse = target
		row.t_warehouse = transit
	doc.to_warehouse = transit
	doc.add_to_transit = 1
	frappe.msgprint(
		_(
			"Goods are moving between branches, so they are sent to the transit warehouse {0}. Use End Transit when the branch receives them."
		).format(frappe.bold(transit)),
		alert=True,
	)


def set_destination_from_outgoing_entry(doc):
	for row in doc.items:
		if row.t_warehouse or not row.ste_detail:
			continue
		destination = frappe.db.get_value("Stock Entry Detail", row.ste_detail, "mn_final_warehouse")
		if destination:
			row.t_warehouse = destination
			row.mn_final_warehouse = destination


def is_cross_branch(source, target):
	if not source or not target:
		return False
	source_branch, target_branch = (
		frappe.get_cached_value("Warehouse", source, "mn_branch"),
		frappe.get_cached_value("Warehouse", target, "mn_branch"),
	)
	if not source_branch or not target_branch or source_branch == target_branch:
		return False
	return frappe.get_cached_value("Warehouse", target, "warehouse_type") != "Transit"


def get_transit_warehouse(company, source_warehouse=None):
	if source_warehouse:
		transit = frappe.get_cached_value("Warehouse", source_warehouse, "default_in_transit_warehouse")
		if transit:
			return transit
	return frappe.get_cached_value("Company", company, "default_in_transit_warehouse")


def setup_transit_warehouse(company):
	"""Make sure a Mongolian company has a default in-transit warehouse."""
	if frappe.get_cached_value("Company", company, "default_in_transit_warehouse"):
		return

	transit = frappe.db.get_value(
		"Warehouse",
		{"company": company, "warehouse_type": "Transit", "is_group": 0, "disabled": 0},
	)
	if not transit:
		parent = frappe.db.get_value(
			"Warehouse", {"company": company, "is_group": 1, "parent_warehouse": ("is", "not set")}
		)
		if not parent:
			return
		transit = (
			frappe.get_doc(
				{
					"doctype": "Warehouse",
					"warehouse_name": TRANSIT_WAREHOUSE_NAME,
					"company": company,
					"parent_warehouse": parent,
					"warehouse_type": "Transit",
				}
			)
			.insert(ignore_permissions=True)
			.name
		)

	frappe.db.set_value("Company", company, "default_in_transit_warehouse", transit)


def on_company_update(doc, method=None):
	if doc.country == "Mongolia":
		setup_transit_warehouse(doc.name)


def is_mongolian(company):
	return frappe.get_cached_value("Company", company, "country") == "Mongolia"
