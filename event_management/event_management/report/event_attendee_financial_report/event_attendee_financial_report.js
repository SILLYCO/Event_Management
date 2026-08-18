// Copyright (c) 2026, Haliem and contributors
// For license information, please see license.txt

frappe.query_reports["Event Attendee Financial Report"] = {
	filters: [
		{
			fieldname: "event_activity",
			label: __("Event Activity"),
			fieldtype: "Link",
			options: "Event Activity"
		},
		{
			fieldname: "status",
			label: __("Attendee Status"),
			fieldtype: "Select",
			options: "\nPending Approval\nPending Transaction\nRegistered\nRejected\nCanceled"
		},
		{
			fieldname: "promo_code",
			label: __("Promo Code"),
			fieldtype: "Link",
			options: "Event Promo Code"
		},
		{
			fieldname: "payment_method",
			label: __("Payment Method"),
			fieldtype: "Select",
			options: "\nCash\nInstapay\nVodafone Cash\nOrange Cash\nEtisalat Money"
		},
		{
			fieldname: "from_date",
			label: __("From Date"),
			fieldtype: "Date"
		},
		{
			fieldname: "to_date",
			label: __("To Date"),
			fieldtype: "Date"
		}
	]
};
