
import streamlit as st
import mysql.connector
from datetime import date



def get_connection():
    return mysql.connector.connect(
        host="localhost",
        user="root",
        password="password",
        database="hotel_booking"
    )


def check_room_availability(check_in, check_out, bed_type, breakfast):
    connection = get_connection()
    cursor = connection.cursor(dictionary=True)

    try:
        query = """
            SELECT r.*
            FROM rooms r
            WHERE r.bed_type = %s
              AND r.breakfast = %s
              AND r.status = 'Available'
              AND NOT EXISTS (
                  SELECT 1
                  FROM bookings b
                  WHERE b.room_no = r.room_no
                    AND b.booking_status = 'Confirmed'
                    AND b.check_in < %s
                    AND b.check_out > %s
              )
            ORDER BY r.price_per_night
        """

        cursor.execute(
            query,
            (bed_type, breakfast, check_out, check_in)
        )
        return cursor.fetchall()

    finally:
        cursor.close()
        connection.close()


def check_alternative_rooms(check_in, check_out):
    connection = get_connection()
    cursor = connection.cursor(dictionary=True)

    try:
        query = """
            SELECT r.*
            FROM rooms r
            WHERE r.status = 'Available'
              AND NOT EXISTS (
                  SELECT 1
                  FROM bookings b
                  WHERE b.room_no = r.room_no
                    AND b.booking_status = 'Confirmed'
                    AND b.check_in < %s
                    AND b.check_out > %s
              )
            ORDER BY r.price_per_night
        """

        cursor.execute(query, (check_out, check_in))
        return cursor.fetchall()

    finally:
        cursor.close()
        connection.close()



def save_booking(
    room_no, guest_name, guest_email,
    check_in, check_out, guests
):
    connection = get_connection()
    cursor = connection.cursor()

    try:
        connection.start_transaction()

        cursor.execute(
            """
            SELECT status
            FROM rooms
            WHERE room_no = %s
            FOR UPDATE
            """,
            (room_no,)
        )

        room = cursor.fetchone()

        if room is None or room[0] != "Available":
            connection.rollback()
            return None, "This room is not available."

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
            (room_no, check_out, check_in)
        )

        if cursor.fetchone():
            connection.rollback()
            return None, "This room is already booked for those dates."

        cursor.execute(
            """
            INSERT INTO bookings
            (
                room_no, guest_name, guest_email,
                check_in, check_out, guests, booking_status
            )
            VALUES (%s, %s, %s, %s, %s, %s, 'Confirmed')
            """,
            (
                room_no, guest_name, guest_email,
                check_in, check_out, guests
            )
        )

        booking_id = cursor.lastrowid
        connection.commit()
        return booking_id, None

    except mysql.connector.Error as error:
        connection.rollback()
        return None, f"Database error: {error}"

    finally:
        cursor.close()
        connection.close()


st.set_page_config(
    page_title="Hotel Booking Assistant",
    page_icon="🏨",
    layout="centered"
)

st.title("🏨 Hotel Booking Assistant")
st.write("Find available rooms and book your stay.")

st.subheader("1. Search for a room")

with st.form("room_search_form"):
    check_in = st.date_input(
        "Check-in date",
        value=date.today(),
        min_value=date.today()
    )

    check_out = st.date_input(
        "Check-out date",
        value=date.today(),
        min_value=date.today()
    )

    bed_type = st.selectbox("Bed type", ["Single", "Double"])
    breakfast = st.selectbox("Breakfast included?", ["Yes", "No"])

    search_clicked = st.form_submit_button("Check Availability")


if search_clicked:
    if check_out <= check_in:
        st.error("Check-out must be after check-in.")
        st.session_state.pop("rooms", None)
        st.session_state.pop("alternatives", None)

    else:
        try:
            rooms = check_room_availability(
                check_in,
                check_out,
                bed_type,
                breakfast == "Yes"
            )

            st.session_state["rooms"] = rooms
            st.session_state["alternatives"] = []
            st.session_state["check_in"] = check_in
            st.session_state["check_out"] = check_out

            # Get alternatives only if exact matches are unavailable
            if not rooms:
                st.session_state["alternatives"] = (
                    check_alternative_rooms(check_in, check_out)
                )

        except mysql.connector.Error as error:
            st.error(f"Could not check availability: {error}")



