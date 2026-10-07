// Copyright (c) 2026, Anjaa and contributors
// For license information, please see license.txt

frappe.ui.form.on("Mongolia Gateway Invoice", {
	refresh(frm) {
		if (frm.doc.status === "Unpaid") {
			frm.add_custom_button(__("Төлөлт шалгах"), () =>
				frappe.call({
					method: "mongolia_compliance.mongolia_banking.payments.check_gateway_invoice",
					args: { name: frm.doc.name },
					freeze: true,
					callback: () => frm.reload_doc(),
				})
			);
			frm.add_custom_button(__("Цуцлах"), () =>
				frappe.confirm(__("Энэ QR нэхэмжлэхийг цуцлах уу?"), () =>
					frappe.call({
						method: "mongolia_compliance.mongolia_banking.payments.cancel_gateway_invoice",
						args: { name: frm.doc.name },
						freeze: true,
						callback: () => frm.reload_doc(),
					})
				)
			);
		}
		if (frm.doc.qr_image) {
			frm.dashboard.set_headline(
				`<img src="data:image/png;base64,${frm.doc.qr_image}" style="width:160px;height:160px">`
			);
		}
	},
});
