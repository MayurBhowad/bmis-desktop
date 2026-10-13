import io
import json
import os
import socket
import subprocess
import sys
import threading
from typing import Self

import pytest

from bmis_desktop.bmis.client import BMisClient
from bmis_desktop.main import PROFILE_DATABASE_ENV, handle_backend_request, handle_request, main
from bmis_desktop.profiles import ConnectionProfileRepository
from bmis_desktop.session import BackendSession


def _fast_client(host: str, port: int) -> BMisClient:
    return BMisClient(host, port, connect_timeout=1.0, socket_timeout=1.0)


def _connect_request(host: str, port: int) -> dict[str, object]:
    return {"command": "connect", "host": host, "port": port}


def _closed_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


class MockBMisServer:
    """Local TCP peer that speaks a small subset of BMis replies."""

    def __init__(self) -> None:
        self.commands: list[str] = []
        self.accepts = 0
        self.error: BaseException | None = None
        self.client_closed = threading.Event()
        self._values: dict[str, str] = {}
        self._lock = threading.Lock()
        self._stopping = False
        self._workers: list[threading.Thread] = []
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._socket.bind(("127.0.0.1", 0))
        self._socket.listen(8)
        self.host, self.port = self._socket.getsockname()
        self._thread = threading.Thread(target=self._accept_loop, daemon=True)
        self._thread.start()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def close(self) -> None:
        self._stopping = True
        try:
            self._socket.close()
        except OSError:
            pass
        self._thread.join(timeout=2)
        for worker in self._workers:
            worker.join(timeout=2)

    def _accept_loop(self) -> None:
        self._socket.settimeout(0.1)
        while not self._stopping:
            try:
                connection, _ = self._socket.accept()
            except TimeoutError:
                continue
            except OSError:
                return
            with self._lock:
                self.accepts += 1
            worker = threading.Thread(
                target=self._handle_client,
                args=(connection,),
                daemon=True,
            )
            self._workers.append(worker)
            worker.start()

    def _handle_client(self, connection: socket.socket) -> None:
        try:
            with connection:
                connection.settimeout(0.2)
                buffer = b""
                while not self._stopping:
                    try:
                        data = connection.recv(4096)
                    except TimeoutError:
                        continue
                    if not data:
                        self.client_closed.set()
                        return
                    buffer += data
                    while b"\n" in buffer:
                        raw, buffer = buffer.split(b"\n", 1)
                        command = raw.decode("utf-8")
                        with self._lock:
                            self.commands.append(command)
                            reply = self._reply(command)
                        connection.sendall(reply)
        except OSError:
            if not self._stopping:
                self.client_closed.set()
        except Exception as exc:  # noqa: BLE001 - keep unexpected mock failures on the server.
            self.error = exc

    def _reply(self, command: str) -> bytes:
        if command == "GET multiline":
            return b"$6\r\nMay\nur\r\n"
        if command.startswith("INCR "):
            return b":1\r\n"

        parts = command.split(" ", 2)
        if len(parts) == 3 and parts[0] == "SET":
            self._values[parts[1]] = parts[2]
            return b"+OK\r\n"
        if len(parts) >= 2 and parts[0] == "GET":
            value = self._values.get(parts[1])
            if value is None:
                return b"$-1\r\n"
            payload = value.encode("utf-8")
            return f"${len(payload)}\r\n".encode("ascii") + payload + b"\r\n"
        return b"-ERR unknown command\r\n"


def test_ping_and_malformed_requests_keep_existing_contract() -> None:
    ping = handle_request({"command": "ping"})
    assert ping == {
        "status": True,
        "message": "BMis python backend is running",
    }

    missing = handle_request({})
    assert missing == {
        "status": False,
        "error": "Command must be a non-empty string",
    }

    unknown = handle_request({"command": "unknown"})
    assert unknown == {"status": False, "error": "Invalid command: unknown"}

    for payload in (None, [], "hello", 123, True):
        response = handle_request(payload)
        assert response == {
            "status": False,
            "error": "Request must be a JSON object",
        }


