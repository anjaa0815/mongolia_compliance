"""Pure calculation rules for Mongolian payroll.

Nothing in this module imports frappe, so the rules can be unit tested on their own.
All rates are percentages (8.5 means 8.5%) and all amounts are monthly tugriks.

Legal basis:
- Нийгмийн даатгалын тухай хууль: шимтгэлийн хувь, дээд хязгаар (хөдөлмөрийн хөлсний доод хэмжээ x 10).
- Хувь хүний орлогын албан татварын тухай хууль: шатлалтай хувь, сар бүрийн татварын хөнгөлөлт.
- Хөдөлмөрийн тухай хууль: илүү цаг, баярын өдрийн ажил, ээлжийн амралтын олговор.
"""

from __future__ import annotations

import calendar
import datetime
from dataclasses import dataclass, field

# Fund keys used for the НД-7 / НД-8 breakdown.
PENSION = "pension"  # Тэтгэврийн даатгал
BENEFIT = "benefit"  # Тэтгэмжийн даатгал
ACCIDENT = "accident"  # Үйлдвэрлэлийн осол, мэргэжлээс шалтгаалсан өвчний даатгал (ҮОМШӨ)
UNEMPLOYMENT = "unemployment"  # Ажилгүйдлийн даатгал
HEALTH = "health"  # Эрүүл мэндийн даатгал

FUNDS = (PENSION, BENEFIT, ACCIDENT, UNEMPLOYMENT, HEALTH)


@dataclass
class Slab:
	from_amount: float
	to_amount: float  # 0 means "no upper limit"
	value: float  # rate in % for tax slabs, tugriks for credit slabs

	def contains(self, amount: float) -> bool:
		return amount > self.from_amount and (not self.to_amount or amount <= self.to_amount)


def default_pit_slabs() -> list[Slab]:
	return [
		Slab(0, 6_000_000, 10),
		Slab(6_000_000, 12_000_000, 15),
		Slab(12_000_000, 0, 20),
	]


def default_pit_credit_slabs() -> list[Slab]:
	# Сарын хөнгөлөлт 20,000₮ (жилд 240,000₮) - 10,000₮ (жилд 120,000₮), 3 саяас дээш 0.
	return [
		Slab(0, 500_000, 20_000),
		Slab(500_000, 1_000_000, 18_000),
		Slab(1_000_000, 1_500_000, 16_000),
		Slab(1_500_000, 2_000_000, 14_000),
		Slab(2_000_000, 2_500_000, 12_000),
		Slab(2_500_000, 3_000_000, 10_000),
	]


