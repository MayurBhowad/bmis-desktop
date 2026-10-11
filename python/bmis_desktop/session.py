import json
import re
from collections.abc import Callable

from bmis_desktop.bmis.client import BMisClient
from bmis_desktop.bmis.protocol import ProtocolError

_PING_MESSAGE = "BMis python backend is running"
_STATEFUL_COMMANDS = {"connect", "status", "execute", "disconnect"}
_HOST_PATTERN = re.compile(r"[A-Za-z0-9.:\[\]-]+")
_MAX_HOST_LENGTH = 255
_MIN_PORT = 1
_MAX_PORT = 65535

ClientFactory = Callable[[str, int], BMisClient]


def error_response(message: str) -> dict[str, object]:
    return {"status": False, "error": message}


def _parse_host(value: object) -> tuple[str, None] | tuple[None, str]:
    if not isinstance(value, str):
        return None, "Host must be a non-empty hostname or IP address"
    if "\n" in value or "\r" in value:
        return None, "Host cannot contain newline characters"

    host = value.strip()
    if (
        not host
        or len(host) > _MAX_HOST_LENGTH
        or _HOST_PATTERN.fullmatch(host) is None
    ):
        return None, "Host must be a non-empty hostname or IP address"
    return host, None


def _parse_port(value: object) -> tuple[int, None] | tuple[None, str]:
    if isinstance(value, bool) or not isinstance(value, int):
        return None, "Port must be an integer between 1 and 65535"
    if value < _MIN_PORT or value > _MAX_PORT:
        return None, "Port must be an integer between 1 and 65535"
    return value, None


def _parse_bmis_command(value: object) -> tuple[str, None] | tuple[None, str]:
    if not isinstance(value, str) or not value.strip():
        return None, "Request must be a non-empty string"
    # One BMis command per line. CR/LF would smuggle a second command.
    if "\n" in value or "\r" in value:
        return None, "Request cannot contain newline characters"
    return value, None


def _connection_error_message(exc: OSError) -> str:
    reason = (exc.strerror or "connection failed").replace("\r", " ").replace("\n", " ")
    reason = reason.strip() or "connection failed"
    return f"Unable to connect to BMis: {reason[:200]}"


def _requires_session(request: object) -> bool:
    if not isinstance(request, dict):
        return False
    command = request.get("command")
    return isinstance(command, str) and command in _STATEFUL_COMMANDS


def _default_client(host: str, port: int) -> BMisClient:
    return BMisClient(host, port)


class BackendSession:
    """Retains one BMis client across desktop IPC requests."""

    def __init__(self, client_factory: ClientFactory | None = None) -> None:
        self._client_factory = client_factory or _default_client
        self._client: BMisClient | None = None
        self._host: str | None = None
        self._port: int | None = None

    def handle_request(self, request: object) -> dict[str, object]:
        try:
            return self._handle_request(request)
        except Exception:  # noqa: BLE001 - IPC must not leak unexpected failures.
            return error_response("Internal error")

    def close(self) -> None:
        client = self._client
        self._client = None
        self._host = None
        self._port = None
        if client is None:
            return
        try:
            client.close()
        except Exception:  # noqa: BLE001 - shutdown must not surface cleanup failures.
            return

    def _handle_request(self, request: object) -> dict[str, object]:
        if not isinstance(request, dict):
            return error_response("Request must be a JSON object")

        command = request.get("command")
        if not isinstance(command, str) or not command.strip():
            return error_response("Command must be a non-empty string")

        if command == "ping":
            return {"status": True, "message": _PING_MESSAGE}

        if command == "connect":
            return self._connect(request)

        if command == "status":
            return self._status()

        if command == "execute":
            return self._execute(request)

        if command == "disconnect":
            return self._disconnect()

        return error_response(f"Invalid command: {command}")

    def _connect(self, request: dict[str, object]) -> dict[str, object]:
        host, host_error = _parse_host(request.get("host"))
        if host_error is not None or host is None:
            return error_response(
                host_error or "Host must be a non-empty hostname or IP address"
            )

        port, port_error = _parse_port(request.get("port"))
        if port_error is not None or port is None:
            return error_response(
                port_error or "Port must be an integer between 1 and 65535"
            )

        self.close()
        try:
            client = self._client_factory(host, port)
        except Exception:  # noqa: BLE001 - factory failures stay off the IPC response.
            return error_response("Unable to connect to BMis")

        try:
            client.connect()
        except OSError as exc:
            self._close_client(client)
            return error_response(_connection_error_message(exc))
        except Exception:  # noqa: BLE001 - connect failures must not include tracebacks.
            self._close_client(client)
            return error_response("Unable to connect to BMis")

        if not client.is_connected():
            self._close_client(client)
            return error_response("Unable to connect to BMis")

        self._client = client
        self._host = host
        self._port = port
        return self._connection_state(True)

    def _status(self) -> dict[str, object]:
        if self._connected_client() is None:
            return self._connection_state(False)
        return self._connection_state(True)

    def _execute(self, request: dict[str, object]) -> dict[str, object]:
        bmis_command, command_error = _parse_bmis_command(request.get("request"))
        if command_error is not None or bmis_command is None:
            return error_response(
                command_error or "Request must be a non-empty string"
            )

        client = self._connected_client()
        if client is None:
            return error_response("Not connected to BMis")

        try:
            result = client.execute(bmis_command)
        except UnicodeDecodeError:
            return self._fail_execution("Invalid BMis response")
        except ValueError as exc:
            return error_response(self._value_error_message(exc))
        except TimeoutError:
            return self._fail_execution("Timed out waiting for BMis response")
        except ConnectionError:
            return self._fail_execution("BMis server closed the connection")
        except ProtocolError:
            return self._fail_execution("Invalid BMis response")
        except RuntimeError as exc:
            if str(exc) == "Client is not connected":
                return self._fail_execution("Not connected to BMis")
            return self._fail_execution("BMis command failed")
        except OSError:
            return self._fail_execution("BMis connection failed")
        except Exception:  # noqa: BLE001 - execution failures must not include tracebacks.
            return self._fail_execution("BMis command failed")

        response: dict[str, object] = {"status": True, "result": result}
        try:
            json.dumps(response)
        except (TypeError, ValueError):
            return error_response("BMis response could not be encoded")
        return response

    def _disconnect(self) -> dict[str, object]:
        self.close()
        return self._connection_state(False)

    def _connection_state(self, connected: bool) -> dict[str, object]:
        if not connected:
            return {
                "status": True,
                "connected": False,
                "host": None,
                "port": None,
            }
        return {
            "status": True,
            "connected": True,
            "host": self._host,
            "port": self._port,
        }

    def _connected_client(self) -> BMisClient | None:
        client = self._client
        if client is None:
            return None
        if not client.is_connected():
            self.close()
            return None
        return client

    def _fail_execution(self, message: str) -> dict[str, object]:
        self.close()
        return error_response(message)

    def _value_error_message(self, exc: ValueError) -> str:
        message = str(exc)
        if message == "Command cannot be empty":
            return "Request must be a non-empty string"
        if message == "Command cannot contain newline characters":
            return "Request cannot contain newline characters"
        return "BMis command failed"

    def _close_client(self, client: BMisClient) -> None:
        try:
            client.close()
        except Exception:  # noqa: BLE001 - failed connects must still release the socket.
            return


def handle_request(
    request: object,
    session: BackendSession | None = None,
) -> dict[str, object]:
    if session is not None:
        return session.handle_request(request)
    if _requires_session(request):
        return error_response("No active session")
    return BackendSession().handle_request(request)
