import json
import os
import sys
from datetime import UTC, datetime

from bmis_desktop.profiles import (
    ConnectionProfile,
    ConnectionProfileRepository,
    ProfileError,
    ProfileRepositoryError,
)
from bmis_desktop.session import BackendSession, error_response, handle_request

__all__ = ["PROFILE_DATABASE_ENV", "handle_backend_request", "handle_request", "main"]

# Set by the Tauri host when the process starts. Profile requests cannot override it.
PROFILE_DATABASE_ENV = "BMIS_PROFILE_DATABASE"
_PROFILE_COMMANDS = {
    "create_profile",
    "list_profiles",
    "update_profile",
    "delete_profile",
}
_PROFILE_STORAGE_FAILED = "Profile storage failed"
_INTERNAL_ERROR = "Internal error"


def _encode_response(response: object) -> str:
    try:
        return json.dumps(response)
    except (TypeError, ValueError):
        return json.dumps(
            {
                "status": False,
                "error": "BMis response could not be encoded",
            }
        )


def _public_profile_error(exc: ProfileError) -> str:
    """Return a client-safe profile error without paths or tracebacks."""
    message = " ".join(str(exc).split())
    if (
        not message
        or len(message) > 200
        or "/" in message
        or "\\" in message
        or "Traceback" in message
    ):
        return _PROFILE_STORAGE_FAILED
    return message


def _iso_timestamp(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ProfileRepositoryError("Profile timestamp must be timezone-aware")
    return value.astimezone(UTC).isoformat(timespec="microseconds")


def _profile_payload(profile: ConnectionProfile) -> dict[str, object]:
    return {
        "id": profile.id,
        "name": profile.name,
        "host": profile.host,
        "port": profile.port,
        "created_at": _iso_timestamp(profile.created_at),
        "updated_at": _iso_timestamp(profile.updated_at),
    }


def _load_profile_repository() -> ConnectionProfileRepository:
    configured = os.environ.get(PROFILE_DATABASE_ENV)
    if configured is None or not configured.strip():
        raise ProfileRepositoryError("Profile database path is not configured")
    try:
        repository = ConnectionProfileRepository(configured)
        repository.list_profiles()
    except ProfileError:
        raise
    except Exception as exc:
        raise ProfileRepositoryError("Profile storage could not be initialized") from exc
    return repository


def _profile_command(
    command: str,
    request: dict[str, object],
    profiles: ConnectionProfileRepository,
) -> dict[str, object]:
    try:
        if command == "create_profile":
            profile = profiles.create(
                request.get("name"),
                request.get("host"),
                request.get("port"),
            )
            return {"status": True, "profile": _profile_payload(profile)}
        if command == "list_profiles":
            return {
                "status": True,
                "profiles": [_profile_payload(profile) for profile in profiles.list_profiles()],
            }
        if command == "update_profile":
            profile = profiles.update(
                request.get("id"),
                name=request.get("name"),
                host=request.get("host"),
                port=request.get("port"),
            )
            return {"status": True, "profile": _profile_payload(profile)}
        if command == "delete_profile":
            profiles.delete(request.get("id"))
            return {"status": True}
    except ProfileError as exc:
        return error_response(_public_profile_error(exc))
    return error_response(f"Invalid command: {command}")


def _dispatch_request(
    request: object,
    session: BackendSession,
    profiles: ConnectionProfileRepository,
) -> dict[str, object]:
    if isinstance(request, dict):
        command = request.get("command")
        # The database path is process configuration, never a request field.
        if isinstance(command, str) and command in _PROFILE_COMMANDS:
            return _profile_command(command, request, profiles)
    return handle_request(request, session)


def handle_backend_request(
    request: object,
    session: BackendSession,
    profiles: ConnectionProfileRepository,
) -> dict[str, object]:
    try:
        return _dispatch_request(request, session, profiles)
    except Exception:  # noqa: BLE001 - IPC must not leak unexpected failures.
        return error_response(_INTERNAL_ERROR)


def main() -> None:
    try:
        profiles = _load_profile_repository()
    except ProfileError as exc:
        print(_public_profile_error(exc), file=sys.stderr, flush=True)
        raise SystemExit(1) from None

    session = BackendSession()
    try:
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue

            try:
                request = json.loads(line)
            except json.JSONDecodeError:
                response: object = error_response("Invalid JSON")
            else:
                try:
                    response = handle_backend_request(request, session, profiles)
                except Exception:  # noqa: BLE001 - one bad request must not stop the loop.
                    response = error_response(_INTERNAL_ERROR)

            print(_encode_response(response), flush=True)
    finally:
        session.close()


if __name__ == "__main__":
    main()
