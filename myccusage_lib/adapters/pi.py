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
from .base import BaseAgentAdapter

class PiAdapter(BaseAgentAdapter):
    """Pi Agent 适配器，解析本地 jsonl 日志以提取信息"""
    agent_id = "pi"
    display_name = "Pi Agent"
    has_times = False

    def __init__(self):
        """初始化 Pi 会话目录"""
        super().__init__()
        self.base_dir = os.path.expanduser("~/.pi/agent/sessions")

    def is_available(self) -> bool:
        """检查基础目录是否存在"""
        return os.path.exists(self.base_dir)

    def get_titles_and_times(self) -> tuple[dict[str, str], dict[str, str]]:
        """扫描各会话日志文件以提取用户请求作为标题"""
        titles = {}
        times = {}
        if not self.is_available():
            return titles, times

        for p in glob.glob(os.path.join(self.base_dir, "*/*.jsonl")):
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

    def fetch_data(self) -> tuple[dict[str, list[dict]], list[dict]]:
        """
        提取 Pi Agent 的会话数据。
        采用文件 mtime/size 增量缓存策略。
        """
        if not self.is_available():
            return {}, []

        daily_map = {}
        session_map = {}

        files = glob.glob(os.path.join(self.base_dir, "*/*.jsonl"))

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

                for sid, date_str, iso_str, inp, cr, out, tot in records:
                    # 每日切片数据聚合
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
                    ds["inputTokens"] += inp
                    ds["cacheReadTokens"] += cr
                    ds["outputTokens"] += out
                    ds["totalTokens"] += tot
                    if iso_str > ds["lastActivity"]:
                        ds["lastActivity"] = iso_str

                    # 项目生命周期汇总 (全生命周期累加计算)
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
                    ss["inputTokens"] += inp
                    ss["cacheReadTokens"] += cr
                    ss["outputTokens"] += out
                    ss["totalTokens"] += tot
                    if iso_str > ss["lastActivity"]:
                        ss["lastActivity"] = iso_str

        daily_res = {d: list(s_dict.values()) for d, s_dict in daily_map.items()}
        session_res = list(session_map.values())
        return daily_res, session_res
