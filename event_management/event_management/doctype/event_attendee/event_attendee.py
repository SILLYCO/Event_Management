import frappe
from frappe.model.document import Document

class EventAttendee(Document):
    def before_insert(self):
        if frappe.session.user == "Guest":
            frappe.throw("You must be logged in to register.")
        
        self.user = frappe.session.user
        self.status = "Pending Approval"

        # Check for Duplicates
        if frappe.db.exists("Event Attendee", {
            "event_activity": self.event_activity, # FIX: Matches your field name
            "user": self.user,
            "status": ["in", ["Pending Approval", "Registered"]]
        }):
            frappe.throw("You have already applied for this event.")

        # Check Event Status
        # We assume your Link field in 'Event Attendee' is named 'event_activity'
        event_doc = frappe.get_doc("Event Activity", self.event_activity)
        
        # FIX: Using 'event_status' to match your Event Activity fields
        if event_doc.event_status == "Completed":
            frappe.throw("This event has ended.")
        if event_doc.event_status == "Sold Out":
            frappe.throw("Sorry, this event is fully booked.")

    def validate(self):
        # Check if Admin is approving
        if self.status == "Registered" and self.db_get("status") != "Registered":
            if "System Manager" not in frappe.get_roles(frappe.session.user):
                frappe.throw("Only Administrators can approve registrations.")
            
            self.check_capacity_and_reserve()

    def on_update(self):
        self.update_event_status()

    def on_trash(self):
        self.update_event_status()

    def check_capacity_and_reserve(self):
        event_doc = frappe.get_doc("Event Activity", self.event_activity)
        
        confirmed_count = frappe.db.count("Event Attendee", {
            "event_activity": self.event_activity, # FIX: Matches your field name
            "status": "Registered"
        })

        if confirmed_count >= event_doc.capacity:
            frappe.throw(f"Cannot approve. The event is full ({confirmed_count}/{event_doc.capacity}).")

    def update_event_status(self):
        event_doc = frappe.get_doc("Event Activity", self.event_activity)
        
        if hasattr(event_doc, "update_status"):
            event_doc.update_status()
            event_doc.flags.ignore_permissions = True
            event_doc.save()