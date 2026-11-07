"""
Pure-Python G.711 mu-law (PCMU) Encoder, Decoder and Resampler.
Standard ITU-T G.711 implementation compatible with Python 3.10 through 3.14+
without audioop or external C dependencies.
Designed for Twilio / Exotel 8kHz telephony media streams.
"""

import struct

BIAS = 0x84  # 132
CLIP = 32635
_SEG_END = [0x3F, 0x7F, 0xFF, 0x1FF, 0x3FF, 0x7FF, 0xFFF, 0x1FFF]


def _search(val: int) -> int:
    for i, b in enumerate(_SEG_END):
        if val <= b:
            return i
    return len(_SEG_END)


def linear2ulaw(pcm_val: int) -> int:
    """Encode a single 16-bit signed linear PCM value to an 8-bit mu-law sample."""
    if pcm_val < 0:
        pcm_val = -pcm_val
        mask = 0x7F
    else:
        mask = 0xFF

    if pcm_val > CLIP:
        pcm_val = CLIP

    pcm_val += BIAS
    seg = _search(pcm_val >> 2)
    if seg >= 8:
        return 0x7F ^ mask

    uval = (seg << 4) | ((pcm_val >> (seg + 3)) & 0x0F)
    return uval ^ mask


def ulaw2linear(u_val: int) -> int:
    """Decode a single 8-bit mu-law sample to a 16-bit signed linear PCM value."""
    u = ~u_val & 0xFF
    t = ((u & 0x0F) << 3) + BIAS
    t <<= (u & 0x70) >> 4
    return (BIAS - t) if (u & 0x80) else (t - BIAS)


# Precompute 256-entry lookup table for ultra-fast decoding
_ULAW_TO_LINEAR_TABLE = [ulaw2linear(i) for i in range(256)]


def pcm16_to_mulaw(pcm_data: bytes) -> bytes:
    """Convert 16-bit signed little-endian linear PCM byte buffer to G.711 mu-law bytes."""
    sample_count = len(pcm_data) // 2
    if sample_count == 0:
        return b""
    samples = struct.unpack(f"<{sample_count}h", pcm_data[:sample_count * 2])
    return bytes(linear2ulaw(s) for s in samples)


def mulaw_to_pcm16(mulaw_data: bytes) -> bytes:
    """Convert G.711 mu-law bytes to 16-bit signed little-endian linear PCM byte buffer."""
    if not mulaw_data:
        return b""
    samples = [_ULAW_TO_LINEAR_TABLE[b] for b in mulaw_data]
    return struct.pack(f"<{len(samples)}h", *samples)


def resample_16k_to_8k(pcm_16k_data: bytes) -> bytes:
    """2:1 decimation downsampling from 16kHz 16-bit PCM to 8kHz 16-bit PCM."""
    sample_count = len(pcm_16k_data) // 2
    if sample_count < 2:
        return b""
    samples = struct.unpack(f"<{sample_count}h", pcm_16k_data[:sample_count * 2])
    downsampled = samples[0::2]
    return struct.pack(f"<{len(downsampled)}h", *downsampled)


def resample_8k_to_16k(pcm_8k_data: bytes) -> bytes:
    """Linear interpolation upsampling from 8kHz 16-bit PCM to 16kHz 16-bit PCM."""
    sample_count = len(pcm_8k_data) // 2
    if sample_count == 0:
        return b""
    samples = struct.unpack(f"<{sample_count}h", pcm_8k_data[:sample_count * 2])
    upsampled = []
    for i in range(len(samples)):
        s1 = samples[i]
        upsampled.append(s1)
        if i + 1 < len(samples):
            s2 = samples[i + 1]
            interp = (s1 + s2) // 2
            upsampled.append(interp)
        else:
            upsampled.append(s1)
    return struct.pack(f"<{len(upsampled)}h", *upsampled)
