import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, "/data/data/com.termux/files/home/pico")
from device_sensors import SafeCommandRunner

async def verify_permissions():
    print("=== TESTING TERMUX:API PERMISSIONS ===")
    
    # 1. Contacts
    ok, out, err = await SafeCommandRunner.run(["termux-contact-list"], timeout=3.0)
    if "Please grant" in out or ("permission" in out.lower() and "error" in out.lower()):
        print(f"[-] Contacts: NOT GRANTED ({out[:80]}...)")
    elif ok and out.strip():
        print(f"[+] Contacts: GRANTED (Successfully read address book, {len(out)} bytes)")
    else:
        print(f"[-] Contacts: status={ok}, err={err}")

    # 2. Mic Recording (3 seconds test)
    test_audio = Path("/data/data/com.termux/files/home/pico/spikes/audio/test_mic.m4a")
    if test_audio.exists():
        test_audio.unlink()
        
    print("[*] Recording 3 seconds of local audio via microphone...")
    ok, out, err = await SafeCommandRunner.run([
        "termux-microphone-record", "-f", str(test_audio), "-l", "3", "-e", "aac"
    ], timeout=3.0)
    
    if ok:
        await asyncio.sleep(3.5)
        await SafeCommandRunner.run(["termux-microphone-record", "-q"], timeout=2.0)
        if test_audio.exists() and test_audio.stat().st_size > 0:
            kb = test_audio.stat().st_size / 1024.0
            print(f"[+] Microphone: GRANTED & WORKING! Recorded {kb:.1f} KB audio file.")
        else:
            print("[-] Microphone: File not created or empty.")
    else:
        print(f"[-] Microphone: Failed to initiate recording: {err}")

    # 3. Speaker / TTS
    print("[*] Testing local speaker playback...")
    ok, out, err = await SafeCommandRunner.run(["termux-tts-speak", "Hello Ayush, Pico audio test complete."], timeout=4.0)
    if ok:
        print("[+] Speaker (TTS): WORKING! (TTS audio played through device speaker)")
    else:
        print(f"[-] Speaker: Failed with error: {err}")

if __name__ == "__main__":
    asyncio.run(verify_permissions())
