import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

from .calculator import default_pit_credit_slabs, default_pit_slabs

SETTINGS = "Mongolia Payroll Settings"
RISK_CLASS = "Mongolia NDSH Risk Class"

# ҮОМШӨ-ийн ажил олгогчийн хувь, эрсдэлийн зэргээр. Нийт ажил олгогчийн НДШ 12.5% - 14.5%.
RISK_CLASSES = [
	("I зэрэг", 0.5, "Эрсдэл багатай салбар (нийт 12.5%)"),
	("II зэрэг", 1.5, "Дунд эрсдэлтэй салбар (нийт 13.5%)"),
	("III зэрэг", 2.5, "Эрсдэл өндөртэй салбар (нийт 14.5%)"),
]

EMPLOYER_CONTRIBUTION = "Employer Contribution"

# (name, abbr, type, formula, condition, depends_on_payment_days, description)
COMPONENTS = [
	("Үндсэн цалин", "B", "Earning", "base", "", 1, "Хөдөлмөрийн гэрээгээр тогтоосон үндсэн цалин"),
	(
		"Илүү цагийн хөлс",
		"OT",
		"Earning",
		"mn_overtime_pay(base, start_date, mn_overtime_hours, employee, company)",
		"mn_overtime_hours",
		0,
		"Хөдөлмөрийн тухай хууль: цагийн цалинг 1.5-аар үржүүлнэ. Цагийг цалингийн хуудасны 'Илүү цаг' талбарт оруулна.",
	),
	(
		"Баярын өдрийн ажлын хөлс",
		"HOL",
		"Earning",
		"mn_holiday_pay(base, start_date, mn_holiday_hours, employee, company)",
		"mn_holiday_hours",
		0,
		"Нийтээр амрах баярын өдөр ажилласан цагийг 2.0-оор үржүүлнэ.",
	),
	(
		"Ээлжийн амралтын олговор",
		"VAC",
		"Earning",
		"mn_vacation_pay(employee, mn_vacation_days, start_date, base)",
		"mn_vacation_days",
		0,
		"Өмнөх 12 сарын дундаж өдрийн цалин x амралтын өдөр.",
	),
	(
		"НДШ (ажилтан)",
		"NDSH",
		"Deduction",
		"mn_ndsh_employee(gross_pay)",
		"",
		0,
		"Даатгуулагчийн шимтгэл 11.5% (тэтгэвэр 8.5, тэтгэмж 0.8, ажилгүйдэл 0.2, ЭМД 2.0), дээд хязгаартай.",
	),
	(
		"ХХОАТ",
		"PIT",
		"Deduction",
		"mn_pit(gross_pay, NDSH)",
		"",
		0,
		"(Цалин - НДШ) шатласан хувиар, сар бүрийн хөнгөлөлтийг хассан.",
	),
	(
		"НДШ (ажил олгогч)",
		"NDSH_ER",
		EMPLOYER_CONTRIBUTION,
		"mn_ndsh_employer(gross_pay, company)",
		"",
		0,
		"Ажил олгогчийн шимтгэл 12.5%-14.5%, компанийн эрсдэлийн зэргээс хамаарна.",
	),
]


def setup():
	"""Called from mongolia_compliance.install.after_migrate (idempotent)."""
	make_custom_fields()
	make_risk_classes()
	make_settings()
	make_salary_components()


