"""
Hardware Profiler & Device Tier Engine for Pico.
Adapted from OpenCode, AGY, and Artemis mobile-use patterns.
Enforces hardware gating: keeps low-end devices lightweight & battery-friendly,
while unlocking on-device Chromium and hardware agents on high-end phones.
"""

import os
import shutil
import subprocess
from enum import Enum
from dataclasses import dataclass
from typing import Optional, Dict, Any


class DeviceTier(str, Enum):
    LITE = "LITE"          # < 4.0 GB RAM or < 6 CPU cores (Budget/Constrained devices)
    BALANCED = "BALANCED"  # 4.0 - 5.9 GB RAM and >= 6 cores (Mid-range devices)
    PRO = "PRO"            # >= 6.0 GB RAM and >= 6 cores (Flagship/High-performance devices)


@dataclass
class DeviceInfo:
    model: str
    brand: str
    android_version: str
    soc: str
    total_ram_gb: float
    available_ram_gb: float
    cpu_cores: int
    cpu_load_1m: float
    disk_free_gb: float
    disk_total_gb: float
    tier: DeviceTier
    can_run_local_browser: bool
    can_use_audio: bool
    can_run_heavy_watchers: bool

    def to_dict(self) -> Dict[str, Any]:
        return {
            "model": self.model,
            "brand": self.brand,
            "android_version": self.android_version,
            "soc": self.soc,
            "total_ram_gb": round(self.total_ram_gb, 2),
            "available_ram_gb": round(self.available_ram_gb, 2),
            "cpu_cores": self.cpu_cores,
            "cpu_load_1m": round(self.cpu_load_1m, 2),
            "disk_free_gb": round(self.disk_free_gb, 2),
            "disk_total_gb": round(self.disk_total_gb, 2),
            "tier": self.tier.value,
            "can_run_local_browser": self.can_run_local_browser,
            "can_use_audio": self.can_use_audio,
            "can_run_heavy_watchers": self.can_run_heavy_watchers
        }


