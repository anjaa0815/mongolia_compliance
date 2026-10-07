"""Pure-python tests: `python -m pytest mongolia_compliance/mongolia_banking/tests` from the repo root (no bench needed)."""

import datetime
import io
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from mongolia_compliance.mongolia_banking.statement.matcher import Candidate, best_match, contains_ref, score
from mongolia_compliance.mongolia_banking.statement.parser import (
	StatementParseError,
	parse_amount,
	parse_date,
	parse_rows,
	read_csv,
	read_rows,
)
from mongolia_compliance.mongolia_banking.statement.profiles import GENERIC, STATEMENT_FORMATS, build_profile


def profile(bank):
	return build_profile(next(p for p in STATEMENT_FORMATS if p["format_name"] == bank))


KHAN_ROWS = [
	["ХУУЛГА"],
	["Данс:", "5012345678", None, None],
	["Хугацаа:", "2026.10.01 - 2026.10.07"],
	[],
	[
		"Гүйлгээний огноо",
		"Салбар",
		"Эхний үлдэгдэл",
		"Орлого",
		"Зарлага",
		"Эцсийн үлдэгдэл",
		"Гүйлгээний утга",
		"Харьцсан данс",
	],
	[
		datetime.datetime(2026, 10, 1, 9, 30),
		"Төв",
		1000000,
		1500000,
		0,
		2500000,
		"ACC-SINV-2026-00012 төлбөр",
		5098765432.0,
	],
	["2026.10.02 14:05", "Төв", 2500000, "", "300,000.00", 2200000, "Түрээс 10 сар", "4011223344"],
	[None, None, None, "1,500,000.00", "300,000.00", None, "Нийт дүн", None],
]


def test_khan_layout_with_title_rows_and_totals():
	lines = parse_rows(KHAN_ROWS, profile("Хаан банк"))
	assert len(lines) == 2  # totals row has no date
	first, second = lines
	assert first.date == datetime.date(2026, 10, 1)
	assert first.deposit == 1500000 and first.withdrawal == 0
	assert first.party_account == "5098765432"  # Excel float turned back into an account number
	assert first.description == "ACC-SINV-2026-00012 төлбөр"
	assert first.balance == 2500000
	assert second.date == datetime.date(2026, 10, 2)
	assert second.withdrawal == 300000 and second.deposit == 0
	assert first.row_no == 6


def test_golomt_csv_semicolon_signed_amount_and_direction():
	csv_text = (
		"Огноо;Гүйлгээний утга;Дүн;Төрөл;Харилцсан данс;Гүйлгээний дугаар\n"
		"2026-10-03;ACC-SINV-2026-00015;250 000,00;Кт;1105012345;GL123\n"
		"2026-10-03;Цалин;1 000 000,00;Дт;;GL124\n"
	)
	rows = read_csv(csv_text.encode("utf-8-sig"))
	fmt = dict(next(p for p in STATEMENT_FORMATS if p["format_name"] == "Голомт банк"))
	fmt["decimal_separator"] = ","
	lines = parse_rows(rows, build_profile(fmt))
	assert [(line.deposit, line.withdrawal) for line in lines] == [(250000.0, 0.0), (0.0, 1000000.0)]
	assert lines[0].reference == "GL123"


def test_signed_amount_without_direction_column():
	rows = [
		["Date", "Description", "Amount"],
		["2026-10-05", "fee", "-1,200.50"],
		["2026-10-05", "in", "800"],
	]
	lines = parse_rows(rows)
	assert (lines[0].deposit, lines[0].withdrawal) == (0.0, 1200.5)
	assert (lines[1].deposit, lines[1].withdrawal) == (800.0, 0.0)


def test_missing_header_is_explained():
	with pytest.raises(StatementParseError):
		parse_rows([["foo", "bar"], ["1", "2"]])


def test_xlsx_roundtrip():
	from openpyxl import Workbook

	wb = Workbook()
	ws = wb.active
	for row in KHAN_ROWS:
		ws.append(row)
	buf = io.BytesIO()
	wb.save(buf)
	lines = parse_rows(read_rows(buf.getvalue(), "khan.xlsx"), profile("Хаан банк"))
	assert len(lines) == 2 and lines[0].deposit == 1500000


def test_cp1251_csv():
	# cp1251 lacks the Mongolian-only letters, so only headers without them can come from such legacy exports
	text = "Огноо,Тайлбар,Орлого,Зарлага\n2026-10-01,Тест,100,\n"
	lines = parse_rows(read_csv(text.encode("cp1251")))
	assert lines[0].description == "Тест"


