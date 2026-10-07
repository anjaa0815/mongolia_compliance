// Copyright (c) 2026, Anjaa and contributors
// For license information, please see license.txt

// "QPay-ээр төлүүлэх" on submitted Sales Invoices and Sales Orders: shows the QR code and bank-app links,
// and waits for the payment. The Payment Entry is created on the server once QPay confirms it.

const MN_POLL_MS = 4000;
const MN_POLL_LIMIT_MS = 10 * 60 * 1000;

function mn_amount_due(frm) {
	if (frm.doc.doctype === "Sales Invoice") return flt(frm.doc.outstanding_amount);
	return flt(frm.doc.rounded_total || frm.doc.grand_total) - flt(frm.doc.advance_paid);
}

function mn_add_gateway_button(frm) {
	if (frm.doc.docstatus !== 1 || frm.doc.currency !== "MNT" || mn_amount_due(frm) <= 0) return;
	if (frm.doc.doctype === "Sales Invoice" && frm.doc.is_return) return;
	if (!frappe.model.can_create("Payment Entry")) return;

	frm.add_custom_button(
		__("QPay-ээр төлүүлэх"),
		() => {
			frappe.call({
				method: "mongolia_compliance.mongolia_banking.payments.create_gateway_invoice",
				args: { reference_doctype: frm.doc.doctype, reference_name: frm.doc.name, gateway: "QPay" },
				freeze: true,
				freeze_message: __("QPay нэхэмжлэх үүсгэж байна..."),
				callback: (r) => r.message && mn_show_qr_dialog(frm, r.message),
			});
		},
		__("Create")
	);
}

function mn_show_qr_dialog(frm, invoice) {
	const links = (invoice.deeplinks || [])
		.filter((l) => l.link && !/^\s*(javascript|data):/i.test(l.link))
		.map(
			(l) => `<a href="${encodeURI(
				l.link
			)}" target="_blank" rel="noopener" title="${frappe.utils.escape_html(
				l.description || l.name
			)}" style="display:inline-block;margin:4px;text-align:center;width:64px">
				<img src="${encodeURI(l.logo)}" style="width:40px;height:40px;border-radius:8px"><br>
				<small>${frappe.utils.escape_html(l.description || l.name || "")}</small></a>`
		)
		.join("");

	const dialog = new frappe.ui.Dialog({
		title: __("QPay төлбөр: {0}", [format_currency(invoice.amount, invoice.currency)]),
		fields: [{ fieldtype: "HTML", fieldname: "qr" }],
		primary_action_label: __("Төлөлт шалгах"),
		primary_action: () => check(true),
		secondary_action_label: __("Цуцлах"),
		secondary_action: () =>
			frappe.call({
				method: "mongolia_compliance.mongolia_banking.payments.cancel_gateway_invoice",
				args: { name: invoice.name },
				callback: () => dialog.hide(),
			}),
	});

	dialog.fields_dict.qr.$wrapper.html(`
		<div class="text-center">
			<img src="data:image/png;base64,${invoice.qr_image}" style="width:240px;height:240px">
			<p class="text-muted">${__("Банкны аппликэйшнээр QR кодыг уншуулж төлнө үү")}</p>
			${
				invoice.short_url
					? `<p><a href="${encodeURI(
							invoice.short_url
					  )}" target="_blank" rel="noopener">${frappe.utils.escape_html(
							invoice.short_url
					  )}</a></p>`
					: ""
			}
			<div>${links}</div>
			<p class="mn-qpay-status text-muted" style="margin-top:8px">${__("Төлбөр хүлээж байна...")}</p>
		</div>`);

	const started = Date.now();
	let timer = null;

	const check = (manual) => {
		frappe.call({
			method: "mongolia_compliance.mongolia_banking.payments.check_gateway_invoice",
			args: { name: invoice.name },
			callback: (r) => {
				const status = r.message && r.message.status;
				if (status === "Paid") {
					clearInterval(timer);
					dialog.hide();
					frappe.show_alert({ message: __("Төлбөр орлоо"), indicator: "green" });
					frm.reload_doc();
				} else if (manual) {
					frappe.show_alert({ message: __("Төлбөр хараахан ороогүй байна"), indicator: "orange" });
				}
			},
		});
	};

	timer = setInterval(() => {
		if (!dialog.display || Date.now() - started > MN_POLL_LIMIT_MS) {
			clearInterval(timer);
			return;
		}
		check(false);
	}, MN_POLL_MS);
	dialog.onhide = () => clearInterval(timer);
	dialog.show();
}

frappe.ui.form.on("Sales Invoice", { refresh: mn_add_gateway_button });
frappe.ui.form.on("Sales Order", { refresh: mn_add_gateway_button });
