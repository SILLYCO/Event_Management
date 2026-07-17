// Copyright (c) 2026, Haliem and contributors
// For license information, please see license.txt

frappe.ui.form.on("Event Attendee", {
	refresh(frm) {
		frm.clear_custom_buttons();

		if (!frm.is_new()) {
			const status_options = (frm.fields_dict.status.df.options || "").split('\n');
			status_options.forEach(option => {
				option = option.trim();
				if (!option) return;

				if (option !== frm.doc.status) {
					frm.add_custom_button(__(option), function () {
						frm.set_value("status", option);
						frm.save();
					}, __("Actions"));
				}
			});
		}
	},
});
