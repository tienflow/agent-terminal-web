import asyncio
import json
import os
import pty
import select
import struct
import fcntl
import termios
import time
import logging
from collections import deque
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse
import re
from mcp.server.fastmcp import FastMCP

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger("agent-term")

app = FastAPI()

# ---------------------------------------------------------------------------
# MCP Server
# ---------------------------------------------------------------------------
mcp_server = FastMCP("agent-terminal", sse_path="/sse", message_path="/messages/")


def _strip_ansi(text: str) -> str:
    """Remove ANSI escape sequences from text."""
    ansi_escape = re.compile(r"\x1b\[[0-9;]*[a-zA-Z]|\x1b\].*?\x07")
    return ansi_escape.sub("", text)


@mcp_server.tool()
async def execute_command(cmd: str, timeout: int = 30) -> str:
    """Execute a shell command on the host machine and return the output.

    Args:
        cmd: The shell command to execute.
        timeout: Maximum seconds to wait for output (default 30).
    """
    if not cmd.strip():
        return "Error: empty command"
    if master_fd is None:
        return "Error: PTY not ready"

    # Record current history as baseline for output extraction
    original_before = get_pty_history()
    before = original_before

    # Send command to PTY
    os.write(master_fd, (cmd + "\n").encode("utf-8"))

    # Wait for output to stabilize
    stable_count = 0
    elapsed = 0.0
    interval = 0.2
    while elapsed < timeout:
        await asyncio.sleep(interval)
        elapsed += interval
        after = get_pty_history()
        if after == before:
            stable_count += 1
            if stable_count >= 3:  # Stable for 0.6 seconds
                break
        else:
            stable_count = 0
            before = after

    # Extract new output (everything after the original history)
    full = get_pty_history()
    new_output = full[len(original_before):] if len(full) > len(original_before) else ""

    # Clean up: remove the command echo and trailing prompt
    lines = new_output.split("\n")
    # Remove first line (command echo) if present
    if lines and cmd.strip() in lines[0]:
        lines = lines[1:]
    # Remove last line if it looks like a prompt (non-empty, no newline)
    if lines and not lines[-1].endswith("\n") and any(
        c in lines[-1] for c in ["$", "#", "%", ">"]
    ):
        lines = lines[:-1]

    result = "\n".join(lines).strip()
    if not result:
        result = "(no output)"
    return _strip_ansi(result)


@mcp_server.tool()
async def read_history(lines: int = 0) -> str:
    """Read the terminal replay buffer.

    Args:
        lines: Max number of recent lines to return. 0 = all.
    """
    history = get_pty_history()
    if lines > 0:
        all_lines = history.split("\n")
        history = "\n".join(all_lines[-lines:])
    return _strip_ansi(history)


@mcp_server.tool()
async def clear_history() -> str:
    """Clear the terminal replay buffer."""
    clear_pty_history()
    return "history cleared"


@mcp_server.tool()
async def health_check() -> dict:
    """Check service and PTY status."""
    return {
        "status": "ok",
        "pty_alive": master_fd is not None,
        "timestamp": time.strftime("%H:%M:%S"),
    }



# ---------------------------------------------------------------------------
# PTY management
# ---------------------------------------------------------------------------
master_fd: int | None = None
pty_queue: asyncio.Queue[str | None] = asyncio.Queue()
cmd_queue: asyncio.Queue[dict | None] = asyncio.Queue()
subscribers: set[WebSocket] = set()
pty_history: deque[str] = deque()
pty_history_size = 0
MAX_PTY_HISTORY_BYTES = 64 * 1024


def append_pty_history(data: str):
    global pty_history_size
    if not data:
        return
    pty_history.append(data)
    pty_history_size += len(data.encode("utf-8", errors="ignore"))
    while pty_history and pty_history_size > MAX_PTY_HISTORY_BYTES:
        dropped = pty_history.popleft()
        pty_history_size -= len(dropped.encode("utf-8", errors="ignore"))


def get_pty_history() -> str:
    return "".join(pty_history)


def clear_pty_history():
    global pty_history_size
    pty_history.clear()
    pty_history_size = 0


def resize_pty(fd: int, cols: int, rows: int):
    winsize = struct.pack("HHHH", rows, cols, 0, 0)
    fcntl.ioctl(fd, termios.TIOCSWINSZ, winsize)


