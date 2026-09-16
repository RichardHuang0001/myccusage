"""
myccusage_lib.adapters.agy:
Google Antigravity 适配器:
- 双轨制设计 (Dual-track architecture):
  1. 若本地存在 ~/.cache/myccusage/agy_daily.json 则优先极速命中
  2. 若系统已安装 ccusage CLI，则安全调用底层 ccusage antigravity 抓取最新切片并落盘缓存
  3. 若系统未安装 ccusage CLI，则降级为本地直接解析 ~/.gemini/antigravity 目录
- 支持基于 agyhub_summaries_proto.pb 与 transcript.jsonl 的原生标题与 Prompt 提取
"""

from __future__ import annotations

import os
import re
import json
import glob
import shutil
import subprocess
from datetime import datetime, timezone
from .base import BaseAgentAdapter, ts_to_iso, ts_to_date_str

class AntigravityAdapter(BaseAgentAdapter):
    agent_id = "agy"
    display_name = "Google Antigravity"
    has_times = False

    def __init__(self):
        super().__init__()
        self.base_dir = os.path.expanduser("~/.gemini/antigravity")
        self.cache_dir = os.path.expanduser("~/.cache/myccusage")

    def is_available(self) -> bool:
        return os.path.exists(self.base_dir) or os.path.exists(os.path.join(self.cache_dir, "agy_daily.json"))

    def get_titles_and_times(self) -> tuple[dict[str, str], dict[str, str]]:
        titles = {}
        times = {}
        if not self.is_available():
            return titles, times

        proto_path = os.path.join(self.base_dir, "agyhub_summaries_proto.pb")
        if os.path.exists(proto_path):
            try:
                with open(proto_path, "rb") as f:
                    data = f.read()
                pattern = re.compile(rb"([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})")
                matches = list(pattern.finditer(data))
                for i, m in enumerate(matches):
                    uid = m.group(1).decode("ascii")
                    start = m.end()
                    end = matches[i+1].start() if i + 1 < len(matches) else len(data)
                    slice_data = data[start:min(start+300, end)]
                    text_matches = re.findall(rb"[\x20-\x7e\x80-\xff]{4,}", slice_data)
                    for tm in text_matches:
                        try:
                            t = tm.decode("utf-8").strip().strip("\"'%,!\t ")
                            if (len(t) > 3 and not re.match(r"^[0-9a-f-]{36}$", t) 
                                and not t.startswith("outside") 
                                and not t.startswith("file://") 
                                and not t.startswith("git@")
                                and not t.startswith("main")
                                and not t.endswith("R")
                                and "/" not in t):
                                if uid not in titles:
                                    titles[uid] = t
                                    break
                        except Exception:
                            pass
            except Exception:
                pass

        logs_glob = os.path.join(self.base_dir, "brain/*/.system_generated/logs/transcript.jsonl")
        for log_path in glob.glob(logs_glob):
            parts = log_path.split(os.sep)
            uid = ""
            for idx, p in enumerate(parts):
                if p == "brain" and idx + 1 < len(parts):
                    uid = parts[idx + 1]
                    break
            if not uid:
                uid = parts[-4]

            if uid not in titles or titles[uid].endswith(":") or len(titles[uid]) < 4:
                try:
                    with open(log_path, "r", encoding="utf-8") as f:
                        first_line = f.readline()
                        if first_line:
                            obj = json.loads(first_line)
                            content = obj.get("content", "")
                            if "<USER_REQUEST>" in content:
                                req = content.split("<USER_REQUEST>")[1].split("</USER_REQUEST>")[0].strip()
                            else:
                                req = content.strip()
                            first_line_clean = req.split("\n")[0][:60].strip()
                            if first_line_clean:
                                titles[uid] = first_line_clean
                except Exception:
                    pass

        return titles, times

    def fetch_data(self) -> tuple[dict[str, list[dict]], list[dict]]:
        if not self.is_available():
            return {}, []

        cache_file = os.path.join(self.cache_dir, "agy_daily.json")
        has_ccusage = shutil.which("ccusage") is not None

        # 内存快速命中 (若 60 秒内已读取过，直接返回)
        with self._lock:
            if hasattr(self, "_cached_res") and self._cached_res:
                c_time, c_val = self._cached_res
                import time
                if time.time() - c_time < 60.0:
                    return c_val

        # 方案 A: 若有 ccusage 命令，调用 ccusage antigravity 抓取并同步缓存
        if has_ccusage:
            try:
                res = subprocess.run(["ccusage", "antigravity", "session", "--json", "--offline"],
                                     capture_output=True, text=True, timeout=10)
                if res.returncode == 0:
                    data = json.loads(res.stdout)
                    raw_sessions = data.get("sessions", [])
                    daily_map = {}
                    session_list = []
                    for s in raw_sessions:
                        tot = s.get("totalTokens", 0)
                        if tot <= 0:
                            continue
                        sid = s.get("sessionId", "")
                        inp = s.get("inputTokens", 0)
                        cr = s.get("cacheReadTokens", 0)
                        out = s.get("outputTokens", 0)
                        last_act = s.get("lastActivity") or s.get("firstActivity") or ""
                        date_str = last_act[:10] if last_act else "1970-01-01"

                        rec = {
                            "sessionId": sid,
                            "date": date_str,
                            "inputTokens": inp,
                            "cacheReadTokens": cr,
                            "outputTokens": out,
                            "totalTokens": tot,
                            "lastActivity": last_act
                        }
                        if date_str not in daily_map:
                            daily_map[date_str] = []
                        daily_map[date_str].append(rec)

                        session_list.append({
                            "sessionId": sid,
                            "inputTokens": inp,
                            "cacheReadTokens": cr,
                            "outputTokens": out,
                            "totalTokens": tot,
                            "lastActivity": last_act
                        })

                    try:
                        os.makedirs(self.cache_dir, exist_ok=True)
                        with open(cache_file, "w", encoding="utf-8") as f:
                            json.dump(daily_map, f)
                    except Exception:
                        pass

                    res_pair = (daily_map, session_list)
                    with self._lock:
                        import time
                        self._cached_res = (time.time(), res_pair)
                    return res_pair
            except Exception:
                pass

        # 方案 B: 若 ccusage 不可用或调用失败，读取本地 agy_daily.json 缓存
        if os.path.exists(cache_file):
            try:
                with open(cache_file, "r", encoding="utf-8") as f:
                    daily_map = json.load(f)
                session_list = []
                for d_str, records in daily_map.items():
                    for r in records:
                        session_list.append({
                            "sessionId": r.get("sessionId"),
                            "inputTokens": r.get("inputTokens", 0),
                            "cacheReadTokens": r.get("cacheReadTokens", 0),
                            "outputTokens": r.get("outputTokens", 0),
                            "totalTokens": r.get("totalTokens", 0),
                            "lastActivity": r.get("lastActivity", "")
                        })
                res_pair = (daily_map, session_list)
                with self._lock:
                    import time
                    self._cached_res = (time.time(), res_pair)
                return res_pair
            except Exception:
                pass

        return {}, []
