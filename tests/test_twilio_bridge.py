"""Tests for Twilio Media Stream Telephony Bridge."""

import json
import base64
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from telephony.briefing import FactsPacket, CalleeInfo, AuthorityLevel
from telephony.call_session import CallSession, CallStatus
from telephony.twilio_bridge import (
    build_twiml_stream,
    TwilioCallManager,
    TwilioMediaStreamHandler
)

def test_build_twiml_stream():
    twiml = build_twiml_stream("wss://pico.example.com/media-stream", custom_params={"session_id": "call-123"})
    assert "<Response>" in twiml
    assert "<Connect>" in twiml
    assert '<Stream url="wss://pico.example.com/media-stream">' in twiml
    assert '<Parameter name="session_id" value="call-123"/>' in twiml


@pytest.mark.anyio
async def test_twilio_call_manager_initiate_and_end():
    manager = TwilioCallManager(
        account_sid="ACmock12345",
        auth_token="authmock12345",
        from_number="+1234567890"
    )

    class MockContextManager:
        def __init__(self, resp):
            self.resp = resp
        async def __aenter__(self):
            return self.resp
        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass

    mock_resp = MagicMock()
    mock_resp.status = 201
    mock_resp.json = AsyncMock(return_value={"sid": "CA123456789", "status": "queued"})

    with patch("aiohttp.ClientSession.post", return_value=MockContextManager(mock_resp)):
        res = await manager.initiate_call(
            to_number="+919876543210",
            twiml_url="https://pico.example.com/twiml"
        )
        assert res["sid"] == "CA123456789"
        assert res["status"] == "queued"

    mock_end_resp = MagicMock()
    mock_end_resp.status = 200
    mock_end_resp.json = AsyncMock(return_value={"sid": "CA123456789", "status": "completed"})

    with patch("aiohttp.ClientSession.post", return_value=MockContextManager(mock_end_resp)):
        ok = await manager.end_call("CA123456789")
        assert ok is True


@pytest.mark.anyio
async def test_twilio_media_stream_handler_lifecycle_and_barge_in():
    callee = CalleeInfo(name="Dad", phone_number="+919876543210")
    packet = FactsPacket(callee=callee, objective="Tell him I'm reaching late", authority=AuthorityLevel.L0)
    session = CallSession(packet=packet)

    mock_ws = AsyncMock()
    handler = TwilioMediaStreamHandler(session=session, ws=mock_ws)

    # 1. Handle "connected"
    await handler.handle_message(json.dumps({"event": "connected", "protocol": "Call"}))
    assert handler.stream_sid is None

    # 2. Handle "start"
    start_payload = {
        "event": "start",
        "streamSid": "MZ12345",
        "start": {
            "streamSid": "MZ12345",
            "callSid": "CA99999",
            "customParameters": {"user": "ayush"}
        }
    }
    await handler.handle_message(json.dumps(start_payload))
    assert handler.stream_sid == "MZ12345"
    assert handler.call_sid == "CA99999"

    # 3. Test outbound audio queuing & sending
    # 16-bit PCM 16kHz silence
    pcm_16k = b"\x00\x00" * 320
    await handler.send_audio(pcm_16k)
    assert mock_ws.send_str.called
    sent_data = json.loads(mock_ws.send_str.call_args[0][0])
    assert sent_data["event"] == "media"
    assert sent_data["streamSid"] == "MZ12345"
    assert "payload" in sent_data["media"]

    # 4. Test incoming speech & barge-in interruption
    # Queue pending speech in session audio bridge
    session.audio_bridge.queue_playback_audio(b"\x05\x05" * 100)
    assert session.audio_bridge.has_pending_audio()

    # Simulate incoming callee speech in mu-law
    loud_mulaw = b"\x02" * 160  # Loud sample
    media_payload = {
        "event": "media",
        "streamSid": "MZ12345",
        "media": {
            "payload": base64.b64encode(loud_mulaw).decode("utf-8")
        }
    }
    await handler.handle_message(json.dumps(media_payload))

    # Should have triggered instant clear event over WebSocket!
    clear_calls = [
        json.loads(c[0][0]) for c in mock_ws.send_str.call_args_list
        if "clear" in c[0][0]
    ]
    assert len(clear_calls) > 0
    assert clear_calls[0]["event"] == "clear"
    assert clear_calls[0]["streamSid"] == "MZ12345"

    # 5. Handle "stop"
    await handler.handle_message(json.dumps({"event": "stop", "streamSid": "MZ12345"}))
    assert session.status == CallStatus.ENDED
