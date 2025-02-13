import streamlit as st
import whisper
import dateparser
import re
import os
import tempfile
from googleapiclient.discovery import build
from google.oauth2 import service_account
from datetime import datetime, timedelta
from streamlit_mic_recorder import mic_recorder  # ✅ Import microphone recorder

# ✅ Load Google credentials from Streamlit secrets
service_account_info = st.secrets["google"]
creds = service_account.Credentials.from_service_account_info(service_account_info)
CALENDAR_ID = st.secrets["google"]["CALENDAR_ID"]

# ✅ Load Whisper Model
@st.cache_resource
def load_model():
    return whisper.load_model("small")

model = load_model()

# ✅ Initialize Google Calendar API
SCOPES = ["https://www.googleapis.com/auth/calendar"]
service = build("calendar", "v3", credentials=creds)

# ✅ Streamlit UI
st.title("🎙 Live Audio to Google Calendar Scheduler")

# ✅ Record Audio
st.write("Press 'Start Recording', speak your command, then click 'Stop Recording'.")

# 🔴 Start recording
audio = mic_recorder(start_prompt="🎤 Start Recording", stop_prompt="⏹ Stop Recording")

if audio:
    st.success("✅ Recording complete. Processing...")

    # ✅ Save the recorded audio to a temporary file
    with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as temp_audio:
        temp_audio.write(audio)
        temp_audio_path = temp_audio.name

    # ✅ Transcribe Audio
    result = model.transcribe(temp_audio_path, task="translate")
    command_text = result["text"]
    st.success(f"📝 Translated Command: {command_text}")

    # ✅ Extract Date & Time
    def extract_date_time(text):
        today = datetime.now()
        tomorrow = today + timedelta(days=1)

        text = text.lower()
        if "tomorrow" in text:
            return tomorrow.replace(hour=9, minute=0)  # Default: 9 AM
        elif "today" in text:
            return today.replace(hour=9, minute=0)

        text = re.sub(r'(\d{1,2})(st|nd|rd|th)', r'\1', text)

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

        date_match = re.search(r'(\d{1,2})\s+(january|february|march|april|may|june|july|august|september|october|november|december)', text, re.IGNORECASE)
        extracted_date = None
        if date_match:
            day = int(date_match.group(1))
            month = date_match.group(2).capitalize()
            extracted_date = dateparser.parse(f"{day} {month} {today.year}", settings={"PREFER_DATES_FROM": "future"})

        if extracted_date and extracted_time is not None:
            event_time = extracted_date.replace(hour=extracted_time, minute=0)
        elif extracted_date:
            event_time = extracted_date.replace(hour=9, minute=0)  # Default: 9 AM
        else:
            event_time = None

        return event_time

    event_time = extract_date_time(command_text)
    if event_time is None:
        st.error("❌ Could not extract a valid date/time.")
    else:
        st.write(f"📅 Parsed Date & Time: {event_time}")

        # ✅ Extract Event Summary
        def extract_event_summary(text):
            time_keywords = ["schedule", "meeting", "appointment", "reminder", "on", "at", "tomorrow", "next", "in", "am", "pm", "today", "morning", "evening", "night", "week", "month"]
            event_summary = re.sub(r'\b(?:' + '|'.join(time_keywords) + r')\b', '', text, flags=re.IGNORECASE)
            return event_summary.strip() if event_summary.strip() else "Meeting"

        event_summary = extract_event_summary(command_text)
        st.write(f"📝 Extracted Event Summary: {event_summary}")

        # ✅ Create Google Calendar Event
        event = {
            "summary": event_summary,
            "start": {"dateTime": event_time.isoformat(), "timeZone": "Asia/Karachi"},
            "end": {"dateTime": (event_time + timedelta(hours=1)).isoformat(), "timeZone": "Asia/Karachi"},
        }

        event_result = service.events().insert(calendarId=CALENDAR_ID, body=event).execute()
        st.success(f"✅ Event Created: [📅 View Event]({event_result['htmlLink']})")

    # ✅ Cleanup temp file
    os.remove(temp_audio_path)
