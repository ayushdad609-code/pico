"""
Asynchronous HTTP REST API Server for Pico.
Allows any frontend (mobile app, web UI, curl) to communicate with Pico.
"""

import json
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


class PicoServer:
    def __init__(self, db_path: str = "/data/data/com.termux/files/home/pico/pico_chat.db"):
        self.db_path = db_path
        self.memory = MemoryStore(db_path)
        self.pipeline = PipelineEngine(self.memory)
        self.watcher_engine = PriceWatcherEngine()
        self.token_manager = TokenManager()

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


def create_app():
    server = PicoServer()
    return server.app


if __name__ == "__main__":
    server = PicoServer()
    web.run_app(server.app, host="127.0.0.1", port=8000)
