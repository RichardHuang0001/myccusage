"""
myccusage_lib.adapters.workbuddy:
WorkBuddy (腾讯旗下 AI 编程 Agent) 原生适配器:
- 读取 ~/.workbuddy/workbuddy.db (SQLite 只读模式) 获取会话元数据
- 流式解析 ~/.workbuddy/projects/*/*.jsonl (带 mtime 增量缓存)
"""

from __future__ import annotations

import os
import glob
import json
import sqlite3
from .base import BaseAgentAdapter, ms_to_iso, ms_to_date_str, scan_files_fast, get_candidate_home_dirs

class WorkBuddyAdapter(BaseAgentAdapter):
    """WorkBuddy 适配器，结合 SQLite 的元数据与 JSONL 日志文件的用量数据进行分析"""
    agent_id = "workbuddy"
    display_name = "WorkBuddy"

    def __init__(self):
        """初始化 WorkBuddy 基础配置路径，支持跨环境多根探测"""
        super().__init__()
        self.base_dirs = [
            os.path.join(h, ".workbuddy")
            for h in get_candidate_home_dirs()
            if os.path.exists(os.path.join(h, ".workbuddy"))
        ]
        if not self.base_dirs:
            self.base_dirs = [os.path.expanduser("~/.workbuddy")]
        self.base_dir = self.base_dirs[0]
        self.db_paths = [
            os.path.join(b, "workbuddy.db")
            for b in self.base_dirs
            if os.path.exists(os.path.join(b, "workbuddy.db"))
        ]
        self.db_path = self.db_paths[0] if self.db_paths else os.path.join(self.base_dir, "workbuddy.db")

    def is_available(self) -> bool:
        """检查 WorkBuddy 目录是否存在"""
        return any(os.path.exists(b) for b in self.base_dirs)

    def get_titles_and_times(self) -> tuple[dict[str, str], dict[str, str]]:
        """从 SQLite 数据库或通过回退策略扫描日志提取对话的标题及时间戳"""
        titles = {}
        times = {}
        for db in self.db_paths:
            try:
                uri = f"file:{db}?mode=ro"
                conn = sqlite3.connect(uri, uri=True, timeout=3.0)
                cur = conn.cursor()
                for row in cur.execute("SELECT id, title, custom_title, created_at, updated_at, last_activity_at FROM sessions"):
                    sid, t, ct, ca, ua, la = row
                    title = ct or t
                    if title and title.strip():
                        titles[sid] = title.strip()
                    ts = la or ua or ca
                    if ts:
                        times[sid] = ms_to_iso(ts)
                conn.close()
            except Exception:
                pass

        # 兜底补充扫描 projects 目录中未记录在 DB 或 custom-title 的会话
        for b in self.base_dirs:
            project_files = glob.glob(os.path.join(b, "projects/*/*.jsonl"))
            for p in project_files:
                sid = os.path.basename(p).replace(".jsonl", "")
                if sid not in titles or not titles[sid]:
                    try:
                        with open(p, "r", encoding="utf-8") as f:
                            for line in f:
                                if not line.strip():
                                    continue
                                if "custom-title" in line or '"role":"user"' in line:
                                    obj = json.loads(line)
                                    if obj.get("type") == "custom-title" and obj.get("customTitle"):
                                        titles[sid] = obj["customTitle"].strip()
                                        break
                                    elif obj.get("type") == "message" and obj.get("role") == "user":
                                        cnt = obj.get("content", [])
                                        if isinstance(cnt, list):
                                            for item in cnt:
                                                if isinstance(item, dict) and item.get("text"):
                                                    titles[sid] = item["text"].split("\n")[0][:60].strip()
                                                    break
                                        elif isinstance(cnt, str):
                                            titles[sid] = cnt.split("\n")[0][:60].strip()
                                        if sid in titles:
                                            break
                    except Exception:
                        pass
        return titles, times

    def get_source_fingerprint(self) -> str:
        """极速获取 WorkBuddy 目录修改状态指纹 (< 1ms)"""
        if not self.is_available():
            return ""
        parts = []
        for db in self.db_paths:
            try:
                st = os.stat(db)
                parts.append(f"{st.st_mtime_ns}:{st.st_size}")
            except OSError:
                pass
        dirs = []
        for b in self.base_dirs:
            p_dir = os.path.join(b, "projects")
            s_dir = os.path.join(b, "sessions")
            if os.path.isdir(p_dir):
                dirs.append(p_dir)
            if os.path.isdir(s_dir):
                dirs.append(s_dir)
        hot = scan_files_fast(dirs, extensions=(".jsonl",), recursive=True, today_only=True)
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
        解析 WorkBuddy 的 jsonl 文件提取消耗数据。
        支持特殊数据格式，如 rawUsage vs usage 的平滑兼容。
        - 支持 today_only: 仅扫描今日活跃文件 (提速 50x)
        """
        if not self.is_available():
            return {}, []

        fp = self.get_source_fingerprint()

        cached = self._cached_full_result(fp, today_only)
        if cached is not None:
            return cached

        dirs = []
        for b in self.base_dirs:
            p_dir = os.path.join(b, "projects")
            s_dir = os.path.join(b, "sessions")
            if os.path.isdir(p_dir):
                dirs.append(p_dir)
            if os.path.isdir(s_dir):
                dirs.append(s_dir)
        files = scan_files_fast(dirs, extensions=(".jsonl",), recursive=True, today_only=today_only)

        all_records = []

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

                # 使用 mtime 和 size 的防抖缓存，避免每次全量解析所有 jsonl
                if cached and cached[0] == mtime and cached[1] == size:
                    records = cached[2]
                else:
                    records = []
                    sid = os.path.basename(fpath).replace(".jsonl", "")
                    try:
                        with open(fpath, "r", encoding="utf-8") as f:
                            for line in f:
                                if not line.strip() or ("usage" not in line and "rawUsage" not in line):
                                    continue
                                try:
                                    obj = json.loads(line)
                                except Exception:
                                    continue
                                pd = obj.get("providerData") or {}
                                ru = pd.get("rawUsage")
                                u = pd.get("usage")
                                if not ru and not u:
                                    continue
                                ts = obj.get("timestamp")
                                if not ts:
                                    continue

                                date_str = ms_to_date_str(ts)
                                iso_str = ms_to_iso(ts)

                                # 兼容 rawUsage 与 usage 两种特殊数据格式
                                if ru:
                                    hit = ru.get("prompt_cache_hit_tokens", 0)
                                    miss = ru.get("prompt_cache_miss_tokens", 0)
                                    out = ru.get("completion_tokens", 0)
                                else:
                                    if "input_tokens" in u:
                                        miss = u.get("input_tokens", 0)
                                        hit = 0
                                        out = u.get("output_tokens", 0)
                                    else:
                                        inp = u.get("inputTokens", 0)
                                        hit = sum(d.get("cached_tokens", 0) for d in u.get("inputTokensDetails", []))
                                        miss = max(0, inp - hit)
                                        out = u.get("outputTokens", 0)
                                tot = hit + miss + out
                                records.append((sid, date_str, iso_str, miss, hit, out, tot))
                    except Exception:
                        records = cached[2] if cached else []
                    else:
                        self._file_cache[fpath] = (mtime, size, records)
                        cache_modified = True

                all_records.extend(records)

            if cache_modified and not today_only:
                self._save_persisted_file_cache()

        daily_res, session_res = self._accumulate_records(all_records)
        self._store_full_result(fp, daily_res, session_res, today_only)
        return daily_res, session_res

