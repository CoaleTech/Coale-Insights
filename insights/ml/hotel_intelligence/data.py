# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""
Hotel Intelligence - Centralized Data Layer

All SQL queries against Hoteli DocTypes. Each function returns list[dict] via
frappe.db.sql(as_dict=True). Tables are checked for existence before querying
so the module degrades gracefully when specific DocTypes are absent.
"""

import frappe
from insights.api.ml import get_date_filter_sql


def _table_exists(doctype: str) -> bool:
    """Check if a DocType table exists in the database"""
    try:
        return frappe.db.exists("DocType", doctype) is not None
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Hotel Reservation
# ---------------------------------------------------------------------------

def get_reservations(start_date: str, end_date: str) -> list:
    """
    Get reservations within date range.
    Fields: name, arrival_date, departure_date, status, room_rate, total_amount,
    paid_amount, outstanding_amount, adults, children, meal_plan, booking_source,
    guest, customer, nights, guest_name, check_in_type
    """
    if not _table_exists("Hotel Reservation"):
        return []

    return frappe.db.sql("""
        SELECT
            hr.name,
            hr.arrival_date,
            hr.departure_date,
            hr.status,
            hr.room_rate,
            hr.total_amount,
            hr.paid_amount,
            hr.outstanding_amount,
            hr.adults,
            hr.children,
            hr.meal_plan,
            hr.booking_source,
            hr.guest,
            hr.customer,
            hr.nights,
            hr.guest_name,
            hr.check_in_type,
            hr.total_rooms,
            hr.total_guests
        FROM `tabHotel Reservation` hr
        WHERE hr.arrival_date BETWEEN %(start_date)s AND %(end_date)s
            AND hr.status != 'Cancelled'
        ORDER BY hr.arrival_date
    """, {"start_date": start_date, "end_date": end_date}, as_dict=True)


def get_reservations_for_date(target_date: str) -> list:
    """
    Get reservations that overlap a specific date (for daily occupancy).
    A reservation overlaps if arrival_date <= target_date < departure_date
    and status is Checked In or Check In Arrival.
    """
    if not _table_exists("Hotel Reservation"):
        return []

    return frappe.db.sql("""
        SELECT
            hr.name,
            hr.arrival_date,
            hr.departure_date,
            hr.status,
            hr.total_rooms,
            hr.adults,
            hr.children,
            hr.total_guests
        FROM `tabHotel Reservation` hr
        WHERE hr.arrival_date <= %(target_date)s
            AND hr.departure_date > %(target_date)s
            AND hr.status IN ('Checked In', 'Check In Arrival')
    """, {"target_date": target_date}, as_dict=True)


# ---------------------------------------------------------------------------
# Hotel Room
# ---------------------------------------------------------------------------

def get_rooms() -> list:
    """
    Get all hotel rooms.
    Fields: name, room_number, room_type, status, total_beds, beds_occupied,
    beds_available, max_occupancy, room_rate, floor, building_wing,
    housekeeping_status, maintenance_status
    """
    if not _table_exists("Hotel Room"):
        return []

    return frappe.db.sql("""
        SELECT
            r.name,
            r.room_number,
            r.room_type,
            r.status,
            r.total_beds,
            r.beds_occupied,
            r.beds_available,
            r.max_occupancy,
            r.room_rate,
            r.floor,
            r.building_wing,
            r.housekeeping_status,
            r.maintenance_status
        FROM `tabHotel Room` r
        ORDER BY r.room_number
    """, as_dict=True)


# ---------------------------------------------------------------------------
# Hotel Guest
# ---------------------------------------------------------------------------

def get_guests(start_date: str, end_date: str) -> list:
    """
    Get guest records. Uses last_visit_date for date filtering when available.
    Fields: name, guest_name, total_stays, total_nights, total_spent,
    last_visit_date, vip_status, nationality, linked_customer
    """
    if not _table_exists("Hotel Guest"):
        return []

    return frappe.db.sql("""
        SELECT
            g.name,
            g.guest_name,
            g.total_stays,
            g.total_nights,
            g.total_spent,
            g.last_visit_date,
            g.vip_status,
            g.nationality,
            g.linked_customer
        FROM `tabHotel Guest` g
        WHERE (
            g.last_visit_date BETWEEN %(start_date)s AND %(end_date)s
            OR g.last_visit_date IS NULL
            OR g.creation BETWEEN %(start_date)s AND %(end_date)s
        )
        ORDER BY g.total_spent DESC
    """, {"start_date": start_date, "end_date": end_date}, as_dict=True)


def get_all_guests() -> list:
    """Get all guest records regardless of date range (for lifetime metrics)."""
    if not _table_exists("Hotel Guest"):
        return []

    return frappe.db.sql("""
        SELECT
            g.name,
            g.guest_name,
            g.total_stays,
            g.total_nights,
            g.total_spent,
            g.last_visit_date,
            g.vip_status,
            g.nationality,
            g.linked_customer
        FROM `tabHotel Guest` g
        ORDER BY g.total_spent DESC
    """, as_dict=True)


# ---------------------------------------------------------------------------
# Reservation Room (child table of Hotel Reservation)
# ---------------------------------------------------------------------------

def get_reservation_rooms(start_date: str, end_date: str) -> list:
    """
    Get reservation room details joined with parent reservation.
    Fields: reservation, room_type, room, rate, adults, children,
    beds_selected, arrival_date, departure_date, status, nights
    """
    if not _table_exists("Reservation Room"):
        return []

    return frappe.db.sql("""
        SELECT
            rr.parent as reservation,
            rr.room_type,
            rr.room,
            rr.rate,
            rr.adults,
            rr.children,
            rr.beds_selected,
            hr.arrival_date,
            hr.departure_date,
            hr.status,
            hr.nights
        FROM `tabReservation Room` rr
        JOIN `tabHotel Reservation` hr ON rr.parent = hr.name
        WHERE hr.arrival_date BETWEEN %(start_date)s AND %(end_date)s
            AND hr.status != 'Cancelled'
        ORDER BY hr.arrival_date
    """, {"start_date": start_date, "end_date": end_date}, as_dict=True)


# ---------------------------------------------------------------------------
# Event Booking
# ---------------------------------------------------------------------------

def get_event_bookings(start_date: str, end_date: str) -> list:
    """
    Get event bookings within date range (using event_days child table dates).
    Fields: name, event_name, event_type, total_amount, grand_total,
    total_expected_guests, total_actual_guests, status, banquet_hall,
    banquet_hall_name, days_completed, creation
    """
    if not _table_exists("Event Booking"):
        return []

    return frappe.db.sql("""
        SELECT DISTINCT
            eb.name,
            eb.event_name,
            eb.event_type,
            eb.total_amount,
            eb.grand_total,
            eb.total_expected_guests,
            eb.total_actual_guests,
            eb.status,
            eb.banquet_hall,
            eb.banquet_hall_name,
            eb.days_completed,
            eb.creation
        FROM `tabEvent Booking` eb
        LEFT JOIN `tabEvent Booking Day` ebd ON ebd.parent = eb.name
        WHERE (
            ebd.event_date BETWEEN %(start_date)s AND %(end_date)s
            OR eb.creation BETWEEN %(start_date)s AND %(end_date)s
        )
        AND eb.docstatus = 1
        AND eb.status != 'Cancelled'
        ORDER BY eb.creation DESC
    """, {"start_date": start_date, "end_date": end_date}, as_dict=True)


def get_event_days(start_date: str, end_date: str) -> list:
    """Get individual event days for trend analysis."""
    if not _table_exists("Event Booking Day"):
        return []

    return frappe.db.sql("""
        SELECT
            ebd.parent as event_booking,
            ebd.event_date,
            ebd.banquet_hall,
            ebd.expected_guests,
            ebd.actual_guests,
            ebd.day_status,
            ebd.day_amount,
            eb.event_type,
            eb.status as booking_status
        FROM `tabEvent Booking Day` ebd
        JOIN `tabEvent Booking` eb ON ebd.parent = eb.name
        WHERE ebd.event_date BETWEEN %(start_date)s AND %(end_date)s
            AND eb.docstatus = 1
            AND eb.status != 'Cancelled'
        ORDER BY ebd.event_date
    """, {"start_date": start_date, "end_date": end_date}, as_dict=True)


def get_banquet_halls() -> list:
    """Get all banquet halls with capacity info."""
    if not _table_exists("Banquet Hall"):
        return []

    return frappe.db.sql("""
        SELECT
            bh.name,
            bh.hall_name,
            bh.hall_type,
            bh.capacity,
            bh.is_active,
            bh.base_hourly_rate,
            bh.base_daily_rate
        FROM `tabBanquet Hall` bh
        WHERE bh.is_active = 1
        ORDER BY bh.hall_name
    """, as_dict=True)


# ---------------------------------------------------------------------------
# Restaurant / POS (Sales Invoice)
# ---------------------------------------------------------------------------

def get_restaurant_orders(start_date: str, end_date: str) -> list:
    """
    Get POS (restaurant) orders from Sales Invoice where is_pos=1.
    Fields: name, posting_date, creation, grand_total, net_total,
    pos_profile, customer, status
    """
    if not _table_exists("Sales Invoice"):
        return []

    return frappe.db.sql("""
        SELECT
            si.name,
            si.posting_date,
            si.creation,
            si.grand_total,
            si.net_total,
            si.pos_profile,
            si.customer,
            si.status
        FROM `tabSales Invoice` si
        WHERE si.is_pos = 1
            AND si.docstatus = 1
            AND si.posting_date BETWEEN %(start_date)s AND %(end_date)s
        ORDER BY si.posting_date, si.creation
    """, {"start_date": start_date, "end_date": end_date}, as_dict=True)


def get_restaurant_order_items(start_date: str, end_date: str) -> list:
    """
    Get POS order line items for menu engineering analysis.
    Fields: item_code, item_name, item_group, qty, rate, amount,
    invoice, posting_date
    """
    if not _table_exists("Sales Invoice"):
        return []

    return frappe.db.sql("""
        SELECT
            sii.item_code,
            sii.item_name,
            sii.item_group,
            sii.qty,
            sii.rate,
            sii.amount,
            sii.parent as invoice,
            si.posting_date
        FROM `tabSales Invoice Item` sii
        JOIN `tabSales Invoice` si ON sii.parent = si.name
        WHERE si.is_pos = 1
            AND si.docstatus = 1
            AND si.posting_date BETWEEN %(start_date)s AND %(end_date)s
        ORDER BY si.posting_date
    """, {"start_date": start_date, "end_date": end_date}, as_dict=True)


def get_item_costs(item_codes: list) -> list:
    """Get item valuation rates for contribution margin calculation."""
    if not item_codes:
        return []

    # Build IN clause safely
    placeholders = ", ".join(["%s"] * len(item_codes))
    return frappe.db.sql(f"""
        SELECT
            i.name as item_code,
            i.item_name,
            i.item_group,
            COALESCE(i.valuation_rate, i.standard_rate, 0) as cost_price
        FROM `tabItem` i
        WHERE i.name IN ({placeholders})
    """, tuple(item_codes), as_dict=True)


def get_restaurant_sections() -> list:
    """Get restaurant sections with capacity and hours."""
    if not _table_exists("Restaurant Section"):
        return []

    return frappe.db.sql("""
        SELECT
            rs.name,
            rs.section_name,
            rs.capacity,
            rs.opening_time,
            rs.closing_time,
            rs.is_active
        FROM `tabRestaurant Section` rs
        WHERE rs.is_active = 1
        ORDER BY rs.section_name
    """, as_dict=True)


# ---------------------------------------------------------------------------
# Housekeeping Task
# ---------------------------------------------------------------------------

def get_housekeeping_tasks(start_date: str, end_date: str) -> list:
    """
    Get housekeeping tasks within date range.
    Fields: name, task_type, priority, status, scheduled_date, room,
    assigned_to, started_at, completed_at, actual_duration,
    verification_status, quality_rating
    """
    if not _table_exists("Housekeeping Task"):
        return []

    return frappe.db.sql("""
        SELECT
            ht.name,
            ht.task_type,
            ht.priority,
            ht.status,
            ht.scheduled_date,
            ht.room,
            ht.assigned_to,
            ht.started_at,
            ht.completed_at,
            ht.actual_duration,
            ht.verification_status,
            ht.quality_rating
        FROM `tabHousekeeping Task` ht
        WHERE ht.scheduled_date BETWEEN %(start_date)s AND %(end_date)s
        ORDER BY ht.scheduled_date
    """, {"start_date": start_date, "end_date": end_date}, as_dict=True)
