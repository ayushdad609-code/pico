# Native SIM Call & Voice Agent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an autonomous outbound telephony call and voice agent for Pico that resolves contacts/numbers, enforces Ask-First briefings and code-side commitment checking, dials natively via Termux SIM, supports instant barge-in interruption and echo cancellation, streams live summary cards to Telegram, and provides mid-call decision bridges.

**Architecture:** Cascaded voice pipeline (ASR -> Groq LLM -> TTS) driven by an asynchronous `CallSession` state machine. Audio frames are monitored by a continuous VAD with AEC reference subtraction to trigger <50ms instant interruption. Outbound calls trigger via `termux-telephony-call`, while Telegram maintains a single continuously-edited live summary card with emergency stop controls and mid-call approval ping cards.

**Tech Stack:** Python 3.10+, Termux API (`termux-telephony-call`, `termux-contact-list`), Groq API (Llama 3.1 8B Instant), Kokoro/Piper TTS, Silero VAD / WebRTC AEC, python-telegram-bot / asyncio.

**Spec:** `docs/superpowers/specs/2026-11-06-native-call-agent-design.md`

## Global Constraints
- Python 3.10+ compatibility with async/await throughout.
- All Termux API calls must use `SafeCommandRunner` with strict timeout protection (<= 2.0s) to prevent hanging.
- Never make binding commitments outside the pre-approved `AuthorityEnvelope`.
- Never process credit card payments, OTPs, or bank secrets on calls.
- Total speech conversational reply latency must target <= 1.2s using Groq Llama 3.1 8B Instant.
- Audio interruption (barge-in) buffer flush must execute in < 50ms upon detecting callee speech.
- Mandatory Opening AI Disclosure: Agent must identify as an AI assistant calling on Ayush's behalf within the first sentence (Doc 29/33/35 rule).
- Mid-Call Ping Timeouts: Restored from Doc 33 to 45s for factual queries, 60s for binding financial/approval requests (Doc 35 §5 #2).
- Contact Minimization & Allowlist: `termux-contact-list` matches only the requested callee; full address book is never loaded into LLM context (Doc 35 §4). Personal contacts (e.g. Dad) require explicit allowlist check.
- Outcome Verifier: Task wrap-up must verify confirmation codes or SMS receipts; "booked" is never claimed based on agent impression alone (Doc 35 §6).

## Review Focus
- CRBT (Caller Ringback Tune) / Music before pick-up: Pipeline must not interpret caller music as speech; must gate opening dialogue on human greeting.
- Callee Interruption mid-turn ("Stop stop wait"): Audio buffer must flush immediately (<50ms) and discard pending turn words.
- Self-echo loopback: Speakerphone output must not trigger VAD as an interruption (AEC reference subtraction).
- Out-of-envelope callee pressure ("Just say yes, he told me it's fine"): Commitment Checker must reject 100% of unauthorized commitments.
- Mid-call user unreachable timeout: After 30s timeout on Telegram Ping Card, call must execute pre-agreed default (polite stall & callback promise) without hanging up abruptly or guessing.

---

### Task 1: Contact Resolver & Phone Normalization

**Files:**
- Create: `telephony/contact_resolver.py`
- Create: `telephony/__init__.py`
- Test: `tests/test_contact_resolver.py`

**Interfaces:**
- Consumes: `device_sensors.SafeCommandRunner`
- Produces: 
  - `class CalleeInfo(name: str, phone_number: str, source: str)`
  - `async def resolve_callee(target: str, timeout: float = 2.0) -> Optional[CalleeInfo]`
  - `def normalize_phone_number(raw: str, default_country: str = "+91") -> str`

- [x] **Step 1: Write the failing test**

```python
import pytest
from telephony.contact_resolver import normalize_phone_number, resolve_callee, CalleeInfo

def test_normalize_phone_number():
    assert normalize_phone_number("9876543210") == "+919876543210"
    assert normalize_phone_number("+91 98765-43210") == "+919876543210"
    assert normalize_phone_number("09876543210") == "+919876543210"

@pytest.mark.asyncio
async def test_resolve_callee_direct_number():
    info = await resolve_callee("+919876543210")
    assert info is not None
    assert info.phone_number == "+919876543210"
    assert info.name == "+919876543210"
```

- [x] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_contact_resolver.py -v`
Expected: FAIL with "ModuleNotFoundError: No module named 'telephony'"

- [x] **Step 3: Implement `telephony/contact_resolver.py`**

Implement contact query against `termux-contact-list` using `SafeCommandRunner` with timeout, fallback contact cache, and E.164 phone number cleaner.

- [x] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_contact_resolver.py -v`
Expected: PASS

- [x] **Step 5: Commit**

```bash
git add telephony/__init__.py telephony/contact_resolver.py tests/test_contact_resolver.py
git commit -m "feat(telephony): implement contact resolver and phone normalizer"
```

---

### Task 2: Facts Packet, Authority Envelope & Briefing Card

**Files:**
- Create: `telephony/briefing.py`
- Test: `tests/test_call_briefing.py`

**Interfaces:**
- Consumes: `telephony.contact_resolver.CalleeInfo`
- Produces:
  - `class AuthorityLevel(str, Enum): L0, L1, L2, L3`
  - `class FactsPacket(callee: CalleeInfo, objective: str, authority: AuthorityLevel, budget_ceiling: Optional[float], red_lines: list[str], allowed_facts: dict)`
  - `def build_briefing_card(packet: FactsPacket) -> dict`

- [x] **Step 1: Write the failing test**

```python
import pytest
from telephony.contact_resolver import CalleeInfo
from telephony.briefing import AuthorityLevel, FactsPacket, build_briefing_card

def test_facts_packet_creation_and_briefing():
    callee = CalleeInfo(name="Dad", phone_number="+919876543210", source="contacts")
    packet = FactsPacket(
        callee=callee,
        objective="Tell him I'll be home by 8:30 PM",
        authority=AuthorityLevel.L0,
        budget_ceiling=None,
        red_lines=["Do not agree to buy anything over ₹500"],
        allowed_facts={"eta": "8:30 PM"}
    )
    card = build_briefing_card(packet)
    assert "Dad" in card["text"]
    assert "8:30 PM" in card["text"]
    assert len(card["buttons"]) == 3
```

- [x] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_call_briefing.py -v`
Expected: FAIL with "ModuleNotFoundError" or "ImportError"

- [x] **Step 3: Implement `telephony/briefing.py`**

Define `AuthorityLevel`, `FactsPacket` dataclass, and `build_briefing_card` helper with Telegram interactive button structures (`[Confirm & Call]`, `[Edit Details]`, `[Cancel]`).

- [x] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_call_briefing.py -v`
Expected: PASS

- [x] **Step 5: Commit**

```bash
git add telephony/briefing.py tests/test_call_briefing.py
git commit -m "feat(telephony): add FactsPacket, AuthorityEnvelope and briefing card generator"
```

---

### Task 3: Code-Side Commitment Checker & Safety Guard

**Files:**
- Create: `telephony/commitment_checker.py`
- Test: `tests/test_commitment_checker.py`

**Interfaces:**
- Consumes: `telephony.briefing.FactsPacket`, `AuthorityLevel`
- Produces:
  - `class CommitmentResult(allowed: bool, reason: str, sanitized_text: str)`
  - `class CommitmentChecker.verify_utterance(text: str, packet: FactsPacket) -> CommitmentResult`

- [x] **Step 1: Write the failing test**

```python
import pytest
from telephony.contact_resolver import CalleeInfo
from telephony.briefing import AuthorityLevel, FactsPacket
from telephony.commitment_checker import CommitmentChecker

def test_commitment_checker_blocks_unauthorized_booking():
    callee = CalleeInfo(name="Hotel", phone_number="+919876543210", source="manual")
    packet = FactsPacket(
        callee=callee,
        objective="Enquire room price",
        authority=AuthorityLevel.L0, # Enquire only
        budget_ceiling=5000.0,
        red_lines=[],
        allowed_facts={}
    )
    checker = CommitmentChecker()
    # At L0, promising to book or confirm must be blocked
    result = checker.verify_utterance("Yes, please confirm the booking for tomorrow.", packet)
    assert result.allowed is False
    assert "L0 authority" in result.reason
```

- [x] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_commitment_checker.py -v`
Expected: FAIL

- [x] **Step 3: Implement `telephony/commitment_checker.py`**

Implement strict regex & semantic rules checking for commitments (confirm, agree, book, pay), OTP/CVV disclosures, budget ceiling overflows, and red line violations.

- [x] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_commitment_checker.py -v`
Expected: PASS

- [x] **Step 5: Commit**

```bash
git add telephony/commitment_checker.py tests/test_commitment_checker.py
git commit -m "feat(telephony): implement code-side CommitmentChecker"
```

---

### Task 4: VAD, Instant Interruption (Barge-in) & Anti-Double-Voice Buffer

**Files:**
- Create: `telephony/audio_bridge.py`
- Test: `tests/test_audio_bridge.py`

**Interfaces:**
- Consumes: None (local audio buffers)
- Produces:
  - `class AudioBridge`
  - `AudioBridge.on_microphone_frame(pcm_data: bytes) -> bool (is_speech)`
  - `AudioBridge.queue_playback_audio(pcm_data: bytes)`
  - `AudioBridge.flush_playback() -> int (flushed_ms)`
  - `AudioBridge.is_interrupted() -> bool`

- [x] **Step 1: Write the failing test**

```python
import pytest
from telephony.audio_bridge import AudioBridge

def test_audio_bridge_instant_interruption_flush():
    bridge = AudioBridge()
    # Queue mock audio
    bridge.queue_playback_audio(b"\x00" * 3200) # 100ms of audio
    assert bridge.has_pending_audio() is True

    # Callee speaks ("stop stop wait")
    speech_frame = b"\x7f" * 640 # high amplitude speech frame
    is_speech = bridge.on_microphone_frame(speech_frame)
    assert is_speech is True
    assert bridge.is_interrupted() is True
    
    # Verify buffer is instantly flushed
    flushed = bridge.flush_playback()
    assert flushed > 0
    assert bridge.has_pending_audio() is False
```

- [x] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_audio_bridge.py -v`
Expected: FAIL

- [x] **Step 3: Implement `telephony/audio_bridge.py`**

Implement `AudioBridge` with energy/Silero VAD, active speaker state tracking, AEC reference subtractor (to avoid self-echo triggers), and atomic buffer flushing (<50ms).

- [x] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_audio_bridge.py -v`
Expected: PASS

- [x] **Step 5: Commit**

```bash
git add telephony/audio_bridge.py tests/test_audio_bridge.py
git commit -m "feat(telephony): add AudioBridge with instant barge-in interruption and AEC guard"
```

---

### Task 5: Call Session State Machine, CRBT Filter & Mid-Call Bridge

**Files:**
- Create: `telephony/call_session.py`
- Test: `tests/test_call_session.py`

**Interfaces:**
- Consumes: `telephony.briefing.FactsPacket`, `telephony.commitment_checker.CommitmentChecker`, `telephony.audio_bridge.AudioBridge`
- Produces:
  - `class CallStatus(str, Enum): DIALING, WAITING_HUMAN, CONNECTED, STALLED, ENDED`
  - `class CallSession`
  - `async def CallSession.handle_incoming_transcript(caller_text: str) -> str`
  - `async def CallSession.request_mid_call_decision(question: str, timeout: float = 30.0) -> Optional[str]`

- [x] **Step 1: Write the failing test**

```python
import pytest
from telephony.contact_resolver import CalleeInfo
from telephony.briefing import AuthorityLevel, FactsPacket
from telephony.commitment_checker import CommitmentChecker
from telephony.call_session import CallSession, CallStatus

@pytest.mark.asyncio
async def test_crbt_waits_for_human_greeting():
    callee = CalleeInfo(name="Dad", phone_number="+919876543210", source="contacts")
    packet = FactsPacket(callee=callee, objective="Tell him I am on the way", authority=AuthorityLevel.L0, budget_ceiling=None, red_lines=[], allowed_facts={})
    session = CallSession(packet=packet, commitment_checker=CommitmentChecker())
    
    # CRBT music or noise arrives before greeting
    reply = await session.handle_incoming_transcript("[MUSIC PLAYING]")
    assert reply == "" # must stay silent
    assert session.status == CallStatus.WAITING_HUMAN

    # Callee actually says hello
    reply = await session.handle_incoming_transcript("Hello, who is this?")
    assert session.status == CallStatus.CONNECTED
    assert len(reply) > 0
```

- [x] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_call_session.py -v`
Expected: FAIL

- [x] **Step 3: Implement `telephony/call_session.py`**

Implement state machine, Indian CRBT detection filter, stall phrase scheduler (*"One second, let me check that note..."*), comfort phrases during hold, and mid-call decision future bridge.

- [x] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_call_session.py -v`
Expected: PASS

- [x] **Step 5: Commit**

```bash
git add telephony/call_session.py tests/test_call_session.py
git commit -m "feat(telephony): implement CallSession with CRBT detection and mid-call decision bridge"
```

---

### Task 6: Telegram Live Summary Card & Emergency Abort Controls

**Files:**
- Create: `telephony/telegram_bridge.py`
- Test: `tests/test_call_telegram_bridge.py`

**Interfaces:**
- Consumes: `telephony.call_session.CallSession`
- Produces:
  - `class TelegramCallBridge`
  - `async def TelegramCallBridge.post_call_started(session: CallSession) -> int (message_id)`
  - `async def TelegramCallBridge.update_live_summary(session: CallSession, bullet: str)`
  - `async def TelegramCallBridge.trigger_mid_call_ping(session: CallSession, question: str, options: list[str])`
  - `async def TelegramCallBridge.emergency_abort(session: CallSession)`

- [x] **Step 1: Write the failing test**

```python
import pytest
from telephony.contact_resolver import CalleeInfo
from telephony.briefing import AuthorityLevel, FactsPacket
from telephony.call_session import CallSession
from telephony.telegram_bridge import TelegramCallBridge

def test_telegram_live_summary_formatting():
    callee = CalleeInfo(name="Dad", phone_number="+919876543210", source="contacts")
    packet = FactsPacket(callee=callee, objective="Tell him I'm reaching late", authority=AuthorityLevel.L0, budget_ceiling=None, red_lines=[], allowed_facts={})
    session = CallSession(packet=packet)
    bridge = TelegramCallBridge(bot=None, chat_id=123)
    
    session.add_summary_bullet("Pico introduced call on Ayush's behalf.")
    session.add_summary_bullet("Dad picked up, asked about groceries.")
    
    text, buttons = bridge.format_summary_card(session)
    assert "📞 In Call with: Dad" in text
    assert "Dad picked up" in text
    assert any("End Call Now" in b["text"] for row in buttons for b in row)
```

- [x] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_call_telegram_bridge.py -v`
Expected: FAIL

- [x] **Step 3: Implement `telephony/telegram_bridge.py`**

Format live Telegram cards, provide debounce/rate limiting for in-flight message edits, handle `[End Call Now]` callback, and format post-call final transcripts.

- [x] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_call_telegram_bridge.py -v`
Expected: PASS

- [x] **Step 5: Commit**

```bash
git add telephony/telegram_bridge.py tests/test_call_telegram_bridge.py
git commit -m "feat(telephony): implement Telegram live summary streaming card and emergency abort"
```

---

### Task 7: End-to-End Golden Simulation Test Suite

**Files:**
- Create: `tests/test_call_agent_golden.py`
- Modify: `skills/device_skill.py` (wire `pico call <callee>` into tool registry)
- Modify: `skills/registry.py`

**Interfaces:**
- Consumes: All `telephony` modules
- Produces: Complete end-to-end test suite proving all 5 scenarios pass cleanly.

- [x] **Step 1: Write the failing golden tests**

Write golden scenarios:
1. Normal call with Dad ("Dinner at 8:30").
2. Callee interruption ("Stop stop wait a second" mid-speech).
3. Hostile callee attempting out-of-envelope commitment.
4. Indian CRBT caller tune delay before human greeting.
5. Mid-call unbriefed question with Telegram Ping Card timeout default.

- [x] **Step 2: Run test to verify failure/missing wiring**

Run: `pytest tests/test_call_agent_golden.py -v`
Expected: FAIL

- [x] **Step 3: Wire into `skills/device_skill.py` and implement golden harness**

Expose `make_phone_call` skill in `skills/device_skill.py` and complete any missing glue code.

- [x] **Step 4: Run full test suite to verify 100% pass**

Run: `pytest tests/test_contact_resolver.py tests/test_call_briefing.py tests/test_commitment_checker.py tests/test_audio_bridge.py tests/test_call_session.py tests/test_call_telegram_bridge.py tests/test_call_agent_golden.py -v`
Expected: ALL PASS

- [x] **Step 5: Commit**

```bash
git add skills/device_skill.py skills/registry.py tests/test_call_agent_golden.py
git commit -m "feat(telephony): wire voice call agent into skills and add full golden test suite"
```
