# BMis Desktop — Product & Engineering Plan

## 1. Project Overview

**BMis Desktop** is a cross-platform desktop client for the existing **BMis** server.

BMis Desktop will **not** reimplement the BMis server. The existing BMis repository remains the source of truth for the server/database implementation.

The desktop application will provide a developer-friendly graphical interface to connect to and operate an existing BMis instance.

### Core principle

> BMis Desktop is a client for BMis, not a replacement for BMis.

---

# 2. Goals

## Primary Goals

1. Build a production-quality desktop client for BMis.
2. Connect to local and remote BMis instances.
3. Provide a graphical key browser.
4. Provide data inspection and editing.
5. Provide a command console.
6. Keep frontend, desktop shell, and Python backend cleanly separated.
7. Package Python with the desktop application so users do not install Python separately.
8. Support Linux first, then Windows and macOS.
9. Keep BMis Desktop independent from BMis internal implementation details.
10. Build incrementally with tests and clear acceptance criteria.

## Non-Goals

The project must NOT:

- Reimplement the BMis server.
- Modify BMis server behavior just to make the desktop client easier.
- Introduce unnecessary microservices.
- Require users to install Python, Node.js, npm, or other development tools.
- Add AI features before the core desktop client is stable.
- Add unrelated productivity features.
- Become a generic database management application.
- Add features without a defined BMis use case.

---

# 3. Existing BMis Repository

There are two separate repositories.

```text
BMis
└── Existing BMis server

BMis-Desktop
└── Desktop client for BMis
```

The repositories must remain separate.

## BMis Repository Responsibility

BMis owns:

- Server implementation
- BMis protocol
- Commands
- Data structures
- Persistence
- Networking
- Server-side behavior
- Server tests

## BMis Desktop Responsibility

BMis Desktop owns:

- Desktop UI
- Connection management
- Key browsing
- Data visualization
- Command console
- Local application state
- Desktop packaging
- Python client/backend
- User experience

---

# 4. Architecture

## High-Level Architecture

```text
                         BMis Desktop
                              |
                +-------------+-------------+
                |                           |
                v                           v
       React + TypeScript             Tauri Shell
                |                           |
                +-------------+-------------+
                              |
                              v
                       Python Sidecar
                              |
                         FastAPI / Client
                              |
                              v
                       Existing BMis
                              |
                    +---------+---------+
                    |                   |
                  Local              Remote
                  BMis                BMis
```

## Important

We are using **Tauri**, but application/business logic should be implemented in:

- TypeScript
- Python

We should minimize custom Rust code.

Tauri's Rust layer is part of the framework, but we are **not building the application backend in Rust**.

---

# 5. Technology Stack

## Desktop

**Tauri**

Responsibilities:

- Desktop window
- Application lifecycle
- Native desktop integration
- Starting/stopping the Python sidecar
- Packaging
- OS integration

## Frontend

**React + TypeScript**

Responsibilities:

- UI
- Navigation
- Forms
- Key browser
- Data viewer
- Command console
- Application state
- Error presentation

## Backend / Sidecar

**Python**

Recommended:

- Python
- FastAPI
- Pydantic

Responsibilities:

- BMis client
- Connection management
- Command execution
- Data transformation
- Backend validation
- Communication with BMis

## Local Storage

**SQLite**

Use SQLite for:

- Saved connections
- Application preferences
- Command history
- Future local metadata

Do not store BMis server data in SQLite unless explicitly required by a future feature.

---

# 6. Python Packaging Requirement

The end user must **not** need to install Python.

Development environment:

```text
Developer machine
    |
    +-- Python
    +-- FastAPI
    +-- Dependencies
    +-- BMis Desktop
```

Production application:

```text
BMis Desktop Installer
    |
    +-- Tauri application
    +-- Frontend assets
    +-- Bundled Python runtime/backend
```

The application must launch its bundled Python backend automatically.

The user experience should be:

```text
Download
    |
Install
    |
Open BMis Desktop
    |
Connect to BMis
```

The user should NOT need:

```text
python install
pip install
npm install
cargo install
```

---

# 7. Python Sidecar