@dataclass
class PayrollRules:
	minimum_wage: float = 792_000
	ceiling_multiplier: float = 10
	employee_rates: dict = field(
		default_factory=lambda: {PENSION: 8.5, BENEFIT: 0.8, ACCIDENT: 0.0, UNEMPLOYMENT: 0.2, HEALTH: 2.0}
	)
	# ACCIDENT for the employer comes from the company's risk class, see employer_rates_for().
	employer_rates: dict = field(
		default_factory=lambda: {PENSION: 8.5, BENEFIT: 1.0, ACCIDENT: 0.5, UNEMPLOYMENT: 0.5, HEALTH: 2.0}
	)
	pit_slabs: list = field(default_factory=default_pit_slabs)
	pit_credit_slabs: list = field(default_factory=default_pit_credit_slabs)
	daily_hours: float = 8
	overtime_multiplier: float = 1.5
	holiday_multiplier: float = 2.0
	precision: int = 2

	# --- НДШ ---------------------------------------------------------------

	@property
	def ndsh_ceiling(self) -> float:
		return self.minimum_wage * self.ceiling_multiplier

	def ndsh_base(self, wage: float) -> float:
		"""Шимтгэл ногдуулах орлого: дээд хязгаараар таслана."""
		wage = max(float(wage or 0), 0)
		if self.ndsh_ceiling:
			wage = min(wage, self.ndsh_ceiling)
		return wage

	def employer_rates_for(self, accident_rate: float | None = None) -> dict:
		rates = dict(self.employer_rates)
		if accident_rate is not None:
			rates[ACCIDENT] = accident_rate
		return rates

	def contribution_breakdown(self, base: float, rates: dict) -> dict:
		return {fund: round(base * float(rates.get(fund) or 0) / 100, self.precision) for fund in FUNDS}

	def ndsh_employee(self, wage: float) -> float:
		return round(
			sum(self.contribution_breakdown(self.ndsh_base(wage), self.employee_rates).values()),
			self.precision,
		)

	def ndsh_employer(self, wage: float, accident_rate: float | None = None) -> float:
		rates = self.employer_rates_for(accident_rate)
		return round(sum(self.contribution_breakdown(self.ndsh_base(wage), rates).values()), self.precision)

	@property
	def employee_total_rate(self) -> float:
		return sum(float(v or 0) for v in self.employee_rates.values())

	# --- ХХОАТ -------------------------------------------------------------

	def pit_before_credit(self, taxable: float) -> float:
		"""Шатласан хувиар тооцсон татвар (хөнгөлөлтөөс өмнө)."""
		taxable = max(float(taxable or 0), 0)
		tax = 0.0
		for slab in sorted(self.pit_slabs, key=lambda s: s.from_amount):
			if taxable <= slab.from_amount:
				break
			upper = taxable if not slab.to_amount else min(taxable, slab.to_amount)
			tax += (upper - slab.from_amount) * slab.value / 100
		return round(tax, self.precision)

	def pit_credit(self, wage: float) -> float:
		"""Сар бүрийн татварын хөнгөлөлт, сарын цалин хөлсний хэмжээнээс хамаарна."""
		wage = float(wage or 0)
		if wage <= 0:
			return 0.0
		for slab in self.pit_credit_slabs:
			if slab.contains(wage):
				return float(slab.value)
		return 0.0

	def pit(self, wage: float, ndsh_employee: float) -> float:
		"""Суутгах ХХОАТ = (цалин - ажилтны НДШ)-ээс шатлалаар бодсон татвар - хөнгөлөлт, 0-ээс бага биш."""
		taxable = max(float(wage or 0) - float(ndsh_employee or 0), 0)
		return round(max(self.pit_before_credit(taxable) - self.pit_credit(wage), 0), self.precision)

	# --- Хөдөлмөрийн хууль -------------------------------------------------

	def hourly_rate(self, monthly_salary: float, norm_days: float) -> float:
		norm_hours = float(norm_days or 0) * self.daily_hours
		return float(monthly_salary or 0) / norm_hours if norm_hours else 0.0

	def overtime_pay(self, monthly_salary: float, norm_days: float, hours: float) -> float:
		return round(
			self.hourly_rate(monthly_salary, norm_days) * float(hours or 0) * self.overtime_multiplier,
			self.precision,
		)

	def holiday_pay(self, monthly_salary: float, norm_days: float, hours: float) -> float:
		return round(
			self.hourly_rate(monthly_salary, norm_days) * float(hours or 0) * self.holiday_multiplier,
			self.precision,
		)

	def vacation_pay(self, average_daily_wage: float, days: float) -> float:
		return round(float(average_daily_wage or 0) * float(days or 0), self.precision)


def average_daily_wage(total_wage: float, total_days: float) -> float:
	"""Ээлжийн амралтын олговрын дундаж: өмнөх 12 сарын цалин / ажилласан өдөр."""
	return float(total_wage or 0) / float(total_days) if total_days else 0.0


def norm_working_days(any_date: datetime.date, non_working_dates=None) -> int:
	"""Сарын ажлын өдрийн норм.

	`non_working_dates` (амралтын болон баярын өдрүүд, Holiday List-ээс) өгөгдвөл тухайн сарын
	хуанлийн өдрөөс хасна; өгөгдөөгүй бол Даваа-Баасан гарагийг тоолно.
	"""
	days_in_month = calendar.monthrange(any_date.year, any_date.month)[1]
	if non_working_dates is not None:
		in_month = {d for d in non_working_dates if d.year == any_date.year and d.month == any_date.month}
		return days_in_month - len(in_month)
	return sum(
		1
		for day in range(1, days_in_month + 1)
		if datetime.date(any_date.year, any_date.month, day).weekday() < 5
	)
