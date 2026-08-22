// Copyright (c) 2026, Haliem and contributors
// For license information, please see license.txt

frappe.ui.form.on("Event Attendee", {
	refresh(frm) {
		frm.clear_custom_buttons();

		if (!frm.is_new()) {
			// Status Transition Actions
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

			// Quick "Record Payment" dialog for Admins & Receptionists
			if (frm.doc.event_is_paid === "Paid") {
				frm.add_custom_button(__("Record Payment"), function () {
					show_record_payment_dialog(frm);
				}, __("Payments"));
			}
		}
	},

	paid_amount(frm) {
		calculate_ledger_totals(frm);
	},

	final_price(frm) {
		calculate_ledger_totals(frm);
	}
});

// Child Table Event Listeners for Event Payment Entry
frappe.ui.form.on("Event Payment Entry", {
	amount(frm, cdt, cdn) {
		calculate_ledger_totals(frm);
	},
	status(frm, cdt, cdn) {
		calculate_ledger_totals(frm);
	},
	payment_entries_add(frm, cdt, cdn) {
		calculate_ledger_totals(frm);
	},
	payment_entries_remove(frm, cdt, cdn) {
		calculate_ledger_totals(frm);
	}
});

function calculate_ledger_totals(frm) {
	if (frm.doc.event_is_paid === "Paid") {
		const final_price = flt(frm.doc.final_price);
		let total_paid = 0;

		if (frm.doc.payment_entries && frm.doc.payment_entries.length > 0) {
			frm.doc.payment_entries.forEach(entry => {
				if (entry.status === "Approved") {
					total_paid += flt(entry.amount);
				}
			});
			frm.set_value("paid_amount", total_paid);
		} else {
			total_paid = flt(frm.doc.paid_amount);
		}

		const remaining = Math.max(0, final_price - total_paid);
		frm.set_value("remaining_amount", remaining);
	} else {
		frm.set_value("paid_amount", 0);
		frm.set_value("remaining_amount", 0);
	}
}

function show_record_payment_dialog(frm) {
	const default_amount = flt(frm.doc.remaining_amount) > 0 ? flt(frm.doc.remaining_amount) : 0;

	const d = new frappe.ui.Dialog({
		title: __("Record Payment / Installment"),
		fields: [
			{
				fieldname: "amount",
				label: __("Amount"),
				fieldtype: "Currency",
				default: default_amount,
				reqd: 1
			},
			{
				fieldname: "payment_method",
				label: __("Payment Method"),
				fieldtype: "Select",
				options: "Cash\nInstapay\nVodafone Cash\nOrange Cash\nEtisalat Money\nBank Transfer",
				default: frm.doc.payment_method || "Cash",
				reqd: 1
			},
			{
				fieldname: "status",
				label: __("Status"),
				fieldtype: "Select",
				options: "Approved\nPending Verification\nRejected",
				default: "Approved",
				reqd: 1
			},
			{
				fieldname: "transaction_reference",
				label: __("Transaction / Ref ID"),
				fieldtype: "Data"
			},
			{
				fieldname: "receipt_image",
				label: __("Receipt Screenshot"),
				fieldtype: "Attach Image"
			},
			{
				fieldname: "notes",
				label: __("Notes"),
				fieldtype: "Small Text",
				default: __("Recorded via Desk")
			}
		],
		primary_action_label: __("Record & Save"),
		primary_action(values) {
			const row = frm.add_child("payment_entries", {
				payment_date: frappe.datetime.now_datetime(),
				amount: flt(values.amount),
				payment_method: values.payment_method,
				status: values.status || "Approved",
				transaction_reference: values.transaction_reference,
				receipt_image: values.receipt_image,
				notes: values.notes,
				recorded_by: frappe.session.user
			});

			if (values.payment_method) {
				frm.set_value("payment_method", values.payment_method);
			}

			calculate_ledger_totals(frm);
			frm.save().then(() => {
				d.hide();
				frappe.show_alert({
					message: __("Payment recorded successfully"),
					indicator: "green"
				});
			});
		}
	});

	d.show();
}