def make_custom_fields():
	create_custom_fields(
		{
			"Company": [
				dict(
					fieldname="mn_ndsh_risk_class",
					label="НДШ эрсдэлийн зэрэг",
					fieldtype="Link",
					options=RISK_CLASS,
					insert_after="tax_id",
				),
				dict(
					fieldname="mn_ndsh_employer_no",
					label="НД-ын ажил олгогчийн дугаар",
					fieldtype="Data",
					insert_after="mn_ndsh_risk_class",
				),
			],
			"Employee": [
				dict(
					fieldname="mn_register_no",
					label="Регистрийн дугаар",
					fieldtype="Data",
					insert_after="last_name",
				),
				dict(
					fieldname="mn_insured_type",
					label="Даатгуулагчийн төрөл (код)",
					fieldtype="Data",
					default="01",
					insert_after="mn_register_no",
				),
				dict(
					fieldname="mn_occupation_code",
					label="Ажил мэргэжлийн код (ҮАМАТ)",
					fieldtype="Data",
					insert_after="mn_insured_type",
				),
			],
			"Salary Slip": [
				dict(
					fieldname="mn_section",
					label="Илүү цаг, баяр, амралт",
					fieldtype="Section Break",
					insert_after="payment_days",
					collapsible=1,
				),
				dict(
					fieldname="mn_overtime_hours",
					label="Илүү цаг (цаг)",
					fieldtype="Float",
					insert_after="mn_section",
				),
				dict(
					fieldname="mn_holiday_hours",
					label="Баярын өдөр ажилласан цаг",
					fieldtype="Float",
					insert_after="mn_overtime_hours",
				),
				dict(
					fieldname="mn_column",
					fieldtype="Column Break",
					insert_after="mn_holiday_hours",
				),
				dict(
					fieldname="mn_vacation_days",
					label="Ээлжийн амралтын өдөр",
					fieldtype="Float",
					insert_after="mn_column",
				),
			],
		},
		update=True,
	)


def make_risk_classes():
	for risk_class, rate, description in RISK_CLASSES:
		if not frappe.db.exists(RISK_CLASS, risk_class):
			frappe.get_doc(
				doctype=RISK_CLASS, risk_class=risk_class, accident_rate=rate, description=description
			).insert(ignore_permissions=True)


def make_settings():
	settings = frappe.get_single(SETTINGS)
	if settings.pit_slabs or settings.pit_credit_slabs:
		return  # already configured; never overwrite the user's rates

	for field in settings.meta.fields:
		if field.default and settings.get(field.fieldname) in (None, "", 0):
			settings.set(field.fieldname, field.default)
	settings.default_risk_class = RISK_CLASSES[0][0]
	for slab in default_pit_slabs():
		settings.append(
			"pit_slabs", {"from_amount": slab.from_amount, "to_amount": slab.to_amount, "rate": slab.value}
		)
	for slab in default_pit_credit_slabs():
		settings.append(
			"pit_credit_slabs",
			{"from_amount": slab.from_amount, "to_amount": slab.to_amount, "credit_amount": slab.value},
		)
	settings.flags.ignore_permissions = True
	settings.save()


def component_type(type_):
	"""Older HRMS has no 'Employer Contribution' type: fall back to a statistical deduction."""
	if type_ != EMPLOYER_CONTRIBUTION:
		return type_, 0
	options = frappe.get_meta("Salary Component").get_field("type").options or ""
	if EMPLOYER_CONTRIBUTION in options.split("\n"):
		return type_, 0
	return "Deduction", 1


def make_salary_components():
	for name, abbr, type_, formula, condition, depends_on_payment_days, description in COMPONENTS:
		if frappe.db.exists("Salary Component", name):
			continue
		type_, statistical = component_type(type_)
		frappe.get_doc(
			doctype="Salary Component",
			salary_component=name,
			salary_component_abbr=abbr,
			type=type_,
			description=description,
			depends_on_payment_days=depends_on_payment_days,
			amount_based_on_formula=1,
			formula=formula,
			condition=condition,
			statistical_component=statistical,
			remove_if_zero_valued=1,
		).insert(ignore_permissions=True)


def make_salary_structure(company: str) -> str:
	name = f"Монгол стандарт цалин - {frappe.get_cached_value('Company', company, 'abbr')}"
	if frappe.db.exists("Salary Structure", name):
		return name

	make_salary_components()
	structure = frappe.new_doc("Salary Structure")
	structure.name = name
	structure.update(
		{
			"company": company,
			"is_active": "Yes",
			"payroll_frequency": "Monthly",
			"currency": frappe.get_cached_value("Company", company, "default_currency") or "MNT",
		}
	)
	for comp_name, *_ in COMPONENTS:
		component = frappe.get_cached_doc("Salary Component", comp_name)
		table = {"Earning": "earnings", "Deduction": "deductions"}.get(
			component.type, "employer_contributions"
		)
		structure.append(
			table,
			{
				"salary_component": comp_name,
				"abbr": component.salary_component_abbr,
				"amount_based_on_formula": 1,
				"formula": component.formula,
				"condition": component.condition,
				"depends_on_payment_days": component.depends_on_payment_days,
				"statistical_component": component.statistical_component,
			},
		)
	structure.insert()
	return structure.name