def test_bmis_text_is_not_accepted_as_a_desktop_operation() -> None:
    response = handle_request({"command": "SET desktop_test Mayur"})

    assert response == {
        "status": False,
        "error": "Invalid command: SET desktop_test Mayur",
    }


def test_stateful_command_without_session_does_not_connect() -> None:
    with MockBMisServer() as server:
        response = handle_request(_connect_request(server.host, server.port))

        assert response == {"status": False, "error": "No active session"}
        assert not server.client_closed.wait(0.2)
        assert server.accepts == 0


def test_connect_status_execute_and_disconnect() -> None:
    with MockBMisServer() as server:
        session = BackendSession(client_factory=_fast_client)
        try:
            disconnected = handle_request({"command": "status"}, session)
            assert disconnected == {
                "status": True,
                "connected": False,
                "host": None,
                "port": None,
            }

            connected = handle_request(
                _connect_request(server.host, server.port),
                session,
            )
            assert connected == {
                "status": True,
                "connected": True,
                "host": server.host,
                "port": server.port,
            }

            ping = handle_request({"command": "ping"}, session)
            assert ping["status"] is True

            stored = handle_request(
                {"command": "execute", "request": "SET desktop_test Mayur"},
                session,
            )
            assert stored == {"status": True, "result": "OK"}

            fetched = handle_request(
                {"command": "execute", "request": "GET desktop_test"},
                session,
            )
            assert fetched == {"status": True, "result": "Mayur"}

            status = handle_request({"command": "status"}, session)
            assert status["connected"] is True

            disconnected = handle_request({"command": "disconnect"}, session)
            assert disconnected == {
                "status": True,
                "connected": False,
                "host": None,
                "port": None,
            }

            after = handle_request({"command": "status"}, session)
            assert after["connected"] is False
            assert server.commands == [
                "SET desktop_test Mayur",
                "GET desktop_test",
            ]
            assert server.error is None
        finally:
            session.close()


def test_multiple_operations_use_the_same_connection() -> None:
    with MockBMisServer() as server:
        session = BackendSession(client_factory=_fast_client)
        try:
            assert handle_request(
                _connect_request(server.host, server.port),
                session,
            )["status"] is True

            assert handle_request(
                {"command": "execute", "request": "SET desktop_test Mayur"},
                session,
            )["result"] == "OK"
            assert handle_request(
                {"command": "execute", "request": "GET desktop_test"},
                session,
            )["result"] == "Mayur"
            assert handle_request(
                {"command": "execute", "request": "GET missing"},
                session,
            )["result"] is None
            assert handle_request(
                {"command": "execute", "request": "INCR desktop_test"},
                session,
            )["result"] == 1
            multiline = handle_request(
                {"command": "execute", "request": "GET multiline"},
                session,
            )

            assert multiline["result"] == "May\nur"
            assert "\n" not in json.dumps(multiline)
            assert server.accepts == 1
        finally:
            session.close()


@pytest.mark.parametrize(
    ("host", "message"),
    [
        ("", "Host must be a non-empty hostname or IP address"),
        ("   ", "Host must be a non-empty hostname or IP address"),
        (None, "Host must be a non-empty hostname or IP address"),
        (127, "Host must be a non-empty hostname or IP address"),
        ("bad host", "Host must be a non-empty hostname or IP address"),
        ("local/host", "Host must be a non-empty hostname or IP address"),
        ("127.0.0.1\nSET x", "Host cannot contain newline characters"),
        ("127.0.0.1\rSET x", "Host cannot contain newline characters"),
    ],
)
def test_rejects_invalid_host(host: object, message: str) -> None:
    created: list[tuple[str, int]] = []

    def factory(host_arg: str, port: int) -> BMisClient:
        created.append((host_arg, port))
        return _fast_client(host_arg, port)

    session = BackendSession(client_factory=factory)
    response = handle_request(
        {"command": "connect", "host": host, "port": 6379},
        session,
    )

    assert response == {"status": False, "error": message}
    assert created == []


