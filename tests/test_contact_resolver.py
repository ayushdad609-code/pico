import pytest
import json
from unittest.mock import AsyncMock, patch
from telephony.contact_resolver import (
    normalize_phone_number,
    resolve_callee,
    CalleeInfo,
)

def test_normalize_phone_number():
    assert normalize_phone_number("9876543210") == "+919876543210"
    assert normalize_phone_number("+91 98765-43210") == "+919876543210"
    assert normalize_phone_number("09876543210") == "+919876543210"
    assert normalize_phone_number("+1 (555) 123-4567") == "+15551234567"
    assert normalize_phone_number("invalid") == ""

@pytest.mark.anyio
async def test_resolve_callee_direct_number():
    info = await resolve_callee("+919876543210")
    assert info is not None
    assert info.phone_number == "+919876543210"
    assert info.name == "+919876543210"
    assert info.source == "direct"

@pytest.mark.anyio
async def test_resolve_callee_contact_lookup():
    mock_contacts = [
        {"name": "Dad", "number": "9876543210"},
        {"name": "Mom", "number": "9123456789"},
        {"name": "Dentist Dr. Sharma", "number": "+91 99999 88888"}
    ]
    with patch("telephony.contact_resolver.SafeCommandRunner.run", new_callable=AsyncMock) as mock_run:
        mock_run.return_value = (True, json.dumps(mock_contacts), "")
        
        info = await resolve_callee("dad")
        assert info is not None
        assert info.name == "Dad"
        assert info.phone_number == "+919876543210"
        assert info.source == "contacts"

@pytest.mark.anyio
async def test_resolve_callee_privacy_minimization_and_not_found():
    mock_contacts = [
        {"name": "Secret Contact", "number": "1234567890"},
        {"name": "Bank Manager", "number": "0987654321"}
    ]
    with patch("telephony.contact_resolver.SafeCommandRunner.run", new_callable=AsyncMock) as mock_run:
        mock_run.return_value = (True, json.dumps(mock_contacts), "")
        
        info = await resolve_callee("nonexistent")
        assert info is None
