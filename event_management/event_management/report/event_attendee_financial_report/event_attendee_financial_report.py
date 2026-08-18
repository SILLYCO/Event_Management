# Copyright (c) 2026, Haliem and contributors
# For license information, please see license.txt

import json
import frappe
from frappe.utils import flt

def execute(filters=None):
	filters = filters or {}
	custom_questions = get_custom_questions(filters)
	columns = get_columns(custom_questions)
	data = get_data(filters, custom_questions)
	report_summary = get_report_summary(data, custom_questions)
	chart = get_chart_data(data)

	return columns, data, None, chart, report_summary

def get_custom_questions(filters):
	"""
	Discovers custom questions defined for the selected Event Activity
	or across active events with attendees.
	"""
	event_name = filters.get("event_activity")
	if event_name:
		fields = frappe.get_all(
			"Event Custom Field",
			filters={"parent": event_name, "parenttype": "Event Activity"},
			fields=["label", "fieldtype", "options"],
			order_by="idx asc"
		)
	else:
		fields = frappe.db.sql("""
			SELECT label, fieldtype, options, MIN(idx) as min_idx
			FROM `tabEvent Custom Field`
			WHERE parenttype = 'Event Activity'
			GROUP BY label, fieldtype, options
			ORDER BY min_idx ASC
		""", as_dict=True)

	questions = []
	seen = set()
	for f in fields:
		label = (f.get("label") or "").strip()
		if not label or label in seen:
			continue
		seen.add(label)
		slug = f"custom_q_{frappe.scrub(label)}"
		questions.append({
			"label": label,
			"fieldname": slug,
			"fieldtype": f.get("fieldtype") or "Data",
			"options": f.get("options") or ""
		})
	return questions

def get_columns(custom_questions):
	base_columns = [
		{
			"label": "Attendee ID",
			"fieldname": "name",
			"fieldtype": "Link",
			"options": "Event Attendee",
			"width": 170
		},
		{
			"label": "Full Name",
			"fieldname": "full_name",
			"fieldtype": "Data",
			"width": 160
		},
		{
			"label": "Email",
			"fieldname": "email",
			"fieldtype": "Data",
			"width": 190
		},
		{
			"label": "Phone",
			"fieldname": "phone_number",
			"fieldtype": "Data",
			"width": 130
		},
		{
			"label": "Event Activity",
			"fieldname": "event_activity",
			"fieldtype": "Link",
			"options": "Event Activity",
			"width": 200
		},
		{
			"label": "Status",
			"fieldname": "status",
			"fieldtype": "Data",
			"width": 140
		},
		{
			"label": "Promo Code",
			"fieldname": "promo_code",
			"fieldtype": "Link",
			"options": "Event Promo Code",
			"width": 130
		},
		{
			"label": "Base Price",
			"fieldname": "event_price",
			"fieldtype": "Currency",
			"width": 110
		},
		{
			"label": "Total Due",
			"fieldname": "final_price",
			"fieldtype": "Currency",
			"width": 110
		},
		{
			"label": "Paid Amount",
			"fieldname": "paid_amount",
			"fieldtype": "Currency",
			"width": 110
		},
		{
			"label": "Remaining (To Have)",
			"fieldname": "remaining_amount",
			"fieldtype": "Currency",
			"width": 150
		},
		{
			"label": "Payment Method",
			"fieldname": "payment_method",
			"fieldtype": "Data",
			"width": 130
		},
		{
			"label": "Date",
			"fieldname": "date",
			"fieldtype": "Datetime",
			"width": 160
		}
	]

	# Dynamically append custom question columns
	for q in custom_questions:
		base_columns.append({
			"label": q["label"],
			"fieldname": q["fieldname"],
			"fieldtype": "Data",
			"width": 160
		})

	return base_columns

