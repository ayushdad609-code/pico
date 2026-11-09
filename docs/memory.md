# Pico Companion — MEMORY.md

> **Engine:** Hermes Memory System  
> **Storage:** SQLite Vector & Key-Value Store  
> **Color Identity:** Pico Red (`#EF4444`)

---

## 1. Memory Architecture
Hermes stores personal facts, verified preferences, and habit streaks across 3 tiers:

1. **Short-Term Staging (7 Days):**
   - Ingested Chrome browsing tabs
   - Gmail invoice & alert summaries
   - Transient conversational context

2. **Curated Facts (Committed):**
   - Workout logs & fitness goals
   - Tech stack & coding preferences
   - Core routine wake/sleep anchors

3. **Nightly Self-Report & Scorecard:**
   - 0-2 scale on memory honesty, verdict quality, research honesty, and discipline
   - Heartbeat count (silent vs active beats)
   - Habit streak protection