The Python backend will run as a local process owned by the desktop application.

Conceptually:

```text
Tauri
   |
   | start
   v
Python Sidecar
   |
   +-- FastAPI
   +-- BMis Client
   +-- Connection Manager
   +-- Command Service
```

Initial communication:

```text
Frontend
    |
    v
Python FastAPI
    |
    v
BMis
```

Use localhost communication initially because it is simple, testable, and easy to debug.

Example:

```text
127.0.0.1:<dynamic-port>
```

Do not hardcode a production port unless there is a strong reason.

---

# 8. BMis Connection Model

BMis Desktop must support multiple BMis connections.

Example:

```text
Connections

Local
Development
Staging
Production
```

Each connection may contain:

```text
Name
Host
Port
Username
Password
TLS configuration
```

Credentials must not be stored as plain text.

Use the operating system's secure credential/key storage where practical.

---

# 9. Repository Structure

Recommended structure:

```text
BMis-Desktop/
|
+-- frontend/
|   |
|   +-- src/
|       +-- components/
|       +-- pages/
|       +-- services/
|       +-- stores/
|       +-- types/
|       +-- hooks/
|       +-- utils/
|
+-- python/
|   |
|   +-- app/
|       +-- main.py
|       +-- api/
|       +-- clients/
|       +-- services/
|       +-- models/
|       +-- config/
|       +-- utils/
|   |
|   +-- tests/
|   +-- requirements.txt
|
+-- src-tauri/
|   |
|   +-- tauri.conf.json
|   +-- capabilities/
|   +-- icons/
|
+-- scripts/
|   +-- build-python/
|   +-- package/
|
+-- tests/
|
+-- docs/
|
+-- README.md
```

The exact structure may evolve, but responsibilities must remain separated.

---

# 10. Product Scope

## V0.1 — Foundation

The first release must be deliberately small.

### Features

1. Application starts successfully.
2. Tauri launches.
3. Frontend loads.
4. Python sidecar starts automatically.
5. Frontend can communicate with Python.
6. Python can connect to BMis.
7. PING command.
8. Basic command execution.
9. Basic connection management.
10. Basic error handling.
11. Basic logging.

### Acceptance Criteria

```text
Tauri starts
    |
Python sidecar starts
    |
Frontend detects backend
    |
User enters BMis connection
    |
Connection succeeds
    |
PING succeeds
```

This milestone proves the architecture.

---

# 11. V0.2 — Connection Manager

Build the connection management UI.

## UI

```text
Connections
-------------------------
+ Add Connection

Local
Development
Staging
Production
```

## Add Connection

```text
Name
Host
Port
Username
Password
TLS

[Test Connection]
[Save]
```

## Requirements

- Create connection
- Edit connection
- Delete connection
- Test connection
- Connect/disconnect
- Connection status
- Secure credential handling

---

# 12. V0.3 — Key Browser

After connection:

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

## Critical Requirement

Do not load millions of keys into the frontend.

Use a server-side/streaming/paginated approach supported by BMis.

Prefer cursor-based iteration where the BMis protocol supports it.

The UI must remain responsive for large datasets.

---

# 13. V0.4 — Data Viewer

Selecting a key opens a data viewer.

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

Support BMis data types progressively.

Initial target:

```text
STRING
LIST
SET
ZSET
HASH
```

Later:

```text
STREAM
```

Only implement types actually supported by BMis.

---

# 14. V0.5 — Key Operations

Implement:

- GET
- SET
- DEL
- EXISTS
- TTL
- EXPIRE
- Rename
- Edit value
- Copy key
- Copy value

For every operation:

```text
UI
 |
 v
Python service
 |
 v
BMis client
 |
 v
BMis
```

Do not bypass the Python layer with ad-hoc BMis connections from the frontend.

---

# 15. V0.6 — Command Console

Add a terminal-like console.

Example:

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

- Command input
- Command execution
- Output
- Command history
- Clear console
- Error output
- Keyboard shortcuts

The command parser should not duplicate BMis command semantics unnecessarily.

Prefer forwarding valid commands through the Python BMis client.

---

# 16. V0.7 — Search and Usability

Add:

