import pytest
import asyncio
from unittest.mock import AsyncMock, patch
from pico.telegram_bot import PicoTelegramBot
from telephony.contact_resolver import CalleeInfo
from telephony.call_session import CallStatus

@pytest.fixture
def mock_bot():
    bot = PicoTelegramBot(bot_token="mock_token", db_path=":memory:")
    bot.api.send_message = AsyncMock(return_value={"message_id": 100})
    bot.api.edit_message_text = AsyncMock(return_value={"message_id": 100})
    bot.api.send_chat_action = AsyncMock()
    bot.api.answer_callback_query = AsyncMock()
    return bot

@pytest.mark.anyio
async def test_call_two_step_ask_first_flow(mock_bot):
    chat_id = 12345
    dad_callee = CalleeInfo(name="Dad", phone_number="+919876543210", source="contacts")

    with patch("pico.telegram_bot.resolve_callee", new_callable=AsyncMock) as mock_resolve:
        mock_resolve.return_value = dad_callee

        # Step 1: User says "pico call dad" without objective
        await mock_bot.handle_message(chat_id, "pico call dad", "Ayush")

        # Verify Pico asks what to say / Ask First
        assert mock_bot.api.send_message.call_count == 1
        call_args = mock_bot.api.send_message.call_args[0]
        assert call_args[0] == chat_id
        text = call_args[1]
        assert "Setting up call with Dad" in text
        assert "What should I tell or ask Dad" in text

        # Verify chat state is awaiting objective
        assert chat_id in mock_bot.pending_call_briefings
        assert mock_bot.pending_call_briefings[chat_id]["stage"] == "awaiting_objective"

        # Step 2: User sends the objective
        await mock_bot.handle_message(chat_id, "Tell him dinner is at 8:30 PM", "Ayush")

        # Verify Pico responded with Briefing Card
        assert mock_bot.api.send_message.call_count == 2
        card_call = mock_bot.api.send_message.call_args
        card_text = card_call[0][1]
        card_markup = card_call[1].get("reply_markup", {})

        assert "Call Briefing Card" in card_text
        assert "Dad" in card_text
        assert "dinner is at 8:30 PM" in card_text

        # Verify buttons contain Confirm & Call and Cancel
        flat_buttons = [b for row in card_markup.get("inline_keyboard", []) for b in row]
        assert any("Confirm & Call" in b["text"] for b in flat_buttons)
        assert any("Cancel" in b["text"] for b in flat_buttons)

@pytest.mark.anyio
async def test_call_single_step_flow(mock_bot):
    chat_id = 12345
    mom_callee = CalleeInfo(name="Mom", phone_number="+919876543211", source="contacts")

    with patch("pico.telegram_bot.resolve_callee", new_callable=AsyncMock) as mock_resolve:
        mock_resolve.return_value = mom_callee

        # User provides callee and objective in one message
        await mock_bot.handle_message(chat_id, "/call mom ask if she needs vegetables", "Ayush")

        assert mock_bot.api.send_message.call_count == 1
        card_call = mock_bot.api.send_message.call_args
        card_text = card_call[0][1]
        assert "Mom" in card_text
        assert "needs vegetables" in card_text

@pytest.mark.anyio
async def test_telephony_callback_confirm_abort_and_decision(mock_bot):
    chat_id = 12345
    dad_callee = CalleeInfo(name="Dad", phone_number="+919876543210", source="contacts")

    with patch("pico.telegram_bot.resolve_callee", new_callable=AsyncMock) as mock_resolve, \
         patch("skills.telephony_skill.SafeCommandRunner.run", new_callable=AsyncMock) as mock_dial:
        mock_resolve.return_value = dad_callee
        mock_dial.return_value = (True, "dialed", "")

        # 1. Setup call
        await mock_bot.handle_message(chat_id, "call dad reaching late", "Ayush")
        card_markup = mock_bot.api.send_message.call_args[1].get("reply_markup", {})
        flat_buttons = [b for row in card_markup.get("inline_keyboard", []) for b in row]
        confirm_btn = next(b for b in flat_buttons if "Confirm & Call" in b["text"])
        confirm_cb_data = confirm_btn["callback_data"]
        call_id = confirm_cb_data.replace("confirm_call_", "")

        # 2. User taps [Confirm & Call]
        cb_query = {
            "id": "cb_1",
            "data": confirm_cb_data,
            "message": {"chat": {"id": chat_id}}
        }
        await mock_bot.handle_callback_query(cb_query)

        # Verify active session is created
        assert call_id in mock_bot.active_call_sessions
        session = mock_bot.active_call_sessions[call_id]
        assert session.packet.callee.name == "Dad"
        mock_bot.api.answer_callback_query.assert_called_with("cb_1", text="Dialing Dad... 📞")

        # 3. User sends mid-call decision
        decide_query = {
            "id": "cb_2",
            "data": f"call_decide_{call_id}_0",  # "Yes, proceed"
            "message": {"chat": {"id": chat_id}}
        }
        await mock_bot.handle_callback_query(decide_query)
        assert session.user_decision == "Yes, proceed"

        # 4. User taps Emergency Abort
        abort_query = {
            "id": "cb_3",
            "data": f"abort_call_{call_id}",
            "message": {"chat": {"id": chat_id}}
        }
        await mock_bot.handle_callback_query(abort_query)

        # Verify session is ended and cleaned up
        assert call_id not in mock_bot.active_call_sessions
        assert session.status == CallStatus.ENDED

@pytest.mark.anyio
async def test_telephony_callback_cancel(mock_bot):
    chat_id = 12345
    callee = CalleeInfo(name="Doctor", phone_number="+919876543299", source="contacts")

    with patch("pico.telegram_bot.resolve_callee", new_callable=AsyncMock) as mock_resolve:
        mock_resolve.return_value = callee
        await mock_bot.handle_message(chat_id, "/call doctor confirm appointment", "Ayush")
        card_markup = mock_bot.api.send_message.call_args[1].get("reply_markup", {})
        flat_buttons = [b for row in card_markup.get("inline_keyboard", []) for b in row]
        cancel_btn = next(b for b in flat_buttons if "Cancel" in b["text"])
        cancel_cb_data = cancel_btn["callback_data"]

        cb_query = {
            "id": "cb_cancel",
            "data": cancel_cb_data,
            "message": {"chat": {"id": chat_id}}
        }
        await mock_bot.handle_callback_query(cb_query)
        mock_bot.api.answer_callback_query.assert_called_with("cb_cancel", text="Call cancelled ❌")
        last_msg = mock_bot.api.send_message.call_args[0][1]
        assert "Doctor call cancelled" in last_msg
