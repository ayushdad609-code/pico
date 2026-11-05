"""
Tests for Pico 24/7 Autonomous Process Supervisor & Background Scheduler.
Validates:
1. Process supervisor PID management, wake-lock acquisition, and status diagnostics.
2. Memory RSS and system RAM metric extraction.
3. HeartbeatRunner integration in Telegram bot.
4. /status command output format and sensor health reporting.
5. Termux boot autostart script existence and execution permission.
"""

import os
import time
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from pico.supervisor import PicoProcessSupervisor, BASE_DIR
from pico.telegram_bot import PicoTelegramBot
from pico.models import UserProfile
from pico.heartbeat import HeartbeatRunner


def test_supervisor_pid_alive_and_memory():
    current_pid = os.getpid()
    assert PicoProcessSupervisor.is_pid_alive(current_pid) is True
    assert PicoProcessSupervisor.is_pid_alive(99999999) is False

    rss = PicoProcessSupervisor.get_process_memory_mb(current_pid)
    assert isinstance(rss, int)
    assert rss >= 0


def test_supervisor_status_structure():
    stat = PicoProcessSupervisor.get_status()
    assert "supervisor_alive" in stat
    assert "daemon_alive" in stat
    assert "daemon_rss_mb" in stat
    assert "system_avail_ram_mb" in stat
    assert isinstance(stat["system_avail_ram_mb"], int)


def test_supervisor_wake_lock_handling():
    # Should execute safely without raising exceptions
    res = PicoProcessSupervisor.acquire_wake_lock()
    assert isinstance(res, bool)


def test_termux_boot_script_exists_and_executable():
    boot_script = Path("/data/data/com.termux/files/home/.termux/boot/start-pico.sh")
    assert boot_script.exists()
    assert os.access(boot_script, os.X_OK)
    content = boot_script.read_text()
    assert "termux-wake-lock" in content
    assert "pico.supervisor start" in content


def test_telegram_bot_heartbeat_runner_creation():
    bot = PicoTelegramBot(bot_token="test_token_123", db_path=":memory:")
    profile = UserProfile(user_id="test_user", name="Ayush")

    runner1 = bot.get_or_create_heartbeat_runner(12345, profile)
    assert isinstance(runner1, HeartbeatRunner)
    assert runner1.profile.name == "Ayush"

    # Should return cached instance on second call
    runner2 = bot.get_or_create_heartbeat_runner(12345, profile)
    assert runner1 is runner2


def test_telegram_bot_status_command():
    import asyncio
    bot = PicoTelegramBot(bot_token="test_token_123", db_path=":memory:")
    bot.api = AsyncMock()

    profile = UserProfile(user_id="tg_12345", name="Ayush")
    bot.user_profiles[12345] = profile

    async def run_status():
        await bot.handle_message(chat_id=12345, text="/status", user_first_name="Ayush")

    asyncio.run(run_status())

    assert bot.api.send_message.called
    sent_text = bot.api.send_message.call_args[0][1]
    assert "Pico 24/7 Autonomous Daemon Status" in sent_text
    assert "Uptime" in sent_text
    assert "Available RAM" in sent_text
    assert "Termux Wake Lock" in sent_text
