# BMis Desktop

Cross-platform desktop client for the existing **BMis** server.

BMis Desktop is a **client**, not a reimplementation of BMis. The [BMis](../BMis) repository remains the source of truth for the server, protocol, persistence, and networking. This project owns the desktop UI, connection management, key browsing, data inspection, command console, packaging, and the bundled Python backend.

> BMis Desktop is a client for BMis, not a replacement for BMis.

## Goals

- Production-quality desktop client for local and remote BMis instances
- Graphical key browser, data inspection/editing, and command console
- Clean separation of frontend, desktop shell, and Python backend
- Bundled Python runtime — end users do **not** install Python, Node.js, or other toolchains
- Linux first, then Windows and macOS
- Incremental delivery with tests and clear acceptance criteria

### Non-goals

- Reimplementing or modifying the BMis server for client convenience
- Requiring users to install development tools
- AI features, cloud sync, generic DB tooling, or unrelated productivity features before the core client is stable

## Architecture

```text
                    BMis Desktop
                         |
              +----------+----------+
              |                     |
        React + TypeScript        Tauri
              |                     |
              +----------+----------+
                         |
                  Python Sidecar
                         |
                    FastAPI
                         |
                   BMis Client
                         |
                         v
                    Existing BMis
                    (local / remote)
```

| Layer | Technology | Role |
|-------|------------|------|
| Desktop shell | **Tauri** | Window, lifecycle, OS integration, start/stop Python sidecar, packaging |
| Frontend | **React + TypeScript** | UI, navigation, key browser, data viewer, console, app state |
| Backend | **Python + FastAPI + Pydantic** | BMis client, connections, commands, validation, data transforms |
| Local storage | **SQLite** | Saved connections, preferences, command history — not BMis server data |

Application logic lives in TypeScript and Python. Custom Rust is minimized; Tauri’s Rust layer is framework-only.

Frontend ↔ Python uses localhost (`127.0.0.1:<dynamic-port>`). Do not hardcode a production port without a strong reason.

- Full plan: [`BMis-Desktop-PLAN.md`](./BMis-Desktop-PLAN.md)
- User guide: [`docs/USER_GUIDE.md`](./docs/USER_GUIDE.md)

## Repository structure

```text
BMis-Desktop/
├── frontend/          # React + TypeScript UI
├── python/            # FastAPI sidecar + BMis client
├── src-tauri/         # Tauri shell and packaging
├── scripts/           # Python build / package helpers
├── tests/             # Integration / E2E
├── docs/
├── BMis-Desktop-PLAN.md
└── README.md
```

## Roadmap (summary)

| Phase | Focus |
|-------|--------|
| **V0.1** | Foundation — Tauri + React + Python sidecar, health check, connect + PING |
| **V0.2** | Connection manager (CRUD, test, secure credentials) |
| **V0.3** | Key browser (paginated / cursor-based; no full keyspace load) |
| **V0.4** | Data viewer (STRING, LIST, SET, ZSET, HASH as supported by BMis) |
| **V0.5** | Key operations (GET/SET/DEL/TTL/… via Python only) |
| **V0.6** | Command console |
| **V0.7** | Search and usability |
| **V0.8** | Server monitoring (only metrics BMis provides) |
| **V0.9** | Pub/Sub and advanced features (after core is stable) |
| **V1.0** | Production release — installer, bundled Python, tests, packaging |

**Current priority:** prove the foundation — Tauri launches the bundled Python backend and communicates with an existing BMis instance (PING end-to-end). Do not build the full UI yet.

## Security

- Never hardcode or commit credentials
- Store passwords via OS secure credential storage, not plain text
- Bind the local API to localhost only; validate local API access
- Minimize Tauri permissions; keep secrets out of logs
- Prefer TLS for remote BMis when supported

## Performance

Designed for large BMis instances: cursor/pagination through Python, virtualized lists, lazy loading, and no blocking work on the UI thread. Never load an entire keyspace into the frontend.

## Development principles

1. Respect the locked architecture (React/TS → Tauri → Python → BMis).
2. Do not copy or rewrite the BMis server into this repo.
3. Prefer vertical slices (UI → Python API → BMis client → test) over layer-by-layer big-bang integration.
4. Follow milestone order; no scope creep without explicit approval.
5. A feature is done only when implementation, tests, error handling, docs, and acceptance criteria are complete.

Before implementing work, check [`BMis-Desktop-PLAN.md`](./BMis-Desktop-PLAN.md) for phase, boundaries, and acceptance criteria.

## Status

Project setup phase. Application scaffolding (Tauri + React + Python sidecar) is the next step.

## Success criteria

A developer can install BMis Desktop, connect to BMis, browse and inspect keys, edit values, and run commands without relying on the CLI — as a real desktop product, not a browser wrapped in a window.
