"""
myccusage_lib.adapters.pi:
Pi Agent 原生适配器:
- 流式解析 ~/.pi/agent/sessions/*/*.jsonl (带 mtime 增量缓存)
"""

from __future__ import annotations

import os
import glob
import json
from datetime import datetime, timezone
from .base import BaseAgentAdapter, scan_files_fast, get_candidate_home_dirs

class PiAdapter(BaseAgentAdapter):
    """Pi Agent 适配器，解析本地 jsonl 日志以提取信息"""
    agent_id = "pi"
    display_name = "Pi Agent"

    def __init__(self):
        """初始化 Pi 会话目录，支持跨环境多根探测"""
        super().__init__()
        self.base_dirs = [
            os.path.join(h, ".pi", "agent", "sessions")
            for h in get_candidate_home_dirs()
            if os.path.exists(os.path.join(h, ".pi", "agent", "sessions"))
        ]
        if not self.base_dirs:
            self.base_dirs = [os.path.expanduser("~/.pi/agent/sessions")]
        self.base_dir = self.base_dirs[0]

    def is_available(self) -> bool:
        """检查基础目录是否存在"""
        return any(os.path.exists(b) for b in self.base_dirs)

    def get_titles_and_times(self) -> tuple[dict[str, str], dict[str, str]]:
        """扫描各会话日志文件以提取用户请求作为标题"""
        titles = {}
        times = {}
        if not self.is_available():
            return titles, times

        for b in self.base_dirs:
            for p in glob.glob(os.path.join(b, "*", "*.jsonl")):
                sid = os.path.basename(p).split("_")[-1].replace(".jsonl", "")
                try:
                    with open(p, "r", encoding="utf-8") as f:
                        for line in f:
                            if not line.strip():
                                continue
                            try:
                                data = json.loads(line)
                            except Exception:
                                continue
                            if data.get("type") == "message" and data.get("message", {}).get("role") == "user":
                                content = data["message"].get("content", [])
                                t = ""
                                if isinstance(content, str):
                                    t = content.strip()
                                elif isinstance(content, list):
                                    parts = [x.get("text", "") for x in content if isinstance(x, dict) and x.get("type") == "text"]
                                    t = "".join(parts).strip()
                                if t:
                                    titles[sid] = " ".join(t.split())[:60]
                                    break
                except Exception:
                    pass
        return titles, times

    def get_source_fingerprint(self) -> str:
        """极速获取 Pi 会话目录修改状态指纹 (< 1ms)"""
        if not self.is_available():
            return ""
        hot = scan_files_fast(self.base_dirs, extensions=(".jsonl",), recursive=True, today_only=True)
        max_m = 0
        for h in hot:
            try:
                mt = os.path.getmtime(h)
                if mt > max_m:
                    max_m = mt
            except OSError:
                pass
        return f"{len(hot)}:{max_m}"

    def fetch_data(self, today_only: bool = False) -> tuple[dict[str, list[dict]], list[dict]]:
        """
        提取 Pi Agent 的会话数据。
        采用文件 mtime/size 增量缓存策略。
        - 支持 today_only: 仅扫描今日活跃文件 (提速 50x)
        """
        if not self.is_available():
            return {}, []

        fp = self.get_source_fingerprint()

        cached = self._cached_full_result(fp, today_only)
        if cached is not None:
            return cached

        all_records = []

        files = scan_files_fast(self.base_dirs, extensions=(".jsonl",), recursive=True, today_only=today_only)

        with self._lock:
            for fpath in files:
                try:
                    stat = os.stat(fpath)
                except OSError:
                    continue

                mtime, size = stat.st_mtime, stat.st_size
                cached = self._file_cache.get(fpath)
                # 使用 mtime 和 size 进行文件级防抖，提高加载性能
                if cached and cached[0] == mtime and cached[1] == size:
                    records = cached[2]
                else:
                    records = []
                    sid = os.path.basename(fpath).split("_")[-1].replace(".jsonl", "")
                    try:
                        with open(fpath, "r", encoding="utf-8") as f:
                            for line in f:
                                if "usage" not in line:
                                    continue
                                try:
                                    obj = json.loads(line)
                                except Exception:
                                    continue
                                u = (obj.get("message") or {}).get("usage")
                                if not u:
                                    continue
                                ts_str = obj.get("timestamp") or ""
                                if ts_str:
                                    try:
                                        dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                                        date_str = dt.astimezone().strftime("%Y-%m-%d")
                                        iso_str = dt.astimezone(timezone.utc).isoformat()
                                    except Exception:
                                        date_str = "1970-01-01"
                                        iso_str = ts_str
                                else:
                                    date_str = "1970-01-01"
                                    iso_str = ""

                                inp = u.get("input", 0)
                                cr = u.get("cacheRead", 0)
                                out = u.get("output", 0)
                                tot = u.get("totalTokens", 0) or (inp + cr + out)
                                if tot > 0:
                                    records.append((sid, date_str, iso_str, inp, cr, out, tot))
                    except Exception:
                        pass
                    # 将解析得到的结果存入缓存，下次无修改直接命中
                    self._file_cache[fpath] = (mtime, size, records)

                all_records.extend(records)

        daily_res, session_res = self._accumulate_records(all_records)
        self._store_full_result(fp, daily_res, session_res, today_only)
        return daily_res, session_res
