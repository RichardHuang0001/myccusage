import os
base = "/Users/huangwei/Desktop/PythonProjects/ccusage-sessions/myccusage_lib/adapters"

def r(fname, old, new):
    with open(f"{base}/{fname}", "r") as f:
        c = f.read()
    if old in c:
        c = c.replace(old, new)
        with open(f"{base}/{fname}", "w") as f:
            f.write(c)
    else:
        print(f"Failed to find '{old}' in {fname}")

r("agy.py", 
  "    def is_available(self) -> bool:", 
  "    def is_available(self) -> bool:\n        \"\"\"检测本地 Antigravity 目录或缓存文件是否存在\"\"\"")

r("agy.py",
  "    def get_titles_and_times(self)",
  "    def get_titles_and_times(self) -> tuple[dict[str, str], dict[str, str]]:\n        \"\"\"\n        解析 pb 文件和 jsonl 日志，提取对话标题。\n        \"\"\"")

r("agy.py",
  "        # 方案 A: 若有 ccusage 命令，调用 ccusage antigravity 抓取并同步缓存",
  "        # 方案 A: 若有 ccusage 命令，调用 ccusage antigravity 抓取并同步缓存\n        # 这种方式速度快，并会自动生成最新切片的缓存")

r("agy.py",
  "        # 方案 B: 若 ccusage 不可用或调用失败，读取本地 agy_daily.json 缓存",
  "        # 方案 B: 若 ccusage 不可用或调用失败，读取本地 agy_daily.json 缓存\n        # 降级方案，只读取缓存的聚合数据")

r("claude.py",
  "    def fetch_data(self) -> tuple[dict[str, list[dict]], list[dict]]:",
  "    def fetch_data(self) -> tuple[dict[str, list[dict]], list[dict]]:\n        \"\"\"\n        提取 Claude 消耗数据，使用文件 mtime/size 进行防抖缓存，避免重复读取大文件。\n        \"\"\"")

r("claude.py",
  "                    # 项目生命周期汇总",
  "                    # 项目生命周期汇总 (全生命周期累加计算)")

r("claude.py",
  "                                # 保留最新的那一次上报（通常包含完整的 thinking + output_tokens）",
  "                                # 根据 message.id 幂等去重\n                                # 保留最新的那一次上报（通常包含完整的 thinking + output_tokens），避免重复计算")

r("codex.py",
  "    def fetch_data(self) -> tuple[dict[str, list[dict]], list[dict]]:",
  "    def fetch_data(self) -> tuple[dict[str, list[dict]], list[dict]]:\n        \"\"\"\n        提取 Codex 消耗数据。\n        通过捕获 token_count 的累计增量进行差分计算。\n        \"\"\"")

r("codex.py",
  "                                delta_raw_inp = max(0, cur_raw_inp - prev_raw_inp)",
  "                                # 计算累计增量差分\n                                delta_raw_inp = max(0, cur_raw_inp - prev_raw_inp)")

r("codex.py",
  "                    # 项目生命周期汇总",
  "                    # 项目生命周期汇总 (全生命周期累加计算)")

r("grok.py",
  "    def fetch_data(self) -> tuple[dict[str, list[dict]], list[dict]]:",
  "    def fetch_data(self) -> tuple[dict[str, list[dict]], list[dict]]:\n        \"\"\"\n        提取 Grok 的会话数据，通过分析 updates.jsonl 中的 turn_completed 获取每轮消耗。\n        使用文件级 mtime/size 防抖缓存。\n        \"\"\"")

r("hermes.py",
  "    def fetch_data(self) -> tuple[dict[str, list[dict]], list[dict]]:",
  "    def fetch_data(self) -> tuple[dict[str, list[dict]], list[dict]]:\n        \"\"\"\n        查询 Hermes 数据库提取统计数据，按时间正序返回每日切片和汇总。\n        \"\"\"")

r("hermes.py",
  "                # 每日切片记录",
  "                # 每日切片记录 (按天聚合)")

r("opencode.py",
  "    def fetch_data(self) -> tuple[dict[str, list[dict]], list[dict]]:",
  "    def fetch_data(self) -> tuple[dict[str, list[dict]], list[dict]]:\n        \"\"\"\n        查询 OpenCode 数据库，提取统计数据。\n        \"\"\"")

r("pi.py",
  "    def fetch_data(self) -> tuple[dict[str, list[dict]], list[dict]]:",
  "    def fetch_data(self) -> tuple[dict[str, list[dict]], list[dict]]:\n        \"\"\"\n        提取 Pi Agent 的会话数据。\n        采用文件 mtime/size 增量缓存策略。\n        \"\"\"")

r("workbuddy.py",
  "    def fetch_data(self) -> tuple[dict[str, list[dict]], list[dict]]:",
  "    def fetch_data(self) -> tuple[dict[str, list[dict]], list[dict]]:\n        \"\"\"\n        解析 WorkBuddy 的 jsonl 文件提取消耗数据。\n        支持特殊数据格式，如 rawUsage vs usage 的平滑兼容。\n        \"\"\"")

r("workbuddy.py",
  "                                if ru:",
  "                                # 兼容 rawUsage 与 usage 两种特殊数据格式\n                                if ru:")


