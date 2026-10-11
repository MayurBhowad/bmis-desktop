# BMis Desktop — User Guide

## Current prototype status

This guide describes the **current prototype**, not the full future product. At present, the UI can send a request to the Python backend through Tauri IPC and display the backend's response.

The current **Ping Python** button verifies the Python process/IPC path. It does **not** connect to a BMis server or issue a BMis server `PING` command. Connection management, key browsing, data viewing, and the command console are planned but not implemented yet.

## Run the prototype

For development setup, see [Development Guide](DEVELOPMENT.md).

From the `frontend/` directory:

```bash
npm run tauri dev
```

The window should show **BMis Desktop** and a **Ping Python** button.

## Verify Python IPC

1. Launch the app.
2. Click **Ping Python**.
3. A successful response currently looks like:

```json
{"status": true, "message": "BMis python backend is running"}
```

This response confirms the UI → Tauri command → Python process → Tauri result → UI path. It does not confirm BMis server availability.

## Current limitations

- The Python executable is currently expected at `python/.venv/bin/python` on Linux development setups.
- Packaged Python sidecar/runtime support is not yet implemented.
- The UI is not yet connected to the Python BMis TCP client.
- Saved connections, credentials, key browser, data viewer, command console, and server monitoring are not implemented in the current prototype.
- Cross-platform installer and release behavior have not yet been validated.

See [BMis-Desktop-PLAN.md](../BMis-Desktop-PLAN.md) for the planned product roadmap and [Architecture](ARCHITECTURE.md) for current versus target architecture.
