# Copyright (c) 2026, Haliem and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import get_datetime, now_datetime

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

        # 4. Check Event Status and Date Expiration
        event_doc = frappe.get_doc("Event Activity", self.event_activity)
        
        if hasattr(event_doc, "update_status"):
            old_status = event_doc.event_status
            event_doc.update_status()
            if event_doc.event_status != old_status:
                event_doc.db_set("event_status", event_doc.event_status, update_modified=False)

        now = now_datetime()
        effective_end = event_doc.end_date or event_doc.start_date

        if (effective_end and get_datetime(effective_end) < now) or event_doc.event_status == "Completed":
            frappe.throw("Registration is closed because this event has already taken place or ended.")
        
        if event_doc.event_status == "Sold Out":
            frappe.throw("Sorry, this event is fully booked.")

    def validate(self):
        """
        Runs on every save. Checks permissions and enforces strict queue fairness.
        """
        # 1. Enforce Queue Fairness (Prevent reopening canceled registrations)
        if not self.is_new():
            old_status = self.db_get("status")
            if old_status == "Canceled" and self.status != "Canceled":
                frappe.throw("A canceled registration cannot be reopened. The user must submit a new application to ensure a fair queue order.")

        # 2. Existing check for Registration Approval capacity and roles
        if self.status == "Registered" and self.db_get("status") != "Registered":
            if "System Manager" not in frappe.get_roles(frappe.session.user):
                frappe.throw("Only Administrators can approve registrations.")
            
            self.check_capacity_and_reserve()

        # 3. Prevent Overlapping Registrations
        if self.status in ["Pending Approval", "Pending Transaction", "Registered"]:
            self.check_date_overlap()

    def check_date_overlap(self):
        """
        Ensures the user does not have any other active/pending registrations 
        that overlap in date and time with the selected event.
        """
        event_dates = frappe.db.get_value("Event Activity", self.event_activity, ["event_title", "start_date", "end_date"], as_dict=True)
        if not event_dates or not event_dates.start_date:
            return

        start_date = event_dates.start_date
        end_date = event_dates.end_date or start_date

        # Query overlapping active registrations for the same user
        overlapping_events = frappe.db.sql("""
            SELECT 
                ea.event_title, ea.start_date, ea.end_date
            FROM 
                `tabEvent Attendee` attr
            JOIN 
                `tabEvent Activity` ea ON attr.event_activity = ea.name
            WHERE 
                attr.user = %s
                AND attr.status IN ('Pending Approval', 'Pending Transaction', 'Registered')
                AND attr.name != %s
                AND (
                    (ea.start_date < %s AND %s < COALESCE(ea.end_date, ea.start_date))
                    OR (ea.start_date = %s)
                )
        """, (self.user, self.name or "NewDocument", end_date, start_date, start_date), as_dict=True)

        if overlapping_events:
            overlapping_titles = ", ".join([e.event_title for e in overlapping_events])
            frappe.throw(
                f"Cannot register. The dates for this event overlap with other event(s) "
                f"you have registered for or applied to: {overlapping_titles}."
            )


    def before_save(self):
        """
        Runs before saving. Calculates the final price and enforces race-condition locks.
        """
        # Fetch fields from event_activity if they are not set (fetch_from safety)
        if self.event_activity and (not self.event_is_paid or not self.event_price):
            is_paid, ticket_price = frappe.db.get_value("Event Activity", self.event_activity, ["is_paid", "ticket_price"])
            self.event_is_paid = is_paid
            self.event_price = ticket_price

        if not self.is_new():
            self._old_promo_code = self.db_get("promo_code")
            self._old_status = self.db_get("status")

        if self.event_is_paid == "Paid":
            base_price = float(self.event_price or 0.0)
            
            if self.promo_code:
                # If promo code is new or changed, validate with row locking
                if self.is_new() or (hasattr(self, "_old_promo_code") and self.promo_code != self._old_promo_code):
                    frappe.db.sql("""
                        SELECT name FROM `tabEvent Promo Code` 
                        WHERE name = %s FOR UPDATE
                    """, (self.promo_code,))
                    
                    result = validate_promo_code(self.promo_code, self.event_activity, attendee_name=self.name, user=self.user)
                    if result.get("valid"):
                        discount_amt = base_price * (float(result.get("discount_percentage")) / 100.0)
                        self.final_price = base_price - discount_amt
                    else:
                        frappe.throw(f"Promo Code Error: {result.get('message')}")
                else:
                    # Promo code is unchanged: preserve discounted final price
                    discount_pct = frappe.db.get_value("Event Promo Code", self.promo_code, "discount_percentage") or 0.0
                    discount_amt = base_price * (float(discount_pct) / 100.0)
                    self.final_price = base_price - discount_amt
            else:
                self.final_price = base_price
        else:
            self.promo_code = None
            self.final_price = 0.0

        # Calculate Remaining Amount
        if self.event_is_paid == "Paid":
            final_price = float(self.final_price or 0.0)
            paid_amount = float(self.paid_amount or 0.0)
            self.remaining_amount = max(0.0, final_price - paid_amount)
        else:
            self.remaining_amount = 0.0

    def on_update(self):
        self.update_event_status()
        
        # Recalculate usage for current promo code
        if self.promo_code:
            update_promo_code_usage(self.promo_code)
            
        # Recalculate usage for old promo code if it changed
        if hasattr(self, "_old_promo_code") and self._old_promo_code and self._old_promo_code != self.promo_code:
            update_promo_code_usage(self._old_promo_code)

    def on_trash(self):
        self.update_event_status()

    def after_delete(self):
        if self.promo_code:
            update_promo_code_usage(self.promo_code)

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

