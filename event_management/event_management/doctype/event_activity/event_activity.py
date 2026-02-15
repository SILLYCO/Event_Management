# Copyright (c) 2026, Haliem and contributors
# For license information, please see license.txt

import frappe
from frappe.website.website_generator import WebsiteGenerator
from frappe.utils import get_datetime, now_datetime

class EventActivity(WebsiteGenerator):
    
    def validate(self):
        self.validate_dates()
        self.generate_route()  # <--- Add this line
        self.update_status()

    def generate_route(self):
        """
        Auto-generates the URL slug if it is missing.
        Example: "Scout Camp" -> "scout-camp"
        """
        if not self.route:
            # We use 'frappe.scrub' to make it URL friendly (lowercase + dashes)
            # We assume your field is 'event_title' based on your screenshot
            self.route = frappe.scrub(self.event_title)
            
            # Optional: If you want unique URLs (like events/scout-camp-2026), 
            # you can append the ID or date:
            # self.route = f"{frappe.scrub(self.event_title)}-{self.name}"

    def validate_dates(self):
        if self.end_date and self.start_date:
            if get_datetime(self.end_date) < get_datetime(self.start_date):
                frappe.throw("End Date cannot be before Start Date")

    def update_status(self):
        # 1. Time Check
        if self.end_date and get_datetime(self.end_date) < now_datetime():
            self.event_status = "Completed"
            return 

        # 2. Capacity Check
        if self.capacity > 0:
            confirmed_attendees = frappe.db.count("Event Attendee", {
                "event_activity": self.name, 
                "status": "Registered"
            })

            if confirmed_attendees >= self.capacity:
                self.event_status = "Sold Out"
            
            elif self.event_status == "Sold Out" and confirmed_attendees < self.capacity:
                self.event_status = "Open for Registration"