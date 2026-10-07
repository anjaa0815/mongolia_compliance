// Copyright (c) 2026, Anjaa and contributors
// For license information, please see license.txt

frappe.ui.form.on("Mongolia Payroll Settings", {
	refresh(frm) {
		frm.add_custom_button(__("Цалингийн бүтэц үүсгэх"), () => {
			frappe.prompt(
				{
					fieldname: "company",
					fieldtype: "Link",
					options: "Company",
					label: __("Company"),
					reqd: 1,
					default: frappe.defaults.get_user_default("Company"),
				},
				(values) => {
					frappe
						.call({
							method: "mongolia_compliance.mongolia_payroll.doctype.mongolia_payroll_settings.mongolia_payroll_settings.create_salary_structure",
							args: { company: values.company },
						})
						.then((r) => r.message && frappe.set_route("Form", "Salary Structure", r.message));
				},
				__("Монгол стандарт цалингийн бүтэц")
			);
		});
	},
	minimum_wage: (frm) => frm.set_value("ndsh_ceiling", frm.doc.minimum_wage * frm.doc.ceiling_multiplier),
	ceiling_multiplier: (frm) =>
		frm.set_value("ndsh_ceiling", frm.doc.minimum_wage * frm.doc.ceiling_multiplier),
});
