# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import today


class RadiologyProcedureTemplate(Document):
	def before_insert(self):
		if self.link_existing_item and self.item:
			price_list = frappe.db.get_all(
				"Item Price", {"item_code": self.item}, ["price_list_rate"], order_by="valid_from desc"
			)
			if price_list:
				self.rate = price_list[0].get("price_list_rate")

	def validate(self):
		self.validate_billable()
		self.enable_disable_item()

	def validate_billable(self):
		"""Validate rate is set when billable and not linking existing item."""
		if self.is_billable and not self.link_existing_item and not self.rate:
			frappe.throw(_("Rate is mandatory when 'Is Billable' is checked and not linking existing item."))

	def after_insert(self):
		if not self.link_existing_item:
			create_item_from_template(self)

	def on_update(self):
		doc_before_save = self.get_doc_before_save()
		if not doc_before_save:
			return
		if (
			doc_before_save.template != self.template
			or doc_before_save.rate != self.rate
			or doc_before_save.is_billable != self.is_billable
			or doc_before_save.item_group != self.item_group
			or doc_before_save.description != self.description
			or doc_before_save.medical_department != self.medical_department
		):
			update_item_and_item_price(self)

	def enable_disable_item(self):
		if self.is_billable and self.item:
			if self.disabled:
				frappe.db.set_value("Item", self.item, "disabled", 1)
			else:
				frappe.db.set_value("Item", self.item, "disabled", 0)


def create_item_from_template(doc):
	"""Create Item master entry for billing."""
	disabled = doc.disabled
	if doc.is_billable and not doc.disabled:
		disabled = 0

	uom = frappe.db.exists("UOM", "Unit") or frappe.db.get_single_value("Stock Settings", "stock_uom")
	item = frappe.get_doc(
		{
			"doctype": "Item",
			"item_code": doc.item_code or doc.template,
			"item_name": doc.template,
			"item_group": doc.item_group,
			"description": doc.description,
			"is_sales_item": 1,
			"is_service_item": 1,
			"is_purchase_item": 0,
			"is_stock_item": 0,
			"show_in_website": 0,
			"is_pro_applicable": 0,
			"disabled": disabled,
			"stock_uom": uom,
		}
	).insert(ignore_permissions=True, ignore_mandatory=True)

	if doc.is_billable and doc.rate:
		make_item_price(item.name, doc.rate)
	doc.db_set("item", item.name)


def make_item_price(item, item_price):
	"""Create Item Price entry."""
	price_list_name = frappe.db.get_value(
		"Selling Settings", None, "selling_price_list"
	) or frappe.db.get_value("Price List", {"selling": 1})
	frappe.get_doc(
		{
			"doctype": "Item Price",
			"price_list": price_list_name,
			"item_code": item,
			"price_list_rate": item_price,
			"valid_from": today(),
		}
	).insert(ignore_permissions=True, ignore_mandatory=True)


def update_item_and_item_price(doc):
	"""Update linked Item when template is modified."""
	if doc.is_billable and doc.item:
		item_doc = frappe.get_doc("Item", {"item_code": doc.item})
		item_doc.item_name = doc.template
		item_doc.item_group = doc.item_group
		item_doc.description = doc.description
		item_doc.disabled = 0
		item_doc.save(ignore_permissions=True)
		
		if doc.rate:
			if not frappe.db.exists("Item Price", {"item_code": doc.item, "valid_from": today()}):
				make_item_price(doc.item, doc.rate)
			else:
				item_price = frappe.get_doc("Item Price", {"item_code": doc.item, "valid_from": today()})
				item_price.item_name = doc.template
				item_price.price_list_rate = doc.rate
				item_price.save()

	elif not doc.is_billable and doc.item and not doc.link_existing_item:
		frappe.db.set_value("Item", doc.item, "disabled", 1)
