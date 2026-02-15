# Copyright (c) 2026, Haliem and contributors
# For license information, please see license.txt

import frappe
from frappe.website.website_generator import WebsiteGenerator
from frappe.utils import get_datetime, now_datetime

class EventActivity(WebsiteGenerator):
    
    def validate(self):
        self.validate_dates()
        self.update_status()

    def validate_dates(self):
        if self.end_date and self.start_date:
            if get_datetime(self.end_date) < get_datetime(self.start_date):
                frappe.throw("End Date cannot be before Start Date")

    def update_status(self):
        # 1. Time Check
        if self.end_date and get_datetime(self.end_date) < now_datetime():
            self.event_status = "Completed" # Updated field name
            return 

        # 2. Capacity Check
        if self.capacity > 0:
            # FIX: Using 'event_activity' to match your database column
            confirmed_attendees = frappe.db.count("Event Attendee", {
                "event_activity": self.name, 
                "status": "Registered"
            })

            if confirmed_attendees >= self.capacity:
                self.event_status = "Sold Out" # Updated field name
            
            elif self.event_status == "Sold Out" and confirmed_attendees < self.capacity:
                self.event_status = "Open for Registration" # Updated field name