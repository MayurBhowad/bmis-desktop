# Security Policy

## Project status

BMis Desktop is under active development. Do not assume that the current prototype is suitable for production or for managing sensitive production data.

## Reporting a vulnerability

Please do not disclose suspected vulnerabilities in a public issue before the maintainer has had a chance to assess them.

Use GitHub's private vulnerability reporting feature for this repository if it is enabled. Otherwise, contact the repository maintainer privately through a channel available on the GitHub profile. Include reproduction steps, affected versions/commits, impact, and any suggested mitigation. Do not include real credentials or customer data in the report.

## Security expectations

- Never commit passwords, tokens, private keys, or production connection strings.
- Do not log credentials or secret values.
- Validate JSON IPC requests and command arguments.
- Keep Python IPC on Tauri's child-process stdin/stdout; do not expose an unauthenticated local HTTP service.
- Keep Tauri capabilities and CSP permissions as restrictive as practical.
- Treat BMis commands that modify or delete data as potentially destructive.
- Prefer TLS for remote BMis connections when the server supports it.
- Use OS secure credential storage before implementing persistent password storage; do not store passwords in plain text.
- Review dependencies and generated/packaged artifacts before releases.

## Scope limitations

The current implementation uses a development virtual environment path for Python and has not completed production sidecar packaging or cross-platform security validation. Do not use the current prototype as a production security boundary.
