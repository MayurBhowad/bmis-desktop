import io
import json
import os
import subprocess
import sys
from datetime import UTC, datetime

import pytest

from bmis_desktop.main import PROFILE_DATABASE_ENV, handle_backend_request, main
from bmis_desktop.profiles import (
    ConnectionProfileRepository,
    ProfileRepositoryError,
)
from bmis_desktop.session import BackendSession

_CREATED_AT = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
_UPDATED_AT = datetime(2026, 1, 1, 13, 0, tzinfo=UTC)
_CREATED_STAMP = "2026-01-01T12:00:00.000000+00:00"
_UPDATED_STAMP = "2026-01-01T13:00:00.000000+00:00"


class SequenceClock:
    def __init__(self, *times: datetime) -> None:
        self._times = iter(times)

    def __call__(self) -> datetime:
        return next(self._times)


def _repository(path, **kwargs) -> ConnectionProfileRepository:
    return ConnectionProfileRepository(path, **kwargs)


def _profiles(tmp_path, **kwargs) -> tuple[BackendSession, ConnectionProfileRepository]:
    return BackendSession(), _repository(tmp_path / "profiles.db", **kwargs)


def _request(session, profiles, payload: dict[str, object]) -> dict[str, object]:
    return handle_backend_request(payload, session, profiles)


def _backend_env(database) -> dict[str, str]:
    env = os.environ.copy()
    env[PROFILE_DATABASE_ENV] = os.fspath(database)
    return env


def _run_backend(lines: list[str], env: dict[str, str]) -> list[dict[str, object]]:
    process = subprocess.run(
        [sys.executable, "-m", "bmis_desktop.main"],
        input="\n".join(lines) + "\n",
        text=True,
        capture_output=True,
        check=False,
        env=env,
    )
    assert process.returncode == 0
    assert process.stderr == ""
    assert "Traceback" not in process.stdout
    return [json.loads(line) for line in process.stdout.splitlines()]


def test_create_list_update_and_delete_profiles(tmp_path) -> None:
    session, profiles = _profiles(
        tmp_path,
        clock=SequenceClock(_CREATED_AT, _UPDATED_AT),
        id_factory=lambda: "profile-1",
    )

    created = _request(
        session,
        profiles,
        {
            "command": "create_profile",
            "name": "  Local  ",
            "host": " 127.0.0.1 ",
            "port": 6379,
            "database": str(tmp_path / "ignored.db"),
        },
    )
    assert created == {
        "status": True,
        "profile": {
            "id": "profile-1",
            "name": "Local",
            "host": "127.0.0.1",
            "port": 6379,
            "created_at": _CREATED_STAMP,
            "updated_at": _CREATED_STAMP,
        },
    }
    assert not (tmp_path / "ignored.db").exists()

    listed = _request(session, profiles, {"command": "list_profiles"})
    assert listed == {"status": True, "profiles": [created["profile"]]}

    updated = _request(
        session,
        profiles,
        {
            "command": "update_profile",
            "id": "profile-1",
            "name": "Staging",
            "host": "db.example",
            "port": 6380,
        },
    )
    assert updated == {
        "status": True,
        "profile": {
            "id": "profile-1",
            "name": "Staging",
            "host": "db.example",
            "port": 6380,
            "created_at": _CREATED_STAMP,
            "updated_at": _UPDATED_STAMP,
        },
    }

    deleted = _request(
        session,
        profiles,
        {"command": "delete_profile", "id": "profile-1"},
    )
    assert deleted == {"status": True}
    assert _request(session, profiles, {"command": "list_profiles"}) == {
        "status": True,
        "profiles": [],
    }


def test_profiles_persist_across_processes(tmp_path) -> None:
    database = tmp_path / "profiles.db"
    env = _backend_env(database)
    created = _run_backend(
        [
            json.dumps(
                {
                    "command": "create_profile",
                    "name": "Local",
                    "host": "127.0.0.1",
                    "port": 6379,
                }
            )
        ],
        env,
    )
    listed = _run_backend([json.dumps({"command": "list_profiles"})], env)
    assert listed == [{"status": True, "profiles": [created[0]["profile"]]}]
    ping = _run_backend([json.dumps({"command": "ping"})], env)
    assert ping == [
        {"status": True, "message": "BMis python backend is running"},
    ]


def test_request_loop_continues_after_invalid_profile_requests(tmp_path) -> None:
    responses = _run_backend(
        [
            "{invalid}",
            json.dumps({"command": "create_profile", "name": " ", "host": "127.0.0.1", "port": 1}),
            json.dumps({"command": "delete_profile"}),
            json.dumps(
                {
                    "command": "create_profile",
                    "name": "Local",
                    "host": "127.0.0.1",
                    "port": 6379,
                }
            ),
            json.dumps({"command": "ping"}),
            json.dumps({"command": "status"}),
        ],
        _backend_env(tmp_path / "profiles.db"),
    )

    assert responses[0] == {"status": False, "error": "Invalid JSON"}
    assert responses[1] == {"status": False, "error": "Name must be a non-empty string"}
    assert responses[2] == {"status": False, "error": "Profile id must be a non-empty string"}
    assert responses[3]["status"] is True
    assert responses[4] == {
        "status": True,
        "message": "BMis python backend is running",
    }
    assert responses[5] == {
        "status": True,
        "connected": False,
        "host": None,
        "port": None,
    }


