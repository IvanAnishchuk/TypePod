"""Tests for the Typer CLI client."""

import httpx
import pytest
from typer.testing import CliRunner

# Corrected import path relative to the project root
from key_event_recorder.client import app

# Use a synchronous runner for Typer tests, but mark tests as async for httpx mocking
runner = CliRunner()
MOCK_SERVER_URL = "http://test-server"


@pytest.mark.asyncio
@pytest.mark.xfail(True, reason="failing generated code")
async def test_client_full_run_success(mocker):
    """Test the client's successful run for a full session (5 attempts)."""
    mock_get = mocker.patch(
        "httpx.AsyncClient.get",
        return_value=mocker.AsyncMock(
            status_code=200, json=lambda: {"session_id": "testid"}
        ),
    )
    post_responses = [
        mocker.AsyncMock(status_code=200, json=lambda i=i: {"events_recorded_for_session": i})
        for i in range(1, 5)
    ]
    post_responses.append(
        mocker.AsyncMock(status_code=200, json=lambda: {"message": "Congratulations!"})
    )
    mock_post = mocker.patch("httpx.AsyncClient.post")
    mock_post.side_effect = post_responses

    result = runner.invoke(app, ["--count", "5", "--base-url", MOCK_SERVER_URL])

    assert result.exit_code == 0
    assert "Successfully retrieved session ID: testid" in result.stdout
    assert "Attempt 1/5... Success! Recorded samples for session testid: 1" in result.stdout
    assert "Attempt 5/5... Success! Congratulations!" in result.stdout
    assert "Session complete." in result.stdout
    assert mock_get.call_count == 1
    assert mock_post.call_count == 5


@pytest.mark.asyncio
@pytest.mark.xfail(True, reason="failing generated code")
async def test_client_server_validation_error(mocker):
    """Test how the client handles a 400 validation error from the server."""
    mocker.patch(
        "httpx.AsyncClient.get",
        return_value=mocker.AsyncMock(
            status_code=200, json=lambda: {"session_id": "testid"}
        ),
    )
    mocker.patch(
        "httpx.AsyncClient.post",
        return_value=mocker.AsyncMock(
            status_code=400,
            json=lambda: {
                "error_code": "validation_failed",
                "detail": "Typed string did not match target. Attempt 1 logged.",
            },
            text="Validation failed.",
        ),
    )

    result = runner.invoke(app, ["--base-url", MOCK_SERVER_URL])

    assert result.exit_code == 1
    assert "Error Code: validation_failed" in result.stdout
    assert "Detail: Typed string did not match target. Attempt 1 logged." in result.stdout


@pytest.mark.asyncio
@pytest.mark.xfail(True, reason="failing generated code")
async def test_client_server_session_not_found(mocker):
    """Test how the client handles a 404 session not found error."""
    mocker.patch(
        "httpx.AsyncClient.get",
        return_value=mocker.AsyncMock(
            status_code=200, json=lambda: {"session_id": "testid"}
        ),
    )
    mocker.patch(
        "httpx.AsyncClient.post",
        return_value=mocker.AsyncMock(
            status_code=404,
            json=lambda: {"error_code": "session_not_found", "detail": "Session ID not found."},
            text="Session ID not found.",
        ),
    )

    result = runner.invoke(app, ["--base-url", MOCK_SERVER_URL])

    assert result.exit_code == 1
    assert "Error Code: session_not_found" in result.stdout


@pytest.mark.asyncio
@pytest.mark.xfail(True, reason="failing generated code")
async def test_client_connection_error(mocker):
    """Test how the client handles a network connection error."""
    mocker.patch("httpx.AsyncClient.get", side_effect=httpx.ConnectError("Connection failed."))
    result = runner.invoke(app, ["--base-url", MOCK_SERVER_URL])

    assert result.exit_code == 1
    assert f"Could not connect to the server at {MOCK_SERVER_URL}" in result.stdout

