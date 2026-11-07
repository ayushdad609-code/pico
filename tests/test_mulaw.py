"""Tests for pure-Python G.711 mu-law encoder and decoder."""

import pytest
from telephony.mulaw import (
    linear2ulaw,
    ulaw2linear,
    pcm16_to_mulaw,
    mulaw_to_pcm16,
    resample_16k_to_8k,
    resample_8k_to_16k
)

def test_single_sample_roundtrip():
    # Test silence
    u_silence = linear2ulaw(0)
    assert ulaw2linear(u_silence) == 0

    # Test positive values
    for val in [100, 1000, 5000, 15000, 30000]:
        u = linear2ulaw(val)
        dec = ulaw2linear(u)
        # Mu-law is lossy 8-bit, relative error should be within ~5% for large amplitudes
        diff = abs(val - dec)
        assert diff <= max(100, val * 0.10)

    # Test negative values
    for val in [-100, -1000, -5000, -15000, -30000]:
        u = linear2ulaw(val)
        dec = ulaw2linear(u)
        diff = abs(val - dec)
        assert diff <= max(100, abs(val) * 0.10)


def test_buffer_conversion():
    # 10 samples of 16-bit linear PCM (20 bytes)
    import struct
    samples = [0, 500, 1500, 5000, 10000, -500, -1500, -5000, -10000, 0]
    pcm_bytes = struct.pack(f"<{len(samples)}h", *samples)

    mulaw_bytes = pcm16_to_mulaw(pcm_bytes)
    assert len(mulaw_bytes) == len(samples)

    reconstructed_pcm = mulaw_to_pcm16(mulaw_bytes)
    assert len(reconstructed_pcm) == len(pcm_bytes)

    reconstructed_samples = struct.unpack(f"<{len(samples)}h", reconstructed_pcm)
    for orig, rec in zip(samples, reconstructed_samples):
        assert abs(orig - rec) <= max(100, abs(orig) * 0.10)


def test_resampling_8k_and_16k():
    # 8 samples at 16kHz should become 4 samples at 8kHz
    import struct
    samples_16k = [100, 200, 300, 400, 500, 600, 700, 800]
    pcm_16k = struct.pack("<8h", *samples_16k)

    pcm_8k = resample_16k_to_8k(pcm_16k)
    assert len(pcm_8k) == 8  # 4 samples * 2 bytes = 8 bytes

    samples_8k = struct.unpack("<4h", pcm_8k)
    assert len(samples_8k) == 4

    # Upsample back to 16kHz
    pcm_16k_up = resample_8k_to_16k(pcm_8k)
    assert len(pcm_16k_up) == 16  # 8 samples * 2 bytes
