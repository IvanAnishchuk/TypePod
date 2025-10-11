"""Key Event Recorder FastAPI Server."""

import asyncio
import random
import string
from pathlib import Path
from typing import Annotated, Union

import aiofiles
import typer
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# --- CLI and App Setup ---
cli_app = typer.Typer()
app = FastAPI(title="Key Event Recorder API")

# --- CORS Middleware for Local Testing ---
# This allows a frontend (if served from a different origin) to communicate with the API.
# WARNING: This is a permissive policy for development. For production, you should
# restrict the origins to your actual frontend domain.
origins = [
    "http://localhost",
    "http://localhost:8080",
    "http://127.0.0.1",
    "http://127.0.0.1:8080",
    #"null", # Important for opening local file://index.html
    #None,
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"], # Allows all methods (GET, POST, etc.)
    allow_headers=["*"], # Allows all headers
)



# --- Global State and Constants (to be configured by CLI) ---
class AppState:
    """A simple class to hold configurable application state."""

    TARGET_STRING = "a full moon illuminates the night sky"
    CONGRATULATIONS_MESSAGE = (
        "Congratulations! You have successfully completed all samples for this session."
    )
    MAX_SAMPLES = 5
    DATA_DIR = Path("collected_data")
    FAILED_ATTEMPTS_DIR = Path("failed_attempts")
    SESSIONS_DIR = Path("sessions")
    SESSION_ID_LENGTH = 6
    SESSION_ID_CHARS = string.ascii_lowercase + string.digits


state = AppState()


# --- Custom Exceptions ---
class APIError(HTTPException):
    """Custom base exception to include a machine-readable error code."""

    def __init__(self, status_code: int, error_code: str, detail: str):
        super().__init__(status_code=status_code, detail={"error_code": error_code, "detail": detail})


# --- Pydantic Models for Validation ---
class KeyEvent(BaseModel):
    """A single key press event."""

    key: str = Field(..., min_length=1, description="The key that was pressed.")
    keyDownTimestamp: int = Field(..., gt=0, description="Timestamp of key down event (nanoseconds).")
    keyUpTimestamp: int = Field(..., gt=0, description="Timestamp of key up event (nanoseconds).")


class DataSample(BaseModel):
    """A data sample containing a session ID and a matrix of key events."""

    session_id: str
    key_events: list[KeyEvent] = Field(..., min_length=1)


class RecordSuccessResponse(BaseModel):
    """Standard response for a successfully recorded sample."""

    events_recorded_for_session: int


class SessionCompleteResponse(BaseModel):
    """Special response for the final successful sample."""

    message: str


# --- Helper Functions ---
def generate_unique_session_id() -> str:
    """Generates a short random ID and ensures it's not already in use."""
    while True:
        session_id = "".join(random.choices(state.SESSION_ID_CHARS, k=state.SESSION_ID_LENGTH))
        success_exists = any(f.name.startswith(session_id) for f in state.DATA_DIR.glob("*.csv"))
        failed_exists = any(f.name.startswith(session_id) for f in state.FAILED_ATTEMPTS_DIR.glob("*.csv"))
        if not success_exists and not failed_exists:
            return session_id


async def write_csv_data(file_path: Path, rows: list[list]):
    """Asynchronously writes rows to a new CSV file with a header."""
    header = "key,keyDownTimestamp,keyUpTimestamp\n"
    lines_to_write = [",".join(map(str, row)) + "\n" for row in rows]
    async with aiofiles.open(file_path, mode="w", newline="", encoding="utf-8") as f:
        await f.write(header)
        await f.writelines(lines_to_write)


# --- API Endpoints ---
@app.get("/session", response_model=dict[str, str])
async def get_session_id() -> dict[str, str]:
    """Generates a new unique session ID and records it by creating a marker file."""
    session_id = generate_unique_session_id()
    session_marker_file = state.SESSIONS_DIR / session_id
    try:
        async with aiofiles.open(session_marker_file, "w") as f:
            await f.write("")
    except IOError:
        raise APIError(500, "session_creation_failed", "Could not create session file.")
    return {"session_id": session_id}


@app.post(
    "/record",
    response_model=Union[RecordSuccessResponse, SessionCompleteResponse],
)
async def record_data_sample(
    sample: DataSample,
) -> Union[RecordSuccessResponse, SessionCompleteResponse]:
    """Receives, validates, and records key event data. Requires a valid session ID."""
    session_marker_file = state.SESSIONS_DIR / sample.session_id
    try:
        exists = await asyncio.to_thread(session_marker_file.exists)
    except Exception:
        raise APIError(500, "internal_error", "Error checking session existence.")
    if not exists:
        raise APIError(404, "session_not_found", "Session ID not found.")

    new_rows = [[event.key, event.keyDownTimestamp, event.keyUpTimestamp] for event in sample.key_events]
    key_map = {"space": " ", "enter": ""}
    typed_keys = [key_map.get(event.key.lower(), event.key) for event in sample.key_events]
    typed_string = "".join(typed_keys).strip()

    if typed_string != state.TARGET_STRING:
        existing_failures = list(state.FAILED_ATTEMPTS_DIR.glob(f"{sample.session_id}_*.csv"))
        attempt_number = len(existing_failures) + 1
        failed_file = state.FAILED_ATTEMPTS_DIR / f"{sample.session_id}_{attempt_number}.csv"
        try:
            await write_csv_data(failed_file, new_rows)
        except IOError:
            raise APIError(500, "log_write_failed", "Validation failed, and could not log the attempt.")
        raise APIError(
            400,
            "validation_failed",
            f"Typed string did not match target. Attempt {attempt_number} logged.",
        )

    try:
        existing_samples = list(state.DATA_DIR.glob(f"{sample.session_id}_*.csv"))
        if len(existing_samples) >= state.MAX_SAMPLES:
            raise APIError(403, "session_complete", "This session is complete.")
        sample_number = len(existing_samples) + 1
        session_file = state.DATA_DIR / f"{sample.session_id}_{sample_number}.csv"
        await write_csv_data(session_file, new_rows)
    except IOError as e:
        raise APIError(500, "file_operation_failed", f"File operation failed: {e}")

    if sample_number == state.MAX_SAMPLES:
        return SessionCompleteResponse(message=state.CONGRATULATIONS_MESSAGE)
    return RecordSuccessResponse(events_recorded_for_session=sample_number)


@cli_app.command()
def main(
    data_dir: Annotated[
        Path,
        typer.Option(
            help="The root directory to store session and data files.",
            dir_okay=True,
            file_okay=False,
            resolve_path=True,
        ),
    ] = Path("."),
    host: Annotated[str, typer.Option(help="The host to bind the server to.")] = "127.0.0.1",
    port: Annotated[int, typer.Option(help="The port to run the server on.")] = 8000,
):
    """Runs the Key Event Recorder FastAPI server."""
    typer.secho(f"Starting server...", fg=typer.colors.GREEN)
    typer.secho(f"Data directory: {data_dir.absolute()}", fg=typer.colors.YELLOW)

    # Configure global state with CLI parameters
    state.DATA_DIR = data_dir / "collected_data"
    state.FAILED_ATTEMPTS_DIR = data_dir / "failed_attempts"
    state.SESSIONS_DIR = data_dir / "sessions"

    # Create directories if they don't exist
    state.DATA_DIR.mkdir(exist_ok=True)
    state.FAILED_ATTEMPTS_DIR.mkdir(exist_ok=True)
    state.SESSIONS_DIR.mkdir(exist_ok=True)

    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    cli_app()

