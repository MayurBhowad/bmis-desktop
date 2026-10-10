from bmis_desktop.main import handle_request

import json
import subprocess
import sys


def test_main_continues_after_invalid_json() -> None:
    process = subprocess.run(
        [sys.executable, "-m", "bmis_desktop.main"],
        input='{invalid}\n{"command":"ping"}\n',
        text=True,
        capture_output=True,
        check=True,
    )

    responses = [
        json.loads(line)
        for line in process.stdout.splitlines()
    ]

    assert responses == [
        {"status": False, "error": "Invalid JSON"},
        {
            "status": True,
            "message": "BMis python backend is running",
        },
    ]



def test_missing_command() -> None:
    response = handle_request({})

    assert response["status"] is False
    assert response["error"] == "Command must be a non-empty string"



def test_ping() -> None:
    response = handle_request({"command": "ping"})

    assert response["status"] is True
    assert response["message"] == "BMis python backend is running"


def test_unknown_command() -> None:
    response = handle_request({"command": "unknown"})

    assert response["status"] is False
    assert response["error"] == "Invalid command: unknown"


def test_missing_command() -> None:
    response = handle_request({})

    assert response["status"] is False
    assert response["error"] == "Command must be a non-empty string"



import pytest


@pytest.mark.parametrize(
    "payload",
    [
        None,
        [],
        "hello",
        123,
        True,
    ],
)
def test_rejects_non_object_requests(payload) -> None:
    response = handle_request(payload)

    assert response["status"] is False
    assert response["error"] == "Request must be a JSON object"


@pytest.mark.parametrize(
    "command",
    [
        None,
        "",
        123,
        [],
        {},
        True,
    ],
)
def test_rejects_invalid_command_types(command) -> None:
    response = handle_request({"command": command})

    assert response["status"] is False
    assert response["error"] == "Command must be a non-empty string"


def test_rejects_whitespace_only_command() -> None:
    response = handle_request({"command": "   "})

    assert response["status"] is False
    assert response["error"] == "Command must be a non-empty string"
