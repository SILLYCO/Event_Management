import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_to_date, now_datetime

class TestEventAttendee(FrappeTestCase):
    def setUp(self):
        # Create dummy events for testing
        self.user = "test_attendee@example.com"
        if not frappe.db.exists("User", self.user):
            user = frappe.new_doc("User")
            user.email = self.user
            user.first_name = "Test"
            user.last_name = "Attendee"
            user.send_welcome_email = 0
            user.insert(ignore_permissions=True)

        self.start1 = now_datetime()
        self.end1 = add_to_date(self.start1, hours=2)

        # Event 1: Today, duration 2 hours
        self.event1 = self.create_test_event("Event 1", self.start1, self.end1)
        # Event 2: Today, overlaps with Event 1 (starts 1 hour after Event 1 start)
        self.event2 = self.create_test_event("Event 2", add_to_date(self.start1, hours=1), add_to_date(self.start1, hours=3))
        # Event 3: Today, starts right after Event 1 ends (no overlap)
        self.event3 = self.create_test_event("Event 3", self.end1, add_to_date(self.end1, hours=2))

    def tearDown(self):
        frappe.db.rollback()

    def create_test_event(self, title, start_date, end_date):
        doc = frappe.new_doc("Event Activity")
        doc.event_title = title
        doc.start_date = start_date
        doc.end_date = end_date
        doc.event_category = "Camps"
        doc.event_description = "Test Description"
        doc.capacity = 10
        doc.insert(ignore_permissions=True)
        return doc.name

    def test_overlapping_registrations(self):
        frappe.set_user(self.user)

        # Register user for Event 1
        reg1 = frappe.new_doc("Event Attendee")
        reg1.event_activity = self.event1
        reg1.insert(ignore_permissions=True) # Should pass

        # Try to register user for Event 2 (Overlapping Event)
        reg2 = frappe.new_doc("Event Attendee")
        reg2.event_activity = self.event2
        self.assertRaises(frappe.ValidationError, reg2.insert, ignore_permissions=True)

        # Try to register user for Event 3 (Non-overlapping Event starting immediately after)
        reg3 = frappe.new_doc("Event Attendee")
        reg3.event_activity = self.event3
        reg3.insert(ignore_permissions=True) # Should pass

