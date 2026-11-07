# Pico Call & Voice Agent: Native SIM Dialer & Device Call Manager

## Intent and the Why
Enable Pico to autonomously place and manage phone calls on behalf of the user using the user's Android phone SIM card. The user can simply instruct Pico in Telegram (e.g., *"pico call dad"* or *"pico call +919876543210"*). Pico verifies what to say and checks boundaries before placing the call, dials natively through the device SIM so the callee sees the user's authentic caller ID, conducts the conversation with a fast voice pipeline, streams a live summary card to Telegram during the call, halts and pings the user if an unbriefed question or decision arises, and delivers a final verified outcome and transcript.

## Goals, Non-Goals, and Anti-Goals

### Goals
- **Dual Callee Targeting:** Support both named contacts (e.g., `"dad"`, `"mom"`, `"reception"`) resolved via device contacts/memory, and explicit phone numbers (E.164 or local format).
- **Ask First Gate:** Prevent unauthorized dials by requiring a concise pre-call briefing (goal, message to deliver, authority envelope L0–L3, and red lines) with single-tap Telegram confirmation.
- **Native SIM Calling:** Trigger outbound phone calls via `termux-telephony-call`, ensuring the callee sees the user's real phone number without third-party cloud caller ID spoofing.
- **Cascaded Voice Pipeline:** Streamlined ASR (faster-whisper / phone audio) -> LLM Dialogue Planner (Groq Llama 3.1 8B Instant, target reply < 1s) -> TTS (Kokoro/Piper).
- **Anti-Double-Voice & Instant Interruption (Barge-in):** Millisecond voice activity detection (Silero VAD) with instant audio buffer flushing (<50ms cutoff) so Pico stops mid-syllable when the caller interrupts, paired with Acoustic Echo Cancellation (AEC) so Pico never hears or interrupts its own voice.
- **Live Summary Streaming:** Continuously update an in-flight Telegram status card with call state, callee responses, and conversational milestones.
- **Mid-Call Decision Bridge:** When the callee asks something unbriefed or presents a critical choice, the agent uses conversational hold/stall phrases (e.g., *"Just checking a quick note on that, give me a moment"*), pings the user in Telegram with high-priority one-tap buttons, and relays the user's decision back to the callee.
- **Commitment Checker:** Code-side strict validator that screens LLM proposed utterances against the agreed authority envelope before any binding commitment or private information is spoken.
- **Post-Call Verification & Transcript:** Store full audio/transcript, log outcome, and update user memory.

### Non-Goals
- Inbound call answering (calls are outbound-only in v1).
- Processing financial payments, credit card disclosures, or bank OTP relays over calls (strictly prohibited).
- Cold marketing, automated robocalling, or mass spam calls.
- Full duplex human voice cloning without explicit user model onboarding.

### Anti-Goals
- Never hallucinate commitments or agree to terms outside the user's pre-approved envelope.
- Never place a call silently without an explicit user Briefing Card confirmation.
- Never freeze or lock the Telegram bot while a call is active.

## Constraints
- **Android Audio Tapping:** Android OS security restricts non-system apps from directly tapping into raw in-call cellular audio streams without root or specific accessibility/telecom integrations. Approach 2 requires using Android speakerphone loopback or audio routing bridges with echo cancellation and robust VAD (Silero VAD) to avoid feedback loops.
- **Termux API Latency:** Calls to Termux API (`termux-telephony-call`, `termux-contact-list`) must run through non-blocking asynchronous runners with strict timeouts (e.g., `SafeCommandRunner`) to prevent UI lockup.
- **Network & Inference Speed:** Total conversational reply gap must stay <= ~1.2s to prevent unnatural conversational dropouts on cellular calls. Fast inference via Groq Llama 3.1 8B Instant is required.

## Approaches Considered

### Approach 1: Cloud Telephony Webhook Pipeline (Doc 34 Original)
- **Architecture:** Exotel/Twilio dials the callee; audio streams bi-directionally via WebSockets to a cloud or local server.
- **Trade-offs:** Crystal-clear digital audio with no acoustic feedback, but incurs per-minute voice fees and displays a virtual or rented caller ID rather than the user's personal SIM number.

