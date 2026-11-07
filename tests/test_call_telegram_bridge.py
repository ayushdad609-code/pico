import pytest
from telephony.contact_resolver import CalleeInfo
from telephony.briefing import AuthorityLevel, FactsPacket
from telephony.call_session import CallSession, CallStatus
from telephony.telegram_bridge import TelegramCallBridge

@pytest.fixture
def active_session():
    callee = CalleeInfo(name="Dad", phone_number="+919876543210", source="contacts")
    packet = FactsPacket(
        callee=callee,
        objective="Tell him I'll be home late",
        authority=AuthorityLevel.L0,
        allowed_facts={"eta": "8:30 PM"},
        allowlist_confirmed=True
    )
    session = CallSession(packet=packet)
    session.status = CallStatus.CONNECTED
    session.add_summary_bullet("Pico introduced call on Ayush's behalf.")
    session.add_summary_bullet("Dad picked up, asked about groceries.")
    return session

def test_telegram_live_summary_formatting(active_session):
    bridge = TelegramCallBridge(bot=None, chat_id=123)
    text, buttons = bridge.format_summary_card(active_session)
    
    assert "In Call with: Dad" in text
    assert "+919876543210" in text
    assert "Connected" in text
    assert "Pico introduced call" in text
    assert "Dad picked up" in text
    
    # Check for Emergency End Call button
    assert len(buttons) >= 1
    abort_btn = buttons[0][0]
    assert "End Call" in abort_btn["text"]
    assert f"abort_call_{active_session.packet.call_id}" == abort_btn["callback_data"]

def test_mid_call_ping_card_formatting(active_session):
    bridge = TelegramCallBridge(bot=None, chat_id=123)
    question = "Dad asks: Should we start dinner without you?"
    options = ["Yes, start", "No, wait 20m"]
    text, buttons = bridge.format_mid_call_ping(active_session, question, options=options)
    
    assert "URGENT MID-CALL APPROVAL" in text
    assert question in text
    assert "45s" in text or "countdown" in text.lower()
    
    # Buttons for options
    flat_btns = [b for row in buttons for b in row]
    assert any("Yes, start" in b["text"] for b in flat_btns)
    assert any("No, wait 20m" in b["text"] for b in flat_btns)

@pytest.mark.anyio
async def test_emergency_abort_terminates_session(active_session):
    bridge = TelegramCallBridge(bot=None, chat_id=123)
    result = await bridge.emergency_abort(active_session)
    assert active_session.status == CallStatus.ENDED
    assert "aborted" in result.lower() or "terminated" in result.lower()
    assert any("ended" in b.lower() for b in active_session.summary_bullets)

def test_final_report_formatting(active_session):
    bridge = TelegramCallBridge(bot=None, chat_id=123)
    active_session.end_call("completed")
    report = bridge.format_final_report(active_session)
    
    assert "CALL COMPLETED" in report
    assert "Dad" in report
    assert "Duration" in report
    assert "Full Transcript" in report

@pytest.mark.anyio
async def test_telegram_async_bridge_lifecycle(active_session):
    from unittest.mock import AsyncMock
    bot = AsyncMock()
    bot.send_message = AsyncMock(return_value={"message_id": 42})
    bot.edit_message_text = AsyncMock(return_value={"message_id": 42})

    bridge = TelegramCallBridge(bot=bot, chat_id=123, min_edit_interval=1.0)

    # 1. Post call started
    mid = await bridge.post_call_started(active_session)
    assert mid == 42
    bot.send_message.assert_called_once()
    assert "In Call with: Dad" in bot.send_message.call_args.kwargs["text"]

    # 2. Update live summary rate limited immediately after
    rate_limited = await bridge.update_live_summary(active_session, "Another bullet")
    assert rate_limited is False  # rate limited by 1.0s interval

    # 3. Trigger mid-call ping
    ping_mid = await bridge.trigger_mid_call_ping(active_session, "Question?", ["A", "B"])
    assert ping_mid == 42
    assert bot.send_message.call_count == 2

    # 4. Post final report
    rep_mid = await bridge.post_final_report(active_session)
    assert rep_mid == 42
    assert bot.send_message.call_count == 3
