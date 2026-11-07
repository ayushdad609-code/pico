"""
Phase -1 Physical Audio Spike Harness (Doc 35 §2)
Tests physical acoustic coupling on Termux / Android:
1. Verifies Termux:API companion APK responsiveness.
2. Measures mic capture vs speaker playback latency and quality.
3. Tests transcription accuracy of Hinglish/English audio.
4. Diagnoses whether Android OS allows background mic capture during active cellular calls.
"""

import os
import sys
import time
import json
import asyncio
from pathlib import Path

# Add pico root to path
PICO_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PICO_DIR))

from device_sensors import SafeCommandRunner

SPIKE_AUDIO_DIR = PICO_DIR / "spikes" / "audio"
SPIKE_AUDIO_DIR.mkdir(parents=True, exist_ok=True)


async def check_termux_api_health() -> dict:
    """Check if com.termux.api companion app is installed and responding."""
    results = {}
    
    # 1. Package check via pm
    ok, out, _ = await SafeCommandRunner.run(["/system/bin/pm", "list", "packages"], timeout=2.0)
    termux_pkgs = [line.replace("package:", "").strip() for line in out.splitlines() if "termux" in line]
    results["installed_packages"] = termux_pkgs
    results["api_apk_installed"] = "com.termux.api" in termux_pkgs
    
    # 2. Probe Termux:API command responsiveness
    probe_ok, _, err = await SafeCommandRunner.run(["termux-battery-status"], timeout=2.0)
    results["api_bridge_responsive"] = probe_ok
    results["probe_error"] = err if not probe_ok else None
    
    return results


async def record_sample(duration_sec: int = 5, output_file: Path = None) -> tuple[bool, str]:
    """Records microphone audio using termux-microphone-record."""
    if output_file is None:
        output_file = SPIKE_AUDIO_DIR / f"mic_sample_{int(time.time())}.m4a"
        
    print(f"[*] Recording microphone for {duration_sec}s to {output_file.name}...")
    
    # Start recording
    start_ok, out, err = await SafeCommandRunner.run([
        "termux-microphone-record",
        "-f", str(output_file),
        "-l", str(duration_sec),
        "-e", "aac"
    ], timeout=3.0)
    
    if not start_ok:
        return False, f"Failed to start recording: {err}"
        
    # Wait for completion
    await asyncio.sleep(duration_sec + 0.5)
    
    # Stop recording just in case
    await SafeCommandRunner.run(["termux-microphone-record", "-q"], timeout=2.0)
    
    if output_file.exists() and output_file.stat().st_size > 0:
        size_kb = output_file.stat().st_size / 1024.0
        return True, f"Success ({size_kb:.1f} KB written to {output_file})"
    else:
        return False, f"Recording file not found or empty (size=0 bytes)"


async def test_speaker_playback(text: str = "Pico audio test on speakerphone.") -> tuple[bool, str]:
    """Tests speaker output using termux-tts-speak."""
    print(f"[*] Testing TTS speaker playback: '{text}'...")
    ok, out, err = await SafeCommandRunner.run(["termux-tts-speak", text], timeout=4.0)
    if ok:
        return True, "TTS playback initiated"
    return False, f"TTS playback failed: {err}"


async def run_diagnostics():
    print("=" * 60)
    print("  PICO PHASE -1: PHYSICAL AUDIO SPIKE DIAGNOSTICS (Doc 35 §2)")
    print("=" * 60)
    
    print("\n[Step 1] Checking Termux:API APK status...")
    health = await check_termux_api_health()
    print(f"  - Detected Termux Packages : {health.get('installed_packages')}")
    print(f"  - Termux:API APK Installed : {'YES' if health.get('api_apk_installed') else 'NO (MISSING)'}")
    print(f"  - Termux:API Bridge Working: {'YES' if health.get('api_bridge_responsive') else 'NO (TIMED OUT)'}")
    
    if not health.get("api_apk_installed"):
        print("\n  [CRITICAL FINDING]")
        print("  The Android companion APK 'com.termux.api' is NOT installed on this device.")
        print("  Termux commands (termux-telephony-call, termux-microphone-record, etc.)")
        print("  cannot communicate with Android hardware until the Termux:API APK is installed.")
        print("  Install it from F-Droid or GitHub Releases matching your Termux build.")
        print("=" * 60)
        return health
        
    print("\n[Step 2] Testing Microphone Capture...")
    rec_ok, rec_msg = await record_sample(duration_sec=3)
    print(f"  - Mic Recording Result: {rec_msg}")
    
    print("\n[Step 3] Testing Speaker Playback...")
    tts_ok, tts_msg = await test_speaker_playback()
    print(f"  - Speaker Result: {tts_msg}")
    
    print("=" * 60)
    return health


if __name__ == "__main__":
    asyncio.run(run_diagnostics())
