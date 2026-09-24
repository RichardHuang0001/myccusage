"""
myccusage_lib.adapters.opencode:
OpenCode 原生适配器:
- 直连 ~/.local/share/opencode/opencode.db SQLite (系统级只读模式)
- 读取 session 表，提取毫秒级极速统计
"""

from __future__ import annotations

import os
import sqlite3
from .base import BaseAgentAdapter, ms_to_iso, ms_to_date_str, get_today_midnight_ts, get_candidate_home_dirs, UNKNOWN_MODEL

class OpenCodeAdapter(BaseAgentAdapter):
    """OpenCode 原生适配器，读取 SQLite 获取数据"""
    agent_id = "opencode"
    display_name = "OpenCode"

    def __init__(self):
        """初始化 OpenCode 数据库路径，支持跨环境多根探测"""
        super().__init__()
        self.db_paths = []
        for h in get_candidate_home_dirs():
            cand1 = os.path.join(h, ".local", "share", "opencode", "opencode.db")
            if os.path.exists(cand1):
                self.db_paths.append(cand1)
            cand2 = os.path.join(h, ".opencode", "opencode.db")
            if os.path.exists(cand2) and cand2 not in self.db_paths:
                self.db_paths.append(cand2)
        self.base_dir = os.path.dirname(self.db_paths[0]) if self.db_paths else os.path.expanduser("~/.local/share/opencode")
        self.db_path = self.db_paths[0] if self.db_paths else os.path.join(self.base_dir, "opencode.db")

    def is_available(self) -> bool:
        """检查数据库文件是否存在"""
        return len(self.db_paths) > 0

    def get_source_fingerprint(self) -> str:
        """快速获取 opencode.db 修改状态指纹 (< 0.1ms)"""
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
        """从 session 表提取标题及时间信息"""
        titles = {}
        times = {}
        if not self.is_available():
            return titles, times
        for db in self.db_paths:
            try:
                uri = f"file:{db}?mode=ro"
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

    def fetch_data(self, today_only: bool = False) -> tuple[dict[str, list[dict]], list[dict]]:
        """
        查询 OpenCode 数据库，提取统计数据。
        - 支持 today_only: 仅扫描今日活跃交互 (SQL 过滤提速 50x)
        """
        if not self.is_available():
            return {}, []

        fp = self.get_source_fingerprint()

        cached = self._cached_full_result(fp, today_only)
        if cached is not None:
            return cached

        records = []

        for db in self.db_paths:
            try:
                uri = f"file:{db}?mode=ro"
                conn = sqlite3.connect(uri, uri=True, timeout=3.0)
                cur = conn.cursor()

                min_tc = int(get_today_midnight_ts() * 1000) if today_only else 0
                # 优先从 part 表获取基于单轮交互的精确时间戳与 Token 切片
                if today_only:
                    sql_parts = """
                        SELECT
                            session_id,
                            time_created,
                            data
                        FROM part
                        WHERE time_created >= ?
                            AND data LIKE '%step-finish%'
                            AND data LIKE '%tokens%'
                        ORDER BY time_created ASC
                    """
                    cur.execute(sql_parts, (min_tc,))
                else:
                    sql_parts = """
                        SELECT
                            session_id,
                            time_created,
                            data
                        FROM part
                        WHERE data LIKE '%step-finish%'
                            AND data LIKE '%tokens%'
                        ORDER BY time_created ASC
                    """
                    cur.execute(sql_parts)
                part_rows = cur.fetchall()

                sessions_with_parts = set()

                for sid, tc, data in part_rows:
                    try:
                        import json
                        obj = json.loads(data)
                        tok = obj.get("tokens", {})
                        inp = tok.get("input", 0)
                        out = tok.get("output", 0)
                        cr = tok.get("cache", {}).get("read", 0)
                        cw = tok.get("cache", {}).get("write", 0)
                        tot = inp + out + cr + cw
                        if tot <= 0:
                            continue

                        sessions_with_parts.add(sid)
                        date_str = ms_to_date_str(tc) if tc else "1970-01-01"
                        iso_str = ms_to_iso(tc) if tc else ""
                        # TODO(二期): 替换为真实模型提取逻辑（见 docs/tasks/第二期-归属推导型.md）
                        records.append((sid, date_str, iso_str, inp + cw, cr, out, tot, UNKNOWN_MODEL))
                    except Exception:
                        pass

                # 兜底补充未在 part 表中记录 step-finish 的会话（兼容极旧版结构）
                if today_only:
                    sql_sessions = """
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
                            AND (time_updated >= ? OR time_created >= ?)
                        ORDER BY time_created ASC
                    """
                    cur.execute(sql_sessions, (min_tc, min_tc))
                else:
                    sql_sessions = """
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
                    cur.execute(sql_sessions)
                for row in cur.fetchall():
                    sid, tc, tu, inp, out, cr, cw = row
                    if sid in sessions_with_parts:
                        continue
                    act_time = tu or tc or 0
                    date_str = ms_to_date_str(act_time) if act_time else "1970-01-01"
                    iso_str = ms_to_iso(act_time) if act_time else ""
                    tot = inp + cr + cw + out

                    # TODO(二期): 替换为真实模型提取逻辑（见 docs/tasks/第二期-归属推导型.md）
                    records.append((sid, date_str, iso_str, inp + cw, cr, out, tot, UNKNOWN_MODEL))

                conn.close()
            except Exception:
                pass

        # 复用基类的统一聚合（含模型维度），避免在此重复实现累加逻辑
        daily_map, session_list = self._accumulate_records(records)

        self._store_full_result(fp, daily_map, session_list, today_only)

        return daily_map, session_list