def get_data(filters, custom_questions):
	conditions = []
	values = {}

	if filters.get("event_activity"):
		conditions.append("event_activity = %(event_activity)s")
		values["event_activity"] = filters["event_activity"]

	if filters.get("status"):
		conditions.append("status = %(status)s")
		values["status"] = filters["status"]

	if filters.get("promo_code"):
		conditions.append("promo_code = %(promo_code)s")
		values["promo_code"] = filters["promo_code"]

	if filters.get("payment_method"):
		conditions.append("payment_method = %(payment_method)s")
		values["payment_method"] = filters["payment_method"]

	if filters.get("from_date"):
		conditions.append("date >= %(from_date)s")
		values["from_date"] = filters["from_date"]

	if filters.get("to_date"):
		conditions.append("date <= %(to_date)s")
		values["to_date"] = f"{filters['to_date']} 23:59:59"

	where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

	data = frappe.db.sql(f"""
		SELECT 
			name, full_name, email, phone_number, event_activity,
			status, promo_code, event_price, final_price, 
			paid_amount, remaining_amount, payment_method, date,
			custom_answers
		FROM `tabEvent Attendee`
		{where_clause}
		ORDER BY date DESC
	""", values, as_dict=True)

	for row in data:
		row["event_price"] = flt(row.get("event_price"))
		row["final_price"] = flt(row.get("final_price"))
		row["paid_amount"] = flt(row.get("paid_amount"))
		row["remaining_amount"] = flt(row.get("remaining_amount"))

		# Parse custom_answers JSON
		answers_raw = row.get("custom_answers")
		answers_dict = {}
		if answers_raw:
			try:
				if isinstance(answers_raw, str):
					answers_dict = json.loads(answers_raw)
				elif isinstance(answers_raw, dict):
					answers_dict = answers_raw
			except Exception:
				answers_dict = {}

		# Populate each dynamic question column
		for q in custom_questions:
			row[q["fieldname"]] = answers_dict.get(q["label"], "")

	return data

def get_report_summary(data, custom_questions):
	total_due = sum(flt(row.get("final_price")) for row in data)
	total_paid = sum(flt(row.get("paid_amount")) for row in data)
	total_remaining = sum(flt(row.get("remaining_amount")) for row in data)
	total_records = len(data)

	summary = [
		{
			"value": total_paid,
			"label": "Total Paid (Collected)",
			"datatype": "Currency",
			"indicator": "Green"
		},
		{
			"value": total_remaining,
			"label": "Total Remaining (To Have)",
			"datatype": "Currency",
			"indicator": "Red" if total_remaining > 0 else "Grey"
		},
		{
			"value": total_due,
			"label": "Total Expected Revenue",
			"datatype": "Currency",
			"indicator": "Blue"
		},
		{
			"value": total_records,
			"label": "Total Attendees",
			"datatype": "Int",
			"indicator": "Grey"
		}
	]

	# Add Answer distribution counts for choice questions (Select / Check)
	for q in custom_questions:
		if q.get("fieldtype") in ["Select", "Check"]:
			counts = {}
			for row in data:
				ans = row.get(q["fieldname"])
				if ans:
					counts[ans] = counts.get(ans, 0) + 1
			if counts:
				breakdown_str = ", ".join([f"{k}: {v}" for k, v in counts.items()])
				summary.append({
					"value": breakdown_str,
					"label": f"Answers: {q['label']}",
					"datatype": "Data",
					"indicator": "Purple"
				})

	return summary

def get_chart_data(data):
	total_paid = sum(flt(row.get("paid_amount")) for row in data)
	total_remaining = sum(flt(row.get("remaining_amount")) for row in data)

	if total_paid == 0 and total_remaining == 0:
		return None

	return {
		"data": {
			"labels": ["Paid (Collected)", "Remaining (To Have)"],
			"datasets": [
				{
					"name": "Financials",
					"values": [total_paid, total_remaining]
				}
			]
		},
		"type": "donut",
		"colors": ["#10b981", "#ef4444"]
	}
