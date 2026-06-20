# Agent Terminal Web — 交接文档

## 当前状态

当前主工程已经固定在：
- 本地目录：`/Users/apple/Documents/My_Code/Dev/agent-terminal-web`
- GitHub： https://github.com/tienflow/agent-terminal-web

当前项目文档已经同步到最新状态：
- `README.md` 已更新为 x86 镜像构建与导出命令
- `docs/离线部署指南.md` 已统一为当前工程名和镜像名

## 当前关键事实

- 当前标准镜像名：`agent-terminal-web:x86`
- 当前标准离线包名：`agent-terminal-web-x86.tar` / `agent-terminal-web-x86.tar.gz`
- 当前主代码入口：`app.py`
- 当前前端入口：`index.html`

## 仍需继续关注的问题

- Web 终端刷新后的首屏回放体验仍需继续验证，不要默认已经完全稳定
- `Clear` + 刷新 + 多浏览器连接 的组合行为，需要继续用真实浏览器压测

## 建议下一步

1. 先读：
   - `README.md`
   - `docs/离线部署指南.md`
2. 再读：
   - `app.py`
   - `index.html`
3. 用真实浏览器复现刷新回放问题

## 建议技能

- `ego-browser`
- `handoff`
- `neat-freak`
