frappe.listview_settings["Event Activity"] = {
	add_fields: ["event_status"],
	get_indicator: function (doc) {
		if (doc.event_status === "Opening Soon") {
			return [__("Opening Soon"), "yellow", "event_status,=,Opening Soon"];
		} else if (doc.event_status === "Open for Registration") {
			return [__("Open for Registration"), "green", "event_status,=,Open for Registration"];
		} else if (doc.event_status === "Sold Out") {
			return [__("Sold Out"), "orange", "event_status,=,Sold Out"];
		} else if (doc.event_status === "Cancelled") {
			return [__("Cancelled"), "red", "event_status,=,Cancelled"];
		} else if (doc.event_status === "Completed") {
			return [__("Completed"), "grey", "event_status,=,Completed"];
		}
	},
	formatters: {
		event_status(value, df, doc) {
			const colors = {
				"Opening Soon": "yellow",
				"Open for Registration": "green",
				"Sold Out": "orange",
				"Cancelled": "red",
				"Completed": "grey"
			};
			const color = colors[value] || "grey";
			return `<span class="indicator-pill ${color}">${__(value)}</span>`;
		}
	}
};
