// Copyright (c) 2026, Anjaa and contributors
// For license information, please see license.txt

frappe.query_reports["Goods In Transit"] = {
	filters: [
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			reqd: 1,
			default: frappe.defaults.get_user_default("Company"),
		},
		{
			fieldname: "from_date",
			label: __("From Date"),
			fieldtype: "Date",
			reqd: 1,
			default: frappe.datetime.add_months(frappe.datetime.get_today(), -3),
		},
		{
			fieldname: "to_date",
			label: __("To Date"),
			fieldtype: "Date",
			reqd: 1,
			default: frappe.datetime.get_today(),
		},
		{
			fieldname: "status",
			label: __("Status"),
			fieldtype: "Select",
			options: ["", "In Transit", "Partially Received", "Received"],
		},
		{
			fieldname: "warehouse",
			label: __("Destination Warehouse"),
			fieldtype: "Link",
			options: "Warehouse",
			get_query: () => ({
				filters: { company: frappe.query_report.get_filter_value("company") },
			}),
		},
	],
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (column.fieldname === "status" && data && data.status) {
			const color = {
				"In Transit": "orange",
				"Partially Received": "red",
				Received: "green",
			}[data.status];
			value = `<span class="indicator-pill ${color || "gray"}">${__(data.status)}</span>`;
		}
		return value;
	},
};
