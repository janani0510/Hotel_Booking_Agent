import os
import re
from datetime import date, datetime
from decimal import Decimal

import mysql.connector
import streamlit as st
from dotenv import load_dotenv
from google import genai

load_dotenv()

api_key = os.getenv("GEMINI_API_KEY")

if api_key:
    gemini_client = genai.Client(api_key=api_key)
else:
    gemini_client = None


def get_connection():
    return mysql.connector.connect(
        host=os.getenv("MYSQL_HOST", "localhost"),
        user=os.getenv("MYSQL_USER", "root"),
        password=os.getenv("MYSQL_PASSWORD", "janani@1005"),
        database=os.getenv("MYSQL_DATABASE", "hotel_booking"),
    )


def check_room_availability(check_in, check_out, bed_type, breakfast):
    """Return rooms matching the requested bed/breakfast and dates."""
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            """
            SELECT r.*
            FROM rooms r
            WHERE r.bed_type = %s
              AND r.breakfast = %s
              AND NOT EXISTS (
                  SELECT 1
                  FROM bookings b
                  WHERE b.room_no = r.room_no
                    AND b.booking_status = 'Confirmed'
                    AND b.check_in < %s
                    AND b.check_out > %s
              )
            ORDER BY r.price_per_night
            """,
            (bed_type, breakfast, check_out, check_in),
        )
        return cursor.fetchall()
    finally:
        cursor.close()
        conn.close()


def check_alternative_rooms(check_in, check_out, bed_type, breakfast):
    """Return up to two available rooms that differ from the exact preference."""
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            """
            SELECT r.*
            FROM rooms r
            WHERE NOT EXISTS (
                SELECT 1
                FROM bookings b
                WHERE b.room_no = r.room_no
                  AND b.booking_status = 'Confirmed'
                  AND b.check_in < %s
                  AND b.check_out > %s
            )
            ORDER BY
                (r.bed_type = %s) DESC,
                (r.breakfast = %s) DESC,
                r.price_per_night
            LIMIT 2
            """,
            (check_out, check_in, bed_type, breakfast),
        )
        return cursor.fetchall()
    finally:
        cursor.close()
        conn.close()


def save_booking(room_no, guest_name, guest_email, check_in, check_out, guests):
    """Create a booking only if the room is not already booked for the dates."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        conn.start_transaction()
        cursor.execute(
            """
            SELECT room_no
            FROM rooms
            WHERE room_no = %s
            FOR UPDATE
            """,
            (room_no,),
        )
        if cursor.fetchone() is None:
            conn.rollback()
            return None, "That room could not be found."

        cursor.execute(
            """
            SELECT booking_id
            FROM bookings
            WHERE room_no = %s
              AND booking_status = 'Confirmed'
              AND check_in < %s
              AND check_out > %s
            LIMIT 1
            """,
            (room_no, check_out, check_in),
        )
        if cursor.fetchone():
            conn.rollback()
            return None, "Sorry, that room was just booked for those dates. Please search again."

        cursor.execute(
            """
            INSERT INTO bookings
                (room_no, guest_name, guest_email, check_in, check_out, guests, booking_status)
            VALUES (%s, %s, %s, %s, %s, %s, 'Confirmed')
            """,
            (room_no, guest_name, guest_email, check_in, check_out, guests),
        )
        booking_id = cursor.lastrowid
        conn.commit()
        return booking_id, None
    except mysql.connector.Error as error:
        conn.rollback()
        return None, f"Database error: {error}"
    finally:
        cursor.close()
        conn.close()


def room_summary(room):
    breakfast = "Included" if room["breakfast"] else "Not included"
    price = Decimal(str(room["price_per_night"]))
    return (
        f"Room {room['room_no']} — {room['room_type']} | "
        f"{room['bed_type']} bed | Breakfast: {breakfast} | "
        f"₹{price:,.2f}/night"
    )


def reset_conversation():
    for key in list(st.session_state.keys()):
        if key.startswith("chat_") or key == "messages":
            del st.session_state[key]
    st.session_state.messages = [
        {
            "role": "assistant",
            "content": (
                "Hello! Welcome to our hotel booking assistant. "
                "Let’s find a room. What are your check-in and check-out dates?"
            ),
        }
    ]
    st.session_state.chat_step = "dates"
    st.session_state.chat_check_in = None
    st.session_state.chat_check_out = None
    st.session_state.chat_bed_type = None
    st.session_state.chat_breakfast = None
    st.session_state.chat_guests = 1
    st.session_state.chat_rooms = []
    st.session_state.chat_selected_room = None
    st.session_state.chat_guest_name = ""
    st.session_state.chat_guest_email = ""
    st.session_state.chat_booking_id = None


st.set_page_config(page_title="Conversational Hotel Booking Agent", page_icon="🏨")
st.title("🏨 Conversational Hotel Booking Agent")
st.caption("A Streamlit conversational prototype connected to MySQL.")

if "chat_step" not in st.session_state:
    reset_conversation()

with st.sidebar:
    st.subheader("Conversation controls")
    if st.button("Start a new conversation"):
        reset_conversation()
        st.rerun()
    st.caption("Bookings are saved in your hotel_booking MySQL database.")
    st.caption("Email confirmation is shown as a demo preview; no email is sent.")



def extract_booking_details(user_message):
    if gemini_client is None:
        return None

    try:
        response = gemini_client.models.generate_content(
            model="gemini-3.8-flash",
            contents=f"""
