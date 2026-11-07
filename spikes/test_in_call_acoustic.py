"""
In-Call Acoustic Coupling Test (Doc 35 §2)
Dials safe toll-free IVR (198), records 6s of audio during the call,
and analyzes whether Android OS allows background mic capture or mutes it.
"""

import sys
import time
import asyncio
import struct
import math
from pathlib import Path

PICO_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PICO_DIR))

from device_sensors import SafeCommandRunner

AUDIO_DIR = PICO_DIR / "spikes" / "audio"
AUDIO_DIR.mkdir(parents=True, exist_ok=True)
SAMPLE_M4A = AUDIO_DIR / "in_call_sample.m4a"
SAMPLE_WAV = AUDIO_DIR / "in_call_sample.wav"


def calculate_audio_energy(wav_path: Path) -> dict:
    """Reads raw PCM/WAV and calculates RMS energy and silence percentage."""
    if not wav_path.exists() or wav_path.stat().st_size < 100:
        return {"error": "File empty or missing"}
    
    with open(wav_path, "rb") as f:
        # Skip WAV header (44 bytes)
        f.seek(44)
        raw_bytes = f.read()

    sample_count = len(raw_bytes) // 2
    if sample_count == 0:
        return {"error": "No audio samples"}

    samples = struct.unpack(f"<{sample_count}h", raw_bytes[:sample_count * 2])
    sum_sq = sum(s * s for s in samples)
    rms = math.sqrt(sum_sq / sample_count)
    max_sample = max(abs(s) for s in samples)
    silent_samples = sum(1 for s in samples if abs(s) < 50)
    silence_pct = (silent_samples / sample_count) * 100.0

    return {
        "sample_count": sample_count,
        "duration_sec": round(sample_count / 16000.0, 2),
        "rms_energy": round(rms, 2),
        "peak_amplitude": max_sample,
        "silence_percentage": round(silence_pct, 1)
    }


async def run_in_call_test(number: str = "198"):
    print("=" * 60)
    print(f"  PHASE -1 SPIKE: DIALING TOLL-FREE IVR ({number})")
    print("=" * 60)
    
    # Clean previous test audio
    if SAMPLE_M4A.exists():
        SAMPLE_M4A.unlink()
    if SAMPLE_WAV.exists():
        SAMPLE_WAV.unlink()

    print(f"\n[1/4] Triggering call to {number} via termux-telephony-call...")
    ok, out, err = await SafeCommandRunner.run(["termux-telephony-call", number], timeout=3.0)
    if not ok:
        print(f"[-] Dial failed: {err}")
        return
    print(f"[+] Call initiated successfully to {number}!")
    
    print("\n[2/4] Waiting 6 seconds for call connect...")
    print("      👉 NOTE: Please ensure SPEAKERPHONE is turned ON on your call screen!")
    for i in range(6, 0, -1):
        print(f"      Connecting... {i}s", end="\r", flush=True)
        await asyncio.sleep(1.0)
    print("\n")

    print("[3/4] Recording 6 seconds of in-call audio from microphone...")
    rec_ok, out, err = await SafeCommandRunner.run([
        "termux-microphone-record",
        "-f", str(SAMPLE_M4A),
        "-l", "6",
        "-e", "aac"
    ], timeout=3.0)
    
    if not rec_ok:
        print(f"[-] Recording trigger failed: {err}")
        return

    # Wait for the recording to finish
    await asyncio.sleep(6.5)
    await SafeCommandRunner.run(["termux-microphone-record", "-q"], timeout=2.0)

    if not SAMPLE_M4A.exists() or SAMPLE_M4A.stat().st_size == 0:
        print("[-] Recording failed: audio file was not written by Android.")
        return

    size_kb = SAMPLE_M4A.stat().st_size / 1024.0
    print(f"[+] Audio captured! File size: {size_kb:.1f} KB")

    print("\n[4/4] Converting to PCM & Analyzing Signal Energy...")
    # Convert m4a to 16kHz mono WAV for analysis
    conv_ok, _, conv_err = await SafeCommandRunner.run([
        "ffmpeg", "-y", "-i", str(SAMPLE_M4A),
        "-ar", "16000", "-ac", "1", str(SAMPLE_WAV)
    ], timeout=5.0)

    if not conv_ok:
        print(f"[-] FFmpeg conversion error: {conv_err}")
        return

    metrics = calculate_audio_energy(SAMPLE_WAV)
    print("\n" + "=" * 60)
    print("  AUDIO COUPLING ANALYSIS RESULTS")
    print("=" * 60)
    print(f"  - Duration Recorded  : {metrics.get('duration_sec')} seconds")
    print(f"  - RMS Energy Level   : {metrics.get('rms_energy')}")
    print(f"  - Peak Amplitude     : {metrics.get('peak_amplitude')} / 32767")
    print(f"  - Silence Ratio      : {metrics.get('silence_percentage')}%")
    print("-" * 60)

    rms = metrics.get("rms_energy", 0)
    if rms < 80:
        print("  ⚠️ VERDICT: SILENCE / MUTED")
        print("  Android OS blocked or muted background mic capture during active GSM call.")
        print("  This is standard stock Android protection against call recording apps.")
    elif rms < 300:
        print("  ⚠️ VERDICT: VERY FAINT / AMBIENT ONLY")
        print("  Speakerphone volume may be low or mic is picking up faint room noise.")
    else:
        print("  ✅ VERDICT: LIVE SPEECH / CALL AUDIO DETECTED!")
        print("  Microphone successfully captured audio while call was active.")
    print("=" * 60)
    print("\n(You can now tap 'End Call' on your phone screen whenever you want.)")


if __name__ == "__main__":
    asyncio.run(run_in_call_test("198"))
