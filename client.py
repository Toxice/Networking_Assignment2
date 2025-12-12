# client.py
import argparse, socket, json, sys


# sending the request bytes over the defined IP address and Port (Socket) and partition it as defined
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


PRE_MADE_EXPR = {"1": "2+2", "2": "5+7", "3": "sin(10)", "4": "12*3"}

'''
Persistent TCP Mode, enables sending multiple TCP request over the same Socket without having to close and reopen the connection
works by letting the user choose between 3 options:
calc - for calculations
gpt - for sending a prompt to ChatGPT over the OpenAI API
quit - closing the connection
'''
def persistent_mode(host: str, port: int):

    print(f"Connecting to {host}:{port}...")

    try:
        # Create a persistent socket connection
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

                if choice == "quit":
                    print("Closing connection...")
                    break

                # Build payload based on user choice
                payload = None

                if choice == "calc":
                    payload = calc_mode()

                elif choice == "gpt":
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

                # Send request on the SAME socket (persistent connection)
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
            sock.close()
            print("\nConnection closed.")

    except Exception as e:
        print(f"Connection error: {e}", file=sys.stderr)
        sys.exit(1)


# calculation mode - sends data for calculation and retrieves the answer
def calc_mode():
    choose: str = input("Type expr for your own kind of expression or pre made for a premade expression: ").strip()

    if choose == "expr":
        expr = input("Enter an expression of your choice: ")
        if not expr:
            print("Empty expression, skipping...")

        payload = {
            "mode": "calc",
            "data": {"expr": expr},
            "options": {"cache": True}
        }
        return payload

    elif choose == "pre made":
        print("choose from a library of premade expressions:")
        print(PRE_MADE_EXPR)

        pre_made_expr = input("enter your choice: ")

        if pre_made_expr in PRE_MADE_EXPR:
            payload = {
                "mode": "calc",
                "data": {"expr": str(PRE_MADE_EXPR[pre_made_expr])},
                "options": {"cache": True}
            }
            return payload
    else:
        raise ValueError("illegal constant type")


"""
    Legacy mode for single request (backward compatibility).
    This opens a connection, sends ONE request, and closes.
"""


def single_request_mode(host: str, port: int, mode: str, expr: str = None, prompt: str = None, no_cache: bool = False):
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
    else:  # gpt
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

    # a command flag for setting a persistent mode
    ap.add_argument(
        "--p", "--persistent",
        action="store_true",
        help="Persistent mode: send multiple requests on the same connection"
    )

    # Legacy single-request arguments
    ap.add_argument("--mode", choices=["calc", "gpt"], help="Request mode (calc or gpt)")
    ap.add_argument("--expr", help="Expression for mode=calc")
    ap.add_argument("--prompt", help="Prompt for mode=gpt")
    ap.add_argument("--no-cache", action="store_true", help="Disable caching")

    args = ap.parse_args()

    # Choose between persistent and single-request mode
    if args.p:
        # New persistent connection mode
        persistent_mode(args.host, args.port)
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
