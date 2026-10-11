# Architecture

## Purpose and boundaries

BMis Desktop is a client for the separate BMis server repository. The desktop repository owns the user interface, desktop lifecycle, Python client/backend, and packaging. The BMis server repository remains authoritative for server behavior, commands, protocol, persistence, and networking.

## Current implementation

```text
React + TypeScript
       │ @tauri-apps/api/core invoke()
       ▼
Tauri command: python_request (Rust)
       │ one JSON request per line on stdin
       ▼
Python module: bmis_desktop.main
       │ one JSON response per line on stdout
       ▼
Tauri command result → React state/UI
```

### Frontend

- `frontend/src/App.tsx` renders the prototype UI.
- The current button invokes the Tauri command `python_request`.
- The current command payload is JSON containing `{"command":"ping"}`.
- In this prototype, `ping` means **Python backend health**, not a BMis server `PING` command.

### Tauri host

- `frontend/src-tauri/src/lib.rs` registers the command and holds `PythonProcessManager` in managed application state.
- `frontend/src-tauri/src/python_process.rs` starts the Python module and exchanges newline-delimited JSON through stdin/stdout.
- The manager currently assumes the development interpreter at `python/.venv/bin/python`. This is not a production packaging solution yet.
- Tauri's Rust layer should remain a thin host/IPC/process-management layer; business logic belongs in TypeScript or Python.

### Python backend and BMis client

- `python/bmis_desktop/main.py` is the JSON Lines IPC entry point.
- `python/bmis_desktop/bmis/client.py` and `protocol.py` implement the BMis TCP client and response parsing.
- The Python IPC entry point currently handles backend `ping` and invalid requests/commands. It does not yet expose the BMis client through the UI request handler.

## Target end-to-end architecture

```text
React UI
   │ Tauri IPC
   ▼
Tauri command / process manager
   │ JSON Lines over stdin/stdout
   ▼
Python backend
   │ validated operation / BMis client
   ▼
BMis TCP server
```

The target architecture is not considered complete until a test demonstrates a real command travelling from the UI through Tauri and Python to a running BMis server and back.

## IPC contract

- Transport: newline-delimited JSON over the Python child process's stdin/stdout.
- One request JSON object is sent per line.
- One response JSON object is expected per line.
- `stdout` is reserved for protocol responses. Diagnostics belong on `stderr` or the logging system.
- Invalid JSON should produce a structured error response and must not terminate the request loop.
- Requests must be validated before their fields are used.
- Keep the Python process long-lived instead of starting a new process per request.

## BMis TCP client

The Python BMis client uses the existing BMis TCP protocol, not HTTP. Its socket connection and response parser are separate from the desktop IPC protocol. Do not confuse a Python-backend health check with a successful BMis server connection.

## Security boundaries

- Keep the current frontend-to-Python transport on Tauri IPC; do not introduce a localhost HTTP listener without an explicit architecture decision.
- Keep Tauri capabilities minimal.
- Validate IPC input and return safe, structured errors.
- Never write credentials or secret values to logs.
- Treat the configured CSP as a security control that must be verified in development and packaged builds.

## Architecture decisions

| Decision | Current position |
|---|---|
| Desktop shell | Tauri 2 |
| UI | React + TypeScript + Vite |
| Application/backend logic | Python and TypeScript |
| Frontend-to-backend transport | Tauri IPC to a long-lived Python process |
| IPC wire format | Newline-delimited JSON |
| BMis transport | Existing BMis TCP protocol through Python client |
| Rust role | Thin Tauri host and process lifecycle |
| Python packaging | Not implemented; current `.venv` path is development-only |
