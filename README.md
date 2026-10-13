# BMis Desktop

BMis Desktop is a desktop client prototype for the existing **BMis** server. It is a separate project: it does not reimplement the server or own the server's protocol and data-storage behavior.

> **Current status:** the UI checks the Python backend, saves named connection profiles, connects to one BMis server, sends a command, and shows the server response. Choosing a profile fills the host and port and does not connect by itself. **Ping Python** checks the Python process. The live server check is `SET desktop_test Mayur` → `OK` and `GET desktop_test` → `Mayur` on `127.0.0.1:6379`.

## Current stack

- **Desktop shell:** Tauri 2 / Rust
- **Frontend:** React, TypeScript, Vite
- **Python backend:** JSON Lines over the child process's stdin/stdout
- **BMis client:** Python TCP client and response parser
- **Tests:** pytest and Rust unit tests

The current IPC path is:

```text
React UI
   │ Tauri invoke("python_request")
   ▼
Tauri command (Rust)
   │ JSON request line over stdin
   ▼
Long-running Python process
   │ JSON response line over stdout
   ▼
Tauri command → React UI
```

The BMis command path is:

```text
React UI → Tauri IPC → Python backend → BMis TCP client → BMis server
```

See [Architecture](docs/ARCHITECTURE.md) for the IPC contract and the recorded server commands.

## Repository layout

```text
.
├── frontend/                    # React + TypeScript + Vite
│   └── src-tauri/                # Tauri/Rust host and configuration
├── python/
│   ├── bmis_desktop/              # Python IPC entry point and BMis client
│   ├── tests/                     # Python tests
│   └── pyproject.toml
├── scripts/                       # Development helpers
├── docs/
│   ├── ARCHITECTURE.md
│   ├── DEVELOPMENT.md
│   └── USER_GUIDE.md
├── .github/                       # CI and contribution templates
├── BMis-Desktop-PLAN.md           # Product/engineering roadmap
├── CONTRIBUTING.md
├── SECURITY.md
├── CHANGELOG.md
└── README.md
```

## Development setup

Prerequisites: Python 3.12+, Node.js compatible with the Vite version in `frontend/package.json`, npm, Rust stable/Cargo, and the native Tauri dependencies for your operating system.

### 1. Set up Python

From the repository root:

```bash
python3 -m venv python/.venv
python/.venv/bin/python -m pip install --upgrade pip
python/.venv/bin/python -m pip install pytest
```

The app currently launches `python/.venv/bin/python` on Linux. This is a development-only assumption; packaged Python sidecar support is still pending.

### 2. Set up the frontend

```bash
cd frontend
npm ci
```

### 3. Run the desktop app

From `frontend/`:

```bash
npm run tauri dev
```

Use **Ping Python** to verify that the UI can communicate with the Python process. A successful response looks like:

```json
{"status": true, "message": "BMis python backend is running"}
```

That confirms Python IPC. To reach BMis, start a server, click **Connect** (defaults: `127.0.0.1` and `6379`), then run a command such as `SET desktop_test Mayur` and `GET desktop_test`. See the [user guide](docs/USER_GUIDE.md).

## Tests and checks

Run commands from the repository root unless stated otherwise.

### Python tests

```bash
python/.venv/bin/python -m pytest -c python/pyproject.toml -q
```

Integration tests requiring a running BMis server are excluded from the default suite. To run them explicitly, start the compatible BMis server first, then run:

```bash
python/.venv/bin/python -m pytest -c python/pyproject.toml -q -m integration
```

### Frontend production build

```bash
cd frontend
npm ci
npm run build
```

### Rust tests

Create `python/.venv` first because the current Rust tests launch the Python backend through that path. Then run:

```bash
cargo test --manifest-path frontend/src-tauri/Cargo.toml
```

Linux builds/tests may require Tauri's native system packages. See [Development](docs/DEVELOPMENT.md).

## Documentation

- [Architecture and current implementation boundaries](docs/ARCHITECTURE.md)
- [Development setup and test commands](docs/DEVELOPMENT.md)
- [User guide for the current prototype](docs/USER_GUIDE.md)
- [Product and engineering roadmap](BMis-Desktop-PLAN.md)
- [Contributing](CONTRIBUTING.md)
- [Security reporting and practices](SECURITY.md)
- [Changelog](CHANGELOG.md)

## Project workflow

Work incrementally through GitHub issues:

1. Issue and acceptance criteria
2. Design/approach
3. Implementation
4. Unit tests and relevant integration tests
5. Manual verification
6. Review the diff
7. Commit and push
8. Open/update the pull request and close the issue when merged

Use `local-dev` for local work if following the repository's three-branch workflow, merge into `dev`, push `dev`, and open a PR from `dev` to `main`. Do not push `local-dev` to the remote.

## Scope and limitations

Not yet complete: production Python packaging, saved-connection manager, key browser, data viewer, and production release validation. One live connection and a command console are implemented. Track the rest against `BMis-Desktop-PLAN.md`; do not describe planned functionality as implemented.