@pytest.mark.parametrize(
    "port",
    [0, -1, 65536, True, False, "6379", 6379.0, None, [], {}],
)
def test_rejects_invalid_port(port: object) -> None:
    created: list[int] = []

    def factory(host: str, port_arg: int) -> BMisClient:
        created.append(port_arg)
        return _fast_client(host, port_arg)

    session = BackendSession(client_factory=factory)
    response = handle_request(
        {"command": "connect", "host": "127.0.0.1", "port": port},
        session,
    )

    assert response == {
        "status": False,
        "error": "Port must be an integer between 1 and 65535",
    }
    assert created == []


@pytest.mark.parametrize("request_value", ["", "   ", None, 1, [], {}])
def test_rejects_empty_bmis_command(request_value: object) -> None:
    session = BackendSession()
    response = handle_request(
        {"command": "execute", "request": request_value},
        session,
    )

    assert response == {
        "status": False,
        "error": "Request must be a non-empty string",
    }


def test_rejects_newline_injection_in_bmis_command() -> None:
    with MockBMisServer() as server:
        session = BackendSession(client_factory=_fast_client)
        try:
            assert handle_request(
                _connect_request(server.host, server.port),
                session,
            )["status"] is True

            response = handle_request(
                {"command": "execute", "request": "SET desktop_test Mayur\nDEL desktop_test"},
                session,
            )

            assert response == {
                "status": False,
                "error": "Request cannot contain newline characters",
            }
            assert server.commands == []
            fetched = handle_request(
                {"command": "execute", "request": "GET desktop_test"},
                session,
            )
            assert fetched == {"status": True, "result": None}
        finally:
            session.close()


def test_connection_refused_is_not_reported_as_success() -> None:
    session = BackendSession(client_factory=_fast_client)
    try:
        response = handle_request(
            _connect_request("127.0.0.1", _closed_port()),
            session,
        )

        assert response["status"] is False
        assert response["error"] == "Unable to connect to BMis: Connection refused"
        assert "connected" not in response
        assert "Traceback" not in json.dumps(response)

        status = handle_request({"command": "status"}, session)
        assert status["connected"] is False
    finally:
        session.close()


def test_connect_success_requires_client_connect() -> None:
    class IdleClient(BMisClient):
        def __init__(self, host: str, port: int) -> None:
            super().__init__(host, port)
            self.was_closed = False

        def connect(self) -> None:
            return

        def close(self) -> None:
            self.was_closed = True
            super().close()

    created: list[IdleClient] = []

    def factory(host: str, port: int) -> IdleClient:
        client = IdleClient(host, port)
        created.append(client)
        return client

    session = BackendSession(client_factory=factory)
    response = handle_request(_connect_request("127.0.0.1", 6379), session)

    assert response == {"status": False, "error": "Unable to connect to BMis"}
    assert created[0].was_closed is True
    assert handle_request({"command": "status"}, session)["connected"] is False


def test_connect_failure_does_not_expose_exception_text() -> None:
    class SecretClient(BMisClient):
        def __init__(self, host: str, port: int) -> None:
            super().__init__(host, port)
            self.was_closed = False

        def connect(self) -> None:
            raise RuntimeError("secret traceback detail")

        def close(self) -> None:
            self.was_closed = True
            super().close()

    created: list[SecretClient] = []

    def factory(host: str, port: int) -> SecretClient:
        client = SecretClient(host, port)
        created.append(client)
        return client

    session = BackendSession(client_factory=factory)
    response = handle_request(_connect_request("127.0.0.1", 6379), session)

    assert response == {"status": False, "error": "Unable to connect to BMis"}
    assert "secret" not in json.dumps(response)
    assert created[0].was_closed is True
    assert handle_request({"command": "status"}, session)["connected"] is False


