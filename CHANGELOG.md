# Changelog

Notable changes to BMis Desktop are recorded here.

The project has not published a production release yet. Entries below summarize the current development baseline; they are not a claim that the full product roadmap is implemented.

## Unreleased

### Added

- Tauri 2 desktop shell with React, TypeScript, and Vite frontend.
- Long-running Python backend communicating with Tauri over newline-delimited JSON on stdin/stdout.
- Python BMis TCP client and incremental response parser.
- Python IPC request validation and malformed-JSON recovery tests.
- Client connection timeouts, command validation, and connection lifecycle handling.
- Separation of unit tests from tests requiring a running BMis server.
- Tauri Content Security Policy configuration.
- Project architecture, development, contributing, and security documentation.
- CI workflow for Python tests, frontend build, and Rust tests.

### Fixed

- Correct distinction between incomplete protocol responses and a legitimate null response.
- Python client cleanup after socket timeout and safer handling of child-process pipe setup failures.

### Known limitations

- The current UI health check tests the Python backend only; it does not yet send commands to a BMis server.
- Python is launched from `python/.venv/bin/python` in development; packaged sidecar/runtime support is pending.
- Connection management UI, key browser, data viewer, command console, and production installers remain roadmap items.
