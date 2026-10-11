# Contributing

Thank you for helping improve BMis Desktop. The project is developed incrementally, one issue at a time.

## Before starting

1. Read [README.md](README.md) and [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).
2. Check [BMis-Desktop-PLAN.md](BMis-Desktop-PLAN.md) for scope and milestone order.
3. Work from an existing GitHub issue or create one with a clear problem statement and acceptance criteria.
4. Avoid implementing planned features as though they already exist; update documentation when implementation status changes.

## Branch workflow

The project uses `main`, `dev`, and a local-only `local-dev` workflow:

1. Make changes on `local-dev`.
2. Test and review the changes.
3. Merge `local-dev` into `dev`.
4. Push `dev` to `origin`.
5. Open a pull request from `dev` to `main`.
6. Do not push `local-dev` to the remote.

Follow the current repository policy if the branch strategy is changed later.

## Engineering rules

- Keep the BMis server in its own repository; do not reimplement server behavior here.
- Keep custom Rust limited to Tauri integration/process management.
- Put UI logic in TypeScript and backend/client logic in Python.
- Preserve the JSON Lines IPC contract: one JSON request per line and one JSON response per line.
- Keep Python stdout free of logs and diagnostics.
- Validate external input and return structured errors.
- Do not commit credentials, tokens, local virtual environments, build output, or generated caches.
- Add or update tests when behavior changes.
- Update the relevant docs when architecture, setup, commands, or feature status changes.

## Checks

Run the relevant checks before requesting review.

```bash
# Python
python/.venv/bin/python -m pytest -c python/pyproject.toml -q

# Frontend
cd frontend
npm run build
npm run lint
cd ..

# Rust/Tauri (requires python/.venv/bin/python for current tests)
cargo test --manifest-path frontend/src-tauri/Cargo.toml

# Patch hygiene
git diff --check
git status --short
git diff
```

Run integration tests only when the required BMis server is available:

```bash
python/.venv/bin/python -m pytest -c python/pyproject.toml -q -m integration
```

## Pull requests

A pull request should:

- Link the issue it addresses.
- Explain what changed and why.
- Include test results and any manual verification.
- Call out limitations or follow-up work.
- Update documentation if behavior or setup changed.
- Keep unrelated formatting or refactoring out of the patch.