- Key pattern search
- Filtering
- Sorting where meaningful
- Pagination/cursor navigation
- Refresh
- Auto-refresh where appropriate
- Copy buttons
- Expand/collapse values
- JSON formatting where applicable
- Empty states
- Loading states
- Error states

The application must remain usable with large keyspaces.

---

# 17. V0.8 — Monitoring Information

If supported by BMis, expose:

```text
Server information
Memory
Connected clients
Commands
Uptime
Version
```

Do not invent metrics that BMis cannot provide.

---

# 18. V0.9 — Pub/Sub and Advanced Features

After the core client is stable:

- Pub/Sub
- Streams
- Slow log
- Server statistics
- Connection diagnostics
- Advanced key inspection

These are secondary features.

They must not delay the core product.

---

# 19. V1.0 — Production Release

V1.0 should provide:

```text
Connection Management
        +
Key Browser
        +
Data Viewer
        +
Key Operations
        +
Command Console
        +
Search
        +
Basic Server Information
        +
Error Handling
        +
Secure Credential Storage
        +
Bundled Python Runtime
        +
Installer
```

Before calling V1.0 complete:

- Automated tests pass.
- Build works from a clean machine.
- Python does not need to be installed.
- Application can connect to a real BMis instance.
- Application handles connection failures.
- Application handles malformed commands.
- Application does not freeze on large keyspaces.
- Application can be packaged for the target OS.

---

# 20. Development Strategy

Development must happen in small vertical slices.

Bad approach:

```text
Build entire frontend
    |
Build entire Python backend
    |
Integrate at the end
```

Preferred approach:

```text
Feature
  |
UI
  |
Python API
  |
BMis Client
  |
BMis
  |
Test
```

Each feature should work end-to-end before moving to the next feature.

---

# 21. Testing Strategy

## Python Tests

Test:

- BMis client
- Connection manager
- Command service
- API endpoints
- Validation
- Error handling

## Frontend Tests

Test:

- Components
- Forms
- State
- Loading states
- Error states
- User interactions

## Integration Tests

Test:

```text
Frontend
    |
Python
    |
BMis
```

## End-to-End Tests

Test:

```text
Launch application
    |
Start Python
    |
Connect to BMis
    |
Execute command
    |
Display result
```

---

# 22. Error Handling

Errors must be handled at every layer.

```text
BMis
 |
 v
Python
 |
 v
Tauri
 |
 v
Frontend
```

The frontend should receive structured errors.

Example:

```json
{
  "code": "CONNECTION_FAILED",
  "message": "Unable to connect to BMis",
  "details": {}
}
```

Avoid exposing Python stack traces directly to users.

Detailed stack traces should go to development logs.

---

# 23. Security

Security is a first-class requirement.

## Requirements

- Never hardcode credentials.
- Never commit credentials.
- Never store passwords as plain text.
- Validate local API access.
- Bind local backend only to localhost.
- Minimize Tauri permissions.
- Use secure communication for remote BMis connections when supported.
- Sanitize user-provided values.
- Avoid arbitrary OS command execution.
- Keep secrets out of logs.

Any feature that introduces command execution or filesystem access requires explicit security review.

---

# 24. Performance Requirements

BMis Desktop must be designed for large BMis instances.

Do not:

```text
Load every key
    |
Convert everything to JSON
    |
Send everything to frontend
```

Prefer:

```text
BMis
 |
Cursor / pagination
 |
Python
 |
Incremental response
 |
Frontend
```

UI requirements:

- Virtualized lists where needed.
- Lazy loading.
- Incremental rendering.
- No blocking operations on the UI thread.
- Background operations for expensive work.

---

# 25. UI Principles

The UI should be:

- Simple
- Developer-focused
- Fast
- Keyboard-friendly
- Consistent
- Information-dense without being cluttered

Primary layout:

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

After connecting:

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

---

# 26. Logging

Implement structured logging.

Separate:

```text
Application logs
Python logs
BMis connection logs
Error logs
```

Never log:

- Passwords
- Authentication tokens
- Secrets
- Sensitive values unnecessarily

Provide a way to collect diagnostic logs for troubleshooting.

