# Pico UI Design & Architecture Brief

> **Version:** 1.0.0  
> **Status:** Implemented & Verified  
> **Repository:** `pico`  
> **Primary Serving Route:** `http://127.0.0.1:8000/`

---

## 1. Executive Summary & Design Vision

**Pico** is a standalone agentic companion, routine spine, and daily momentum engine. The user interface bridges two distinct paradigms:
1. **Duolingo Physical Tactility:** Playful, high-dopamine 3D push-button affordances, winding routine spines, and physical feedback without visual fatigue.
2. **Meta Muse Agentic Transparency:** Clutter-free conversational grammar, 3-layer progressive disclosure (glanceable -> visual pipeline -> granular audit), and dedicated, non-polluting workspace panels.

The interface is intentionally **minimal, clean, and distraction-free**, adhering to a strict **Zero-Emoji Policy** across navigation, headers, status tags, and buttons to maintain focused typography.

---

## 2. Core Design Tokens & Visual Language

### 2.1 Color Palette
* **Primary / Success:** `#58cc02` (`--duo-feather-green`), shadow `#58a700` (`--duo-mask-green`)
* **Urgency / Abort:** `#ff4b4b` (`--duo-cardinal`), shadow `#ea2b2b` (`--duo-cardinal-dark`)
* **Information / Tools:** `#1cb0f6` (`--duo-sky`), shadow `#1899d6`
* **XP / Highlight:** `#ffc800` (`--duo-macaw`), shadow `#e5a500`
* **Surfaces:** `#ffffff` (`--duo-snow`), `#f7f7f7` (`--duo-polar`), `#e5e5e5` (`--duo-swan`)
* **Typography:** `#4b4b4b` (`--muse-ink`), `#777777` (`--muse-ink-secondary`), `#afafaf` (`--muse-ink-muted`)
* **Accents:** `#7c3aed` (Pico Purple accent), `#f5f3ff` (Purple tint)

### 2.2 Tactile 3D Affordance
Buttons use a physical bottom shadow layer that depresses 4px on click/tap:
```css
.duo-btn-3d {
  background-color: var(--duo-feather-green);
  box-shadow: 0 4px 0 var(--duo-mask-green);
  transition: transform 0.08s ease, box-shadow 0.08s ease;
}
.duo-btn-3d:active {
  transform: translateY(4px);
  box-shadow: 0 0 0 transparent;
}
```

---

## 3. Structural Page Breakdown

### View 1: Authentic Duolingo Frontpage Hero (`#view-duolingo`)
* **Layout:** Centered two-column split with max-width 1040px.
* **Left Graphic:** Pico Mascot pointing at the primary call-to-action with animated float/bob (`duo-bob`).
* **Right Hero Content:**
  * Clean headline: *"The free, fun, and effective way to master your daily momentum!"*
  * Primary Button: **`GET STARTED`** (3D green button, switches to Muse Chat).
  * Secondary Button: **`I ALREADY HAVE AN ACCOUNT`** (3D white outline button).
* **Stripped Clutter:** Marketing ribbon, feature comparison rows, and multi-column footers removed.

### View 2: Muse Chat & Workspace Viewport (`#view-chat`)
* **Layout:** Full-height responsive layout with collapsible sidebar and master switcher bar.
* **Master Switcher Bar:** Top header allowing quick switching between **Duolingo**, **Chat**, and **Settings**.
* **Top-Right Mascot Avatar (`#btn-pico-tasks`):**
  * Tapping Pico's circular avatar toggles a clean, white floating dropdown card displaying today's prioritized tasks and current routine spine state.
* **Sidebar Minimal Navigation (`.muse-sidebar`):**
  * Dedicated workspace buttons with clean panel switching (does **not** pollute the chat thread):
    1. **`chat`**: Return to active companion chat conversation.
    2. **`connectors`**: Status of external pipes (Chrome DevTools CDP, Gmail IMAP, Twilio WebSocket).
    3. **`skills`**: Installed sandboxed Python skills + Component Registries catalog.
    4. **`artifacts`**: Dynamic living artifacts (SIP compound interest calculator & 90-day trajectory tracker).
    5. **`md files`**: Direct repository documentation viewer.
    6. **`download`**: Direct JSON chat history export (`pico_chat_export_YYYY-MM-DD.json`).
    7. **`schedule`**: 24-hour routine spine table with quiet hours.
  * **Bottom Profile Section:** Displays user name (`Ayush`), role (`Founder`), and a clean progress tag (streak flames removed).

### View 3: Settings & Governance (`#view-settings`)
* **Profile & 90-Day Trajectory:** Trajectory goal editor with real-time word counter enforcing the 20-word minimum threshold.
* **Voice & Telephony:** Twilio cloud media stream bridge settings and Ask-First authority gates (L0 Observation -> L1 Reversible -> L2 Live Call -> L3 Hard-Blocked).
* **Daily Spine & Quiet Hours:** Sleep schedule protection enforcing strict quiet hours (22:00–07:00).
* **Watchers, Memory & Quota:** Chrome tabs, Gmail receipt scanner, 7-day memory staging, and 40M token quota monitor.

---

## 4. Component Libraries & Design Engineering Integration

Integrated into the **Skills** workspace panel and agent skill directory:
* **21st.dev:** The npm for design engineers (`npx 21st add <item>`, Magic MCP).
* **v0 by Vercel:** Generative UI engine producing React + shadcn/ui layouts (`npx v0 add <block-id>`).
* **shadcn/ui:** Accessible primitives on Radix UI + Tailwind tokens (`npx shadcn@latest add`).
* **Magic UI:** 150+ animated blocks: Bento grids, border beams, marquees, confetti.
* **Aceternity UI:** 3D cards, lamp glow headers, hero parallax, canvas shaders.
* **Origin UI:** Accessible form controls, inputs, selects, switches, and sliders.
* **Uiverse.io:** 4,000+ open-source CSS & Tailwind micro-elements.
* **Cult UI:** Dynamic islands, audio buttons, and shader canvases.

---

## 5. Artifact Distribution & Standalone Builds

1. **Local Server (aiohttp):**
   * Server: [`pico/api.py`](file:///data/data/com.termux/files/home/pico/api.py)
   * Static assets: [`pico/static/index.html`](file:///data/data/com.termux/files/home/pico/static/index.html), [`pico/static/style.css`](file:///data/data/com.termux/files/home/pico/static/style.css), [`pico/static/app.js`](file:///data/data/com.termux/files/home/pico/static/app.js)
2. **Standalone Single-File:**
   * Path: [`/sdcard/Download/pico.html`](file:///sdcard/Download/pico.html) (also in `~/downloads/pico.html`)
   * Fully inlined CSS, JS, and base64 mascot image for offline mobile viewing.
3. **Modular Distribution Directory:**
   * Path: [`/sdcard/Download/pico_site/`](file:///sdcard/Download/pico_site)

---

## 6. Test Suite & Verification

Pico UI endpoints and DOM integrity are validated by automated tests in [`tests/test_api.py`](file:///data/data/com.termux/files/home/pico/tests/test_api.py):
* `test_api_get_started_page_endpoint`: Validates hero elements, 3D buttons, workspace panel DOM nodes, absence of emojis, and absence of deprecated marketing ribbons.
* Run command: `pytest tests/test_api.py` (100% passing).
