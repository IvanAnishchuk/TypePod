"""Fixtures for the Key Event Recorder test suite."""

import random
import time
from pathlib import Path

import pytest

# Import the app and constants to be used in fixtures
from key_event_recorder.server import app

TARGET_STRING = "a full moon illuminates the night sky"


@pytest.fixture
def sample_data_correct() -> dict:
    """
    Provides a valid data sample where the key events match the TARGET_STRING.
    The session_id is a placeholder and should be replaced by the test.
    """
    events = []
    base_time = time.time_ns()
    for char in TARGET_STRING:
        key = "space" if char == " " else char
        keydown_time = base_time + random.randint(50_000_000, 150_000_000)
        keyup_time = keydown_time + random.randint(30_000_000, 80_000_000)
        events.append(
            {
                "key": key,
                "keyDownTimestamp": keydown_time,
                "keyUpTimestamp": keyup_time,
            }
        )
        base_time = keyup_time

    return {"session_id": "placeholder_id", "key_events": events}


@pytest.fixture
def sample_data_incorrect() -> dict:
    """
    Provides an invalid data sample where the key events do not match.
    """
    incorrect_string = "this is not the correct string"
    events = []
    base_time = time.time_ns()
    for char in incorrect_string:
        key = "space" if char == " " else char
        keydown_time = base_time + random.randint(50_000_000, 150_000_000)
        keyup_time = keydown_time + random.randint(30_000_000, 80_000_000)
        events.append(
            {
                "key": key,
                "keyDownTimestamp": keydown_time,
                "keyUpTimestamp": keyup_time,
            }
        )
        base_time = keyup_time

    return {"session_id": "placeholder_id", "key_events": events}


@pytest.fixture
def test_data_dir(tmp_path: Path) -> Path:
    """
    Creates a temporary root data directory with subdirectories for each test.
    """
    root_dir = tmp_path / "test_server_data"
    (root_dir / "collected_data").mkdir(parents=True)
    (root_dir / "failed_attempts").mkdir()
    (root_dir / "sessions").mkdir()
    return root_dir


@pytest.fixture
def configured_app(test_data_dir: Path, monkeypatch):
    """
    A fixture that configures the app to use a temporary data directory for tests.

    It uses monkeypatch to temporarily change the global path variables
    in the server module.
    """
    monkeypatch.setattr(
        "key_event_recorder.server.state.DATA_DIR", test_data_dir / "collected_data"
    )
    monkeypatch.setattr(
        "key_event_recorder.server.state.FAILED_ATTEMPTS_DIR",
        test_data_dir / "failed_attempts",
    )
    monkeypatch.setattr(
        "key_event_recorder.server.state.SESSIONS_DIR", test_data_dir / "sessions"
    )
    return app
