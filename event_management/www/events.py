import frappe
from frappe.utils import get_datetime

def get_context(context):
    # 1. Fetch all events (Now including Capacity for the progress bar)
    events = frappe.get_all(
        "Event Activity",
        fields=[
            "name", "event_title", "event_category", "event_status", 
            "start_date", "event_image", "route", "event_description", "capacity"
        ],
        order_by="start_date desc"
    )

    # 2. Extract unique categories for filter buttons
    categories = set()
    for e in events:
        if e.event_category:
            categories.add(e.event_category)
    context.categories = sorted(list(categories))

    # --- NEW: Extract unique statuses for the dropdown filter ---
    statuses = set()
    for e in events:
        if e.event_status:
            statuses.add(e.event_status)
    context.statuses = sorted(list(statuses))
    # ------------------------------------------------------------

    # 3. Fetch user RSVPs and calculate Total Registered per event
    user_status_map = {}
    registered_counts = {}
    
    # Get ALL registered attendees to calculate capacity urgency
    all_registered = frappe.get_all("Event Attendee", filters={"status": "Registered"}, fields=["event_activity"])
    for r in all_registered:
        registered_counts[r.event_activity] = registered_counts.get(r.event_activity, 0) + 1

    # Get the specific logged-in user's RSVPs (if logged in)
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

    # 4. Format data and calculate scarcity
    for event in events:
        if event.start_date:
            event.formatted_date = get_datetime(event.start_date).strftime('%A, %d-%m-%Y %I:%M %p')
        else:
            event.formatted_date = "TBA"
            
        event.user_status = user_status_map.get(event.name)
        
        # Scarcity Logic (calculates the percentage for the HTML progress bar)
        event.registered_count = registered_counts.get(event.name, 0)
        event.fill_percentage = 0
        if event.capacity and event.capacity > 0:
            event.fill_percentage = min(int((event.registered_count / event.capacity) * 100), 100)

    context.events = events