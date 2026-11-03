"""
Tests for Pico Built-in Skills and Dynamic Skill Creator.
"""

from pico.skills import (
    SkillRegistry,
    SkillCreator,
    SkillSpec,
    ScriptDoctorSkill,
    MacroCalculatorSkill,
    FoodLookupSkill,
    FlashcardGeneratorSkill,
    PomodoroPlannerSkill,
    LevelCalculatorSkill,
    RunwayCalculatorSkill,
    PackingChecklistSkill
)
from pico.mcp_host import PermissionLevel


def test_script_doctor_skill():
    skill = ScriptDoctorSkill()
    sample_script = (
        "Why do 90% of creators fail on YouTube Shorts? "
        "Because they spend 20 minutes explaining the problem before getting to the solution. "
        "In this video, I will show you the exact 3-second hook structure that keeps retention above 80%."
    )
    res = skill.execute({"script_text": sample_script, "target_seconds": 30})
    assert res.success is True
    assert res.output["word_count"] > 20
    assert "one_advice" in res.output


def test_macro_calculator_skill():
    skill = MacroCalculatorSkill()
    res = skill.execute({
        "weight_kg": 72.0, "height_cm": 178.0, "age": 24,
        "activity_level": "moderate", "goal": "cut", "diet_type": "vegetarian"
    })
    assert res.success is True
    assert res.output["macros"]["protein_grams"] >= 120
    assert "Paneer" in res.output["suggested_protein_sources"]


def test_food_lookup_skill():
    skill = FoodLookupSkill()

    # 1. Look up 2 rotis
    res_roti = skill.execute({"food_item": "roti", "quantity": 2})
    assert res_roti.success is True
    assert res_roti.output["calories_kcal"] == 170  # 85 * 2
    assert res_roti.output["macronutrients"]["protein_g"] == 6.0

    # 2. Look up paneer
    res_paneer = skill.execute({"food_item": "paneer", "quantity": 1})
    assert res_paneer.success is True
    assert res_paneer.output["macronutrients"]["protein_g"] == 18.0

    # 3. Unknown food item error handling
    res_unknown = skill.execute({"food_item": "extraterrestrial_pie"})
    assert res_unknown.success is False
    assert "Couldn't find exact nutrition" in res_unknown.error


def test_flashcard_generator_skill():
    skill = FlashcardGeneratorSkill()
    notes = (
        "Photosynthesis is the process used by plants to convert light energy into chemical energy. "
        "Mitochondria are known as the powerhouse of the cell. "
        "Chlorophyll is the green pigment responsible for absorbing light."
    )
    res = skill.execute({"notes_text": notes, "subject": "Biology"})
    assert res.success is True
    assert res.output["total_cards_created"] >= 2
    assert "Tomorrow (Day 1)" in res.output["cards"][0]["review_schedule"]["first_review"]


def test_pomodoro_planner_skill():
    skill = PomodoroPlannerSkill()

    # 2.5 hours session -> should yield ~5 cycles
    res = skill.execute({"available_hours": 2.5, "mode_preference": "standard_25", "task_name": "Maths"})
    assert res.success is True
    assert res.output["focus_cycles"] >= 4
    assert len(res.output["timeline"]) >= 4

    # Long session burnout warning
    res_long = skill.execute({"available_hours": 5.0})
    assert res_long.output["burnout_warning"] is not None


def test_level_calculator_skill():
    skill = LevelCalculatorSkill()
    res = skill.execute({"high": 70000.0, "low": 60000.0, "close": 68000.0})
    assert res.success is True
    out = res.output

    # Golden ratio 0.618 level = 70000 - 0.618 * 10000 = 63820.0
    assert out["fibonacci_retracements"]["fib_0_618_golden"] == 63820.0
    # Pivot point = (70000 + 60000 + 68000) / 3 = 66000.0
    assert out["pivot_points"]["pivot_point"] == 66000.0
    assert "Not investment advice" in out["compliance_notice"]


def test_runway_calculator_skill():
    skill = RunwayCalculatorSkill()

    # Critical runway (< 6 months)
    res_crit = skill.execute({"cash_balance": 500000, "monthly_burn_rate": 150000})
    assert res_crit.success is True
    assert res_crit.output["runway_months"] == 3.3
    assert "CRITICAL" in res_crit.output["health_tier"]

    # Healthy runway (> 12 months)
    res_safe = skill.execute({"cash_balance": 2400000, "monthly_burn_rate": 100000})
    assert res_safe.output["runway_months"] == 24.0
    assert "HEALTHY" in res_safe.output["health_tier"]


def test_packing_checklist_skill():
    skill = PackingChecklistSkill()
    res = skill.execute({"destination": "Goa", "trip_days": 4, "climate": "tropical", "trip_type": "leisure"})
    assert res.success is True
    out = res.output

    assert out["duration_days"] == 4
    assert "5x T-shirts / Tops" in out["checklist"]["👕 Clothing & Layers"]
    assert "Swimwear" in out["checklist"]["👕 Clothing & Layers"]
    assert out["total_items"] > 10


def test_skill_creator_and_registry_integration():
    registry = SkillRegistry()
    creator = SkillCreator(registry)

    # All 9 default skills are loaded (including browser_agent)
    assert len(registry.skills) == 9

    # Dynamic creation test
    def hydration_calc(inputs):
        return {"glasses": inputs.get("weight_kg", 60) // 10}

    spec = SkillSpec(
        name="custom_hydration",
        description="Calculates glasses of water",
        parameters_schema={"weight_kg": {"type": "number", "required": True}},
        logic_callable=hydration_calc
    )
    ok, msg, _ = creator.create_and_register_skill(spec, dry_run_input={"weight_kg": 70})
    assert ok is True
    assert len(registry.skills) == 10


def test_browser_skill_clean_fetch():
    from pico.skills import BrowserSkill
    skill = BrowserSkill()

    # Normal public URL
    res = skill.execute({"url": "https://example.com", "max_length": 500})
    assert res.success is True
    assert "example.com" in res.output["host"]
    assert len(res.output["text_content"]) > 0


def test_browser_skill_ssrf_protection():
    from pico.skills import BrowserSkill
    skill = BrowserSkill()

    # Disallowed local network hosts
    bad_urls = [
        "http://localhost:8080/admin",
        "http://127.0.0.1:5432",
        "http://169.254.169.254/latest/meta-data",
        "http://192.168.1.1/router"
    ]

    for bad in bad_urls:
        res = skill.execute({"url": bad})
        assert res.success is False
        assert "blocked by Security Policy" in res.error