class DeviceProfiler:
    """
    Non-blocking system capability detector.
    Uses zero-overhead Linux /proc filesystem and Android system properties.
    """

    _cached_info: Optional[DeviceInfo] = None

    @classmethod
    def _get_android_prop(cls, prop_name: str) -> str:
        try:
            return subprocess.check_output(
                ["getprop", prop_name],
                text=True,
                stderr=subprocess.DEVNULL,
                timeout=1.0
            ).strip()
        except Exception:
            return ""

    @classmethod
    def _read_meminfo(cls) -> tuple[float, float]:
        """Returns (total_ram_gb, available_ram_gb)."""
        total_kb = 0
        avail_kb = 0
        try:
            if os.path.exists("/proc/meminfo"):
                with open("/proc/meminfo", "r") as f:
                    for line in f:
                        if line.startswith("MemTotal:"):
                            total_kb = int(line.split()[1])
                        elif line.startswith("MemAvailable:"):
                            avail_kb = int(line.split()[1])
            else:
                # Fallback for non-Linux
                total_kb = 4 * 1024 * 1024
                avail_kb = 2 * 1024 * 1024
        except Exception:
            total_kb = 4 * 1024 * 1024
            avail_kb = 2 * 1024 * 1024

        total_gb = total_kb / (1024 * 1024)
        avail_gb = (avail_kb or (total_kb * 0.4)) / (1024 * 1024)
        return total_gb, avail_gb

    @classmethod
    def _read_cpu_load(cls) -> float:
        try:
            if hasattr(os, "getloadavg"):
                return os.getloadavg()[0]
            if os.path.exists("/proc/loadavg"):
                with open("/proc/loadavg", "r") as f:
                    return float(f.read().split()[0])
        except Exception:
            pass
        return 0.5

    @classmethod
    def inspect(cls, force_refresh: bool = False) -> DeviceInfo:
        """Inspects hardware and returns classified DeviceInfo."""
        """Inspects hardware and returns classified DeviceInfo."""
        if cls._cached_info and not force_refresh:
            return cls._cached_info

        brand = cls._get_android_prop("ro.product.brand") or "Generic"
        model_name = cls._get_android_prop("ro.product.model") or "Device"
        full_model = f"{brand.capitalize()} {model_name}" if brand != "Generic" else model_name
        android_ver = cls._get_android_prop("ro.build.version.release") or "Linux"
        soc = cls._get_android_prop("ro.soc.model") or cls._get_android_prop("ro.board.platform") or "ARM64"

        total_ram_gb, avail_ram_gb = cls._read_meminfo()
        cpu_cores = os.cpu_count() or 4
        cpu_load = cls._read_cpu_load()

        # Disk usage
        try:
            total_bytes, used_bytes, free_bytes = shutil.disk_usage("/")
            disk_free_gb = free_bytes / (1024 ** 3)
            disk_total_gb = total_bytes / (1024 ** 3)
        except Exception:
            disk_free_gb = 10.0
            disk_total_gb = 64.0

        # Tier grading logic
        if total_ram_gb < 4.0 or cpu_cores < 6:
            tier = DeviceTier.LITE
            can_browser = False
            can_audio = False
            can_heavy_watchers = False
        elif total_ram_gb < 6.0:
            tier = DeviceTier.BALANCED
            can_browser = (avail_ram_gb >= 1.5)
            can_audio = True
            can_heavy_watchers = True
        else:
            tier = DeviceTier.PRO
            can_browser = True
            can_audio = True
            can_heavy_watchers = True

        info = DeviceInfo(
            model=full_model,
            brand=brand,
            android_version=android_ver,
            soc=soc,
            total_ram_gb=total_ram_gb,
            available_ram_gb=avail_ram_gb,
            cpu_cores=cpu_cores,
            cpu_load_1m=cpu_load,
            disk_free_gb=disk_free_gb,
            disk_total_gb=disk_total_gb,
            tier=tier,
            can_run_local_browser=can_browser,
            can_use_audio=can_audio,
            can_run_heavy_watchers=can_heavy_watchers
        )

        cls._cached_info = info
        return info

    @classmethod
    def get_tier(cls) -> DeviceTier:
        return cls.inspect().tier

    @classmethod
    def get_stats(cls) -> DeviceInfo:
        return cls.inspect()

    @classmethod
    def can_run_browser(cls) -> tuple[bool, str]:
        """Validates if current device is allowed to spawn on-device Chromium."""
        info = cls.inspect(force_refresh=True)
        if info.tier == DeviceTier.LITE:
            return (
                False,
                f"Locked to Lite Mode ({info.total_ram_gb:.1f}GB RAM / {info.cpu_cores} cores). "
                "On-device Chromium is disabled to keep your phone snappy and prevent battery drain."
            )
        if info.available_ram_gb < 0.8:
            return (
                False,
                f"Low available memory ({info.available_ram_gb:.2f}GB free). "
                "Please close heavy background apps before launching Chromium."
            )
        return True, "Eligible"

    @classmethod
    def format_diagnostic_card(cls) -> str:
        """Formatted diagnostics for mobile users and Telegram bot."""
        info = cls.inspect(force_refresh=True)
        badge = "🟢 PRO" if info.tier == DeviceTier.PRO else ("🟡 BALANCED" if info.tier == DeviceTier.BALANCED else "🛡️ LITE")
        browser_status = "✅ Enabled (On-Device Chromium)" if info.can_run_local_browser else "❌ Gated (Lite Cloud Fallback)"
        audio_status = "✅ Enabled" if info.can_use_audio else "❌ Disabled"

        lines = [
            f"📱 **Device Architecture & Hardware Profile**",
            f"• Tier: **{badge}**",
            f"• Phone: **{info.model}** (Android {info.android_version})",
            f"• Chipset: **{info.soc}** ({info.cpu_cores} Cores)",
            f"• Memory: **{info.available_ram_gb:.1f} GB free** / {info.total_ram_gb:.1f} GB total",
            f"• CPU Load (1m): **{info.cpu_load_1m:.2f}**",
            "",
            f"⚡ **Hardware Capability Gates:**",
            f"• Local Chromium Agent: {browser_status}",
            f"• Audio / TTS Alerts: {audio_status}",
            f"• High-Freq Watchers: {'✅ Enabled' if info.can_run_heavy_watchers else '🟡 Throttled'}",
        ]
        return "\n".join(lines)
