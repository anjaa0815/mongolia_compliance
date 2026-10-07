# Copyright (c) 2026, Anjaa and contributors
# See license.txt

from frappe.tests import UnitTestCase

from mongolia_compliance.mongolia_forms.utils import mn_date, mn_money_in_words, number_in_words


class TestMongoliaFormsUtils(UnitTestCase):
	def test_number_in_words(self):
		cases = {
			0: "тэг",
			15: "арван таван",
			120: "нэг зуун хорин",
			1000: "нэг мянган",
			2500: "хоёр мянга таван зуун",
			21000: "хорин нэг мянган",
			1250300: "нэг сая хоёр зуун тавин мянга гурван зуун",
			2000000005: "хоёр тэрбум таван",
		}
		for number, words in cases.items():
			self.assertEqual(number_in_words(number), words)

	def test_money_in_words(self):
		self.assertEqual(mn_money_in_words(2500.5, "MNT"), "Хоёр мянга таван зуун төгрөг 50 мөнгө")
		self.assertEqual(mn_money_in_words(1000, "MNT"), "Нэг мянган төгрөг")

	def test_date(self):
		self.assertEqual(mn_date("2026-10-07"), "2026 оны 10 сарын 07")
