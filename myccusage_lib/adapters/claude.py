"""
myccusage_lib.adapters.claude:
Claude Code 原生适配器:
- 读取 ~/.claude/history.jsonl 与 ~/.claude/projects/*/*.jsonl
- 流式提取 Token，并根据 message.id 进行精准幂等去重 (解决 thinking 与 text 重复上报)
"""

from __future__ import annotations

import os
import glob
import json
from datetime import datetime, timezone
from .base import BaseAgentAdapter, scan_files_fast

class ClaudeAdapter(BaseAgentAdapter):
    """Claude Code 适配器，处理本地历史日志文件"""
    agent_id = "claude"
    display_name = "Claude Code"
    has_times = False

    def __init__(self):
        """初始化 Claude 配置目录路径"""
        super().__init__()
        self.base_dir = os.path.expanduser("~/.claude")
        self.projects_dir = os.path.join(self.base_dir, "projects")

    def is_available(self) -> bool:
        """检查目录是否存在以确定可用性"""
        return os.path.exists(self.base_dir)

    def get_titles_and_times(self) -> tuple[dict[str, str], dict[str, str]]:
        """从 history.jsonl 与各个项目的日志中提取对话标题与时间戳"""
        titles = {}
        times = {}
        if not self.is_available():
            return titles, times

        history_file = os.path.join(self.base_dir, "history.jsonl")
        if os.path.exists(history_file):
            try:
                with open(history_file, "r", encoding="utf-8") as f:
                    for line in f:
                        try:
                            obj = json.loads(line)
                            sid = obj.get("sessionId")
                            disp = obj.get("display", "").strip()
                            if sid and disp and sid not in titles:
                                titles[sid] = disp[:60]
                        except Exception:
                            pass
            except Exception:
                pass

        for p in glob.glob(os.path.join(self.projects_dir, "*/*.jsonl")):
            sid = os.path.basename(p).replace(".jsonl", "")
            if sid not in titles or titles[sid].startswith("/"):
                try:
                    with open(p, "r", encoding="utf-8") as f:
                        for line in f:
                            try:
                                obj = json.loads(line)
                            except Exception:
                                continue
                            if obj.get("type") == "user":
                                msg = obj.get("message", {})
                                cnt = msg.get("content")
                                if isinstance(cnt, str) and cnt.strip():
                                    titles[sid] = cnt.split("\n")[0][:60].strip()
                                    break
                                elif isinstance(cnt, list):
                                    for item in cnt:
                                        if isinstance(item, dict) and item.get("text"):
                                            titles[sid] = item["text"].split("\n")[0][:60].strip()
                                            break
                                    if sid in titles:
                                        break
                except Exception:
                    pass
        return titles, times

    def get_source_fingerprint(self) -> str:
        """极速获取 Claude 项目目录修改状态指纹 (< 1ms)"""
        if not self.is_available():
            return ""
        parts = []
        hist = os.path.join(self.base_dir, "history.jsonl")
        if os.path.exists(hist):
            try:
                st = os.stat(hist)
                parts.append(f"{st.st_mtime_ns}:{st.st_size}")
            except OSError:
                pass
        hot = scan_files_fast(self.projects_dir, extensions=(".jsonl",), recursive=True, today_only=True)
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
        提取 Claude 消耗数据，使用文件 mtime/size 进行防抖缓存，避免重复读取大文件。
        - 支持 today_only: 仅扫描今日活跃文件 (提速 50x)
        """
        if not self.is_available():
            return {}, []

        fp = self.get_source_fingerprint()

        # 全量模式下检查整体缓存
        if not today_only:
            with self._lock:
                if self._full_cache[0] == fp and self._full_cache[1][0] is not None:
                    return self._full_cache[1]

        daily_map = {}
        session_map = {}

        files = scan_files_fast(self.projects_dir, extensions=(".jsonl",), recursive=True, today_only=today_only)

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

                # mtime/size 防抖缓存的工作原理：对比文件的修改时间与大小，如果没有变化直接使用缓存
                if cached and cached[0] == mtime and cached[1] == size:
                    records = cached[2]
                else:
                    records = []
                    sid = os.path.basename(fpath).replace(".jsonl", "")
                    seen_msg_ids = {} # msg_id -> (date_str, iso_str, inp, cr, cw, out, tot)
                    try:
                        with open(fpath, "r", encoding="utf-8") as f:
                            for idx, line in enumerate(f):
                                if "usage" not in line:
                                    continue
                                try:
                                    obj = json.loads(line)
                                except Exception:
                                    continue
                                msg = obj.get("message") or {}
                                mid = msg.get("id")
                                u = msg.get("usage")
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

                                inp = u.get("input_tokens", 0)
                                cr = u.get("cache_read_input_tokens", 0)
                                cw = u.get("cache_creation_input_tokens", 0)
                                out = u.get("output_tokens", 0)
                                tot = inp + cr + cw + out
                                if tot == 0:
                                    continue

                                key = mid if mid else f"line_{idx}"
                                # 根据 message.id 幂等去重
                                # 保留最新的那一次上报（通常包含完整的 thinking + output_tokens），避免重复计算
                                seen_msg_ids[key] = (sid, date_str, iso_str, inp + cw, cr, out, tot)

                        records = list(seen_msg_ids.values())
                    except Exception:
                        records = cached[2] if cached else []
                    else:
                        self._file_cache[fpath] = (mtime, size, records)
                        cache_modified = True

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

            if cache_modified and not today_only:
                self._save_persisted_file_cache()

        daily_res = {d: list(s_dict.values()) for d, s_dict in daily_map.items()}
        session_res = list(session_map.values())
        if not today_only:
            with self._lock:
                self._full_cache = (fp, (daily_res, session_res))
        return daily_res, session_res

