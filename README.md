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
docker build -t agent-terminal:latest .
```

## 本地运行

```bash
docker run -d \
  --name agent-terminal \
  --restart unless-stopped \
  --privileged \
  --pid=host \
  -p 7681:7681 \
  agent-terminal:latest
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

## 文档

离线服务器部署见：

- [docs/离线部署指南.md](docs/离线部署指南.md)