Extract hotel booking details from the user's message.
Return ONLY valid JSON with these keys:
check_in, check_out, bed_type, breakfast, guests.

Rules:
- Dates must use YYYY-MM-DD format.
- bed_type must be "Single", "Double", or null.
- breakfast must be true, false, or null.
- guests must be an integer or null.
- Use null for any detail the user did not provide.
- Do not guess missing dates or preferences.
- Today's date is {date.today()}.
- User message: {user_message}
"""
        )

        import json
        result = json.loads(response.text.strip().replace("```json", "").replace("```", ""))
        return result

    except Exception as e:
        st.error(f"Could not extract booking details: {e}")
        return None




def get_gemini_response(user_message):
    if gemini_client is None:
        return "I'm your hotel booking assistant. I can help you find rooms and complete a booking."

    try:
        response = gemini_client.models.generate_content(
            model="gemini-3.8-flash",
            contents=(
                "You are a polite hotel booking assistant. "
                "Use simple, friendly English. Help users understand "
                "room types, breakfast options, dates, prices, and booking steps. "
                "Never invent room availability, prices, or booking IDs. "
                "The Python application checks availability and confirms bookings. "
                "If information is missing, ask a short clarifying question.\n\n"
                f"User message: {user_message}"
            ),
        )
        return response.text or "I can help you with your hotel booking."
    except Exception as e:
        return f"Gemini error: {e}"


for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

def add_message(role, content):
    st.session_state.messages.append({"role": role, "content": content})




if prompt := st.chat_input("Ask me about your hotel booking..."):
    add_message("user", prompt)

    details = extract_booking_details(prompt)

    if details and any(
        details.get(key) is not None
        for key in ["check_in", "check_out", "bed_type", "breakfast", "guests"]
    ):
        try:
            check_in = (
                date.fromisoformat(details["check_in"])
                if details.get("check_in") else None
            )
            check_out = (
                date.fromisoformat(details["check_out"])
                if details.get("check_out") else None
            )

            if check_in and check_in < date.today():
                reply = "Check-in date cannot be in the past. Please provide a future date."

            elif check_in and check_out and check_out <= check_in:
                reply = "Check-out must be after check-in. Please correct your dates."

            else:
                if check_in:
                    st.session_state.chat_check_in = check_in
                if check_out:
                    st.session_state.chat_check_out = check_out
                if details.get("bed_type") in ("Single", "Double"):
                    st.session_state.chat_bed_type = details["bed_type"]
                if details.get("breakfast") is not None:
                    st.session_state.chat_breakfast = details["breakfast"]
                if details.get("guests") is not None:
                    guests = int(details["guests"])
                    if 1 <= guests <= 10:
                        st.session_state.chat_guests = guests

                if (
                    st.session_state.chat_check_in
                    and st.session_state.chat_check_out
                    and st.session_state.chat_check_out > st.session_state.chat_check_in
                    and st.session_state.chat_bed_type
                    and st.session_state.chat_breakfast is not None
                ):
                    rooms = check_room_availability(
                        st.session_state.chat_check_in,
                        st.session_state.chat_check_out,
                        st.session_state.chat_bed_type,
                        st.session_state.chat_breakfast,
                    )
                    st.session_state.chat_rooms = rooms

                    if rooms:
                        st.session_state.chat_step = "choose_room"
                        reply = (
                            f"I found {len(rooms)} matching room(s). "
                            "Choose a room below to review its price before booking."
                        )
                    else:
                        reply = (
                            "Sorry, no exact matching rooms are available "
                            "for those dates. Please try changing your dates or preferences."
                        )
                else:
                    reply = (
                        "Thanks! Please provide your check-in and check-out dates, "
                        "bed type (Single or Double), and breakfast preference "
                        "so I can check availability."
                    )

        except (ValueError, TypeError, KeyError):
            reply = "I couldn't understand the dates or booking details. Please enter them clearly."
        except mysql.connector.Error as error:
            reply = f"I couldn't check room availability in the database: {error}"

        add_message("assistant", reply)
    else:
        reply = get_gemini_response(prompt)
        add_message("assistant", reply)

    st.rerun()



step = st.session_state.chat_step

if step == "dates":
    with st.form("chat_dates_form"):
        check_in = st.date_input("Check-in date", min_value=date.today(), value=date.today())
        default_out = date.today().fromordinal(date.today().toordinal() + 1)
        check_out = st.date_input(
            "Check-out date",
            min_value=date.today(),
            value=default_out if default_out > date.today() else date.today(),
        )
        submitted = st.form_submit_button("Send dates")
    if submitted:
        add_message("user", f"Check-in: {check_in}; Check-out: {check_out}")
        if check_in < date.today():
            add_message("assistant", "Check-in cannot be in the past. Please enter valid dates.")
        elif check_out <= check_in:
            add_message("assistant", "Check-out must be after check-in. Please try again.")
        else:
            st.session_state.chat_check_in = check_in
            st.session_state.chat_check_out = check_out
            st.session_state.chat_step = "preferences"
            add_message("assistant", "Thanks! Would you like a single or double bed, and should breakfast be included?")
        st.rerun()

elif step == "preferences":
    with st.form("chat_preferences_form"):
        bed_type = st.radio("Bed type", ["Single", "Double"], horizontal=True)
        breakfast_label = st.radio("Breakfast included?", ["Yes", "No"], horizontal=True)
        guests = st.number_input("Number of guests", min_value=1, max_value=10, value=1, step=1)
        submitted = st.form_submit_button("Find my room")
    if submitted:
        breakfast = breakfast_label == "Yes"
        add_message("user", f"{bed_type} bed; breakfast: {breakfast_label}; guests: {guests}")
        try:
            rooms = check_room_availability(
                st.session_state.chat_check_in,
                st.session_state.chat_check_out,
                bed_type,
                breakfast,
            )
            st.session_state.chat_bed_type = bed_type
            st.session_state.chat_breakfast = breakfast
            st.session_state.chat_guests = int(guests)
            st.session_state.chat_rooms = rooms
            if rooms:
                st.session_state.chat_step = "choose_room"
                add_message("assistant", f"I found {len(rooms)} matching room(s). Please choose one below. I’ll show the price before you commit.")
            else:
                alternatives = check_alternative_rooms(
                    st.session_state.chat_check_in,
                    st.session_state.chat_check_out,
                    bed_type,
                    breakfast,
                )
                st.session_state.chat_rooms = alternatives
                if alternatives:
                    st.session_state.chat_step = "choose_alternative"
                    add_message("assistant", "No exact match is available. Here are up to two alternatives. You can choose one or decline.")
                else:
                    st.session_state.chat_step = "no_rooms"
                    add_message("assistant", "Sorry, no rooms are available for those dates. Please start a new conversation to try different dates.")
        except mysql.connector.Error as error:
            add_message("assistant", f"I couldn't access the room database: {error}")
        st.rerun()

elif step in ("choose_room", "choose_alternative"):
    rooms = st.session_state.chat_rooms
    for index, room in enumerate(rooms):
        st.write(room_summary(room))
        nights = (st.session_state.chat_check_out - st.session_state.chat_check_in).days
        total = Decimal(str(room["price_per_night"])) * nights
        st.caption(f"{nights} night(s) · Total before booking: ₹{total:,.2f}")
        col1, col2 = st.columns(2)
        with col1:
            if st.button("Choose this room", key=f"choose_room_{step}_{room['room_no']}"):
                st.session_state.chat_selected_room = room
                st.session_state.chat_step = "guest_details"
                add_message("user", f"I choose Room {room['room_no']}.")
                add_message("assistant", "Great. Please enter your name and email address to review the booking before confirming.")
                st.rerun()
        if step == "choose_alternative":
            with col2:
                if st.button("Decline alternatives", key=f"decline_{room['room_no']}"):
                    st.session_state.chat_step = "no_rooms"
                    add_message("user", "I don't want these alternatives.")
                    add_message("assistant", "No problem. You can start a new conversation and change your dates or preferences.")
                    st.rerun()
    if step == "choose_alternative" and st.button("Decline all alternatives", key="decline_all"):
        st.session_state.chat_step = "no_rooms"
        add_message("user", "I decline all alternatives.")
        add_message("assistant", "No problem. Start a new conversation to try different dates or preferences.")
        st.rerun()

elif step == "guest_details":
    room = st.session_state.chat_selected_room
    nights = (st.session_state.chat_check_out - st.session_state.chat_check_in).days
    price = Decimal(str(room["price_per_night"]))
    total = price * nights
    st.subheader("Review before confirming")
    st.write(f"**Room:** {room['room_no']} — {room['room_type']}")
    st.write(f"**Stay:** {st.session_state.chat_check_in} to {st.session_state.chat_check_out} ({nights} night(s))")
    st.write(f"**Guests:** {st.session_state.chat_guests}")
    st.write(f"**Price:** ₹{price:,.2f} per night")
    st.write(f"**Total:** ₹{total:,.2f}")
    with st.form("chat_guest_details_form"):
        guest_name = st.text_input("Full name")
        guest_email = st.text_input("Email address")
        confirm = st.form_submit_button("Confirm booking")
    if confirm:
        add_message("user", f"Name: {guest_name}; Email: {guest_email}; request to confirm booking")
        if not guest_name.strip():
            st.error("Please enter your name.")
        elif not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", guest_email.strip()):
            st.error("Please enter a valid email address.")
        else:
            booking_id, error = save_booking(
                room["room_no"],
                guest_name.strip(),
                guest_email.strip(),
                st.session_state.chat_check_in,
                st.session_state.chat_check_out,
                st.session_state.chat_guests,
            )
            if error:
                add_message("assistant", error)
                st.session_state.chat_step = "preferences"
                st.session_state.chat_rooms = []
                st.rerun()
            else:
                st.session_state.chat_guest_name = guest_name.strip()
                st.session_state.chat_guest_email = guest_email.strip()
                st.session_state.chat_step = "confirmed"
                add_message("assistant", f"Your booking is confirmed! Your booking ID is **{booking_id}**. The confirmation email below is a demo preview.")
                st.session_state.chat_booking_id = booking_id
                st.rerun()

elif step == "confirmed":
    room = st.session_state.chat_selected_room
    nights = (st.session_state.chat_check_out - st.session_state.chat_check_in).days
    total = Decimal(str(room["price_per_night"])) * nights
    st.success("Booking confirmed!")
    st.write(f"**Booking ID:** {st.session_state.chat_booking_id}")
    st.write(f"**Guest:** {st.session_state.chat_guest_name}")
    st.write(f"**Room:** {room['room_no']} — {room['room_type']}")
    st.write(f"**Stay:** {st.session_state.chat_check_in} to {st.session_state.chat_check_out}")
    st.write(f"**Total amount:** ₹{total:,.2f}")
    st.subheader("📧 Email confirmation preview (mock)")
    st.write(f"**To:** {st.session_state.chat_guest_email}")
    st.write("**Subject:** Hotel Booking Confirmation")
    st.markdown(
        f"Dear {st.session_state.chat_guest_name},\n\n"
        f"Your booking (ID **{st.session_state.chat_booking_id}**) for Room **{room['room_no']}** "
        f"from **{st.session_state.chat_check_in}** to **{st.session_state.chat_check_out}** "
        f"is confirmed. Total amount: **₹{total:,.2f}**.\n\n"
        "Thank you for choosing our hotel."
    )
    st.info("Demo only: no actual email has been sent.")

elif step == "no_rooms":
    st.info("No booking was made. Start a new conversation to try other dates or preferences.")



st.divider()
st.header("📋 Booking History")

if st.button("View Booking History", key="view_chat_booking_history"):
    conn = None
    cursor = None
    try:
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT
                b.booking_id,
                b.room_no,
                b.guest_name,
                b.guest_email,
                b.check_in,
                b.check_out,
                b.guests,
                b.booking_status,
                r.room_type,
                r.price_per_night,
                DATEDIFF(b.check_out, b.check_in) AS total_nights
            FROM bookings b
            JOIN rooms r ON b.room_no = r.room_no
            ORDER BY b.booking_id DESC
            """
        )
        bookings = cursor.fetchall()
        if bookings:
            for booking in bookings:
                nights = booking["total_nights"] or 0
                total_price = Decimal(str(booking["price_per_night"])) * nights
                with st.expander(
                    f"Booking ID: {booking['booking_id']} | "
                    f"Room: {booking['room_no']} | {booking['booking_status']}"
                ):
                    st.write(f"**Guest Name:** {booking['guest_name']}")
                    st.write(f"**Email:** {booking['guest_email']}")
                    st.write(f"**Room Type:** {booking['room_type']}")
                    st.write(f"**Check-in:** {booking['check_in']}")
                    st.write(f"**Check-out:** {booking['check_out']}")
                    st.write(f"**Guests:** {booking['guests']}")
                    st.write(f"**Total Nights:** {nights}")
                    st.write(f"**Price per Night:** ₹{Decimal(str(booking['price_per_night'])):,.2f}")
                    st.write(f"**Total Price:** ₹{total_price:,.2f}")
                    st.write(f"**Booking Status:** {booking['booking_status']}")
        else:
            st.info("No booking history found.")
    except mysql.connector.Error as error:
        st.error(f"Unable to load booking history: {error}")
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()



