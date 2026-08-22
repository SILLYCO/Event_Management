import json
import frappe
from frappe.utils import get_datetime, now_datetime, flt

def get_context(context):
    # Enforce authentication
    if frappe.session.user == "Guest":
        frappe.msgprint("Please log in to view your events and tickets.", alert=True)
        frappe.local.flags.redirect_location = "/login?redirect-to=/my-events"
        raise frappe.Redirect

    context.no_footer = 1
    context.hide_footer = 1
    context.title = "My Events & Tickets"

    user = frappe.session.user
    context.user_email = user
    user_doc = frappe.get_doc("User", user)
    context.user_fullname = user_doc.full_name or user_doc.first_name or user

    # 1. Fetch all registrations for the logged-in user
    attendees = frappe.get_all(
        "Event Attendee",
        filters={"user": user},
        fields=[
            "name", "event_activity", "status", "promo_code", 
            "event_price", "final_price", "paid_amount", "remaining_amount", 
            "payment_method", "custom_answers", "date", "rejection_reason"
        ],
        order_by="date desc"
    )

    # 2. Fetch linked Event Activity details
    event_names = list({a.event_activity for a in attendees if a.event_activity})
    events_map = {}
    if event_names:
        event_docs = frappe.get_all(
            "Event Activity",
            filters={"name": ["in", event_names]},
            fields=[
                "name", "event_title", "event_category", "start_date", "end_date",
                "event_image", "route", "is_paid", "ticket_price", "event_status",
                "event_description"
            ]
        )
        for ev in event_docs:
            events_map[ev.name] = ev

    # 3. Fetch all Payment Entries for attendee records
    attendee_names = [a.name for a in attendees]
    payments_map = {}
    if attendee_names:
        payment_entries = frappe.get_all(
            "Event Payment Entry",
            filters={"parent": ["in", attendee_names], "parenttype": "Event Attendee"},
            fields=[
                "parent", "payment_date", "amount", "payment_method", 
                "status", "transaction_reference", "receipt_image", "rejection_reason", "notes"
            ],
            order_by="payment_date asc"
        )
        for pe in payment_entries:
            payments_map.setdefault(pe.parent, []).append(pe)

    now = now_datetime()
    confirmed_tickets = []
    pending_actions = []
    past_events = []
    cancelled_tickets = []

    total_spent = 0.0

    for a in attendees:
        ev = events_map.get(a.event_activity)
        if not ev:
            continue

        # Format Dates
        start_dt = get_datetime(ev.start_date) if ev.start_date else None
        end_dt = get_datetime(ev.end_date) if ev.end_date else start_dt
        
        a.event_title = ev.event_title
        a.event_category = ev.event_category or "Event"
        a.event_image = ev.event_image
        a.route = ev.route or f"events/{ev.name}"
        a.event_status = ev.event_status
        a.is_paid = ev.is_paid
        a.ticket_price = flt(ev.ticket_price)
        a.final_price = flt(a.final_price or ev.ticket_price)
        a.paid_amount = flt(a.paid_amount or 0.0)
        a.remaining_amount = flt(a.remaining_amount if a.remaining_amount is not None else max(0.0, a.final_price - a.paid_amount))
        a.formatted_start_date = start_dt.strftime('%a, %d %b %Y • %I:%M %p') if start_dt else "TBA"
        a.formatted_end_date = end_dt.strftime('%a, %d %b %Y • %I:%M %p') if end_dt else None
        a.start_date_iso = start_dt.isoformat() if start_dt else ""
        a.end_date_iso = end_dt.isoformat() if end_dt else ""
        a.event_description = ev.event_description or ""

        # Parse Custom Form Answers
        a.custom_fields_list = []
        if a.custom_answers:
            try:
                answers_dict = json.loads(a.custom_answers) if isinstance(a.custom_answers, str) else a.custom_answers
                for label, val in answers_dict.items():
                    if val:
                        a.custom_fields_list.append({"label": label, "value": str(val)})
            except Exception:
                pass

        a.payment_entries = payments_map.get(a.name, [])
        a.approved_payments_count = sum(1 for p in a.payment_entries if p.status == "Approved")
        a.pending_payments_count = sum(1 for p in a.payment_entries if p.status == "Pending Verification")

        if a.status == "Registered":
            total_spent += a.paid_amount
            # Check if event is past
            is_past = (end_dt and end_dt < now) or ev.event_status == "Completed"
            if is_past:
                past_events.append(a)
            else:
                confirmed_tickets.append(a)
        elif a.status in ["Pending Transaction", "Pending Approval"]:
            pending_actions.append(a)
        elif a.status in ["Canceled", "Rejected"]:
            cancelled_tickets.append(a)

    context.confirmed_tickets = confirmed_tickets
    context.pending_actions = pending_actions
    context.past_events = past_events
    context.cancelled_tickets = cancelled_tickets

    context.kpi_confirmed = len(confirmed_tickets)
    context.kpi_pending = len(pending_actions)
    context.kpi_past = len(past_events)
    context.kpi_total_spent = total_spent
