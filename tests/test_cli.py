"""
Smoke tests for Pico Interactive CLI.
Verifies that onboarding, initialization, and basic commands execute without NameErrors or crashes.
"""

import sys
from io import StringIO
from unittest.mock import patch
import pytest
from pico.cli import run_interactive_cli


def test_cli_fast_path_onboarding_and_exit():
    # Simulate piped inputs for: name, nickname, age, languages, category, and then /exit
    simulated_inputs = [
        "Ayush",             # Name
        "Ayush",             # Nickname
        "24",                # Age
        "English, Hinglish", # Languages
        "1",                 # Gym & Fitness category
        "/tokens",           # Check tokens
        "/exit"              # Exit CLI
    ]

    with patch("builtins.input", side_effect=simulated_inputs):
        with patch("sys.stdout", new_callable=StringIO) as fake_out:
            run_interactive_cli()
            output = fake_out.getvalue()

    assert "WELCOME TO PICO (YOUR FRIEND)" in output
    assert "PICO IS ALIVE!" in output
    assert "Tokens Page" in output
    assert "Bye for now" in output
