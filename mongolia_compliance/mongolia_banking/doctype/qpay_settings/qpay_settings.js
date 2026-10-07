// Copyright (c) 2026, Anjaa and contributors
// For license information, please see license.txt

frappe.ui.form.on("QPay Settings", {
	setup(frm) {
		frm.set_query("payment_account", () => ({
			filters: { company: frm.doc.company, is_group: 0, account_type: ["in", ["Bank", "Cash"]] },
		}));
	},
	refresh(frm) {
		if (!frm.is_new()) {
			frm.add_custom_button(__("Холболт шалгах"), () =>
				frappe.call({
					method: "mongolia_compliance.mongolia_banking.doctype.qpay_settings.qpay_settings.test_connection",
					args: { company: frm.doc.company },
					freeze: true,
					callback: (r) => frappe.show_alert({ message: r.message, indicator: "green" }),
				})
			);
		}
	},
});
