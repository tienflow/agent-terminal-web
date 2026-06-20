# MCP Server 实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 为 Agent Terminal Web 添加 MCP Server，让 AI Agent 通过标准 MCP 协议（SSE transport）调用宿主机终端

**架构：** 在现有 FastAPI app 中挂载 MCP 子应用，复用 PTY 实例，通过官方 mcp SDK 的 `FastMCP.sse_app()` 暴露 4 个 tools

**技术栈：** Python 3.12, FastAPI, mcp SDK 1.28.0, SSE transport

---

## 文件结构

| 文件 | 职责 | 变更类型 |
|------|------|---------|
| `requirements.txt` | Python 依赖 | 修改：新增 `mcp` |
| `app.py` | FastAPI 应用 + PTY 管理 + MCP Server | 修改：新增 MCP 代码块 |

---

### 任务 1：添加 mcp 依赖

**文件：**
- 修改：`requirements.txt`

- [ ] **步骤 1：在 requirements.txt 中新增 mcp 依赖**

```txt
fastapi==0.115.12
uvicorn[standard]==0.34.2
websockets==15.0.1
mcp>=1.28.0
```

- [ ] **步骤 2：验证依赖可安装**

运行：`pip install -r requirements.txt`
预期：成功安装 mcp 及其依赖（sse-starlette, anyio 等）

- [ ] **步骤 3：Commit**

```bash
git add requirements.txt
git commit -m "deps: add mcp SDK for MCP server support"
```

---

### 任务 2：实现 MCP Server 和 4 个 Tools

**文件：**
- 修改：`app.py`

- [ ] **步骤 1：在 app.py 顶部新增 MCP 相关 import**

在现有 import 块之后（第 11 行 `from fastapi.responses import HTMLResponse, JSONResponse` 之后），新增：

```python
import re
from mcp.server.fastmcp import FastMCP
```

- [ ] **步骤 2：创建 MCP Server 实例和 tool 定义**

在 `app = FastAPI()` 之后、PTY 管理代码块之前（约第 21 行之后），新增：

```python
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

    # Record current history length as baseline
    before = get_pty_history()

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
    new_output = full[len(before):] if len(full) > len(before) else ""

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
```

- [ ] **步骤 3：在 startup 事件后挂载 MCP 子应用到 FastAPI**

在 `app.py` 末尾（`async def index()` 函数之后），新增：

```python
# Mount MCP SSE sub-application
app.mount("/mcp", mcp_server.sse_app(mount_path="/mcp"))
```

- [ ] **步骤 4：验证代码无语法错误**

运行：`python3 -c "import ast; ast.parse(open('app.py').read()); print('OK')"`
预期：`OK`

- [ ] **步骤 5：Commit**

```bash
git add app.py
git commit -m "feat: add MCP server with 4 tools (execute_command, read_history, clear_history, health_check)"
```

---

### 任务 3：Docker 构建验证

**文件：**
- 无修改（Dockerfile 不需要改动，pip install 会自动处理新依赖）

- [ ] **步骤 1：构建 Docker 镜像**

运行：`docker buildx build --platform linux/amd64 -t agent-terminal-web:x86 --load .`
预期：构建成功，mcp 依赖被安装

- [ ] **步骤 2：启动容器**

运行：
```bash
docker rm -f agent-terminal-web 2>/dev/null || true
docker run -d \
  --name agent-terminal-web \
  --restart unless-stopped \
  --privileged \
  --pid=host \
  -p 7681:7681 \
  agent-terminal-web:x86
```

预期：容器启动成功

- [ ] **步骤 3：验证健康检查**

运行：`curl -s http://127.0.0.1:7681/health`
预期：`{"status":"ok","pty":true,"time":"..."}`

- [ ] **步骤 4：验证 MCP SSE 端点可访问**

运行：`curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:7681/mcp/sse`
预期：`200`（SSE 连接建立）

- [ ] **步骤 5：验证 Web 终端仍然正常**

运行：`curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:7681/`
预期：`200`

运行：`curl -s -o /dev/null -w "%{http_code}" -X POST http://127.0.0.1:7681/exec -H 'Content-Type: application/json' -d '{"cmd":"echo hello"}'`
预期：`200`

- [ ] **步骤 6：Commit（如有修复）**

如果验证过程中发现并修复了问题：
```bash
git add -A
git commit -m "fix: address issues found during Docker verification"
```

---

### 任务 4：MCP Inspector 端到端验证

**文件：**
- 无修改

- [ ] **步骤 1：启动 MCP Inspector**

运行：`npx @modelcontextprotocol/inspector`
预期：Inspector 在浏览器中打开

- [ ] **步骤 2：连接到 MCP Server**

在 Inspector 中输入 URL：`http://127.0.0.1:7681/mcp/sse`
预期：连接成功，显示 4 个 tools

- [ ] **步骤 3：测试 health_check**

调用 `health_check`，预期返回：
```json
{"status": "ok", "pty_alive": true, "timestamp": "..."}
```

- [ ] **步骤 4：测试 execute_command**

调用 `execute_command`，参数 `cmd: "hostname && whoami"`
预期：返回宿主机的 hostname 和用户名

- [ ] **步骤 5：测试 read_history**

调用 `read_history`，预期：返回包含刚才命令输出的终端历史

- [ ] **步骤 6：测试 clear_history**

调用 `clear_history`，预期：返回 `"history cleared"`
调用 `read_history`，预期：历史已清空

- [ ] **步骤 7：验证 Web 终端共存**

浏览器打开 `http://127.0.0.1:7681`，确认 Web 终端仍然正常工作

- [ ] **步骤 8：更新 README**

在 `README.md` 的"接口"章节后新增 MCP 相关文档：

```markdown
### MCP Server

服务同时提供 MCP Server，Agent 可通过标准 MCP 协议连接：

- SSE 端点：`http://<服务器IP>:7681/mcp/sse`
- 暴露 4 个 Tools：
  - `execute_command` — 执行命令并返回输出
  - `read_history` — 读取终端回放缓存
  - `clear_history` — 清空回放缓存
  - `health_check` — 检查服务状态

Agent 配置示例：
\`\`\`json
{
  "mcpServers": {
    "agent-terminal": {
      "url": "http://<服务器IP>:7681/mcp/sse"
    }
  }
}
\`\`\`
```

- [ ] **步骤 9：最终 Commit**

```bash
git add README.md
git commit -m "docs: add MCP server usage to README"
```
