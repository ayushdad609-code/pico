"""
Twilio WebSocket Media Stream Bridge for Pico Telephony.
Handles real-time bidirectional audio streaming, instant barge-in cut-off,
and call lifecycle over Twilio Voice WebSockets (Doc 34 §3 & Doc 35 §2).
"""

import os
import json
import base64
import logging
import aiohttp
from typing import Optional, Dict, Any

from telephony.mulaw import (
    mulaw_to_pcm16,
    pcm16_to_mulaw,
    resample_8k_to_16k,
    resample_16k_to_8k
)
from telephony.call_session import CallSession, CallStatus

logger = logging.getLogger(__name__)


def build_twiml_stream(stream_url: str, custom_params: Optional[Dict[str, str]] = None) -> str:
    """Generate TwiML connecting an active call to a bidirectional WebSocket Media Stream."""
    params_xml = ""
    if custom_params:
        for k, v in custom_params.items():
            params_xml += f'        <Parameter name="{k}" value="{v}"/>\n'

    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<Response>\n'
        '    <Connect>\n'
        f'        <Stream url="{stream_url}">\n'
        f'{params_xml}'
        '        </Stream>\n'
        '    </Connect>\n'
        '</Response>'
    )


class TwilioCallManager:
    """Manages Twilio REST API interactions for creating and terminating outbound calls."""

    def __init__(
        self,
        account_sid: Optional[str] = None,
        auth_token: Optional[str] = None,
        from_number: Optional[str] = None
    ):
        self.account_sid = account_sid or os.getenv("TWILIO_ACCOUNT_SID", "")
        self.auth_token = auth_token or os.getenv("TWILIO_AUTH_TOKEN", "")
        self.from_number = from_number or os.getenv("TWILIO_FROM_NUMBER", "")
        self.base_url = f"https://api.twilio.com/2010-04-01/Accounts/{self.account_sid}"

    def _get_auth_headers(self) -> Dict[str, str]:
        creds = f"{self.account_sid}:{self.auth_token}"
        encoded = base64.b64encode(creds.encode("utf-8")).decode("utf-8")
        return {"Authorization": f"Basic {encoded}"}

    async def initiate_call(
        self,
        to_number: str,
        twiml_url: str,
        from_number: Optional[str] = None
    ) -> Dict[str, Any]:
        """Trigger an outbound call through Twilio pointing to the TwiML webhook URL."""
        if not self.account_sid or not self.auth_token:
            raise ValueError("TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN must be configured.")

        caller_id = from_number or self.from_number
        if not caller_id:
            raise ValueError("TWILIO_FROM_NUMBER caller ID must be specified.")

        url = f"{self.base_url}/Calls.json"
        data = {
            "To": to_number,
            "From": caller_id,
            "Url": twiml_url,
            "Record": "false"
        }

        headers = self._get_auth_headers()
        async with aiohttp.ClientSession(headers=headers) as session:
            async with session.post(url, data=data) as resp:
                resp_json = await resp.json()
                if resp.status not in (200, 201):
                    err_msg = resp_json.get("message", f"HTTP {resp.status}")
                    raise RuntimeError(f"Twilio call failed: {err_msg}")
                return resp_json

    async def end_call(self, call_sid: str) -> bool:
        """Terminate an active call."""
        if not self.account_sid or not self.auth_token:
            return False

        url = f"{self.base_url}/Calls/{call_sid}.json"
        data = {"Status": "completed"}
        headers = self._get_auth_headers()
        async with aiohttp.ClientSession(headers=headers) as session:
            async with session.post(url, data=data) as resp:
                return resp.status in (200, 204)


class TwilioMediaStreamHandler:
    """
    Handles a single bidirectional WebSocket connection from Twilio.
    - Decodes incoming 8kHz mu-law audio -> 16kHz linear PCM for VAD & Whisper ASR.
    - Encodes outgoing 16kHz linear PCM -> 8kHz mu-law for Twilio playback.
    - Enforces <50ms instant barge-in cut-off by sending Twilio 'clear' event.
    """

    def __init__(self, session: CallSession, ws: Any):
        self.session = session
        self.ws = ws
        self.stream_sid: Optional[str] = None
        self.call_sid: Optional[str] = None
        self._closed: bool = False

    async def handle_message(self, raw_msg: str) -> None:
        """Process an incoming JSON message from Twilio Media Stream WebSocket."""
        try:
            data = json.loads(raw_msg)
        except Exception as e:
            logger.warning(f"Failed to parse Twilio WS message: {e}")
            return

        event = data.get("event")

        if event == "connected":
            logger.info("Twilio MediaStream connected.")

        elif event == "start":
            start_data = data.get("start", {})
            self.stream_sid = data.get("streamSid") or start_data.get("streamSid")
            self.call_sid = start_data.get("callSid")
            logger.info(f"Twilio MediaStream started: streamSid={self.stream_sid}, callSid={self.call_sid}")

        elif event == "media":
            payload_b64 = data.get("media", {}).get("payload", "")
            if not payload_b64:
                return

            try:
                mulaw_bytes = base64.b64decode(payload_b64)
            except Exception:
                return

            # Convert 8kHz mu-law to 16kHz 16-bit PCM for VAD & ASR
            pcm_8k = mulaw_to_pcm16(mulaw_bytes)
            pcm_16k = resample_8k_to_16k(pcm_8k)

            # Process microphone frame into AudioBridge
            # If callee spoke while Pico was playing audio, AudioBridge triggers barge-in!
            self.session.audio_bridge.on_microphone_frame(pcm_16k)

            # If interrupted, immediately send "clear" event to Twilio to stop playback in <50ms!
            if self.session.audio_bridge.is_interrupted() and self.stream_sid:
                await self.send_clear()

        elif event == "stop":
            logger.info("Twilio MediaStream stopped.")
            self.session.status = CallStatus.ENDED
            self._closed = True

    async def send_audio(self, pcm_16k_data: bytes) -> None:
        """Downsample 16kHz PCM audio to 8kHz mu-law and send to Twilio callee."""
        if not self.stream_sid or self._closed:
            return

        pcm_8k = resample_16k_to_8k(pcm_16k_data)
        mulaw_bytes = pcm16_to_mulaw(pcm_8k)
        payload_b64 = base64.b64encode(mulaw_bytes).decode("utf-8")

        msg = {
            "event": "media",
            "streamSid": self.stream_sid,
            "media": {
                "payload": payload_b64
            }
        }
        await self.ws.send_str(json.dumps(msg))

    async def send_clear(self) -> None:
        """Immediately clear Twilio playback buffer (<50ms cutoff) upon interruption."""
        if not self.stream_sid or self._closed:
            return

        msg = {
            "event": "clear",
            "streamSid": self.stream_sid
        }
        await self.ws.send_str(json.dumps(msg))
