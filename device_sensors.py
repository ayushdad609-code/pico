"""
Safe Non-Blocking Android Device Sensor & Hardware Bridge for Pico.
Adapted from Artemis (mobile-use) and OpenCode patterns.
All hardware operations use strict non-blocking async timeouts (1.5s - 2.0s)
to guarantee Termux:API never hangs Python or crashes Pico.
"""

import os
import json
import asyncio
import logging
import subprocess
from dataclasses import dataclass
from typing import Optional, Dict, Any, Tuple

logger = logging.getLogger("pico.device_sensors")


# =====================================================================
# 1. TIMEOUT-ENFORCED SUBPROCESS RUNNER
# =====================================================================

class SafeCommandRunner:
    """Runs system commands with hard timeouts and process tree cleanup."""

    @staticmethod
    async def run(cmd: list[str], timeout: float = 1.5) -> Tuple[bool, str, str]:
        """
        Runs an async command. Returns (success, stdout_str, stderr_str).
        Kills process on timeout and never hangs.
        """
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            out_str = stdout.decode("utf-8", errors="replace").strip()
            err_str = stderr.decode("utf-8", errors="replace").strip()
            return proc.returncode == 0, out_str, err_str
        except asyncio.TimeoutError:
            try:
                proc.kill()
                await proc.wait()
            except Exception:
                pass
            logger.debug(f"Command '{cmd[0]}' timed out after {timeout}s")
            return False, "", "TIMEOUT"
        except FileNotFoundError:
            return False, "", "COMMAND_NOT_FOUND"
        except Exception as e:
            return False, "", str(e)


# =====================================================================
# 2. BATTERY & THERMAL SENSOR
# =====================================================================

@dataclass
class BatteryStatus:
    percentage: Optional[int] = None
    temperature_c: Optional[float] = None
    is_charging: bool = False
    status: str = "UNKNOWN"
    available: bool = False

    def to_summary(self) -> str:
        if not self.available or self.percentage is None:
            return "🔋 Battery status: External / Not reporting"
        charge_icon = "⚡ Charging" if self.is_charging else "🔋 Discharging"
        temp_str = f" ({self.temperature_c:.1f}°C)" if self.temperature_c else ""
        return f"{charge_icon} at **{self.percentage}%**{temp_str}"


class BatterySensor:
    """Reads device battery and charging state with graceful fallback."""

    @classmethod
    async def get_status(cls, timeout: float = 1.5) -> BatteryStatus:
        ok, out, _ = await SafeCommandRunner.run(["termux-battery-status"], timeout=timeout)
        if not ok or not out:
            return BatteryStatus(available=False)

        try:
            data = json.loads(out)
            percentage = data.get("percentage")
            temp = data.get("temperature")
            status = data.get("status", "").upper()
            plugged = data.get("plugged", "").upper()
            is_charging = (status in ["CHARGING", "FULL"]) or (plugged in ["AC", "USB", "WIRELESS"])

            return BatteryStatus(
                percentage=percentage,
                temperature_c=temp,
                is_charging=is_charging,
                status=status,
                available=True
            )
        except Exception as e:
            logger.debug(f"Failed to parse termux-battery-status: {e}")
            return BatteryStatus(available=False)

    @classmethod
    async def should_remind_plug_in(cls) -> Tuple[bool, str]:
        """Returns True if battery is under 20% and not currently charging."""
        bs = await cls.get_status()
        if bs.available and bs.percentage is not None:
            if bs.percentage <= 20 and not bs.is_charging:
                return True, f"Battery is low at {bs.percentage}% and unplugged! Plug your phone in so routines stay active."
        return False, ""


# =====================================================================
# 3. ANDROID CLIPBOARD BRIDGE
# =====================================================================

class ClipboardBridge:
    """Safely copies and reads system clipboard without blocking."""

    @staticmethod
    async def read_text(timeout: float = 1.5) -> Optional[str]:
        ok, out, _ = await SafeCommandRunner.run(["termux-clipboard-get"], timeout=timeout)
        return out if ok and out else None

    @staticmethod
    async def copy_text(text: str, timeout: float = 1.5) -> bool:
        if not text:
            return False
        # Use stdin pipe to prevent shell escaping bugs
        try:
            proc = await asyncio.create_subprocess_exec(
                "termux-clipboard-set",
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            await asyncio.wait_for(proc.communicate(input=text.encode("utf-8")), timeout=timeout)
            return proc.returncode == 0
        except Exception:
            return False


# =====================================================================
# 4. APP LAUNCHER & ANDROID INTENTS (from Artemis patterns)
# =====================================================================

class AppLauncher:
    """Safe application and URL launcher via Android Activity Manager."""

    APP_MAP = {
        "spotify": "com.spotify.music",
        "youtube": "com.google.android.youtube",
        "tradingview": "com.tradingview.tradingviewapp",
        "chrome": "com.android.chrome",
        "settings": "com.android.settings",
        "calculator": "com.google.android.calculator",
        "clock": "com.google.android.deskclock",
    }

    @staticmethod
    async def open_url(url: str, timeout: float = 2.0) -> bool:
        """Opens URL via Android default browser intent."""
        if not url.startswith("http"):
            url = "https://" + url

        # Try termux-open-url first
        ok, _, _ = await SafeCommandRunner.run(["termux-open-url", url], timeout=timeout)
        if ok:
            return True

        # Fallback to Android am start
        ok, _, _ = await SafeCommandRunner.run([
            "am", "start",
            "-a", "android.intent.action.VIEW",
            "-d", url
        ], timeout=timeout)
        return ok

    @classmethod
    async def launch_app(cls, app_alias: str, timeout: float = 2.0) -> Tuple[bool, str]:
        """Launches a known application by alias."""
        pkg = cls.APP_MAP.get(app_alias.lower())
        if not pkg:
            return False, f"Unknown app '{app_alias}'. Supported: {', '.join(cls.APP_MAP.keys())}"

        # Try monkey launch (most reliable in Android shell without knowing MainActivity)
        ok, _, err = await SafeCommandRunner.run([
            "monkey",
            "-p", pkg,
            "-c", "android.intent.category.LAUNCHER",
            "1"
        ], timeout=timeout)

        if ok:
            return True, f"Launched {app_alias.capitalize()} ({pkg})"
        return False, f"Could not launch {app_alias}: {err or 'Permission denied'}"


# =====================================================================
# 5. HAPTICS & TOAST ALERTS
# =====================================================================

class HapticNotifier:
    """Haptic vibrations and on-screen toast alerts."""

    @staticmethod
    async def vibrate(duration_ms: int = 200, timeout: float = 1.0) -> bool:
        ok, _, _ = await SafeCommandRunner.run(["termux-vibrate", "-d", str(duration_ms)], timeout=timeout)
        return ok

    @staticmethod
    async def toast(message: str, timeout: float = 1.0) -> bool:
        ok, _, _ = await SafeCommandRunner.run(["termux-toast", message], timeout=timeout)
        return ok
