"""Built-in statement layouts for Mongolian internet banking exports.

Pure python (no frappe import) so the parser can be unit tested without a bench. On install every
profile becomes a "Mongolia Bank Statement Format" record that users can edit when a bank changes its
export. Column names are matched case-insensitively after collapsing spaces, so only the wording matters.

The bank-specific header names below are taken from typical corporate internet bank exports. They have
not been checked against every export variant, which is why each profile also falls back to the common
aliases in GENERIC.
"""

# Fields a statement line can carry, and the column names that usually hold them.
GENERIC = {
	"date_columns": [
		"Гүйлгээний огноо",
		"Огноо",
		"Гүйлгээ хийсэн огноо",
		"Бүртгэсэн огноо",
		"Transaction date",
		"Posting date",
		"Date",
	],
	"description_columns": [
		"Гүйлгээний утга",
		"Утга",
		"Гүйлгээний тайлбар",
		"Тайлбар",
		"Description",
		"Narrative",
		"Details",
	],
	"deposit_columns": [
		"Орлого",
		"Кредит",
		"Кредит гүйлгээ",
		"Кт",
		"Орсон",
		"Credit",
		"Deposit",
	],
	"withdrawal_columns": [
		"Зарлага",
		"Дебит",
		"Дебит гүйлгээ",
		"Дт",
		"Гарсан",
		"Debit",
		"Withdrawal",
	],
	"amount_columns": ["Гүйлгээний дүн", "Дүн", "Amount"],
	"direction_columns": ["Гүйлгээний төрөл", "Төрөл", "Дт/Кт", "Type", "Dr/Cr"],
	"account_columns": [
		"Харьцсан данс",
		"Харилцсан данс",
		"Харилцагч данс",
		"Харилцагчийн данс",
		"Харьцагч данс",
		"Хүлээн авагчийн данс",
		"Илгээгчийн данс",
		"Данс",
		"Counterparty account",
		"Account",
	],
	"party_name_columns": [
		"Харьцсан дансны нэр",
		"Харилцагчийн нэр",
		"Харьцагчийн нэр",
		"Хүлээн авагч",
		"Илгээгч",
		"Counterparty name",
		"Counterparty",
	],
	"reference_columns": [
		"Гүйлгээний дугаар",
		"Гүйлгээний код",
		"Журналын дугаар",
		"Лавлах дугаар",
		"Reference",
		"Transaction ID",
	],
	"balance_columns": ["Эцсийн үлдэгдэл", "Үлдэгдэл", "Balance", "Closing balance"],
	"date_formats": [
		"%Y-%m-%d",
		"%Y.%m.%d",
		"%Y/%m/%d",
		"%Y-%m-%d %H:%M:%S",
		"%Y-%m-%d %H:%M",
		"%Y.%m.%d %H:%M:%S",
		"%Y.%m.%d %H:%M",
		"%Y/%m/%d %H:%M:%S",
		"%d.%m.%Y",
		"%d/%m/%Y",
		"%d.%m.%Y %H:%M:%S",
		"%m/%d/%Y",
	],
	# Values of the direction column that mean money came in.
	"deposit_markers": ["кт", "кредит", "орлого", "cr", "credit", "c", "+"],
	"decimal_separator": ".",
}

STATEMENT_FORMATS = [
	{
		"format_name": "Хаан банк",
		"bank": "Хаан банк",
		"date_columns": ["Гүйлгээний огноо", "Огноо"],
		"description_columns": ["Гүйлгээний утга"],
		"deposit_columns": ["Орлого", "Кредит гүйлгээ"],
		"withdrawal_columns": ["Зарлага", "Дебит гүйлгээ"],
		"account_columns": ["Харьцсан данс"],
		"party_name_columns": ["Харьцсан дансны нэр"],
		"balance_columns": ["Эцсийн үлдэгдэл"],
	},
	{
		"format_name": "Голомт банк",
		"bank": "Голомт банк",
		"date_columns": ["Гүйлгээний огноо", "Огноо"],
		"description_columns": ["Гүйлгээний утга", "Утга"],
		"deposit_columns": ["Кредит", "Орлого"],
		"withdrawal_columns": ["Дебит", "Зарлага"],
		"account_columns": ["Харилцсан данс", "Харьцсан данс"],
		"reference_columns": ["Гүйлгээний дугаар"],
		"balance_columns": ["Үлдэгдэл"],
	},
	{
		"format_name": "Худалдаа хөгжлийн банк",
		"bank": "Худалдаа хөгжлийн банк",
		"date_columns": ["Огноо", "Гүйлгээний огноо"],
		"description_columns": ["Гүйлгээний утга", "Тайлбар"],
		"deposit_columns": ["Кредит", "Орлого"],
		"withdrawal_columns": ["Дебит", "Зарлага"],
		"account_columns": ["Харилцагч данс", "Харьцсан данс"],
		"reference_columns": ["Журналын дугаар", "Гүйлгээний дугаар"],
		"balance_columns": ["Үлдэгдэл"],
	},
	{
		"format_name": "Хас банк",
		"bank": "Хас банк",
		"date_columns": ["Гүйлгээний огноо", "Огноо"],
		"description_columns": ["Гүйлгээний утга", "Утга"],
		"deposit_columns": ["Орлого", "Кредит"],
		"withdrawal_columns": ["Зарлага", "Дебит"],
		"account_columns": ["Харьцсан данс", "Харилцагчийн данс"],
		"party_name_columns": ["Харилцагчийн нэр"],
		"balance_columns": ["Үлдэгдэл"],
	},
	{
		"format_name": "Ерөнхий (бусад банк)",
		"bank": None,
	},
]

PROFILE_FIELDS = [
	"date_columns",
	"description_columns",
	"deposit_columns",
	"withdrawal_columns",
	"amount_columns",
	"direction_columns",
	"account_columns",
	"party_name_columns",
	"reference_columns",
	"balance_columns",
	"date_formats",
	"deposit_markers",
]


def build_profile(overrides: dict | None = None) -> dict:
	"""Bank-specific names first, then the generic aliases, without duplicates."""
	overrides = overrides or {}
	profile = {}
	for field in PROFILE_FIELDS:
		merged = []
		for name in [*(overrides.get(field) or []), *GENERIC[field]]:
			if name and name not in merged:
				merged.append(name)
		profile[field] = merged
	profile["decimal_separator"] = overrides.get("decimal_separator") or GENERIC["decimal_separator"]
	return profile
