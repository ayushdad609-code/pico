"""
Gmail Event, Booking & Receipt Watcher for Pico.
Uses IMAP with App Passwords (zero external dependencies).
Extracts receipts, travel tickets, PNRs, and booking confirmations into Pico's timeline.
"""

import os
import re
import imaplib
import email
from email.header import decode_header
from enum import Enum
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any, Tuple
import logging

logger = logging.getLogger("pico.gmail_watcher")


class EventType(str, Enum):
    BOOKING = "BOOKING"
    RECEIPT = "RECEIPT"
    ALERT = "ALERT"
    GENERAL = "GENERAL"


@dataclass
class GmailMessage:
    message_id: str
    sender: str
    subject: str
    date: str
    body: str
    is_unread: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "message_id": self.message_id,
            "sender": self.sender,
            "subject": self.subject,
            "date": self.date,
            "body_preview": self.body[:200] if self.body else "",
            "is_unread": self.is_unread
        }


@dataclass
class ExtractedEvent:
    event_type: EventType
    title: str
    merchant: str
    amount: Optional[float] = None
    currency: str = "INR"
    reference_code: Optional[str] = None
    date: str = ""
    raw_snippet: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_type": self.event_type.value,
            "title": self.title,
            "merchant": self.merchant,
            "amount": self.amount,
            "currency": self.currency,
            "reference_code": self.reference_code,
            "date": self.date,
            "raw_snippet": self.raw_snippet[:150]
        }


def _clean_header_text(header_val: Any) -> str:
    """Decodes MIME encoded header strings safely."""
    if not header_val:
        return ""
    decoded_fragments = decode_header(str(header_val))
    parts = []
    for frag, encoding in decoded_fragments:
        if isinstance(frag, bytes):
            parts.append(frag.decode(encoding or "utf-8", errors="replace"))
        else:
            parts.append(str(frag))
    return " ".join(parts).strip()


def extract_events_from_message(msg: GmailMessage) -> List[ExtractedEvent]:
    """Scans email content for bookings, receipts, and order confirmations."""
    events = []
    text = f"{msg.subject}\n{msg.body}"

    # 1. Booking & Reservation Detection
    booking_match = re.search(r"\b(?:reservation|booking|flight|hotel|ticket|pnr)\b", text, re.IGNORECASE)
    ref_match = re.search(r"\b(?:pnr|reservation\s*id|booking\s*id|reference|ref)\s*(?:is|:)?\s*([A-Za-z0-9\-]{4,15}\b)", text, re.IGNORECASE)
    if not ref_match:
        # Check standard airline/hotel uppercase alphanumeric code
        alt_ref = re.search(r"\b([A-Z]{2,4}[-\s]?[0-9]{3,6})\b", text)
        if alt_ref and booking_match:
            ref_match = alt_ref

    # Amount detection: Rs. 4500, INR 4500, ₹4500, $50
    amount = None
    amt_match = re.search(r"(?:rs\.?|inr|₹|\$)\s*([0-9]+(?:,[0-9]+)*(?:\.[0-9]{1,2})?)", text, re.IGNORECASE)
    if amt_match:
        try:
            amount = float(amt_match.group(1).replace(",", ""))
        except Exception:
            amount = None

    # Merchant detection from sender or text
    merchant = "Unknown"
    sender_clean = msg.sender.lower()
    for domain, brand in [
        ("swiggy", "Swiggy"),
        ("zomato", "Zomato"),
        ("amazon", "Amazon"),
        ("flipkart", "Flipkart"),
        ("makemytrip", "MakeMyTrip"),
        ("uber", "Uber"),
        ("ola", "Ola"),
        ("hotelsunrise", "Hotel Sunrise"),
        ("indigo", "IndiGo"),
        ("airindia", "Air India")
    ]:
        if domain in sender_clean or domain in text.lower():
            merchant = brand
            break
    if merchant == "Unknown" and "@" in msg.sender:
        merchant = msg.sender.split("@")[-1].split(".")[0].capitalize()

    # Determine Event Category
    if booking_match and ref_match:
        events.append(ExtractedEvent(
            event_type=EventType.BOOKING,
            title=msg.subject,
            merchant=merchant,
            amount=amount,
            reference_code=ref_match.group(1).strip(),
            date=msg.date,
            raw_snippet=msg.body[:200]
        ))
    elif amount is not None or "order" in text.lower() or "receipt" in text.lower() or "delivered" in text.lower():
        events.append(ExtractedEvent(
            event_type=EventType.RECEIPT,
            title=msg.subject,
            merchant=merchant,
            amount=amount or 0.0,
            reference_code=ref_match.group(1).strip() if ref_match else None,
            date=msg.date,
            raw_snippet=msg.body[:200]
        ))
    elif "alert" in text.lower() or "urgent" in text.lower() or "statement" in text.lower():
        events.append(ExtractedEvent(
            event_type=EventType.ALERT,
            title=msg.subject,
            merchant=merchant,
            date=msg.date,
            raw_snippet=msg.body[:200]
        ))

    return events