@pytest.mark.parametrize(
    ("payload", "error"),
    [
        (
            {"command": "create_profile", "host": "127.0.0.1", "port": 6379},
            "Name must be a non-empty string",
        ),
        (
            {"command": "create_profile", "name": "Local\n", "host": "127.0.0.1", "port": 6379},
            "Name cannot contain newline characters",
        ),
        (
            {"command": "create_profile", "name": "Local", "port": 6379},
            "Host must be a non-empty string",
        ),
        (
            {"command": "create_profile", "name": "Local", "host": "127.0.0.1", "port": True},
            "Port must be an integer between 1 and 65535",
        ),
        (
            {"command": "create_profile", "name": "Local", "host": "127.0.0.1", "port": 0},
            "Port must be an integer between 1 and 65535",
        ),
        (
            {"command": "create_profile", "name": "Local", "host": "127.0.0.1", "port": 65536},
            "Port must be an integer between 1 and 65535",
        ),
        (
            {"command": "create_profile", "name": "Local", "host": "127.0.0.1", "port": "6379"},
            "Port must be an integer between 1 and 65535",
        ),
        (
            {"command": "update_profile", "name": "Local", "host": "127.0.0.1", "port": 1},
            "Profile id must be a non-empty string",
        ),
        (
            {"command": "delete_profile", "id": "   "},
            "Profile id must be a non-empty string",
        ),
    ],
)
def test_profile_commands_reject_invalid_fields(tmp_path, payload, error) -> None:
    session, profiles = _profiles(tmp_path)
    assert _request(session, profiles, payload) == {"status": False, "error": error}
    assert _request(session, profiles, {"command": "list_profiles"}) == {
        "status": True,
        "profiles": [],
    }


def test_missing_profile_id_is_rejected(tmp_path) -> None:
    session, profiles = _profiles(tmp_path, id_factory=lambda: "profile-1")
    created = _request(
        session,
        profiles,
        {"command": "create_profile", "name": "Local", "host": "127.0.0.1", "port": 6379},
    )
    assert created["status"] is True

    missing_update = _request(
        session,
        profiles,
        {
            "command": "update_profile",
            "id": "missing",
            "name": "Other",
            "host": "10.0.0.2",
            "port": 1,
        },
    )
    missing_delete = _request(
        session,
        profiles,
        {"command": "delete_profile", "id": "missing"},
    )
    assert missing_update == {"status": False, "error": "Connection profile not found"}
    assert missing_delete == {"status": False, "error": "Connection profile not found"}
    assert _request(session, profiles, {"command": "list_profiles"}) == {
        "status": True,
        "profiles": [created["profile"]],
    }


def test_duplicate_profile_id_keeps_the_original(tmp_path) -> None:
    session, profiles = _profiles(tmp_path, id_factory=lambda: "profile-1")
    created = _request(
        session,
        profiles,
        {"command": "create_profile", "name": "Local", "host": "127.0.0.1", "port": 6379},
    )
    duplicate = _request(
        session,
        profiles,
        {"command": "create_profile", "name": "Other", "host": "10.0.0.2", "port": 6380},
    )
    assert created["status"] is True
    assert duplicate == {"status": False, "error": "Connection profile id already exists"}
    assert _request(session, profiles, {"command": "list_profiles"}) == {
        "status": True,
        "profiles": [created["profile"]],
    }


def test_profile_storage_errors_hide_filesystem_details(tmp_path, monkeypatch) -> None:
    session, profiles = _profiles(tmp_path)
    secret = tmp_path / "secret-location" / "profiles.db"

    def fail_read() -> list[object]:
        raise ProfileRepositoryError(f"could not open {secret}")

    monkeypatch.setattr(profiles, "list_profiles", fail_read)
    response = _request(session, profiles, {"command": "list_profiles"})
    encoded = json.dumps(response)
    assert response == {"status": False, "error": "Profile storage failed"}
    assert "secret-location" not in encoded
    assert "Traceback" not in encoded


def test_unexpected_profile_errors_do_not_stop_later_commands(tmp_path, monkeypatch) -> None:
    session, profiles = _profiles(tmp_path)

    def explode() -> list[object]:
        raise RuntimeError(f"boom {tmp_path / 'secret.db'}")

    monkeypatch.setattr(profiles, "list_profiles", explode)
    failed = _request(session, profiles, {"command": "list_profiles"})
    ping = _request(session, profiles, {"command": "ping"})
    assert failed == {"status": False, "error": "Internal error"}
    assert str(tmp_path) not in json.dumps(failed)
    assert ping == {
        "status": True,
        "message": "BMis python backend is running",
    }


def test_main_refuses_to_start_without_profile_storage(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.delenv(PROFILE_DATABASE_ENV, raising=False)
    monkeypatch.setattr(sys, "stdin", io.StringIO('{"command":"ping"}\n'))
    with pytest.raises(SystemExit) as caught:
        main()
    assert caught.value.code == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.strip() == "Profile database path is not configured"
    assert "Traceback" not in captured.err


def test_main_does_not_fall_back_to_memory(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv(PROFILE_DATABASE_ENV, ":memory:")
    monkeypatch.setattr(sys, "stdin", io.StringIO('{"command":"ping"}\n'))
    with pytest.raises(SystemExit) as caught:
        main()
    assert caught.value.code == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.strip() == "Database path must be a SQLite file path"
    assert ":memory:" not in captured.err
    assert "Traceback" not in captured.err


def test_main_hides_filesystem_details_when_storage_cannot_start(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path,
) -> None:
    database = tmp_path / "secret-location" / "profiles.db"
    monkeypatch.setenv(PROFILE_DATABASE_ENV, str(database))
    monkeypatch.setattr(sys, "stdin", io.StringIO('{"command":"ping"}\n'))
    with pytest.raises(SystemExit) as caught:
        main()
    assert caught.value.code == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.strip() == "Profile database directory does not exist"
    assert "secret-location" not in captured.err
    assert "Traceback" not in captured.err
