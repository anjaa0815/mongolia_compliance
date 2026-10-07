// Copyright (c) 2026, Anjaa and contributors
// For license information, please see license.txt

frappe.query_reports["ND-7"] = {
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
			fieldname: "year",
			label: __("Year"),
			fieldtype: "Int",
			reqd: 1,
			default: moment().year(),
		},
		{
			fieldname: "month",
			label: __("Month"),
			fieldtype: "Select",
			options: ["1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11", "12"],
			reqd: 1,
			default: String(moment().month() + 1),
		},
	],
	onload(report) {
		report.page.add_inner_button(__("НДЕГ Excel загвар"), () => {
			const filters = report.get_values();
			if (!filters) return;
			open_url_post(
				"/api/method/mongolia_compliance.mongolia_payroll.social_insurance.download_excel",
				{
					report: "ND-7",
					filters: JSON.stringify(filters),
				}
			);
		});
	},
};
