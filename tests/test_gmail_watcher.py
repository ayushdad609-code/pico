"""Tests for Gmail Event & Receipt Watcher (IMAP App Password)."""

import pytest
from unittest.mock import MagicMock, patch
from pico.gmail_watcher import (
    GmailWatcher,
    GmailMessage,
    ExtractedEvent,
    EventType,
    extract_events_from_message
)
from pico.receipts import ReceiptsTimelineEngine

def test_extract_booking_event_from_email():
    msg = GmailMessage(
        message_id="msg_001",
        sender="reservations@hotelsunrise.com",
        subject="Booking Confirmation - Hotel Sunrise Goa",
        date="2026-11-07 10:00:00",
        body="Dear Ayush, your room is booked for 14-16 Dec. Your reservation ID is HSR-9482. Total amount paid is INR 4500."
    )

    events = extract_events_from_message(msg)
    assert len(events) >= 1
    booking = next((e for e in events if e.event_type == EventType.BOOKING), None)
    assert booking is not None
    assert booking.reference_code == "HSR-9482"
    assert booking.merchant == "Hotel Sunrise"
    assert booking.amount == 4500.0


def test_extract_food_receipt_from_email():
    msg = GmailMessage(
        message_id="msg_002",
        sender="no-reply@swiggy.in",
        subject="Order Delivered: Order #SW-88912",
        date="2026-11-07 13:30:00",
        body="Your order from Burger King was delivered. Total paid: Rs. 349.50 via UPI."
    )

    events = extract_events_from_message(msg)
    receipt = next((e for e in events if e.event_type == EventType.RECEIPT), None)
    assert receipt is not None
    assert receipt.amount == 349.50
    assert "Burger King" in receipt.merchant or "Swiggy" in receipt.merchant


def test_gmail_watcher_mock_connection_and_sync(tmp_path):
    watcher = GmailWatcher(email_address="test@gmail.com", app_password="mock_app_password")

    # Mock IMAP client
    mock_imap = MagicMock()
    mock_imap.login.return_value = ("OK", [b"Logged in"])
    mock_imap.select.return_value = ("OK", [b"1"])
    mock_imap.search.return_value = ("OK", [b"1 2"])

    raw_email_bytes = (
        b"From: travel@makemytrip.com\r\n"
        b"Subject: Flight Confirmed PNR 6E4921\r\n"
        b"Date: Sat, 07 Nov 2026 12:00:00 +0530\r\n\r\n"
        b"Your flight to Mumbai is confirmed. PNR: 6E4921. Total fare: Rs. 6200.\r\n"
    )
    mock_imap.fetch.return_value = ("OK", [(b"1", raw_email_bytes)])

    with patch("imaplib.IMAP4_SSL", return_value=mock_imap):
        emails = watcher.fetch_recent_emails(limit=2)
        assert len(emails) >= 1
        assert emails[0].subject == "Flight Confirmed PNR 6E4921"

        db_path = str(tmp_path / "test_pico.db")
        receipts_engine = ReceiptsTimelineEngine(db_path=db_path)
        synced_count = watcher.sync_to_receipts_engine(emails, receipts_engine, user_id="ayush_01")
        assert synced_count >= 1

        timeline = receipts_engine.get_timeline("ayush_01")
        assert len(timeline) >= 1
        assert "6200.0" in timeline[0].value_recorded or "6200" in timeline[0].claim
