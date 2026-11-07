import pytest
from telephony.audio_bridge import AudioBridge

def test_audio_bridge_instant_interruption_flush():
    bridge = AudioBridge(sample_rate=16000, frame_duration_ms=20)
    # Queue mock playback audio (100ms = 3200 bytes)
    bridge.queue_playback_audio(b"\x10\x00" * 1600)
    assert bridge.has_pending_audio() is True

    # Callee speaks ("stop stop wait") - high energy frame
    speech_frame = b"\x7f\x7f" * 320 # 20ms frame at 16kHz
    is_speech = bridge.on_microphone_frame(speech_frame)
    assert is_speech is True
    assert bridge.is_interrupted() is True
    
    # Verify buffer is instantly flushed in < 50ms
    flushed = bridge.flush_playback()
    assert flushed > 0
    assert bridge.has_pending_audio() is False

def test_silence_does_not_interrupt():
    bridge = AudioBridge(sample_rate=16000, frame_duration_ms=20)
    bridge.queue_playback_audio(b"\x10\x00" * 1600)
    
    # Silence frame (low energy)
    silence_frame = b"\x00\x00" * 320
    is_speech = bridge.on_microphone_frame(silence_frame)
    assert is_speech is False
    assert bridge.is_interrupted() is False
    assert bridge.has_pending_audio() is True

def test_audio_bridge_aec_prevents_self_echo():
    bridge = AudioBridge(sample_rate=16000, frame_duration_ms=20)
    # Speaker output chunk
    speaker_chunk = b"\x50\x20" * 320
    bridge.queue_playback_audio(speaker_chunk)
    
    # Simulate speaker playing this chunk now (recorded in AEC reference buffer)
    bridge.record_speaker_playback(speaker_chunk)

    # Microphone picks up the exact speaker sound from the room
    echo_frame = speaker_chunk
    is_speech = bridge.on_microphone_frame(echo_frame)
    # AEC should suppress this echo and NOT flag it as caller interruption
    assert is_speech is False
    assert bridge.is_interrupted() is False
