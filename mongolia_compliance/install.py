# Copyright (c) 2026, Anjaa and contributors
# License: GNU General Public License v3. See license.txt

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def after_install():
	after_migrate()


def after_migrate():
	make_custom_fields()
	sync_report_templates()

	from mongolia_compliance.mongolia_accounting.setup import setup_tax_withholding_categories

	for company in frappe.get_all("Company", filters={"country": "Mongolia"}, pluck="name"):
		setup_tax_withholding_categories(company)


def sync_report_templates():
	from erpnext.accounts.doctype.financial_report_template.financial_report_template import (
		_sync_templates_for,
	)

	_sync_templates_for("mongolia_compliance")


def make_custom_fields(update=True):
	invoice_fields = [
		dict(
			fieldname="ebarimt_section",
			label="E-Barimt",
			fieldtype="Section Break",
			insert_after="po_date",
			collapsible=1,
		),
		dict(
			fieldname="ebarimt_type",
			label="E-Barimt Type",
			fieldtype="Select",
			options="\nB2C_RECEIPT\nB2B_RECEIPT\nB2C_INVOICE\nB2B_INVOICE",
			description="Leave empty to choose automatically from the customer and payment.",
			insert_after="ebarimt_section",
			print_hide=1,
		),
		dict(
			fieldname="ebarimt_consumer_no",
			label="Consumer E-Barimt No",
			fieldtype="Data",
			description="8-digit E-Barimt number of an individual customer.",
			insert_after="ebarimt_type",
			print_hide=1,
		),
		dict(
			fieldname="ebarimt_customer_tin",
			label="Customer TIN",
			fieldtype="Data",
			description="Filled from the customer's registration number when left empty.",
			insert_after="ebarimt_consumer_no",
			print_hide=1,
		),
		dict(fieldname="ebarimt_column_break", fieldtype="Column Break", insert_after="ebarimt_customer_tin"),
		dict(
			fieldname="ebarimt_status",
			label="E-Barimt Status",
			fieldtype="Select",
			options="\nSent\nFailed\nCancelled\nReturn Processed",
			insert_after="ebarimt_column_break",
			read_only=1,
			no_copy=1,
			allow_on_submit=1,
			in_standard_filter=1,
			print_hide=1,
		),
		dict(
			fieldname="ebarimt_id",
			label="E-Barimt Receipt ID",
			fieldtype="Data",
			insert_after="ebarimt_status",
			read_only=1,
			no_copy=1,
			allow_on_submit=1,
			in_standard_filter=1,
		),
		dict(
			fieldname="ebarimt_lottery",
			label="E-Barimt Lottery No",
			fieldtype="Data",
			insert_after="ebarimt_id",
			read_only=1,
			no_copy=1,
			allow_on_submit=1,
		),
		dict(
			fieldname="ebarimt_date",
			label="E-Barimt Date",
			fieldtype="Datetime",
			insert_after="ebarimt_lottery",
			read_only=1,
			no_copy=1,
			allow_on_submit=1,
			print_hide=1,
		),
		dict(
			fieldname="ebarimt_previous_id",
			label="Replaced E-Barimt Receipt ID",
			fieldtype="Data",
			insert_after="ebarimt_date",
			read_only=1,
			no_copy=1,
			allow_on_submit=1,
			print_hide=1,
		),
		dict(
			fieldname="ebarimt_qr_data",
			label="E-Barimt QR Data",
			fieldtype="Small Text",
			insert_after="ebarimt_previous_id",
			read_only=1,
			no_copy=1,
			allow_on_submit=1,
			hidden=1,
			print_hide=1,
		),
		dict(
			fieldname="ebarimt_error",
			label="E-Barimt Error",
			fieldtype="Small Text",
			insert_after="ebarimt_qr_data",
			read_only=1,
			no_copy=1,
			allow_on_submit=1,
			depends_on="eval:doc.ebarimt_status=='Failed'",
			print_hide=1,
		),
	]

	custom_fields = {
		"Sales Invoice": invoice_fields,
		"POS Invoice": invoice_fields,
		"Item": [
			dict(
				fieldname="ebarimt_classification_code",
				label="E-Barimt Classification Code",
				fieldtype="Data",
				description="Product and service classification code (БҮНА) reported on E-Barimt receipts.",
				insert_after="item_group",
			),
			dict(
				fieldname="ebarimt_tax_type",
				label="E-Barimt Tax Type",
				fieldtype="Select",
				options="\nVAT_ABLE\nVAT_FREE\nVAT_ZERO\nNO_VAT",
				description="Used when no VAT is charged on the item. VAT_FREE and VAT_ZERO need a Tax Product Code.",
				insert_after="ebarimt_classification_code",
			),
			dict(
				fieldname="ebarimt_tax_product_code",
				label="E-Barimt Tax Product Code",
				fieldtype="Data",
				depends_on="eval:['VAT_FREE','VAT_ZERO'].includes(doc.ebarimt_tax_type)",
				insert_after="ebarimt_tax_type",
			),
		],
		"Company": [
			dict(
				fieldname="mn_use_mongolian_chart",
				label="Use Mongolian Chart of Accounts",
				fieldtype="Check",
				default="1",
				depends_on="eval:doc.country=='Mongolia'",
				description="Replace the chart selected above with the Mongolian chart of accounts while the company has no transactions.",
				insert_after="chart_of_accounts",
			),
			dict(
				fieldname="mn_chart_installed",
				label="Mongolian Chart of Accounts Installed",
				fieldtype="Check",
				read_only=1,
				no_copy=1,
				depends_on="eval:doc.country=='Mongolia'",
				insert_after="mn_use_mongolian_chart",
			),
		],
		"Customer": [
			dict(
				fieldname="ebarimt_tin",
				label="TIN",
				fieldtype="Data",
				description="Taxpayer identification number, looked up from the Tax ID (registration number).",
				insert_after="tax_id",
			),
			dict(
				fieldname="ebarimt_vat_payer",
				label="VAT Payer",
				fieldtype="Check",
				read_only=1,
				insert_after="ebarimt_tin",
			),
		],
	}

	create_custom_fields(custom_fields, update=update)
