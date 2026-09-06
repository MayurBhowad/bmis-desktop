from bmis_desktop.main import handle_request


def test_ping():
    response = handle_request({"command": "ping"})

    assert response["status"] is True
    assert response["message"] == "BMis python backend is running"


def test_unknown_command():
    response = handle_request({"command": "unknown"})

    assert response["status"] is False