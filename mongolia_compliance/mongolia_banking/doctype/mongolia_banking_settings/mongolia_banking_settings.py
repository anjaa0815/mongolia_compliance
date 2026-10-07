# Copyright (c) 2026, Anjaa and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class MongoliaBankingSettings(Document):
	def on_update(self):
		from mongolia_compliance.mongolia_banking.formats import apply_formats

		apply_formats(self)
