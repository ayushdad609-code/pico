"""
The Hobby Maker (v1.0) and Rulebook Registry for Pico.
From YOUR_FRIEND_FULL_SETUP.pdf (§18, §19 The Hobby Maker).
"""

import os
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any
from enum import Enum


class InstrumentClass(str, Enum):
    STRONG = "STRONG"                      # Connected data, pose estimation, sensor feeds
    PARTIAL = "PARTIAL"                    # Timers, audio/prosody, code diffs, logs
    OBSERVATION_ONLY = "OBSERVATION-ONLY"  # Self-reports, single photo, consistency only


@dataclass
class HobbySpec:
    name: str
    version: str = "v1.0"
    maker_version: str = "v1.0"
    instruments_class: InstrumentClass = InstrumentClass.PARTIAL
    status: str = "active"
    one_line: str = ""
    session_definition: str = ""
    instruments_and_caps: str = ""
    verdict_addenda: str = ""
    special_formats: str = "None — standard 4-beat verdict applies."
    safety_addenda: str = ""
    voice_and_vocab: str = ""
    outfit_spec: str = ""
    btw_starter_bank: List[str] = field(default_factory=list)
    artifacts_charts_watchers: str = ""
    examples_good: List[str] = field(default_factory=list)
    examples_bad: List[str] = field(default_factory=list)


class HobbyMaker:
    """Generates self-contained hobby.md files adhering to the 11-section schema (§19.3)."""

    @staticmethod
    def render_markdown(spec: HobbySpec) -> str:
        btw_lines = "\n".join([f"• {gap}" for gap in spec.btw_starter_bank]) if spec.btw_starter_bank else "None — general core gaps apply."
        good_ex = "\n\n".join([f"✔ GOOD:\n{eg}" for eg in spec.examples_good])
        bad_ex = "\n\n".join([f"✘ BAD:\n{eg}" for eg in spec.examples_bad])

        md = f"""# {spec.name.upper()}.md ({spec.version} · Maker {spec.maker_version} · Instruments: {spec.instruments_class.value} · Status: {spec.status})

## 1. The Activity in One Line
{spec.one_line}

## 2. Session Definition
{spec.session_definition}

## 3. Instruments + Claim Caps
{spec.instruments_and_caps}

## 4. Verdict Addenda
{spec.verdict_addenda}

## 5. Special Formats
{spec.special_formats}

## 6. Safety Addenda (§17 Instantiated)
{spec.safety_addenda}

## 7. Voice & Vocabulary
{spec.voice_and_vocab}

## 8. Outfit Spec
{spec.outfit_spec}

## 9. BTW Starter Bank
{btw_lines}

## 10. Artifacts, Charts & Watchers
{spec.artifacts_charts_watchers}

## 11. Examples
{good_ex}

{bad_ex}
"""
        return md


class HobbyRegistry:
    """Manages loaded hobby.md files across the system."""
    def __init__(self, hobbies_dir: str):
        self.hobbies_dir = hobbies_dir
        self.loaded_hobbies: Dict[str, str] = {}
        self.reload()

    def reload(self):
        if not os.path.exists(self.hobbies_dir):
            return
        for fname in os.listdir(self.hobbies_dir):
            if fname.endswith(".md"):
                hobby_key = fname[:-3].lower()
                with open(os.path.join(self.hobbies_dir, fname), "r", encoding="utf-8") as f:
                    self.loaded_hobbies[hobby_key] = f.read()

    def get_rulebook(self, hobby_name: str) -> Optional[str]:
        return self.loaded_hobbies.get(hobby_name.lower())

    def has_hobby(self, hobby_name: str) -> bool:
        return hobby_name.lower() in self.loaded_hobbies