---

# 27. Build and Packaging

The build pipeline must eventually produce platform-specific applications.

Target:

```text
Linux
Windows
macOS
```

Each platform must contain the correct Python runtime/sidecar.

Conceptually:

```text
BMis Desktop Linux
    |
    +-- Tauri Linux
    +-- Python Linux sidecar

BMis Desktop Windows
    |
    +-- Tauri Windows
    +-- Python Windows sidecar

BMis Desktop macOS
    |
    +-- Tauri macOS
    +-- Python macOS sidecar
```

Do not assume a Python environment built on one OS works on another OS.

---

# 28. CI/CD

Eventually implement CI for:

- TypeScript lint
- TypeScript tests
- Python lint
- Python tests
- Build validation
- Tauri build
- Packaging

Recommended pipeline:

```text
Pull Request
     |
     +-- Frontend checks
     +-- Python checks
     +-- Tests
     +-- Build check
     |
     v
Merge
     |
     v
Release Build
     |
     +-- Linux
     +-- Windows
     +-- macOS
```

---

# 29. GitHub Issue Strategy

Each milestone should be represented by GitHub issues.

Example:

```text
Epic: BMis Desktop V0.1

Issue 1: Initialize Tauri + React project
Issue 2: Add Python sidecar
Issue 3: Implement frontend ↔ Python communication
Issue 4: Implement BMis client
Issue 5: Implement connection management
Issue 6: Implement PING
Issue 7: Add integration tests
```

Do not create huge issues containing months of work.

Each issue should have:

- Problem
- Goal
- Scope
- Technical approach
- Acceptance criteria
- Out of scope

---

# 30. Definition of Done

A feature is complete only when:

```text
Implementation
      +
Tests
      +
Error handling
      +
Documentation
      +
Acceptance criteria
```

are complete.

Do not mark a feature complete just because it works manually once.

---

# 31. Development Rules for Cursor

Cursor must follow these rules throughout the project.

## Rule 1 — Respect the architecture

Do not introduce a new architecture without explicit approval.

Current architecture:

```text
React + TypeScript
        |
      Tauri
        |
Python Sidecar
        |
Existing BMis
```

## Rule 2 — Do not rewrite BMis

The existing BMis repository is external to this project.

Do not copy BMis server implementation into BMis Desktop.

## Rule 3 — No unnecessary Rust

Do not move business logic into Rust.

Use Tauri only for desktop/native responsibilities unless a specific requirement requires Rust.

## Rule 4 — No unnecessary dependencies

Before adding a dependency:

1. Check whether the feature can be implemented using existing dependencies.
2. Check whether the dependency is actively maintained.
3. Check security/licensing implications.
4. Add it only if it provides meaningful value.

## Rule 5 — No scope creep

Do not implement:

- AI
- Cloud synchronization
- User accounts
- Collaboration
- Analytics
- Generic database support
- Unrelated utilities

unless explicitly added to the roadmap.

## Rule 6 — Follow milestone order

Do not jump ahead.

Preferred order:

```text
Foundation
   ↓
Python sidecar
   ↓
BMis connection
   ↓
Connection manager
   ↓
Key browser
   ↓
Data viewer
   ↓
Key operations
   ↓
Console
   ↓
Search/usability
   ↓
Monitoring
   ↓
Advanced features
   ↓
Packaging
   ↓
V1.0
```

## Rule 7 — Preserve working code

Do not perform broad refactors while implementing a small feature.

Prefer focused changes.

## Rule 8 — Test before moving forward

After each milestone:

```text
Implement
   ↓
Test
   ↓
Fix
   ↓
Document
   ↓
Commit
   ↓
Next milestone
```

## Rule 9 — Ask before changing architecture

If implementation requires a significant architectural change, stop and explain:

- Current architecture
- Problem
- Proposed change
- Alternatives
- Tradeoffs

Do not silently change architecture.

## Rule 10 — Keep BMis compatibility explicit

Whenever implementing a BMis feature, verify the actual BMis command/protocol behavior.

Do not assume Redis behavior is automatically identical to BMis.

---

# 32. Current Priority

