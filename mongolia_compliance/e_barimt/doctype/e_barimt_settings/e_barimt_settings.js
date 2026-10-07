// Copyright (c) 2026, Anjaa and contributors
// For license information, please see license.txt

frappe.ui.form.on("E-Barimt Settings", {
	setup(frm) {
		frm.set_query("company", () => ({ filters: { country: "Mongolia" } }));
		["vat_account", "city_tax_account"].forEach((field) => {
			frm.set_query(field, () => ({
				filters: { company: frm.doc.company, account_type: "Tax", is_group: 0 },
			}));
		});
	},

	refresh(frm) {
		if (frm.is_new()) return;

		frm.add_custom_button(__("Test Connection"), () => {
			frm.call("test_connection").then((r) => {
				frappe.msgprint({
					title: __("PosAPI Info"),
					message: `<pre>${frappe.utils.escape_html(JSON.stringify(r.message, null, 2))}</pre>`,
				});
			});
		});
	},
});
