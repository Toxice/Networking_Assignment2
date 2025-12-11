# server.py
'''
Enabling real GPT calls (optional):
1. Install deps: pip install -r requirements.txt.
2. Create a .env file with OPENAI_API_KEY=... .
3. Replace call_gpt() in server.py with the real implementation shown in the comments, or keep the stub.
'''
import argparse, socket, json, time, threading, math, os, ast, operator, collections
from typing import Any, Dict

from dotenv import load_dotenv
from openai import OpenAI


# ---------------- LRU Cache (simple) ----------------
class LRUCache:
    """Minimal LRU cache based on OrderedDict."""

    def __init__(self, capacity: int = 128):
        self.capacity = capacity
        self._d = collections.OrderedDict()

    def get(self, key):
        if key not in self._d:
            return None
        self._d.move_to_end(key)
        return self._d[key]

    def set(self, key, value):
        self._d[key] = value
        self._d.move_to_end(key)
        if len(self._d) > self.capacity:
            self._d.popitem(last=False)


# ---------------- Safe Math Eval (no eval) ----------------
_ALLOWED_FUNCS = {
    "sin": math.sin, "cos": math.cos, "tan": math.tan, "sqrt": math.sqrt,
    "log": math.log, "exp": math.exp, "max": max, "min": min, "abs": abs,
}
_ALLOWED_CONSTS = {"pi": math.pi, "e": math.e}
_ALLOWED_OPS = {
    ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
    ast.Div: operator.truediv, ast.Pow: operator.pow, ast.USub: operator.neg,
    ast.UAdd: operator.pos, ast.FloorDiv: operator.floordiv, ast.Mod: operator.mod,
}


def _eval_node(node):
    """Evaluate a restricted AST node safely."""
    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float)):
            return node.value
        raise ValueError("illegal constant type")
    if hasattr(ast, "Num") and isinstance(node, ast.Num): # legacy fallback
        return node.n
    if isinstance(node, ast.Name):
        if node.id in _ALLOWED_CONSTS:
            return _ALLOWED_CONSTS[node.id]
        raise ValueError(f"unknown symbol {node.id}")
    if isinstance(node, ast.UnaryOp) and type(node.op) in _ALLOWED_OPS:
        return _ALLOWED_OPS[type(node.op)](_eval_node(node.operand))
    if isinstance(node, ast.BinOp) and type(node.op) in _ALLOWED_OPS:
        return _ALLOWED_OPS[type(node.op)](_eval_node(node.left), _eval_node(node.right))
    if isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name) or node.func.id not in _ALLOWED_FUNCS:
            raise ValueError("illegal function call")
        args = [_eval_node(a) for a in node.args]
        return _ALLOWED_FUNCS[node.func.id](*args)
    raise ValueError("illegal expression")


def safe_eval_expr(expr: str) -> float:
    """Parse and evaluate the expression safely using ast (no eval)."""
    tree = ast.parse(expr, mode="eval")
    return float(_eval_node(tree.body))


# ---------------- GPT Call (stub by default) ----------------
   """
    Stub for GPT call – returns a placeholder string.
    Replace this with a real OpenAI call if desired.
    """
def call_gpt_phony(prompt: str) -> str:

    return f"[GPT-STUB] Received a prompt of length {len(prompt)} chars."

def call_gpt(prompt: str) -> str:
    load_dotenv()
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    gpt_model = os.getenv("GPT_MODEL")

    response = client.responses.create(
        model=gpt_model,
        input=prompt
    )

    return response.output_text

# ---------------- Server core ----------------
def handle_request(msg: Dict[str, Any], cache: LRUCache) -> Dict[str, Any]:
    mode = msg.get("mode")
    data = msg.get("data") or {}
    options = msg.get("options") or {}
    use_cache = bool(options.get("cache", True))

    started = time.time()
    cache_key = json.dumps(msg, sort_keys=True)

    if use_cache:
        hit = cache.get(cache_key)
        if hit is not None:
            return {"ok": True, "result": hit,
                    "meta": {"from_cache": True, "took_ms": int((time.time() - started) * 1000)}}

    try:
        if mode == "calc":
            expr = data.get("expr")
            if not expr or not isinstance(expr, str):
                return {"ok": False, "error": "Bad request: 'expr' is required (string)"}
            res = safe_eval_expr(expr)
        elif mode == "gpt":
            prompt = data.get("prompt")
            if not prompt or not isinstance(prompt, str):
                return {"ok": False, "error": "Bad request: 'prompt' is required (string)"}
            res = call_gpt(prompt)
        else:
            return {"ok": False, "error": "Bad request: unknown mode"}

        took = int((time.time() - started) * 1000)
        if use_cache:
            cache.set(cache_key, res)
        return {"ok": True, "result": res, "meta": {"from_cache": False, "took_ms": took}}
    except Exception as e:
        return {"ok": False, "error": f"Server error: {e}"}


def serve(host: str, port: int, cache_size: int):
    cache = LRUCache(cache_size)
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind((host, port))
        s.listen(16)
        print(f"[server] listening on {host}:{port} (cache={cache_size})")
        while True:
            conn, addr = s.accept()
            threading.Thread(target=handle_client, args=(conn, addr, cache), daemon=True).start()


def handle_client(conn: socket.socket, addr, cache: LRUCache):
    """
    MODIFIED: Handle multiple requests on the same connection.
    The connection stays open until:
    1. Client closes the connection (recv returns empty)
    2. An error occurs
    """
    print(f"[server] New connection from {addr}")
    with conn:
        raw = b"" # Buffer to accumulate incoming data
        try:
            while True: # Removed the break - keep processing requests
                # Read data from client
                chunk = conn.recv(4096)

                # Check if client closed connection
                if not chunk:
                    print(f"[server] Client {addr} disconnected")
                    break # Exit loop when client closes connection

                raw += chunk

                # Process ALL complete messages in buffer (loop instead of if)
                # This handles cases where multiple requests arrive in one chunk
                while b"\n" in raw:
                    line, _, raw = raw.partition(b"\n")

                    try:
                        # Parse the JSON request
                        msg = json.loads(line.decode("utf-8"))
                        print(f"[server] Processing request from {addr}: {msg.get('mode')}")

                        # Handle the request and get response
                        resp = handle_request(msg, cache)

                        # Send response back to client
                        out = (json.dumps(resp, ensure_ascii=False) + "\n").encode("utf-8")
                        conn.sendall(out)
                        print(f"[server] Sent response to {addr}")

                    except json.JSONDecodeError as e:
                        # Handle malformed JSON
                        error_resp = {"ok": False, "error": f"Invalid JSON: {e}"}
                        conn.sendall((json.dumps(error_resp) + "\n").encode("utf-8"))
                    except Exception as e:
                        # Handle other errors during request processing
                        error_resp = {"ok": False, "error": f"Processing error: {e}"}
                        conn.sendall((json.dumps(error_resp) + "\n").encode("utf-8"))

        except Exception as e:
            # Handle connection-level errors
            print(f"[server] Error with client {addr}: {e}")
            try:
                conn.sendall((json.dumps({"ok": False, "error": f"Connection error: {e}"}) + "\n").encode("utf-8"))
            except:
                pass


def main():
    ap = argparse.ArgumentParser(description="JSON TCP server (calc/gpt) – student skeleton")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=5555)
    ap.add_argument("--cache-size", type=int, default=128)
    args = ap.parse_args()
    serve(args.host, args.port, args.cache_size)


if __name__ == "__main__":
    main()