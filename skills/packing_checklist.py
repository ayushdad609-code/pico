"""
Built-in Smart Packing Checklist Generator Skill for Pico.
From YOUR_FRIEND_FULL_SETUP.pdf (§19 Travel & Routine).
"""

import time
from typing import Dict, Any, Optional, List
from .base_skill import BaseSkill, SkillResult
from pico.mcp_host import PermissionLevel


class PackingChecklistSkill(BaseSkill):
    name = "packing_checklist"
    description = "Generates a complete trip packing checklist tailored to destination, trip duration, climate, and activities."
    version = "v1.0"
    permission_level = PermissionLevel.SEE
    parameters_schema = {
        "destination": {"type": "string", "required": True},
        "trip_days": {"type": "integer", "required": False, "default": 3},
        "climate": {"type": "string", "required": False, "default": "moderate"},  # tropical, cold, rainy, moderate
        "trip_type": {"type": "string", "required": False, "default": "leisure"}   # business, leisure, hiking, fitness
    }

    def execute(self, inputs: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> SkillResult:
        start_t = time.time()
        dest = inputs.get("destination", "Your Trip").strip()
        days = max(1, int(inputs.get("trip_days", 3)))
        climate = inputs.get("climate", "moderate").lower()
        trip_type = inputs.get("trip_type", "leisure").lower()

        # Documents & Criticals
        documents = [
            "Government ID / Passport / Visa",
            "Boarding passes / Train tickets (saved offline)",
            "Credit / Debit cards + emergency cash",
            "Hotel / Stay confirmation details"
        ]

        # Clothing calculated based on days
        shirts = days + 1
        underwear = days + 1
        pants = max(2, (days // 2) + 1)
        clothing = [
            f"{shirts}x T-shirts / Tops",
            f"{underwear}x Underwear & Socks",
            f"{pants}x Pants / Shorts / Bottoms",
            "Sleepwear / Loungewear (1-2 sets)"
        ]

        # Climate-specific gear
        if climate == "cold":
            clothing.extend(["1x Heavy jacket or fleece", "Thermal innerwear", "Beanie / Gloves"])
        elif climate == "tropical":
            clothing.extend(["Swimwear", "UV sunglasses", "Light breathable linen / cotton clothes"])
        elif climate == "rainy":
            clothing.extend(["Compact travel umbrella", "Waterproof rain jacket", "Quick-dry socks"])

        # Tech gear
        tech = [
            "Phone + fast charger cable",
            "High-capacity power bank (charged)",
            "Earphones / Headphones (for transit noise)",
            "Universal travel adapter plug"
        ]
        if trip_type == "business":
            tech.extend(["Laptop + charger", "Mouse & notebook with pen"])

        # Toiletries & Health
        toiletries = [
            "Toothbrush + toothpaste (travel size)",
            "Deodorant / Fragrance",
            "Daily sunscreen (SPF 50)",
            "Emergency meds kit (pain reliever, antacid, band-aids)"
        ]

        # Activity specific
        activity_gear = []
        if trip_type in ["hiking", "fitness"]:
            activity_gear = ["Broken-in trail/running shoes", "Electrolyte hydration sachets", "Compact microfiber towel"]
        elif trip_type == "business":
            activity_gear = ["Formal footwear", "Wrinkle-free ironed shirts / blazer"]
        else:
            activity_gear = ["Comfortable daily walking sneakers", "Reusable water bottle"]

        categories = {
            "📄 Documents & Money": documents,
            "👕 Clothing & Layers": clothing,
            "🔌 Tech & Chargers": tech,
            "🧴 Toiletries & Health": toiletries,
            "🎒 Trip Gear": activity_gear
        }

        output = {
            "destination": dest,
            "duration_days": days,
            "climate": climate.title(),
            "trip_type": trip_type.title(),
            "checklist": categories,
            "total_items": sum(len(items) for items in categories.values()),
            "his_line": f"Pack list ready for {dest} ({days} days, {climate})! 🎒 Check off each item before you zip up your bag."
        }

        return SkillResult(
            success=True,
            skill_name=self.name,
            output=output,
            execution_time_ms=round((time.time() - start_t) * 1000, 2)
        )
