# myccusage Agent & Developer Architecture Guide

> **面向 AI Coding Agent（如 Antigravity、Claude Code、Cursor、Copilot 等）及底层维护者的全景设计与代码维护指南。**  
> 本文档旨在提供高度结构化、精准、直接可操作的技术细节，帮助智能体和工程师在零摸索成本下完成代码扩展、Bug 排查与功能迭代。

---

## 目录

- [1. 计价规则体系与数据持久化](#1-计价规则体系与数据持久化)
  - [1.1 计价模型对象数据结构 (JSON Schema)](#11-计价模型对象数据结构-json-schema)
  - [1.2 Web 端存储架构与 LocalStorage 键名契约](#12-web-端存储架构与-localstorage-键名契约)
  - [1.3 CLI/Python 后端计价内核与汇率换算](#13-clipython-后端计价内核与汇率换算)
  - [1.4 磁盘两级切片缓存机制 (~/.cache/myccusage/)](#14-磁盘两级切片缓存机制-cachemyccusage)
- [2. 核心模块组织与关键接口清单](#2-核心模块组织与关键接口清单)
  - [2.1 myccusage_lib/core.py (数据内核与元数据提取)](#21-myccusage_libcorepy-数据内核与元数据提取)
  - [2.2 myccusage_lib/cli.py (命令行路由与字符级对齐排版)](#22-myccusage_libclipy-命令行路由与字符级对齐排版)
  - [2.3 myccusage_lib/web/server.py (零依赖 HTTP 服务与心跳自退)](#23-myccusage_libwebserverpy-零依赖-http-服务与心跳自退)
  - [2.4 myccusage_lib/web/static/app.js (响应式客户端与动态重算)](#24-myccusage_libwebstaticappjs-响应式客户端与动态重算)
- [3. Agent 维护与二次开发实战指南 (Cookbook)](#3-agent-维护与二次开发实战指南-cookbook)
  - [3.1 新增一个全新 Agent 适配](#31-新增一个全新-agent-适配)
  - [3.2 增加或更新预设计价模型](#32-增加或更新预设计价模型)
  - [3.3 缓存清理与调试技巧](#33-缓存清理与调试技巧)
  - [3.4 版本发布与 PyPI 发版自动化流程](#34-版本发布与-pypi-发版自动化流程)

---

## 1. 计价规则体系与数据持久化

### 1.1 计价模型对象数据结构 (JSON Schema)

无论是系统预设、用户新增/导入，还是前端导出的计价模型，均严格遵循以下规范定义：

```json
{
  "id": "deepseek-v4.1-flash",
  "name": "DeepSeek-V4.1-Flash (高峰期)",
  "badge": "官方高峰期",
  "currency": "CNY",
  "inputRate": 2.0,
  "cacheRate": 0.04,
  "outputRate": 8.0,
  "isBuiltin": true,
  "isModified": false,
  "note": "官方高峰期计费标准 (输入未命中 ¥2/M | 缓存命中 ¥0.04/M | 输出 ¥8/M)"
}
```

#### 字段语义说明：
- `id` (`string`, 必需): 模型唯一代号，全小写字母、数字与连字符（如 `deepseek-v4.1-flash`）。
- `name` (`string`, 必需): 前端展示名称。
- `badge` (`string`, 可选): 标签说明（如 `官方高峰期`、`官方低谷期`、`自定义`）。
- `currency` (`string`, 必需): 货币种类，目前支持 `"CNY"`（人民币）或 `"USD"`（美元）。
- `inputRate` (`number`, 必需): 每 100 万（1M）未命中 Input Tokens 的单价。
- `cacheRate` (`number`, 必需): 每 100 万（1M）命中 Cache Tokens 的单价。
- `outputRate` (`number`, 必需): 每 100 万（1M）Output Tokens（含思考过程/Reasoning）的单价。
- `isBuiltin` (`boolean`, 可选): 是否为系统出厂预设模型。
- `isModified` (`boolean`, 可选): 是否被用户编辑覆盖过。
- `note` (`string`, 可选): 详细计费说明文字。

#### 批量导入/导出 JSON 格式：
前端模态框导入或导出 JSON 时，采用封装外层对象：
```json
{
  "version": "1.0",
  "exportedAt": "2026-09-10T12:00:00.000Z",
  "models": {
    "model-id-1": { ... },
    "model-id-2": { ... }
  }
}
```

---

### 1.2 Web 端存储架构与 LocalStorage 键名契约

Web 前端（`app.js`）完全基于浏览器客户端持久化存储，无需数据库，各 Key 约定如下：

| Key 名 | 类型 | 作用与生命周期 | 默认回退值 |
| :--- | :--- | :--- | :--- |
| `myccusage_pricing_model` | `string` | 记录当前选中的计价模型 `id`。每次切换模型下拉菜单时自动写入。 | `'deepseek-v4.1-flash'` |
| `myccusage_custom_pricing_models` | `string` (JSON) | 存储用户在前端新建、导入或修改过的模型字典（Map: `id -> ModelObject`）。 | `'{}'` |
| `myccusage_deleted_pricing_models` | `string` (JSON) | 存储用户删除的模型 `id` 列表（`Array<string>`），用于屏蔽系统内置模型的展示。 | `'[]'` |
| `myccusage_theme` | `string` | 当前界面主题：`'dark'` 或 `'light'`。 | `'dark'` |

#### 模型聚合算法 (`getAllPricingModels()`)：
1. 浅拷贝出厂预设 `DEFAULT_PRICING_MODELS`；
2. 读取 `myccusage_custom_pricing_models`，合并/覆盖预设；
3. 读取 `myccusage_deleted_pricing_models`，剔除已被标记删除的 ID；
4. 若当前存储的 `pricingModel` 不存在于最终列表中，自动降级回退至 `'deepseek-v4.1-flash'`。

---

### 1.3 CLI/Python 后端计价内核与汇率换算

CLI 终端排版报表时，默认采用最新官方 **DeepSeek-V4.1-Flash 高峰期**定价公式（定义在 `myccusage_lib/core.py`）：

```python
def calc_deepseek_cost(input_tokens, cache_read_tokens, total_output_tokens):
    """
    DeepSeek-V4.1-Flash 官方高峰期定价算法（自 2026 年 9 月 10 日生效）：
    - 输入（未命中/Cache Miss）：¥2.00 / 1M Tokens
    - 输入（命中缓存/Cache Hit）：¥0.04 / 1M Tokens
    - 输出（含思维链/Output+Reasoning）：¥8.00 / 1M Tokens
    """
    cny = (input_tokens * 2.0 + cache_read_tokens * 0.04 + total_output_tokens * 8.0) / 1_000_000
    return cny
```

#### 汇率换算约定：
- 当前后端统一按 `$1 USD = ¥7.25 CNY` 折算；
- `costUsd = cny / 7.25`；
- 输出保留两位小数，如 `¥12.50 (~$1.72 USD)`。

---

### 1.4 磁盘两级切片缓存机制 (`~/.cache/myccusage/`)

#### 缓存目录与命名：
- 目录路径：`os.path.expanduser("~/.cache/myccusage")`
- 单 Agent 缓存文件：`~/.cache/myccusage/{agent}_daily.json`（例如 `agy_daily.json`、`claude_daily.json`）

#### 缓存数据结构：
```json
{
  "2026-09-08": [
    {
      "sessionId": "4955ce77-96a9-467a-...",
      "totalTokens": 150000,
      "inputTokens": 100000,
      "cacheReadTokens": 45000,
      "lastActivity": "2026-09-08T15:30:00Z"
    }
  ]
}
```

#### 增量同步与防漂移策略：
1. 先通过 `ccusage <agent> daily --json` 获取所有有活动的日期列表；
2. 若某日期为**过去的历史日**且缓存中已存在，则**直接读取缓存**（0.1ms 瞬时响应）；
3. 若某日期为**今天 (Today)** 或**未缓存的历史日**，则实时执行：
   ```bash
   ccusage <agent> session -s <Date> -u <Date> --json
   ```
   获得该单日的准确切片，并对历史日进行回写落盘。确保历史小计绝不漂移，今日实时消耗保持最新。

---

## 2. 核心模块组织与关键接口清单

### 项目目录树：
```
myccusage/
├── myccusage.py                 # CLI 入口，处理软链接并委托 cli.py
├── myccusage_lib/
│   ├── __init__.py             # 版本号与元数据定义 (__version__ = "1.2.2")
│   ├── core.py                 # 标题解析、底层切片采集、两级缓存、聚合计算内核
│   ├── cli.py                  # CLI 参数解析、Unicode 字符级中英宽度排版渲染
│   └── web/
│       ├── server.py           # 原生单文件 HTTP 服务、REST API、30s 心跳自退
│       └── static/
│           ├── index.html      # 单页 Dashboard 结构
│           ├── style.css       # 响应式玻璃拟态暗色/亮色样式
│           └── app.js          # 原生 JavaScript 状态流、动态全站重算、Chart.js
├── README.md                   # 面向终端开发者与用户的标准文档
├── README.agent.md             # 面向 AI Agent 与系统维护者的工程架构指南 (本文档)
├── install.sh                  # 一键链接与全局环境配置脚本
└── pyproject.toml              # PEP 621 打包配置与 PyPI 发布入口
```

---

### 2.1 `myccusage_lib/core.py` (数据内核与元数据提取)

#### 全局常量与注册表：
- `SUPPORTED_AGENTS`:
  ```python
  SUPPORTED_AGENTS = {
      "agy": {"name": "Google Antigravity", "subcmd": "antigravity", "has_times": False},
      "claude": {"name": "Claude Code", "subcmd": "claude", "has_times": False},
      "hermes": {"name": "Hermes Agent", "subcmd": "hermes", "has_times": True},
      "codex": {"name": "OpenAI Codex", "subcmd": "codex", "has_times": False},
      "grok": {"name": "Grok", "subcmd": "grok", "has_times": False},
      "pi": {"name": "Pi Agent", "subcmd": "pi", "has_times": False},
      "opencode": {"name": "OpenCode", "subcmd": "opencode", "has_times": True},
      "workbuddy": {"name": "WorkBuddy", "subcmd": "workbuddy", "has_times": True},
  }
  ```

#### 核心数据处理接口：
- `get_daily_data(agent_type: str, sort_by_tokens: bool = False) -> dict`
  - **作用**：获取每日账本流水。
  - **返回值**：字典包含 `agent`, `displayName`, `activeDaysCount`, `totalRecordsCount`, `days`（按日期分组的会话列表、`subtotal` 日小计、`weekSummary` 周小计）、`grandTotal`（全周期汇总）。
- `get_session_data(agent_type: str, sort_by_tokens: bool = False, clean_args: list = None) -> dict`
  - **作用**：获取各 Session 全生命周期的累计消耗总览。
  - **返回值**：字典包含 `sessions` 列表（含 `sessionId`, `time`, `title`, `totalTokens`, `cost`, `hitRate` 等）及 `summary`。
- `get_all_agents_summary() -> dict`
  - **作用**：Web 看板首屏使用的 8 大 Agent 跨助手全景对比数据，包含各 Agent 总 Token、各部分细分与折算总费用。

#### 原生标题与时间提取函数（均返回 `dict[str, str]` 映射 `sessionId -> title`）：
- `get_agy_titles()`: 从 `~/.gemini/antigravity/agyhub_summaries_proto.pb` 反序列化二进制 UTF-8 文本；兜底读取 `transcript.jsonl` 首行。
- `get_claude_titles()`: 从 `~/.claude/history.jsonl` 及各工程 `~/.claude/projects/*/*.jsonl` 中读取。
- `get_hermes_titles_and_times()`: 读取 `~/.hermes/state.db` SQLite 数据表。
- `get_codex_titles()`: 读取 `~/.codex/session_index.jsonl` 与各 rollout 记录。
- `get_grok_titles()`: 读取 `~/.grok/sessions/session_search.sqlite` 与 `prompt_history.jsonl`。
- `get_pi_titles()`: 读取 `~/.pi/agent/sessions/*/*.jsonl`。
- `get_opencode_titles_and_times()`: 读取 `~/.local/share/opencode/opencode.db`。
- `get_workbuddy_titles_and_times()`: 读取 `~/.workbuddy/workbuddy.db` SQLite 数据表；兜底读取 `~/.workbuddy/projects/*/*.jsonl`。

---

### 2.2 `myccusage_lib/cli.py` (命令行路由与字符级对齐排版)

- `main()`: 解析命令行入参。未传递 agent 参数时触发 `--help`；捕获底层 `ccusage` 缺失异常并友好提示。
- `pad_str(s: str, width: int, align: str = "left") -> str`:
  - **极其关键**：利用 `unicodedata.east_asian_width(ch)` 精确计算每个字符在终端的显示列宽（全角中文算 2 列，半角英文算 1 列）。
  - **任何修改终端输出样式的 Agent 必须复用此函数**，否则会导致中英混合表格竖线错位。
- `render_daily_table(data: dict)`: 将日账本数据以高对比度 ASCII/Unicode 边框输出，最新日期位于表格最下方。
- `render_session_table(data: dict)`: 渲染项目累计总览报表。

---

### 2.3 `myccusage_lib/web/server.py` (零依赖 HTTP 服务与心跳自退)

- 基于 Python 标准库 `http.server.HTTPServer` 实现，无需 Flask/FastAPI/Uvicorn 等第三方重量依赖。
- **RESTful 路由表**：
  - `GET /api/data?agent=<agent>&mode=<daily|session>&sort=<time|tokens>`: 返回单 Agent 详细数据。
  - `GET /api/all_agents`: 返回全 Agent 横向对比概览。
  - `POST /api/heartbeat`: 客户端每 3 秒发送一次心跳保活。
  - `POST /api/exit`: 浏览器页面关闭触发 `sendBeacon` 即刻结束进程。
- **心跳守护设计 (`_auto_killer_loop`)**：
  - 后台守护线程检测 `last_heartbeat_time`。若页面全部关闭超过 30 秒无任何心跳，自动触发 `os._exit(0)`，杜绝占用端口产生僵尸进程。

---

### 2.4 `myccusage_lib/web/static/app.js` (响应式客户端与动态重算)

- **核心状态容器 (`state`)**：
  ```javascript
  const state = {
    agent: 'agy',
    mode: 'daily',
    sort: 'time',
    timeSortOrder: 'desc',
    pricingModel: 'deepseek-v4.1-flash',
    data: null,
    allAgentsData: null,
    trendChartInstance: null,
    donutChartInstance: null,
    isDarkTheme: true
  };
  ```
- **核心动态重算算法 (`recalculateAllCosts()`)**：
  - 当用户在前端切换或编辑计价模型时，**无需重新向后端请求接口**。
  - 前端基于当前内存中的 Raw Token 数，以微秒级重算每一条 Session、日小计、周小计、大计与图表数据集，体验丝滑。
- **图表渲染生命周期 (`renderCharts()`)**：
  - 在重新绘制前必须调用 `destroy()` 销毁旧 Chart 实例，避免 Canvas 重影及内存泄漏。

---

## 3. Agent 维护与二次开发实战指南 (Cookbook)

### 3.1 新增一个全新 Agent 适配

假设需要新增一个名为 `cursor` 的 AI Agent：

1. **在 `myccusage_lib/core.py` 注册**：
   ```python
   SUPPORTED_AGENTS["cursor"] = {
       "name": "Cursor IDE",
       "subcmd": "cursor",  # ccusage cursor 子命令
       "has_times": False
   }
   ```
2. **编写原生标题提取器**：
   在 `core.py` 增加 `get_cursor_titles() -> dict[str, str]`，解析其本地状态存储，并在 `get_daily_data` 和 `get_session_data` 的 `agent_type == "cursor"` 分支中进行调用。
3. **在 `cli.py` 添加参数映射**：
   在 `main()` 参数解析部分增加 `--cursor` 选项，并更新 `print_usage_hint()`。
4. **在 `index.html` 增加选择项**：
   在 `<div class="agent-tabs">` 中增加对应 Tab 按钮。

---

### 3.2 增加或更新预设计价模型

1. **在 `myccusage_lib/web/static/app.js` 的 `DEFAULT_PRICING_MODELS` 添加或修改条目**：
   ```javascript
   'my-new-model': {
     id: 'my-new-model',
     name: 'My-New-Model',
     badge: '官方标准',
     currency: 'CNY',
     inputRate: 1.5,
     cacheRate: 0.03,
     outputRate: 5.0,
     isBuiltin: true,
     note: '计费说明'
   }
   ```
2. **如需设为默认模型**：
   同步更新 `app.js` 中的 `state.pricingModel`、`initApp()` 中的 fallback，以及 `core.py` 中的 `calc_deepseek_cost` 函数（若该模型为后端默认标准）。

---

### 3.3 缓存清理与调试技巧

- **清理切片缓存**：
  若底层数据不一致或开发调试解析逻辑，可直接删除缓存目录：
  ```bash
  rm -rf ~/.cache/myccusage/
  ```
- **CLI 单步调试**：
  ```bash
  # 运行并打印详细输出
  python3 myccusage.py --agy -d
  ```
- **Web 前端本地开发**：
  ```bash
  python3 myccusage.py --web -p 8488
  ```

---

### 3.4 版本发布与 PyPI 发版自动化流程

本项目已配置 GitHub Actions 自动化发布流水线（`.github/workflows/publish.yml`）：

1. **版本号对齐**（确保两处严格一致）：
   - `myccusage_lib/__init__.py`: `__version__ = "X.Y.Z"`
   - `pyproject.toml`: `version = "X.Y.Z"`
2. **本地预构建与校验**：
   ```bash
   python3 -m build
   python3 -m twine check dist/*
   ```
3. **提交代码并打 Git 标签**：
   ```bash
   git add -A
   git commit -m "chore: release vX.Y.Z"
   git tag -a vX.Y.Z -m "Release vX.Y.Z"
   ```
4. **推送触发自动化部署**：
   ```bash
   git push origin main --tags
   ```
   GitHub Actions 检测到 `v*` 标签后，将自动构建分发包并利用预设的 `PYPI_API_TOKEN` 上传至 PyPI 官方索引库。
