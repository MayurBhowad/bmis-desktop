from bmis_desktop.main import handle_request


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
    assert response["error"] == "Invalid command: None"