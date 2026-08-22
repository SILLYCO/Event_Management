import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_to_date, now_datetime

class TestEventAttendee(FrappeTestCase):
    def get_or_create_user(self, email, first_name="Test"):
        if frappe.db.exists("User", email):
            return email
        user = frappe.new_doc("User")
        user.email = email
        user.first_name = first_name
        user.send_welcome_email = 0
        user.insert(ignore_permissions=True)
        return user.name

    def setUp(self):
        frappe.set_user("Administrator")
        self.user = self.get_or_create_user("test_attendee@example.com", "Test")

        self.start1 = now_datetime()
        self.end1 = add_to_date(self.start1, hours=2)

        # Event 1: Today, duration 2 hours
        self.event1 = self.create_test_event("Event 1", self.start1, self.end1)
        # Event 2: Today, overlaps with Event 1 (starts 1 hour after Event 1 start)
        self.event2 = self.create_test_event("Event 2", add_to_date(self.start1, hours=1), add_to_date(self.start1, hours=3))
        # Event 3: Today, starts right after Event 1 ends (no overlap)
        self.event3 = self.create_test_event("Event 3", self.end1, add_to_date(self.end1, hours=2))

    def tearDown(self):
        frappe.set_user("Administrator")
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
        self.user2 = self.get_or_create_user("test_attendee2@example.com", "Test2")
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
        self.user3 = self.get_or_create_user("test_attendee3@example.com", "Test3")
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

    def test_promo_code_preserved_on_status_change(self):
        frappe.set_user(self.user)
        promo_name = "STATUSPROMO"
        self.create_test_promo_code(promo_name, limit=1, discount=20)

        # 1. User registers with promo code
        reg = frappe.new_doc("Event Attendee")
        reg.event_activity = self.event1
        reg.promo_code = promo_name
        reg.event_is_paid = "Paid"
        reg.event_price = 100.0
        reg.insert(ignore_permissions=True)

        self.assertEqual(reg.promo_code, promo_name)
        self.assertEqual(reg.final_price, 80.0)
        self.assertEqual(reg.remaining_amount, 80.0)

        # 2. Administrator updates status to Pending Transaction
        frappe.set_user("Administrator")
        reg_doc = frappe.get_doc("Event Attendee", reg.name)
        reg_doc.status = "Pending Transaction"
        reg_doc.save(ignore_permissions=True)

        reg_reloaded = frappe.get_doc("Event Attendee", reg.name)
        self.assertEqual(reg_reloaded.status, "Pending Transaction")
        self.assertEqual(reg_reloaded.promo_code, promo_name)
        self.assertEqual(reg_reloaded.final_price, 80.0)
        self.assertEqual(reg_reloaded.remaining_amount, 80.0)

        # 3. Partial payment made, then status set to Registered
        reg_reloaded.paid_amount = 60.0
        reg_reloaded.status = "Registered"
        reg_reloaded.save(ignore_permissions=True)

        reg_final = frappe.get_doc("Event Attendee", reg.name)
        self.assertEqual(reg_final.status, "Registered")
        self.assertEqual(reg_final.promo_code, promo_name)
        self.assertEqual(reg_final.final_price, 80.0)
        self.assertEqual(reg_final.paid_amount, 60.0)
        self.assertEqual(reg_final.remaining_amount, 20.0)

    def test_multi_installment_payment_ledger(self):
        frappe.set_user(self.user)

        # 1. Create attendee for 100 EGP event
        reg = frappe.new_doc("Event Attendee")
        reg.event_activity = self.event1
        reg.event_is_paid = "Paid"
        reg.event_price = 100.0
        reg.insert(ignore_permissions=True)

        self.assertEqual(reg.final_price, 100.0)
        self.assertEqual(reg.paid_amount, 0.0)
        self.assertEqual(reg.remaining_amount, 100.0)

        # 2. Add Installment 1: 30.0 with status Approved
        reg.append("payment_entries", {
            "payment_date": now_datetime(),
            "amount": 30.0,
            "payment_method": "Instapay",
            "status": "Approved",
            "transaction_reference": "INSTA-12345"
        })
        reg.save(ignore_permissions=True)

        reg_check1 = frappe.get_doc("Event Attendee", reg.name)
        self.assertEqual(reg_check1.paid_amount, 30.0)
        self.assertEqual(reg_check1.remaining_amount, 70.0)
        self.assertEqual(len(reg_check1.payment_entries), 1)

        # 3. Add Installment 2: 50.0 with status Pending Verification (should NOT increase paid_amount)
        reg_check1.append("payment_entries", {
            "payment_date": now_datetime(),
            "amount": 50.0,
            "payment_method": "Vodafone Cash",
            "status": "Pending Verification",
            "transaction_reference": "01012345678"
        })
        reg_check1.save(ignore_permissions=True)

        reg_check2 = frappe.get_doc("Event Attendee", reg.name)
        self.assertEqual(reg_check2.paid_amount, 30.0)
        self.assertEqual(reg_check2.remaining_amount, 70.0)
        self.assertEqual(len(reg_check2.payment_entries), 2)

        # 4. Add Installment 3: 20.0 with status Rejected (should NOT increase paid_amount)
        reg_check2.append("payment_entries", {
            "payment_date": now_datetime(),
            "amount": 20.0,
            "payment_method": "Cash",
            "status": "Rejected",
            "rejection_reason": "Receipt unreadable"
        })
        reg_check2.save(ignore_permissions=True)

        reg_check3 = frappe.get_doc("Event Attendee", reg.name)
        self.assertEqual(reg_check3.paid_amount, 30.0)
        self.assertEqual(reg_check3.remaining_amount, 70.0)
        self.assertEqual(len(reg_check3.payment_entries), 3)

        # 5. Admin Approves Installment 2 (50.0)
        frappe.set_user("Administrator")
        reg_check3.payment_entries[1].status = "Approved"
        reg_check3.save(ignore_permissions=True)

        reg_check4 = frappe.get_doc("Event Attendee", reg.name)
        self.assertEqual(reg_check4.paid_amount, 80.0)
        self.assertEqual(reg_check4.remaining_amount, 20.0)

    def test_submit_payment_proof_api(self):
        frappe.set_user(self.user)

        # 1. User applies (creates Pending Approval)
        reg = frappe.new_doc("Event Attendee")
        reg.event_activity = self.event1
        reg.event_is_paid = "Paid"
        reg.event_price = 100.0
        reg.insert(ignore_permissions=True)

        # 2. Administrator moves status to Pending Transaction (Payment Requested)
        frappe.set_user("Administrator")
        reg_doc = frappe.get_doc("Event Attendee", reg.name)
        reg_doc.status = "Pending Transaction"
        reg_doc.save(ignore_permissions=True)

        # 3. User submits payment proof from Web
        frappe.set_user(self.user)
        from event_management.event_management.doctype.event_attendee.event_attendee import submit_payment_proof

        res = submit_payment_proof(
            attendee_name=reg.name,
            amount=45.0,
            payment_method="Instapay",
            transaction_reference="INSTA-9999"
        )

        self.assertTrue(res.get("success"))
        # Prior to admin approval, paid_amount remains 0.0
        self.assertEqual(res.get("paid_amount"), 0.0)
        self.assertEqual(res.get("remaining_amount"), 100.0)

        reg_reloaded = frappe.get_doc("Event Attendee", reg.name)
        self.assertEqual(reg_reloaded.paid_amount, 0.0)
        self.assertEqual(reg_reloaded.remaining_amount, 100.0)
        self.assertEqual(len(reg_reloaded.payment_entries), 1)
        self.assertEqual(reg_reloaded.payment_entries[0].status, "Pending Verification")

        # 4. Administrator approves the payment entry in Desk
        frappe.set_user("Administrator")
        reg_reloaded.payment_entries[0].status = "Approved"
        reg_reloaded.save(ignore_permissions=True)

        reg_approved = frappe.get_doc("Event Attendee", reg.name)
        self.assertEqual(reg_approved.paid_amount, 45.0)
        self.assertEqual(reg_approved.remaining_amount, 55.0)

    def test_my_events_portal_context(self):
        from event_management.www.my_events import get_context

        # 1. Guest redirect check
        frappe.set_user("Guest")
        ctx = frappe._dict()
        self.assertRaises(frappe.Redirect, get_context, ctx)

        # 2. Logged-in user context check
        frappe.set_user(self.user)

        # Create confirmed registration
        reg1 = frappe.new_doc("Event Attendee")
        reg1.event_activity = self.event1
        reg1.event_is_paid = "Paid"
        reg1.event_price = 100.0
        reg1.insert(ignore_permissions=True)

        frappe.set_user("Administrator")
        reg1.status = "Registered"
        reg1.append("payment_entries", {
            "payment_date": now_datetime(),
            "amount": 100.0,
            "payment_method": "Instapay",
            "status": "Approved"
        })
        reg1.save(ignore_permissions=True)

        # Create pending registration
        frappe.set_user(self.user)
        reg2 = frappe.new_doc("Event Attendee")
        reg2.event_activity = self.event3
        reg2.event_is_paid = "Paid"
        reg2.event_price = 100.0
        reg2.insert(ignore_permissions=True) # Defaults to Pending Approval

        # Fetch context
        ctx = frappe._dict()
        get_context(ctx)

        self.assertEqual(ctx.kpi_confirmed, 1)
        self.assertEqual(ctx.kpi_pending, 1)
        self.assertEqual(len(ctx.confirmed_tickets), 1)
        self.assertEqual(len(ctx.pending_actions), 1)
        self.assertEqual(ctx.confirmed_tickets[0].name, reg1.name)
        self.assertEqual(ctx.pending_actions[0].name, reg2.name)

        # 3. Test HTTP Response
        from frappe.website.serve import get_response
        res = get_response("my_events")
        self.assertEqual(res.status_code, 200)



