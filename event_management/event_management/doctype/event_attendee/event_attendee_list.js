frappe.listview_settings["Event Attendee"] = {
	add_fields: ["status"],
	formatters: {
		status(value, df, doc) {
			const colors = {
				"Registered": "green",
				"Pending Approval": "yellow",
				"Pending Transaction": "orange",
				"Rejected": "red",
				"Canceled": "grey",
				"Cancelled": "grey"
			};
			const color = colors[value] || "grey";
			return `<span class="indicator-pill ${color}">${__(value)}</span>`;
		}
	}
};
