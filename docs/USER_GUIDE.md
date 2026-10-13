# BMis Desktop — User Guide

## Current prototype status

This guide describes the **current prototype**, not the full future product. The UI can check the Python backend, save connection profiles, connect to one BMis server, send one command, and show the server's decoded response.

**Ping Python** checks the desktop Python process. **Saved profiles** stores a name, host, and port. The **BMis server** panel is the server connection. The **Command console** sends the text you type as a raw BMis command.

## Run the prototype

For development setup, see [Development Guide](DEVELOPMENT.md).

From the `frontend/` directory:

```bash
npm run tauri dev
```

The window should show **BMis Desktop**, **Python backend**, **Saved profiles**, **BMis server**, and **Command console**.

## Verify Python IPC

1. Launch the app.
2. Click **Ping Python**.
3. A successful response looks like:

```json
{
  "status": true,
  "message": "BMis python backend is running"
}
```

This confirms the UI → Tauri command → Python process → Tauri result → UI path. It does not confirm BMis server availability.

## Save a connection profile

Profiles remember a name, hostname or IP, and port. They do not store a password.

1. In **Saved profiles**, click **New profile**.
2. Enter a name, hostname or IP, and port, then click **Save profile**.
3. Click a saved profile to fill the **BMis server** host and port. That does not connect.
4. Click **Edit** to change a saved profile, or **Delete** and then **Delete profile** to remove it. **Cancel** leaves the profile in place.
5. You can still type a host and port directly and click **Connect** without using a saved profile.

An empty name, empty host, or port outside 1 through 65535 is shown as an error and is not sent. A backend failure stays on the page. While a profile request is running, its action stays disabled so it cannot be submitted twice.

## Connect and run a command

1. Start a BMis server. The form defaults to `127.0.0.1` and port `6379`.
2. Click **Connect**. A successful connection shows **Connected** and `Connected to 127.0.0.1:6379`.
3. In **Command console**, enter a command and click **Execute**.
4. Click **Disconnect** when finished. That closes the server socket.

The recorded live server check, from `python/tests/test_session.py`, is:

| Command | Displayed result |
|---|---|
| `SET desktop_test Mayur` | `OK` |
| `GET desktop_test` | `Mayur` |

A successful execute response looks like:

```json
{
  "status": true,
  "result": "OK"
}
```

Invalid host or port, a refused connection, a timeout, and a server error stay in the page as an error message. **Disconnect** and closing the app release the socket. **Ping Python** stays independent of that connection.

## Current limitations

- The Python executable is currently expected at `python/.venv/bin/python` on Linux development setups.
- Packaged Python sidecar/runtime support is not yet implemented.
- Credentials, key browser, data viewer, and server monitoring are not implemented in the current prototype.
- Cross-platform installer and release behavior have not yet been validated.

See [BMis-Desktop-PLAN.md](../BMis-Desktop-PLAN.md) for the planned product roadmap and [Architecture](ARCHITECTURE.md) for current versus target architecture.
