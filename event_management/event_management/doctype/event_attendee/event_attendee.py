# Copyright (c) 2026, Haliem and contributors
# For license information, please see license.txt

import frappe
import json
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
        
        self.user = frappe.session.user
        self.status = "Pending Approval"

        # 2. Auto-Fetch User Details (Fix for Website Registration)
        # We manually fetch details because the UI "Fetch From" doesn't run during API calls.
        user_details = frappe.db.get_value("User", self.user, ["full_name", "email", "mobile_no"], as_dict=True)
        
        if user_details:
            self.full_name = user_details.full_name
            self.email = user_details.email
            self.phone_number = user_details.mobile_no

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
        Runs on every save. Checks permissions for Status Changes.
        """
        # Security: Prevent regular users from approving themselves
        if self.status == "Registered" and self.db_get("status") != "Registered":
            if "System Manager" not in frappe.get_roles(frappe.session.user):
                frappe.throw("Only Administrators can approve registrations.")
            
            # If Admin approves, we check if there is actual space left
            self.check_capacity_and_reserve()

    def before_save(self):
        """
        Runs before saving. Calculates the final price if promo codes are used.
        """
        if self.event_is_paid == "Paid":
            base_price = float(self.event_price or 0.0)
            
            # If a promo code is applied, calculate the discount
            if self.promo_code:
                try:
                    promo = frappe.get_doc("Event Promo Code", self.promo_code)
                    if promo.active:
                        discount_amt = base_price * (float(promo.discount_percentage) / 100.0)
                        self.final_price = base_price - discount_amt
                    else:
                        self.final_price = base_price
                except frappe.DoesNotExistError:
                    self.final_price = base_price
            else:
                self.final_price = base_price

    def on_update(self):
        self.update_event_status()

    def on_trash(self):
        self.update_event_status()

    def check_capacity_and_reserve(self):
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
            event_doc.flags.ignore_permissions = True
            event_doc.save()

# --- NEW FUNCTION FOR CANCELLATION ---
@frappe.whitelist()
def cancel_registration(attendee_name):
    """
    API endpoint to cancel a registration.
    """
    if frappe.session.user == "Guest":
        frappe.throw("You must be logged in.")

    if not frappe.db.exists("Event Attendee", attendee_name):
        frappe.throw("Registration not found.")

    doc = frappe.get_doc("Event Attendee", attendee_name)

    # Security: Ensure the user owns this ticket
    if doc.user != frappe.session.user:
        frappe.throw("You are not authorized to cancel this registration.")

    # Validation: Cannot cancel if event is over
    event = frappe.get_doc("Event Activity", doc.event_activity)
    if event.event_status == "Completed":
        frappe.throw("Cannot cancel. The event has already ended.")

    # Update Status
    doc.status = "Canceled" # Ensure this matches your DocType option spelling
    doc.save(ignore_permissions=True)
    
    return "success"


# --- QR CODE CHECK-IN API ---
@frappe.whitelist()
def process_qr_checkin(qr_text, event_name):
    """
    Takes the scanned JSON QR string, finds the Servant, maps it to the User email, 
    and checks them into the Event Attendee record.
    """
    # Security: Only admins/event managers should be able to check people in
    if "System Manager" not in frappe.get_roles(frappe.session.user):
        return {"status": "error", "message": "Not authorized to perform check-ins."}

    try:
        # 1. Decode the JSON from the scanner
        qr_data = json.loads(qr_text)
        servant_id = qr_data.get("refrance_id")

        if not servant_id:
            return {"status": "error", "message": "Invalid QR: Missing refrance_id."}

        # 2. Find the Servant profile
        if not frappe.db.exists("Servant", servant_id):
            return {"status": "error", "message": f"Servant {servant_id} not found."}

        # 3. Get the Servant's Email 
        # (Checking both common naming conventions based on your screenshot)
        servant_email = frappe.db.get_value("Servant", servant_id, "email_address")
        if not servant_email:
            servant_email = frappe.db.get_value("Servant", servant_id, "email")
        
        if not servant_email:
            return {"status": "error", "message": f"Servant {servant_id} has no email address on their profile."}

        # 4. Find their Event Attendee record
        attendee = frappe.db.get_value("Event Attendee", {
            "event_activity": event_name,
            "user": servant_email
        }, ["name", "status", "attended", "full_name"], as_dict=True)

        if not attendee:
            return {"status": "error", "message": f"User ({servant_email}) is not registered for this event."}

        # 5. Validate their status (Must be Registered!)
        if attendee.status != "Registered":
            return {"status": "error", "message": f"Cannot check in. Attendee status is: {attendee.status}"}

        # 6. Check if they already checked in
        if attendee.attended:
            return {"status": "warning", "message": f"{attendee.full_name} is already checked in!"}

        # 7. Success! Mark as attended.
        frappe.db.set_value("Event Attendee", attendee.name, "attended", 1)
        
        return {
            "status": "success", 
            "message": f"Successfully checked in {attendee.full_name}!"
        }

    except json.JSONDecodeError:
        return {"status": "error", "message": "Invalid QR format (Not valid JSON)."}
    except Exception as e:
        return {"status": "error", "message": f"Server error: {str(e)}"}