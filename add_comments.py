import re

def process_base(code):
    code = code.replace(
        "    def __init__(self):",
        "    def __init__(self):\n        # 存储文件级的 mtime 和 size 防抖缓存，避免重复解析同一文件\n        self._file_cache = {}\n        # 线程安全锁，保护缓存并发读写"
    )
    code = code.replace(
        "    def is_available(self) -> bool:\n        \"\"\"检测当前 Agent 本地数据源是否存在\"\"\"",
        "    def is_available(self) -> bool:\n        \"\"\"\n        检测当前 Agent 本地数据源是否存在\n        返回 True 表示数据源目录或核心文件存在\n        \"\"\""
    )
    code = code.replace(
        "    def fetch_data(self) -> tuple[dict[str, list[dict]], list[dict]]:",
        "    def fetch_data(self) -> tuple[dict[str, list[dict]], list[dict]]:\n        \"\"\"\n        高性能提取原始数据:\n        返回 (daily_map, session_list) 二元组\n        - daily_map: 每日切片数据聚合，格式为 { \"YYYY-MM-DD\": [ {sessionId, date, inputTokens, cacheReadTokens, outputTokens, totalTokens, lastActivity}, ... ] }\n        - session_list: 全生命周期汇总，格式为 [ {sessionId, inputTokens, cacheReadTokens, outputTokens, totalTokens, lastActivity}, ... ]\n        \"\"\""
    )
    return code

with open("/Users/huangwei/Desktop/PythonProjects/ccusage-sessions/myccusage_lib/adapters/base.py", "r") as f:
    code = f.read()
with open("/Users/huangwei/Desktop/PythonProjects/ccusage-sessions/myccusage_lib/adapters/base.py", "w") as f:
    f.write(process_base(code))

