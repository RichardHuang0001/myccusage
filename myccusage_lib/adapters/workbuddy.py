"""
myccusage_lib.adapters.workbuddy:
WorkBuddy (腾讯旗下 AI 编程 Agent) 原生适配器:
- 读取 ~/.workbuddy/workbuddy.db (SQLite 只读模式) 获取会话元数据
- 流式解析 ~/.workbuddy/projects/*/*.jsonl (带 mtime 增量缓存)
"""

import os
import glob
import json
import sqlite3
from .base import BaseAgentAdapter, ms_to_iso, ms_to_date_str

class WorkBuddyAdapter(BaseAgentAdapter):
    agent_id = "workbuddy"
    display_name = "WorkBuddy"
    has_times = True

    def __init__(self):
        super().__init__()
        self.base_dir = os.path.expanduser("~/.workbuddy")
        self.db_path = os.path.join(self.base_dir, "workbuddy.db")

    def is_available(self) -> bool:
        return os.path.exists(self.base_dir)

    def get_titles_and_times(self) -> tuple[dict[str, str], dict[str, str]]:
        titles = {}
        times = {}
        if os.path.exists(self.db_path):
            try:
                uri = f"file:{self.db_path}?mode=ro"
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
        project_files = glob.glob(os.path.join(self.base_dir, "projects/*/*.jsonl"))
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

    def fetch_data(self) -> tuple[dict[str, list[dict]], list[dict]]:
        if not self.is_available():
            return {}, []

        project_globs = [
            os.path.join(self.base_dir, "projects/*/*.jsonl"),
            os.path.join(self.base_dir, "sessions/*/*.jsonl"),
            os.path.join(self.base_dir, "sessions/*.jsonl")
        ]
        files = []
        seen_files = set()
        for g in project_globs:
            for fpath in glob.glob(g):
                if fpath not in seen_files:
                    seen_files.add(fpath)
                    files.append(fpath)

        daily_map = {}
        session_map = {}

        with self._lock:
            for fpath in files:
                try:
                    stat = os.stat(fpath)
                except OSError:
                    continue

                mtime, size = stat.st_mtime, stat.st_size
                cached = self._file_cache.get(fpath)
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
                        pass
                    self._file_cache[fpath] = (mtime, size, records)

                for sid, date_str, iso_str, miss, hit, out, tot in records:
                    # 每日切片
                    if date_str not in daily_map:
                        daily_map[date_str] = {}
                    if sid not in daily_map[date_str]:
                        daily_map[date_str][sid] = {
                            "sessionId": sid,
                            "date": date_str,
                            "inputTokens": 0,
                            "cacheReadTokens": 0,
                            "outputTokens": 0,
                            "totalTokens": 0,
                            "lastActivity": iso_str
                        }
                    ds = daily_map[date_str][sid]
                    ds["inputTokens"] += miss
                    ds["cacheReadTokens"] += hit
                    ds["outputTokens"] += out
                    ds["totalTokens"] += tot
                    if iso_str > ds["lastActivity"]:
                        ds["lastActivity"] = iso_str

                    # 全生命周期会话
                    if sid not in session_map:
                        session_map[sid] = {
                            "sessionId": sid,
                            "inputTokens": 0,
                            "cacheReadTokens": 0,
                            "outputTokens": 0,
                            "totalTokens": 0,
                            "lastActivity": iso_str
                        }
                    ss = session_map[sid]
                    ss["inputTokens"] += miss
                    ss["cacheReadTokens"] += hit
                    ss["outputTokens"] += out
                    ss["totalTokens"] += tot
                    if iso_str > ss["lastActivity"]:
                        ss["lastActivity"] = iso_str

        daily_res = {d: list(s_dict.values()) for d, s_dict in daily_map.items()}
        session_res = list(session_map.values())
        return daily_res, session_res