if "rooms" in st.session_state:
    rooms = st.session_state["rooms"]

    if not rooms:
        st.warning("No matching rooms available for these dates.")

        alternatives = st.session_state.get("alternatives", [])

        if alternatives:
            st.subheader("Alternative Available Rooms")
            st.write(
                "These rooms have different bed or breakfast options "
                "but are available for your dates."
            )

            for room in alternatives:
                st.write(
                    f"**Room {room['room_no']} — {room['room_type']}**"
                )
                st.write(
                    f"Bed: {room['bed_type']} | "
                    f"Breakfast: {'Yes' if room['breakfast'] else 'No'}"
                )
                st.write(
                    f"Price: ₹{room['price_per_night']} per night"
                )
        else:
            st.info("No alternative rooms are available either.")

    else:
        st.subheader("2. Available Rooms")

        room_options = {}

        for room in rooms:
            st.write(
                f"**Room {room['room_no']} — {room['room_type']}**"
            )
            st.write(
                f"Bed: {room['bed_type']} | "
                f"Breakfast: {'Yes' if room['breakfast'] else 'No'}"
            )
            st.write(
                f"Price: ₹{room['price_per_night']} per night"
            )

            label = (
                f"Room {room['room_no']} — {room['room_type']} — "
                f"₹{room['price_per_night']}/night"
            )
            room_options[label] = room

        selected_label = st.selectbox(
            "Choose your room",
            list(room_options.keys())
        )

        selected_room = room_options[selected_label]
        room_no = selected_room["room_no"]

        st.subheader("3. Guest Details")

        with st.form("booking_form"):
            guest_name = st.text_input("Full name")
            guest_email = st.text_input("Email address")
            guests = st.number_input(
                "Number of guests",
                min_value=1,
                max_value=10,
                value=1,
                step=1
            )

            book_clicked = st.form_submit_button("Book Room")

        if book_clicked:
            if not guest_name.strip():
                st.error("Please enter your name.")

            elif (
                "@" not in guest_email
                or "." not in guest_email.split("@")[-1]
            ):
                st.error("Please enter a valid email address.")

            else:
                try:
                    booking_id, error = save_booking(
                        room_no,
                        guest_name.strip(),
                        guest_email.strip(),
                        st.session_state["check_in"],
                        st.session_state["check_out"],
                        int(guests)
                    )

                    if error:
                        st.error(error)

                    else:
                        check_in_date = st.session_state["check_in"]
                        check_out_date = st.session_state["check_out"]
                        total_nights = (
                            check_out_date - check_in_date
                        ).days

                        price_per_night = float(
                            selected_room["price_per_night"]
                        )
                        total_price = total_nights * price_per_night

                        st.success("Booking confirmed!")
                        st.subheader("Booking Confirmation")
                        st.write(f"**Booking ID:** {booking_id}")
                        st.write(f"**Room Number:** {room_no}")
                        st.write(f"**Guest Name:** {guest_name.strip()}")
                        st.write(f"**Check-in:** {check_in_date}")
                        st.write(f"**Check-out:** {check_out_date}")
                        st.write(f"**Total Nights:** {total_nights}")
                        st.write(
                            f"**Price per Night:** "
                            f"₹{price_per_night:,.2f}"
                        )
                        st.write(f"**Total Price:** ₹{total_price:,.2f}")

                        st.divider()
                        st.subheader("📧 Email Confirmation (Mock)")
                        st.success(
                            f"Confirmation prepared for "
                            f"{guest_email.strip()}"
                        )
                        st.write(f"**To:** {guest_email.strip()}")
                        st.write("**Subject:** Hotel Booking Confirmation")
                        st.write(f"Dear {guest_name.strip()},")
                        st.write(
                            f"Your booking for Room {room_no} "
                            "has been confirmed."
                        )
                        st.write(
                            f"Stay: {check_in_date} to {check_out_date}"
                        )
                        st.write(f"Total Amount: ₹{total_price:,.2f}")
                        st.info(
                            "Demo only: No actual email has been sent."
                        )

                except mysql.connector.Error as error:
                    st.error(f"Booking failed: {error}")



st.divider()
st.header("📋 Booking History")

if st.button("View Booking History"):
    try:
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)

        query = """
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

        cursor.execute(query)
        bookings = cursor.fetchall()

        cursor.close()
        conn.close()

        if bookings:
            for booking in bookings:
                total_price = (
                    float(booking["price_per_night"])
                    * booking["total_nights"]
                )

                with st.expander(
                    f"Booking ID: {booking['booking_id']} | "
                    f"Room: {booking['room_no']}"
                ):
                    st.write("**Guest Name:**", booking["guest_name"])
                    st.write("**Email:**", booking["guest_email"])
                    st.write("**Room Type:**", booking["room_type"])
                    st.write("**Check-in:**", booking["check_in"])
                    st.write("**Check-out:**", booking["check_out"])
                    st.write("**Guests:**", booking["guests"])
                    st.write("**Total Nights:**", booking["total_nights"])
                    st.write(
                        "**Price per Night:** ₹{:,.2f}".format(
                            float(booking["price_per_night"])
                        )
                    )
                    st.write("**Total Price:** ₹{:,.2f}".format(total_price))
                    st.write(
                        "**Booking Status:**",
                        booking["booking_status"]
                    )
        else:
            st.info("No booking history found.")

    except Exception as e:
        st.error(f"Unable to load booking history: {e}")



st.divider()
st.header("❌ Cancel Booking")

cancel_booking_id = st.number_input(
    "Enter Booking ID to cancel",
    min_value=1,
    step=1,
    key="cancel_booking_id"
)

if st.button("Cancel Booking"):
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
            (int(cancel_booking_id),)
        )

        if cursor.rowcount > 0:
            conn.commit()
            st.success(
                f"Booking ID {cancel_booking_id} cancelled successfully!"
            )
        else:
            conn.rollback()
            st.warning(
                "Booking not found or it is already cancelled."
            )

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

if st.button("Refresh Dashboard"):
    conn = None
    cursor = None

    try:
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("""
            SELECT
                COUNT(*) AS total_bookings,
                SUM(booking_status = 'Confirmed') AS confirmed_bookings,
                SUM(booking_status = 'Cancelled') AS cancelled_bookings
            FROM bookings
        """)

        booking_stats = cursor.fetchone()

        cursor.execute("""
            SELECT
                COUNT(*) AS total_rooms,
                SUM(status = 'Available') AS available_rooms
            FROM rooms
        """)

        room_stats = cursor.fetchone()

        col1, col2, col3 = st.columns(3)

        col1.metric(
            "Total Bookings",
            booking_stats["total_bookings"] or 0
        )
        col2.metric(
            "Confirmed Bookings",
            booking_stats["confirmed_bookings"] or 0
        )
        col3.metric(
            "Cancelled Bookings",
            booking_stats["cancelled_bookings"] or 0
        )

        col4, col5 = st.columns(2)

        col4.metric(
            "Total Rooms",
            room_stats["total_rooms"] or 0
        )
        col5.metric(
            "Available Rooms",
            room_stats["available_rooms"] or 0
        )

    except mysql.connector.Error as error:
        st.error(f"Unable to load dashboard: {error}")

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

