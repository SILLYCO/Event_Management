# Copyright (c) 2026, Haliem and contributors
# For license information, please see license.txt

import frappe
from frappe.website.website_generator import WebsiteGenerator
from frappe.utils import get_datetime, now_datetime

class EventActivity(WebsiteGenerator):
    
    def validate(self):
        """
        Run checks before saving the Event.
        """
        self.validate_dates()
        self.generate_route()
        self.update_status()

    def validate_dates(self):
        """
        Ensure End Date is after Start Date.
        """
        if self.end_date and self.start_date:
            if get_datetime(self.end_date) < get_datetime(self.start_date):
                frappe.throw("End Date cannot be before Start Date")

    def generate_route(self):
        """
        Auto-generates the URL slug if it is missing.
        Example: "Summer Camp" -> "summer-camp"
        """
        if not self.route:
            self.route = frappe.scrub(self.event_title)

    def update_status(self):
        """
        Checks time, capacity, and registration start date to set status automatically.
        Priority: Completed > Sold Out > Opening Soon > Open
        """
        # --- THE FIX: Guard clause to protect manual overrides ---
        if self.event_status == "Cancelled":
            return
        
        now = now_datetime()
        
        # --- UPDATE REGISTERED COUNT ---
        # We count this regardless of capacity limits so the admin always sees the live number.
        self.registered_count = frappe.db.count("Event Attendee", {
            "event_activity": self.name, 
            "status": "Registered"
        })

        # 1. Check if Event is Completed (Time-based - Highest Priority)
        if self.end_date and get_datetime(self.end_date) < now:
            self.event_status = "Completed"
            return 

        # 2. Check Capacity (Sold Out - High Priority)
        # Only enforces "Sold Out" if capacity is greater than 0
        if self.capacity > 0 and self.registered_count >= self.capacity:
            self.event_status = "Sold Out"
            return # Stop here if full

        # 3. Check Registration Start Date (Opening Soon vs Open)
        if self.registration_start_date:
            if get_datetime(self.registration_start_date) > now:
                # Registration date is in the future
                self.event_status = "Opening Soon"
            else:
                # Registration date has passed, and we are not full/completed
                self.event_status = "Open for Registration"
        
        else:
            # Fallback: If no start date is set, assume it is open immediately
            # (unless it was already set to something else manually, but we enforce Open here)
            if self.event_status != "Sold Out":
                self.event_status = "Open for Registration"


# --- SCHEDULED JOB FUNCTION ---
def update_all_event_statuses():
    """
    Scheduled job to update statuses for all non-completed events.
    Add this to your hooks.py under scheduler_events.
    """
    # THE FIX: Exclude both 'Completed' and 'Cancelled' from the daily check
    events = frappe.get_all("Event Activity", 
        filters={"event_status": ["not in", ["Completed", "Cancelled"]]}, 
        fields=["name"]
    )

    for event in events:
        doc = frappe.get_doc("Event Activity", event.name)
        # This runs the logic we just wrote above
        doc.update_status()
        doc.save(ignore_permissions=True)