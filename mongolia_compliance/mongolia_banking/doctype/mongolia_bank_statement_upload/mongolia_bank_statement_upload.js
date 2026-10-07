// Copyright (c) 2026, Anjaa and contributors
// For license information, please see license.txt

frappe.ui.form.on("Mongolia Bank Statement Upload", {
	setup(frm) {
		frm.set_query("bank_account", () => ({ filters: { is_company_account: 1 } }));
	},

	bank_account(frm) {
		if (!frm.doc.bank_account) return;
		frappe.call({
			method: "mongolia_compliance.mongolia_banking.doctype.mongolia_bank_statement_upload.mongolia_bank_statement_upload.get_default_format",
			args: { bank_account: frm.doc.bank_account },
			callback: (r) => r.message && frm.set_value("statement_format", r.message),
		});
	},

	refresh(frm) {
		if (frm.is_new() || frm.is_dirty()) return;

		if (["Draft", "Failed"].includes(frm.doc.status)) {
			frm.add_custom_button(__("Урьдчилан харах"), () =>
				frm.call("preview").then((r) => show_preview(r.message || []))
			);
			frm.add_custom_button(__("Импортлох"), () =>
				frm.call({ method: "start_import", doc: frm.doc, freeze: true }).then((r) => {
					if (r.message) frappe.show_alert({ message: r.message, indicator: "blue" });
					frm.reload_doc();
				})
			).addClass("btn-primary");
		}

		if (frm.doc.status === "Completed") {
			frm.add_custom_button(__("Банкны тулгалт"), () => {
				frappe.route_options = {
					company: frm.doc.company,
					bank_account: frm.doc.bank_account,
					bank_statement_from_date: frm.doc.from_date,
					bank_statement_to_date: frm.doc.to_date,
				};
				frappe.set_route("Form", "Bank Reconciliation Tool");
			});
			frm.add_custom_button(__("Банкны гүйлгээнүүд"), () =>
				frappe.set_route("List", "Bank Transaction", {
					bank_account: frm.doc.bank_account,
					date: ["between", [frm.doc.from_date, frm.doc.to_date]],
				})
			);
			frm.dashboard.add_indicator(__("Тулгагдсан: {0}", [frm.doc.matched_count]), "green");
			frm.dashboard.add_indicator(__("Тулгагдаагүй: {0}", [frm.doc.unmatched_count]), "orange");
		}
	},
});

function show_preview(rows) {
	const fmt = (v) => (v ? format_currency(v, "MNT") : "");
	const body = rows
		.map((r) =>
			r.more
				? `<tr><td colspan="5">${__("... дахиад {0} мөр", [r.more])}</td></tr>`
				: `<tr><td>${r.date}</td><td>${frappe.utils.escape_html(r.description || "")}</td>
				<td class="text-right">${fmt(r.deposit)}</td><td class="text-right">${fmt(r.withdrawal)}</td>
				<td>${frappe.utils.escape_html(r.party_account || "")}</td></tr>`
		)
		.join("");
	frappe.msgprint({
		title: __("Хуулгын урьдчилсан харагдац"),
		wide: true,
		message: `<table class="table table-bordered table-sm">
			<thead><tr><th>${__("Огноо")}</th><th>${__("Гүйлгээний утга")}</th><th>${__("Орлого")}</th>
			<th>${__("Зарлага")}</th><th>${__("Харьцсан данс")}</th></tr></thead><tbody>${body}</tbody></table>`,
	});
}
