"""
Unit tests for Pico Live Web Item Price Scraper, Dynamic Schedule Engine, and Multi-Symbol Watcher.
"""

import time
import asyncio
from unittest.mock import AsyncMock, patch

from pico.skills.price_scraper_skill import ItemPriceScraperSkill
from pico.scheduled import ScheduledWorkRegistry, ScheduledJob
from pico.models import UserProfile
from pico.routine import RoutineGraph
from pico.heartbeat import HeartbeatRunner, HeartbeatOutcome
from pico.telegram_bot import PicoTelegramBot


def test_price_scraper_skill_execution():
    skill = ItemPriceScraperSkill()
    res = skill.execute({"url": "https://books.toscrape.com/"})

    assert res.success is True
    assert "items" in res.output
    assert len(res.output["items"]) > 0
    assert "analytics" in res.output
    analytics = res.output["analytics"]
    assert "min" in analytics
    assert "max" in analytics
    assert "avg" in analytics
    assert analytics["min"] <= analytics["max"]
    assert "summary_text" in res.output


def test_dynamic_schedule_registration_and_heartbeat():
    profile = UserProfile(user_id="test_sched_user", name="Ayush")
    sched_reg = ScheduledWorkRegistry.install_defaults(profile)

    job = ScheduledJob(
        id="job_reading_22_00",
        name="Read 20 pages of book",
        schedule_display="Daily at 22:00 IST",
        trigger_time="22:00"
    )
    sched_reg.register(job)

    assert "job_reading_22_00" in sched_reg.jobs
    job_list = sched_reg.list_jobs()
    assert any(j["name"] == "Read 20 pages of book" for j in job_list)

    # Trigger heartbeat at 22:00
    routine = RoutineGraph.seed_from_profile(profile)
    runner = HeartbeatRunner(profile, routine, sched_reg)
    beat = runner.fire_beat("22:00")

    # In quiet hours (22:00) Check 4 becomes PREPARE; otherwise SPEAK
    assert beat.outcome in [HeartbeatOutcome.SPEAK, HeartbeatOutcome.PREPARE]
    assert "Read 20 pages of book" in beat.reason


def test_telegram_scrape_command():
    bot = PicoTelegramBot(bot_token="test_token", db_path=":memory:")
    sent = []
    bot.api.send_message = AsyncMock(side_effect=lambda cid, txt, **kwargs: sent.append(txt))
    bot.api.send_chat_action = AsyncMock()

    profile = UserProfile(user_id="tg_12345", name="Ayush")
    bot.user_profiles[12345] = profile

    async def run_scrape():
        await bot.handle_message(chat_id=12345, text="/scrape https://books.toscrape.com/", user_first_name="Ayush")

    asyncio.run(run_scrape())

    assert len(sent) == 1
    assert "Live Web Item Price Scraper" in sent[0]
    assert "Items Found" in sent[0]


def test_telegram_schedule_command_list_and_add():
    bot = PicoTelegramBot(bot_token="test_token", db_path=":memory:")
    sent = []
    bot.api.send_message = AsyncMock(side_effect=lambda cid, txt, **kwargs: sent.append(txt))

    profile = UserProfile(user_id="tg_12345", name="Ayush")
    bot.user_profiles[12345] = profile

    async def run_sched():
        # 1. List schedules
        await bot.handle_message(chat_id=12345, text="/schedule", user_first_name="Ayush")
        assert "Scheduled Jobs Registry" in sent[-1]

        # 2. Add custom schedule
        await bot.handle_message(chat_id=12345, text="/schedule 19:30 Evening Gym Workout", user_first_name="Ayush")
        assert "Job Scheduled Successfully" in sent[-1]
        assert "19:30 IST" in sent[-1]

    asyncio.run(run_sched())


def test_telegram_watch_multisymbol():
    bot = PicoTelegramBot(bot_token="test_token", db_path=":memory:")
    sent = []
    bot.api.send_message = AsyncMock(side_effect=lambda cid, txt, **kwargs: sent.append(txt))

    profile = UserProfile(user_id="tg_12345", name="Ayush")
    bot.user_profiles[12345] = profile

    async def run_watch():
        await bot.handle_message(chat_id=12345, text="/watch SOL 95.5", user_first_name="Ayush")
        assert "SOLUSDT" in sent[-1]
        assert "Watcher Armed" in sent[-1]

    asyncio.run(run_watch())