@pytest.mark.parametrize(
	"value,expected",
	[
		("1,234,567.89", 1234567.89),
		("1 234 567.89", 1234567.89),
		("(500.00)", -500.0),
		("500-", -500.0),
		("₮ 12,000", 12000.0),
		("1500,5", 1500.5),
		("", None),
		("-", None),
		(42, 42.0),
	],
)
def test_parse_amount(value, expected):
	assert parse_amount(value) == expected


def test_parse_amount_decimal_comma():
	assert parse_amount("1.234.567,89", ",") == 1234567.89


@pytest.mark.parametrize(
	"value,expected",
	[
		("2026-10-07", datetime.date(2026, 10, 7)),
		("2026.10.07", datetime.date(2026, 10, 7)),
		("2026/10/07 13:45:00", datetime.date(2026, 10, 7)),
		("07.10.2026", datetime.date(2026, 10, 7)),
		("2026-10-07T08:00:00.123", datetime.date(2026, 10, 7)),
		(46302, datetime.date(2026, 10, 7)),  # Excel serial
		("Нийт", None),
	],
)
def test_parse_date(value, expected):
	assert parse_date(value, GENERIC["date_formats"]) == expected


def test_duplicate_key_is_stable_and_distinct():
	lines = parse_rows(KHAN_ROWS, profile("Хаан банк"))
	assert lines[0].key("BA-1") == parse_rows(KHAN_ROWS, profile("Хаан банк"))[0].key("BA-1")
	assert lines[0].key("BA-1") != lines[1].key("BA-1")
	assert lines[0].key("BA-1") != lines[0].key("BA-2")


def test_every_builtin_profile_has_amount_columns():
	for fmt in STATEMENT_FORMATS:
		p = build_profile(fmt)
		assert p["date_columns"] and p["deposit_columns"] and p["withdrawal_columns"]


# --- matching -----------------------------------------------------------------------------------


def line(amount=1500000, description="", party_account="", reference="", date=datetime.date(2026, 10, 1)):
	from mongolia_compliance.mongolia_banking.statement.parser import StatementLine

	return StatementLine(
		row_no=1,
		date=date,
		description=description,
		deposit=amount,
		party_account=party_account,
		reference=reference,
	)


def test_contains_ref_handles_stripped_dashes_and_longer_numbers():
	assert contains_ref("ACCSINV202600012 tulbur", "ACC-SINV-2026-00012")
	assert not contains_ref("ACC-SINV-2026-000123", "ACC-SINV-2026-00012")
	assert not contains_ref("abc", "12")


def test_invoice_number_in_description_wins():
	cands = [
		Candidate("Sales Invoice", "ACC-SINV-2026-00012", 1500000, party="Номин ХХК"),
		Candidate("Sales Invoice", "ACC-SINV-2026-00013", 1500000, party="Говь ХК"),
	]
	match = best_match(line(description="ACC-SINV-2026-00012 төлбөр"), cands)
	assert match.name == "ACC-SINV-2026-00012"


def test_amount_alone_is_not_enough():
	cands = [Candidate("Payment Entry", "PE-1", 1500000, posting_date=datetime.date(2026, 10, 1))]
	assert best_match(line(description="төлбөр"), cands) is None


def test_two_equal_candidates_are_ambiguous():
	cands = [
		Candidate("Payment Entry", "PE-1", 1500000, party_accounts=["5098765432"]),
		Candidate("Payment Entry", "PE-2", 1500000, party_accounts=["5098765432"]),
	]
	assert best_match(line(party_account="5098765432"), cands) is None


def test_party_account_and_reference_match():
	cand = Candidate("Payment Entry", "PE-1", 1500000, reference_no="GL123", party_accounts=["5098765432"])
	scored = score(line(party_account="5098765432", reference="GL123"), cand)
	assert scored.score >= 120


def test_wrong_amount_scores_zero():
	cand = Candidate("Payment Entry", "PE-1", 1400000)
	assert score(line(description="PE-1"), cand).score == 0


def test_partial_payment_of_invoice():
	cand = Candidate("Sales Invoice", "ACC-SINV-2026-00012", 3000000, party_accounts=["5098765432"])
	assert best_match(line(description="ACC-SINV-2026-00012 1-р хэсэг"), [cand]) is None
	match = best_match(line(description="ACC-SINV-2026-00012 1-р хэсэг", party_account="5098765432"), [cand])
	assert match is not None and "хэсэгчилсэн төлөлт" in match.reasons


def test_payment_entry_found_through_its_invoice_reference():
	cand = Candidate("Payment Entry", "ACC-PAY-2026-00001", 1500000, extra_refs=["ACC-SINV-2026-00012"])
	match = best_match(line(description="SINV 2026 00012"), [cand])
	assert match is None  # "SINV202600012" is only part of the invoice number
	match = best_match(line(description="ACC-SINV-2026-00012"), [cand])
	assert match.name == "ACC-PAY-2026-00001"
