"""
myccusage_lib.adapters.hermes:
Hermes Agent 原生适配器:
- 直连 ~/.hermes/state.db SQLite (系统级只读模式)
- 读取 sessions 与 session_model_usage 表，提取毫秒级极速统计
"""

import os
import sqlite3
from .base import BaseAgentAdapter, ts_to_iso, ts_to_date_str

class HermesAdapter(BaseAgentAdapter):
    agent_id = "hermes"
    display_name = "Hermes Agent"
    has_times = True

    def __init__(self):
        super().__init__()
        self.base_dir = os.path.expanduser("~/.hermes")
        self.db_path = os.path.join(self.base_dir, "state.db")

    def is_available(self) -> bool:
        return os.path.exists(self.db_path)

    def get_titles_and_times(self) -> tuple[dict[str, str], dict[str, str]]:
        titles = {}
        times = {}
        if not self.is_available():
            return titles, times
        try:
            uri = f"file:{self.db_path}?mode=ro"
            conn = sqlite3.connect(uri, uri=True, timeout=3.0)
            c = conn.cursor()
            for row in c.execute("SELECT id, started_at, ended_at, title FROM sessions"):
                sid, st, et, title = row
                last_t = et or st
                if last_t:
                    times[sid] = ts_to_iso(last_t)
                if title and title.strip():
                    titles[sid] = title.strip()
            conn.close()
        except Exception:
            pass
        return titles, times

    def fetch_data(self) -> tuple[dict[str, list[dict]], list[dict]]:
        if not self.is_available():
            return {}, []

        daily_map = {}
        session_list = []

        try:
            uri = f"file:{self.db_path}?mode=ro"
            conn = sqlite3.connect(uri, uri=True, timeout=3.0)
            c = conn.cursor()

            # 查询有效会话并按时间正序提取
            sql = """
                SELECT
                    id,
                    started_at,
                    ended_at,
                    input_tokens,
                    output_tokens,
                    cache_read_tokens
                FROM sessions
                WHERE model IS NOT NULL
                    AND TRIM(model) != ''
                    AND (input_tokens + output_tokens + cache_read_tokens) > 0
                ORDER BY started_at ASC
            """
            for row in c.execute(sql):
                sid, st, et, inp, out, cr = row
                act_time = et or st or 0
                date_str = ts_to_date_str(act_time) if act_time else "1970-01-01"
                iso_str = ts_to_iso(act_time) if act_time else ""
                tot = inp + cr + out

                # 每日切片记录
                if date_str not in daily_map:
                    daily_map[date_str] = []
                daily_map[date_str].append({
                    "sessionId": sid,
                    "date": date_str,
                    "inputTokens": inp,
                    "cacheReadTokens": cr,
                    "outputTokens": out,
                    "totalTokens": tot,
                    "lastActivity": iso_str
                })

                # 项目生命周期汇总记录
                session_list.append({
                    "sessionId": sid,
                    "inputTokens": inp,
                    "cacheReadTokens": cr,
                    "outputTokens": out,
                    "totalTokens": tot,
                    "lastActivity": iso_str
                })
            conn.close()
        except Exception:
            pass

        return daily_map, session_list
