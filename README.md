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
# 启动本地 Web 仪表盘
ccu web
# 或
myccusage ui
```
默认访问地址为 `http://127.0.0.1:8488`。

### 命令行（CLI）直接查看

现已全面支持极简短命令 **`ccu`**，支持直接传参、无需敲 `--`：

```bash
# 1. 零参数速报（查看今日多 Agent 用量总览与花费）
ccu

# 2. 查看各 Agent 每日明细账本
ccu agy             # Google Antigravity
ccu claude          # Claude Code
ccu codex           # OpenAI Codex
ccu workbuddy       # WorkBuddy
ccu grok            # Grok

# 3. 查看项目全生命周期总览 (-s)
ccu agy -s

# 4. 按 Token 消耗量降序排列 (-t)
ccu agy -s -t
```

#### 常用命令速查

| 极简命令 | 原长命令 | 说明 |
| :--- | :--- | :--- |
| `ccu` | `myccusage` | **今日速报**：查看今日各 Agent 汇总 Token、缓存命中率与花费 |
| `ccu agy` | `myccusage --agy` | 查看 Antigravity 每日会话用量账本（默认按日切片） |
| `ccu agy -s` | `myccusage --agy -s` | 查看 Antigravity 项目生命周期总览 |
| `ccu claude` | `myccusage --claude` | 查看 Claude Code 每日账本 |
| `ccu codex` | `myccusage --codex` | 查看 OpenAI Codex 账本 |
| `ccu web` | `myccusage --web` | 一键启动本地 Web 仪表盘并自动打开浏览器 |
| `ccu -t` | `myccusage -t` | 按 Token 消耗从高到低排序 |

---

### macOS 原生程序坞常驻微型看板 (可选)

本项目支持一键运行原生 macOS 程序坞应用（`myccusage.app`）：
- **Dock 动态微型看板**：每 60 秒极低能耗自动刷新（基于 `mtime` 单 Agent 指纹嗅探与今日热文件剪枝，刷新仅耗时 5ms，CPU 占用趋近 0%），大字清晰展示今日 Token 吞吐、今日 100M 进度条与最新活跃 Session 的 KV Cache 命中率圆环。
- **原生磨砂悬浮卡片**：点击 Dock 图标即可在上方升起半透明磨砂气泡卡片，智能跟随 Dock 位置并带有指示呼应箭头，展示今日各活跃 Agent 的细分用量，并附带“一键打开完整 Web 看板”入口。
- **一键运行与构建**：
  ```bash
  # 终端直接运行（首次会自动构建，约需 2 秒）
  myccusage dock
  ```
  或者通过脚本手动构建：
  ```bash
  bash macos/build_app.sh
  open dist/myccusage.app
  ```
  构建产物仅数百 KB，常驻内存仅数十 MB，离电续航完全无感。

---

---

## 二次开发与底层文档

如果需要了解数据缓存切片机制、计价规则配置或扩展新的 Agent 适配，请参阅：
👉 [README.agent.md](README.agent.md)

---

## 开源协议

本项目采用 [MIT License](LICENSE) 协议开源。
