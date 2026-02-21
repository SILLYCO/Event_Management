import frappe
from frappe.utils import get_datetime

def get_context(context):
    # 1. Fetch all events from the database
    events = frappe.get_all(
        "Event Activity",
        fields=[
            "name", 
            "event_title", 
            "event_category", 
            "event_status", 
            "start_date", 
            "event_image", 
            "route", 
            "event_description"
        ],
        order_by="start_date desc"
    )

    # --- NEW: Extract unique categories for our filter buttons ---
    categories = set()
    for e in events:
        if e.event_category:
            categories.add(e.event_category)
    context.categories = sorted(list(categories))
    # -------------------------------------------------------------

    # 2. Fetch the current logged-in user's RSVPs
    user_status_map = {}
    if frappe.session.user != "Guest":
        attendances = frappe.get_all(
            "Event Attendee",
            filters={"user": frappe.session.user},
            fields=["event_activity", "status"],
            order_by="creation desc"
        )
        
        for att in attendances:
            if att.event_activity not in user_status_map:
                user_status_map[att.event_activity] = att.status

    # 3. Format dates and attach the user's status
    for event in events:
        if event.start_date:
            event.formatted_date = get_datetime(event.start_date).strftime('%A, %d-%m-%Y %I:%M %p')
        else:
            event.formatted_date = "TBA"
            
        event.user_status = user_status_map.get(event.name)

    # Send the data to the HTML template
    context.events = events