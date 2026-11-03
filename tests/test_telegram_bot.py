"""
Pytest unit tests for Pico Telegram Mobile Bot Bridge.
"""

import asyncio
from unittest.mock import AsyncMock, patch
from pico.telegram_bot import PicoTelegramBot, TelegramApiClient


def test_telegram_keyboards():
    bot = PicoTelegramBot(bot_token="mock_token", db_path=":memory:")
    main_kb = bot.build_main_keyboard()
    assert "keyboard" in main_kb
    assert len(main_kb["keyboard"]) >= 3

    outfit_kb = bot.build_outfit_inline_keyboard()
    assert "inline_keyboard" in outfit_kb
    assert any("Chill" in btn["text"] for row in outfit_kb["inline_keyboard"] for btn in row)

    appr_kb = bot.build_approval_keyboard("act_1")
    assert "inline_keyboard" in appr_kb
    assert appr_kb["inline_keyboard"][0][0]["text"] == "✅ Approve"


def test_telegram_message_handlers():
    bot = PicoTelegramBot(bot_token="mock_token", db_path=":memory:")
    sent_messages = []

    async def mock_send_message(chat_id, text, parse_mode=None, reply_markup=None):
        sent_messages.append({"chat_id": chat_id, "text": text, "reply_markup": reply_markup})
        return {"message_id": len(sent_messages)}

    bot.api.send_message = AsyncMock(side_effect=mock_send_message)
    bot.api.send_chat_action = AsyncMock()

    async def run_tests():
        chat_id = 998877

        # 1. /start
        await bot.handle_message(chat_id, "/start", "Ayush")
        assert len(sent_messages) == 1
        assert "I'm Pico!" in sent_messages[-1]["text"]

        # 2. /path
        await bot.handle_message(chat_id, "/path", "Ayush")
        assert "Today's Day Path" in sent_messages[-1]["text"]

        # 3. /brief
        await bot.handle_message(chat_id, "/brief", "Ayush")
        assert "Morning Brief" in sent_messages[-1]["text"]

        # 4. /review
        await bot.handle_message(chat_id, "/review", "Ayush")
        assert "Evening Review" in sent_messages[-1]["text"]

        # 5. /sip
        await bot.handle_message(chat_id, "/sip 5000 15 20", "Ayush")
        assert "SIP Compounding Calculator" in sent_messages[-1]["text"]

        # 6. /outfit
        await bot.handle_message(chat_id, "/outfit", "Ayush")
        assert "Current Outfit" in sent_messages[-1]["text"]

        # 7. /lockin
        await bot.handle_message(chat_id, "/lockin", "Ayush")
        assert "LOCKED IN 🔒" in sent_messages[-1]["text"]

        # 8. /food
        await bot.handle_message(chat_id, "/food roti 2", "Ayush")
        assert "Whole Wheat Roti" in sent_messages[-1]["text"]

        # 9. Natural conversation with fact extraction
        await bot.handle_message(chat_id, "My favorite color is navy blue", "Ayush")
        assert "Pico" in sent_messages[-1]["text"]
        assert "Pencil-note: Pico remembered" in sent_messages[-1]["text"]

        # 10. Check /whatiknow
        await bot.handle_message(chat_id, "/whatiknow", "Ayush")
        assert "favorite_color" in sent_messages[-1]["text"]
        assert "navy blue" in sent_messages[-1]["text"]

    asyncio.run(run_tests())


def test_telegram_callback_queries():
    bot = PicoTelegramBot(bot_token="mock_token", db_path=":memory:")
    sent_messages = []
    answers = []

    bot.api.send_message = AsyncMock(side_effect=lambda cid, txt, **kwargs: sent_messages.append(txt))
    bot.api.answer_callback_query = AsyncMock(side_effect=lambda qid, text=None: answers.append((qid, text)))

    async def run_callbacks():
        chat_id = 998877

        # 1. Outfit button tap
        cb_outfit = {
            "id": "q1",
            "data": "outfit_gym",
            "message": {"chat": {"id": chat_id}}
        }
        await bot.handle_callback_query(cb_outfit)
        assert bot.user_modes[chat_id] == "gym"
        assert any("GYM" in m for m in sent_messages)

        # 2. Approve button tap
        cb_appr = {
            "id": "q2",
            "data": "approve_save_goal",
            "message": {"chat": {"id": chat_id}}
        }
        await bot.handle_callback_query(cb_appr)
        assert any("Approved!" in m for m in sent_messages)

        # 3. Reject button tap
        cb_rej = {
            "id": "q3",
            "data": "reject_save_goal",
            "message": {"chat": {"id": chat_id}}
        }
        await bot.handle_callback_query(cb_rej)
        assert any("Cancelled." in m for m in sent_messages)

    asyncio.run(run_callbacks())
