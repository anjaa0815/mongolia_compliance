// Copyright (c) 2026, Anjaa and contributors
// License: GNU General Public License v3. See license.txt

frappe.ui.form.on("Customer", {
	refresh(frm) {
		if (frappe.boot.sysdefaults.country !== "Mongolia" || !frm.fields_dict.ebarimt_tin) return;

		frm.add_custom_button(__("Look up Taxpayer"), () => erpnext_mongolia_lookup_taxpayer(frm));
	},
});

function erpnext_mongolia_lookup_taxpayer(frm) {
	if (!frm.doc.tax_id) {
		frappe.msgprint(__("Enter the registration number in Tax ID first."));
		return;
	}

	frappe
		.call({
			method: "mongolia_compliance.e_barimt.ebarimt.get_taxpayer_info",
			args: { reg_no: frm.doc.tax_id },
			freeze: true,
		})
		.then(({ message: info }) => {
			if (!info) return;

			frm.set_value("ebarimt_tin", info.tin);
			frm.set_value("ebarimt_vat_payer", info.vat_payer);
			if (info.name && frm.doc.customer_name !== info.name) {
				frappe.confirm(
					__("Registered name is {0}. Use it as the customer name?", [
						frappe.utils.escape_html(info.name).bold(),
					]),
					() => frm.set_value("customer_name", info.name)
				);
			}
		});
}
