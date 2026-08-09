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
        doc.is_paid = "Paid"
        doc.ticket_price = 100.0
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

    def test_past_event_registration_blocked(self):
        frappe.set_user(self.user)
        # Create an event in the past (2 days ago)
        past_start = add_to_date(now_datetime(), days=-2)
        past_end = add_to_date(now_datetime(), days=-1)
        past_event = self.create_test_event("Past Event", past_start, past_end)

        # Check status is automatically Completed
        event_doc = frappe.get_doc("Event Activity", past_event)
        event_doc.update_status()
        self.assertEqual(event_doc.event_status, "Completed")

        # Attempt registration should raise ValidationError
        reg = frappe.new_doc("Event Attendee")
        reg.event_activity = past_event
        self.assertRaises(frappe.ValidationError, reg.insert, ignore_permissions=True)

    def create_test_promo_code(self, name, limit=5, discount=10):
        if frappe.db.exists("Event Promo Code", name):
            frappe.delete_doc("Event Promo Code", name, ignore_permissions=True)
        doc = frappe.new_doc("Event Promo Code")
        doc.name = name
        doc.active = 1
        doc.usage_limit = limit
        doc.discount_percentage = discount
        doc.promo_type = "Global"
        doc.insert(ignore_permissions=True)
        return doc.name

    def test_promo_code_lifecycle(self):
        frappe.set_user(self.user)
        promo_name = "TESTPROMO"
        self.create_test_promo_code(promo_name, limit=2, discount=15)

        # 1. Create attendee with promo code (User 1)
        reg1 = frappe.new_doc("Event Attendee")
        reg1.event_activity = self.event1
        reg1.promo_code = promo_name
        reg1.event_is_paid = "Paid"
        reg1.event_price = 100.0
        reg1.insert(ignore_permissions=True)

        # Verify discount applied
        self.assertEqual(reg1.final_price, 85.0)

        # Verify times_used is 1
        times_used = frappe.db.get_value("Event Promo Code", promo_name, "times_used")
        self.assertEqual(times_used, 1)

        # Create User 2
        self.user2 = "test_attendee2@example.com"
        if not frappe.db.exists("User", self.user2):
            u2 = frappe.new_doc("User")
            u2.email = self.user2
            u2.first_name = "Test2"
            u2.last_name = "Attendee"
            u2.send_welcome_email = 0
            u2.insert(ignore_permissions=True)

        frappe.set_user(self.user2)

        # 2. Add second registration using the same promo code (User 2)
        reg2 = frappe.new_doc("Event Attendee")
        reg2.event_activity = self.event3
        reg2.promo_code = promo_name
        reg2.event_is_paid = "Paid"
        reg2.event_price = 100.0
        reg2.user = self.user2
        reg2.insert(ignore_permissions=True)

        # Verify times_used is 2 (limit reached)
        times_used = frappe.db.get_value("Event Promo Code", promo_name, "times_used")
        self.assertEqual(times_used, 2)

        # Create User 3
        self.user3 = "test_attendee3@example.com"
        if not frappe.db.exists("User", self.user3):
            u3 = frappe.new_doc("User")
            u3.email = self.user3
            u3.first_name = "Test3"
            u3.last_name = "Attendee"
            u3.send_welcome_email = 0
            u3.insert(ignore_permissions=True)

        frappe.set_user(self.user3)

        # 3. Third registration should fail due to usage limit reached (User 3)
        event4 = self.create_test_event("Event 4", add_to_date(self.end1, hours=2), add_to_date(self.end1, hours=4))
        reg3 = frappe.new_doc("Event Attendee")
        reg3.event_activity = event4
        reg3.promo_code = promo_name
        reg3.event_is_paid = "Paid"
        reg3.event_price = 100.0
        reg3.user = self.user3
        
        self.assertRaises(frappe.ValidationError, reg3.insert, ignore_permissions=True)

        # 4. Cancel reg1 (User 1's registration - this should free up one usage slot)
        frappe.set_user(self.user)
        reg1.status = "Canceled"
        reg1.save(ignore_permissions=True)

        # Verify times_used is decremented to 1
        times_used = frappe.db.get_value("Event Promo Code", promo_name, "times_used")
        self.assertEqual(times_used, 1)

        # 5. Now reg3 should pass because one slot was freed
        frappe.set_user(self.user3)
        reg3.insert(ignore_permissions=True)
        times_used = frappe.db.get_value("Event Promo Code", promo_name, "times_used")
        self.assertEqual(times_used, 2)

        # 6. Delete reg3 (this should decrement usage count)
        frappe.delete_doc("Event Attendee", reg3.name, ignore_permissions=True)
        times_used = frappe.db.get_value("Event Promo Code", promo_name, "times_used")
        self.assertEqual(times_used, 1)


