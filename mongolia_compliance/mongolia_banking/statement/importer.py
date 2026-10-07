"""Import a Mongolian bank statement into Bank Transactions and reconcile what clearly matches."""

import datetime
import re

import frappe
from frappe import _
from frappe.utils import add_days, cint, flt

from mongolia_compliance.mongolia_banking.statement.matcher import (
	AUTO_MATCH_SCORE,
	DATE_WINDOW_DAYS,
	Candidate,
	best_match,
)
from mongolia_compliance.mongolia_banking.statement.parser import StatementLine, parse_rows, read_rows

BACKGROUND_THRESHOLD = 100
UPLOAD = "Mongolia Bank Statement Upload"


def get_matching_settings() -> frappe._dict:
	settings = frappe.get_cached_doc("Mongolia Banking Settings")
	return frappe._dict(
		threshold=cint(settings.match_threshold) or AUTO_MATCH_SCORE,
		window=cint(settings.date_window_days) or DATE_WINDOW_DAYS,
	)


def read_statement(upload) -> list[StatementLine]:
	file_doc = frappe.get_doc("File", {"file_url": upload.statement_file})
	content = file_doc.get_content()
	if isinstance(content, str):
		content = content.encode()
	profile = frappe.get_doc("Mongolia Bank Statement Format", upload.statement_format).as_profile()
	return parse_rows(read_rows(content, file_doc.file_name or upload.statement_file), profile)


def import_statement(upload_name: str):
	upload = frappe.get_doc(UPLOAD, upload_name)
	try:
		_import(upload)
	except Exception as e:
		frappe.db.rollback()
		upload.reload()
		upload.db_set({"status": "Failed", "import_log": frappe.as_json([{"error": str(e)}])})
		frappe.log_error("Bank statement import", reference_doctype=UPLOAD, reference_name=upload_name)
		if not frappe.flags.in_background_job:
			raise


def _import(upload):
	lines = read_statement(upload)
	bank_account = frappe.get_cached_doc("Bank Account", upload.bank_account)
	gl_account = bank_account.account
	currency = frappe.get_cached_value("Account", gl_account, "account_currency") if gl_account else None
	settings = get_matching_settings()

	log, counts = [], frappe._dict(imported=0, duplicate=0, matched=0, created=0, unmatched=0)
	for line in lines:
		entry = {
			"row": line.row_no,
			"date": line.date.isoformat(),
			"deposit": line.deposit,
			"withdrawal": line.withdrawal,
			"description": line.description[:140],
		}
		key = line.key(upload.bank_account)
		existing = frappe.db.get_value(
			"Bank Transaction",
			{"bank_account": upload.bank_account, "transaction_id": key, "docstatus": ("!=", 2)},
		)
		if existing:
			counts.duplicate += 1
			entry.update(result="duplicate", transaction=existing)
			log.append(entry)
			continue

		frappe.db.savepoint("mn_statement_line")
		try:
			transaction = create_bank_transaction(upload, bank_account, line, key, currency)
			counts.imported += 1
			entry["transaction"] = transaction.name
			if upload.auto_match and gl_account:
				result = reconcile_line(
					transaction, line, gl_account, settings, cint(upload.create_payment_entries)
				)
				entry.update(result)
				if result.get("result") == "matched":
					counts.matched += 1
				elif result.get("result") == "created":
					counts.matched += 1
					counts.created += 1
				else:
					counts.unmatched += 1
			else:
				counts.unmatched += 1
		except Exception as e:
			frappe.db.rollback(save_point="mn_statement_line")
			entry.update(result="error", error=str(e)[:500])
			frappe.clear_last_message()
		log.append(entry)

	dates = [line.date for line in lines]
	upload.db_set(
		{
			"status": "Completed",
			"total_lines": len(lines),
			"imported_count": counts.imported,
			"duplicate_count": counts.duplicate,
			"matched_count": counts.matched,
			"created_payment_count": counts.created,
			"unmatched_count": counts.unmatched,
			"from_date": min(dates) if dates else None,
			"to_date": max(dates) if dates else None,
			"import_log": frappe.as_json(log),
		}
	)
	frappe.db.commit()
	return counts