class GmailWatcher:
    """IMAP client for polling Gmail and syncing events into Pico."""

    def __init__(
        self,
        email_address: Optional[str] = None,
        app_password: Optional[str] = None
    ):
        self.email_address = email_address or os.getenv("GMAIL_ADDRESS", "")
        self.app_password = app_password or os.getenv("GMAIL_APP_PASSWORD", "")
        self.imap_host = "imap.gmail.com"
        self.imap_port = 993

    def is_configured(self) -> bool:
        return bool(self.email_address and self.app_password)

    def fetch_recent_emails(
        self,
        limit: int = 10,
        folder: str = "INBOX",
        unread_only: bool = False
    ) -> List[GmailMessage]:
        """Connects to Gmail via IMAP and retrieves recent messages."""
        if not self.is_configured():
            logger.warning("GmailWatcher: GMAIL_ADDRESS or GMAIL_APP_PASSWORD not configured.")
            return []

        messages: List[GmailMessage] = []
        mail = None
        try:
            mail = imaplib.IMAP4_SSL(self.imap_host, self.imap_port)
            mail.login(self.email_address, self.app_password)
            mail.select(folder)

            search_criteria = "UNSEEN" if unread_only else "ALL"
            status, data = mail.search(None, search_criteria)
            if status != "OK" or not data or not data[0]:
                return []

            msg_ids = data[0].split()
            # Fetch latest first
            latest_ids = msg_ids[-limit:]
            latest_ids.reverse()

            for mid in latest_ids:
                fetch_status, fetch_data = mail.fetch(mid, "(RFC822)")
                if fetch_status != "OK" or not fetch_data:
                    continue

                raw_bytes = None
                for part in fetch_data:
                    if isinstance(part, tuple) and len(part) >= 2:
                        raw_bytes = part[1]
                        break

                if not raw_bytes:
                    continue

                parsed = email.message_from_bytes(raw_bytes)
                subject = _clean_header_text(parsed.get("Subject", "No Subject"))
                sender = _clean_header_text(parsed.get("From", "Unknown Sender"))
                date_str = _clean_header_text(parsed.get("Date", ""))

                # Extract plain text body
                body = ""
                if parsed.is_multipart():
                    for p in parsed.walk():
                        if p.get_content_type() == "text/plain":
                            try:
                                body = p.get_payload(decode=True).decode("utf-8", errors="replace")
                                break
                            except Exception:
                                pass
                else:
                    try:
                        body = parsed.get_payload(decode=True).decode("utf-8", errors="replace")
                    except Exception:
                        body = str(parsed.get_payload())

                messages.append(GmailMessage(
                    message_id=mid.decode("utf-8", errors="replace") if isinstance(mid, bytes) else str(mid),
                    sender=sender,
                    subject=subject,
                    date=date_str,
                    body=body.strip()
                ))

        except Exception as e:
            logger.warning(f"Gmail IMAP error: {e}")
        finally:
            if mail:
                try:
                    mail.logout()
                except Exception:
                    pass

        return messages

    def sync_to_receipts_engine(
        self,
        emails: List[GmailMessage],
        receipts_engine: Any,
        user_id: str = "ayush_01"
    ) -> int:
        """Parses emails and records any detected receipts into ReceiptsTimelineEngine."""
        synced_count = 0
        for msg in emails:
            events = extract_events_from_message(msg)
            for ev in events:
                if ev.amount is not None and ev.amount > 0:
                    try:
                        claim = f"Transaction of {ev.currency} {ev.amount} at {ev.merchant} ({ev.title})"
                        source_ref = f"gmail:{msg.message_id}"
                        receipts_engine.record_receipt(
                            user_id=user_id,
                            claim=claim,
                            source_type="gmail_receipt",
                            source_ref=source_ref,
                            value_recorded=str(ev.amount)
                        )
                        synced_count += 1
                    except Exception as e:
                        logger.warning(f"Receipt sync exception: {e}")
        return synced_count
