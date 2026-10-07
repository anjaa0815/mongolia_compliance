// Copyright (c) 2026, Anjaa and contributors
// For license information, please see license.txt

frappe.query_reports["Mongolia VAT Report"] = {
	filters: [
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			reqd: 1,
			default: frappe.defaults.get_user_default("Company"),
			get_query: () => ({ filters: { country: "Mongolia" } }),
		},
		{
			fieldname: "from_date",
			label: __("From Date"),
			fieldtype: "Date",
			reqd: 1,
			default: frappe.datetime.month_start(frappe.datetime.add_months(frappe.datetime.get_today(), -1)),
		},
		{
			fieldname: "to_date",
			label: __("To Date"),
			fieldtype: "Date",
			reqd: 1,
			default: frappe.datetime.month_end(frappe.datetime.add_months(frappe.datetime.get_today(), -1)),
		},
		{
			fieldname: "output_vat_account",
			label: __("Output VAT Account"),
			fieldtype: "Link",
			options: "Account",
			description: __("Defaults to the VAT Account in E-Barimt Settings"),
			get_query: () => ({
				filters: { company: frappe.query_report.get_filter_value("company"), account_type: "Tax" },
			}),
		},
		{
			fieldname: "input_vat_account",
			label: __("Input VAT Account"),
			fieldtype: "Link",
			options: "Account",
			description: __("Defaults to account 1211 (VAT receivable)"),
			get_query: () => ({
				filters: { company: frappe.query_report.get_filter_value("company"), account_type: "Tax" },
			}),
		},
	],
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (data && data.is_summary) {
			value = `<b>${value}</b>`;
		}
		return value;
	},
};
