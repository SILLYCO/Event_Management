# Copyright (c) 2026, Haliem and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document

class EventAttendee(Document):
    def before_insert(self):
        """
        Runs before the document is saved to the database.
        Sets default values and validates eligibility.
        """
        # 1. Check Login
        if frappe.session.user == "Guest":
            frappe.throw("You must be logged in to register.")
        
        # Set the User and Default Status
        self.user = frappe.session.user
        self.status = "Pending Approval"

        # 2. Auto-Fetch User Details (Fix for Website Registration)
        # We manually fetch details because the UI "Fetch From" doesn't run during API calls.
        user_details = frappe.db.get_value("User", self.user, ["full_name", "email", "mobile_no"], as_dict=True)
        
        if user_details:
            self.full_name = user_details.full_name
            self.email = user_details.email
            self.phone_number = user_details.mobile_no  # Maps User's mobile to your phone_number field

        # 3. Check for Duplicate Applications
        # We check if this user has already applied (Pending) or is already Registered
        if frappe.db.exists("Event Attendee", {
            "event_activity": self.event_activity, 
            "user": self.user,
            "status": ["in", ["Pending Approval", "Registered"]]
        }):
            frappe.throw("You have already applied for this event.")

        # 4. Check Event Status
        event_doc = frappe.get_doc("Event Activity", self.event_activity)
        
        if event_doc.event_status == "Completed":
            frappe.throw("This event has ended.")
        
        if event_doc.event_status == "Sold Out":
            frappe.throw("Sorry, this event is fully booked.")

    def validate(self):
        """
        Runs on every save. checks permissions for Status Changes.
        """
        # Security: Prevent regular users from approving themselves
        # We check if the status is changing TO 'Registered'
        if self.status == "Registered" and self.db_get("status") != "Registered":
            if "System Manager" not in frappe.get_roles(frappe.session.user):
                frappe.throw("Only Administrators can approve registrations.")
            
            # If Admin approves, we check if there is actual space left
            self.check_capacity_and_reserve()

    def on_update(self):
        """
        Runs after the document is updated.
        """
        self.update_event_status()

    def on_trash(self):
        """
        Runs when the document is deleted.
        """
        self.update_event_status()

    def check_capacity_and_reserve(self):
        """
        Ensures we don't approve more people than the event capacity allows.
        """
        event_doc = frappe.get_doc("Event Activity", self.event_activity)
        
        # Count only CONFIRMED (Registered) attendees
        confirmed_count = frappe.db.count("Event Attendee", {
            "event_activity": self.event_activity,
            "status": "Registered"
        })

        if confirmed_count >= event_doc.capacity:
            frappe.throw(f"Cannot approve. The event is full ({confirmed_count}/{event_doc.capacity}).")

    def update_event_status(self):
        """
        Triggers the parent Event to recalculate its status (e.g. set to Sold Out).
        """
        event_doc = frappe.get_doc("Event Activity", self.event_activity)
        
        if hasattr(event_doc, "update_status"):
            event_doc.update_status()
            # Save without permission checks so users can trigger the update
            event_doc.flags.ignore_permissions = True
            event_doc.save()