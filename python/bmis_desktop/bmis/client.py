import socket
from bmis_desktop.bmis.protocol import INCOMPLETE, ProtocolParser
class BMisClient:
    def __init__(
        self,
        host: str,
        port: int,
        connect_timeout: float = 5.0,
        socket_timeout: float = 5.0,
    ) -> None:
        if connect_timeout <= 0 or socket_timeout <= 0:
            raise ValueError("Timeouts must be positive")

        self.host = host
        self.port = port
        self.connect_timeout = connect_timeout
        self.socket_timeout = socket_timeout
        self._socket: socket.socket | None = None
        self._parser = ProtocolParser()

    def connect(self) -> None:
        if self._socket is not None:
            raise RuntimeError("Client is already connected")

        connection = socket.create_connection(
            (self.host, self.port),
            timeout=self.connect_timeout,
        )

        connection.settimeout(self.socket_timeout)
        self._socket = connection

    def is_connected(self) -> bool:
        return self._socket is not None

    def execute(self, command: str):
        if not isinstance(command, str) or not command.strip():
            raise ValueError("Command cannot be empty")

        if "\n" in command or "\r" in command:
            raise ValueError("Command cannot contain newline characters")

        if self._socket is None:
            raise RuntimeError("Client is not connected")

        try:
            self._socket.sendall(f"{command}\n".encode("utf-8"))

            while True:
                data = self._socket.recv(4096)

                if not data:
                    self.close()
                    raise ConnectionError(
                        "BMis server closed the connection"
                    )

                response = self._parser.feed(data)

                if response is not INCOMPLETE:
                    return response

        except socket.timeout:
            self.close()
            raise



    def close(self) -> None:
        connection = self._socket
        self._socket = None
        self._parser = ProtocolParser()

        if connection is not None:
            connection.close()
