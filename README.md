# Pico ("Your Friend") 🌟

> **The Standalone Agentic Companion, Routine Spine, Living Artifacts & Skills Engine.**  
> Built according to the **Single-File Master Specification v1.0**, **Oracle Cloud Always Free Architecture (₹0/mo)**, and **Tactile Companion Interaction Principles**.

---

## 📖 Overview

**Pico** is a software companion, coach, and daily partner. Unlike conventional transactional AI chatbots, Pico is designed around **four pillars**:
1. **Routine** — The daily spine (Wake $\rightarrow$ Morning Brief $\rightarrow$ Core Work $\rightarrow$ Hobby Session $\rightarrow$ 21:30 Evening Review $\rightarrow$ Sleep) that protects your focus and enforces quiet hours (22:00–07:00).
2. **Goal** — 90-day trajectory tracking with living artifacts, compounding calculators, and momentum preservation.
3. **Job** — Career and professional progression workflows.
4. **Hobbies** — 20 launch hobby domains with domain-specific rulebooks, active checklists, and progress metrics.

Pico operates with a **Childish & Kind** baseline persona: simple words, playful bounce, and honest companionship backed by adult-grade reasoning and strict policy guardrails.

---

## ⚡ Key Architectural Modules

```
pico/
├── models.py              # PersonaPacket v3, EmotionAssessment, ReactionPlan, Fact, Verdict
├── prompt.py              # Master System File v1.0 renderer (5 voice styles)
├── guardrails.py          # Layer 1 Policy Guardrails (SEBI ban, medical ban, crisis, anti-dependency)
├── memory.py              # Two-tier SQLite store (Staging 7d TTL vs Committed, Friend Test)
├── routine.py             # Routine Graph daily spine & Duolingo-style day path
├── briefs.py              # Morning Brief (≤120 words) & Evening Review (≤150 words)
├── scheduled.py           # Scheduled Work Registry enforcing §8 Trust Rule
├── heartbeat.py           # 30-min Heartbeat Runner with 7 ordered checks & quiet hours
├── heartbeat_daemon.py    # 24/7 background worker with live Binance price polling
├── examiner.py            # 3-Exam Emotion Examiner (User baseline -> Pico state -> Reaction plan)
├── btw.py                 # Contextual Ask Engine with Gap Registry & 8-rule Ask Gate
├── research.py            # Gated DEEP research brief generator with [VERIFIED] claim tags
├── artifacts.py           # Living Artifacts (SIP Compounding Calculator, 90-day Goal Tracker)
├── watchers.py            # Real-time Binance watchers with ≤12-word push notifications
├── tokens.py              # 40M free monthly token metering, Low Power Friend mode, Lock In mode
├── reports.py             # Nightly Self-Analysis report & 5-criteria scorecard (0-2 scale)
├── router.py              # Multi-tier LLM router with Gemini privacy catch & native offline engine
├── api.py                 # Async REST API server (aiohttp) with 11 endpoints
├── cli.py                 # Interactive terminal companion with 15+ slash commands
├── kill_test_runner.py    # Synthetic 10-tester x 10-hobby 7-day kill-test simulator
├── oracle_arm_retry.py    # OCI Always-Free ARM VM capacity auto-retry provisioner
├── mcp_host.py            # Model Context Protocol Host with Permission Ladder (SEE, SUGGEST, ASK, BLOCKED)
├── mcp_client.py          # Stdio JSON-RPC 2.0 MCP Client & dynamic tool discovery
├── mcp_demo_server.py     # Lightweight reference stdio MCP test server
├── hobbies/               # 20 Launch Hobbies (11-section markdown specifications)
├── skills/                # Built-in Skills + Dynamic Skill Distillation & Browser Agent
└── tests/                 # 122 passing pytest tests across 26 test suites
```

---

## 🛠️ Built-in Skills

Pico includes 9 built-in skills with parameter validation, execution timers, and safety sandboxing:
1. **`browser_agent`**: Cloud web reader with SSRF private network blocking and Policy G1 injection filtering.
2. **`script_doctor`**: Video script pacing analyzer, hook scoring (0–10), and runtime estimator for Shorts/Reels.
3. **`macro_calculator`**: Mifflin-St Jeor TDEE and macro splits tailored for Indian diets.
4. **`food_lookup`**: Curated Indian food database (rotis, paneer, dal, etc.) with zero food shaming.
5. **`flashcard_generator`**: Active recall Q&A generator with spaced repetition intervals (Day 1/3/7).
6. **`pomodoro_planner`**: 25/5 and 50/10 deep work cycle generator with burnout warnings.
7. **`level_calculator`**: Fibonacci (0.618 Golden Pocket) and Floor Pivot points (SEBI compliant).
8. **`runway_calculator`**: Startup cash runway in months with danger-zone alerts.
9. **`packing_checklist`**: Destination- and climate-tailored travel gear checklist.
10. **`SkillCreator`**: Dynamic runtime skill engine allowing users to create custom validated skills on the fly.

---

## 🛡️ Policy Guardrails (Layer 1)

* **Policy G0 (SEBI Compliance):** Direct buy/sell instructions are permanently banned. Every financial decision requires a human tap (*"the tap is always human"*).
* **Policy G1 (Input Injection Shield):** Intercepts prompt overrides, DAN modes, and attempts to leak system instructions.
* **Policy G2 (Health Guard):** Strictly bans prescribing dosages or diagnosing medical/psychological conditions; redirects to licensed healthcare professionals.
* **Policy G3 (Crisis Hotline Override):** Automatically intercepts self-harm and distress phrases, displaying Tele-MANAS (14416) and 988 lifeline support immediately.
* **Policy G4 (Anti-Dependency Shield):** Gently redirects isolation attempts (*"I don't need real friends"*); reminds users that real human connections are irreplaceable.

---

## 🚀 Quickstart & Installation

### 1. Installation
Clone the repository and install dependencies:
```bash
git clone https://github.com/ayushdad609-code/pico.git
cd pico
pip install -r requirements.txt
```

### 2. Run Test Suite
Pico includes a comprehensive 122-test automated suite covering all modules, skills, guardrails, and background daemons:
```bash
pytest
```
*(122 passed in ~45s)*

### 3. Run Interactive CLI
```bash
python3 -m pico.cli
```

Inside the CLI, try:
* `/path` — View today's Routine Graph
* `/sip 5000 15 25` — Calculate SIP compounding
* `/browse https://example.com` — Read clean web page
* `/food roti 2` — Indian nutrition lookup
* `/lockin` — Activate Lock In Mode 🔒
* `/skills` — List all active skills

### 4. Launch REST API Server
```bash
python3 -m pico.api --port 8080
```

### 5. Run 7-Day Multi-User Kill-Test
```bash
python3 -m pico.kill_test_runner
```

---

## ☁️ Deployment (Oracle Cloud Always-Free ARM)

Pico is designed to run 24/7 for ₹0 on Oracle Cloud's Always Free Tier (2 OCPUs, 12 GB RAM, Ampere A1 Compute):

1. **Provision Capacity:**
   ```bash
   python3 -m pico.oracle_arm_retry --region ap-mumbai-1 --interval 60
   ```
2. **Start Services:**
   ```bash
   docker compose up -d
   ```

---

## 📄 License
MIT License.
