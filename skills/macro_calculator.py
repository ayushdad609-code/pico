"""
Built-in TDEE & Macro Nutrition Calculator Skill for Pico.
From YOUR_FRIEND_FULL_SETUP.pdf (§19 Gym & Food).
"""

import time
from typing import Dict, Any, Optional
from .base_skill import BaseSkill, SkillResult
from pico.mcp_host import PermissionLevel


class MacroCalculatorSkill(BaseSkill):
    name = "macro_calculator"
    description = "Calculates BMR, TDEE, and daily protein/carbs/fat targets with Indian vegetarian and non-veg dietary options."
    version = "v1.0"
    permission_level = PermissionLevel.SEE
    parameters_schema = {
        "weight_kg": {"type": "number", "required": True},
        "height_cm": {"type": "number", "required": True},
        "age": {"type": "integer", "required": True},
        "gender": {"type": "string", "required": False, "default": "male"},
        "activity_level": {"type": "string", "required": False, "default": "moderate"},
        "goal": {"type": "string", "required": False, "default": "cut"},
        "diet_type": {"type": "string", "required": False, "default": "vegetarian"}
    }

    def execute(self, inputs: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> SkillResult:
        start_t = time.time()
        w = float(inputs.get("weight_kg", 70.0))
        h = float(inputs.get("height_cm", 175.0))
        age = int(inputs.get("age", 24))
        gender = inputs.get("gender", "male").lower()
        activity = inputs.get("activity_level", "moderate").lower()
        goal = inputs.get("goal", "cut").lower()
        diet = inputs.get("diet_type", "vegetarian").lower()

        # Mifflin-St Jeor BMR Equation
        if gender == "female":
            bmr = 10 * w + 6.25 * h - 5 * age - 161
        else:
            bmr = 10 * w + 6.25 * h - 5 * age + 5

        # Activity multipliers
        multipliers = {
            "sedentary": 1.2,
            "light": 1.375,
            "moderate": 1.55,
            "active": 1.725,
            "very_active": 1.9
        }
        mult = multipliers.get(activity, 1.55)
        tdee = bmr * mult

        # Adjust for goal
        if goal == "cut":
            target_calories = round(tdee - 400)
            target_label = "Caloric Deficit (Fat Loss)"
        elif goal == "bulk":
            target_calories = round(tdee + 350)
            target_label = "Caloric Surplus (Muscle Building)"
        else:
            target_calories = round(tdee)
            target_label = "Maintenance"

        # Protein target: ~1.8g to 2.0g per kg of bodyweight
        protein_g = round(w * 1.8)
        # Fat target: ~0.8g per kg of bodyweight
        fat_g = round(w * 0.8)
        # Remainder calories into Carbs (4 kcal/g protein, 9 kcal/g fat, 4 kcal/g carbs)
        cals_from_p_and_f = (protein_g * 4) + (fat_g * 9)
        carbs_g = max(50, round((target_calories - cals_from_p_and_f) / 4))

        # Suggested food sources based on Indian dietary preferences
        if diet == "vegetarian":
            sources = ["Paneer", "Greek Yogurt / Curd", "Tofu / Soya Chunks", "Moong Dal", "Whey Protein"]
        elif diet == "vegan":
            sources = ["Tofu", "Soya Chunks", "Chickpeas (Chana)", "Lentils (Dal)", "Pea Protein Isolate"]
        else:
            sources = ["Eggs", "Chicken Breast", "Fish", "Paneer / Curd", "Whey Protein"]

        output = {
            "bmr_kcal": round(bmr),
            "tdee_maintenance_kcal": round(tdee),
            "target_calories_kcal": target_calories,
            "goal": target_label,
            "macros": {
                "protein_grams": protein_g,
                "carbs_grams": carbs_g,
                "fat_grams": fat_g
            },
            "diet_type": diet.title(),
            "suggested_protein_sources": sources,
            "his_line": f"Target locked: {target_calories} kcal with {protein_g}g protein! Boring daily consistency beats perfection every time."
        }

        return SkillResult(
            success=True,
            skill_name=self.name,
            output=output,
            execution_time_ms=round((time.time() - start_t) * 1000, 2)
        )
