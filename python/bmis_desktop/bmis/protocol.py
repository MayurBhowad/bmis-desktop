class ProtocolError(Exception):
    """Raised when a BMis protocol response is invalid."""


def decode_response(data: bytes):
    if not data:
        raise ProtocolError("Empty response")

    response = data.decode("utf-8")

    if response.startswith("+"):
        return response[1:].rstrip("\r\n")

    if response.startswith(":"):
        return int(response[1:].rstrip("\r\n"))

    if response.startswith("-"):
        return response[1:].rstrip("\r\n")

    if response.startswith("$"):
        lines = response.split("\r\n")

        length = int(lines[0][1:])

        if length == -1:
            return None

        return lines[1]

    if response.startswith("*"):
        lines = response.split("\r\n")
        count = int(lines[0][1:])

        result = []
        index = 1

        for _ in range(count):
            length = int(lines[index][1:])
            index += 1

            if length == -1:
                result.append(None)
            else:
                result.append(lines[index])
                index += 1

        return result

    raise ProtocolError("Unknown response type")




class ProtocolParser:
    def __init__(self):
        self._buffer = bytearray()

    def feed(self, data: bytes):
        self._buffer.extend(data)

        response = self._parse_response()

        if response is None:
            return None

        return response

    def _parse_response(self):
        if not self._buffer:
            return None

        response_type = chr(self._buffer[0])

        if response_type == "+":
            return self._parse_simple_string()

        if response_type == ":":
            return self._parse_integer()

        if response_type == "$":
            return self._parse_bulk_string()

        if response_type == "*":
            return self._parse_array()

        if response_type == "-":
            return self._parse_error()

        raise ProtocolError(f"Unknown response type: {response_type}")

    def _find_crlf(self):
        index = self._buffer.find(b"\r\n")

        if index == -1:
            return None

        return index

    def _parse_simple_string(self):
        end = self._find_crlf()

        if end is None:
            return None

        value = bytes(self._buffer[1:end]).decode("utf-8")
        del self._buffer[:end + 2]

        return value

    def _parse_integer(self):
        end = self._find_crlf()

        if end is None:
            return None

        value = int(bytes(self._buffer[1:end]))
        del self._buffer[:end + 2]

        return value

    def _parse_error(self):
        end = self._find_crlf()

        if end is None:
            return None

        value = bytes(self._buffer[1:end]).decode("utf-8")
        del self._buffer[:end + 2]

        return value

    def _parse_bulk_string(self):
        header_end = self._find_crlf()

        if header_end is None:
            return None

        length = int(bytes(self._buffer[1:header_end]))

        if length == -1:
            del self._buffer[:header_end + 2]
            return None

        data_start = header_end + 2
        data_end = data_start + length

        if len(self._buffer) < data_end + 2:
            return None

        if self._buffer[data_end:data_end + 2] != b"\r\n":
            raise ProtocolError("Invalid bulk string terminator")

        value = bytes(self._buffer[data_start:data_end]).decode("utf-8")
        del self._buffer[:data_end + 2]

        return value

    def _parse_array(self):
        header_end = self._find_crlf()

        if header_end is None:
            return None

        count = int(bytes(self._buffer[1:header_end]))

        if count < 0:
            del self._buffer[:header_end + 2]
            return None

        position = header_end + 2
        result = []

        for _ in range(count):
            if position >= len(self._buffer):
                return None

            if self._buffer[position:position + 1] != b"$":
                raise ProtocolError("Only bulk strings are supported in arrays")

            item_header_end = self._buffer.find(b"\r\n", position)

            if item_header_end == -1:
                return None

            length = int(bytes(self._buffer[position + 1:item_header_end]))

            if length < 0:
                result.append(None)
                position = item_header_end + 2
                continue

            item_start = item_header_end + 2
            item_end = item_start + length

            if len(self._buffer) < item_end + 2:
                return None

            if self._buffer[item_end:item_end + 2] != b"\r\n":
                raise ProtocolError("Invalid array item terminator")

            result.append(
                bytes(self._buffer[item_start:item_end]).decode("utf-8")
            )
            position = item_end + 2

        del self._buffer[:position]

        return result