def test_reconnect_closes_the_previous_client_first() -> None:
    with MockBMisServer() as first, MockBMisServer() as second:
        session = BackendSession(client_factory=_fast_client)
        try:
            assert handle_request(
                _connect_request(first.host, first.port),
                session,
            )["status"] is True
            assert handle_request(
                _connect_request(second.host, second.port),
                session,
            )["status"] is True

            assert first.client_closed.wait(2)
            stored = handle_request(
                {"command": "execute", "request": "SET desktop_test Mayur"},
                session,
            )
            assert stored["result"] == "OK"
            assert first.commands == []
            assert second.commands == ["SET desktop_test Mayur"]
        finally:
            session.close()


def test_failed_reconnect_leaves_the_session_disconnected() -> None:
    with MockBMisServer() as server:
        session = BackendSession(client_factory=_fast_client)
        try:
            assert handle_request(
                _connect_request(server.host, server.port),
                session,
            )["status"] is True

            failed = handle_request(
                _connect_request("127.0.0.1", _closed_port()),
                session,
            )

            assert failed["status"] is False
            assert str(failed["error"]).startswith("Unable to connect to BMis")
            assert server.client_closed.wait(2)
            status = handle_request({"command": "status"}, session)
            assert status["connected"] is False
            execute = handle_request(
                {"command": "execute", "request": "GET desktop_test"},
                session,
            )
            assert execute == {"status": False, "error": "Not connected to BMis"}
        finally:
            session.close()


def test_invalid_connect_does_not_drop_the_current_client() -> None:
    with MockBMisServer() as server:
        session = BackendSession(client_factory=_fast_client)
        try:
            assert handle_request(
                _connect_request(server.host, server.port),
                session,
            )["status"] is True

            rejected = handle_request(
                {"command": "connect", "host": "bad host", "port": 1},
                session,
            )

            assert rejected["status"] is False
            stored = handle_request(
                {"command": "execute", "request": "SET desktop_test Mayur"},
                session,
            )
            assert stored == {"status": True, "result": "OK"}
            assert server.accepts == 1
        finally:
            session.close()


def test_execute_when_not_connected() -> None:
    session = BackendSession()
    response = handle_request(
        {"command": "execute", "request": "GET desktop_test"},
        session,
    )

    assert response == {"status": False, "error": "Not connected to BMis"}


def test_execute_when_server_closes_the_connection() -> None:
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    host, port = server.getsockname()

    def worker() -> None:
        connection, _ = server.accept()
        connection.recv(1024)
        connection.close()

    thread = threading.Thread(target=worker)
    thread.start()
    session = BackendSession(client_factory=_fast_client)
    try:
        assert handle_request(_connect_request(host, port), session)["status"] is True
        response = handle_request(
            {"command": "execute", "request": "GET desktop_test"},
            session,
        )

        assert response == {
            "status": False,
            "error": "BMis server closed the connection",
        }
        assert "Traceback" not in json.dumps(response)
        status = handle_request({"command": "status"}, session)
        assert status["connected"] is False
    finally:
        session.close()
        thread.join(timeout=2)
        server.close()


def test_execute_timeout_disconnects_the_session() -> None:
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    host, port = server.getsockname()
    release = threading.Event()

    def worker() -> None:
        connection, _ = server.accept()
        with connection:
            connection.recv(1024)
            release.wait(timeout=3)

    def factory(client_host: str, client_port: int) -> BMisClient:
        return BMisClient(client_host, client_port, connect_timeout=1.0, socket_timeout=0.2)

    thread = threading.Thread(target=worker)
    thread.start()
    session = BackendSession(client_factory=factory)
    try:
        assert handle_request(_connect_request(host, port), session)["status"] is True
        response = handle_request(
            {"command": "execute", "request": "GET desktop_test"},
            session,
        )

        assert response == {
            "status": False,
            "error": "Timed out waiting for BMis response",
        }
        status = handle_request({"command": "status"}, session)
        assert status["connected"] is False
    finally:
        session.close()
        release.set()
        thread.join(timeout=2)
        server.close()


