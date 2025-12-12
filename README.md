# JSON-over-TCP Calc/GPT Protocol

This asssignment implements a simple **application-layer protocol over TCP** using
newline-delimited JSON messages.

The protocol supports two operations as defined at the assignment:

- `calc` – safely evaluate math expressions on the server.
- `gpt`  – send a prompt to a GPT model via the OpenAI API.

this code also includes:

- **Persistnet TCP Server that can handle multiple requests on a single connection.**  
- **a Client with a Commnad Line Interface that supports single-request mode and persistent mode.** 
- **a TCP proxy server with an LRU response cache.** 

---

##  Assignment Architecture

### Components

- **Server (`server.py`)**
  - Listens on a TCP port (default `127.0.0.1:5555`).
  - Accepts multiple concurrent clients.
  - On each connection, accepts **many** JSON requests separated by `\n`.
  - Supports:
    - `mode="calc"` – safe math evaluation (Abstract Syntex Tree based, no `eval`).
    - `mode="gpt"` – calls a GPT model via OpenAI (requires API key). (uses the python-dotenv library)

- **Client (`client.py`)**
  - Commnad Line Interface Wrapper that "speaks" the protocol to the user.
  - **Single-request mode**: open TCP, send one request, close.
  - **Persistent mode**: keep the same TCP connection and send multiple requests in a loop.  

- **Proxy (`proxy.py`)**
  - Listens on its own TCP port (default `127.0.0.1:5554`).
  - Forwards JSON-line messages to the backend server.
  - Maintains an **LRU cache** of responses keyed by the full JSON request. 

- **OpenAI Integration**
  - Controlled by environment variables in `.env`:
    - `OPENAI_API_KEY`
    - `GPT_MODEL`
  - Real GPT calls require the dependencies in `requirements.txt`. 

---

## Transport-Level Protocol

The transport is plain **TCP**:

- Each message is a **single line of UTF-8 JSON**.
- Messages are delimited by a single newline character `\n`.
- Both client and server:
  - Accumulate bytes from `recv(...)` into a buffer.
  - Extract complete lines using the first `\n`.
  - Decode that line as UTF-8 JSON.
- Multiple requests can be sent over and over on the same connection (persistent mode).

---
## Client Setup
---

The client can be either set in persistent mode or single reuqest mode

to activate the persistent mode you should enter this prompt: `python client.py --p`
if you want it to set on a different socket then use the args `--host` for a different IP address and `--port` for a different Port

example: `python client.py --host 127.0.0.1 --port 5555 --p` : sets the client with IP `127.0.0.1`, port `5555` and in persistent mode
for single-request mode, just drop the `--p`

---

## Message Format
---
### Requests
---
Every request is a JSON object with the following structure:

```jsonc
{
  "mode": "calc" | "gpt",
  "data": { ... },
  "options": {
    "cache": true | false   // optional, defaults to true
  }
}
```

`mode calc:`
```jsonc
{
  "mode": "calc",
  "data": {
    "expr": "1 + 2*3"
  },
  "options": {
    "cache": true
  }
}
```
- expr (string) – a math expression using a restricted set of:

- Functions: sin, cos, tan, sqrt, log, exp, max, min, abs

- Constants: pi, e

- Operators: + - * / // % ** and unary + / - 

- notice that in order to use the AST based evaluations you'll require the dependencies in `requirements.txt`.

`mode gpt:`

```jsonc
{
  "mode": "gpt",
  "data": {
    "prompt": "hello"
  },
  "options": {
    "cache": true
  }
}
```

- prompt (string) – user text that will be sent to GPT.

- Note: the actual GPT call is implemented in `call_gpt()` in server.py and uses the OpenAI Python client.
---
### Responses
---
`mode calc`

```jsonc
{
"ok": true,
"result": 7,
"meta": {
  "from_cache": true | false  // default as false - if data is found in cache then its made true
  "took_ms": time
  }
}
```

`mode gpt`

```jsonc
{
"ok": true,
"result": "Hello! How can I help you today?",
"meta": {
  "from_cache": true | false,  // default as false - if data is found in cache then its made true
  "took_ms": number of miliseconds
  }
}
```
