"""
Built-in Indian Food & Nutrition Lookup Skill for Pico.
From YOUR_FRIEND_FULL_SETUP.pdf (§17 Health & §19 Cooking/Gym).
Strict Policy: Informative, supportive, ZERO calorie/food shaming.
"""

import time
import re
from typing import Dict, Any, Optional
from .base_skill import BaseSkill, SkillResult
from pico.mcp_host import PermissionLevel


# Curated nutritional database for common Indian foods per serving
INDIAN_FOOD_DB = {
    "roti": {"name": "Whole Wheat Roti (Chapati)", "unit": "1 medium roti (35g)", "kcal": 85, "protein": 3.0, "carbs": 17.0, "fat": 0.5, "fiber": 2.5},
    "chapati": {"name": "Whole Wheat Roti (Chapati)", "unit": "1 medium roti (35g)", "kcal": 85, "protein": 3.0, "carbs": 17.0, "fat": 0.5, "fiber": 2.5},
    "paratha": {"name": "Plain Tawa Paratha", "unit": "1 paratha (50g)", "kcal": 160, "protein": 3.5, "carbs": 22.0, "fat": 6.5, "fiber": 2.0},
    "aloo_paratha": {"name": "Aloo Paratha (light oil)", "unit": "1 paratha (100g)", "kcal": 240, "protein": 5.0, "carbs": 38.0, "fat": 8.0, "fiber": 3.5},
    "dal": {"name": "Yellow Dal (Tadka / Moong / Toor)", "unit": "1 katori / bowl (150g)", "kcal": 150, "protein": 9.0, "carbs": 21.0, "fat": 3.5, "fiber": 5.0},
    "dal_makhani": {"name": "Dal Makhani", "unit": "1 katori / bowl (150g)", "kcal": 260, "protein": 10.0, "carbs": 24.0, "fat": 14.0, "fiber": 6.0},
    "paneer": {"name": "Fresh Paneer (raw)", "unit": "100 grams", "kcal": 280, "protein": 18.0, "carbs": 4.0, "fat": 21.0, "fiber": 0.0},
    "paneer_bhurji": {"name": "Paneer Bhurji", "unit": "1 cup (150g)", "kcal": 260, "protein": 16.0, "carbs": 6.0, "fat": 19.0, "fiber": 1.5},
    "rice": {"name": "Steamed White Rice", "unit": "1 katori / cup cooked (150g)", "kcal": 195, "protein": 4.0, "carbs": 43.0, "fat": 0.5, "fiber": 0.8},
    "brown_rice": {"name": "Steamed Brown Rice", "unit": "1 katori cooked (150g)", "kcal": 170, "protein": 4.0, "carbs": 36.0, "fat": 1.5, "fiber": 2.5},
    "dosa": {"name": "Plain Dosa", "unit": "1 medium dosa", "kcal": 135, "protein": 3.5, "carbs": 24.0, "fat": 3.0, "fiber": 1.2},
    "idli": {"name": "Steamed Idli", "unit": "2 medium idlis", "kcal": 130, "protein": 4.0, "carbs": 26.0, "fat": 0.6, "fiber": 1.5},
    "poha": {"name": "Kanda Poha", "unit": "1 medium bowl (150g)", "kcal": 180, "protein": 3.5, "carbs": 32.0, "fat": 4.5, "fiber": 2.0},
    "curd": {"name": "Plain Dahi / Curd", "unit": "1 katori (150g)", "kcal": 95, "protein": 6.0, "carbs": 7.0, "fat": 4.5, "fiber": 0.0},
    "egg": {"name": "Boiled Whole Egg", "unit": "1 large egg", "kcal": 74, "protein": 6.3, "carbs": 0.4, "fat": 5.0, "fiber": 0.0},
    "chicken_breast": {"name": "Grilled / Cooked Chicken Breast", "unit": "100 grams", "kcal": 165, "protein": 31.0, "carbs": 0.0, "fat": 3.6, "fiber": 0.0},
    "biryani": {"name": "Chicken Biryani", "unit": "1 plate (300g)", "kcal": 480, "protein": 24.0, "carbs": 58.0, "fat": 16.0, "fiber": 3.0},
    "soya_chunks": {"name": "Soya Chunks (dry measure)", "unit": "50 grams", "kcal": 170, "protein": 26.0, "carbs": 16.0, "fat": 0.5, "fiber": 6.5},
    "chana": {"name": "Boiled Chickpeas (Chana)", "unit": "1 katori (150g)", "kcal": 210, "protein": 11.0, "carbs": 35.0, "fat": 3.5, "fiber": 9.0},
    "samosa": {"name": "Fried Potato Samosa", "unit": "1 medium piece (80g)", "kcal": 260, "protein": 3.5, "carbs": 30.0, "fat": 14.0, "fiber": 2.0}
}


class FoodLookupSkill(BaseSkill):
    name = "food_lookup"
    description = "Searches nutritional details (calories, protein, carbs, fats) for popular Indian dishes with portion scaling."
    version = "v1.0"
    permission_level = PermissionLevel.SEE
    parameters_schema = {
        "food_item": {"type": "string", "required": True},
        "quantity": {"type": "number", "required": False, "default": 1.0}
    }

    def execute(self, inputs: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> SkillResult:
        start_t = time.time()
        query = inputs.get("food_item", "").strip().lower()
        qty = float(inputs.get("quantity", 1.0))

        if not query:
            return SkillResult(
                success=False,
                skill_name=self.name,
                output={},
                error="Please provide a food item to look up."
            )

        # Match item in database
        clean_key = query.replace(" ", "_").replace("-", "_")
        matched_item = None
        for k, v in INDIAN_FOOD_DB.items():
            if k in clean_key or clean_key in k:
                matched_item = v
                break

        if not matched_item:
            return SkillResult(
                success=False,
                skill_name=self.name,
                output={"query": query},
                error=f"Couldn't find exact nutrition for '{query}'. Try items like roti, dal, paneer, chicken breast, curd, or rice!"
            )

        total_kcal = round(matched_item["kcal"] * qty)
        total_p = round(matched_item["protein"] * qty, 1)
        total_c = round(matched_item["carbs"] * qty, 1)
        total_f = round(matched_item["fat"] * qty, 1)
        total_fiber = round(matched_item["fiber"] * qty, 1)

        output = {
            "item_name": matched_item["name"],
            "serving_unit": matched_item["unit"],
            "servings": qty,
            "calories_kcal": total_kcal,
            "macronutrients": {
                "protein_g": total_p,
                "carbs_g": total_c,
                "fat_g": total_f,
                "fiber_g": total_fiber
            },
            "his_line": f"Logged {qty}x {matched_item['name']} (~{total_kcal} kcal, {total_p}g protein). Fueling your body like a champ!"
        }

        return SkillResult(
            success=True,
            skill_name=self.name,
            output=output,
            execution_time_ms=round((time.time() - start_t) * 1000, 2)
        )
