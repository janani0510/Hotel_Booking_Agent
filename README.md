# Conversational Hotel Booking Agent

## 1. Project Overview

The Conversational Hotel Booking Agent is a Python-based hotel room availability and booking assistant. It uses Streamlit to provide the user interface, Google Gemini to understand natural-language messages, and MySQL to store room and booking information.

Users can provide their stay dates, preferred bed type, breakfast preference, and number of guests. The application checks room availability, displays matching rooms and prices, and allows users to confirm a booking.

## 2. Technologies Used

- Python
- Streamlit
- Google Gemini API (`google-genai`)
- MySQL
- `mysql-connector-python`
- `python-dotenv`

## 3. Key Features

- Conversational interaction using Gemini
- Room availability checking against MySQL booking records
- Single and double bed preferences
- Breakfast preference selection
- Room price and total-stay cost calculation
- Alternative room suggestions when configured in the application
- Guest details collection and booking confirmation
- Booking history and cancellation
- Hotel dashboard with booking statistics and revenue
- Mock email confirmation preview

## 4. Architecture

The application follows this flow:

1. The user enters a message in the Streamlit chat interface.
2. Gemini extracts the booking details from the message.
3. Python validates the dates and booking preferences.
4. The Python availability function queries MySQL to find rooms that match the preferences and do not have overlapping confirmed bookings.
5. Streamlit displays matching rooms and prices.
6. The user selects a room and submits their details.
7. Python saves the booking in MySQL and displays the confirmation.

**Important:** Gemini assists with natural-language understanding. Python performs validation and database operations. Room availability and booking confirmation are determined by the application and database, not invented by the language model.

## 5. Database

The application uses the `hotel_booking` MySQL database, with `rooms` and `bookings` tables.

The `rooms` table stores room information such as room number, room type, bed type, breakfast availability, price per night, and room status.

The `bookings` table stores booking details such as room number, guest details, check-in and check-out dates, number of guests, and booking status.

## 6. Setup Instructions

### Prerequisites

Install Python and MySQL. Ensure the `hotel_booking` database and required tables are configured.

### Install dependencies

```bash
pip install streamlit mysql-connector-python google-genai python-dotenv
```

### Configure environment variables

Create a `.env` file in the project root:

```text
GEMINI_API_KEY=your_gemini_api_key
```

Use your own API key. Do not upload `.env` to GitHub or share it publicly.

Configure the MySQL connection settings in the application to match your local database.

### Run the application

```bash
python -m streamlit run chat_app.py
```

If your main Python file has a different name, use that filename in the command.

## 7. Validation and Testing

The prototype should be tested for:

- Past check-in dates
- Check-out dates that are the same as or earlier than check-in
- Available and unavailable rooms
- Different bed and breakfast preferences
- Room price calculation
- Booking confirmation and booking history
- Booking cancellation
- Database connection errors

## 8. Limitations

- Email confirmation is a demonstration preview; no actual email is sent.
- Availability depends on the booking records stored in MySQL.
- Guest capacity can only be validated if room-capacity information is stored and checked.
- Gemini API access requires a valid API key and internet access.
- The prototype should be tested further before production use.

## 9. Future Enhancements

- Actual email notifications
- Room capacity validation
- More robust natural-language preference changes
- Improved handling of alternative rooms
- Authentication and secure administration