def test_unexpected_execute_error_hides_exception_details() -> None:
    class ExplodingClient(BMisClient):
        def execute(self, command: str) -> object:
            raise RuntimeError("secret traceback detail")

    with MockBMisServer() as server:
        session = BackendSession(
            client_factory=lambda host, port: ExplodingClient(
                host,
                port,
                connect_timeout=1.0,
                socket_timeout=1.0,
            )
        )
        try:
            assert handle_request(
                _connect_request(server.host, server.port),
                session,
            )["status"] is True
            response = handle_request(
                {"command": "execute", "request": "GET desktop_test"},
                session,
            )

            assert response == {"status": False, "error": "BMis command failed"}
            assert "secret" not in json.dumps(response)
            assert "Traceback" not in json.dumps(response)
            assert handle_request({"command": "status"}, session)["connected"] is False
        finally:
            session.close()


def test_invalid_server_response_is_a_safe_error() -> None:
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    host, port = server.getsockname()

    def worker() -> None:
        connection, _ = server.accept()
        connection.recv(1024)
        connection.sendall(b"?nope\r\n")
        connection.close()

    thread = threading.Thread(target=worker)
    thread.start()
    session = BackendSession(client_factory=_fast_client)
    try:
        assert handle_request(_connect_request(host, port), session)["status"] is True
        response = handle_request(
            {"command": "execute", "request": "GET desktop_test"},
            session,
        )

        assert response == {"status": False, "error": "Invalid BMis response"}
        assert handle_request({"command": "status"}, session)["connected"] is False
    finally:
        session.close()
        thread.join(timeout=2)
        server.close()


def test_session_close_is_safe_and_idempotent() -> None:
    with MockBMisServer() as server:
        session = BackendSession(client_factory=_fast_client)
        assert handle_request(
            _connect_request(server.host, server.port),
            session,
        )["status"] is True

        session.close()
        session.close()

        assert server.client_closed.wait(2)
        status = handle_request({"command": "status"}, session)
        assert status == {
            "status": True,
            "connected": False,
            "host": None,
            "port": None,
        }
        again = handle_request({"command": "disconnect"}, session)
        assert again["connected"] is False


def test_main_closes_the_session_when_stdin_ends(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path,
) -> None:
    monkeypatch.setenv(PROFILE_DATABASE_ENV, str(tmp_path / "profiles.db"))
    class TrackingSession(BackendSession):
        def __init__(self) -> None:
            super().__init__()
            instances.append(self)
            self.close_count = 0

        def close(self) -> None:
            self.close_count += 1
            super().close()

    instances: list[TrackingSession] = []

    with MockBMisServer() as server:
        payload = "\n".join(
            [
                json.dumps(_connect_request(server.host, server.port)),
                json.dumps(
                    {"command": "execute", "request": "SET desktop_test Mayur"}
                ),
                json.dumps({"command": "status"}),
            ]
        ) + "\n"
        monkeypatch.setattr("bmis_desktop.main.BackendSession", TrackingSession)
        monkeypatch.setattr(sys, "stdin", io.StringIO(payload))

        main()

        captured = capsys.readouterr()
        responses = [json.loads(line) for line in captured.out.splitlines()]
        assert captured.err == ""
        assert responses[0]["connected"] is True
        assert responses[1]["result"] == "OK"
        assert responses[2]["connected"] is True
        assert len(instances) == 1
        # Connect closes any previous client, then process shutdown closes the live one.
        assert instances[0].close_count == 2
        assert server.client_closed.wait(2)
        status = instances[0].handle_request({"command": "status"})
        assert status["connected"] is False
        assert server.commands == ["SET desktop_test Mayur"]
        assert server.error is None