### Approach 2: Native Android SIM Dialer with Device Audio (Selected)
- **Architecture:** Outbound call placed directly via `termux-telephony-call` on the user's device. Audio handled locally via speakerphone / hardware audio bridge.
- **Trade-offs:** ₹0 per-minute cost, authentic personal caller ID shown to family/contacts. Requires careful acoustic handling and VAD tuning.
- **Decision:** Selected by user (Ayush) to leverage local SIM calling pack and authentic caller ID.

## Detailed Architecture & Flow

### 1. Intent Capture & Callee Resolution
- User input: `"pico call dad"` or `"pico call +919876543210"`.
- If a name is supplied: Pico queries local contact cache / `termux-contact-list` (with timeout protection). If ambiguous (e.g. multiple numbers for "Dad"), Pico prompts the user to select the correct number.
- If a number is supplied: Validates format and country code (+91 default for India).

### 2. Stage A — Ask First Gate & Briefing Card
Pico responds in Telegram with a Briefing Card containing:
- **Callee:** Name & Number.
- **Objective:** What Pico needs to say or ask.
- **Authority Envelope:**
  - L0: Enquire only (ask questions, report back).
  - L1: Reserve / Hold (tentative, no money).
  - L2: Commit / Book (within strict bounds, e.g. dates, budget).
  - L3: Mid-Call Approval Only (requires real-time tap for every commitment).
- **Red Lines:** What Pico is strictly forbidden from disclosing or agreeing to.
- **Buttons:** `[Confirm & Call]` | `[Edit Details]` | `[Cancel]`.

### 3. Stage B — Native Dialing, Speech Loop & Interruption Engine
- Upon user tapping `Confirm & Call`, Pico launches the call via `termux-telephony-call`.
- Audio capture and playback initialize with Silero VAD and Acoustic Echo Cancellation (AEC):
  1. **Continuous VAD Listening:** While TTS audio plays out, a dedicated thread continuously monitors incoming 20ms audio frames.
  2. **Instant Interruption (Barge-in):** The moment human speech is detected (*"Stop stop wait"*), the playback thread receives a hard interrupt signal, immediately flushing the audio output buffer (<50ms cutoff) so Pico cuts off mid-syllable.
  3. **Thought Reset:** Any queued or unplayed TTS chunks are purged from memory, and the incoming speech is fed fresh into ASR.
  4. **Anti-Double-Voice:** Acoustic Echo Cancellation (or digital audio stream separation) subtracts Pico's own speaker output from the microphone feed so Pico never confuses its own voice for an interruption.
  5. **Fast Generation:** Groq Llama 3.1 8B Instant generates conversational replies under 400ms, screened by the code-side **Commitment Checker** before reaching TTS.

### 4. Stage C — Live Telegram Summary & Mid-Call Bridge
- **Live Summary Card:** Pico keeps a single editable Telegram message updated:
  ```
  📞 In Call with: Dad (+91 98xxx xxxxx)
  ⏱ Duration: 00:42 | Status: Connected
  
  📝 Live Summary:
  • Pico introduced call on Ayush's behalf.
  • Delivered message: Arriving home by 8:30 PM.
  • Dad answered: Dinner is ready, asked if you need anything from the market.
  ```
- **Mid-Call Info Bridge:** If Dad asks a question Pico cannot answer from the Facts Packet:
  - Agent immediately speaks a polite conversational stall: *"One second, let me check that note from Ayush."*
  - Telegram sends a high-priority Ping Card with a 30s countdown and quick reply buttons:
    `[Yes]` | `[No]` | `[Custom Text Reply]`
  - If user taps an option, agent resumes and speaks the answer.
  - If timeout expires, agent applies pre-agreed default (e.g., *"Ayush isn't able to confirm right now, he'll text you directly"*).

### 5. Stage D — Call Wrap-up & Proof
- Agent politely signs off and terminates the call session.
- Telegram message updates with final status: duration, key outcomes, action items, and full expandable transcript.

## What is Left to the Builder
- Audio bridge implementation strategy on Termux (testing speakerphone mic/speaker loopback vs USB/Bluetooth headset or audio routing daemon).
- Exact prompt engineering for Groq Llama 3.1 8B Instant for short, conversational telephony turns (<25 words per turn).
- Unit test suite for `CommitmentChecker`, `FactsPacket`, contact resolution, and simulated dialogue turn-taking.
- Simulator harness to run automated test calls without initiating real phone calls during development.
