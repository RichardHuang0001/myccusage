"""
myccusage_lib.adapters.grok:
Grok Build CLI 原生适配器:
- 读取 session_search.sqlite、summary.json 与 prompt_history.jsonl 获取标题
- 流式解析 ~/.grok/sessions/**/updates.jsonl 提取各轮消耗
"""

from __future__ import annotations

import os
import glob
import json
import sqlite3
from .base import BaseAgentAdapter, ts_to_iso, ts_to_date_str, scan_files_fast, get_candidate_home_dirs

class GrokAdapter(BaseAgentAdapter):
    """Grok 适配器，支持 SQLite 及本地日志文件的解析与防抖缓存"""
    agent_id = "grok"
    display_name = "Grok"

    def __init__(self):
        """初始化 Grok 配置和会话目录，支持跨环境多根探测"""
        super().__init__()
        self.base_dirs = [
            os.path.join(h, ".grok")
            for h in get_candidate_home_dirs()
            if os.path.exists(os.path.join(h, ".grok"))
        ]
        if not self.base_dirs:
            self.base_dirs = [os.path.expanduser("~/.grok")]
        self.base_dir = self.base_dirs[0]
        self.sessions_dirs = [
            os.path.join(b, "sessions")
            for b in self.base_dirs
            if os.path.exists(os.path.join(b, "sessions"))
        ]
        self.sessions_dir = self.sessions_dirs[0] if self.sessions_dirs else os.path.join(self.base_dir, "sessions")

    def is_available(self) -> bool:
        """检查 grok 配置目录是否存在"""
        return any(os.path.exists(b) for b in self.base_dirs)

    def get_titles_and_times(self) -> tuple[dict[str, str], dict[str, str]]:
        """从 SQLite 及 jsonl 中提取标题数据"""
        titles = {}
        times = {}
        if not self.is_available():
            return titles, times

        # 从 SQLite 数据库读取
        for sdir in self.sessions_dirs:
            db_path = os.path.join(sdir, "session_search.sqlite")
            if os.path.exists(db_path):
                try:
                    uri = f"file:{db_path}?mode=ro"
                    conn = sqlite3.connect(uri, uri=True, timeout=3.0)
                    cur = conn.cursor()
                    cur.execute("SELECT session_id, title FROM session_docs")
                    for sid, t in cur.fetchall():
                        if t and t.strip():
                            titles[sid] = t.strip()[:60]
                    conn.close()
                except Exception:
                    pass

        # 从 summary 日志读取
        for sdir in self.sessions_dirs:
            for summary_path in glob.glob(os.path.join(sdir, "**", "summary.json"), recursive=True):
                try:
                    with open(summary_path, "r", encoding="utf-8") as f:
                        sdata = json.load(f)
                        sid = sdata.get("info", {}).get("id")
                        summ = sdata.get("session_summary")
                        if sid and summ and summ.strip() and sid not in titles:
                            titles[sid] = summ.strip()[:60]
                except Exception:
                    pass

        # 从 prompt 历史日志读取
        for sdir in self.sessions_dirs:
            for ph in glob.glob(os.path.join(sdir, "*", "prompt_history.jsonl")):
                try:
                    with open(ph, "r", encoding="utf-8") as f:
                        for line in f:
                            try:
                                row = json.loads(line)
                                sid = row.get("session_id")
                                p = row.get("prompt")
                                if sid and p and sid not in titles:
                                    titles[sid] = p.strip()[:60]
                            except Exception:
                                pass
                except Exception:
                    pass

        return titles, times

    def get_source_fingerprint(self) -> str:
        """极速获取 Grok 会话目录修改状态指纹 (< 1ms)"""
        if not self.is_available():
            return ""
        parts = []
        for sdir in self.sessions_dirs:
            db_path = os.path.join(sdir, "session_search.sqlite")
            if os.path.exists(db_path):
                try:
                    st = os.stat(db_path)
                    parts.append(f"{st.st_mtime_ns}:{st.st_size}")
                except OSError:
                    pass
        hot = scan_files_fast(self.sessions_dirs, extensions=(".jsonl",), recursive=True, today_only=True)
        parts.append(str(len(hot)))
        max_m = 0
        for h in hot:
            try:
                mt = os.path.getmtime(h)
                if mt > max_m:
                    max_m = mt
            except OSError:
                pass
        parts.append(str(max_m))
        return "|".join(parts)

    def fetch_data(self, today_only: bool = False) -> tuple[dict[str, list[dict]], list[dict]]:
        """
        提取 Grok 的会话数据，通过分析 updates.jsonl 中的 turn_completed 获取每轮消耗。
        - 支持 today_only: 仅扫描今日活跃文件 (提速 50x)
        """
        if not self.is_available():
            return {}, []

        fp = self.get_source_fingerprint()

        cached = self._cached_full_result(fp, today_only)
        if cached is not None:
            return cached

        all_records = []

        files = scan_files_fast(self.sessions_dirs, extensions=("updates.jsonl",), recursive=True, today_only=today_only)

        with self._lock:
            if not self._file_cache:
                self._load_persisted_file_cache()
            cache_modified = False

            for fpath in files:
                try:
                    stat = os.stat(fpath)
                except OSError:
                    continue

                mtime, size = stat.st_mtime, stat.st_size
                cached = self._file_cache.get(fpath)

                # 使用防抖缓存策略
                if cached and cached[0] == mtime and cached[1] == size:
                    records = cached[2]
                else:
                    records = []
                    sid = os.path.basename(os.path.dirname(fpath))
                    try:
                        with open(fpath, "r", encoding="utf-8") as f:
                            for line in f:
                                if "turn_completed" not in line:
                                    continue
                                try:
                                    obj = json.loads(line)
                                except Exception:
                                    continue
                                u = obj.get("params", {}).get("update", {}).get("usage") or {}
                                raw_inp = u.get("inputTokens", 0)
                                c_read = u.get("cachedReadTokens", 0)
                                out = u.get("outputTokens", 0)
                                inp = max(0, raw_inp - c_read)
                                tot = inp + c_read + out
                                if tot == 0:
                                    continue

                                ts = obj.get("timestamp") or 0
                                date_str = ts_to_date_str(ts) if ts else "1970-01-01"
                                iso_str = ts_to_iso(ts) if ts else ""

                                records.append((sid, date_str, iso_str, inp, c_read, out, tot))
                    except Exception:
                        pass
                    # 更新文件防抖缓存
                    self._file_cache[fpath] = (mtime, size, records)
                    cache_modified = True

                all_records.extend(records)

            if cache_modified and not today_only:
                self._save_persisted_file_cache()

        daily_res, session_res = self._accumulate_records(all_records)
        self._store_full_result(fp, daily_res, session_res, today_only)
        return daily_res, session_res

