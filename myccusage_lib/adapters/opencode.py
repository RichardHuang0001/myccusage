"""
myccusage_lib.adapters.opencode:
OpenCode 原生适配器:
- 直连 ~/.local/share/opencode/opencode.db SQLite (系统级只读模式)
- 读取 session 表，提取毫秒级极速统计
"""

from __future__ import annotations

import os
import sqlite3
from .base import BaseAgentAdapter, ms_to_iso, ms_to_date_str

class OpenCodeAdapter(BaseAgentAdapter):
    """OpenCode 原生适配器，读取 SQLite 获取数据"""
    agent_id = "opencode"
    display_name = "OpenCode"
    has_times = True

    def __init__(self):
        """初始化 OpenCode 数据库路径"""
        super().__init__()
        self.base_dir = os.path.expanduser("~/.local/share/opencode")
        self.db_path = os.path.join(self.base_dir, "opencode.db")

    def is_available(self) -> bool:
        """检查数据库文件是否存在"""
        return os.path.exists(self.db_path)

    def get_titles_and_times(self) -> tuple[dict[str, str], dict[str, str]]:
        """从 session 表提取标题及时间信息"""
        titles = {}
        times = {}
        if not self.is_available():
            return titles, times
        try:
            uri = f"file:{self.db_path}?mode=ro"
            # 建立只读连接，保障读操作不干扰数据库写入
            conn = sqlite3.connect(uri, uri=True, timeout=3.0)
            cur = conn.cursor()
            cur.execute("SELECT id, title, time_created, time_updated FROM session")
            for sid, title, tc, tu in cur.fetchall():
                ts = tu or tc
                if ts:
                    times[sid] = ms_to_iso(ts)
                if title and title.strip():
                    titles[sid] = title.strip()
            conn.close()
        except Exception:
            pass
        return titles, times

    def fetch_data(self) -> tuple[dict[str, list[dict]], list[dict]]:
        """
        查询 OpenCode 数据库，提取统计数据。
        """
        if not self.is_available():
            return {}, []

        daily_map = {}
        session_list = []

        try:
            uri = f"file:{self.db_path}?mode=ro"
            conn = sqlite3.connect(uri, uri=True, timeout=3.0)
            cur = conn.cursor()

            sql = """
                SELECT
                    id,
                    time_created,
                    time_updated,
                    tokens_input,
                    tokens_output,
                    tokens_cache_read,
                    tokens_cache_write
                FROM session
                WHERE (tokens_input + tokens_cache_read + tokens_output + tokens_cache_write) > 0
                ORDER BY time_created ASC
            """
            for row in cur.execute(sql):
                sid, tc, tu, inp, out, cr, cw = row
                act_time = tu or tc or 0
                date_str = ms_to_date_str(act_time) if act_time else "1970-01-01"
                iso_str = ms_to_iso(act_time) if act_time else ""
                # cw (cache_write) 计入 inputTokens 或 totalTokens
                # 这里做数据平整化处理
                tot = inp + cr + cw + out

                # 每日切片记录 (按天聚合)
                if date_str not in daily_map:
                    daily_map[date_str] = []
                daily_map[date_str].append({
                    "sessionId": sid,
                    "date": date_str,
                    "inputTokens": inp + cw,
                    "cacheReadTokens": cr,
                    "outputTokens": out,
                    "totalTokens": tot,
                    "lastActivity": iso_str
                })

                # 项目生命周期汇总记录
                session_list.append({
                    "sessionId": sid,
                    "inputTokens": inp + cw,
                    "cacheReadTokens": cr,
                    "outputTokens": out,
                    "totalTokens": tot,
                    "lastActivity": iso_str
                })
            conn.close()
        except Exception:
            pass

        return daily_map, session_list
