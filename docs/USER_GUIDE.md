# BMis Desktop — User Guide

This guide describes how to install and use **BMis Desktop**, the desktop client for an existing BMis server.

BMis Desktop does not replace BMis. You need a running BMis instance (local or remote) to connect to.

---

## 1. What you need

- A supported OS: **Linux** (primary), later **Windows** and **macOS**
- A reachable **BMis** server (host, port, and credentials if required)
- The BMis Desktop installer for your platform

You do **not** need to install Python, Node.js, npm, or Cargo. Those are for developers only.

---

## 2. Install and open

```text
Download installer
        ↓
Install BMis Desktop
        ↓
Open BMis Desktop
        ↓
Connect to BMis
```

1. Download the installer for your operating system.
2. Run the installer and follow the prompts.
3. Launch **BMis Desktop** from your applications menu or desktop shortcut.

On first launch the app starts its bundled backend automatically. You should see the main window with a connections area and workspace.

---

## 3. Main window

### Before connecting

```text
+--------------------------------------------------+
| BMis Desktop                         Settings    |
+----------------+---------------------------------+
| Connections    |                                 |
|                |                                 |
| Local          |        Main Workspace           |
| Development    |                                 |
| Staging        |                                 |
| Production     |                                 |
|                |                                 |
+----------------+---------------------------------+
```

- **Connections** (left): saved BMis targets you can open, edit, or remove
- **Main workspace** (right): content for the selected connection or feature
- **Settings**: application preferences

### After connecting

```text
+--------------------------------------------------+
| Connection: Local                                |
+----------------+---------------------------------+
| Keys           | Key Details                     |
|                |                                 |
| user:1         | user:1                          |
| user:2         | Type: HASH                      |
| product:1      | TTL: 3600                       |
| session:1      |                                 |
|                | Fields                          |
| Search...      | name = Mayur                    |
|                | role = admin                    |
+----------------+---------------------------------+
```

- **Keys**: browse and search keys in the connected instance
- **Key details**: type, TTL, and value for the selected key

---

## 4. Connections

### Add a connection

1. Open **Connections**.
2. Choose **Add Connection**.
3. Fill in:

| Field | Purpose |
|-------|---------|
| **Name** | Label in the list (e.g. Local, Staging) |
| **Host** | BMis host name or IP |
| **Port** | BMis port |
| **Username** | Account if authentication is required |
| **Password** | Password (stored securely, not as plain text) |
| **TLS** | Enable secure transport when the server supports it |

4. Optional: click **Test Connection** to verify host, port, and credentials.
5. Click **Save**.

### Manage connections

| Action | What it does |
|--------|----------------|
| **Edit** | Change name, host, port, credentials, or TLS |
| **Delete** | Remove a saved connection |
| **Test Connection** | Check reachability without opening the full session |
| **Connect** | Open a session to that BMis instance |
| **Disconnect** | Close the active session |

Connection status (connected, disconnected, error) appears in the UI for the active connection.

### Examples

Typical saved connections:

- Local  
- Development  
- Staging  
- Production  

Use clear names so you do not mix environments.

---

## 5. Connect and verify

1. Select a saved connection.
2. Click **Connect**.
3. Wait for a successful status.
4. Optionally run **Ping** (or `PING` in the console) to confirm the server responds with `PONG`.

If connection fails:

- Check host and port
- Confirm BMis is running and reachable from your machine
- Verify username, password, and TLS settings
- Review any error message shown in the app (stack traces are for logs, not the main UI)

---

## 6. Key browser

After a successful connection, open the **Keys** view.

```text
BMis
|
+-- Keys
|   +-- user:1
|   +-- user:2
|   +-- product:1
|   +-- session:123
|
+-- Search
```

### Browse safely on large instances

BMis Desktop does **not** load every key into memory at once. Keys are loaded in pages or via cursor-style iteration so the UI stays responsive on large keyspaces.

- Scroll or page through results as needed
- Use search/filter instead of dumping the full keyspace
- Refresh when you expect server-side changes

---

## 7. Inspect data

Select a key to open the **data viewer**.

Example:

```text
Key: user:1
Type: HASH
TTL: 3600

--------------------------------
Field          Value
--------------------------------
name           Mayur
role           admin
email          ...
```

Supported types are introduced progressively, based on what BMis actually supports. Initial types include:

