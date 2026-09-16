# myccusage

[English](README.en.md) | [中文](README.md)

[![PyPI Version](https://img.shields.io/pypi/v/myccusage.svg)](https://pypi.org/project/myccusage/)
[![Python Version](https://img.shields.io/badge/python-3.8%2B-blue.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

`myccusage` is a lightweight, local usage analytics and cost ledger for AI coding assistants.

If you write code with tools like Claude Code, Google Antigravity, or OpenAI Codex, `myccusage` aggregates your local session logs to track Token consumption, monitor Prompt Cache (KV Cache) hit rates, and estimate equivalent costs using pricing models such as DeepSeek or Gemini.

The tool runs entirely locally by parsing local log files in read-only mode, without uploading any code or prompts. When you close the browser tab, the background web server shuts down automatically to free system resources.

---

## Preview

### Usage Overview & Trends
View total token throughput, cache hit rates, cost estimates, daily usage charts, and token distributions.

![Usage Overview Dashboard](docs/images/dashboard-overview.png)

### Session Ledger & Breakdowns
Automatically resolves human-readable session titles, with weekly/daily subtotals and per-session hit rates and cost metrics.

![Session Details Ledger](docs/images/dashboard-details.png)

---

## Features

- **Multi-Agent Support**: Aggregates usage data across Google Antigravity, Claude Code, Hermes Agent, OpenAI Codex, Grok, Pi Agent, OpenCode, and WorkBuddy.
- **Token Breakdown & Cost Estimation**: Details Input, Output, and Cache tokens, with configurable pricing models (e.g., DeepSeek-V4.1-Flash, Gemini 3.8 Flash).
- **Prompt Cache Analytics**: Visualizes KV cache hit rates to help you see how much context caching actually saves.
- **Readable Session Titles**: Parses local SQLite / JSONL / Protobuf metadata to display actual task titles instead of cryptic UUIDs.
- **Dual Tracking Modes**:
  - **Daily Ledger (`-d`)**: Accurate daily slicing to prevent cross-day metric drift, complete with daily and weekly subtotals.
  - **Project Lifetime (`-s`)**: Aggregates total token consumption per session or project.
- **Local & Low Overhead**:
  - 100% offline and read-only analysis without remote network requests.
  - Local slice caching for fast loading even with large historical logs.
  - Web service shuts down within 30 seconds after the browser tab is closed.

---

## Installation

### Step 1: Install `ccusage` globally

`myccusage` relies on [ccusage](https://github.com/ryoppippi/ccusage) to collect raw agent metrics:

```bash
npm install -g ccusage
# or with bun / pnpm:
# bun add -g ccusage
# pnpm add -g ccusage
```

### Step 2: Install `myccusage`

```bash
pip install myccusage
```

For users in China, you can use the Tsinghua PyPI mirror for faster downloads:
```bash
pip install -i https://pypi.tuna.tsinghua.edu.cn/simple myccusage
```

---

## Usage

### Local Web Dashboard

Run the following command to open the dashboard in your default browser:

```bash
myccusage ui
# or
myccusage --web
```
Default URL: `http://127.0.0.1:8488`.

### Command Line Interface (CLI)

Output formatted usage tables directly in your terminal:

```bash
# View Antigravity daily ledger (default)
myccusage --agy

# View Claude Code daily ledger
myccusage --claude

# View Codex / Hermes / OpenCode / WorkBuddy
myccusage --codex
myccusage --hermes
myccusage --opencode
myccusage --workbuddy

# View project lifetime totals
myccusage --agy -s

# Sort by token volume descending
myccusage --agy -s -t
```

#### Common CLI Flags

| Flag | Description |
| :--- | :--- |
| `ui` / `--web` | Launch local Web dashboard in browser |
| `--agy` / `--claude` / `--hermes` / ... | Select specific agent |
| `-d`, `--daily` | Daily ledger mode (default) with daily & weekly subtotals |
| `-s`, `--session` | Project lifetime mode aggregating total token consumption |
| `-t`, `--tokens` | Sort by token consumption descending |

---

## Development & Internal Docs

For caching architecture, pricing schemas, and adding new agent adapters, please refer to:
👉 [README.agent.md](README.agent.md)

---

## License

Released under the [MIT License](LICENSE).
