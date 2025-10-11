"""Key Event Recorder FastAPI Server with Typer CLI for configuration."""

import asyncio
import random
import string
from pathlib import Path
from typing import Union

import aiofiles
import typer
import uvicorn
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

# --- CLI Application using Typer ---
cli_app = typer.Typer()

# --- Configuration (will be set by the Typer CLI before app startup) ---
# Initialize with placeholder paths. These are dynamically configured by the CLI.
DATA_DIR = Path(".")
FAILED_ATTEMPTS_DIR = Path(".")
SESSIONS_DIR = Path(".")

# --- FastAPI App ---
# This object is configured and then run by the Typer command.
app = FastAPI(title="Key Event Recorder API")

# --- Constants ---
TARGET_STRING = "a full moon illuminates the night sky"
CONGRATULATIONS_MESSAGE = (
    "Congratulations! You have successfully completed all samples for this session."
)
MAX_SAMPLES = 5
SESSION_ID_LENGTH = 6
SESSION_ID_CHARS = string.ascii_lowercase + string.digits


# --- Custom Exception Handling ---
class APIException(Exception):
    """Custom exception class for returning structured JSON errors."""

    def __init__(self, status_code: int, error_code: str, detail: str):
        self.status_code = status_code
        self.error_code = error_code
        self.detail = detail


@app.exception_handler(APIException)
async def api_exception_handler(request: Request, exc: APIException):
    """Handles APIExceptions and returns a standardized JSON error response."""
    return JSONResponse(
        status_code=exc.status_code,
        content={"error_code": exc.error_code, "detail": exc.detail},
    )


# --- Pydantic Models for Validation and Responses ---
class KeyEvent(BaseModel):
    key: str = Field(..., min_length=1)
    keyDownTimestamp: int = Field(..., gt=0)
    keyUpTimestamp: int = Field(..., gt=0)


class DataSample(BaseModel):
    session_id: str = Field(..., min_length=SESSION_ID_LENGTH, max_length=SESSION_ID_LENGTH)
    key_events: list[KeyEvent] = Field(..., min_length=1)


class RecordSuccessResponse(BaseModel):
    events_recorded_for_session: int


class SessionCompleteResponse(BaseModel):
    message: str


class ErrorResponse(BaseModel):
    error_code: str
    detail: str


# --- Helper Functions ---
def generate_unique_session_id() -> str:
    """Generates a short random ID and ensures it's not already in use."""
    while True:
        session_id = "".join(random.choices(SESSION_ID_CHARS, k=SESSION_ID_LENGTH))
        if not any(f.name.startswith(session_id) for f in SESSIONS_DIR.glob("*")):
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
    session_id = generate_unique_session_id()
    session_marker_file = SESSIONS_DIR / session_id
    try:
        async with aiofiles.open(session_marker_file, "w") as f:
            await f.write("")
    except IOError:
        raise APIException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            error_code="session_creation_failed",
            detail="Could not create session file.",
        )
    return {"session_id": session_id}


@app.post(
    "/record",
    response_model=Union[RecordSuccessResponse, SessionCompleteResponse],
    responses={
        400: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def record_data_sample(
    sample: DataSample,
) -> Union[RecordSuccessResponse, SessionCompleteResponse]:
    session_marker_file = SESSIONS_DIR / sample.session_id
    try:
        exists = await asyncio.to_thread(session_marker_file.exists)
    except Exception as e:
        import logging
        logging.exception(f'500! : {e}')
        raise APIException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            error_code="session_check_failed",
            detail="Error checking session existence.",
        )
    if not exists:
        raise APIException(
            status_code=status.HTTP_404_NOT_FOUND,
            error_code="session_not_found",
            detail="Session ID not found.",
        )

    new_rows = [[event.key, event.keyDownTimestamp, event.keyUpTimestamp] for event in sample.key_events]
    key_map = {"space": " ", "enter": ""}
    typed_string = "".join(
        [key_map.get(event.key.lower(), event.key) for event in sample.key_events]
    ).strip()

    if typed_string != TARGET_STRING:
        existing_failures = list(FAILED_ATTEMPTS_DIR.glob(f"{sample.session_id}_*.csv"))
        attempt_number = len(existing_failures) + 1
        failed_file = FAILED_ATTEMPTS_DIR / f"{sample.session_id}_{attempt_number}.csv"
        try:
            await write_csv_data(failed_file, new_rows)
        except IOError:
            raise APIException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                error_code="failed_attempt_log_failed",
                detail="Validation failed, and could not log the attempt.",
            )
        raise APIException(
            status_code=status.HTTP_400_BAD_REQUEST,
            error_code="validation_failed",
            detail=f"Typed string did not match target. Attempt {attempt_number} logged.",
        )

    try:
        existing_samples = list(DATA_DIR.glob(f"{sample.session_id}_*.csv"))
        if len(existing_samples) >= MAX_SAMPLES:
            raise APIException(
                status_code=status.HTTP_403_FORBIDDEN,
                error_code="session_complete",
                detail="This session is complete. No more samples can be recorded.",
            )
        sample_number = len(existing_samples) + 1
        session_file = DATA_DIR / f"{sample.session_id}_{sample_number}.csv"
        await write_csv_data(session_file, new_rows)
    except IOError as e:
        raise APIException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            error_code="file_operation_failed",
            detail=f"File operation failed: {e}",
        )

    if sample_number == MAX_SAMPLES:
        return SessionCompleteResponse(message=CONGRATULATIONS_MESSAGE)
    return RecordSuccessResponse(events_recorded_for_session=sample_number)


@cli_app.command()
def main(
    data_dir: Path = typer.Option(
        ".",
        "--data-dir",
        "-d",
        help="The root directory for storing session and data files.",
        resolve_path=True,
    ),
    host: str = typer.Option("127.0.0.1", help="Host to bind the server to."),
    port: int = typer.Option(8000, help="Port to bind the server to."),
):
    """
    Runs the Key Event Recorder FastAPI server.
    """
    global DATA_DIR, FAILED_ATTEMPTS_DIR, SESSIONS_DIR

    # Configure the global paths based on the CLI argument before the app starts
    DATA_DIR = data_dir / "collected_data"
    FAILED_ATTEMPTS_DIR = data_dir / "failed_attempts"
    SESSIONS_DIR = data_dir / "sessions"

    # Ensure directories exist
    typer.echo(f"Using data directory: {data_dir.resolve()}")
    DATA_DIR.mkdir(exist_ok=True)
    FAILED_ATTEMPTS_DIR.mkdir(exist_ok=True)
    SESSIONS_DIR.mkdir(exist_ok=True)

    typer.echo(f"Starting server on {host}:{port}")
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    cli_app()