- STRING  
- LIST  
- SET  
- ZSET  
- HASH  

Later types (for example STREAM) appear only when BMis supports them and the client implements them.

Use expand/collapse and formatting (such as JSON where applicable) to read large or nested values.

---

## 8. Key operations

From the UI you can perform common key actions, for example:

| Operation | Typical use |
|-----------|-------------|
| GET / view | Read the current value |
| SET / edit | Create or change a value |
| DEL | Delete a key |
| EXISTS | Check whether a key exists |
| TTL / EXPIRE | Inspect or set expiry |
| Rename | Change the key name |
| Copy key / copy value | Copy to the clipboard |

All operations go through the desktop app’s backend to BMis. You do not configure a separate client connection in the UI for these actions.

---

## 9. Command console

Open the **console** for a terminal-style session against the connected instance.

```text
BMis Console

> PING
PONG

> SET name Mayur
OK

> GET name
"Mayur"
```

Features:

- Type and run commands
- See command output and errors
- Command history
- Clear console
- Keyboard shortcuts for faster input

Prefer valid BMis commands. The console forwards commands through the same client path as the rest of the app; it is not a separate shell on your machine.

---

## 10. Search and usability

When available in your version:

- Key pattern search
- Filtering and sorting where it is meaningful
- Pagination / cursor navigation
- Refresh and optional auto-refresh
- Copy buttons for keys and values
- Empty, loading, and error states for clear feedback

Keep search patterns specific when working against large production keyspaces.

---

## 11. Server information

If your BMis server exposes monitoring data, BMis Desktop may show items such as:

- Server information  
- Memory  
- Connected clients  
- Command stats  
- Uptime  
- Version  

Only metrics that BMis actually provides are shown. The client does not invent server metrics.

---

## 12. Settings and preferences

Use **Settings** for application preferences (for example UI options and local behavior). Preferences are stored locally (SQLite). They do not store your BMis server’s data.

Passwords and secrets use the operating system’s secure credential storage where practical. Do not paste production secrets into logs or screenshots.

---

## 13. Logging and diagnostics

The app keeps structured logs for troubleshooting (application, Python backend, connection, and errors).

Logs should **not** contain:

- Passwords  
- Authentication tokens  
- Other secrets  

If you need help diagnosing a problem, use the app’s diagnostic log collection if available, and redact any sensitive values before sharing.

---

## 14. Typical workflows

### First-time setup

1. Install and open BMis Desktop.  
2. Add a connection to your BMis server.  
3. Test connection, then Connect.  
4. Run Ping to confirm `PONG`.  

### Inspect a key

1. Connect.  
2. Find the key in the browser or via search.  
3. Open it in the data viewer.  
4. Copy or edit as needed.  

### Run ad-hoc commands

1. Connect.  
2. Open the command console.  
3. Enter a BMis command and review the output.  

### Work across environments

1. Save separate connections (Local, Staging, Production).  
2. Disconnect before switching.  
3. Confirm the active connection name in the header before making changes.

---

## 15. Troubleshooting

| Symptom | What to check |
|---------|----------------|
| App does not start | Reinstall; confirm your OS is supported |
| Backend / health failure | Restart the app; check diagnostic logs |
| Cannot connect | Host, port, firewall, BMis running, credentials, TLS |
| Ping fails | Connection may be incomplete or the server may be unhealthy |
| Keys load slowly / UI freezes | Prefer search and pagination; avoid patterns that match huge keyspaces |
| Command errors | Confirm command syntax and that BMis supports that command |
| Auth failures | Update saved credentials; avoid expired or wrong environment secrets |

---

## 16. Safety reminders

- Treat Production connections carefully; prefer Test Connection before Connect when unsure.
- Do not store passwords in plain text outside the app’s secure storage.
- Prefer TLS for remote servers when available.
- Remember that key edits and deletes apply on the live BMis instance.

---

## 17. Related documents

| Document | Audience |
|----------|----------|
| [README.md](../README.md) | Project overview and architecture |
| [BMis-Desktop-PLAN.md](../BMis-Desktop-PLAN.md) | Full product and engineering plan |

---

*Feature availability depends on your BMis Desktop version and what your BMis server supports. Early releases focus on connect + PING; key browser, viewer, console, and monitoring follow the product roadmap.*
