"""Typer CLI Client for the Key Event Recorder API."""

import asyncio
import random
import time

import httpx
import typer
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn

# --- Constants and Setup ---
TARGET_STRING = "a full moon illuminates the night sky"
app = typer.Typer()
console = Console()


# --- Helper Functions ---
def generate_key_events(target: str) -> list[dict]:
    """Generates a list of simulated key event dictionaries for a given string."""
    events = []
    base_time = time.time_ns()
    for char in target:
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
    return events


async def get_session(client: httpx.AsyncClient, base_url: str) -> str:
    """Retrieves a new session ID from the server."""
    console.print("Requesting new session ID...")
    response = await client.get(f"{base_url}/session")
    response.raise_for_status()
    session_id = response.json()["session_id"]
    console.print(f"[bold green]Successfully retrieved session ID:[/] {session_id}")
    return session_id


async def post_data(client: httpx.AsyncClient, session_id: str, base_url: str):
    """Generates and posts one data sample to the server."""
    key_events = generate_key_events(TARGET_STRING)
    data_sample = {"session_id": session_id, "key_events": key_events}
    response = await client.post(f"{base_url}/record", json=data_sample, timeout=10.0)
    response.raise_for_status()
    return response.json()


# --- Typer Commands ---
@app.command()
def record(
    count: int = typer.Option(5, "--count", "-c", help="Number of samples to record."),
    base_url: str = typer.Option(
        "http://127.0.0.1:8000", "--base-url", help="Base URL of the server."
    ),
):
    """
    Starts a session and records a specified number of data samples.
    """

    async def main():
        """Asynchronous main function to run the client logic."""
        try:
            async with httpx.AsyncClient() as client:
                session_id = await get_session(client, base_url)
                console.line()

                for i in range(1, count + 1):
                    with Progress(
                        SpinnerColumn(),
                        TextColumn("[progress.description]{task.description}"),
                        transient=True,
                    ) as progress:
                        progress.add_task(description=f"Attempt {i}/{count}...", total=None)
                        post_response = await post_data(client, session_id, base_url)

                    if "message" in post_response:
                        console.print(
                            Panel(
                                f"[bold green]Success![/] {post_response['message']}",
                                title=f"Attempt {i}/{count}",
                                border_style="green",
                            )
                        )
                        console.print("\n[bold]Session complete.[/bold]")
                        return
                    else:
                        recorded_count = post_response.get("events_recorded_for_session", "N/A")
                        console.print(
                            Panel(
                                f"[green]Success![/] Recorded samples for session {session_id}: {recorded_count}",
                                title=f"Attempt {i}/{count}",
                                border_style="green",
                            )
                        )
                    await asyncio.sleep(1)

        except httpx.ConnectError as e:
            console.print(f"[bold red]Connection Error:[/] Could not connect to the server at {base_url}.")
            console.print(f"Please ensure the server is running. Details: {e}")
            raise typer.Exit(code=1)
        except httpx.HTTPStatusError as e:
            console.print(f"[bold red]Error:[/] Failed to record data.")
            error_json = e.response.json()
            error_code = error_json.get("error_code", "unknown_error")
            detail = error_json.get("detail", e.response.text)
            console.print(f"Server responded with {e.response.status_code} {e.response.reason_phrase}")
            console.print(f"Error Code: [bold yellow]{error_code}[/]")
            console.print(f"Detail: {detail}")
            raise typer.Exit(code=1)
        except Exception as e:
            console.print(f"[bold red]An unexpected error occurred:[/] {e}")
            raise typer.Exit(code=1)

    asyncio.run(main())

    console.print("[bold green]Done![/]")
    raise typer.Exit(code=0)


if __name__ == "__main__":
    app()

