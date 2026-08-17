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

	paid_amount(frm) {
		calculate_remaining_amount(frm);
	},

	final_price(frm) {
		calculate_remaining_amount(frm);
	}
});

function calculate_remaining_amount(frm) {
	if (frm.doc.event_is_paid === "Paid") {
		const final_price = flt(frm.doc.final_price);
		const paid_amount = flt(frm.doc.paid_amount);
		const remaining = Math.max(0, final_price - paid_amount);
		frm.set_value("remaining_amount", remaining);
	} else {
		frm.set_value("remaining_amount", 0);
	}
}