def create_bank_transaction(upload, bank_account, line: StatementLine, key: str, currency: str | None):
	party_type, party = find_party_by_account(line.party_account)
	transaction = frappe.get_doc(
		{
			"doctype": "Bank Transaction",
			"date": line.date,
			"bank_account": upload.bank_account,
			"company": bank_account.company,
			"currency": currency,
			"deposit": line.deposit,
			"withdrawal": line.withdrawal,
			"description": line.description,
			"reference_number": line.reference or None,
			"transaction_id": key,
			"bank_party_name": line.party_name or None,
			"bank_party_account_number": line.party_account or None,
			"party_type": party_type,
			"party": party,
		}
	)
	transaction.insert()
	transaction.submit()
	return transaction


def find_party_by_account(account_no: str) -> tuple[str | None, str | None]:
	if not account_no:
		return None, None
	row = frappe.db.get_value(
		"Bank Account",
		{"bank_account_no": account_no, "is_company_account": 0, "party": ("is", "set")},
		["party_type", "party"],
		as_dict=True,
	)
	return (row.party_type, row.party) if row else (None, None)


# --- matching ---------------------------------------------------------------------------------


def party_details(party_type: str | None, party: str | None) -> tuple[str, list[str]]:
	if not party_type or not party:
		return "", []
	name_field = {"Customer": "customer_name", "Supplier": "supplier_name", "Employee": "employee_name"}.get(
		party_type
	)
	name = frappe.db.get_value(party_type, party, name_field) if name_field else party
	accounts = frappe.get_all(
		"Bank Account",
		filters={"party_type": party_type, "party": party, "is_company_account": 0},
		pluck="bank_account_no",
	)
	return name or party, [a for a in accounts if a]


def voucher_candidates(transaction, gl_account: str, window: int) -> list[Candidate]:
	from erpnext.accounts.doctype.bank_reconciliation_tool.bank_reconciliation_tool import (
		_get_linked_payments,
	)

	vouchers = _get_linked_payments(
		transaction.name,
		["payment_entry", "journal_entry", "exact_match"],
		from_date=add_days(transaction.date, -window),
		to_date=add_days(transaction.date, window),
	)
	candidates = []
	for voucher in vouchers:
		if flt(voucher.get("paid_amount")) <= 0:
			continue
		party_name, accounts = party_details(voucher.get("party_type"), voucher.get("party"))
		refs = []
		if voucher.get("doctype") == "Payment Entry":
			refs = frappe.get_all(
				"Payment Entry Reference", filters={"parent": voucher["name"]}, pluck="reference_name"
			)
		candidates.append(
			Candidate(
				doctype=voucher["doctype"],
				name=voucher["name"],
				amount=flt(voucher["paid_amount"]),
				posting_date=_date(voucher.get("posting_date")),
				reference_no=voucher.get("reference_no") or "",
				party=voucher.get("party") or "",
				party_name=party_name,
				party_accounts=accounts,
				extra_refs=refs,
			)
		)
	return candidates


DOC_TOKEN = re.compile(r"[0-9A-ZА-ЯЁӨҮ][0-9A-ZА-ЯЁӨҮ\-/.]{3,}")


def reference_tokens(text: str) -> list[str]:
	tokens = {t.strip("-/.") for t in DOC_TOKEN.findall((text or "").upper())}
	return [t for t in tokens if any(ch.isdigit() for ch in t)]


