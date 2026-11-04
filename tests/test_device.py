"""
Unit tests for DeviceProfiler and Hardware Tier Gating.
"""

from unittest.mock import patch
from pico.device import DeviceProfiler, DeviceTier, DeviceInfo


def test_device_profiler_real_system():
    info = DeviceProfiler.inspect(force_refresh=True)
    assert info.total_ram_gb > 0
    assert info.cpu_cores >= 1
    assert info.tier in [DeviceTier.LITE, DeviceTier.BALANCED, DeviceTier.PRO]
    assert isinstance(info.model, str)
    assert len(info.model) > 0


def test_device_profiler_low_end_mock():
    # Mock a low-end 3GB RAM / 4-core device
    with patch.object(DeviceProfiler, "_read_meminfo", return_value=(3.0, 1.0)):
        with patch("os.cpu_count", return_value=4):
            DeviceProfiler._cached_info = None
            info = DeviceProfiler.inspect(force_refresh=True)
            assert info.tier == DeviceTier.LITE
            assert info.can_run_local_browser is False
            assert info.can_use_audio is False

            can_run, reason = DeviceProfiler.can_run_browser()
            assert can_run is False
            assert "Locked to Lite Mode" in reason


def test_device_profiler_mid_range_mock():
    # Mock a 5GB RAM / 6-core device
    with patch.object(DeviceProfiler, "_read_meminfo", return_value=(5.0, 2.0)):
        with patch("os.cpu_count", return_value=6):
            DeviceProfiler._cached_info = None
            info = DeviceProfiler.inspect(force_refresh=True)
            assert info.tier == DeviceTier.BALANCED
            assert info.can_run_local_browser is True
            assert info.can_use_audio is True


def test_device_profiler_flagship_mock():
    # Mock a 12GB RAM / 8-core device
    with patch.object(DeviceProfiler, "_read_meminfo", return_value=(12.0, 6.0)):
        with patch("os.cpu_count", return_value=8):
            DeviceProfiler._cached_info = None
            info = DeviceProfiler.inspect(force_refresh=True)
            assert info.tier == DeviceTier.PRO
            assert info.can_run_local_browser is True
            assert info.can_use_audio is True
            assert info.can_run_heavy_watchers is True

            can_run, reason = DeviceProfiler.can_run_browser()
            assert can_run is True
            assert reason == "Eligible"


def test_format_diagnostic_card():
    card = DeviceProfiler.format_diagnostic_card()
    assert "Device Architecture" in card
    assert "Memory:" in card
    assert "Hardware Capability Gates:" in card
