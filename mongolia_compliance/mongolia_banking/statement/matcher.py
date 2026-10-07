"""Score how well a bank statement line matches an ERPNext voucher or open invoice.

Pure python. Mongolian payers usually write the invoice number, contract number or their company name
in "Гүйлгээний утга", so the description is the strongest signal next to the amount. A match is only
used when it is clearly better than the runner-up, so ambiguous lines stay for manual reconciliation.
"""

import datetime
import re
from dataclasses import dataclass, field

AUTO_MATCH_SCORE = 70
MIN_MARGIN = 15
DATE_WINDOW_DAYS = 5


@dataclass
class Candidate:
	doctype: str
	name: str
	amount: float  # paid amount for vouchers, outstanding amount for invoices
	posting_date: datetime.date | None = None
	reference_no: str = ""
	party: str = ""
	party_name: str = ""
	party_accounts: list[str] = field(default_factory=list)
	extra_refs: list[str] = field(default_factory=list)  # PO no, QPay invoice no, contract no
	score: int = 0
	reasons: list[str] = field(default_factory=list)


def compact(value) -> str:
	"""Upper-case letters and digits only: bank systems often drop dashes and spaces."""
	return re.sub(r"[^0-9A-ZА-ЯЁӨҮ]", "", str(value or "").upper())


def searchable(value) -> str:
	"""Drop separators inside numbers ("ACC-SINV-2026/00012" -> "ACCSINV202600012") but keep word gaps."""
	text = re.sub(r"[-/._]", "", str(value or "").upper())
	return re.sub(r"[^0-9A-ZА-ЯЁӨҮ]+", " ", text)


def contains_ref(description: str, reference: str) -> bool:
	ref = compact(reference)
	if len(ref) < 4:
		return False
	text = searchable(description)
	for match in re.finditer(re.escape(ref), text):
		# "SINV-2026-0001" must not match inside "SINV-2026-00012"
		end = match.end()
		if ref[-1].isdigit() and end < len(text) and text[end].isdigit():
			continue
		return True
	return False


def score(line, candidate: Candidate) -> Candidate:
	"""line: StatementLine (or anything with date, amount, description, reference, party_account, party_name)."""
	points, reasons = 0, []
	amount = round(float(line.amount), 2)
	cand_amount = round(float(candidate.amount or 0), 2)

	if cand_amount and abs(cand_amount - amount) < 0.01:
		points += 50
		reasons.append("дүн тэнцүү")
	elif cand_amount and amount < cand_amount and candidate.doctype in ("Sales Invoice", "Purchase Invoice"):
		points += 10
		reasons.append("хэсэгчилсэн төлөлт")
	else:
		# a voucher for a different amount is never this line
		candidate.score, candidate.reasons = 0, ["дүн зөрүүтэй"]
		return candidate

	text = " ".join(filter(None, [line.description, line.reference]))
	if contains_ref(text, candidate.name):
		points += 40
		reasons.append("утгад баримтын дугаар")
	elif any(contains_ref(text, ref) for ref in candidate.extra_refs if ref):
		points += 30
		reasons.append("утгад холбоос дугаар")

	if (
		candidate.reference_no
		and line.reference
		and compact(candidate.reference_no) == compact(line.reference)
	):
		points += 40
		reasons.append("гүйлгээний дугаар тэнцүү")
	elif candidate.reference_no and contains_ref(line.description, candidate.reference_no):
		points += 25
		reasons.append("утгад лавлах дугаар")

	if line.party_account and compact(line.party_account) in {compact(a) for a in candidate.party_accounts}:
		points += 30
		reasons.append("харьцсан данс")

	party_name = compact(candidate.party_name or candidate.party)
	if len(party_name) >= 4 and party_name in compact(f"{line.description} {line.party_name}"):
		points += 15
		reasons.append("харилцагчийн нэр")

	if candidate.posting_date and line.date:
		days = abs((line.date - candidate.posting_date).days)
		if days <= 1:
			points += 10
			reasons.append("огноо ойр")
		elif days <= DATE_WINDOW_DAYS:
			points += 5

	candidate.score, candidate.reasons = points, reasons
	return candidate


def best_match(line, candidates: list[Candidate], threshold: int = AUTO_MATCH_SCORE) -> Candidate | None:
	scored = sorted((score(line, c) for c in candidates), key=lambda c: c.score, reverse=True)
	if not scored or scored[0].score < threshold:
		return None
	if len(scored) > 1 and scored[0].score - scored[1].score < MIN_MARGIN:
		return None
	return scored[0]
