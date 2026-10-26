"""Read the live dashboard stream (server-sent events) from the command line.

    uv run python examples/sse_client.py --email admin@example.com

Signs in through auth-service (POST /auth/login), then reads GET /api/dashboard/stream
through nginx and prints every event: `snapshot` (the dashboard numbers as JSON), a
`: ping` heartbeat while idle, and `reauth` when the token expires. Uses httpx (already
a dependency). Stop with Ctrl+C."""

import argparse
import getpass
import json

import httpx


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--base-url", default="http://localhost", help="nginx (or Vite) URL")
    parser.add_argument("--email", required=True)
    args = parser.parse_args()
    password = getpass.getpass("Password: ")  # never on the command line

    with httpx.Client(base_url=args.base_url, timeout=None) as client:
        login = client.post("/auth/login", json={"email": args.email, "password": password})
        login.raise_for_status()
        token = login.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}", "Accept": "text/event-stream"}
        with client.stream("GET", "/api/dashboard/stream", headers=headers) as stream:
            stream.raise_for_status()
            event = "message"
            for line in stream.iter_lines():
                if line.startswith(":"):
                    print("(heartbeat)")
                elif line.startswith("event:"):
                    event = line.split(":", 1)[1].strip()
                elif line.startswith("data:"):
                    data = line.split(":", 1)[1].strip()
                    if event == "snapshot":
                        print(json.dumps(json.loads(data), indent=2))
                    else:
                        print(f"{event}: {data}")
                    if event == "reauth":
                        print("Token expired: run again to sign in.")
                        return


if __name__ == "__main__":
    main()