def init_pty():
    global master_fd
    master_fd, slave_fd = pty.openpty()
    resize_pty(master_fd, 160, 50)

    pid = os.fork()
    if pid == 0:
        os.close(master_fd)
        os.setsid()
        fcntl.ioctl(slave_fd, termios.TIOCSCTTY, 0)
        os.dup2(slave_fd, 0)
        os.dup2(slave_fd, 1)
        os.dup2(slave_fd, 2)
        os.close(slave_fd)
        os.execvp("nsenter", [
            "nsenter", "-t", "1", "-m", "-u", "-i", "-n", "-p",
            "--", "/bin/bash", "--login"
        ])
    os.close(slave_fd)
    log.info(f"PTY started (host ns), pid={pid}")


def _pty_reader():
    """Thread: read PTY → put into asyncio queue."""
    while master_fd is not None:
        try:
            r, _, _ = select.select([master_fd], [], [], 0.05)
            if r:
                data = os.read(master_fd, 8192).decode("utf-8", errors="replace")
                if data:
                    append_pty_history(data)
                    asyncio.run_coroutine_threadsafe(
                        pty_queue.put(data), _loop
                    ).result(timeout=2)
        except OSError:
            break
    asyncio.run_coroutine_threadsafe(pty_queue.put(None), _loop)


_loop: asyncio.AbstractEventLoop | None = None


async def _broadcast_pty():
    """Async: PTY output → WebSocket."""
    while True:
        data = await pty_queue.get()
        if data is None:
            break
        dead = set()
        for ws in list(subscribers):
            try:
                await ws.send_text(data)
            except Exception:
                dead.add(ws)
        subscribers.difference_update(dead)


async def _broadcast_cmds():
    """Async: agent command notifications → WebSocket."""
    while True:
        msg = await cmd_queue.get()
        if msg is None:
            break
        payload = json.dumps(msg)
        dead = set()
        for ws in list(subscribers):
            try:
                await ws.send_text(payload)
            except Exception:
                dead.add(ws)
        subscribers.difference_update(dead)


@app.on_event("startup")
async def startup():
    global _loop
    _loop = asyncio.get_event_loop()
    init_pty()
    _loop.run_in_executor(None, _pty_reader)
    _loop.create_task(_broadcast_pty())
    _loop.create_task(_broadcast_cmds())
    log.info("Agent-Terminal started — host mode (nsenter)")


# ---------------------------------------------------------------------------
# WebSocket — live terminal
# ---------------------------------------------------------------------------
@app.websocket("/ws")
async def ws_terminal(ws: WebSocket):
    await ws.accept()
    history = get_pty_history()
    if history:
        await ws.send_text(history)
    subscribers.add(ws)
    log.info(f"WS connected, total={len(subscribers)}")
    try:
        while True:
            data = await ws.receive_text()
            try:
                msg = json.loads(data)
                if msg.get("type") == "resize" and master_fd:
                    resize_pty(master_fd, msg["cols"], msg["rows"])
                    continue
            except (json.JSONDecodeError, KeyError):
                pass
            if master_fd:
                os.write(master_fd, data.encode("utf-8"))
    except WebSocketDisconnect:
        pass
    finally:
        subscribers.discard(ws)
        log.info(f"WS disconnected, total={len(subscribers)}")


# ---------------------------------------------------------------------------
# HTTP API
# ---------------------------------------------------------------------------
@app.post("/exec")
async def exec_cmd(payload: dict):
    cmd = payload.get("cmd", "").strip()
    if not cmd:
        return JSONResponse({"error": "empty cmd"}, 400)
    if master_fd is None:
        return JSONResponse({"error": "PTY not ready"}, 500)
    log.info(f"EXEC: {cmd}")
    os.write(master_fd, (cmd + "\n").encode("utf-8"))
    # Notify frontends that agent executed a command
    await cmd_queue.put({"type": "agent_cmd", "cmd": cmd, "time": time.strftime("%H:%M:%S")})
    await asyncio.sleep(1.0)
    return {"status": "sent", "cmd": cmd}


@app.post("/clear-history")
async def clear_history():
    clear_pty_history()
    return {"status": "cleared"}


@app.get("/history")
async def history():
    return HTMLResponse(f"<pre>{get_pty_history()}</pre>")


@app.get("/health")
async def health():
    return {"status": "ok", "pty": master_fd is not None, "time": time.strftime("%H:%M:%S")}


@app.get("/")
async def index():
    return HTMLResponse(Path(__file__).parent.joinpath("index.html").read_text())


# Mount MCP SSE sub-application
app.mount("/mcp", mcp_server.sse_app(mount_path="/mcp"))
