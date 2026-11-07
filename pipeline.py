"""
The 7-Step Pipeline (v2) for Pico.
From YOUR_FRIEND_FULL_SETUP.pdf (§10 The Pipeline v2 — every run, every trigger).
"""

import uuid
import re
from datetime import datetime, timezone
from typing import Dict, Any, Optional, Tuple
from .models import (
    UserProfile,
    PersonaPacket,
    MemoryPack,
    Fact,
    FactStatus,
    FactSource,
    Sensitivity,
    PicoEmotion,
    EmotionSensitivity,
)
from .memory import MemoryStore
from .examiner import EmotionExaminer
from .guardrails import check_input_shield, validate_output_policy, format_safe_fallback, check_crisis_signals, get_crisis_response
from .prompt import render_system_prompt
from .router import LLMRouter
from .hermes_memory import HermesMemoryCoordinator
from .hermes_curator import HermesMemoryCurator
from .btw import BTWEngine


class PipelineEngine:
    def __init__(self, memory_store: MemoryStore, router: Optional[LLMRouter] = None):
        self.memory = memory_store
        self.examiner = EmotionExaminer()
        self.router = router or LLMRouter()
        self.hermes_memory = HermesMemoryCoordinator(memory_store)
        self.hermes_curator = HermesMemoryCurator(self.hermes_memory, memory_store)
        self.btw_engine = BTWEngine()
        self.run_history: list = []

    def run(
        self,
        user_message: str,
        profile: UserProfile,
        trigger: str = "user_chat",
        active_mode: Optional[str] = None,
        event_metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Executes the full 7-step pipeline on an incoming interaction.
        """
        run_id = str(uuid.uuid4())[:8]
        started_at = datetime.now(timezone.utc).isoformat()

        # =========================================================
        # STEP 0: ROUTE & PRIORITY + IMMEDIATE CRISIS CHECK (M1)
        # =========================================================
        priority = "P1" if trigger == "user_chat" else ("P0" if trigger == "alert" else "P2")

        if check_crisis_signals(user_message):
            crisis_resp = get_crisis_response(profile.name)
            self.memory.log_crisis_event(profile.user_id, run_id, "Crisis signals detected at Step 0")
            return {
                "run_id": run_id,
                "status": "crisis_override",
                "output": crisis_resp,
                "mode": "crisis",
                "emotion": PicoEmotion.WORRIED.value,
                "is_crisis": True,
                "tokens_estimated": len(crisis_resp.split()) + 50
            }

        # =========================================================
        # STEP 1: CHAT (receive & shield check)
        # =========================================================
        is_safe, shield_reason = check_input_shield(user_message)
        if not is_safe:
            return {
                "run_id": run_id,
                "status": "blocked",
                "output": "I noticed some funny instructions in that message, so I'm ignoring those and staying safe!",
                "mode": active_mode or "chill",
                "emotion": PicoEmotion.WORRIED.value
            }

        # Resolve live Mode: context -> topic -> user profile primary
        mode = active_mode or self._detect_topic_mode(user_message, profile)

        # =========================================================
        # STEP 2: THINK + STORE (Friend Test & Fact Extraction)
        # =========================================================
        # Check if user answered a pending BTW ask (Step 2 pre-check, §11 / M2)
        captured_fact = self.btw_engine.capture_answer(user_message, profile.user_id)
        if captured_fact:
            self.memory.store_fact(profile.user_id, captured_fact)

        extracted_facts = self._extract_facts(user_message, mode)
        for fact in extracted_facts:
            self.memory.store_fact(profile.user_id, fact)

        # =========================================================
        # STEP 3: CHECK MEMORY
        # =========================================================
        memory_pack = self.memory.build_memory_pack(profile, mode=mode)

        # =========================================================
        # STEP 4: RESEARCH GATE
        # =========================================================
        research_tier = self._classify_research_need(user_message)
        research_context = None

        # Automatic URL detection & web page reading via BrowserSkill
        url_match = re.search(r"https?://[^\s\"'>]+", user_message)
        if url_match:
            try:
                from .skills.browser_skill import BrowserSkill
                bskill = BrowserSkill()
                b_res = bskill.execute({"url": url_match.group(0), "max_length": 2500})
                if b_res.success:
                    research_context = (
                        f"[LIVE BROWSED WEB PAGE: {b_res.output.get('title') or b_res.output['host']} ({b_res.output['url']})]\n"
                        f"{b_res.output['text_content'][:2000]}"
                    )
            except Exception:
                pass

        # Check for stock / index queries (e.g. Nifty 50, Sensex)
        if any(w in user_message.lower() for w in ["nifty", "sensex"]):
            try:
                from .watchers import PriceWatcherEngine
                quote = PriceWatcherEngine.fetch_live_index_quote("NIFTY" if "nifty" in user_message.lower() else "SENSEX")
                if quote:
                    research_context = f"[REAL-TIME LIVE MARKET DATA]: {quote['summary_text']}"
            except Exception:
                pass

        # Check for device hardware / sensor queries
        if any(w in user_message.lower() for w in ["battery", "storage", "disk space", "ram", "specs", "device info", "how much memory", "free space", "phone info", "my device"]):
            try:
                from .skills.device_skill import DeviceSkill
                dskill = DeviceSkill()
                lower_msg = user_message.lower()
                if "battery" in lower_msg:
                    d_res = dskill.execute({"action": "battery"})
                elif any(w in lower_msg for w in ["storage", "disk", "free space"]):
                    d_res = dskill.execute({"action": "storage"})
                elif any(w in lower_msg for w in ["specs", "hardware", "ram", "cpu", "memory"]):
                    d_res = dskill.execute({"action": "specs"})
                else:
                    d_res = dskill.execute({"action": "status"})

                if d_res.success:
                    device_text = d_res.output.get("status_text") or d_res.output.get("summary_text")
                    d_context = f"[VERIFIED DEVICE HARDWARE CONTEXT]: {device_text}"
                    research_context = f"{research_context}\n{d_context}" if research_context else d_context
            except Exception:
                pass

        # Check for app launching intent
        app_match = re.search(r"\b(?:launch|open)\s+(spotify|youtube|tradingview|chrome|settings|calculator|clock)\b", user_message.lower())
        if app_match:
            try:
                from .skills.device_skill import DeviceSkill
                app_name = app_match.group(1).lower()
                dskill = DeviceSkill()
                d_res = dskill.execute({"action": "launch_app", "app_name": app_name})
                if d_res.success:
                    app_context = f"[DEVICE APP LAUNCH]: {d_res.output.get('status_text')}"
                    research_context = f"{research_context}\n{app_context}" if research_context else app_context
            except Exception:
                pass

        user_msg_lower = user_message.lower()

        # Check for Gmail query intent
        if any(kw in user_msg_lower for kw in ["check my email", "check email", "check gmail", "unread email", "any new email"]):
            try:
                from .gmail_watcher import GmailWatcher
                gw = GmailWatcher()
                if not gw.is_configured():
                    email_context = "[GMAIL CONTEXT]: Gmail is not yet configured. Set GMAIL_ADDRESS and GMAIL_APP_PASSWORD in .env."
                else:
                    emails = gw.fetch_recent_emails(limit=3)
                    if emails:
                        lines = [f"• From {em.sender}: '{em.subject}'" for em in emails]
                        email_context = f"[RECENT GMAIL INBOX HIGHLIGHTS]:\n" + "\n".join(lines)
                    else:
                        email_context = "[GMAIL CONTEXT]: No new unread emails found."
                research_context = f"{research_context}\n{email_context}" if research_context else email_context
            except Exception:
                pass

        # Check for Chrome tabs query intent
        if any(kw in user_msg_lower for kw in ["what tabs", "open tabs", "chrome tabs", "check tabs", "active tabs"]):
            try:
                from .chrome_watcher import ChromeWatcher
                cw = ChromeWatcher()
                summary = cw.get_browsing_summary()
                if summary["tab_count"] > 0:
                    domains = ", ".join(summary["top_domains"][:4])
                    tab_context = f"[ACTIVE CHROME TABS]: {summary['tab_count']} tabs open. Primary focus: {summary['primary_category']}. Top domains: {domains}."
                else:
                    tab_context = "[CHROME TABS]: No active open tabs recorded."
                research_context = f"{research_context}\n{tab_context}" if research_context else tab_context
            except Exception:
                pass

        if not research_context:
            search_intent = any(kw in user_msg_lower for kw in [
                "search up", "search for", "look up", "going for", "current price",
                "access browser", "nifty 50", "nifty50", "latest news"
            ])
            if search_intent:
                try:
                    from .skills.browser_skill import BrowserSkill
                    clean_q = user_message
                    for pfix in ["forget about that", "can you search up", "search up", "search for", "look up", "check if you can"]:
                        clean_q = re.sub(re.escape(pfix), "", clean_q, flags=re.IGNORECASE)
                    clean_q = clean_q.strip() or user_message
                    snippets = BrowserSkill.search_web(clean_q)
                    research_context = (
                        f"[LIVE BROWSER SEARCH FOR '{clean_q}']:\n" +
                        "\n".join([f"• {s}" for s in snippets])
                    )
                except Exception:
                    pass

        # Layer 2: SQLite FTS5 Cross-Session Recall
        past_matches = self.hermes_memory.search_cross_session(profile.user_id, user_message, limit=2)
        if past_matches:
            cross_bridge = self.hermes_memory.summarize_past_context(past_matches)
            if research_context and research_context != "Verified local context checked.":
                research_context = f"{cross_bridge}\n\n{research_context}"
            else:
                research_context = cross_bridge

        if not research_context:
            if research_tier == "LIGHT":
                research_context = "Verified local context checked."
            elif research_tier == "DEEP":
                research_context = "Sourced external data needed."

        # =========================================================
        # STEP 5: MAKE THE VERDICT / RESPONSE
        # =========================================================
        # 5c. Emotion Examiner runs (Exams 1, 2, 3)
        user_emotion = self.examiner.exam_1_user_emotion(user_message, profile)
        pico_emotion, reasons = self.examiner.exam_2_pico_emotion(
            user_emotion,
            profile,
            event=event_metadata
        )
        reaction_plan = self.examiner.exam_3_reaction_plan(user_emotion, pico_emotion, profile)

        # Assemble Persona Packet v3
        packet = PersonaPacket(
            mode=mode,
            emotion_assessment=user_emotion,
            his_emotion=pico_emotion,
            reasons=reasons,
            reaction_plan=reaction_plan,
            intensity_dial=float(user_emotion.intensity),
            memory_pack=memory_pack,
            research=research_context,
            missing=memory_pack.missing
        )

        # 5d. Render Master System Prompt
        system_prompt = render_system_prompt(
            profile=profile,
            packet=packet,
            is_p0_alert=(priority == "P0"),
            is_lock_in=(mode == "lock_in")
        )

        # Generate response via LLM Router
        raw_output = self.router.route_and_generate(
            system_prompt=system_prompt,
            user_message=user_message,
            packet=packet,
            profile=profile,
            step="step_5_verdict"
        )

        # 5e. Self-Check Gate
        is_valid, violations = validate_output_policy(raw_output, profile)
        final_output = raw_output if is_valid else format_safe_fallback(raw_output, violations)

        # 5f. The BTW Engine Slot (Contextual Ask Gate, §11 / M2)
        if priority != "P0":
            passed, gap = self.btw_engine.evaluate_ask_gate(
                packet=packet,
                current_topic=mode,
                value_delivered=True
            )
            if passed and gap:
                final_output = f"{final_output}\n\n{gap.question_template}"

        # =========================================================
        # STEP 6: LEARN & AUDIT LOG (with Hermes Reflection)
        # =========================================================
        curation = self.hermes_curator.reflect_and_curate(
            user_id=profile.user_id,
            prompt=user_message,
            agent_response=final_output,
            session_id=run_id
        )

        run_record = {
            "run_id": run_id,
            "timestamp": started_at,
            "trigger": trigger,
            "priority": priority,
            "mode": mode,
            "input": user_message,
            "output": final_output,
            "pico_emotion": pico_emotion.value,
            "user_emotion": user_emotion.primary,
            "facts_extracted": len(extracted_facts) + curation.get("facts_extracted", 0),
            "guardrail_violations": violations,
            "tokens_estimated": len(system_prompt.split()) + len(user_message.split()) + len(final_output.split())
        }
        self.run_history.append(run_record)

        return {
            "run_id": run_id,
            "status": "ok",
            "output": final_output,
            "mode": mode,
            "emotion": pico_emotion.value,
            "user_emotion": user_emotion.primary,
            "facts_saved": [f.key for f in extracted_facts],
            "memory_pack_size": len(memory_pack.committed_facts) + len(memory_pack.staging_facts),
            "pico_nudge": curation.get("nudge"),
            "dialectic_synthesis": curation.get("dialectic_synthesis")
        }

    def _detect_topic_mode(self, text: str, profile: UserProfile) -> str:
        """Determines active Mode from message topic (§10 Step 5a)."""
        lower = text.lower()
        if any(w in lower for w in ["gym", "workout", "squat", "bench", "deadlift", "reps", "exercise", "pushup"]):
            return "gym"
        if any(w in lower for w in ["btc", "crypto", "trading", "stocks", "nifty", "shares", "portfolio"]):
            return "trading"
        if any(w in lower for w in ["lock in", "deep work", "focus session"]):
            return "lock_in"
        if any(w in lower for w in ["cook", "meal", "recipe", "dinner", "lunch", "kitchen", "bake", "dal"]):
            return "cooking"
        if any(w in lower for w in ["game", "gaming", "ranked", "scrim", "aim", "valorant", "bgmi", "playstation"]):
            return "gaming"
        if any(w in lower for w in ["study", "exam", "syllabus", "pomodoro", "flashcards", "revision"]):
            return "study"
        if any(w in lower for w in ["video", "script", "shorts", "reels", "youtube", "editing", "hook"]):
            return "content_creation"
        if any(w in lower for w in ["guitar", "piano", "chords", "song", "bpm", "metronome", "instrument"]):
            return "music"
        if any(w in lower for w in ["startup", "landing page", "customer interview", "mvp", "founder", "pmf"]):
            return "startups"
        if any(w in lower for w in ["book", "reading", "chapter", "novel", "journal", "pages read"]):
            return "reading_writing"
        if any(w in lower for w in ["vocab", "vocabulary", "spanish", "french", "german", "language lesson"]):
            return "language_learning"
        if any(w in lower for w in ["travel", "trip", "packing", "flight", "itinerary", "hiking"]):
            return "travel"
        if any(w in lower for w in ["cricket", "football", "badminton", "tennis", "match score"]):
            return "sports"
        return profile.primary_hobby or "chill"

    def _extract_facts(self, text: str, mode: str) -> list[Fact]:
        """
        Step 2 Think+Store: Simple fact extraction with Friend Test filter.
        General personal facts go to 'shared' core; mode-specific facts go to that mode.
        """
        facts = []
        lower = text.lower()

        # General personal likes/facts belong to shared core memory
        fav_match = re.search(r"my favorite\s+([a-z0-9_\s]+?)\s+is\s+([a-z0-9_\s]+?)(?:\s+now|\.|$)", lower)
        if fav_match:
            category = fav_match.group(1).strip()
            item = fav_match.group(2).strip()
            facts.append(Fact(
                key=f"favorite_{category}",
                value=item,
                source=FactSource.USER_SAID,
                status=FactStatus.COMMITTED,
                mode="shared"
            ))

        # Check for hobby mentions (also shared profile knowledge)
        if "i started learning" in lower or "i love playing" in lower:
            match = re.search(r"(?:i started learning|i love playing)\s+([a-z0-9_\s]+)", lower)
            if match:
                hobby = match.group(1).strip()
                facts.append(Fact(
                    key=f"hobby_interest_{hobby}",
                    value=hobby,
                    source=FactSource.USER_SAID,
                    status=FactStatus.COMMITTED,
                    mode="shared"
                ))

        return facts

    def _classify_research_need(self, text: str) -> str:
        """Step 4 Research Gate: SKIP (~55%), LIGHT (~30%), DEEP (<=15%)."""
        lower = text.lower()
        if any(w in lower for w in ["research", "compare the market", "deep dive", "find sources for"]):
            return "DEEP"
        if any(w in lower for w in ["price of", "latest news", "what is"]):
            return "LIGHT"
        return "SKIP"
