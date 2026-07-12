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
        
        self.user = frappe.session.user
        self.status = "Pending Approval"

        # 2. Auto-Fetch User Details
        user_details = frappe.db.get_value("User", self.user, ["full_name", "email", "mobile_no"], as_dict=True)
        
        if user_details:
            self.full_name = user_details.full_name
            self.email = user_details.email
            self.phone_number = user_details.mobile_no

        # 3. Check for Duplicate Applications
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
        if self.status == "Registered" and self.db_get("status") != "Registered":
            if "System Manager" not in frappe.get_roles(frappe.session.user):
                frappe.throw("Only Administrators can approve registrations.")
            
            self.check_capacity_and_reserve()

    def before_save(self):
        """
        Runs before saving. Calculates the final price and enforces race-condition locks.
        """
        if self.event_is_paid == "Paid":
            base_price = float(self.event_price or 0.0)
            
            if self.promo_code:
                # --- RACE CONDITION PROTECTION ---
                # If this is a brand new application, lock the promo code row in MySQL
                # to prevent concurrent users from bypassing the usage limit.
                if self.is_new():
                    frappe.db.sql("""
                        SELECT name FROM `tabEvent Promo Code` 
                        WHERE name = %s FOR UPDATE
                    """, (self.promo_code,))
                
                # Re-validate with the locked state
                result = validate_promo_code(self.promo_code, self.event_activity, self.name)
                
                if result.get("valid"):
                    discount_amt = base_price * (float(result.get("discount_percentage")) / 100.0)
                    self.final_price = base_price - discount_amt
                else:
                    # If invalid during insertion, abort the save entirely.
                    if self.is_new():
                        frappe.throw(f"Promo Code Error: {result.get('message')}")
                    else:
                        self.promo_code = None
                        self.final_price = base_price
            else:
                self.final_price = base_price

    def after_insert(self):
        """
        Increment the promo code usage counter securely.
        """
        if self.promo_code:
            try:
                promo = frappe.get_doc("Event Promo Code", self.promo_code)
                promo.times_used = (promo.times_used or 0) + 1
                promo.save(ignore_permissions=True)
            except Exception as e:
                frappe.log_error(f"Failed to increment promo code {self.promo_code}: {str(e)}")

    def on_update(self):
        self.update_event_status()

    def on_trash(self):
        self.update_event_status()

    def check_capacity_and_reserve(self):
        event_doc = frappe.get_doc("Event Activity", self.event_activity)
        
        confirmed_count = frappe.db.count("Event Attendee", {
            "event_activity": self.event_activity,
            "status": "Registered"
        })

        # FIX: Only block approval if capacity is strictly greater than 0
        if event_doc.capacity > 0 and confirmed_count >= event_doc.capacity:
            frappe.throw(f"Cannot approve. The event is full ({confirmed_count}/{event_doc.capacity}).")

    def update_event_status(self):
        event_doc = frappe.get_doc("Event Activity", self.event_activity)
        if hasattr(event_doc, "update_status"):
            event_doc.update_status()
            event_doc.flags.ignore_permissions = True
            event_doc.save()

# --- NEW FUNCTION FOR CANCELLATION ---
@frappe.whitelist()
def cancel_registration(attendee_name):
    if frappe.session.user == "Guest":
        frappe.throw("You must be logged in.")

    if not frappe.db.exists("Event Attendee", attendee_name):
        frappe.throw("Registration not found.")

    doc = frappe.get_doc("Event Attendee", attendee_name)

    if doc.user != frappe.session.user:
        frappe.throw("You are not authorized to cancel this registration.")

    event = frappe.get_doc("Event Activity", doc.event_activity)
    if event.event_status == "Completed":
        frappe.throw("Cannot cancel. The event has already ended.")

    doc.status = "Canceled"
    doc.save(ignore_permissions=True)
    
    return "success"

# --- PROMO CODE VALIDATION API ---
@frappe.whitelist()
def validate_promo_code(promo_code, event_name, attendee_name=None):
    """
    Validates a promo code based on its type, category, limits, and user history.
    """
    if not frappe.db.exists("Event Promo Code", promo_code):
        return {"valid": False, "message": "Invalid promo code."}
        
    promo = frappe.get_doc("Event Promo Code", promo_code)
    event = frappe.get_doc("Event Activity", event_name)
    
    # 1. Check Active Status
    if not promo.active:
        return {"valid": False, "message": "This promo code is inactive."}
        
    # 2. Check Usage Limits
    if promo.usage_limit and promo.usage_limit > 0 and (promo.times_used or 0) >= promo.usage_limit:
        return {"valid": False, "message": "This promo code has reached its usage limit."}
        
    # 3. Check Event Specific Logic
    if promo.promo_type == "Event Specific" and promo.target_event != event.name:
        return {"valid": False, "message": "This code is not valid for this specific event."}
        
    # 4. Check Category Specific Logic
    if promo.promo_type == "Category Specific" and promo.target_category != event.event_category:
        return {"valid": False, "message": f"This code is only valid for {promo.target_category} events."}
        
    # 5. Check One Per User Restriction (Prevent double-dipping)
    if frappe.session.user != "Guest":
        filters = {
            "user": frappe.session.user,
            "promo_code": promo_code
        }
        # If updating an existing record, exclude itself from the "already used" check
        if attendee_name:
            filters["name"] = ["!=", attendee_name]
            
        if frappe.db.exists("Event Attendee", filters):
            return {"valid": False, "message": "You have already used this promo code on a previous application."}
        
    return {"valid": True, "discount_percentage": promo.discount_percentage}