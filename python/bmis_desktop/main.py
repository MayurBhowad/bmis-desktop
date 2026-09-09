import json
import sys


def handle_request(request: dict) -> dict:
    command = request.get("command")

    if command == 'ping':
        return {
            "status": True,
            "message": "BMis python backend is running",
        }

    return {
        "status": False,
        "error": f"Invalid command: {command}",
    }

    
def main():
    for line in sys.stdin:
        line = line.strip()

        if not line:
            continue

        try:
            request = json.loads(line)
            response = handle_request(request)
        except json.JSONDecodeError:
            response = {
                "status": False,
                "error": "Invalid JSON",
            }

        print(json.dumps(response), flush=True)


if __name__ == "__main__":
    main()