def invoice_candidates(transaction, line: StatementLine) -> list[Candidate]:
	if transaction.deposit:
		doctype, party_field, name_field, ref_field = "Sales Invoice", "customer", "customer_name", "po_no"
	else:
		doctype, party_field, name_field, ref_field = (
			"Purchase Invoice",
			"supplier",
			"supplier_name",
			"bill_no",
		)

	fields = ["name", "outstanding_amount", "posting_date", party_field, name_field, ref_field]
	common = {
		"docstatus": 1,
		"company": transaction.company,
		"currency": transaction.currency,
		"outstanding_amount": (">", 0),
	}
	rows = {}
	tokens = reference_tokens(f"{line.description} {line.reference}")
	if tokens:
		for field in ("name", ref_field):
			for row in frappe.get_all(doctype, filters={**common, field: ("in", tokens)}, fields=fields):
				rows[row.name] = row
	for row in frappe.get_all(
		doctype, filters={**common, "outstanding_amount": line.amount}, fields=fields, limit=50
	):
		rows[row.name] = row
	if transaction.party and transaction.party_type == ("Customer" if transaction.deposit else "Supplier"):
		for row in frappe.get_all(doctype, filters={**common, party_field: transaction.party}, fields=fields):
			rows[row.name] = row

	party_type = "Customer" if transaction.deposit else "Supplier"
	candidates = []
	for row in rows.values():
		_, accounts = party_details(party_type, row[party_field])
		candidates.append(
			Candidate(
				doctype=doctype,
				name=row.name,
				amount=flt(row.outstanding_amount),
				posting_date=None,  # invoice date says nothing about when it is paid
				party=row[party_field],
				party_name=row[name_field] or "",
				party_accounts=accounts,
				extra_refs=[row[ref_field]] if row.get(ref_field) else [],
			)
		)
	return candidates


def reconcile_line(transaction, line, gl_account: str, settings, create_payment_entries: bool) -> dict:
	from erpnext.accounts.doctype.bank_reconciliation_tool.bank_reconciliation_tool import (
		_reconcile_vouchers,
	)

	match = best_match(line, voucher_candidates(transaction, gl_account, settings.window), settings.threshold)
	if match:
		_reconcile_vouchers(
			transaction.name,
			[{"payment_doctype": match.doctype, "payment_name": match.name, "amount": match.amount}],
		)
		return _result("matched", match)

	if not create_payment_entries:
		return {"result": "unmatched"}

	match = best_match(line, invoice_candidates(transaction, line), settings.threshold)
	# never create a payment from the amount alone: the description or the payer's account must point at it
	if not match or not (
		{"утгад баримтын дугаар", "утгад холбоос дугаар", "харьцсан данс"} & set(match.reasons)
	):
		return {"result": "unmatched"}

	payment_entry = create_payment_entry(transaction, match, gl_account)
	_reconcile_vouchers(
		transaction.name,
		[{"payment_doctype": "Payment Entry", "payment_name": payment_entry.name, "amount": line.amount}],
		is_new_voucher=True,
	)
	result = _result("created", match)
	result["voucher"] = payment_entry.name
	result["invoice"] = match.name
	return result


def create_payment_entry(transaction, match: Candidate, gl_account: str):
	from erpnext.accounts.doctype.payment_entry.payment_entry import get_payment_entry

	amount = transaction.deposit or transaction.withdrawal
	pe = get_payment_entry(
		match.doctype,
		match.name,
		party_amount=amount,
		bank_account=gl_account,
		reference_date=transaction.date,
	)
	pe.posting_date = transaction.date
	pe.reference_date = transaction.date
	pe.reference_no = (transaction.reference_number or transaction.name)[:140]
	pe.bank_account = transaction.bank_account
	pe.remarks = _("Банкны хуулгаас: {0}").format(transaction.description or transaction.name)
	pe.insert()
	pe.submit()
	return pe


def _result(result: str, match: Candidate) -> dict:
	return {
		"result": result,
		"voucher_type": match.doctype,
		"voucher": match.name,
		"score": match.score,
		"reasons": match.reasons,
	}


def _date(value) -> datetime.date | None:
	if not value:
		return None
	if isinstance(value, datetime.datetime):
		return value.date()
	if isinstance(value, datetime.date):
		return value
	return frappe.utils.getdate(value)
