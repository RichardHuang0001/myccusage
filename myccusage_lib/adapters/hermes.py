"""
myccusage_lib.adapters.hermes:
Hermes Agent 原生适配器:
- 直连 ~/.hermes/state.db SQLite (系统级只读模式)
- 读取 sessions 与 session_model_usage 表，提取毫秒级极速统计
"""

from __future__ import annotations

import os
import sqlite3
from .base import BaseAgentAdapter, ts_to_iso, ts_to_date_str, get_today_midnight_ts, get_candidate_home_dirs

class HermesAdapter(BaseAgentAdapter):
    """Hermes Agent 适配器，通过直连 SQLite 数据库进行高速查询"""
    agent_id = "hermes"
    display_name = "Hermes Agent"

    def __init__(self):
        """初始化数据库连接路径，支持跨环境多根探测"""
        super().__init__()
        self.base_dirs = [
            os.path.join(h, ".hermes")
            for h in get_candidate_home_dirs()
            if os.path.exists(os.path.join(h, ".hermes"))
        ]
        if not self.base_dirs:
            self.base_dirs = [os.path.expanduser("~/.hermes")]
        self.base_dir = self.base_dirs[0]
        self.db_paths = [
            os.path.join(b, "state.db")
            for b in self.base_dirs
            if os.path.exists(os.path.join(b, "state.db"))
        ]
        self.db_path = self.db_paths[0] if self.db_paths else os.path.join(self.base_dir, "state.db")

    def is_available(self) -> bool:
        """检查 state.db 数据库文件是否存在"""
        return len(self.db_paths) > 0

    def get_source_fingerprint(self) -> str:
        """快速获取 state.db 修改状态指纹 (< 0.1ms)"""
        if not self.is_available():
            return ""
        parts = []
        for db in self.db_paths:
            try:
                st = os.stat(db)
                wal_path = db + "-wal"
                wal_mtime = 0
                if os.path.exists(wal_path):
                    try:
                        wal_mtime = os.stat(wal_path).st_mtime_ns
                    except OSError:
                        pass
                parts.append(f"{st.st_mtime_ns}:{st.st_size}:{wal_mtime}")
            except OSError:
                pass
        return "|".join(parts)

    def get_titles_and_times(self) -> tuple[dict[str, str], dict[str, str]]:
        """从 sessions 表提取所有会话的标题和时间"""
        titles = {}
        times = {}
        if not self.is_available():
            return titles, times
        for db in self.db_paths:
            try:
                uri = f"file:{db}?mode=ro"
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

    def fetch_data(self, today_only: bool = False) -> tuple[dict[str, list[dict]], list[dict]]:
        """
        查询 Hermes 数据库提取统计数据，按时间正序返回每日切片和汇总。
        - 支持 today_only: 仅扫描今日活跃会话 (SQL 过滤提速)
        """
        if not self.is_available():
            return {}, []

        fp = self.get_source_fingerprint()

        cached = self._cached_full_result(fp, today_only)
        if cached is not None:
            return cached

        daily_map = {}
        session_list = []

        for db in self.db_paths:
            try:
                uri = f"file:{db}?mode=ro"
                conn = sqlite3.connect(uri, uri=True, timeout=3.0)
                c = conn.cursor()

                where_clauses = [
                    "model IS NOT NULL",
                    "TRIM(model) != ''",
                    "(input_tokens + output_tokens + cache_read_tokens) > 0"
                ]
                params = []
                if today_only:
                    min_ts = get_today_midnight_ts()
                    where_clauses.append("(started_at >= ? OR ended_at >= ?)")
                    params.extend([min_ts, min_ts])

                where_sql = " AND ".join(where_clauses)
                sql = f"""
                    SELECT
                        id,
                        started_at,
                        ended_at,
                        input_tokens,
                        output_tokens,
                        cache_read_tokens
                    FROM sessions
                    WHERE {where_sql}
                    ORDER BY started_at ASC
                """
                for row in c.execute(sql, params):
                    sid, st, et, inp, out, cr = row
                    act_time = et or st or 0
                    date_str = ts_to_date_str(act_time) if act_time else "1970-01-01"
                    iso_str = ts_to_iso(act_time) if act_time else ""
                    tot = inp + cr + out

                    # 每日切片记录 (按天聚合)
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

        self._store_full_result(fp, daily_map, session_list, today_only)

        return daily_map, session_list
