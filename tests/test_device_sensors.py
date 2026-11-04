"""
Unit tests for safe non-blocking device sensors and hardware wrappers.
"""

import pytest
from unittest.mock import patch
from pico.device_sensors import (
    SafeCommandRunner,
    BatterySensor,
    BatteryStatus,
    ClipboardBridge,
    AppLauncher
)


@pytest.mark.anyio
async def test_safe_command_runner_echo():
    ok, out, err = await SafeCommandRunner.run(["echo", "hello_pico"])
    assert ok is True
    assert out == "hello_pico"
    assert err == ""


@pytest.mark.anyio
async def test_safe_command_runner_timeout():
    # Command that sleeps longer than timeout
    ok, out, err = await SafeCommandRunner.run(["sleep", "2"], timeout=0.2)
    assert ok is False
    assert err == "TIMEOUT"


@pytest.mark.anyio
async def test_safe_command_runner_not_found():
    ok, out, err = await SafeCommandRunner.run(["__non_existent_binary_xyz_123__"], timeout=0.5)
    assert ok is False
    assert err in ["COMMAND_NOT_FOUND", "TIMEOUT"] or "No such file" in err


@pytest.mark.anyio
async def test_battery_sensor_parsing():
    mock_json = '{"percentage": 78, "temperature": 31.2, "status": "CHARGING", "plugged": "AC"}'
    with patch.object(SafeCommandRunner, "run", return_value=(True, mock_json, "")):
        status = await BatterySensor.get_status()
        assert status.available is True
        assert status.percentage == 78
        assert status.temperature_c == 31.2
        assert status.is_charging is True
        assert "78%" in status.to_summary()


@pytest.mark.anyio
async def test_battery_sensor_low_unplugged_reminder():
    mock_json = '{"percentage": 14, "temperature": 30.0, "status": "DISCHARGING", "plugged": "UNPLUGGED"}'
    with patch.object(SafeCommandRunner, "run", return_value=(True, mock_json, "")):
        remind, msg = await BatterySensor.should_remind_plug_in()
        assert remind is True
        assert "14%" in msg
        assert "unplugged" in msg.lower()


@pytest.mark.anyio
async def test_battery_sensor_charging_no_reminder():
    mock_json = '{"percentage": 14, "temperature": 30.0, "status": "CHARGING", "plugged": "AC"}'
    with patch.object(SafeCommandRunner, "run", return_value=(True, mock_json, "")):
        remind, msg = await BatterySensor.should_remind_plug_in()
        assert remind is False


@pytest.mark.anyio
async def test_battery_sensor_unavailable():
    with patch.object(SafeCommandRunner, "run", return_value=(False, "", "TIMEOUT")):
        status = await BatterySensor.get_status()
        assert status.available is False
        assert status.percentage is None
        assert "Not reporting" in status.to_summary()


def test_app_launcher_aliases():
    assert "spotify" in AppLauncher.APP_MAP
    assert "youtube" in AppLauncher.APP_MAP
    assert "tradingview" in AppLauncher.APP_MAP


@pytest.mark.anyio
async def test_app_launcher_unknown():
    ok, msg = await AppLauncher.launch_app("some_fake_app_123")
    assert ok is False
    assert "Unknown app" in msg
