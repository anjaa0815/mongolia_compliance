const MN_CUSTOMS_DUTY_RATE = 5;

frappe.ui.form.on("Landed Cost Taxes and Charges", {
	mn_import_charge(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (!row.mn_import_charge || !frm.doc.company) return;

		frappe.call({
			method: "mongolia_compliance.mongolia_accounting.landed_cost.get_import_charge_account",
			args: { company: frm.doc.company, charge: row.mn_import_charge },
			callback(r) {
				if (r.message) {
					frappe.model.set_value(cdt, cdn, "expense_account", r.message);
				}
			},
		});
		frappe.model.set_value(cdt, cdn, "description", __(row.mn_import_charge));

		if (row.mn_import_charge === "Customs Duty" && !row.amount) {
			// suggestion only: the customs declaration decides the dutiable value
			const items_total = (frm.doc.items || []).reduce((sum, d) => sum + flt(d.amount), 0);
			if (items_total) {
				frappe.model.set_value(
					cdt,
					cdn,
					"amount",
					flt((items_total * MN_CUSTOMS_DUTY_RATE) / 100, precision("amount", row))
				);
			}
		}
	},
});
