
Working app: http://typepod.l5.fyi/

[![OpenSSF Best Practices](https://www.bestpractices.dev/projects/11307/badge)](https://www.bestpractices.dev/projects/11307)

[Donate](https://optimistic.etherscan.io/address/0x17ac0B98b4B5a26E3a6e67DB20Cf2A38aAAEd5B6) - ivan-official.eth


## Key Event Recorder API Project

This project demonstrates a modern, asynchronous Python development workflow with a practical client-server application for recording keyboard event data. It is built upon the principles outlined in the "opinionated python introduction."

The project consists of:

* A FastAPI server with endpoints to generate short, unique session IDs and record validated keyboard event data to CSV files.

* A Typer-based CLI client that gets a session ID, sends a sample matrix of keyboard events, and displays the server's response.

* A single-page front-end.

Asynchronous code using async/await for high performance.

Dependency management with uv.

Code quality enforced by ruff, pylint, and pre-commit.

Automated testing with pytest, including unit tests and coverage reporting.

###Project Structure

```
.
├── .pre-commit-config.yaml
├── pyproject.toml
├── README.md
├── src
│   └── key_event_recorder
│       ├── __init__.py
│       ├── client.py
│       └── server.py
└── tests
    ├── __init__.py
    ├── test_client.py
    └── test_server.py
```

### Setup

Clone the repository and navigate into the project directory.

Create and activate a virtual environment using uv:

```
uv venv
source .venv/bin/activate
# On Windows: .venv\Scripts\activate
```

Install all project and development dependencies:

```
uv pip install -e ".[dev]"
```

Install the pre-commit git hooks:

```
pre-commit install
```

### Usage

Run the API server:
The server will create a collected_data/ directory in the project root to store CSV files.

```
uvicorn key_event_recorder.server:app --port 8000
```

In a new terminal, run the CLI client:
The client will automatically get a session ID and send a sample payload to the server.

```
python -m key_event_recorder.client run
```

Testing
Run all tests:

```
pytest
```

Run tests with a code coverage report:

```
pytest --cov=src/key_event_recorder --cov-report=term-missing
```
