"""
Asynchronous HTTP REST API Server for Pico.
Allows any frontend (mobile app, web UI, curl) to communicate with Pico.
"""

import os
import json
from typing import Optional
from aiohttp import web
from datetime import datetime, timezone
from .models import UserProfile
from .onboarding import OnboardingFlow
from .memory import MemoryStore
from .pipeline import PipelineEngine
from .routine import RoutineGraph
from .briefs import BriefGenerator
from .scheduled import ScheduledWorkRegistry
from .heartbeat import HeartbeatRunner
from .artifacts import ArtifactFactory
from .watchers import PriceWatcherEngine
from .tokens import TokenManager
from .reports import SelfAnalysisEngine, DailyScorecard
from .paths import get_default_db_path
from .chrome_watcher import ChromeWatcher
from .gmail_watcher import GmailWatcher, extract_events_from_message

STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
INDEX_HTML = os.path.join(STATIC_DIR, "index.html")


class PicoServer:
    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or get_default_db_path()
        self.memory = MemoryStore(self.db_path)
        self.pipeline = PipelineEngine(self.memory)
        self.watcher_engine = PriceWatcherEngine()
        self.token_manager = TokenManager()
        self.chrome_watcher = ChromeWatcher()
        self.gmail_watcher = GmailWatcher()

        # Seed default profile for user_001
        self.profile = OnboardingFlow.create_fast_path_profile(
            user_id="ayush_01",
            name="Ayush",
            nickname="Ayush",
            age=24,
            languages=["English", "Hinglish"],
            selected_categories=["Coding & Tech", "Gym & Fitness"],
            goal_90d="Ship the first live prototype of Pico with 10 testers"
        )

        self.routine = RoutineGraph.seed_from_profile(self.profile)
        self.scheduled = ScheduledWorkRegistry.install_defaults(self.profile)
        self.heartbeat = HeartbeatRunner(self.profile, self.routine, self.scheduled)

        self.app = web.Application()
        self._setup_routes()

    def _setup_routes(self):
        # Frontend UI & Static Assets
        if os.path.isdir(STATIC_DIR):
            self.app.router.add_static("/static", path=STATIC_DIR, name="static")
        self.app.router.add_get("/", self.handle_index)
        self.app.router.add_get("/ui", self.handle_index)

        self.app.router.add_get("/api/health", self.health_check)
        self.app.router.add_post("/api/chat", self.handle_chat)
        self.app.router.add_get("/api/what-i-know", self.handle_what_i_know)
        self.app.router.add_get("/api/path", self.handle_day_path)
        self.app.router.add_get("/api/brief", self.handle_brief)
        self.app.router.add_get("/api/review", self.handle_review)
        self.app.router.add_post("/api/heartbeat", self.handle_heartbeat)
        self.app.router.add_get("/api/artifacts/sip", self.handle_sip_artifact)
        self.app.router.add_get("/api/artifacts/goal", self.handle_goal_artifact)
        self.app.router.add_get("/api/tokens", self.handle_tokens)
        self.app.router.add_get("/api/scorecard", self.handle_scorecard)
        self.app.router.add_get("/api/telephony/twiml", self.handle_twiml)
        self.app.router.add_post("/api/telephony/twiml", self.handle_twiml)
        self.app.router.add_get("/api/telephony/media-stream", self.handle_media_stream)
        self.app.router.add_get("/api/events/gmail", self.handle_gmail_events)
        self.app.router.add_get("/api/events/chrome", self.handle_chrome_tabs)
        self.app.router.add_post("/api/events/chrome", self.handle_chrome_tab_post)
        self.app.router.add_get("/api/docs/{filename:.*}", self.handle_get_doc)

    async def handle_index(self, request):
        if os.path.isfile(INDEX_HTML):
            with open(INDEX_HTML, "r", encoding="utf-8") as f:
                content = f.read()
            return web.Response(
                text=content,
                content_type="text/html",
                headers={
                    "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
                    "Pragma": "no-cache",
                    "Expires": "0"
                }
            )
        return web.Response(text="<h1>Pico Companion UI not found</h1>", status=404, content_type="text/html")

    async def handle_get_doc(self, request):
        filename = request.match_info.get("filename", "")
        clean_path = os.path.normpath(filename).lstrip("/")
        if ".." in clean_path:
            return web.json_response({"error": "Forbidden path"}, status=403)
        base_dir = os.path.dirname(os.path.abspath(__file__))
        target_path = os.path.join(base_dir, clean_path)
        if not os.path.isfile(target_path) or not clean_path.endswith((".md", ".txt", ".json")):
            return web.json_response({"error": "File not found"}, status=404)
        with open(target_path, "r", encoding="utf-8") as f:
            content = f.read()
        return web.json_response({"filename": clean_path, "content": content})

    async def health_check(self, request):
        return web.json_response({
            "status": "healthy",
            "friend_name": "Pico",
            "version": "1.0.0",
            "time": datetime.now(timezone.utc).isoformat()
        })

    async def handle_chat(self, request):
        data = await request.json()
        message = data.get("message", "")
        mode = data.get("mode")

        result = self.pipeline.run(
            user_message=message,
            profile=self.profile,
            active_mode=mode
        )
        return web.json_response(result)

    async def handle_what_i_know(self, request):
        facts = self.memory.get_what_i_know(self.profile.user_id)
        return web.json_response({"facts": facts, "count": len(facts)})

    async def handle_day_path(self, request):
        path = self.routine.render_day_path()
        return web.json_response({"day_path": path})

    async def handle_brief(self, request):
        brief = BriefGenerator.generate_morning_brief(self.profile, self.routine)
        return web.json_response({"morning_brief": brief})

    async def handle_review(self, request):
        review = BriefGenerator.generate_evening_review(self.profile, streak_count=1)
        return web.json_response({"evening_review": review})

    async def handle_heartbeat(self, request):
        now_str = datetime.now().strftime("%H:%M")
        beat = self.heartbeat.fire_beat(now_str)
        return web.json_response({
            "beat_number": beat.beat_number,
            "outcome": beat.outcome.value,
            "reason": beat.reason,
            "was_quiet_hours": beat.was_quiet_hours
        })

    async def handle_sip_artifact(self, request):
        params = request.query
        amt = float(params.get("amt", 5000))
        cagr = float(params.get("cagr", 15))
        years = int(params.get("years", 26))
        art = ArtifactFactory.create_sip_calculator(self.profile.user_id, amt, cagr, years)
        return web.json_response({
            "id": art.id,
            "title": art.title,
            "primary": art.summary_header["metric_primary"],
            "secondary": art.summary_header["metric_secondary"],
            "his_line": art.his_line,
            "controls": art.controls
        })

    async def handle_goal_artifact(self, request):
        goal_text = self.profile.goal_90d or "Launch companion app"
        art = ArtifactFactory.create_goal_tracker(self.profile.user_id, goal_text)
        return web.json_response({
            "id": art.id,
            "title": art.title,
            "primary": art.summary_header["metric_primary"],
            "secondary": art.summary_header["metric_secondary"],
            "his_line": art.his_line
        })

    async def handle_tokens(self, request):
        acc = self.token_manager.get_or_create_account(self.profile.user_id)
        return web.json_response({
            "remaining": acc.tokens_remaining,
            "used": acc.tokens_used,
            "monthly_quota": acc.monthly_allowance,
            "is_low_power": acc.is_low_power,
            "lock_in_sessions_left": acc.lock_in_sessions_left
        })

    async def handle_scorecard(self, request):
        card = DailyScorecard(
            user_id=self.profile.user_id,
            date=datetime.now(timezone.utc).strftime("%Y-%m-%d")
        )
        report_md = SelfAnalysisEngine.generate_nightly_report(card, self.profile)
        return web.json_response({
            "total_score": card.total_score,
            "report_markdown": report_md
        })

    async def handle_twiml(self, request):
        host = request.headers.get("Host", "127.0.0.1:8000")
        proto = "wss" if request.secure else "ws"
        stream_url = f"{proto}://{host}/api/telephony/media-stream"
        from telephony.twilio_bridge import build_twiml_stream
        twiml = build_twiml_stream(stream_url)
        return web.Response(text=twiml, content_type="application/xml")

    async def handle_media_stream(self, request):
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        from telephony.call_session import CallSession
        from telephony.briefing import FactsPacket, CalleeInfo, AuthorityLevel
        from telephony.twilio_bridge import TwilioMediaStreamHandler

        packet = FactsPacket(
            callee=CalleeInfo(name="Callee", phone_number="unknown"),
            objective="Assisted call",
            authority=AuthorityLevel.L0
        )
        session = CallSession(packet=packet)
        handler = TwilioMediaStreamHandler(session=session, ws=ws)

        async for msg in ws:
            if msg.type == web.WSMsgType.TEXT:
                await handler.handle_message(msg.data)
            elif msg.type == web.WSMsgType.ERROR:
                break

        return ws

    async def handle_gmail_events(self, request):
        if not self.gmail_watcher.is_configured():
            return web.json_response({
                "configured": False,
                "message": "Gmail not configured. Set GMAIL_ADDRESS and GMAIL_APP_PASSWORD in .env"
            })

        emails = self.gmail_watcher.fetch_recent_emails(limit=5)
        all_events = []
        for em in emails:
            for ev in extract_events_from_message(em):
                all_events.append(ev.to_dict())

        return web.json_response({
            "configured": True,
            "count": len(emails),
            "events": all_events,
            "emails": [em.to_dict() for em in emails]
        })

    async def handle_chrome_tabs(self, request):
        summary = self.chrome_watcher.get_browsing_summary()
        return web.json_response(summary)

    async def handle_chrome_tab_post(self, request):
        try:
            data = await request.json()
        except Exception:
            return web.json_response({"error": "Invalid JSON"}, status=400)

        url = data.get("url", "")
        title = data.get("title", "")
        if not url:
            return web.json_response({"error": "URL required"}, status=400)

        tab = self.chrome_watcher.record_tab(url=url, title=title)
        self.chrome_watcher.sync_to_memory(self.memory, self.profile.user_id)
        return web.json_response({"success": True, "tab": tab.to_dict()})



def create_app():
    server = PicoServer()
    return server.app


if __name__ == "__main__":
    server = PicoServer()
    web.run_app(server.app, host="0.0.0.0", port=8000)
