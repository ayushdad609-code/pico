"""
Android Hardware & System Diagnostic Skill for Pico.
Allows Pico to inspect device sensors, storage, memory tier, and safely trigger approved phone intents.
"""

import os
import time
import json
import subprocess
from typing import Dict, Any, Optional

from .base_skill import BaseSkill, SkillResult
from pico.mcp_host import PermissionLevel
from pico.device import DeviceProfiler, DeviceTier
from pico.paths import get_pico_home


class DeviceSkill(BaseSkill):
    name = "device_skill"
    description = "Inspects Android phone hardware (battery, storage, RAM, CPU tier) and executes safe device actions."
    version = "v1.1"
    permission_level = PermissionLevel.SEE
    parameters_schema = {
        "action": {"type": "string", "required": True, "description": "One of: 'status', 'storage', 'battery', 'specs', 'launch_app'"},
        "app_name": {"type": "string", "required": False, "description": "App alias when action is 'launch_app'"}
    }

    def execute(self, inputs: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> SkillResult:
        start_t = time.time()
        action = inputs.get("action", "status").lower()

        try:
            if action in ["storage", "disk", "free space"]:
                res = self._get_storage()
            elif action == "battery":
                res = self._get_battery()
            elif action in ["specs", "hardware", "cpu", "ram", "memory"]:
                res = self._get_specs()
            elif action == "launch_app":
                app_name = inputs.get("app_name", "")
                res = self._launch_app(app_name)
            else:
                res = self._get_full_status()

            lat = round((time.time() - start_t) * 1000, 2)
            return SkillResult(
                success=True,
                skill_name=self.name,
                output=res,
                execution_time_ms=lat
            )
        except Exception as e:
            return SkillResult(
                success=False,
                skill_name=self.name,
                output={},
                error=str(e),
                execution_time_ms=round((time.time() - start_t) * 1000, 2)
            )

    @staticmethod
    def _get_storage() -> Dict[str, Any]:
        target_dir = str(get_pico_home())
        st = os.statvfs(target_dir)
        total_gb = round((st.f_blocks * st.f_frsize) / (1024**3), 1)
        free_gb = round((st.f_bavail * st.f_frsize) / (1024**3), 1)
        used_gb = round(total_gb - free_gb, 1)
        used_pct = round((used_gb / total_gb) * 100, 1) if total_gb > 0 else 0
        return {
            "total_gb": total_gb,
            "free_gb": free_gb,
            "used_gb": used_gb,
            "used_percentage": used_pct,
            "status_text": f"💾 Storage: {free_gb} GB free of {total_gb} GB ({used_pct}% used)"
        }

    @staticmethod
    def _get_battery() -> Dict[str, Any]:
        try:
            p = subprocess.run(["termux-battery-status"], capture_output=True, text=True, timeout=1.5)
            if p.returncode == 0 and p.stdout.strip():
                d = json.loads(p.stdout)
                pct = d.get("percentage")
                temp = d.get("temperature")
                status = d.get("status", "").upper()
                plugged = d.get("plugged", "").upper()
                charging = (status in ["CHARGING", "FULL"]) or (plugged in ["AC", "USB", "WIRELESS"])
                icon = "⚡ Charging" if charging else "🔋 Discharging"
                return {
                    "available": True,
                    "percentage": pct,
                    "temperature_c": temp,
                    "is_charging": charging,
                    "status_text": f"{icon} at {pct}%" + (f" ({temp}°C)" if temp else "")
                }
        except Exception:
            pass
        return {
            "available": False,
            "status_text": "🔋 Battery sensor: Termux:API sleeping or unplugged"
        }

    @staticmethod
    def _get_specs() -> Dict[str, Any]:
        stats = DeviceProfiler.get_stats()
        tier = stats.tier
        return {
            "tier": tier.value.lower(),
            "total_ram_gb": round(stats.total_ram_gb, 2),
            "available_ram_gb": round(stats.available_ram_gb, 2),
            "cpu_cores": stats.cpu_cores,
            "device_model": stats.model,
            "soc_model": stats.soc,
            "can_run_browser": stats.can_run_local_browser,
            "status_text": f"📱 {stats.model} ({stats.soc}) | Tier: {tier.value.upper()} | {stats.total_ram_gb:.1f} GB RAM ({stats.available_ram_gb:.1f} GB avail) | {stats.cpu_cores} Cores"
        }

    @staticmethod
    def _launch_app(app_name: str) -> Dict[str, Any]:
        from pico.device_sensors import AppLauncher
        # Check low device gate
        tier = DeviceProfiler.get_tier()
        if tier == DeviceTier.LITE:
            return {
                "launched": False,
                "app": app_name,
                "reason": "LITE_TIER_PROTECTION",
                "status_text": "⚠️ App launching is restricted in LITE device tier (<4GB RAM) to prevent memory pressure."
            }

        import asyncio
        try:
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None

            if loop and loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                    ok, msg = pool.submit(asyncio.run, AppLauncher.launch_app(app_name)).result()
            else:
                ok, msg = asyncio.run(AppLauncher.launch_app(app_name))
        except Exception as e:
            ok, msg = False, str(e)

        return {
            "launched": ok,
            "app": app_name,
            "status_text": msg
        }

    def _get_full_status(self) -> Dict[str, Any]:
        storage = self._get_storage()
        battery = self._get_battery()
        specs = self._get_specs()
        return {
            "specs": specs,
            "storage": storage,
            "battery": battery,
            "summary_text": f"{specs['status_text']}\n{storage['status_text']}\n{battery['status_text']}"
        }
