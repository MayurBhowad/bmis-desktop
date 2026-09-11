import socket
from bmis_desktop.bmis.protocol import ProtocolParser
class BMisClient:
    def __init__(self, host: str, port: int) -> None:
        self._parser = ProtocolParser()
        self.host = host
        self.port = port
        self._socket: socket.socket | None = None

    def connect(self) -> None:
        self._socket = socket.create_connection((self.host, self.port))

    def is_connected(self) -> bool:
        return self._socket is not None

    def execute(self, command: str):
        if self._socket is None:
            raise RuntimeError("Client is not connected")

        self._socket.sendall(f"{command}\n".encode("utf-8"))

        while True:
            data = self._socket.recv(4096)

            if not data:
                raise ConnectionError("BMis server closed the connection")

            response = self._parser.feed(data)

            if response is not None:
                return response
    
    def close(self) -> None:
        if self._socket is not None:
            self._socket.close()
            self._socket = None
