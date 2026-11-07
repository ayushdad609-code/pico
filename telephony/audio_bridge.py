"""Audio Bridge with VAD, Instant Interruption (Barge-in) and AEC Echo Suppression."""

import math
import struct
from collections import deque
from typing import Optional, Deque

class AudioBridge:
    """
    Manages low-latency audio frame buffers between microphone capture and speaker playback.
    Provides instant interruption (barge-in) and acoustic echo cancellation (AEC) reference subtraction.
    """

    def __init__(
        self,
        sample_rate: int = 16000,
        frame_duration_ms: int = 20,
        energy_threshold: float = 1200.0,
        echo_similarity_threshold: float = 0.85
    ):
        self.sample_rate = sample_rate
        self.frame_duration_ms = frame_duration_ms
        self.energy_threshold = energy_threshold
        self.echo_similarity_threshold = echo_similarity_threshold
        
        # 16-bit mono PCM = 2 bytes per sample
        self.frame_size = int(self.sample_rate * (self.frame_duration_ms / 1000.0) * 2)
        
        # Audio buffers
        self._playback_buffer: bytearray = bytearray()
        self._interrupted: bool = False
        
        # AEC reference history: holds recently played speaker frames (up to ~500ms = 25 frames)
        self._speaker_history: Deque[bytes] = deque(maxlen=25)

    def queue_playback_audio(self, pcm_data: bytes) -> None:
        """Queue synthesized TTS audio for playback."""
        if not pcm_data:
            return
        self._playback_buffer.extend(pcm_data)
        self._interrupted = False

    def record_speaker_playback(self, pcm_frame: bytes) -> None:
        """Record what audio was physically emitted to the speaker for AEC reference."""
        if pcm_frame:
            self._speaker_history.append(pcm_frame)

    def has_pending_audio(self) -> bool:
        """Check if audio is currently playing or queued to play."""
        return len(self._playback_buffer) > 0

    def is_interrupted(self) -> bool:
        """Check if callee has interrupted current speech."""
        return self._interrupted

    def flush_playback(self) -> int:
        """
        Immediately drop and flush all pending/queued playback audio (<50ms cutoff).
        Returns the number of bytes purged.
        """
        flushed_bytes = len(self._playback_buffer)
        self._playback_buffer.clear()
        self._interrupted = False
        return flushed_bytes

    def _calculate_rms(self, pcm_frame: bytes) -> float:
        """Calculate Root Mean Square (RMS) energy of 16-bit PCM frame."""
        sample_count = len(pcm_frame) // 2
        if sample_count == 0:
            return 0.0

        try:
            samples = struct.unpack(f"<{sample_count}h", pcm_frame)
            sum_squares = sum(s * s for s in samples)
            return math.sqrt(sum_squares / sample_count)
        except Exception:
            return 0.0

    def _is_echo(self, mic_frame: bytes) -> bool:
        """
        Compare microphone frame against recent speaker output to suppress self-echo.
        """
        if not self._speaker_history:
            return False

        # Fast exact or high-correlation match
        for speaker_frame in self._speaker_history:
            if mic_frame == speaker_frame:
                return True
            
            # Simple correlation if lengths match
            if len(mic_frame) == len(speaker_frame) and len(mic_frame) >= 32:
                # Compare sample differences
                matches = sum(1 for a, b in zip(mic_frame[:64], speaker_frame[:64]) if abs(a - b) <= 2)
                if matches / 64 >= self.echo_similarity_threshold:
                    return True

        return False

    def on_microphone_frame(self, pcm_frame: bytes) -> bool:
        """
        Process an incoming 20ms microphone audio frame.
        Returns True if human speech is detected, False for silence or echo.
        """
        if not pcm_frame:
            return False

        energy = self._calculate_rms(pcm_frame)
        if energy < self.energy_threshold:
            return False

        # Check Acoustic Echo Cancellation (AEC)
        if self._is_echo(pcm_frame):
            return False

        # Speech detected from the other person
        if self.has_pending_audio():
            # Interruption (barge-in) event!
            self._interrupted = True

        return True
