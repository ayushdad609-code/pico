"""
Tests for Hobby Maker, hobby.md schema compliance, and Hobby Registry.
From YOUR_FRIEND_FULL_SETUP.pdf (§19 The Hobby Maker).
"""

import os
from pico.hobby_maker import HobbyMaker, HobbyRegistry, HobbySpec, InstrumentClass


def test_hobby_registry_loading():
    hobbies_dir = "/data/data/com.termux/files/home/pico/hobbies"
    reg = HobbyRegistry(hobbies_dir)

    assert reg.has_hobby("gym") is True
    assert reg.has_hobby("trading") is True
    assert reg.has_hobby("coding") is True

    gym_md = reg.get_rulebook("gym")
    assert gym_md is not None
    assert "## 1. The Activity in One Line" in gym_md
    assert "## 4. Verdict Addenda" in gym_md
    assert "## 6. Safety Addenda" in gym_md
    assert "Instruments: STRONG" in gym_md


def test_trading_rulebook_constraints():
    hobbies_dir = "/data/data/com.termux/files/home/pico/hobbies"
    reg = HobbyRegistry(hobbies_dir)

    trading_md = reg.get_rulebook("trading")
    assert trading_md is not None
    # Trading explicitly forbids streaks
    assert "NO streak" in trading_md
    # Trading explicitly bans buy/sell advice
    assert "buy/sell/hold instructions banned mechanically" in trading_md


def test_hobby_maker_render():
    spec = HobbySpec(
        name="guitar",
        instruments_class=InstrumentClass.PARTIAL,
        one_line="Acoustic and electric guitar practice (chords, scales, songs).",
        session_definition="15+ minutes focused practice with tuner or metronome.",
        instruments_and_caps="Audio pitch/tuner data · self-reports. Caps: timing can be checked, tone nuance cannot.",
        verdict_addenda="Truth = minutes played, chord clean rate; Advice = ONE fingering cue.",
        safety_addenda="Finger pain / blister care → rest, never play through tendon strain.",
        voice_and_vocab="Fret, capo, tab, barre chord, strum pattern, metronome BPM.",
        outfit_spec="Guitar strap + pick in pocket.",
        btw_starter_bank=["guitar_type", "favorite_genre", "current_song_goal"],
        artifacts_charts_watchers="Song Repertoire List · BPM Speed Ladder.",
        examples_good=["Practiced 20 mins — clean F-barre transitions!"],
        examples_bad=["You played poorly because you didn't buy a $2000 Fender."]
    )

    rendered = HobbyMaker.render_markdown(spec)
    assert "# GUITAR.md" in rendered
    assert "## 1. The Activity in One Line" in rendered
    assert "## 7. Voice & Vocabulary" in rendered
    assert "Fret, capo, tab" in rendered
    assert "Finger pain / blister care" in rendered


def test_all_20_launch_hobbies_schema_compliance():
    """
    Validates that exactly 20 launch hobby rulebooks exist and conform
    100% to the 11-section schema from YOUR_FRIEND_FULL_SETUP.pdf (§19.3).
    """
    hobbies_dir = "/data/data/com.termux/files/home/pico/hobbies"
    reg = HobbyRegistry(hobbies_dir)

    assert len(reg.loaded_hobbies) == 20

    mandatory_sections = [
        "## 1. The Activity in One Line",
        "## 2. Session Definition",
        "## 3. Instruments + Claim Caps",
        "## 4. Verdict Addenda",
        "## 5. Special Formats",
        "## 6. Safety Addenda",
        "## 7. Voice & Vocabulary",
        "## 8. Outfit Spec",
        "## 9. BTW Starter Bank",
        "## 10. Artifacts, Charts & Watchers",
        "## 11. Examples"
    ]

    for hobby_name, content in reg.loaded_hobbies.items():
        # Check title and status
        assert "(v1.0" in content, f"Missing version in {hobby_name}"
        assert "Status: active" in content, f"Not active status in {hobby_name}"

        # Check instruments class
        assert any(inst in content for inst in ["Instruments: STRONG", "Instruments: PARTIAL", "Instruments: OBSERVATION-ONLY"]), \
            f"Missing valid instruments class in {hobby_name}"

        # Check all 11 sections
        for sec in mandatory_sections:
            assert sec in content, f"Missing section '{sec}' in {hobby_name}.md"

        # Check examples
        assert "✔ GOOD" in content, f"Missing GOOD example in {hobby_name}.md"
        assert "✘ BAD" in content, f"Missing BAD example in {hobby_name}.md"

