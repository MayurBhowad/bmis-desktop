import json
import sys

from bmis_desktop.session import BackendSession, handle_request

__all__ = ["handle_request", "main"]


def _encode_response(response: object) -> str:
    try:
        return json.dumps(response)
    except (TypeError, ValueError):
        return json.dumps(
            {
                "status": False,
                "error": "BMis response could not be encoded",
            }
        )


def main() -> None:
    session = BackendSession()
    try:
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue

            try:
                request = json.loads(line)
            except json.JSONDecodeError:
                response: object = {
                    "status": False,
                    "error": "Invalid JSON",
                }
            else:
                response = handle_request(request, session)

            print(_encode_response(response), flush=True)
    finally:
        session.close()


if __name__ == "__main__":
    main()
