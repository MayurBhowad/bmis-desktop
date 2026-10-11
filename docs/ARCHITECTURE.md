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

- `frontend/src/App.tsx` renders the desktop UI and calls the Tauri command `python_request`.
- **Ping Python** sends `{"command":"ping"}`. That checks the Python process. It is not a BMis server command.
- **BMis server** sends `connect` with `host` and `port`, `status`, and `disconnect`.
- **Command console** sends `execute` with the raw BMis command in `request`, then shows the JSON response, including `result`.

### Tauri host

- `frontend/src-tauri/src/lib.rs` registers the command and holds `PythonProcessManager` in managed application state.
- `frontend/src-tauri/src/python_process.rs` starts the Python module and exchanges newline-delimited JSON through stdin/stdout.
- The manager currently assumes the development interpreter at `python/.venv/bin/python`. This is not a production packaging solution yet.
- Tauri's Rust layer should remain a thin host/IPC/process-management layer; business logic belongs in TypeScript or Python.

### Python backend and BMis client

- `python/bmis_desktop/main.py` is the JSON Lines IPC entry point. One `BackendSession` lives for the process and closes its socket when stdin ends.
- `python/bmis_desktop/session.py` validates desktop operations and keeps a single `BMisClient` across requests.
- `python/bmis_desktop/bmis/client.py` and `protocol.py` implement the BMis TCP client and response parsing.
- Desktop operations are `ping`, `connect`, `status`, `execute`, and `disconnect`. `ping` checks the Python process. `execute` sends the raw BMis command in `request`. The UI sends all five operations.

## Verified BMis commands

The live acceptance check uses a BMis server at `127.0.0.1:6379`:

| Command | Server result |
|---|---|
| `SET desktop_test Mayur` | `OK` |
| `GET desktop_test` | `Mayur` |

`python/tests/test_session.py` records that check as `test_session_set_and_get_against_real_bmis_server`. The command console displays those decoded results. A separate unit test feeds a local socket the simple string `PONG` for the raw command `PING`; that socket is not the BMis server.

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

The first command path is in place: the UI connects and sends a command through Tauri and Python to a running BMis server, and the integration test records the server response. Saved connections, the key browser, and the data viewer remain later work.

## IPC contract

- Transport: newline-delimited JSON over the Python child process's stdin/stdout.
- One request JSON object is sent per line.
- One response JSON object is expected per line.
- `stdout` is reserved for protocol responses. Diagnostics belong on `stderr` or the logging system.
- Invalid JSON should produce a structured error response and must not terminate the request loop.
- Requests must be validated before their fields are used.
- Keep the Python process long-lived instead of starting a new process per request.
- Success responses use `"status": true`. Failures use `"status": false` and `"error"`, with no traceback.
- `connect` requires `host` and a TCP `port` from 1 through 65535. It reports success only after `BMisClient.connect()` succeeds.
- `execute` requires a non-empty `request` with no CR or LF. The decoded BMis value is returned as `result`.

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
