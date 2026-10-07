app_name = "mongolia_compliance"
app_title = "Mongolia Compliance"
app_publisher = "Anjaa"
app_description = (
	"Mongolian localization for ERPNext: chart of accounts, VAT, E-Barimt, reports and translations"
)
app_email = "anjaaariunjargal@gmail.com"
app_license = "gpl-3.0"

required_apps = ["erpnext"]

after_install = "mongolia_compliance.install.after_install"
after_migrate = "mongolia_compliance.install.after_migrate"

doctype_js = {
	"Customer": "public/js/customer.js",
	"Sales Invoice": "public/js/invoice.js",
	"POS Invoice": "public/js/invoice.js",
}

doc_events = {
	"Company": {
		"on_update": "mongolia_compliance.mongolia_accounting.setup.on_company_update",
	},
	"Sales Invoice": {
		"on_submit": "mongolia_compliance.e_barimt.ebarimt.on_submit",
		"on_cancel": "mongolia_compliance.e_barimt.ebarimt.on_cancel",
	},
	"POS Invoice": {
		"on_submit": "mongolia_compliance.e_barimt.ebarimt.on_submit",
		"on_cancel": "mongolia_compliance.e_barimt.ebarimt.on_cancel",
	},
}

scheduler_events = {
	"hourly": [
		"mongolia_compliance.e_barimt.ebarimt.process_pending",
	],
}

jinja = {
	"methods": [
		"mongolia_compliance.e_barimt.ebarimt.get_qr_code_image",
	],
}
