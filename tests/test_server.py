"""Tests for the FastAPI server, ensuring test isolation with temporary directories."""

import asyncio
from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient

# Import constants used for test logic
from key_event_recorder.server import state

# Mark all tests in this module as async
pytestmark = pytest.mark.asyncio


async def test_get_session_id(configured_app, test_data_dir):
    """Test if the /session endpoint returns a session ID and creates a marker file."""
    async with AsyncClient(transport=ASGITransport(app=configured_app), base_url="http://test") as client:
        response = await client.get("/session")

    assert response.status_code == 200
    data = response.json()
    assert "session_id" in data
    session_id = data["session_id"]
    assert len(session_id) == state.SESSION_ID_LENGTH

    # Verify that the session marker file was created in the temporary directory
    session_marker_file = test_data_dir / "sessions" / session_id
    assert await asyncio.to_thread(session_marker_file.is_file)


async def test_get_session_id_io_error(configured_app, monkeypatch):
    """Test server's response when creating a session file fails with an IOError."""
    with patch("aiofiles.open", side_effect=IOError("Disk full")):
        async with AsyncClient(transport=ASGITransport(app=configured_app), base_url="http://test") as client:
            response = await client.get("/session")

    assert response.status_code == 500
    error_data = response.json()["detail"]
    assert error_data["error_code"] == "session_creation_failed"
    assert "Could not create session file" in error_data["detail"]


async def test_record_data_sample_success_and_completion(configured_app, test_data_dir, sample_data_correct):
    """Test the full lifecycle: 5 successful recordings, then a 403 error."""
    async with AsyncClient(transport=ASGITransport(app=configured_app), base_url="http://test") as client:
        get_response = await client.get("/session")
        assert get_response.status_code == 200
        session_id = get_response.json()["session_id"]
        sample_data_correct["session_id"] = session_id

        for i in range(1, state.MAX_SAMPLES + 1):
            response = await client.post("/record", json=sample_data_correct)
            if i < state.MAX_SAMPLES:
                assert response.status_code == 200
                assert response.json() == {"events_recorded_for_session": i}
            else:
                assert response.status_code == 200
                assert response.json() == {"message": state.CONGRATULATIONS_MESSAGE}

        data_files = list((test_data_dir / "collected_data").glob(f"{session_id}_*.csv"))
        assert len(data_files) == state.MAX_SAMPLES

        # Test one more attempt after completion
        final_response = await client.post("/record", json=sample_data_correct)
        assert final_response.status_code == 403
        error_data = final_response.json()["detail"]
        assert error_data["error_code"] == "session_complete"


async def test_record_data_sample_invalid_session(configured_app, sample_data_correct):
    """Test recording with a session ID that was never created."""
    sample_data_correct["session_id"] = "invald"
    async with AsyncClient(transport=ASGITransport(app=configured_app), base_url="http://test") as client:
        response = await client.post("/record", json=sample_data_correct)

    print(response)
    print(response.__dict__)
    assert response.status_code == 404
    error_data = response.json()["detail"]
    assert error_data["error_code"] == "session_not_found"


async def test_record_data_sample_validation_fail(configured_app, test_data_dir, sample_data_incorrect):
    """Test a failed validation creates a log in the correct temporary directory."""
    async with AsyncClient(transport=ASGITransport(app=configured_app), base_url="http://test") as client:
        get_response = await client.get("/session")
        session_id = get_response.json()["session_id"]
        sample_data_incorrect["session_id"] = session_id
        response = await client.post("/record", json=sample_data_incorrect)

    assert response.status_code == 400
    error_data = response.json()["detail"]
    assert error_data["error_code"] == "validation_failed"
    assert "Attempt 1 logged" in error_data["detail"]

    failed_files = list((test_data_dir / "failed_attempts").glob(f"{session_id}_*.csv"))
    assert len(failed_files) == 1

    # Ensure no data was saved to the success directory
    data_files = list((test_data_dir / "collected_data").glob(f"{session_id}_*.csv"))
    assert len(data_files) == 0


async def test_record_data_failed_attempt_io_error(configured_app, sample_data_incorrect):
    """Test server's response when logging a failed attempt fails with an IOError."""
    async with AsyncClient(transport=ASGITransport(app=configured_app), base_url="http://test") as client:
        get_response = await client.get("/session")
        session_id = get_response.json()["session_id"]
        sample_data_incorrect["session_id"] = session_id

        # Mock the file write operation to fail
        with patch("aiofiles.open", side_effect=IOError("Permission denied")):
            response = await client.post("/record", json=sample_data_incorrect)

    assert response.status_code == 500
    error_data = response.json()["detail"]
    assert error_data["error_code"] == "log_write_failed"
    assert "could not log the attempt" in error_data["detail"]


async def test_record_data_success_io_error(configured_app, sample_data_correct):
    """Test server's response when saving a successful sample fails with an IOError."""
    async with AsyncClient(transport=ASGITransport(app=configured_app), base_url="http://test") as client:
        get_response = await client.get("/session")
        session_id = get_response.json()["session_id"]
        sample_data_correct["session_id"] = session_id

        # Mock the file write operation to fail
        with patch("aiofiles.open", side_effect=IOError("Disk full")):
            response = await client.post("/record", json=sample_data_correct)

    assert response.status_code == 500
    error_data = response.json()["detail"]
    assert error_data["error_code"] == "file_operation_failed"
    assert "File operation failed" in error_data["detail"]


async def test_session_check_internal_error(configured_app, sample_data_correct):
    """Test server's response when checking for a session file raises an unexpected error."""
    async with AsyncClient(transport=ASGITransport(app=configured_app), base_url="http://test") as client:
        get_response = await client.get("/session")
        session_id = get_response.json()["session_id"]
        sample_data_correct["session_id"] = session_id

        # Mock the asyncio.to_thread call to simulate an unexpected internal error
        with patch("asyncio.to_thread", side_effect=Exception("Unexpected error")):
            response = await client.post("/record", json=sample_data_correct)

    assert response.status_code == 500
    error_data = response.json()["detail"]
    assert error_data["error_code"] == "internal_error"
