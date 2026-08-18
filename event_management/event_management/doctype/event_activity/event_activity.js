// Copyright (c) 2026, Haliem and contributors
// For license information, please see license.txt

frappe.ui.form.on("Event Activity", {
	refresh(frm) {
		// Clear existing custom buttons to avoid duplicates on re-render
		frm.clear_custom_buttons();

		// Only show the publish action button for existing, saved documents
		if (!frm.is_new()) {
			if (frm.doc.published) {
				frm.add_custom_button(__("Unpublish"), function () {
					frm.set_value("published", 0);
					frm.save();
				});
			} else {
				frm.add_custom_button(__("Publish"), function () {
					frm.set_value("published", 1);
					frm.save();
				});
			}

			// Add direct link to Financial & Attendee Report pre-filtered for this event
			frm.add_custom_button(__("Financial & Attendee Report"), function () {
				frappe.set_route("query-report", "Event Attendee Financial Report", {
					event_activity: frm.doc.name
				});
			}, __("Reports"));
		}
	},
});
