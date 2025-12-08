# client.py
import argparse, socket, json, sys


def send_request(sock: socket.socket, payload: dict) -> dict:
    """
    Send a single JSON-line request over an existing socket
    and return the JSON-line response.
    """
    # Encode the payload as JSON with newline delimiter
    data = (json.dumps(payload, ensure_ascii=False) + "\n").encode("utf-8")

    # Send the request
    sock.sendall(data)

    # Read the response
    buff = b""
    while True:
        chunk = sock.recv(4096)
        if not chunk:
            # Server closed connection
            return {"ok": False, "error": "Server closed connection"}
        buff += chunk

        # Check if we received a complete line (message)
        if b"\n" in buff:
            line, _, _ = buff.partition(b"\n")
            return json.loads(line.decode("utf-8"))


PRE_MADE_EXPR = {"2 plus 2": "2+2"}


def interactive_mode(host: str, port: int):
    """
    CHANGE 1: New function for interactive mode with persistent connection.
    Allows user to send multiple requests over the same TCP connection.
    """
    print(f"Connecting to {host}:{port}...")

    try:
        # CHANGE 2: Create a persistent socket connection (no 'with' statement yet)
        sock = socket.create_connection((host, port), timeout=10)
        print("Connected! You can now send multiple requests.")
        print("Type 'quit' or 'exit' to close the connection.\n")

        try:
            while True:
                # Ask user what type of request to send
                print("\n" + "=" * 50)
                print("Choose mode:")
                print(" 1. calc - Evaluate mathematical expression")
                print(" 2. gpt - Send prompt to GPT")
                print(" 3. quit - Close connection and exit")
                print("=" * 50)

                choice = input("Enter choice (calc/gpt/quit): ").strip()

                if choice == "quit" or choice.lower() in "exit":
                    print("Closing connection...")
                    break

                # Build payload based on user choice
                payload = None

                if choice == "calc":
                    choose = input("Type 1 for a premade expression or 2 for your own: ").strip()
                    if choose == "2":
                        expr = input("Enter an expression of your choise: ")
                        if not expr:
                            print("Empty expression, skipping...")
                            continue
                        payload = {
                            "mode": "calc",
                            "data": {"expr": expr},
                            "options": {"cache": True}
                        }
                    elif choose == "1":
                        print("choose from a library of premade expressions:")
                        print(PRE_MADE_EXPR)
                        pre_made_expr = str(input("enter your choise: "))

                        if pre_made_expr in PRE_MADE_EXPR:
                            payload = {
                                "mode": "calc",
                                "data": {"expr": str(PRE_MADE_EXPR[pre_made_expr])},
                                "options": {"cache": True}
                            }
                    else:
                        raise ValueError("illegal constant type")

                elif choice == "2":
                    prompt = input("Enter GPT prompt: ").strip()
                    if not prompt:
                        print("Empty prompt, skipping...")
                        continue
                    payload = {
                        "mode": "gpt",
                        "data": {"prompt": prompt},
                        "options": {"cache": True}
                    }

                else:
                    print("Invalid choice, please try again.")
                    continue

                # CHANGE 3: Send request on the SAME socket (persistent connection)
                print(f"\nSending request: {payload['mode']}")
                resp = send_request(sock, payload)

                # Display response
                print("\n--- Response ---")
                print(json.dumps(resp, ensure_ascii=False, indent=2))

                if resp.get("ok"):
                    print(f"\nResult: {resp['result']}")
                    if resp.get("meta", {}).get("from_cache"):
                        print("(Retrieved from cache)")
                else:
                    print(f"Error: {resp.get('error')}")

        finally:
            # CHANGE 4: Properly close the socket when done
            sock.close()
            print("\nConnection closed.")

    except Exception as e:
        print(f"Connection error: {e}", file=sys.stderr)
        sys.exit(1)


def single_request_mode(host: str, port: int, mode: str, expr: str = None, prompt: str = None, no_cache: bool = False):
    """
    CHANGE 5: Legacy mode for single request (backward compatibility).
    This opens a connection, sends ONE request, and closes.
    """
    # Build the payload
    if mode == "calc":
        if not expr:
            print("Missing --expr", file=sys.stderr)
            sys.exit(2)
        payload = {
            "mode": "calc",
            "data": {"expr": expr},
            "options": {"cache": not no_cache}
        }
    else: # gpt
        if not prompt:
            print("Missing --prompt", file=sys.stderr)
            sys.exit(2)
        payload = {
            "mode": "gpt",
            "data": {"prompt": prompt},
            "options": {"cache": not no_cache}
        }

    # Send single request and close
    try:
        with socket.create_connection((host, port), timeout=5) as sock:
            resp = send_request(sock, payload)
            print(json.dumps(resp, ensure_ascii=False, indent=2))
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def main():
    ap = argparse.ArgumentParser(
        description="Client (calc/gpt over JSON TCP) with persistent connection support"
    )
    ap.add_argument("--host", default="127.0.0.1", help="Server host")
    ap.add_argument("--port", type=int, default=5555, help="Server port")

    # CHANGE 6: Add --interactive flag for persistent connection mode
    ap.add_argument(
        "--interactive", "-i",
        action="store_true",
        help="Interactive mode: send multiple requests on the same connection"
    )

    # Legacy single-request arguments
    ap.add_argument("--mode", choices=["calc", "gpt"], help="Request mode (calc or gpt)")
    ap.add_argument("--expr", help="Expression for mode=calc")
    ap.add_argument("--prompt", help="Prompt for mode=gpt")
    ap.add_argument("--no-cache", action="store_true", help="Disable caching")

    args = ap.parse_args()

    # CHANGE 7: Choose between interactive and single-request mode
    if args.interactive:
        # New persistent connection mode
        interactive_mode(args.host, args.port)
    else:
        # Legacy single-request mode (for backward compatibility)
        if not args.mode:
            print("Error: --mode required in non-interactive mode", file=sys.stderr)
            print("Use --interactive or -i for interactive mode", file=sys.stderr)
            sys.exit(2)
        single_request_mode(
            args.host, args.port, args.mode,
            args.expr, args.prompt, args.no_cache
        )


if __name__ == "__main__":
    main()
