# myccusage

[中文](README.md) | [English](README.en.md)

[![PyPI Version](https://img.shields.io/pypi/v/myccusage.svg)](https://pypi.org/project/myccusage/)
[![Python Version](https://img.shields.io/badge/python-3.8%2B-blue.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

`myccusage` 是一个轻量的本地 AI 编程工具用量统计与账本查看器。

如果你平时使用 Claude Code、Google Antigravity、OpenAI Codex 等工具写代码，`myccusage` 可以帮你汇总本地的 Token 消耗、查看 Prompt 缓存（KV Cache）命中率，并按 DeepSeek 或 Gemini 等模型定价折算参考费用。

工具完全在本地运行，直接读取本地日志文件，不上传任何代码与对话记录；Web 页面关闭后后台服务会自动退出，不常驻系统后台。

---

## 界面预览

### 消耗总览与趋势分析
展示全周期 Token 吞吐、缓存命中率、参考费用折算、每日消耗柱状图与 Token 构成分布。

![消耗总览看板](docs/images/dashboard-overview.png)

### 会话明细账本
自动解析并显示会话标题，支持按周和按日查看明细与小计。

![会话明细账本](docs/images/dashboard-details.png)

---

## 主要功能

- **支持多种编程 Agent**：统一查看 Google Antigravity、Claude Code、Hermes Agent、OpenAI Codex、Grok、Pi Agent、OpenCode、WorkBuddy 的使用记录。
- **Token 消耗与费用参考**：统计 Input、Cache 与 Output 构成，支持按 DeepSeek-V4.1-Flash、Gemini 3.8 Flash 等模型单价换算参考费用。
- **缓存命中率统计**：直观查看每次会话与整体的 KV Cache 命中比例，了解缓存节省情况。
- **自动读取会话标题**：解析本地 SQLite / JSONL / Protobuf 文件还原会话标题，避免面对难以辨识的 UUID。
- **两种统计模式**：
  - **每日账本（`-d`）**：按自然日精确切片，防止跨日会话导致的数据漂移，适合日常核算。
  - **项目总览（`-s`）**：按会话/项目完整生命周期累计总消耗。
- **本地运行与低资源消耗**：
  - 纯本地只读解析，不产生任何外部网络请求。
  - 本地历史切片缓存，大数据量下也能快速加载。
  - 浏览器页面关闭 30 秒后，本地 Web 进程自动退出，不常驻占用系统资源。

---

## 安装说明

### 直接使用 pip 安装（无需 Node.js / ccusage）

`myccusage` 现已内置各大 Agent 的原生 Python 高性能解析内核，**完全不依赖 Node.js 或外部 ccusage 工具**，直接 pip 即可安装并使用：

```bash
pip install myccusage
```

国内用户可使用清华镜像源加速：
```bash
pip install -i https://pypi.tuna.tsinghua.edu.cn/simple myccusage
```

---

## 使用方法

### 本地 Web 看板

在终端运行以下命令，会自动在默认浏览器中打开看板：

```bash
myccusage ui
# 或
myccusage --web
```
默认访问地址为 `http://127.0.0.1:8488`。

### 命令行（CLI）直接查看

也可以直接在终端中以表格形式输出指定 Agent 的账本：

```bash
# 查看 Antigravity 每日账本（默认）
myccusage --agy

# 查看 Claude Code 每日账本
myccusage --claude

# 查看 Codex / Hermes / OpenCode / WorkBuddy
myccusage --codex
myccusage --hermes
myccusage --opencode
myccusage --workbuddy

# 查看某 Agent 各项目生命周期总消耗
myccusage --agy -s

# 按 Token 消耗降序排列
myccusage --agy -s -t
```

#### 常用参数速查

| 参数 | 说明 |
| :--- | :--- |
| `ui` / `--web` | 启动本地 Web 仪表盘并打开浏览器 |
| `--agy` / `--claude` / `--hermes` / ... | 指定要查看的 Agent |
| `-d`, `--daily` | 每日账本模式（默认），按自然日切片并带有周小计 |
| `-s`, `--session` | 项目总览模式，按会话累计生命周期总消耗 |
| `-t`, `--tokens` | 按 Token 消耗从高到低排序 |

---

## 二次开发与底层文档

如果需要了解数据缓存切片机制、计价规则配置或扩展新的 Agent 适配，请参阅：
👉 [README.agent.md](README.agent.md)

---

## 开源协议

本项目采用 [MIT License](LICENSE) 协议开源。
