import streamlit as st
import whisper
import dateparser
import re
import os
import subprocess  # ✅ Use subprocess for ffmpeg recording
from googleapiclient.discovery import build
from google.oauth2 import service_account
from datetime import datetime, timedelta
from dotenv import load_dotenv  

load_dotenv()

# ✅ Get values from .env
SERVICE_ACCOUNT_FILE = os.getenv("SERVICE_ACCOUNT_FILE")
CALENDAR_ID = os.getenv("CALENDAR_ID")

# Load Whisper Model
@st.cache_resource
def load_model():
    return whisper.load_model("small")

model = load_model()

SCOPES = ["https://www.googleapis.com/auth/calendar"]
creds = service_account.Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)
service = build("calendar", "v3", credentials=creds)

# Streamlit UI
st.title("Live Audio to Google Calendar Scheduler")

# Recording Configuration
DURATION = st.slider("Select recording duration (seconds)", 5, 60, 10)
FILENAME = "live_recording.wav"

# Function to record audio using ffmpeg
def record_audio(filename, duration=5):
    st.info("Recording... Please speak now.")
    command = f"ffmpeg -y -f avfoundation -i :0 -t {duration} {filename}"  # For MacOS
    # Use this instead for Linux: command = f"ffmpeg -y -f alsa -i default -t {duration} {filename}"
    subprocess.run(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    st.success("Recording complete. Processing...")

if st.button("Start Recording"):
    record_audio(FILENAME, DURATION)

    # Transcribe Audio
    result = model.transcribe(FILENAME, task="translate")
    command_text = result["text"]
    st.success(f"Translated Command: {command_text}")

    # Process and schedule event...

    # Extract Date & Time
    def extract_date_time(text):
        today = datetime.now()
        tomorrow = today + timedelta(days=1)

        # Normalize "today" and "tomorrow"
        text = text.lower()
        if "tomorrow" in text:
            return tomorrow.replace(hour=9, minute=0)  # Default to 9 AM
        elif "today" in text:
            return today.replace(hour=9, minute=0)  # Default to 9 AM

        # Remove ordinal suffixes (st, nd, rd, th)
        text = re.sub(r'(\d{1,2})(st|nd|rd|th)', r'\1', text)

        # Extract time (e.g., "8 pm")
        time_match = re.search(r'(\d{1,2})\s?(am|pm)', text, re.IGNORECASE)
        extracted_time = None
        if time_match:
            hour = int(time_match.group(1))
            period = time_match.group(2).lower()

            if period == "pm" and hour != 12:
                hour += 12
            elif period == "am" and hour == 12:
                hour = 0

            extracted_time = hour

        # Extract date separately (e.g., "16 February")
        date_match = re.search(r'(\d{1,2})\s+(january|february|march|april|may|june|july|august|september|october|november|december)', text, re.IGNORECASE)
        extracted_date = None
        if date_match:
            day = int(date_match.group(1))
            month = date_match.group(2).capitalize()
            extracted_date = dateparser.parse(f"{day} {month} {today.year}", settings={"PREFER_DATES_FROM": "future"})

        # Merge extracted date and time
        if extracted_date and extracted_time is not None:
            event_time = extracted_date.replace(hour=extracted_time, minute=0)
        elif extracted_date:
            event_time = extracted_date.replace(hour=9, minute=0)  # Default time: 9 AM
        else:
            event_time = None  # Unable to parse

        return event_time

    event_time = extract_date_time(command_text)
    if event_time is None:
        st.error("Could not extract a valid date/time from the command.")
    else:
        st.write(f"Parsed Date & Time: {event_time}")

        # Extract Event Summary
        def extract_event_summary(text):
            time_keywords = ["schedule", "meeting", "appointment", "reminder", "on", "at", 
                             "tomorrow", "next", "in", "am", "pm", "today", "morning", "evening", "night", "week", "month"]
            event_summary = re.sub(r'\b(?:' + '|'.join(time_keywords) + r')\b', '', text, flags=re.IGNORECASE)
            event_summary = event_summary.strip()

            return event_summary if event_summary else "Meeting"

        event_summary = extract_event_summary(command_text)
        st.write(f"Extracted Event Summary: {event_summary}")

        # Create Event
        event = {
            "summary": event_summary,
            "start": {"dateTime": event_time.isoformat(), "timeZone": "Asia/Karachi"},
            "end": {"dateTime": (event_time + timedelta(hours=1)).isoformat(), "timeZone": "Asia/Karachi"},
        }

        event_result = service.events().insert(calendarId=CALENDAR_ID, body=event).execute()
        st.success(f"✅ Event Created: [View Event]({event_result['htmlLink']})")
