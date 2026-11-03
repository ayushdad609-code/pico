"""
Interactive CLI for Pico - Your Friend.
Allows testing onboarding, talking to Chill Pico, inspecting memory and emotions.
"""

import sys
from .models import UserProfile, Fact, FactStatus, FactSource
from .memory import MemoryStore
from .pipeline import PipelineEngine
from .onboarding import OnboardingFlow, LAUNCH_CATEGORIES


def run_interactive_cli():
    print("=" * 65)
    print("   🌟 WELCOME TO PICO (YOUR FRIEND) — FAST PATH ONBOARDING 🌟")
    print("=" * 65)
    print("Pico is getting his notebook and pencil ready...\n")

    # Fast Path Onboarding (5 steps)
    name = input("Page 1 & 2: What is your name? [Ayush]: ").strip() or "Ayush"
    nickname = input(f"Do you have a nickname for Pico to call you? [{name}]: ").strip() or name

    age_input = input("Page 3: What is your age? [24]: ").strip() or "24"
    try:
        age = int(age_input)
    except ValueError:
        age = 24

    print("\nPage 4: Languages you speak (e.g., English, Hindi, Hinglish)")
    langs_input = input("Enter languages separated by commas [English, Hinglish]: ").strip() or "English, Hinglish"
    languages = [l.strip() for l in langs_input.split(",")]

    print("\nPage 5: What relates with you? (Top categories):")
    for idx, cat in enumerate(LAUNCH_CATEGORIES[:8], 1):
        print(f"  {idx}. {cat}")
    cat_choice = input("Pick primary interest number or name [1. Gym & Fitness]: ").strip() or "1"
    if cat_choice.isdigit() and 1 <= int(cat_choice) <= len(LAUNCH_CATEGORIES):
        selected_cat = LAUNCH_CATEGORIES[int(cat_choice) - 1]
    else:
        selected_cat = cat_choice

    profile = OnboardingFlow.create_fast_path_profile(
        user_id="user_001",
        name=name,
        nickname=nickname,
        age=age,
        languages=languages,
        selected_categories=[selected_cat]
    )

    # Initialize Memory, Pipeline, Routine, Heartbeat, Watchers, Tokens, and Skills
    memory = MemoryStore(":memory:")
    pipeline = PipelineEngine(memory_store=memory)
    routine_graph = RoutineGraph.seed_from_profile(profile)
    scheduled_reg = ScheduledWorkRegistry.install_defaults(profile)
    heartbeat_runner = HeartbeatRunner(profile, routine_graph, scheduled_reg)
    watcher_engine = PriceWatcherEngine()
    token_mgr = TokenManager()
    token_account = token_mgr.get_or_create_account(profile.user_id)
    from .skills import SkillRegistry, SkillCreator
    skill_registry = SkillRegistry()
    skill_creator = SkillCreator(skill_registry)

    print("\n" + "=" * 65)
    print(f"✨ PICO IS ALIVE! Mode: CHILL (Resting state)")
    print(f"✏️  Pico wrote '{profile.name}' in his notebook.")
    print("Type your message to chat.")
    print("Special commands:")
    print("  /what-i-know       - See all facts stored in memory")
    print("  /path              - View today's Routine Graph path")
    print("  /brief             - Trigger Morning Brief")
    print("  /review            - Trigger Evening Review")
    print("  /heartbeat         - Fire 30-min Heartbeat checks")
    print("  /scheduled         - View Scheduled Work tab (trust rule)")
    print("  /sip [amt] [r] [y] - Launch Living SIP Compounding Artifact")
    print("  /goal              - View 90-Day Living Goal Tracker")
    print("  /watch <level>     - Arm Bitcoin Price Watcher (e.g. /watch 68000)")
    print("  /skills            - List all built-in & custom skills")
    print("  /food <dish> [qty] - Indian Food & Nutrition lookup (e.g. /food roti 2)")
    print("  /pomo <hours>      - Pomodoro Deep Work Flow planner (e.g. /pomo 2.5)")
    print("  /levels <H> <L>    - Pivot & Fibonacci Calculator (e.g. /levels 70000 60000)")
    print("  /runway <cash> <b> - Startup Runway & Burn Meter (e.g. /runway 1200000 150000)")
    print("  /pack <city> [d]   - Smart Travel Packing Checklist (e.g. /pack Goa 4)")
    print("  /flashcard <text>  - Generate Active Recall flashcards")
    print("  /script <text>     - Run Script Doctor & Hook Reviewer")
    print("  /macros [w] [h]    - Run TDEE & Macro Nutrition Calculator")
    print("  /browse <url>      - Cloud Browser Agent: read web pages cleanly")
    print("  /tokens            - View token meter & Low Power status")
    print("  /lockin            - Toggle Lock In Mode 🔒")
    print("  /mode <name>       - Manually change outfit/mode (e.g. /mode gym)")
    print("  /exit              - Quit chat")
    print("=" * 65 + "\n")

    current_mode = "chill"

    while True:
        try:
            user_msg = input(f"\n[{profile.nickname}]: ").strip()
            if not user_msg:
                continue

            if user_msg.lower() in ["/exit", "exit", "quit"]:
                print(f"\nPico waves: Bye for now, {profile.nickname}! I'll be keeping your routine safe! 👋✨")
                break

            if user_msg == "/what-i-know":
                facts = memory.get_what_i_know(profile.user_id)
                print(f"\n📖 [What Pico Knows About You ({len(facts)} facts)]:")
                if not facts:
                    print("  (Notebook is still clean - no personal facts stored yet)")
                for f in facts:
                    print(f"  • {f['key']}: {f['value']} ({f['status']}, source: {f['source']})")
                continue

            if user_msg == "/path":
                path = routine_graph.render_day_path()
                print("\n🗺️ [Today's Day Path (Routine Spine)]:")
                for p in path:
                    indicator = "📍 [ACTIVE NOW]" if p["is_active"] else "  "
                    print(f"  {indicator} {p['time']}: {p['name']} ({p['mode']}) -> {p['status']}")
                continue

            if user_msg == "/brief":
                brief = BriefGenerator.generate_morning_brief(profile, routine_graph)
                print(f"\n☀️ [Morning Brief]:\n{brief}")
                continue

            if user_msg == "/review":
                review = BriefGenerator.generate_evening_review(profile, streak_count=1)
                print(f"\n🌙 [Evening Review (21:30)]:\n{review}")
                continue

            if user_msg == "/heartbeat":
                from datetime import datetime
                now_str = datetime.now().strftime("%H:%M")
                beat = heartbeat_runner.fire_beat(now_str)
                print(f"\n💓 [Heartbeat Check at {now_str}]:")
                print(f"  Outcome: {beat.outcome.value}")
                print(f"  Reason:  {beat.reason}")
                print(f"  Quiet Hours: {'Yes' if beat.was_quiet_hours else 'No'}")
                continue

            if user_msg == "/scheduled":
                jobs = scheduled_reg.list_jobs()
                print("\n⏰ [Scheduled Work (Trust Rule - nothing runs that isn't here)]:")
                for j in jobs:
                    status = "✅ Enabled" if j["enabled"] else "⏸️ Disabled"
                    print(f"  • {j['name']} ({j['schedule']}) - {status} - Last: {j['last_run']}")
                continue

            if user_msg.startswith("/sip"):
                parts = user_msg.split()
                amt = float(parts[1]) if len(parts) > 1 else 5000.0
                cagr = float(parts[2]) if len(parts) > 2 else 15.0
                years = int(parts[3]) if len(parts) > 3 else 26
                from .artifacts import ArtifactFactory
                art = ArtifactFactory.create_sip_calculator(profile.user_id, amt, cagr, years)
                print(f"\n📊 [Living Artifact: {art.title}]")
                print(f"  🎯 Primary Value:  {art.summary_header['metric_primary']} ({art.summary_header['label_primary']})")
                print(f"  💰 Invested Total: {art.summary_header['metric_secondary']} ({art.summary_header['label_secondary']})")
                print(f"  💬 His Line: \"{art.his_line}\"")
                print(f"  📌 {art.footer['assumption_chip']}")
                continue

            if user_msg == "/goal":
                from .artifacts import ArtifactFactory
                goal_text = profile.goal_90d or "Launch companion app prototype"
                art = ArtifactFactory.create_goal_tracker(profile.user_id, goal_text)
                print(f"\n🎯 [Living Artifact: {art.title}]")
                print(f"  ⏳ {art.summary_header['metric_primary']} | Progress: {art.summary_header['metric_secondary']}")
                print(f"  💬 His Line: \"{art.his_line}\"")
                continue

            if user_msg.startswith("/watch"):
                parts = user_msg.split()
                target = float(parts[1]) if len(parts) > 1 else 68000.0
                from .watchers import PriceWatcher
                watcher = PriceWatcher(
                    id=f"w_btc_{profile.user_id}",
                    user_id=profile.user_id,
                    symbol="BTCUSDT",
                    target_level=target,
                    direction="below"
                )
                watcher_engine.add_watcher(watcher)
                live_p = watcher_engine.fetch_live_price("BTCUSDT")
                print(f"\n🛡️ [Price Watcher Armed]: Watching BTCUSDT below ${target:,.2f} (Live: ${live_p:,.2f})")
                # Immediate check
                alerts = watcher_engine.evaluate_watchers()
                if alerts:
                    a = alerts[0]
                    print(f"🚨 [PUSH ALERT (<=12 words)]: {a.push_notification}")
                    print(f"📱 [In-App Card]: {a.in_app_card['headline']}")
                    print(f"   {a.in_app_card['open_question']}")
                continue

            if user_msg == "/skills":
                avail = skill_registry.list_skills()
                print("\n🧰 [Pico's Skills Backpack]:")
                for s in avail:
                    print(f"  • {s['name']} ({s['version']}, {s['permission_level']}): {s['description']}")
                continue

            if user_msg.startswith("/script "):
                script_body = user_msg.split(" ", 1)[1]
                res = skill_registry.execute_skill("script_doctor", {"script_text": script_body, "target_seconds": 60})
                if res.success:
                    out = res.output
                    print("\n🎬 [Script Doctor Debrief]:")
                    print(f"  Words: {out['word_count']} (~{out['estimated_runtime_seconds']}s runtime)")
                    print(f"  Hook Score: {out['hook_score']} -> {out['hook_critique']}")
                    print(f"  Pacing: {out['pacing_status']}")
                    print(f"  💡 ONE Advice: {out['one_advice']}")
                continue

            if user_msg.startswith("/macros"):
                parts = user_msg.split()
                w = float(parts[1]) if len(parts) > 1 else 70.0
                h = float(parts[2]) if len(parts) > 2 else 175.0
                age = int(parts[3]) if len(parts) > 3 else 24
                res = skill_registry.execute_skill("macro_calculator", {
                    "weight_kg": w, "height_cm": h, "age": age,
                    "activity_level": "moderate", "goal": "cut", "diet_type": "vegetarian"
                })
                if res.success:
                    out = res.output
                    m = out["macros"]
                    print("\n🥗 [Macro Nutrition Breakdown]:")
                    print(f"  Maintenance TDEE: {out['tdee_maintenance_kcal']} kcal | Target ({out['goal']}): {out['target_calories_kcal']} kcal")
                    print(f"  Protein: {m['protein_grams']}g | Carbs: {m['carbs_grams']}g | Fat: {m['fat_grams']}g")
                    print(f"  Indian Sources ({out['diet_type']}): {', '.join(out['suggested_protein_sources'])}")
                    print(f"  💬 \"{out['his_line']}\"")
                continue

            if user_msg.startswith("/food "):
                parts = user_msg.split()
                dish = parts[1]
                qty = float(parts[2]) if len(parts) > 2 else 1.0
                res = skill_registry.execute_skill("food_lookup", {"food_item": dish, "quantity": qty})
                if res.success:
                    out = res.output
                    m = out["macronutrients"]
                    print(f"\n🍲 [Food Nutrition: {out['item_name']} ({out['servings']}x)]: {out['calories_kcal']} kcal")
                    print(f"  Protein: {m['protein_g']}g | Carbs: {m['carbs_g']}g | Fat: {m['fat_g']}g | Fiber: {m['fiber_g']}g")
                    print(f"  💬 \"{out['his_line']}\"")
                else:
                    print(f"\n⚠️ {res.error}")
                continue

            if user_msg.startswith("/pomo"):
                parts = user_msg.split()
                hrs = float(parts[1]) if len(parts) > 1 else 2.0
                res = skill_registry.execute_skill("pomodoro_planner", {"available_hours": hrs})
                if res.success:
                    out = res.output
                    print(f"\n⏱️ [Pomodoro Deep Work Plan ({hrs}h window)]:")
                    print(f"  Focus: {out['total_focus_time_mins']}m across {out['focus_cycles']} cycles")
                    for t_item in out["timeline"][:4]:
                        print(f"  • {t_item}")
                    print(f"  💬 \"{out['his_line']}\"")
                continue

            if user_msg.startswith("/levels "):
                parts = user_msg.split()
                if len(parts) >= 3:
                    h = float(parts[1])
                    l = float(parts[2])
                    c = float(parts[3]) if len(parts) > 3 else h
                    res = skill_registry.execute_skill("level_calculator", {"high": h, "low": l, "close": c})
                    if res.success:
                        out = res.output
                        fib = out["fibonacci_retracements"]
                        piv = out["pivot_points"]
                        print(f"\n📈 [Fibonacci & Pivot S/R Levels (Range: {l:,.0f} - {h:,.0f})]:")
                        print(f"  Golden Ratio (0.618): {fib['fib_0_618_golden']:,.2f}")
                        print(f"  Central Pivot (PP):   {piv['pivot_point']:,.2f}")
                        print(f"  R1: {piv['resistance_1']:,.2f} | S1: {piv['support_1']:,.2f}")
                        print(f"  📌 {out['compliance_notice']}")
                continue

            if user_msg.startswith("/runway "):
                parts = user_msg.split()
                if len(parts) >= 3:
                    cash = float(parts[1])
                    burn = float(parts[2])
                    res = skill_registry.execute_skill("runway_calculator", {"cash_balance": cash, "monthly_burn_rate": burn})
                    if res.success:
                        out = res.output
                        print(f"\n💼 [Startup Runway Meter]: {out['runway_months']} Months ({out['health_tier']})")
                        print(f"  Zero-Cash Date: {out['estimated_zero_cash_date']}")
                        print(f"  {out['status_notice']}")
                        print(f"  💬 \"{out['his_line']}\"")
                continue

            if user_msg.startswith("/pack "):
                parts = user_msg.split()
                city = parts[1]
                days = int(parts[2]) if len(parts) > 2 else 3
                climate = parts[3] if len(parts) > 3 else "moderate"
                res = skill_registry.execute_skill("packing_checklist", {"destination": city, "trip_days": days, "climate": climate})
                if res.success:
                    out = res.output
                    print(f"\n🎒 [Packing Checklist for {city} ({days} days, {climate})]:")
                    for cat_name, items in out["checklist"].items():
                        print(f"  {cat_name}: {', '.join(items[:3])}...")
                    print(f"  💬 \"{out['his_line']}\"")
                continue

            if user_msg.startswith("/flashcard "):
                notes_text = user_msg.split(" ", 1)[1]
                res = skill_registry.execute_skill("flashcard_generator", {"notes_text": notes_text})
                if res.success:
                    out = res.output
                    print(f"\n📚 [Generated {out['total_cards_created']} Active Recall Cards]:")
                    for c in out["cards"]:
                        print(f"  ❓ Q: {c['question']}")
                        print(f"  💡 A: {c['answer']}")
                    print(f"  💬 \"{out['his_line']}\"")
                continue

            if user_msg.startswith("/browse "):
                url = user_msg.split(" ", 1)[1].strip()
                res = skill_registry.execute_skill("browser_agent", {"url": url})
                if res.success:
                    out = res.output
                    print(f"\n🌐 [Browser Agent: {out.get('title') or out['host']}]:")
                    print(f"  URL: {out['url']} (Status: {out['status_code']})")
                    print(f"  Word count: {out['word_count']} words")
                    print("  --- Extracted Content (Clean & Shielded) ---")
                    lines = [l.strip() for l in out["text_content"].splitlines() if l.strip()]
                    preview = "\n  ".join(lines[:8])
                    print(f"  {preview}")
                    print(f"  💬 \"{out['his_line']}\"")
                else:
                    print(f"\n⚠️ Browser error: {res.error}")
                continue

            if user_msg == "/tokens":
                pct = token_account.usage_percentage
                print(f"\n🪙 [Tokens Page (You Tab)]:")
                print(f"  Remaining: {token_account.tokens_remaining:,} / {token_account.monthly_allowance:,} tokens")
                print(f"  Usage:     {pct:.1f}%")
                print(f"  State:     {'⚠️ LOW POWER FRIEND (Basic chat & watchers alive)' if token_account.is_low_power else '⚡ Full Power'}")
                print(f"  Lock In:   {token_account.lock_in_sessions_left} trial sessions left this month")
                continue

            if user_msg == "/lockin":
                success, msg = token_mgr.enter_lock_in_mode(token_account)
                if success:
                    current_mode = "lock_in"
                    print(f"\n🎧 [MODE: LOCKED IN 🔒]: {msg}")
                else:
                    print(f"\n⚠️ {msg}")
                continue

            if user_msg.startswith("/mode "):
                current_mode = user_msg.split(" ", 1)[1].strip()
                print(f"👕 *Costume-change animation (1s)*: Pico switched to [{current_mode.upper()}] outfit!")
                continue

            # Run 7-Step Pipeline
            result = pipeline.run(
                user_message=user_msg,
                profile=profile,
                active_mode=current_mode
            )

            print(f"\n[Pico 🌟 | Mode: {result['mode']} | Emotion: {result['emotion']}]:")
            print(f"{result['output']}")

            if result["facts_saved"]:
                print(f"✏️  *Pencil-note animation*: Pico saved facts -> {result['facts_saved']}")

        except (KeyboardInterrupt, EOFError):
            print("\nExiting...")
            break


if __name__ == "__main__":
    run_interactive_cli()