st.divider()
st.header("❌ Cancel Booking")

with st.form("cancel_chat_booking_form"):
    cancel_booking_id = st.number_input(
        "Enter Booking ID to cancel",
        min_value=1,
        step=1,
        value=1,
        key="chat_cancel_booking_id",
    )
    cancel_submitted = st.form_submit_button("Cancel Booking")

if cancel_submitted:
    conn = None
    cursor = None
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE bookings
            SET booking_status = 'Cancelled'
            WHERE booking_id = %s
              AND booking_status = 'Confirmed'
            """,
            (int(cancel_booking_id),),
        )
        if cursor.rowcount > 0:
            conn.commit()
            st.success(f"Booking ID {int(cancel_booking_id)} cancelled successfully!")
            st.info("Click 'View Booking History' above to see the updated status.")
        else:
            conn.rollback()
            st.warning("Booking not found or it is already cancelled.")
    except mysql.connector.Error as error:
        if conn:
            conn.rollback()
        st.error(f"Cancellation failed: {error}")
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()



st.divider()
st.header("📊 Hotel Dashboard")

conn = None
cursor = None
try:
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("SELECT COUNT(*) AS total_rooms FROM rooms")
    total_rooms = cursor.fetchone()["total_rooms"]

    cursor.execute("""
        SELECT
            COUNT(*) AS total_bookings,
            COALESCE(SUM(CASE WHEN booking_status = 'Confirmed' THEN 1 ELSE 0 END), 0) AS confirmed_bookings,
            COALESCE(SUM(CASE WHEN booking_status = 'Cancelled' THEN 1 ELSE 0 END), 0) AS cancelled_bookings
        FROM bookings
    """)
    booking_stats = cursor.fetchone()

    cursor.execute("""
        SELECT COUNT(*) AS available_rooms
        FROM rooms
        WHERE status = 'Available'
    """)
    available_rooms = cursor.fetchone()["available_rooms"]

    cursor.execute("""
        SELECT COALESCE(SUM(
            DATEDIFF(b.check_out, b.check_in) * r.price_per_night
        ), 0) AS total_revenue
        FROM bookings b
        JOIN rooms r ON b.room_no = r.room_no
        WHERE b.booking_status = 'Confirmed'
    """)
    total_revenue = Decimal(str(cursor.fetchone()["total_revenue"] or 0))

    col1, col2, col3 = st.columns(3)
    col1.metric("Total Rooms", total_rooms)
    col2.metric("Available Rooms", available_rooms)
    col3.metric("Total Bookings", booking_stats["total_bookings"])

    col4, col5, col6 = st.columns(3)
    col4.metric("Confirmed Bookings", booking_stats["confirmed_bookings"])
    col5.metric("Cancelled Bookings", booking_stats["cancelled_bookings"])
    col6.metric("Confirmed Booking Revenue", f"₹{total_revenue:,.2f}")

    st.caption(
        "Note: Available Rooms uses the current rooms.status value. "
        "Revenue is the total room charge for confirmed bookings, "
        "calculated from the number of nights × room price per night."
    )

except mysql.connector.Error as error:
    st.error(f"Unable to load dashboard: {error}")
finally:
    if cursor:
        cursor.close()
    if conn:
        conn.close()