def test_main_stdout_carries_only_json_lines(tmp_path) -> None:
    with MockBMisServer() as server:
        payload = "\n".join(
            [
                "{invalid}",
                json.dumps({"command": "ping"}),
                json.dumps(_connect_request(server.host, server.port)),
                json.dumps(
                    {"command": "execute", "request": "SET desktop_test Mayur"}
                ),
                json.dumps(
                    {"command": "execute", "request": "GET desktop_test"}
                ),
                json.dumps({"command": "disconnect"}),
                json.dumps({"command": "status"}),
            ]
        ) + "\n"
        env = os.environ.copy()
        env[PROFILE_DATABASE_ENV] = str(tmp_path / "profiles.db")
        process = subprocess.run(
            [sys.executable, "-m", "bmis_desktop.main"],
            input=payload,
            text=True,
            capture_output=True,
            check=False,
            env=env,
        )

        assert process.returncode == 0
        assert process.stderr == ""
        assert "Traceback" not in process.stdout
        responses = [json.loads(line) for line in process.stdout.splitlines()]
        assert responses == [
            {"status": False, "error": "Invalid JSON"},
            {
                "status": True,
                "message": "BMis python backend is running",
            },
            {
                "status": True,
                "connected": True,
                "host": server.host,
                "port": server.port,
            },
            {"status": True, "result": "OK"},
            {"status": True, "result": "Mayur"},
            {
                "status": True,
                "connected": False,
                "host": None,
                "port": None,
            },
            {
                "status": True,
                "connected": False,
                "host": None,
                "port": None,
            },
        ]
        assert server.client_closed.wait(2)


def test_profile_commands_keep_the_existing_connection(tmp_path) -> None:
    repository = ConnectionProfileRepository(tmp_path / "profiles.db")
    with MockBMisServer() as server:
        session = BackendSession(client_factory=_fast_client)
        try:
            connected = handle_backend_request(
                _connect_request(server.host, server.port),
                session,
                repository,
            )
            assert connected["status"] is True
            assert connected["connected"] is True

            saved = handle_backend_request(
                {
                    "command": "create_profile",
                    "name": "Local",
                    "host": server.host,
                    "port": server.port,
                },
                session,
                repository,
            )
            assert saved["status"] is True

            ping = handle_backend_request({"command": "ping"}, session, repository)
            assert ping == {
                "status": True,
                "message": "BMis python backend is running",
            }
            stored = handle_backend_request(
                {"command": "execute", "request": "SET desktop_test Mayur"},
                session,
                repository,
            )
            assert stored == {"status": True, "result": "OK"}
            status = handle_backend_request({"command": "status"}, session, repository)
            assert status["connected"] is True
            assert server.commands == ["SET desktop_test Mayur"]
            assert server.error is None
        finally:
            session.close()


def test_handle_request_hides_unexpected_exceptions(monkeypatch: pytest.MonkeyPatch) -> None:
    session = BackendSession()

    def explode(request: object) -> dict[str, object]:
        raise RuntimeError("secret traceback detail")

    monkeypatch.setattr(session, "_handle_request", explode)
    response = session.handle_request({"command": "ping"})

    assert response == {"status": False, "error": "Internal error"}
    assert "secret" not in json.dumps(response)


@pytest.mark.integration
def test_session_set_and_get_against_real_bmis_server() -> None:
    session = BackendSession()
    try:
        connected = handle_request(_connect_request("127.0.0.1", 6379), session)
        assert connected["status"] is True
        assert connected["connected"] is True

        stored = handle_request(
            {"command": "execute", "request": "SET desktop_test Mayur"},
            session,
        )
        fetched = handle_request(
            {"command": "execute", "request": "GET desktop_test"},
            session,
        )

        assert stored == {"status": True, "result": "OK"}
        assert fetched == {"status": True, "result": "Mayur"}
    finally:
        session.close()
