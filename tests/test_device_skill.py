"""
Tests for DeviceSkill & Natural Language Hardware Integration in Pico.
"""

import pytest
from unittest.mock import patch
from pico.models import UserProfile
from pico.memory import MemoryStore
from pico.pipeline import PipelineEngine
from pico.onboarding import OnboardingFlow
from pico.skills.device_skill import DeviceSkill
from pico.device import DeviceTier


def test_device_skill_storage():
    skill = DeviceSkill()
    res = skill.execute({"action": "storage"})
    assert res.success is True
    assert res.output["total_gb"] > 0
    assert res.output["free_gb"] > 0
    assert "Storage:" in res.output["status_text"]


def test_device_skill_specs():
    skill = DeviceSkill()
    res = skill.execute({"action": "specs"})
    assert res.success is True
    assert res.output["tier"] in ["lite", "balanced", "pro"]
    assert res.output["cpu_cores"] > 0
    assert res.output["total_ram_gb"] > 0


def test_device_skill_battery_non_blocking():
    skill = DeviceSkill()
    res = skill.execute({"action": "battery"})
    assert res.success is True
    assert "status_text" in res.output


def test_device_skill_full_status():
    skill = DeviceSkill()
    res = skill.execute({"action": "status"})
    assert res.success is True
    assert "specs" in res.output
    assert "storage" in res.output
    assert "battery" in res.output
    assert "summary_text" in res.output


def test_device_skill_low_device_app_launch_restricted():
    skill = DeviceSkill()
    with patch("pico.skills.device_skill.DeviceProfiler.get_tier", return_value=DeviceTier.LITE):
        res = skill.execute({"action": "launch_app", "app_name": "spotify"})
        assert res.success is True
        assert res.output["launched"] is False
        assert res.output["reason"] == "LITE_TIER_PROTECTION"
        assert "restricted in LITE device tier" in res.output["status_text"]


def test_pipeline_device_storage_query():
    memory = MemoryStore(":memory:")
    pipeline = PipelineEngine(memory)
    profile = OnboardingFlow.create_fast_path_profile("test_device_user", "Ayush")

    # Natural language query about phone storage
    res = pipeline.run("Pico, how much free storage space do I have on my phone?", profile)
    assert res["status"] == "ok"
    assert len(res["output"]) > 20
    # Output should mention storage or GB
    out_lower = res["output"].lower()
    assert any(w in out_lower for w in ["storage", "gb", "free", "space", "device", "phone"])