The only current priority is:

> Build the BMis Desktop foundation and prove that Tauri can launch the bundled Python backend and communicate with an existing BMis instance.

Do not implement the full UI yet.

---

# 33. Immediate Execution Plan

## Step 1 — Repository

Create:

```text
BMis-Desktop
```

Initialize Git.

Add:

```text
README.md
ARCHITECTURE.md
ROADMAP.md
```

This document can serve as the master project plan.

---

## Step 2 — Tauri + Frontend

Create:

```text
Tauri
+
React
+
TypeScript
```

Acceptance:

```text
npm/pnpm development command
        |
        v
Tauri application opens
        |
        v
React UI renders
```

---

## Step 3 — Python Sidecar

Create minimal Python application.

Example responsibility:

```text
GET /health
```

Expected:

```json
{
  "status": "ok"
}
```

Acceptance:

```text
Tauri starts
    |
Python starts
    |
Frontend calls /health
    |
status = ok
```

---

## Step 4 — BMis Client

Implement a Python BMis client.

Start with:

```text
connect()
disconnect()
ping()
execute()
```

Do not implement every command yet.

---

## Step 5 — Connect to BMis

Test against the real existing BMis repository.

Flow:

```text
BMis Desktop
      |
      v
Python
      |
      v
Existing BMis
      |
      v
PING
      |
      v
PONG
```

Acceptance:

- Connect succeeds.
- PING succeeds.
- Connection failure is handled.
- Invalid host/port is handled.
- Backend does not crash.

---

## Step 6 — First End-to-End Feature

Implement:

```text
PING
```

from the UI.

Example:

```text
[Connect]

Status: Connected

[Ping BMis]

Result:
PONG
```

This is the first complete vertical slice.

---

# 34. First Release Sequence

The complete project sequence is:

```text
PHASE 0
Project setup
    |
    v
PHASE 1
Tauri + React + TypeScript
    |
    v
PHASE 2
Python sidecar
    |
    v
PHASE 3
Python ↔ BMis client
    |
    v
PHASE 4
Connection manager
    |
    v
PHASE 5
Key browser
    |
    v
PHASE 6
Data viewer
    |
    v
PHASE 7
Key operations
    |
    v
PHASE 8
Command console
    |
    v
PHASE 9
Search + performance
    |
    v
PHASE 10
Monitoring
    |
    v
PHASE 11
Advanced features
    |
    v
PHASE 12
Packaging
    |
    v
PHASE 13
CI/CD
    |
    v
V1.0
```

---

# 35. Success Definition

BMis Desktop is successful when a developer can:

```text
Install BMis Desktop
        |
        v
Open application
        |
        v
Add BMis connection
        |
        v
Connect
        |
        v
Browse keys
        |
        v
Inspect values
        |
        v
Modify values
        |
        v
Execute BMis commands
        |
        v
Work efficiently without using CLI
```

The application must feel like a real desktop product, not a web application wrapped in a window.

---

# 36. Final Architecture Decision

Unless explicitly changed later, use:

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
```

### Locked decisions

- Desktop framework: **Tauri**
- UI: **React + TypeScript**
- Backend: **Python**
- Python delivery: **Bundled sidecar**
- Python installation on client: **Not required**
- Local storage: **SQLite**
- BMis server: **Existing separate repository**
- Application logic: **Python + TypeScript**
- Rust: **Tauri framework layer only; avoid custom Rust unless necessary**
- Initial communication: **localhost**
- Initial target: **Linux**
- Later targets: **Windows + macOS**
- Development style: **Incremental vertical slices**
- First real feature: **PING against existing BMis**

---

# 37. Cursor Instruction

Before implementing any task, read this document and determine:

1. Which phase the task belongs to.
2. Whether the task is currently allowed.
3. Which architecture boundary it belongs to.
4. What existing code can be reused.
5. What tests are required.
6. What acceptance criteria must pass.

If a requested implementation conflicts with this plan, **do not silently change the architecture or scope**. Explain the conflict and ask for approval before proceeding.

> **Build BMis Desktop incrementally. Keep it focused. Do not rebuild BMis. Do not add distractions.**
