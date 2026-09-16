"""
myccusage_lib.adapters.base:
Agent 适配器基类与公共工具函数:
- 统一定义 (daily_map, session_list) 数据返回契约
- 文件级 mtime/size 防抖缓存通用工具
- 统一毫秒/秒级时间戳转换与 ISO 格式化
"""

import os
import threading
from datetime import datetime, timezone

class BaseAgentAdapter:
    agent_id = ""
    display_name = ""
    has_times = False

    def __init__(self):
        self._file_cache = {}
        self._lock = threading.Lock()

    def is_available(self) -> bool:
        """检测当前 Agent 本地数据源是否存在"""
        raise NotImplementedError

    def get_titles_and_times(self) -> tuple[dict[str, str], dict[str, str]]:
        """
        提取会话原生标题映射与时间覆盖映射:
        - titles: { sessionId: title }
        - times: { sessionId: iso_timestamp }
        """
        return {}, {}

    def fetch_data(self) -> tuple[dict[str, list[dict]], list[dict]]:
        """
        高性能提取原始数据:
        - daily_map: { "YYYY-MM-DD": [ {sessionId, date, inputTokens, cacheReadTokens, outputTokens, totalTokens, lastActivity}, ... ] }
        - session_list: [ {sessionId, inputTokens, cacheReadTokens, outputTokens, totalTokens, lastActivity}, ... ]
        """
        raise NotImplementedError

def ts_to_iso(ts_seconds: float) -> str:
    """浮点/整数秒转 ISO 8601 字符串"""
    if not ts_seconds:
        return ""
    try:
        return datetime.fromtimestamp(ts_seconds, timezone.utc).isoformat()
    except Exception:
        return ""

def ms_to_iso(ts_ms: int) -> str:
    """毫秒时间戳转 ISO 8601 字符串"""
    if not ts_ms:
        return ""
    try:
        return datetime.fromtimestamp(ts_ms / 1000.0, timezone.utc).isoformat()
    except Exception:
        return ""

def ts_to_date_str(ts_seconds: float) -> str:
    """浮点/整数秒转 YYYY-MM-DD 本地日期"""
    try:
        return datetime.fromtimestamp(ts_seconds).strftime("%Y-%m-%d")
    except Exception:
        return "1970-01-01"

def ms_to_date_str(ts_ms: int) -> str:
    """毫秒时间戳转 YYYY-MM-DD 本地日期"""
    try:
        return datetime.fromtimestamp(ts_ms / 1000.0).strftime("%Y-%m-%d")
    except Exception:
        return "1970-01-01"
