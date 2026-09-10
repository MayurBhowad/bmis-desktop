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