import json
import sys



def handle_request(request: object) -> dict:
    if not isinstance(request, dict):
        return {
            "status": False,
            "error": "Request must be a JSON object",
        }

    command = request.get("command")

    if not isinstance(command, str) or not command.strip():
        return {
            "status": False,
            "error": "Command must be a non-empty string",
        }

    if command == "ping":
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