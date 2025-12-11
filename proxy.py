# proxy.py
import argparse
import socket
import threading
import json
import collections
import time
from typing import Optional, Dict, Any, Tuple

# -------------------- Minimal LRU Cache --------------------
class LRUCache:
    """Small LRU cache for proxy responses."""
    def __init__(self, capacity: int = 256):
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


# -------------------- Helpers --------------------
def recv_line(sock: socket.socket, buf: bytearray) -> Optional[bytes]:
    """
    Read from sock until a newline is found.
    Maintain buffer across calls (pass in bytearray).
    Return one complete line (without newline) as bytes or None if not available.
    If socket is closed (recv returns b'') and buffer empty -> return None to indicate closed.
    """
    while True:
        if b"\n" in buf:
            line, _, rest = bytes(buf).partition(b"\n")
            # reset buffer to remaining bytes
            buf[:] = rest
            return line
        try:
            chunk = sock.recv(4096)
        except Exception:
            # any socket error treat as closed for simplicity
            chunk = b""
        if not chunk:
            # no more data; if we have some buffered data without newline, treat as closed
            if len(buf) == 0:
                return None
            # if partial data present but no newline, treat it as one final line
            line = bytes(buf)
            buf.clear()
            return line
        buf.extend(chunk)


def send_line(sock: socket.socket, obj: Dict[str, Any]):
    data = (json.dumps(obj, ensure_ascii=False) + "\n").encode("utf-8")
    sock.sendall(data)


# -------------------- Proxy core --------------------
def handle_client(client_sock: socket.socket, server_host: str, server_port: int, cache: LRUCache, server_connect_timeout: float):
    client_addr = client_sock.getpeername()
    print(f"[proxy] client connected: {client_addr}")
    client_buf = bytearray()

    server_sock: Optional[socket.socket] = None
    server_buf = bytearray()

    def ensure_server_connection() -> Tuple[Optional[socket.socket], Optional[str]]:
        nonlocal server_sock, server_buf
        if server_sock:
            return server_sock, None
        try:
            server_sock = socket.create_connection((server_host, server_port), timeout=server_connect_timeout)
            # make recv non-blocking? We keep blocking reads in recv_line; keeping blocking is OK
            server_buf = bytearray()
            return server_sock, None
        except Exception as e:
            server_sock = None
            return None, str(e)

    try:
        with client_sock:
            while True:
                line = recv_line(client_sock, client_buf)
                if line is None:
                    # client closed
                    print(f"[proxy] client {client_addr} disconnected")
                    break

                # ignore empty lines
                if len(line.strip()) == 0:
                    continue

                # parse request JSON
                try:
                    req = json.loads(line.decode("utf-8"))
                except Exception as e:
                    err = {"ok": False, "error": f"Proxy: invalid JSON request: {e}"}
                    try:
                        send_line(client_sock, err)
                    except Exception:
                        pass
                    continue

                # build cache key (deterministic)
                try:
                    cache_key = json.dumps(req, sort_keys=True)
                except Exception:
                    cache_key = str(req)

                # check proxy cache
                cached = cache.get(cache_key)
                if cached is not None:
                    # cached holds the full response object
                    print(f"[proxy] cache HIT for client {client_addr}, mode={req.get('mode')}")
                    try:
                        send_line(client_sock, cached)
                    except Exception:
                        # client may have disconnected
                        break
                    continue

                # cache miss -> forward to server (ensure connection)
                s, err = ensure_server_connection()
                if s is None:
                    # server unavailable
                    print(f"[proxy] backend unavailable ({err}). Checking cache fallback for client {client_addr}")
                    # try to fall back to cache (already checked above) - no cache -> return error
                    error_resp = {"ok": False, "error": f"Proxy: backend unavailable: {err}"}
                    try:
                        send_line(client_sock, error_resp)
                    except Exception:
                        pass
                    # continue loop to accept next client request (maybe backend will come back)
                    continue

                # send request to server
                try:
                    data_out = (json.dumps(req, ensure_ascii=False) + "\n").encode("utf-8")
                    s.sendall(data_out)
                except Exception as e:
                    # sending failed; drop server socket and try to send error or fallback
                    print(f"[proxy] error sending to server: {e}. Closing server connection.")
                    try:
                        server_sock.close()
                    except Exception:
                        pass
                    server_sock = None
                    error_resp = {"ok": False, "error": f"Proxy: error forwarding to backend: {e}"}
                    try:
                        send_line(client_sock, error_resp)
                    except Exception:
                        pass
                    continue

                # read exactly one JSON-line response from server
                try:
                    resp_line = recv_line(s, server_buf)
                    if resp_line is None:
                        # server closed connection unexpectedly
                        print("[proxy] server closed connection unexpectedly")
                        try:
                            server_sock.close()
                        except Exception:
                            pass
                        server_sock = None
                        error_resp = {"ok": False, "error": "Proxy: backend closed connection unexpectedly"}
                        try:
                            send_line(client_sock, error_resp)
                        except Exception:
                            pass
                        continue

                    # parse server response
                    try:
                        resp_obj = json.loads(resp_line.decode("utf-8"))
                    except Exception as e:
                        resp_obj = {"ok": False, "error": f"Proxy: invalid JSON from backend: {e}"}

                    # cache the response (store the entire response JSON object)
                    try:
                        cache.set(cache_key, resp_obj)
                    except Exception:
                        pass

                    # forward response to client
                    try:
                        send_line(client_sock, resp_obj)
                    except Exception:
                        # client probably disconnected
                        break

                except Exception as e:
                    print(f"[proxy] error reading from server: {e}")
                    try:
                        server_sock.close()
                    except Exception:
                        pass
                    server_sock = None
                    try:
                        send_line(client_sock, {"ok": False, "error": f"Proxy: backend read error: {e}"})
                    except Exception:
                        pass
                    continue

    except Exception as e:
        print(f"[proxy] handler exception for client {client_addr}: {e}")
    finally:
        try:
            if server_sock:
                server_sock.close()
        except Exception:
            pass
        print(f"[proxy] handler finished for client {client_addr}")


def main():
    ap = argparse.ArgumentParser(description="JSON-line TCP proxy with simple LRU cache")
    ap.add_argument("--listen-host", default="127.0.0.1")
    ap.add_argument("--listen-port", type=int, default=5554)
    ap.add_argument("--server-host", default="127.0.0.1")
    ap.add_argument("--server-port", type=int, default=5555)
    ap.add_argument("--cache-size", type=int, default=256, help="LRU cache size (responses)")
    ap.add_argument("--server-timeout", type=float, default=5.0, help="seconds to wait when connecting to backend")
    args = ap.parse_args()

    cache = LRUCache(args.cache_size)

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind((args.listen_host, args.listen_port))
        s.listen(100)
        print(f"[proxy] listening {args.listen_host}:{args.listen_port} -> backend {args.server_host}:{args.server_port} (cache={args.cache_size})")
        while True:
            try:
                client, addr = s.accept()
            except KeyboardInterrupt:
                break
            t = threading.Thread(target=handle_client, args=(client, args.server_host, args.server_port, cache, args.server_timeout), daemon=True)
            t.start()


if __name__ == "__main__":
    main()