# --- PROMO CODE DYNAMIC USAGE RECALCULATION ---
def update_promo_code_usage(promo_code):
    """
    Recalculates the usage count for a promo code based on active attendee records.
    """
    if not promo_code:
        return
    count = frappe.db.count("Event Attendee", {
        "promo_code": promo_code,
        "status": ["not in", ["Canceled", "Rejected"]]
    })
    frappe.db.set_value("Event Promo Code", promo_code, "times_used", count, update_modified=False)

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
def validate_promo_code(promo_code, event_name, attendee_name=None, user=None):
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
        
    # 2. Check Usage Limits (exclude current attendee if updating)
    if promo.usage_limit and promo.usage_limit > 0:
        filters = {
            "promo_code": promo_code,
            "status": ["not in", ["Canceled", "Rejected"]]
        }
        if attendee_name:
            filters["name"] = ["!=", attendee_name]
        active_usage = frappe.db.count("Event Attendee", filters)
        if active_usage >= promo.usage_limit:
            return {"valid": False, "message": "This promo code has reached its usage limit."}
        
    # 3. Check Event Specific Logic
    if promo.promo_type == "Event Specific" and promo.target_event != event.name:
        return {"valid": False, "message": "This code is not valid for this specific event."}
        
    # 4. Check Category Specific Logic
    if promo.promo_type == "Category Specific" and promo.target_category != event.event_category:
        return {"valid": False, "message": f"This code is only valid for {promo.target_category} events."}
        
    # 5. Check One Per User Restriction (Prevent double-dipping)
    target_user = user or frappe.session.user
    if target_user and target_user != "Guest":
        filters = {
            "user": target_user,
            "promo_code": promo_code,
            "status": ["not in", ["Canceled", "Rejected"]] # FIX: Exclude canceled/rejected records
        }
        # If updating an existing record, exclude itself from the "already used" check
        if attendee_name:
            filters["name"] = ["!=", attendee_name]
            
        if frappe.db.exists("Event Attendee", filters):
            return {"valid": False, "message": "You have already used this promo code on a previous application."}
        
    return {"valid": True, "discount_percentage": promo.discount_percentage}