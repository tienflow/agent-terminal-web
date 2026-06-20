# Agent Terminal Web

一个单容器 Web 终端服务，支持两种使用方式：
- 浏览器直接打开 Web 终端操作宿主机 shell
- 通过 HTTP API 调用宿主机 shell，并在浏览器里实时看到执行结果

当前实现特性：
- 单容器部署
- 后端基于 FastAPI + WebSocket
- 前端基于 xterm.js
- 通过 `nsenter -t 1` 进入宿主机命名空间
- `POST /exec` 供 Agent 调用
- 支持终端内容回放，刷新页面后可恢复最近输出
- 支持清屏按钮，同时清前端视图和回放缓存

## 文件结构

```text
.
├── app.py
├── index.html
├── Dockerfile
├── requirements.txt
├── README.md
└── docs/
    └── 离线部署指南.md
```

## 本地构建

```bash
docker buildx build --platform linux/amd64 -t agent-terminal-web:x86 --load .
```

## 本地运行

```bash
docker run -d \
  --name agent-terminal-web \
  --restart unless-stopped \
  --privileged \
  --pid=host \
  -p 7681:7681 \
  agent-terminal-web:x86
```

## 接口

### 健康检查

```bash
GET /health
```

### Agent 执行命令

```bash
POST /exec
Content-Type: application/json

{"cmd":"hostname && whoami"}
```

### 清空回放缓存

```bash
POST /clear-history
```

### WebSocket 终端

```text
GET /ws
```

### MCP Server

服务同时提供 MCP Server，Agent 可通过标准 MCP 协议连接：

- SSE 端点：`http://<服务器IP>:7681/mcp/sse`
- 暴露 4 个 Tools：
  - `execute_command` — 执行命令并返回输出
  - `read_history` — 读取终端回放缓存
  - `clear_history` — 清空回放缓存
  - `health_check` — 检查服务状态

Agent 配置示例：
```json
{
  "mcpServers": {
    "agent-terminal": {
      "url": "http://<服务器IP>:7681/mcp/sse"
    }
  }
}


## AI Agent 调用方式

在服务器上安装成功后，你可以把下面这段话直接贴给任何一个有 HTTP 调用能力的 AI agent：

> 你有一台宿主机终端可以操作。调用方式如下：
>
> 1. 发命令：
> ```bash
> curl -s -X POST http://<服务器IP>:7681/exec \
>   -H 'Content-Type: application/json' \
>   -d '{"cmd":"你要执行的命令"}'
> ```
>
> 2. 等待 2-3 秒让命令执行完成。
>
> 3. 读取输出：
> ```bash
> curl -s http://<服务器IP>:7681/history
> ```
>
> `history` 返回的是最近一段终端输出的 HTML 页面，里面包含你要的命令结果。
>
> 注意：
> - 这个终端执行的是宿主机 shell，不是容器内 shell
> - 每次发新命令前，建议先读一次 history 确认上一条命令是否完成

把 `<服务器IP>` 替换成你的实际服务器地址即可。

## 文档

离线服务器部署见：

- [docs/离线部署指南.md](docs/离线部署指南.md)


## x86 镜像打包

当前已验证可在 Apple Silicon 主机上构建 x86 镜像：

```bash
docker buildx build --platform linux/amd64 -t agent-terminal-web:x86 --load .
```

导出离线包：

```bash
docker save -o agent-terminal-web-x86.tar agent-terminal-web:x86
gzip -f agent-terminal-web-x86.tar
```
