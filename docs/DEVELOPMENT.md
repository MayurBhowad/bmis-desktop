# Development Guide

## Prerequisites

- Python 3.12+
- Node.js and npm versions compatible with `frontend/package.json`
- Rust stable and Cargo
- Tauri native dependencies for your OS
- A running BMis server only when running tests marked `integration`

## First-time setup

Run from the repository root.

### Python environment

```bash
python3 -m venv python/.venv
python/.venv/bin/python -m pip install --upgrade pip
python/.venv/bin/python -m pip install pytest
```

Install Ruff too if you want lint checks:

```bash
python/.venv/bin/python -m pip install ruff
```

### Frontend dependencies

```bash
cd frontend
npm ci
```

## Run the desktop app

From `frontend/`:

```bash
npm run tauri dev
```

The window has three areas:

- **Ping Python** checks the Python process and the IPC loop. It does not open a BMis connection.
- **BMis server** connects to the host and port in the form. The defaults are `127.0.0.1` and `6379`. **Refresh Status** reads the current connection. **Disconnect** closes that socket.
- **Command console** is available while the server status is connected. It sends the entered text as one BMis command.

Start a compatible BMis server before using Connect. The recorded live commands are `SET desktop_test Mayur`, which returns `OK`, and `GET desktop_test`, which returns `Mayur`.

## Test commands

### Python

From the repository root:

```bash
python/.venv/bin/python -m pytest -c python/pyproject.toml -q
```

Integration tests require a compatible BMis server to be running:

```bash
python/.venv/bin/python -m pytest -c python/pyproject.toml -q -m integration
```

Do not run the integration suite and interpret a missing-server failure as a unit-test regression. Start the server first and verify its address/port.

### Frontend

```bash
cd frontend
npm run build
npm run lint
```

`npm run build` includes TypeScript compilation through `tsc -b`.

### Rust/Tauri

Ensure `python/.venv/bin/python` exists before running the Rust tests; the current process manager uses that development path.

```bash
cargo test --manifest-path frontend/src-tauri/Cargo.toml
```

Format-checking the entire Tauri crate may report existing formatting differences in files unrelated to a change. Avoid committing unrelated formatter churn; format the file you changed and review the diff.

## Linux Tauri dependencies

On Ubuntu/Debian-based development machines, Tauri may require native packages such as:

```bash
sudo apt-get update
sudo apt-get install -y \
  build-essential curl wget file \
  libwebkit2gtk-4.1-dev \
  libxdo-dev libssl-dev librsvg2-dev
```

Follow the official Tauri prerequisites for your OS and installed Tauri version if a package name is unavailable.

## Debugging

- Frontend UI/build errors: inspect Vite/TypeScript output.
- Tauri command errors: inspect the Rust error returned by `invoke`.
- Python diagnostics: write diagnostic output to `stderr`, not `stdout`, because stdout carries JSON Lines responses.
- Backend does not start: confirm `python/.venv/bin/python` exists and `python/bmis_desktop/main.py` is importable from the `python/` working directory.
- BMis TCP tests fail: ensure the existing BMis server is running and compatible with the tested commands.

## Change workflow

Use a GitHub issue with explicit acceptance criteria. Implement one issue at a time, add tests for behavior, run relevant checks, manually verify UI changes, inspect `git diff`, then commit and push. Keep changes scoped to the issue.
