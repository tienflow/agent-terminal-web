# MCP Server 设计规格

## 目标

为 Agent Terminal Web 添加 MCP Server 支持，让 AI Agent 可以通过标准 MCP 协议（SSE transport）调用宿主机终端，而非仅依赖 HTTP API + curl。

## 决策记录

| 决策 | 选择 | 理由 |
|------|------|------|
| MCP 与 HTTP API 关系 | 共存 | Agent 可任选方式，不破坏现有用法 |
| 传输方式 | SSE / Streamable HTTP | 远程服务器场景，Agent 不在同机 |
| 暴露的 Tools | 4 个（见下方） | 覆盖核心操作 |
| 集成方式 | 集成到 FastAPI | 单进程单容器，复用 PTY，改动最小 |
| MCP 库 | 官方 `mcp` SDK | 标准实现，SSE transport 开箱即用 |

## 架构

```
┌─────────────────────────────────────────────┐
│              Docker Container               │
│  ┌─────────────────────────────────────┐    │
│  │         FastAPI App (app.py)        │    │
│  │                                     │    │
│  │  ┌──────────┐  ┌────────────────┐   │    │
│  │  │ HTTP API │  │  WebSocket /ws │   │    │
│  │  │ /exec    │  │  (xterm.js)    │   │    │
│  │  │ /health  │  └────────────────┘   │    │
│  │  │ /history │                       │    │
│  │  └──────────┘                       │    │
│  │                                     │    │
│  │  ┌──────────────────────────────┐   │    │
│  │  │  MCP Server (新增)           │   │    │
│  │  │  SSE transport @ /mcp/sse    │   │    │
│  │  │  POST messages @ /mcp/messages│  │    │
│  │  └──────────────────────────────┘   │    │
│  │                                     │    │
│  │  ┌──────────────────────────────┐   │    │
│  │  │  PTY Management (现有)       │   │    │
│  │  │  nsenter -t 1 → 宿主机 shell │   │    │
│  │  └──────────────────────────────┘   │    │
│  └─────────────────────────────────────┘    │
└─────────────────────────────────────────────┘
```

MCP Server 作为 FastAPI 子应用挂载在 `/mcp` 路径下，复用现有 PTY 实例。Agent 通过 `http://<server>:7681/mcp/sse` 连接，人类用户继续用 `http://<server>:7681` 的 Web 终端。两条路径共享同一个 PTY 和历史记录。

## Tools 定义

### `execute_command`

在宿主机上执行 shell 命令并返回输出。

- **参数**:
  - `cmd: str` — 要执行的 shell 命令
  - `timeout: int = 30` — 超时秒数
- **返回**: 命令执行后的终端文本（已清理 ANSI 转义序列）
- **输出捕获策略**:
  1. 记录当前 `pty_history` 内容长度作为起点
  2. 通过 PTY 写入命令: `os.write(master_fd, (cmd + "\n").encode())`
  3. 轮询 `pty_history` 直到内容不再变化（稳定检测）
  4. 从起点截取新增内容，清理 ANSI 转义序列后返回
- **错误处理**:
  - PTY 未就绪 → 返回 `"PTY not ready"`
  - 命令为空 → 返回 `"empty command"`
  - 超时 → 返回已捕获的部分输出 + 超时提示

### `read_history`

读取终端回放缓存。

- **参数**:
  - `lines: int = 0` — 限制返回行数，0 表示全部
- **返回**: 终端输出文本

### `clear_history`

清空终端回放缓存。

- **参数**: 无
- **返回**: 确认消息 `"history cleared"`

### `health_check`

检查服务和 PTY 状态。

- **参数**: 无
- **返回**: `{"status": "ok", "pty_alive": true, "timestamp": "HH:MM:SS"}`

## 文件变更

| 文件 | 变更内容 |
|------|---------|
| `app.py` | 新增 MCP Server 创建、4 个 tool 定义、挂载到 FastAPI |
| `requirements.txt` | 新增 `mcp` 依赖 |
| `Dockerfile` | 无需改动 |
| `index.html` | 无需改动 |

## Agent 连接方式

Agent 配置 MCP server：
```json
{
  "mcpServers": {
    "agent-terminal": {
      "url": "http://<server-ip>:7681/mcp/sse"
    }
  }
}
```

## 测试策略

手动验证为主（与项目现有风格一致）：

1. 启动容器，用 MCP Inspector 连接 `http://localhost:7681/mcp/sse`
2. 调用 `health_check` → 确认连接正常
3. 调用 `execute_command("hostname")` → 确认返回宿主机 hostname
4. 调用 `read_history` → 确认能看到命令输出
5. 调用 `clear_history` → 确认清空成功
6. 同时打开浏览器 Web 终端 → 确认两条路径互不干扰

## 不做的事

- 不加单元测试（项目现有风格是真实环境验证）
- 不重构现有 HTTP API
- 不添加 MCP resource 或 prompt（只做 tool）
- 不改 Dockerfile（pip install 自动处理新依赖）
