"""
Built-in Active Recall Flashcard Generator Skill for Pico.
From YOUR_FRIEND_FULL_SETUP.pdf (§19 Study & Exams).
"""

import time
import re
from typing import Dict, Any, Optional, List
from .base_skill import BaseSkill, SkillResult
from pico.mcp_host import PermissionLevel


class FlashcardGeneratorSkill(BaseSkill):
    name = "flashcard_generator"
    description = "Converts study notes into active-recall Q&A flashcards with spaced repetition intervals."
    version = "v1.0"
    permission_level = PermissionLevel.SEE
    parameters_schema = {
        "notes_text": {"type": "string", "required": True},
        "subject": {"type": "string", "required": False, "default": "General Study"}
    }

    def execute(self, inputs: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> SkillResult:
        start_t = time.time()
        text = inputs.get("notes_text", "").strip()
        subject = inputs.get("subject", "General Study").strip()

        if not text or len(text.split()) < 5:
            return SkillResult(
                success=False,
                skill_name=self.name,
                output={},
                error="Please provide at least 5 words of study notes or text to generate cards."
            )

        # Sentence-based question generation
        sentences = [s.strip() for s in re.split(r"[.\n;]", text) if len(s.strip().split()) >= 4]
        cards: List[Dict[str, Any]] = []

        for idx, s in enumerate(sentences[:5], 1):
            words = s.split()
            # If sentence contains "is" or "are" or "means", make a definitional card
            if re.search(r"\b(is|are|means|refers to|caused by)\b", s, re.IGNORECASE):
                parts = re.split(r"\b(?:is|are|means|refers to|caused by)\b", s, maxsplit=1, flags=re.IGNORECASE)
                q = f"What is {parts[0].strip()}?"
                a = parts[1].strip().capitalize() if len(parts) > 1 else s
            else:
                q = f"Explain the key concept: '{' '.join(words[:4])}...'?"
                a = s

            cards.append({
                "card_id": f"card_{idx}",
                "question": q,
                "answer": a,
                "review_schedule": {
                    "first_review": "Tomorrow (Day 1)",
                    "second_review": "In 3 Days",
                    "mastery_review": "In 7 Days"
                }
            })

        output = {
            "subject": subject,
            "total_cards_created": len(cards),
            "cards": cards,
            "his_line": f"Created {len(cards)} active recall flashcards for {subject}! Review them tomorrow morning to lock in memory."
        }

        return SkillResult(
            success=True,
            skill_name=self.name,
            output=output,
            execution_time_ms=round((time.time() - start_t) * 1000, 2)
        )
